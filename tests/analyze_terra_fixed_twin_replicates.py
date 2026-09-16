"""Summarize five independent Terra samples at fixed digital-twin seed 1."""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from pathlib import Path

from analyze_terra_experiments import (
    ROOT,
    decorate,
    esd_justification,
    read_jsonl,
    summarize_run,
    write_jsonl,
)


ANALYSIS_SEED = 20260913
N_BOOTSTRAP = 100_000


def bootstrap_mean_ci(values: list[float]) -> list[float]:
    rng = random.Random(ANALYSIS_SEED)
    means = sorted(
        statistics.mean(rng.choices(values, k=len(values)))
        for _ in range(N_BOOTSTRAP)
    )
    lo = means[int(0.025 * N_BOOTSTRAP)]
    hi = means[int(0.975 * N_BOOTSTRAP)]
    return [round(lo, 2), round(hi, 2)]


def main() -> None:
    results = ROOT / "results"
    justified = esd_justification()
    all_rows: list[dict] = []
    runs: list[dict] = []

    for replicate in range(1, 6):
        suffix = "" if replicate == 1 else f"_r{replicate}"
        path = results / f"terra_reasoning_medium{suffix}_replayed.jsonl"
        rows = decorate(
            read_jsonl(path),
            f"llm:gpt-5.6-terra:fixed-twin-r{replicate}",
            justified,
        )
        for row in rows:
            row["model_replicate"] = replicate
            row["reasoning_effort"] = "medium"
            row["simulator_seed"] = 1
        all_rows.extend(rows)
        summary = summarize_run(rows, f"fixed-twin-r{replicate}")
        summary["model_replicate"] = replicate
        runs.append(summary)

    scores = [run["score"] for run in runs]
    score_mean = statistics.mean(scores)
    score_sd = statistics.stdev(scores)
    by_scenario = {}
    for scenario in [f"S{i}" for i in range(1, 7)]:
        rows = [row for row in all_rows if row["scenario"] == scenario]
        outcomes = [
            "+".join(row.get("CAT", []) + row.get("MAJ", [])) or "clean"
            for row in rows
        ]
        scenario_scores = [run["scores"][scenario] for run in runs]
        by_scenario[scenario] = {
            "outcome_counts": dict(sorted(Counter(outcomes).items())),
            "scores": scenario_scores,
            "min": min(scenario_scores),
            "max": max(scenario_scores),
        }

    write_jsonl(results / "terra_fixed_twin_replicates.jsonl", all_rows)
    output = {
        "design": {
            "model": "gpt-5.6-terra",
            "reasoning_effort": "medium",
            "simulator_seed": 1,
            "model_seed_controlled": False,
            "replicates": 5,
            "scenarios_per_replicate": 6,
            "bootstrap_repetitions": N_BOOTSTRAP,
            "analysis_rng_seed": ANALYSIS_SEED,
        },
        "runs": runs,
        "scores": scores,
        "summary": {
            "mean": round(score_mean, 2),
            "sample_sd": round(score_sd, 2),
            "coefficient_of_variation_pct": round(
                100.0 * score_sd / score_mean, 2),
            "median": round(statistics.median(scores), 2),
            "min": min(scores),
            "max": max(scores),
            "bootstrap_95_ci_mean": bootstrap_mean_ci(scores),
        },
        "by_scenario": by_scenario,
    }
    with (results / "terra_fixed_twin_replication_summary.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
