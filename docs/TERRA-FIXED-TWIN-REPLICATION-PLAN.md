# Terra model stochasticity at fixed twin seed: analysis plan

## Question

How much does the complete NH3Bench score vary across independent model samples when
the digital-twin trajectory seed and all other harness settings are held fixed?

## Design fixed before collecting replicates 4 and 5

- Model: GPT-5.6 Terra.
- Reasoning effort: `medium`.
- Scenarios: S1--S6.
- Digital-twin RNG seed: 1 for every scenario and replicate.
- History: 14.
- Experimental unit: one complete six-scenario benchmark run.
- Replicates: five independent model samples. Existing identically configured runs from
  the baseline and reasoning experiment are replicates 1--3; two new runs are replicates
  4 and 5.
- Model-sampling seed: not controlled because the current interface does not expose it.

The 30 scenario rows will not be treated as 30 independent observations. Parallel
execution of the two new replicates is permitted because they write separate traces and
result files. All traces must reproduce before analysis.

## Planned analysis

Report all five complete-run unified scores, their mean, sample SD, median, minimum,
maximum, and a percentile bootstrap 95% interval for the mean using 100,000 resamples
and analysis RNG seed 20260913. Also report per-scenario outcome frequencies and score
ranges across the five replicates. No hypothesis test is planned because there is only
one experimental condition; this experiment estimates repeatability rather than a
between-condition effect.

Interpret observed dispersion as model-sampling stochasticity plus any residual service
nondeterminism. Because the twin seed and recorded actions are fixed/replayable, twin
perturbation variability is excluded. With only five replicates, uncertainty estimates
are exploratory and cannot establish a precise variance component.
