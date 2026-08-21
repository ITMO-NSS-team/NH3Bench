"""
Прогон языковой модели по сценариям бенчмарка.

    python3 tests/run_llm.py --scenarios S1,S2,S3,S4,S5 --model haiku

Результат построчно дописывается в results/llm.jsonl (кэш по ключу
сценарий/политика/сид, как у эталонных политик), пошаговый протокол с
полными репликами модели -- в results/llm_traces/.

Прогон долгий: каждое решение -- отдельный вызов модели, 3-25 с реального
времени, а решений за эпизод бывает под сотню. Запускать в фоне и следить по
логу; при обрыве повторный запуск досчитает недостающие клетки.
"""

import argparse
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode
from nh3twin.llm_policy import ClaudeCLIPolicy, DEFAULT_CLI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "results")
TRACE_DIR = os.path.join(OUT_DIR, "llm_traces")
os.makedirs(TRACE_DIR, exist_ok=True)


def already_done(out_path):
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["scenario"], r["policy"], r["seed"]))
                except (json.JSONDecodeError, KeyError):
                    pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="S1,S2,S3,S4,S5")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--history", type=int, default=14,
                    help="сколько последних действий показывать модели")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--cli", default=DEFAULT_CLI)
    ap.add_argument("--tag", default="", help="суффикс имени политики")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "llm.jsonl"))
    args = ap.parse_args()

    pol_name = f"llm:{args.model}" + (f":{args.tag}" if args.tag else "")
    sids = [s for s in args.scenarios.split(",") if s]
    seeds = [int(x) for x in args.seeds.split(",")]
    done = already_done(args.out)

    t_all = time.time()
    for sid in sids:
        for seed in seeds:
            if (sid, pol_name, seed) in done:
                print(f"== {sid}/{pol_name}/{seed} уже есть", flush=True)
                continue
            trace = os.path.join(
                TRACE_DIR, f"{pol_name.replace(':', '_')}_{sid}_s{seed}.jsonl")
            if os.path.exists(trace):
                os.remove(trace)
            print(f"== {sid}/{pol_name}/{seed}: старт "
                  f"(горизонт {SCENARIOS[sid].horizon_s:.0f} с)", flush=True)
            t0 = time.time()
            pol = None
            try:
                ep = Episode(SCENARIOS[sid], seed=seed)
                ep._policy_name = pol_name
                pol = ClaudeCLIPolicy(model=args.model, cli=args.cli,
                                      history=args.history,
                                      timeout=args.timeout,
                                      trace_path=trace, label=pol_name,
                                      verbose=True)
                r = ep.run(pol)
                r["policy"] = pol_name
                seg = ep.plant.segments.get("EV-03")
                r["fatigue_EV03"] = round(seg.fatigue, 3) if seg else None
                r["max_dose"] = max(
                    [o["dose"] for o in r["operators"].values()] or [0.0])
                r["milk_max"] = round(
                    max(t[1]["T_MILK"] for t in ep.trace), 2) if ep.trace else None
                r["pcond_max"] = round(
                    max(t[1]["P_COND"] for t in ep.trace), 2) if ep.trace else None
                r["action_counts"] = {}
                for rec in ep.log:
                    key = rec.action.split(":")[0]
                    r["action_counts"][key] = r["action_counts"].get(key, 0) + 1
                r["llm"] = vars(pol.stats)
                r["llm"]["model"] = args.model
                r["llm"]["history"] = args.history
                r["llm"]["tokens_per_decision"] = (
                    round(pol.stats.out_tokens / max(pol.stats.calls, 1), 1))
                r["trace"] = os.path.relpath(trace, ROOT).replace("\\", "/")
            except Exception:
                r = {"scenario": sid, "policy": pol_name, "seed": seed,
                     "error": traceback.format_exc()[-800:]}
                if pol is not None:
                    r["llm"] = vars(pol.stats)
            with open(args.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"== {sid}/{pol_name}/{seed}: CAT={r.get('CAT')} "
                  f"MAJ={r.get('MAJ')} t_end={r.get('t_end_s')} "
                  f"шагов={r.get('n_steps')} "
                  f"({(time.time() - t0) / 60:.1f} мин)", flush=True)

    print(f"готово за {(time.time() - t_all) / 60:.1f} мин", flush=True)


if __name__ == "__main__":
    main()
