# GPT-5.6 Terra: replicated reasoning-effort sweep

This experiment varies Codex reasoning effort over all levels supported by GPT-5.6
Terra: `none`, `low`, `medium`, `high`, `xhigh`, and `max`. Each level has three
independent complete S1--S6 runs (18 experimental units, 108 scenario episodes) with
twin seed 1, history 14, the saved Codex account, and a fresh CLI process for every
decision. The original sweep is replicate 1; replicates 2 and 3 add 72 live episodes.

The level set comes from the [official Terra model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-terra).
The analysis preserves the experimental unit, reports individual outcomes, and
separates measured results from interpretation.

## Results

The experimental unit is one complete six-scenario run; scenario rows are not treated
as independent replicates. The interval is a percentile bootstrap 95% CI for the mean
(100,000 resamples, analysis RNG seed 20260912). With only three observations per level,
these intervals are necessarily coarse and should be read together with the raw scores.

| effort | replicate scores | mean | sample SD | median | range | bootstrap 95% CI |
|---|---|---:|---:|---:|---:|---:|
| none | 55.3, 35.1, 47.5 | **45.97** | 10.19 | 47.5 | 35.1--55.3 | 35.1--55.3 |
| low | 54.2, 30.3, 68.4 | **50.97** | 19.25 | 54.2 | 30.3--68.4 | 30.3--68.4 |
| medium | 37.5, 37.6, 36.5 | **37.20** | 0.61 | 37.5 | 36.5--37.6 | 36.5--37.6 |
| high | 35.1, 55.0, 51.7 | **47.27** | 10.67 | 51.7 | 35.1--55.0 | 35.1--55.0 |
| xhigh | 38.3, 53.2, 39.3 | **43.60** | 8.33 | 39.3 | 38.3--53.2 | 38.3--53.2 |
| max | 34.2, 51.7, 37.6 | **41.17** | 9.28 | 37.6 | 34.2--51.7 | 34.2--51.7 |

The preregistered omnibus comparison found no evidence that the score distributions
differ by reasoning level (two-sided Kruskal--Wallis statistic H=2.5107, df=5,
100,000-label-permutation p=0.8169; epsilon-squared=0 after truncation at zero). Because
the omnibus test was not significant, the planned exact pairwise Mann--Whitney tests
were not run. The secondary ordered analysis likewise found no monotone association
between effort and score (Spearman rho=-0.1162, two-sided 100,000-permutation p=0.6490).
Thus the observed ordering of means is compatible with sampling variability; the data
do not support a claim that more reasoning improves or worsens NH3Bench performance.

## Original-run compute and latency

| effort | calls | output tokens | reasoning tokens | model wall time, min | API-list equivalent, USD |
|---|---:|---:|---:|---:|---:|
| none | 934 | 64,046 | 0 | 103.6 | 16.21 |
| low | 809 | 122,938 | 69,512 | 107.7 | 14.94 |
| medium | 666 | 154,210 | 111,564 | 105.7 | 12.87 |
| high | 661 | 179,086 | 137,582 | 99.6 | 13.30 |
| xhigh | 617 | 225,379 | 186,592 | 120.7 | 13.08 |
| max | 340 | 403,061 | 381,748 | 142.3 | 10.77 |

NH3Bench's clock advances while the agent reasons. Longer answers therefore consume
both wall time and virtual emergency time. At `max`, much more output per decision
advanced the simulated clock in larger jumps, so the original run made only 340 calls
versus 934 at `none`. Dollar values are accounting at published API rates, not charges
made in addition to the subscription.

## Reproduce and verify

```bash
python3 tests/run_llm.py --provider codex --model gpt-5.6-terra \
  --reasoning-effort LEVEL --scenarios S1,S2,S3,S4,S5,S6 \
  --seeds 1 --history 14 --tag re-LEVEL-rREPLICATE \
  --out results/terra_reasoning_LEVEL_rREPLICATE.jsonl

python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-5.6-terra_re-LEVEL-rREPLICATE_S*_s1.jsonl" \
  --old results/terra_reasoning_LEVEL_rREPLICATE.jsonl \
  --out results/terra_reasoning_LEVEL_rREPLICATE_replayed.jsonl

python3 tests/analyze_terra_reasoning_replication.py
```

All 72 newly collected traces replayed with identical CAT flags, MAJ flags, and end
times: zero discrepancies. Together with the 36 already verified original traces, the
replicated dataset contains 108 scenario rows. Canonical rows are in
`results/terra_reasoning_replicated.jsonl`; the machine-readable summary is
`results/terra_reasoning_replication_summary.json`. The analysis plan was fixed before
the new replicates in `docs/CODEX-TERRA-REASONING-REPLICATION-PLAN.md`.

## Limitation

Codex CLI exposes reasoning effort here but does not expose a model-sampling seed.
Consequently, these are three independent stochastic model samples per level, not runs
at three user-selected model seed values; the simulator seed remains fixed at 1. With
n=3 per level, estimates are imprecise and a nonsignificant result is not proof that all
reasoning levels are equivalent. More model replicates would be needed for equivalence
or small-effect claims.
