# Terra reasoning-effort replication: analysis plan

Plan frozen before inspecting the two additional stochastic replicates.

## Design

- Model: `gpt-5.6-terra`, invoked through the saved Codex subscription.
- Effort levels: `none`, `low`, `medium`, `high`, `xhigh`, and `max`.
- Experimental unit: one complete six-scenario NH3Bench run.
- Three independently sampled runs per effort level. The existing sweep is replicate 1;
  two fresh runs are replicates 2 and 3.
- The simulator seed is fixed at 1 in every cell so that simulator variation is not
  mixed into the reasoning-effort comparison.
- Codex CLI and the Responses interface do not expose a model-sampling seed. Replicate
  numbers therefore identify fresh stochastic samples; they are not controllable model
  seeds and cannot recreate a particular sample.

## Outcomes and planned analysis

The primary outcome is the canonical six-scenario NH3Bench score for each complete
replicate. All 18 raw replicate scores will be shown. For each effort level, report the
mean, sample standard deviation, median, range, and a 95% percentile bootstrap interval
for the mean (100,000 resamples; analysis RNG seed 20260912). With only three
replicates per level, these intervals are exploratory descriptions rather than precise
coverage guarantees.

The pre-specified omnibus comparison is a two-sided Kruskal--Wallis test across the six
independent effort groups, with epsilon-squared as effect size. Its p-value will be
computed by 100,000 label permutations because every group has only three observations.
Pairwise two-sided permutation Mann--Whitney tests will be reported only if the omnibus
test is significant, with Holm family-wise correction.

A secondary exploratory monotonic-trend analysis will use Spearman correlation between
the ordered effort code (`none` through `max`) and all replicate scores, with a two-sided
100,000-permutation p-value. No alternative test will replace a non-significant planned
result. Scenario-level rows will not be treated as independent benchmark replicates.

Every new trace will be replayed against the simulator before analysis. Failed or
incomplete cells will be reported and rerun only to obtain a complete pre-specified cell,
not selected by outcome.
