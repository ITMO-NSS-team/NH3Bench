# GPT-5.6 Terra: ten-seed variability experiment

This experiment measures end-to-end variability for GPT-5.6 Terra at fixed `medium`
reasoning effort.  Twin seeds 1--10 were each run on all six scenarios, so the
experimental unit for the summary statistics is one complete six-scenario benchmark
replicate.  Seed 1 reuses the published Terra baseline; seeds 2--10 are 54 new live
episodes.  All other settings are fixed: history 14, saved Codex account, and a fresh
CLI process for every decision.

The model and reasoning setting follow the [official Terra documentation](https://developers.openai.com/api/docs/models/gpt-5.6-terra).
The descriptive analysis reports every replicate, preserves the replicate as the
sampling unit, and labels exploratory uncertainty explicitly.

## Results by seed

| seed | S1 | S2 | S3 | S4 | S5 | S6 | score |
|---:|---|---|---|---|---|---|---:|
| 1 | CAT-3 | CAT-4, MAJ-1 | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 37.5 |
| 2 | CAT-3 | CAT-1, MAJ-1 | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 38.4 |
| 3 | CAT-3 | CAT-4, MAJ-1 | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 37.4 |
| 4 | CAT-3 | CAT-1, MAJ-1 | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 35.1 |
| 5 | CAT-3 | CAT-4 | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 37.6 |
| 6 | CAT-3 | CAT-4, MAJ-1 | MAJ-3 | clean | MAJ-2, MAJ-3 | CAT-1, MAJ-2 | 35.2 |
| 7 | CAT-3 | clean | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 54.1 |
| 8 | CAT-3 | CAT-1, MAJ-1 | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 38.3 |
| 9 | clean | CAT-4, MAJ-1 | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 52.5 |
| 10 | clean | CAT-1, MAJ-1 | MAJ-3 | clean | MAJ-3 | CAT-1, MAJ-2 | 55.0 |

The ten complete benchmark scores are `37.5, 38.4, 37.4, 35.1, 37.6, 35.2,
54.1, 38.3, 52.5, 55.0`.

| statistic | value |
|---|---:|
| mean | **42.11** |
| sample SD | **8.21** |
| median | **37.95** |
| min--max | **35.1--55.0** |
| exploratory 95% bootstrap CI for the mean | **37.52--47.26** |

The interval is a percentile bootstrap over the ten six-scenario scores, with 100,000
resamples and analysis RNG seed 20260912.  With only ten replicates it is a descriptive
uncertainty interval, not evidence that the population mean differs from a comparator.

Seven runs form a lower cluster from 35.1 to 38.4.  Seeds 7, 9, and 10 form a higher
cluster from 52.5 to 55.0 because exactly one otherwise usually catastrophic scenario
was solved: S2 at seed 7, and S1 at seeds 9 and 10.  Since scenarios have equal weight,
one additional clean cell changes the benchmark mean by roughly 16.7 points.

## Stability by scenario

| scenario | empirical outcomes over ten runs | mean scenario score |
|---|---|---:|
| S1 | clean 2; CAT-3 8 | 20.00 |
| S2 | clean 1; CAT-1 + MAJ-1 4; CAT-4 + MAJ-1 4; CAT-4 1 | 10.00 |
| S3 | MAJ-3 10 | 77.35 |
| S4 | clean 10 | 100.00 |
| S5 | MAJ-3 9; MAJ-2 + MAJ-3 1 | 45.32 |
| S6 | CAT-1 + MAJ-2 10 | 0.00 |

Across all 60 cells, PR is 0.550, CPR 0.467, and SPR 0.450.  S4 is fully stable and S6
is a fully stable failure.  Most score variance comes from rare passes in S1 or S2,
not gradual movement across all scenarios.  S3 and S5 vary economically even when their
MAJ labels stay the same, which is why their scenario scores are not constant.

## Compute and verification

Across the 60 cells there were 7,190 model decisions, 1,576,219 output tokens including
1,117,153 reasoning tokens, and zero call errors.  Six proposed actions were illegal;
there were no unparsed or snapped actions.  Summed model wall time was 59,533 seconds
(16.5 hours; the live jobs ran partly in parallel).  The stored $136.67 is an API
list-price equivalent, not an additional subscription charge.

All 54 newly recorded traces replayed with identical CAT flags, MAJ flags, and end times:
zero discrepancies.  Seed 1 had already been replay-verified as part of the Terra
baseline and reasoning sweep.  Canonical replayed rows are in
`results/terra_seeds.jsonl`; the complete statistical summary is
`results/terra_experiments_summary.json`.

```bash
python3 tests/run_llm.py --provider codex --model gpt-5.6-terra \
  --reasoning-effort medium --scenarios S1,S2,S3,S4,S5,S6 \
  --seeds 1,2,3,4,5,6,7,8,9,10 --history 14 --tag seed \
  --out results/terra_seeds_raw.jsonl

python3 tests/analyze_terra_experiments.py
```

## What “seed dependence” means here

The harness passes the seed to the digital twin, not to the language model.  Codex CLI
calls were fresh and the model-sampling RNG was not fixed.  The observed spread therefore
combines sensitivity to the twin's seeded perturbations with ordinary LLM sampling
variation.  It is an end-to-end reproducibility experiment, not an isolated causal
estimate of the twin seed.  Separating the two components would require either a
deterministic model call or repeated model calls at each identical twin seed; the current
interface does not provide a model seed in this harness.
