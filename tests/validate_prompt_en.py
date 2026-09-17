# -*- coding: utf-8 -*-
"""
Validation of the English task track.

The Russian track is the canonical one: the published runs answered it.
English was added alongside and has to satisfy four conditions.

1. The Russian prompt has not changed. It is compared with the version
   from git: if the bytes diverged, the published runs have stopped
   being reproducible.
2. The English prompt has no Cyrillic -- not in the role, not in the
   catalog, not in the observation, not in the plant's replies. An
   untranslated fragment would reach the model silently.
3. The catalog matches in content and order: the same 133 identifiers.
   The task has to be the same; only the language of its description
   may differ.
4. The task briefings match the ones the trainer shows (i18n.js,
   I18N_SCEN). Otherwise a person in the demo and a model in a run
   would be reading different conditions.

Usage:  python tests/validate_prompt_en.py
"""

import io
import json
import os
import re
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from nh3twin import llm_policy as LP                                # noqa: E402
from nh3twin import prompt_en as PE                                 # noqa: E402
from nh3twin.actions import CATALOG                                 # noqa: E402
from nh3twin.episode import Episode, build_observation              # noqa: E402
from nh3twin.scenarios import SCENARIOS                             # noqa: E402

RU = re.compile("[Ѐ-ӿ]")
BASE = "9840c4e"        # the commit before the work on the demo


def _old_module(rev: str):
    """The llm_policy module from a given revision -- for comparing the prompt.
    """
    src = subprocess.run(["git", "-C", ROOT, "show",
                          rev + ":nh3twin/llm_policy.py"],
                         capture_output=True, text=True,
                         encoding="utf-8").stdout
    if not src:
        return None
    src = re.sub(r"^from \.(\w+)", r"from nh3twin.\1", src, flags=re.M)
    mod = types.ModuleType("old_llm_policy")
    sys.modules["old_llm_policy"] = mod
    exec(compile(src, "old_llm_policy", "exec"), mod.__dict__)
    return mod


def check_ru_unchanged(fails):
    old = _old_module(BASE)
    if old is None:
        print("  русский промпт: базовая ревизия недоступна, пропуск")
        return
    ep = Episode(SCENARIOS["S1"], seed=1)
    obs = build_observation(ep)
    legal = ep.legal_actions()
    pairs = [
        ("системная часть", old.system_prompt(), LP.system_prompt()),
        ("часть задания", old.user_prompt(obs, legal, ep, 14),
         LP.user_prompt(obs, legal, ep, 14)),
    ]
    for what, a, b in pairs:
        if a == b:
            print(f"  русский промпт, {what}: совпадает "
                  f"({len(b.encode())} байт)")
        else:
            fails.append(f"русский промпт разошёлся: {what}")


def check_en_clean(fails):
    n = PE.check(verbose=False)
    if n:
        fails.append(f"английский трек: мест без перевода {n}")
        PE.check(verbose=True)
    else:
        print("  английский трек: роль, каталог, вводные и ответы "
              "имитатора -- без кириллицы")

    # Observations of all six tasks at several points.
    bad = 0
    for sid, scen in SCENARIOS.items():
        ep = Episode(SCENARIOS[sid], seed=1)
        for _ in range(3):
            txt = PE.obs_text(build_observation(ep).render(),
                              scen.brief, sid)
            for line in txt.split("\n"):
                if RU.search(line):
                    bad += 1
                    if bad <= 5:
                        print("    остался русский:", line.strip()[:100])
            ep.advance(400)
    if bad:
        fails.append(f"наблюдения: строк с кириллицей {bad}")
    else:
        print("  наблюдения шести задач (по три точки): без кириллицы")

    # The full prompt as a whole -- as it will go to the model.
    ep = Episode(SCENARIOS["S2"], seed=1)
    obs = build_observation(ep)
    for what, text in (("системная часть", LP.system_prompt("en")),
                       ("часть задания",
                        LP.user_prompt(obs, ep.legal_actions(), ep, 14,
                                       "en"))):
        if RU.search(text):
            fails.append(f"английский промпт, {what}: есть кириллица")
        else:
            print(f"  английский промпт, {what}: {len(text.encode())} байт, "
                  f"кириллицы нет")


def check_catalog(fails):
    ru_ids = re.findall(r"^  ([A-Z][A-Z0-9_:\-]*) — ", LP.catalog_text(),
                        re.M)
    en_ids = re.findall(r"^  ([A-Z][A-Z0-9_:\-]*) — ", PE.catalog_text(),
                        re.M)
    if ru_ids == en_ids and len(en_ids) == len(CATALOG):
        print(f"  каталог: {len(en_ids)} идентификаторов, состав и порядок "
              f"совпадают")
    else:
        fails.append(f"каталог разошёлся: ru {len(ru_ids)}, en {len(en_ids)}, "
                     f"в коде {len(CATALOG)}")


def check_briefs(fails):
    """The task briefings must match the ones the trainer shows."""
    try:
        import quickjs
    except ImportError:
        print("  вводные: quickjs не установлен, сверка с i18n.js пропущена")
        return
    src = io.open(os.path.join(ROOT, "trainer", "i18n.js"),
                  encoding="utf-8").read()
    head = src[:src.index("\nfunction ")]
    ctx = quickjs.Context()
    ctx.eval(head)
    scen = json.loads(ctx.eval("JSON.stringify(I18N_SCEN)"))
    n_ok = 0
    for sid, en in sorted(PE.SCEN_EN.items()):
        ui = (scen.get(sid) or {}).get("brief", "")
        if ui == en:
            n_ok += 1
        else:
            fails.append(f"вводная {sid} в промпте и в интерфейсе разная")
            print(f"    {sid} промпт:    {en[:70]}")
            print(f"    {sid} интерфейс: {ui[:70]}")
    if n_ok == len(PE.SCEN_EN):
        print(f"  вводные: {n_ok} из {len(PE.SCEN_EN)} совпадают с "
              f"интерфейсом дословно")


def main():
    fails = []
    print("русский трек:")
    check_ru_unchanged(fails)
    print("английский трек:")
    check_en_clean(fails)
    check_catalog(fails)
    check_briefs(fails)
    print()
    if fails:
        print("НЕ СОШЛОСЬ:", len(fails))
        for f in fails:
            print("  -", f)
        return 1
    print("всё сошлось")
    return 0


if __name__ == "__main__":
    sys.exit(main())
