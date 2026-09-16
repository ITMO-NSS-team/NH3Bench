"""Build the canonical Terra reasoning/seed experiment tables and statistics.

Run this after replaying the recorded traces.  The script intentionally treats a
seed as one six-scenario benchmark replicate; it never pools the 60 scenario rows
as if they were independent benchmark replicates.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nh3twin import metrics as M


LEVELS = ("none", "low", "medium", "high", "xhigh", "max")
SCENARIOS = tuple(f"S{i}" for i in range(1, 7))


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def esd_justification() -> dict[str, bool]:
    rows = read_jsonl(ROOT / "results" / "baselines.jsonl")
    for path in sorted((ROOT / "results").glob("base_S*.jsonl")):
        rows.extend(read_jsonl(path))
    by = {(r["scenario"], r["policy"], r["seed"]): r for r in rows}
    return {
        sid: bool(by[(sid, "null", 1)].get("CAT"))
        and not bool(by[(sid, "esd", 1)].get("CAT"))
        for sid in SCENARIOS
    }


def decorate(rows: list[dict], policy: str, justified: dict[str, bool]) -> list[dict]:
    out = []
    for source in rows:
        row = dict(source)
        row["policy"] = policy
        row["esd_justified"] = justified[row["scenario"]]
        out.append(row)
    return out


def outcome(row: dict) -> str:
    flags = list(row.get("CAT") or []) + list(row.get("MAJ") or [])
    return "+".join(flags) if flags else "clean"


def llm_totals(rows: list[dict]) -> dict:
    keys = (
        "calls", "errors", "illegal", "unparsed", "snapped", "out_tokens",
        "input_tokens", "cached_input_tokens", "reasoning_output_tokens",
    )
    result = {key: sum((r.get("llm") or {}).get(key, 0) for r in rows) for key in keys}
    result["wall_s"] = round(sum((r.get("llm") or {}).get("wall_s", 0.0) for r in rows), 3)
    result["cost_usd"] = round(sum((r.get("llm") or {}).get("cost_usd", 0.0) for r in rows), 6)
    return result


def summarize_run(rows: list[dict], label: str) -> dict:
    if {r["scenario"] for r in rows} != set(SCENARIOS) or len(rows) != 6:
        raise ValueError(f"{label}: expected exactly S1-S6, got {len(rows)} rows")
    agg = M.aggregate(rows, label=label)
    return {
        "label": label,
        "score": agg["score"],
        "score_worst": agg["score_worst"],
        "CPR": agg["CPR"],
        "SPR": agg["SPR"],
        "PR": agg["PR"],
        "harm": agg["harm"],
        "cost_mean_rub": agg["cost_mean_rub"],
        "outcomes": {r["scenario"]: outcome(r) for r in sorted(rows, key=lambda x: x["scenario"])},
        "scores": {r["scenario"]: M.bench_score_run(r) for r in sorted(rows, key=lambda x: x["scenario"])},
        "llm": llm_totals(rows),
    }


def bootstrap_mean_ci(values: list[float], repetitions: int = 100_000) -> list[float]:
    rng = random.Random(20260912)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(repetitions))
    lo = means[int(0.025 * repetitions)]
    hi = means[int(0.975 * repetitions)]
    return [round(lo, 2), round(hi, 2)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reasoning-only", action="store_true")
    args = parser.parse_args()

    results = ROOT / "results"
    justified = esd_justification()

    reasoning_rows = []
    reasoning_summary = []
    for level in LEVELS:
        path = results / f"terra_reasoning_{level}_replayed.jsonl"
        rows = decorate(read_jsonl(path), f"llm:gpt-5.6-terra:re-{level}", justified)
        reasoning_rows.extend(rows)
        reasoning_summary.append(summarize_run(rows, level))
    write_jsonl(results / "terra_reasoning.jsonl", reasoning_rows)

    summary: dict = {
        "design": {
            "model": "gpt-5.6-terra",
            "reasoning_levels": list(LEVELS),
            "reasoning_seed": 1,
            "seed_reasoning_level": "medium",
            "seed_values": list(range(1, 11)),
            "scenarios": list(SCENARIOS),
            "bootstrap_repetitions": 100_000,
            "bootstrap_rng_seed": 20260912,
        },
        "reasoning": reasoning_summary,
    }

    if not args.reasoning_only:
        seed_rows = decorate(
            read_jsonl(results / "terra_reasoning_medium_replayed.jsonl"),
            "llm:gpt-5.6-terra:seed",
            justified,
        )
        replay_files = (
            "terra_seeds_2-4_replayed.jsonl",
            "terra_seeds_5-7_replayed.jsonl",
            "terra_seeds_8-9_head_replayed.jsonl",
            "terra_seed10_head_replayed.jsonl",
            "terra_seed8_tail_replayed.jsonl",
            "terra_seed9_tail_replayed.jsonl",
            "terra_seed10_tail_replayed.jsonl",
        )
        for name in replay_files:
            seed_rows.extend(decorate(
                read_jsonl(results / name),
                "llm:gpt-5.6-terra:seed",
                justified,
            ))
        seed_rows.sort(key=lambda r: (r["seed"], r["scenario"]))
        keys = {(r["scenario"], r["seed"]) for r in seed_rows}
        expected = {(sid, seed) for seed in range(1, 11) for sid in SCENARIOS}
        if keys != expected or len(seed_rows) != 60:
            raise ValueError(f"seed sweep is incomplete: {len(seed_rows)} rows, {len(keys)} unique keys")
        write_jsonl(results / "terra_seeds.jsonl", seed_rows)

        by_seed = []
        for seed in range(1, 11):
            row = summarize_run([r for r in seed_rows if r["seed"] == seed], f"seed-{seed}")
            row["seed"] = seed
            by_seed.append(row)
        values = [r["score"] for r in by_seed]
        by_scenario = {}
        for sid in SCENARIOS:
            rows = [r for r in seed_rows if r["scenario"] == sid]
            scores = [M.bench_score_run(r) for r in rows]
            by_scenario[sid] = {
                "mean_score": round(statistics.mean(scores), 2),
                "sample_sd": round(statistics.stdev(scores), 2),
                "outcomes": dict(sorted(Counter(outcome(r) for r in rows).items())),
            }
        summary["seeds"] = {
            "by_seed": by_seed,
            "score": {
                "values": values,
                "mean": round(statistics.mean(values), 2),
                "sample_sd": round(statistics.stdev(values), 2),
                "median": round(statistics.median(values), 2),
                "min": min(values),
                "max": max(values),
                "bootstrap_95_ci_mean": bootstrap_mean_ci(values),
            },
            "by_scenario": by_scenario,
            "llm": llm_totals(seed_rows),
        }

    with (results / "terra_experiments_summary.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
