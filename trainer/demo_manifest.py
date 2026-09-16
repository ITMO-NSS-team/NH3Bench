# -*- coding: utf-8 -*-
"""
Манифест демонстрации: что интерфейсу известно о существующих прогонах.

    py trainer/demo_manifest.py                      # собрать манифест
    py trainer/demo_manifest.py --selftest           # проверить часы replay
    py trainer/demo_manifest.py --traces-out DIR     # выгрузить лёгкие трейсы

Зачем отдельный слой. Тренажёр до сих пор знал об эталонных исходах из
вписанного руками словаря REF в build_trainer.py, а о 24 сохранённых трейсах
не знал вообще. Пока список моделей и сценариев живёт в коде интерфейса,
каждый новый прогон требует правки JS; с манифестом достаточно пересобрать
HTML. Это прямое требование: набор сценариев не закрыт (ожидается пересъёмка
S3), и появление седьмой строки в матрице не должно быть работой программиста.

Счёт НЕ пересчитывается здесь заново. Обоснованность аварийного останова
берётся из tests/report_metrics.esd_justification, а сам балл -- из
nh3twin.metrics.bench_score_run, то есть ровно теми же функциями, что печатают
официальную таблицу. Иначе демонстрация со временем начала бы показывать числа,
расходящиеся с публикацией, причём незаметно.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Логика счёта живёт в tests/ и переиспользуется, а не дублируется: скопированная
# формула разъедется с официальной таблицей при первой же правке метрик.
sys.path.insert(0, os.path.join(ROOT, "tests"))

from nh3twin import metrics as M                                    # noqa: E402
from nh3twin.episode import POLL_PERIOD, THINK_RATE                 # noqa: E402
from nh3twin.actions import CATALOG, CATALOG_BY_ID                  # noqa: E402
from nh3twin.scenarios import SCENARIOS                             # noqa: E402
import report_metrics as R                                          # noqa: E402


# Пути по умолчанию повторяют дефолты report_metrics: прогоны нового сценария
# законно лежат в собственном файле (base_S6.jsonl, ponr_S6.json).
BASE_GLOBS = ["results/baselines.jsonl", "results/base_S*.jsonl"]
# Опубликованные прогоны моделей: по файлу на модель, перечислены явно.
# Маской нельзя -- рядом лежат осколки по одной задаче (…_S3.jsonl), куски
# докачки (…_head/…_tail/…_partial/…_resumed), перепроверки (…_replayed) и
# архивы прежних версий двойника (…_archive, …_v1). Появление нового файла
# сборка замечает сама (_unlisted_llm) и говорит об этом вслух.
LLM_GLOBS = [
    "results/llm.jsonl",                    # четыре модели Claude, 24 прогона
    "results/llm_gpt-5.6-luna.jsonl",
    "results/llm_gpt-5.6-sol.jsonl",
    "results/llm_gpt-5.6-terra.jsonl",
    "results/llm_gpt-6-astra.jsonl",
    "results/glm-5.3_zai_r1.jsonl",
]
# Что в results/ заведомо не итоговый файл прогона.
LLM_SKIP = re.compile(r"(_S\d+|_head|_tail|_partial|_resumed|_replayed"
                      r"|_archive|_v\d+)\.jsonl$")
# Прогоны, измеренные пользователем самостоятельно (benchmark.py run). Лежат
# отдельно от опубликованной матрицы и помечены в таблице как свои: 24
# опубликованных прогона сделаны в прежнем порядке и пересъёмке не подлежат.
USER_GLOBS = ["results/user/*.jsonl"]
PONR_GLOBS = ["results/ponr.json", "results/ponr_S*.json"]
OUT = "trainer/demo_manifest.json"

# Поля трейса, нужные интерфейсу. `obs` сознательно отброшен: наблюдение
# генерирует сам твин при воспроизведении (он детерминирован), а хранение
# 24 копий текста щита раздувает манифест с 1.3 до 6.4 МБ. Воссоздать нельзя
# только ответ модели -- он и остаётся.
TRACE_KEEP = ("t_rel", "action", "status", "tokens", "wall_s", "error", "reply")


# =========================================================================
# Загрузка
# =========================================================================

def _load_rows(globs, src="base"):
    """Строки прогонов с пометкой источника.

    Источник нужен для склейки: один и тот же слаг модели, измеренный
    пользователем, не должен слиться с опубликованной строкой.
    """
    rows = []
    for pat in globs:
        for path in sorted(glob.glob(os.path.join(ROOT, pat))):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        r = json.loads(line)
                        r["_src"] = src
                        rows.append(r)
    return rows


def _base_model(policy: str) -> str:
    """Модель без пометки прогона: llm:gpt-5.6-terra:re-high -> gpt-5.6-terra.

    Третий сегмент -- это метка конкретного прогона (уровень раздумий,
    номер повтора, подписка провайдера), а не другая модель.
    """
    parts = (policy or "").split(":")
    return parts[1] if len(parts) > 1 and parts[0] == "llm" else ""


def _unlisted_llm(globs=None):
    """Файлы, в которых есть модель, не показанная в демо вовсе.

    Список файлов задан руками, и это правильно: рядом лежат осколки и
    архивы. Но новая модель не должна пропасть молча. Исследования
    чувствительности (те же модели под другими метками прогона) молчат:
    они не отдельные участники таблицы, а разброс уже показанного.
    """
    listed_files, shown = set(), set()
    for pat in (globs or LLM_GLOBS):
        for path in glob.glob(os.path.join(ROOT, pat)):
            listed_files.add(path)
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        shown.add(_base_model(json.loads(line).get("policy")))
    shown.discard("")
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "results", "*.jsonl"))):
        if path in listed_files or LLM_SKIP.search(os.path.basename(path)):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                new_models = {
                    _base_model(json.loads(line).get("policy"))
                    for line in fh if line.strip()}
        except (ValueError, OSError):
            continue
        new_models -= shown | {""}
        if new_models:
            out.append("%s (%s)"
                       % (os.path.relpath(path, ROOT).replace(os.sep, "/"),
                          ", ".join(sorted(new_models))))
    return out


def _load_ponr(globs):
    out = {}
    for pat in globs:
        for path in sorted(glob.glob(os.path.join(ROOT, pat))):
            with open(path, encoding="utf-8") as fh:
                out.update(json.load(fh))
    return out


def _commit() -> str:
    """Версия бенчмарка. Без неё запись в таблице невозможно воспроизвести."""
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# =========================================================================
# Сборка
# =========================================================================

def _trace_stats(path):
    """Сводка по трейсу: сколько решений и насколько дорого думала модель."""
    if not path:
        return None
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None
    toks, steps = [], 0
    with open(full, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            steps += 1
            toks.append(int(json.loads(line).get("tokens") or 0))
    if not steps:
        return None
    return {
        "n_decisions": steps,
        "tokens_total": sum(toks),
        "tokens_median": int(statistics.median(toks)),
        "tokens_max": max(toks),
        # Виртуальные секунды, купленные размышлением. Главная величина
        # демонстрации: именно она объясняет, почему верный ответ опоздал.
        "think_s_total": round(sum(toks) / THINK_RATE, 1),
    }


def _run_id(row) -> str:
    return f"{row['policy']}|{row['scenario']}|{row.get('seed', 1)}"


def _dedup(rows):
    """
    Одна клетка -- один прогон, побеждает последний прочитанный.

    Клетки S6 лежат и в общем baselines.jsonl, и в собственном base_S6.jsonl
    (так их и считали), поэтому без склейки сценарий попадал в манифест
    дважды и число доступных записей оказывалось завышенным.
    """
    out = {}
    for r in rows:
        out[(r.get("scenario"), r.get("policy"), r.get("seed"),
             r.get("_src", "base"), _lang(r))] = r
    return list(out.values())


def _lang(row) -> str:
    """Язык задания прогона. Опорные политики промпта не видят -- ru."""
    return ((row.get("llm") or {}).get("prompt_lang") or "ru")


def _run_key(row) -> str:
    """Идентификатор прогона в манифесте: источник + политика + задача.

    Собирается в одном месте: самопроверка ищет трейс по этому же ключу, и
    расхождение оставило бы её без данных -- молча, с нулём проверенных
    шагов вместо двух тысяч.
    """
    lang = _lang(row)
    return (row.get("_src", "base") + "/" + _run_id(row)
            + ("" if lang == "ru" else "@" + lang))


def build(base_globs=BASE_GLOBS, llm_globs=LLM_GLOBS, ponr_globs=PONR_GLOBS,
          user_globs=USER_GLOBS):
    for f in _unlisted_llm(llm_globs):
        print("ВНИМАНИЕ: в демо нет модели из %s -- допишите файл в "
              "LLM_GLOBS (trainer/demo_manifest.py)" % f, file=sys.stderr)
    base = _load_rows(base_globs, "base")
    llm = _load_rows(llm_globs, "llm")
    user = _load_rows(user_globs, "user")
    allrows = _dedup(base + llm + user)

    by = {(r.get("scenario"), r.get("policy"), r.get("seed")): r
          for r in allrows}
    just, just_why = R.esd_justification(by)
    ponr = _load_ponr(ponr_globs)

    runs = []
    for row in allrows:
        sid = row["scenario"]
        # bench_score_run требует признак обоснованности на строке; он выводится
        # из прогонов π_null/π_esd, а не назначается мнением.
        row = dict(row, esd_justified=just.get(sid, False))
        pol = row["policy"]
        is_model = pol.startswith("llm:")
        trace = row.get("trace")
        runs.append({
            "id": _run_key(row),
            "kind": ("user" if row.get("_src") == "user"
                     else "model" if is_model else "policy"),
            "agent": pol[4:] if is_model else pol,
            "policy": pol,
            "scenario": sid,
            "seed": row.get("seed", 1),
            "prompt_lang": _lang(row),
            "score": M.bench_score_run(row),
            "outcome": R.outcome(row),
            "prevented": bool(row.get("prevented")),
            "clean": M.clean(row),
            "CAT": row.get("CAT") or [],
            "MAJ": row.get("MAJ") or [],
            "barriers": row.get("barriers") or [],
            "esd": bool(row.get("esd")),
            "esd_justified": just.get(sid, False),
            "t_end_s": row.get("t_end_s"),
            "horizon_s": row.get("horizon_s"),
            "n_steps": row.get("n_steps"),
            "trace": trace,
            "watchable": bool(_trace_stats(trace)),
            "trace_stats": _trace_stats(trace),
        })

    scenarios = []
    for sid, scen in SCENARIOS.items():
        p = ponr.get(sid) or {}
        scenarios.append({
            "sid": sid,
            "title": scen.title,
            "brief": scen.brief,
            "hazard": scen.hazard,
            "trap": scen.trap,
            "key_actions": list(scen.key_actions),
            "horizon_s": scen.horizon_s,
            "ponr_cat_s": p.get("ponr_cat_s"),
            "ponr_clean_s": p.get("ponr_clean_s"),
        })
    # Сценарии, встреченные в данных, но отсутствующие в реестре, тоже попадают
    # в манифест: пересъёмка S3 может приехать как отдельная строка.
    known = {s["sid"] for s in scenarios}
    for sid in sorted({r["scenario"] for r in runs} - known):
        scenarios.append({"sid": sid, "title": sid, "brief": "",
                          "hazard": "", "trap": "", "key_actions": [],
                          "horizon_s": None, "ponr_cat_s": None,
                          "ponr_clean_s": None})

    agents = {}
    for r in runs:
        a = agents.setdefault(
            r["kind"] + "|" + r["prompt_lang"] + "|" + r["agent"], {
                "id": r["agent"], "kind": r["kind"],
                "prompt_lang": r["prompt_lang"],
                "scores": {}, "watchable": 0,
            })
        a["scores"][r["scenario"]] = r["score"]
        a["watchable"] += 1 if r["watchable"] else 0
    n_total = len({s["sid"] for s in scenarios})
    for a in agents.values():
        vals = list(a["scores"].values())
        a["score_mean"] = round(sum(vals) / len(vals), 1) if vals else None
        a["score_worst"] = min(vals) if vals else None
        # Полнота строки. Среднее по двум задачам из шести -- не то же число,
        # что среднее по шести, и ставить их в один столбец без пометки
        # значит вводить в заблуждение тем вернее, чем аккуратнее таблица.
        a["n_scored"] = len(vals)
        a["n_total"] = n_total
        a["complete"] = len(vals) == n_total
        name, desc = R.policy_legend(a["id"] if a["kind"] == "policy"
                                     else "llm:" + a["id"])
        if a["kind"] == "user":
            name = f"{a['id']} (свой прогон)"
            desc = ("измерено пользователем через benchmark.py run; не часть "
                    "опубликованной матрицы")
        if a.get("prompt_lang", "ru") != "ru":
            # Задание на другом языке -- другой столбец, а не та же строка:
            # опубликованные прогоны отвечали на русское задание.
            name += f", задание {a['prompt_lang'].upper()}"
            desc += ("; задание на языке " + a["prompt_lang"].upper()
                     + ", напрямую с русским треком не сравнивается")
        a["label"], a["desc"] = name, desc

    # Regulation Gap считается относительно того же оппонента, что в отчёте,
    # и только для полных строк: разность средних по разным наборам задач --
    # не разрыв с регламентом, а бессмыслица.
    reg = agents.get("policy|ru|regulation", {}).get("score_mean")
    for a in agents.values():
        a["reg_gap"] = (round(a["score_mean"] - reg, 1)
                        if (reg is not None and a["score_mean"] is not None
                            and a["complete"])
                        else None)

    return {
        "built_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "benchmark": {
            "commit": _commit(),
            "think_rate_tok_per_s": THINK_RATE,
            "poll_period_s": POLL_PERIOD,
            "catalog_size": len(CATALOG),
            # Канонический язык промпта сохранённых прогонов. Английский трек
            # добавляется отдельно и помечается здесь же, иначе сравнивать
            # строки таблицы между языками будет нельзя.
            "prompt_lang": "ru",
            "token_accounting": "output_tokens",
        },
        # Обоснованность аварийного останова по сценариям. Прогон человека
        # считается в браузере той же bench_score_run, а ей нужен этот
        # признак; выводится он из опорных политик, поэтому приходит отсюда,
        # а не назначается в интерфейсе.
        "esd_just": {sid: bool(just.get(sid, False))
                     for sid in sorted({s["sid"] for s in scenarios})},
        "esd_just_why": {sid: just_why.get(sid, "")
                         for sid in sorted({s["sid"] for s in scenarios})},
        "scenarios": sorted(scenarios, key=lambda s: s["sid"]),
        "agents": sorted(agents.values(),
                         key=lambda a: (a["kind"] == "user",
                                        a["kind"] != "model",
                                        -(a["score_mean"] or 0))),
        "runs": sorted(runs, key=lambda r: (r["scenario"], r["agent"])),
    }


def light_traces(manifest):
    """Трейсы без поля obs -- источник истины для Watch."""
    out = {}
    for r in manifest["runs"]:
        if not r["watchable"]:
            continue
        path = r["trace"]
        full = path if os.path.isabs(path) else os.path.join(ROOT, path)
        steps = []
        with open(full, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                steps.append({k: rec.get(k) for k in TRACE_KEEP})
        out[r["id"]] = steps
    return out


# =========================================================================
# Самопроверка часов
# =========================================================================

def selftest(manifest) -> int:
    """
    Проверка, без которой Watch показывал бы вымысел: время в трейсе и время
    воспроизведения должны быть связаны каноническими часами

        t_действия = t_наблюдения + токены/THINK_RATE + задержка команды

    Последний шаг исключён: эпизод мог кончиться, пока модель думала (именно
    это и произошло у Haiku в S1 -- верное решение опоздало на 17 с).
    """
    rows = {r["id"]: r for r in manifest["runs"]}
    worst, checked, bad = 0.0, 0, []
    for rid, steps in light_traces(manifest).items():
        row = rows[rid]
        tp = None
        for src in (_load_rows(LLM_GLOBS, "llm")
                    + _load_rows(USER_GLOBS, "user")):  # noqa: E501
            if _run_key(src) == rid:
                tp = src.get("t_per_step")
                break
        if not tp:
            continue
        for i, (s, t) in enumerate(list(zip(steps, tp))[:-1]):
            a = CATALOG_BY_ID.get(s["action"])
            exp = s["t_rel"] + (s["tokens"] or 0) / THINK_RATE + (a.latency if a else 0)
            d = abs(exp - t)
            worst = max(worst, d)
            checked += 1
            if d > 1.0:
                bad.append((rid, i, round(d, 1)))
        _ = row
    print(f"проверено шагов: {checked}; макс. отклонение {worst:.2f} с; "
          f"вне допуска: {len(bad)}")
    for b in bad[:10]:
        print("  расхождение:", b)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--traces-out", default="",
                    help="каталог для лёгких трейсов (по одному JSON на прогон)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    man = build()
    if args.selftest:
        sys.exit(selftest(man))

    path = os.path.join(ROOT, args.out)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)
    n_watch = sum(1 for r in man["runs"] if r["watchable"])
    print(f"манифест: {args.out} "
          f"({os.path.getsize(path) / 1024:.0f} КБ); "
          f"сценариев {len(man['scenarios'])}, "
          f"агентов {len(man['agents'])}, "
          f"прогонов {len(man['runs'])}, из них для показа {n_watch}")

    if args.traces_out:
        d = os.path.join(ROOT, args.traces_out)
        os.makedirs(d, exist_ok=True)
        tot = 0
        for rid, steps in light_traces(man).items():
            name = rid.replace(":", "_").replace("|", "_") + ".json"
            p = os.path.join(d, name)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(steps, fh, ensure_ascii=False)
            tot += os.path.getsize(p)
        print(f"трейсы: {args.traces_out} ({tot / 1e6:.1f} МБ без obs)")


if __name__ == "__main__":
    main()
