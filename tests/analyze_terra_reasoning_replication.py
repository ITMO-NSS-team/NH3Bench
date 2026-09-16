"""Analyze three independent Terra samples at each reasoning-effort level.

The experimental unit is a complete six-scenario benchmark run.  Scenario rows
are never pooled as independent replicates.  The analysis follows the plan in
docs/CODEX-TERRA-REASONING-REPLICATION-PLAN.md.
"""

from __future__ import annotations

import itertools
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path

from analyze_terra_experiments import (
    LEVELS,
    ROOT,
    bootstrap_mean_ci,
    decorate,
    esd_justification,
    llm_totals,
    read_jsonl,
    summarize_run,
    write_jsonl,
)


N_PERMUTATIONS = 100_000
ANALYSIS_SEED = 20260912


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2.0
        for index in order[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def kruskal_h(values: list[float], groups: list[int]) -> float:
    ranks = average_ranks(values)
    n = len(values)
    group_ids = sorted(set(groups))
    rank_term = 0.0
    for group in group_ids:
        group_ranks = [rank for rank, label in zip(ranks, groups) if label == group]
        rank_term += sum(group_ranks) ** 2 / len(group_ranks)
    h = 12.0 * rank_term / (n * (n + 1)) - 3.0 * (n + 1)
    counts = Counter(values)
    tie_correction = 1.0 - sum(c ** 3 - c for c in counts.values()) / (n ** 3 - n)
    return h / tie_correction if tie_correction else 0.0


def pearson(x: list[float], y: list[float]) -> float:
    mx, my = statistics.mean(x), statistics.mean(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denominator = math.sqrt(
        sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)
    )
    return numerator / denominator if denominator else 0.0


def spearman_rho(x: list[float], y: list[float]) -> float:
    return pearson(average_ranks(x), average_ranks(y))


def permutation_tests(values: list[float], groups: list[int]) -> dict:
    rng = random.Random(ANALYSIS_SEED)
    observed_h = kruskal_h(values, groups)
    h_extreme = 0
    observed_rho = spearman_rho([float(g) for g in groups], values)
    rho_extreme = 0
    shuffled = list(values)
    for _ in range(N_PERMUTATIONS):
        rng.shuffle(shuffled)
        if kruskal_h(shuffled, groups) >= observed_h - 1e-12:
            h_extreme += 1
        if abs(spearman_rho([float(g) for g in groups], shuffled)) >= abs(observed_rho) - 1e-12:
            rho_extreme += 1
    k, n = len(set(groups)), len(values)
    epsilon_squared = max(0.0, min(1.0, (observed_h - k + 1) / (n - k)))
    return {
        "kruskal_wallis": {
            "H": round(observed_h, 6),
            "df": k - 1,
            "permutation_p_two_sided": round((h_extreme + 1) / (N_PERMUTATIONS + 1), 6),
            "epsilon_squared": round(epsilon_squared, 6),
        },
        "ordered_spearman": {
            "rho": round(observed_rho, 6),
            "permutation_p_two_sided": round((rho_extreme + 1) / (N_PERMUTATIONS + 1), 6),
        },
    }


def mann_whitney_u(a: list[float], b: list[float]) -> float:
    ranks = average_ranks(a + b)
    return sum(ranks[: len(a)]) - len(a) * (len(a) + 1) / 2


def exact_mann_whitney_p(a: list[float], b: list[float]) -> tuple[float, float]:
    values = a + b
    observed = mann_whitney_u(a, b)
    center = len(a) * len(b) / 2
    extreme = 0
    total = 0
    for indices in itertools.combinations(range(len(values)), len(a)):
        chosen = set(indices)
        pa = [value for index, value in enumerate(values) if index in chosen]
        pb = [value for index, value in enumerate(values) if index not in chosen]
        if abs(mann_whitney_u(pa, pb) - center) >= abs(observed - center) - 1e-12:
            extreme += 1
        total += 1
    return observed, extreme / total


def holm_adjust(p_values: list[float]) -> list[float]:
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    adjusted = [0.0] * len(p_values)
    running = 0.0
    m = len(p_values)
    for rank, index in enumerate(order):
        running = max(running, (m - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def main() -> None:
    results = ROOT / "results"
    justified = esd_justification()
    all_rows: list[dict] = []
    runs: list[dict] = []
    for level in LEVELS:
        for replicate in (1, 2, 3):
            suffix = "" if replicate == 1 else f"_r{replicate}"
            path = results / f"terra_reasoning_{level}{suffix}_replayed.jsonl"
            rows = decorate(
                read_jsonl(path),
                f"llm:gpt-5.6-terra:re-{level}-r{replicate}",
                justified,
            )
            for row in rows:
                row["reasoning_effort"] = level
                row["model_replicate"] = replicate
            all_rows.extend(rows)
            summary = summarize_run(rows, f"{level}-r{replicate}")
            summary["reasoning_effort"] = level
            summary["model_replicate"] = replicate
            runs.append(summary)

    write_jsonl(results / "terra_reasoning_replicated.jsonl", all_rows)
    by_level = []
    for level in LEVELS:
        level_runs = [run for run in runs if run["reasoning_effort"] == level]
        scores = [run["score"] for run in level_runs]
        by_level.append({
            "reasoning_effort": level,
            "scores": scores,
            "mean": round(statistics.mean(scores), 2),
            "sample_sd": round(statistics.stdev(scores), 2),
            "median": round(statistics.median(scores), 2),
            "min": min(scores),
            "max": max(scores),
            "bootstrap_95_ci_mean": bootstrap_mean_ci(scores),
        })

    values = [run["score"] for run in runs]
    groups = [LEVELS.index(run["reasoning_effort"]) for run in runs]
    tests = permutation_tests(values, groups)
    pairwise = []
    if tests["kruskal_wallis"]["permutation_p_two_sided"] < 0.05:
        raw = []
        for first, second in itertools.combinations(LEVELS, 2):
            a = next(row["scores"] for row in by_level if row["reasoning_effort"] == first)
            b = next(row["scores"] for row in by_level if row["reasoning_effort"] == second)
            u, p = exact_mann_whitney_p(a, b)
            raw.append({"first": first, "second": second, "U": u, "p_raw": p})
        adjusted = holm_adjust([row["p_raw"] for row in raw])
        for row, p_adjusted in zip(raw, adjusted):
            row["p_holm"] = round(p_adjusted, 6)
            row["p_raw"] = round(row["p_raw"], 6)
        pairwise = raw

    output = {
        "design": {
            "model": "gpt-5.6-terra",
            "reasoning_levels": list(LEVELS),
            "model_replicates_per_level": 3,
            "simulator_seed": 1,
            "model_seed_controlled": False,
            "scenarios_per_replicate": 6,
            "permutation_repetitions": N_PERMUTATIONS,
            "bootstrap_repetitions": 100_000,
            "analysis_rng_seed": ANALYSIS_SEED,
        },
        "runs": runs,
        "by_level": by_level,
        "tests": tests,
        "pairwise_if_omnibus_significant": pairwise,
        "llm": llm_totals(all_rows),
    }
    with (results / "terra_reasoning_replication_summary.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
