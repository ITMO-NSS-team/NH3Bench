"""
Re-deriving agent runs from the saved transcripts.

The model cannot be called again: it is not deterministic, and a second
run would be a different episode. But the sequence of actions and the
cost of deliberation are recorded step by step, and the twin is
deterministic -- so the episode can be reproduced exactly and metrics
that were not collected on the first run can be taken from it.

The match with the recorded outcome is checked and printed. A
divergence means the twin changed between runs, and new metrics then
cannot be compared with the old matrix.

    python3 tests/replay_llm.py
"""

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode
from nh3twin.llm_policy import ReplayPolicy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE_DIR = os.path.join(ROOT, "results", "llm_traces")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", default=os.path.join(TRACE_DIR, "*.jsonl"))
    ap.add_argument("--old", default=os.path.join(ROOT, "results", "llm.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "llm.jsonl"))
    args = ap.parse_args()

    old = {}
    if os.path.exists(args.old):
        with open(args.old, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    old[(r.get("scenario"), r.get("policy"), r.get("seed"))] = r

    rows, mismatches = [], 0
    for path in sorted(glob.glob(args.traces)):
        base = os.path.basename(path)[:-6]          # llm_haiku_S3_s1
        parts = base.split("_")
        sid = next((p for p in parts if p in SCENARIOS), None)
        seed = int(parts[-1][1:]) if parts[-1].startswith("s") else 1
        if sid is None:
            print(f"пропуск {base}: сценарий не распознан", flush=True)
            continue
        pol = ":".join(parts[:parts.index(sid)])

        t0 = time.time()
        ep = Episode(SCENARIOS[sid], seed=seed)
        ep._policy_name = pol
        pol_obj = ReplayPolicy(path)
        r = ep.run(pol_obj)
        r["policy"] = pol
        r["trace"] = os.path.relpath(path, ROOT).replace("\\", "/")

        prev = old.get((sid, pol, seed))
        if prev:
            # we carry over what is known only about the model call itself
            for k in ("llm",):
                if k in prev:
                    r[k] = prev[k]
            same = (sorted(prev.get("CAT") or []) == sorted(r["CAT"])
                    and sorted(prev.get("MAJ") or []) == sorted(r["MAJ"])
                    and abs((prev.get("t_end_s") or 0) - r["t_end_s"]) < 1.0)
            if not same:
                mismatches += 1
                print(f"!! РАСХОЖДЕНИЕ {sid}/{pol}: было CAT={prev.get('CAT')} "
                      f"MAJ={prev.get('MAJ')} t={prev.get('t_end_s')}, "
                      f"стало CAT={r['CAT']} MAJ={r['MAJ']} t={r['t_end_s']}",
                      flush=True)
        r.pop("actions", None)
        r["action_counts"] = {}
        for rec in ep.log:
            key = rec.action.split(":")[0]
            r["action_counts"][key] = r["action_counts"].get(key, 0) + 1
        rows.append(r)
        print(f"{sid}/{pol}: CAT={r['CAT']} MAJ={r['MAJ']} "
              f"t_end={r['t_end_s']} энергия={r['energy_kwh']} кВт·ч, "
              f"HACCP молоко={r['haccp_milk_s']} с "
              f"({time.time() - t0:.0f} с)", flush=True)

    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nвоспроизведено {len(rows)}, расхождений {mismatches}", flush=True)
    if mismatches:
        print("ВНИМАНИЕ: двойник недетерминирован либо изменился — "
              "сравнение с прежней матрицей недействительно", flush=True)


if __name__ == "__main__":
    main()
