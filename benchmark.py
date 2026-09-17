# -*- coding: utf-8 -*-
"""
NH3Bench -- running the benchmark on your own model.

    python benchmark.py list-scenarios
    python benchmark.py list-policies
    python benchmark.py validate
    python benchmark.py run --provider openrouter --model google/gemini-3.7-flash --scenarios S1
    python benchmark.py replay
    python benchmark.py report

This is a thin wrapper: a run is executed by tests/run_llm.py, the
re-derivation by tests/replay_llm.py, and the full table by
tests/report_metrics.py. What lives here is a single entry point, sane
defaults and the provenance of a run. The scoring logic is not
duplicated: the score and the Regulation Gap come from the same
functions that print the published table.

On repeated runs. The benchmark environment is deterministic and the
scenario seed is always 1 -- the only source of spread is the model
itself. Repeats are therefore given as a number of trials (--trials)
rather than as seeds: a trial gets a label and the seed stays as it is.
Changing the seed would change the task itself, and the runs would no
longer be comparable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "trainer"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

ALL_SIDS = "S1,S2,S3,S4,S5,S6"


# =========================================================================
# Catalogs
# =========================================================================

def cmd_list_scenarios(args):
    from nh3twin.scenarios import SCENARIOS
    print(f"{'код':5s}{'горизонт':>10s}  название")
    for sid, sc in SCENARIOS.items():
        print(f"{sid:5s}{sc.horizon_s / 60:8.0f} мин  {sc.title}")
    print("\nПодсказки по решению намеренно не печатаются: они в "
          "docs/SCENARIOS.md, и читать их перед прогоном модели -- значит "
          "испортить измерение.")
    return 0


def cmd_list_policies(args):
    import importlib
    rm = importlib.import_module("report_metrics")
    print("Эталонные политики (запускаются tests/run_baselines.py):\n")
    for pid, (name, desc) in rm.POLICY_LEGEND.items():
        print(f"  {pid:11s} {name}")
        for line in _wrap(desc, 66):
            print(f"              {line}")
    print("\nРазрыв с регламентом считается относительно policy "
          "'regulation'.")
    return 0


def _wrap(text, width):
    import textwrap
    return textwrap.wrap(text, width)


# =========================================================================
# Sanity check
# =========================================================================

def cmd_validate(args):
    """
    Quick check that the plant computes on this machine and gives what is
    claimed. The full run is enabled by --run: it takes about a minute, because
    the task starts with bringing the plant up to its regime.
    """
    ok = True

    def say(name, good, detail=""):
        nonlocal ok
        ok = ok and good
        print(f"  [{'ok ' if good else 'ПЛОХО'}] {name}"
              + (f" -- {detail}" if detail else ""))

    print("1. Импорт имитатора")
    try:
        import numpy
        from nh3twin.actions import CATALOG
        from nh3twin.scenarios import SCENARIOS
        from nh3twin.episode import THINK_RATE, POLL_PERIOD
        say("numpy", True, numpy.__version__)
        say("таблица свойств аммиака", os.path.exists(
            os.path.join(ROOT, "nh3twin", "_nh3_table.npz")),
            "без неё первый импорт требует CoolProp")
        say("каталог действий", len(CATALOG) == 133, f"{len(CATALOG)} команд")
        say("сценарии", len(SCENARIOS) >= 6, ", ".join(SCENARIOS))
        say("часы задачи", THINK_RATE == 40.0 and POLL_PERIOD == 10.0,
            f"{THINK_RATE:.0f} токенов в секунду, опрос {POLL_PERIOD:.0f} с")
    except Exception as e:
        say("импорт", False, f"{type(e).__name__}: {e}")
        return 1

    print("2. Свойства аммиака")
    try:
        from nh3twin import props
        p = props.Psat(243.15)
        t = props.Tsat(p)
        say("обратимость Psat/Tsat", abs(t - 243.15) < 0.05,
            f"расхождение {abs(t - 243.15):.4f} K")
    except Exception as e:
        say("свойства", False, f"{type(e).__name__}: {e}")

    print("3. Провайдеры моделей")
    try:
        from nh3twin.providers import PROVIDERS, load_dotenv
        keys = load_dotenv(os.path.join(ROOT, ".env"))
        say("список провайдеров", True, ", ".join(PROVIDERS))
        has = bool(os.environ.get("OPENROUTER_API_KEY"))
        say("ключ OpenRouter", True,
            "найден" if has else "не задан (нужен только для --provider "
                                "openrouter)")
        _ = keys
    except Exception as e:
        say("провайдеры", False, f"{type(e).__name__}: {e}")

    if args.run:
        print("4. Прогон бездействия на S1 (эталон: КАТ-3 около 614 с)")
        try:
            from nh3twin.episode import Episode
            from nh3twin.policies import NullPolicy
            from nh3twin.scenarios import SCENARIOS
            ep = Episode(SCENARIOS["S1"], seed=1)
            r = ep.run(NullPolicy())
            good = ("CAT-3" in (r.get("CAT") or [])
                    and 550 < r.get("t_end_s", 0) < 700)
            say("исход", good,
                f"КАТ={r.get('CAT')} при t={r.get('t_end_s'):.0f} с")
            need = ("scenario", "policy", "CAT", "MAJ", "t_end_s",
                    "horizon_s", "operators", "tokens", "n_steps")
            miss = [k for k in need if k not in r]
            say("обязательные поля результата", not miss,
                "все на месте" if not miss else f"нет: {miss}")
        except Exception as e:
            say("прогон", False, f"{type(e).__name__}: {e}")
    else:
        print("4. Прогон пропущен (добавьте --run, около минуты)")

    print("\n" + ("ГОТОВО: установка считается." if ok else
                  "ЕСТЬ ПРОБЛЕМЫ, см. выше."))
    return 0 if ok else 1


# =========================================================================
# Running a model
# =========================================================================

def cmd_run(args):
    sids = args.scenarios or ALL_SIDS
    out = args.out or os.path.join(ROOT, "results", "llm.jsonl")
    # Transcripts are placed next to the result. For a standard run that is the
    # shared results/llm_traces directory; for a run into a file of your own it
    # is a directory of your own, or a trial would land in the published matrix
    # on the next re-derivation.
    trace_dir = args.trace_dir or (
        os.path.join(ROOT, "results", "llm_traces")
        if os.path.abspath(out) == os.path.join(ROOT, "results", "llm.jsonl")
        else os.path.splitext(out)[0] + "_traces")

    if args.provider == "openrouter":
        from nh3twin.providers import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        if not os.environ.get(args.api_key_env):
            print(f"Нет ключа: положите {args.api_key_env} в .env в корне "
                  f"проекта или в переменную среды.", file=sys.stderr)
            return 2

    # Flushing the buffer is required: a subprocess writes into the same stream
    # next, and without the flush the header ends up at the end of the file
    # when the log is redirected.
    print(f"модель:     {args.model} через {args.provider}")
    print(f"задачи:     {sids}")
    print(f"попыток:    {args.trials} (сид окружения всегда 1)")
    if args.prompt_lang != "ru":
        print(f"язык задания: {args.prompt_lang} -- отдельный трек, с "
              f"опубликованными русскими прогонами не сравнивается напрямую")
    print(f"результаты: {os.path.relpath(out, ROOT)}")
    print(f"протоколы:  {os.path.relpath(trace_dir, ROOT)}")
    print("Одно решение -- один вызов модели; эпизод это от нескольких "
          "минут до часа.\n", flush=True)

    rc = 0
    for trial in range(1, args.trials + 1):
        # A trial is a label, not another seed: the task has to stay the same,
        # or the runs are not comparable.
        tag = "" if args.trials == 1 else f"t{trial}"
        cmd = [sys.executable, os.path.join("tests", "run_llm.py"),
               "--provider", args.provider,
               "--model", args.model,
               "--scenarios", sids,
               "--seeds", "1",
               "--history", str(args.history),
               "--timeout", str(args.timeout),
               "--out", out,
               "--prompt-lang", args.prompt_lang,
               "--trace-dir", trace_dir]
        if tag:
            cmd += ["--tag", tag]
        if args.base_url:
            cmd += ["--base-url", args.base_url]
        if args.temperature is not None:
            cmd += ["--temperature", str(args.temperature)]
        if args.max_tokens is not None:
            cmd += ["--max-tokens", str(args.max_tokens)]
        if args.trials > 1:
            print(f"== попытка {trial} из {args.trials}", flush=True)
        rc = subprocess.call(cmd, cwd=ROOT) or rc

    print("\nДальше: python benchmark.py report", flush=True)
    return rc


# =========================================================================
# Re-derivation and reporting
# =========================================================================

def cmd_replay(args):
    return subprocess.call(
        [sys.executable, os.path.join("tests", "replay_llm.py")], cwd=ROOT)


def cmd_report(args):
    if args.full:
        return subprocess.call(
            [sys.executable, os.path.join("tests", "report_metrics.py")],
            cwd=ROOT)

    # The compact table. The score comes from the same place as the official
    # one: demo_manifest reuses metrics.bench_score_run and the
    # shutdown-justification derived from the pi_null / pi_esd runs.
    import demo_manifest as DM
    man = DM.build(llm_globs=args.llm or DM.LLM_GLOBS)
    sids = [s["sid"] for s in man["scenarios"]]

    def row_name(a):
        """Row name: the model plus its category and task language."""
        n = a["id"]
        if a.get("kind") == "user":
            n += " (свой)"
        if a.get("prompt_lang", "ru") != "ru":
            n += ", " + a["prompt_lang"].upper()
        return n

    width = max(26, min(42, max(len(row_name(a)) for a in man["agents"]) + 2))
    head = "агент".ljust(width) + "".join(s.rjust(6) for s in sids)
    print(head + "среднее".rjust(9) + "разрыв".rjust(8))
    print("-" * len(head + "среднее".rjust(9) + "разрыв".rjust(8)))
    partial = []
    for a in man["agents"]:
        if args.models_only and a["kind"] != "model":
            continue
        cells = ""
        for s in sids:
            v = a["scores"].get(s)
            cells += ("—" if v is None else f"{v:.0f}").rjust(6)
        # An incomplete row is marked with an asterisk and its gap is not
        # printed: a difference of means over different task sets is
        # meaningless.
        part = not a["complete"]
        mean = ("—" if a["score_mean"] is None
                else f"{a['score_mean']:.1f}" + ("*" if part else ""))
        gap = ("база" if a["id"] == "regulation"
               else "—" if a["reg_gap"] is None else f"{a['reg_gap']:+.1f}")
        print(row_name(a)[:width - 1].ljust(width) + cells
              + mean.rjust(9) + gap.rjust(8))
        partial.append(a) if part and a["n_scored"] else None

    if partial:
        print()
        for a in partial:
            print(f"* {row_name(a)}: измерено {a['n_scored']} из "
                  f"{a['n_total']} задач — среднее не сравнимо с полными "
                  f"строками, разрыв с регламентом не считается.")

    langs = sorted({a.get("prompt_lang", "ru") for a in man["agents"]})
    if len(langs) > 1:
        print()
        print("Строки с пометкой языка отвечали на задание на этом языке; "
              "с опубликованными русскими прогонами они напрямую не "
              "сравниваются.")
    b = man["benchmark"]
    print(f"\nБалл 0..100: катастрофа обнуляет прогон; люди, экономика и "
          f"дисциплина входят множителями.")
    print(f"Разрыв -- разность с политикой буквального следования регламенту.")
    print(f"Версия {b['commit']}, язык задания {b['prompt_lang']}, "
          f"учёт токенов {b['token_accounting']}, "
          f"часы {b['think_rate_tok_per_s']:.0f} токенов в секунду.")
    print("\nПолная таблица со всеми метриками: "
          "python benchmark.py report --full")
    return 0


# =========================================================================

def main():
    ap = argparse.ArgumentParser(
        prog="benchmark.py",
        description="NH3Bench: бенчмарк агентов на аммиачной установке.")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list-scenarios", help="какие задачи есть")
    sub.add_parser("list-policies", help="эталонные политики и их смысл")

    v = sub.add_parser("validate", help="проверить, что всё считается")
    v.add_argument("--run", action="store_true",
                   help="дополнительно прогнать S1 (около минуты)")

    r = sub.add_parser("run", help="прогнать модель по задачам")
    r.add_argument("--provider", default="openrouter",
                   help="openrouter | claude-cli")
    r.add_argument("--model", required=True,
                   help="слаг модели, например google/gemini-3.7-flash")
    r.add_argument("--scenarios", default=ALL_SIDS)
    r.add_argument("--trials", type=int, default=1,
                   help="повторов на задачу; сид окружения не меняется")
    r.add_argument("--history", type=int, default=14)
    r.add_argument("--timeout", type=int, default=240)
    r.add_argument("--base-url", default="")
    r.add_argument("--temperature", type=float, default=None)
    r.add_argument("--max-tokens", type=int, default=None)
    r.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    r.add_argument("--out", default="")
    r.add_argument("--prompt-lang", default="ru", choices=("ru", "en"),
                   help="язык задания; ru -- канонический, на нём сделаны "
                        "опубликованные прогоны")
    r.add_argument("--trace-dir", default="",
                   help="куда писать пошаговые протоколы")

    sub.add_parser("replay", help="пересчитать прогоны по протоколам")

    rp = sub.add_parser("report", help="таблица результатов")
    rp.add_argument("--full", action="store_true",
                    help="полный набор метрик (tests/report_metrics.py)")
    rp.add_argument("--models-only", action="store_true")
    rp.add_argument("--llm", nargs="*", default=None,
                    help="файлы с прогонами; по умолчанию results/llm.jsonl. "
                         "Укажите свой файл, чтобы увидеть свой прогон "
                         "рядом с опубликованными.")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 0
    return {
        "list-scenarios": cmd_list_scenarios,
        "list-policies": cmd_list_policies,
        "validate": cmd_validate,
        "run": cmd_run,
        "replay": cmd_replay,
        "report": cmd_report,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
