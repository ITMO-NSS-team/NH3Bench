"""
Прогон эталонных политик по всем сценариям.

Запуск:  python3 tests/run_baselines.py [сценарии] [сиды]
Результат пишется построчно в results/baselines.jsonl, чтобы прогон можно было
прервать и продолжить.
"""

import sys, os, json, time, argparse, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode
from nh3twin.policies import (NullPolicy, RandomPolicy, RulePolicy,
                              OraclePolicy, RegulationPolicy, ESDPolicy)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "baselines.jsonl")


def make_policy(name, seed):
    if name == "null":
        return NullPolicy()
    if name == "random":
        return RandomPolicy(seed=seed)
    if name == "rules":
        return RulePolicy()
    if name == "oracle":
        return OraclePolicy()
    if name == "regulation":
        return RegulationPolicy()
    if name == "esd":
        return ESDPolicy()
    raise ValueError(name)


def already_done(OUT=OUT):
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["scenario"], r["policy"], r["seed"]))
                except json.JSONDecodeError:
                    pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="S1,S2,S3,S4,S5")
    ap.add_argument("--policies", default="null,random,rules")
    ap.add_argument("--seeds", default="1,2,3,4,5")
    # Отдельный файл на процесс: параллельный дозапись в один и тот же файл
    # на Windows иногда рвёт строку посередине.
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    sids = args.scenarios.split(",")
    pols = args.policies.split(",")
    seeds = [int(x) for x in args.seeds.split(",")]

    done = already_done(args.out)
    total = len(sids) * len(pols) * len(seeds)
    n = 0
    t_all = time.time()

    for sid in sids:
        for pol in pols:
            for seed in seeds:
                n += 1
                if (sid, pol, seed) in done:
                    print(f"[{n}/{total}] {sid}/{pol}/{seed} уже есть", flush=True)
                    continue
                t0 = time.time()
                try:
                    ep = Episode(SCENARIOS[sid], seed=seed)
                    ep._policy_name = pol
                    r = ep.run(make_policy(pol, seed))
                    r["policy"] = pol
                    seg = ep.plant.segments.get("EV-03")
                    r["fatigue_EV03"] = round(seg.fatigue, 3) if seg else None
                    r["cycles_EV03"] = seg.cycles if seg else None
                    r["max_dose"] = max(
                        [o["dose"] for o in r["operators"].values()] or [0.0])
                    r["milk_max"] = round(
                        max(t[1]["T_MILK"] for t in ep.trace), 2) if ep.trace else None
                    r["pcond_max"] = round(
                        max(t[1]["P_COND"] for t in ep.trace), 2) if ep.trace else None
                    r.pop("actions", None)
                    r["action_counts"] = {}
                    for rec in ep.log:
                        key = rec.action.split(":")[0]
                        r["action_counts"][key] = r["action_counts"].get(key, 0) + 1
                except Exception:
                    r = {"scenario": sid, "policy": pol, "seed": seed,
                         "error": traceback.format_exc()[-600:]}
                with open(args.out, "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(f"[{n}/{total}] {sid}/{pol}/{seed}: "
                      f"CAT={r.get('CAT')} MAJ={r.get('MAJ')} "
                      f"({time.time() - t0:.0f} с)", flush=True)

    print(f"готово за {(time.time() - t_all) / 60:.1f} мин", flush=True)


if __name__ == "__main__":
    main()
