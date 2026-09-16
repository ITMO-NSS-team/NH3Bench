# Terra model stochasticity at fixed twin seed

## Result

Five independent complete benchmark samples were compared with the digital-twin RNG
seed fixed at 1. All other harness settings were held constant: GPT-5.6 Terra,
`medium` reasoning, history 14, and scenarios S1--S6.

The five unified scores were **37.5, 37.6, 36.5, 36.5, and 36.5**. Their mean was
**36.92**, sample SD **0.58**, median **36.5**, and range **36.5--37.6**. The sample
coefficient of variation was **1.57%**. A percentile bootstrap with 100,000 resamples
(analysis seed 20260913) gave a **95% interval of 36.50--37.36 for the mean**.

Thus, model sampling changed some actions and scenario-level outcomes, but the observed
complete-run score dispersion was small: the full range was 1.1 points and three of
five runs had the same score of 36.5. Variation was concentrated in S2, S3, and S5.
S1, S4, and S6 had identical outcomes and scores in all five samples. In particular,
S5 ranged from 38.5 to 49.8, whereas S2 varied in event labels while remaining at a
score of zero in every sample.

This is a repeatability estimate for one condition, not a comparison between
conditions, so no hypothesis test was performed. With only five complete-run samples,
the variance and bootstrap interval remain exploratory. The observed dispersion should
be interpreted as model-sampling stochasticity plus any residual service nondeterminism;
the fixed twin seed removes simulator-perturbation variability from this comparison.

## Integrity and artifacts

All 30 scenario episodes were replayed from their saved action traces. Recorded and
replayed `CAT`, `MAJ`, and termination time matched for every episode (30/30; zero
mismatches). The two newly collected samples were executed in independent S1--S3 and
S4--S6 workers; because every scenario creates a fresh twin instance, this affects only
wall-clock scheduling. An incomplete S4 trace left by each stopped base worker was
excluded before replay; neither produced a result row and the complete S4 traces came
from the predeclared tail workers.

- Machine-readable summary: `results/terra_fixed_twin_replication_summary.json`
- Combined scenario rows: `results/terra_fixed_twin_replicates.jsonl`
- New raw runs: `results/terra_reasoning_medium_r4.jsonl` and
  `results/terra_reasoning_medium_r5.jsonl`
- New replayed runs: `results/terra_reasoning_medium_r4_replayed.jsonl` and
  `results/terra_reasoning_medium_r5_replayed.jsonl`
- Analysis: `tests/analyze_terra_fixed_twin_replicates.py`
- Prespecified plan: `docs/TERRA-FIXED-TWIN-REPLICATION-PLAN.md`
