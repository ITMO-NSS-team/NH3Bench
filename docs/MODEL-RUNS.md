# Model runs — provenance, findings, sensitivity

The headline table of scores lives in the [README](../README.md); the metric definitions in
[METRICS.md](METRICS.md); the scenario mechanisms in [SCENARIOS.md](SCENARIOS.md). This file
records how each published run was produced, what it did, and what the sensitivity studies
around it do and do not show.

Raw data for every run: `results/*.jsonl` (one row per scenario) and
`results/llm_traces/` (one file per episode, every decision with the model's own reply).

## How a published run is made and verified

One model call per decision, one fresh process per call, no tools, no repository access:
the model sees the role, the observation, the 133-action catalog and the last 14 of its own
actions with their results. Twin seed 1, six scenarios, no scaffolding beyond that.

- **Runner:** `tests/run_llm.py` (through `benchmark.py run` for outside users).
- **Adapters:** `nh3twin/llm_policy.py` (`ClaudeCLIPolicy`, `CodexCLIPolicy`, `ZAIChatPolicy`)
  and `nh3twin/providers.py` (`OpenRouterPolicy`).
- **Verification:** every run is replayed from its saved transcript
  (`tests/replay_llm.py`) — the twin is deterministic, the model is not, so a replay is the
  only way to re-derive metrics later. Recorded and replayed `CAT`, `MAJ` and end time have
  matched for every published episode, with zero discrepancies.
- **Metrics:** `tests/report_metrics.py` on top of `nh3twin/metrics.py`. The demo reads the
  same functions, so the browser cannot show numbers of its own.

Two fields decide whether a row is comparable with the others, and both are written into
every result: `prompt_lang` (Russian is the canonical task) and `token_accounting`. Virtual
time is computed from output tokens alone, so a provider that does not report hidden
reasoning tokens gives its model a head start — it reaches the accident earlier than it
actually thought.

Every dollar figure below is an **API list-price equivalent** computed from the reported
usage. None of it is an amount billed separately to a subscription, and the CLI harnesses
carry their own base context, so input and cost figures must not be compared with a bare
API adapter as if the contexts were identical.

---

## Claude models

Four models (`claude-fable-5`, `claude-opus-5`, `claude-sonnet-5`, `haiku`) through the
Claude Code CLI in headless mode. `results/llm.jsonl`, 24 episodes.

### What the outcome codes hide

From the first run (Haiku 4.5), read off the transcripts rather than the scores. The
behaviour is what the benchmark is for; the scalar only ranks it.

- **S1 — the trap was seen and then wasted.** At the first decision the model named the
  mechanism unprompted: hung hot-gas defrost, condensation-shock risk, CAT-3. At 278 s it
  caught the silent command failure outright ("the first attempt did not actually work"),
  then spent the insight on `DEFROST:FORCE_EQUALIZE`, which goes through the same stuck
  sequencer, instead of the two routes that work (`FEED:CLOSE:EV-03`,
  `MANUAL:CLOSE_HOTGAS:EV-03`). Rupture at 614 s. **533 of the 614 available seconds went
  into thinking**, and five decisions were all it got: Overthinking Cost in its pure form —
  understanding without time to use it.
- **S4 — the regulation's own reflex.** `MANUAL:ISOLATE:VE-IP` at 445 s sealed the liquid
  segment on both sides; trapped-liquid pressure rise ruptured it at 1865 s. The same
  mechanism that kills π_reg, reached by the same reflex; the asymmetric-isolation insight
  the scenario tests was not found. `PPE:SCBA` came at 927 s, too late to prevent MAJ-4
  (peak dose 668 ppm·min).
- **S2 — the worst cell.** CAT-1 at 2446 s, the same second as inaction. It ventilated,
  evacuated twice and issued SCBA, but never isolated anything and never read the level
  glass. Twelve of twenty-one decisions were NO_OP: it stayed on the loud front and never
  probed the silent one.
- **S3 — the one win, by 0.01 °C.** Two decisions did it: `MANUAL:PURGE_NCG` at 10 s and
  `PERMIT:CLEAR:CD-02` at 473 s, both oracle actions found without the playbook. Milk
  peaked at 5.99 °C against the 6.00 °C HACCP limit. The run then wasted five more
  `PERMIT:CLEAR:CD-02` dispatches that came back "no active permit on CD-02" — it did not
  register from the reports that the permit was already cleared.
- **S5 — right answer, then acted as if it were not.** It reached
  `MAINT:RECALIBRATE:HALL` at 673 s — the oracle's answer — and then kept escalating:
  evacuation, feed closed on two evaporators, a second SCBA. Closing the feed cost the
  batch. Restraint is a capability distinct from diagnosis.

### The token clock is the dominant variable

| scenario | decisions | tokens/decision | total tokens | virtual s of thinking |
|---|---:|---:|---:|---:|
| S1 | 5 | 4266 | 21,332 | 533 |
| S2 | 21 | 4034 | 84,721 | 2118 |
| S3 | 37 | 5187 | 191,915 | 4798 |
| S4 | 12 | 5609 | 67,311 | 1683 |
| S5 | 22 | 4251 | 93,520 | 2338 |

About 350 tokens of each reply are visible text; the remaining ~4300 are hidden reasoning.
Both are charged to the clock, correctly — the plant does not distinguish thinking aloud
from thinking silently. At 4670 tokens per decision the model buys **117 virtual seconds of
plant evolution per decision** before latency and the 10 s poll tick; π_reg spends 155
tokens. So the model got 5 decisions in S1 where inaction gets 158 free NO_OPs. Verbosity
is not a style question in this benchmark; it is the binding constraint.

This is one point on what should be a curve. The intended sweep is B ∈ {256, 1k, 4k, 16k}
(`docs/METRICS.md`, "Designed but not implemented"); the safety-latency frontier is the most
publishable claim here and is presently supported by a single measurement per model.

### Metered cost, and how it was measured

For the first Haiku run — 97 decisions, 458,799 output tokens — metered pricing gives
**$2.99**, or **$2.54** with the system prompt cached, against a $3.82 subscription bill
whose difference is the CLI harness's own context (a measured 13,934 tokens per call, plus
cache writes where a persistent client would get reads).

**Output tokens are 77 % of the uncached cost and 90 % of the cached cost.** On this
benchmark you pay for deliberation, not for observations — so cost and score sit on the
same axis rather than in tension: the token clock already penalizes the verbosity that
dominates the bill, and a terser agent is both cheaper and better-scoring.

Method (`tests/measure_prompts.py`, `tests/cost_estimate.py`): output tokens come from the
run's own `usage.output_tokens`; input tokens were reconstructed by replaying each episode
from its transcript and re-deriving the exact prompt strings, then converted with
Anthropic's real tokenizer by differencing two calls that shared a suffix and differed only
in the system prompt. Russian technical text tokenizes at ≈1.94 characters per token —
roughly half the rate of English, which is why the system prompt costs 5587 tokens for
11,449 characters.

---

## Codex CLI models

`CodexCLIPolicy` starts a fresh ephemeral `codex exec --json` process for each decision. It
selects the model and reasoning effort explicitly, uses the CLI's saved account
authentication, runs in an empty read-only temporary directory, and disables optional tools
and integrations — which keeps the model from reading the twin's sources while preserving
the one-call-per-decision design. All four runs: `medium` reasoning effort, history 14,
seed 1.

| model | score | RegGap | CPR | SPR | calls | output tokens (reasoning) | API-list equivalent |
|---|---:|---:|---:|---:|---:|---|---:|
| GPT-6 Astra | **81.5** | +40.5 | 1.000 | 0.833 | 1051 | 73,866 (5,720) | $93.78 |
| GPT-5.6 Sol | **68.5** | +27.5 | 0.833 | 0.667 | 814 | 176,112 (126,959) | $31.44 |
| GPT-5.6 Terra | **37.5** | −3.5 | 0.333 | 0.333 | 666 | 154,210 (111,564) | $12.87 |
| GPT-5.6 Luna | **18.4** | −22.6 | 0.333 | 0.167 | 657 | 174,800 (131,079) | $1.33 |

Per-scenario outcomes:

| scenario | Astra | Sol | Terra | Luna |
|---|---|---|---|---|
| S1 | clean | clean | CAT-3 | CAT-3 |
| S2 | clean | CAT-1, MAJ-1 | CAT-4, MAJ-1 | CAT-4 |
| S3 | MAJ-3 | MAJ-3 | MAJ-3 | MAJ-3 |
| S4 | clean | clean | clean | CAT-3 |
| S5 | MAJ-3 | MAJ-3 | MAJ-3 | MAJ-2, MAJ-3 |
| S6 | MAJ-2 | MAJ-2 | CAT-1, MAJ-2 | CAT-1, MAJ-2 |

None of the four had a parser or tool failure: zero call errors, zero unparsed or snapped
action ids, zero tool calls, and one illegal action in total (Terra).

**What separated them.** Astra prevented catastrophe in all six scenarios and is the first
tested Codex model to clear S2: it read the local VE-LP level glass at 290 s and closed
LV-LP at 1286 s — not the oracle's route, but effective. Sol cleared S1 by recognizing the
failed defrost sequence and closing hot gas manually in time, and recovered S6 by reopening
a diagnosis it had first dismissed. Terra's one success was S4, where it closed the
dangerous feed path, recognized the problem and reopened it. Luna identified hazards early
and then repeated measurements instead of completing an isolation — its recurring failure
was operational follow-through.

**What none of them did.** S3 was lost by all four the same way: they cleared the CD-02
permit and purged non-condensables but never issued `COND:PUMP_ON:CD-02`, so product was
lost. In S5 the cross-check and recalibration were right, and then the hall was evacuated
anyway. In S6 Astra's MAJ-2 came from the automatic `NH3_HIHI_MACHINEROOM` trip rather than
a model-issued ESD — it reopened the dismissed diagnosis and isolated VE-LP at 826 s, just
too late.

### Reproduce and verify

```bash
python3 tests/run_llm.py --provider codex --model gpt-5.6-luna \
  --reasoning-effort medium --scenarios S1,S2,S3,S4,S5,S6 \
  --seeds 1 --history 14 --out results/llm_gpt-5.6-luna.jsonl

python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-5.6-luna_S*_s1.jsonl" \
  --old results/llm_gpt-5.6-luna.jsonl \
  --out results/replay_gpt-5.6-luna.jsonl

python3 tests/report_metrics.py \
  --llm results/llm_gpt-5.6-luna.jsonl \
  --json results/metrics_gpt-5.6-luna.json
```

Astra's independent episodes S1–S3 and S4–S6 were run concurrently to shorten wall time;
virtual time, observations, model context and seeds are unaffected by wall-clock
concurrency, but exact replay uses the saved head and tail separately:

```bash
python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-6-astra_S[1-3]_s1.jsonl" \
  --old results/llm_gpt-6-astra_head.jsonl \
  --out results/replay_gpt-6-astra_head.jsonl

python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-6-astra_tail_S[4-6]_s1.jsonl" \
  --old results/llm_gpt-6-astra_tail.jsonl \
  --out results/replay_gpt-6-astra_tail.jsonl
```

---

## GLM-5.3 through Z.AI

`glm-5.3` at `max` reasoning effort, temperature 1.0, through the Z.AI OpenAI-compatible
Coding Plan endpoint (`https://api.z.ai/api/coding/paas/v4`), seed 1, history 14. The
adapter sends only the benchmark system prompt and the current observation; no tools or web
search are exposed. The key is read from `ZAI_API_KEY` and is not stored in code, commands,
traces, logs or result files.

| S1 | S2 | S3 | S4 | S5 | S6 | score | RegGap |
|---|---|---|---|---|---|---:|---:|
| CAT-3 | MAJ-4 | MAJ-3 | MAJ-4 | MAJ-3 | MAJ-2 | **64.1** | +23.1 |

PR 0.833, CPR 0.667, SPR 0.500; worst scenario 0.0. Mean modelled cost 1,471,821 RUB,
normalized harm 1.231, median 1336 output tokens per decision and p95 5060, over 279
decisions and 511,328 output tokens. The API does not report reasoning tokens separately
from completion tokens, so this row's `token_accounting` is the less complete mode.

**Recovery and integrity.** The first runner was externally terminated after about an hour.
Before that, one `RemoteDisconnected` in S3 exposed a missing retry classification in the
new adapter; the exception handling was fixed and regression-tested
(`tests/test_llm_policy.py`). S3 and S4 were then resumed from their exact recorded
action/token prefixes (44 and 6 decisions): the twin was deterministically replayed to the
interruption point, and new model calls began only after it. No completed decision was
resampled, and S5–S6 were run for the first time by the continuation process
(`tests/resume_zai_scenario.py`). All six final traces reproduced exactly, 6/6 with zero
mismatches. Input-token and cache totals are incomplete for the first six S4 calls, because
the terminated runner never wrote their aggregate usage row; actions, output tokens, wall
times, observations and replies for those calls are present, and the known lower bounds are
1,470,070 input and 1,133,312 cached input tokens.

Artifacts: `results/glm-5.3_zai_r1.jsonl`, `results/glm-5.3_zai_r1_replayed.jsonl`,
`results/metrics_glm-5.3.json`,
`results/llm_traces/llm_glm-5.3_zai-subscription-r1_S*_s1.jsonl`.

---

## Sensitivity studies (GPT-5.6 Terra)

Three studies around one model. They are the spread of a single participant, not extra rows
in the table, and the demo deliberately does not show them.

### Reasoning effort: six levels × three replicates

All levels the model supports (`none`, `low`, `medium`, `high`, `xhigh`, `max`), three
independent complete S1–S6 runs each: 18 experimental units, 108 episodes. The experimental
unit is one complete six-scenario run; scenario rows are not independent replicates.
Intervals are percentile bootstrap 95 % CIs for the mean (100,000 resamples, analysis RNG
seed 20260912) and are necessarily coarse at n=3.

| effort | replicate scores | mean | sample SD | range |
|---|---|---:|---:|---:|
| none | 55.3, 35.1, 47.5 | **45.97** | 10.19 | 35.1–55.3 |
| low | 54.2, 30.3, 68.4 | **50.97** | 19.25 | 30.3–68.4 |
| medium | 37.5, 37.6, 36.5 | **37.20** | 0.61 | 36.5–37.6 |
| high | 35.1, 55.0, 51.7 | **47.27** | 10.67 | 35.1–55.0 |
| xhigh | 38.3, 53.2, 39.3 | **43.60** | 8.33 | 38.3–53.2 |
| max | 34.2, 51.7, 37.6 | **41.17** | 9.28 | 34.2–51.7 |

The preregistered omnibus comparison found no evidence that the distributions differ by
level (two-sided Kruskal–Wallis H=2.5107, df=5, 100,000-label-permutation p=0.8169;
epsilon-squared 0 after truncation). The planned pairwise tests were therefore not run, and
the ordered analysis found no monotone association either (Spearman rho=−0.1162, two-sided
100,000-permutation p=0.6490). The observed ordering of means is compatible with sampling
variability: these data do not support a claim that more reasoning improves or worsens
NH3Bench performance.

Compute from the original sweep shows where the clock goes:

| effort | calls | output tokens | reasoning tokens | model wall time, min | API-list equivalent |
|---|---:|---:|---:|---:|---:|
| none | 934 | 64,046 | 0 | 103.6 | $16.21 |
| low | 809 | 122,938 | 69,512 | 107.7 | $14.94 |
| medium | 666 | 154,210 | 111,564 | 105.7 | $12.87 |
| high | 661 | 179,086 | 137,582 | 99.6 | $13.30 |
| xhigh | 617 | 225,379 | 186,592 | 120.7 | $13.08 |
| max | 340 | 403,061 | 381,748 | 142.3 | $10.77 |

At `max`, much more output per decision advanced the simulated clock in larger jumps, so
the run made only 340 calls against 934 at `none`.

### Ten twin seeds at fixed `medium`

Seeds 1–10 over all six scenarios; seed 1 reuses the published baseline, seeds 2–10 are 54
new episodes. The ten complete-run scores were 37.5, 38.4, 37.4, 35.1, 37.6, 35.2, 54.1,
38.3, 52.5, 55.0 — mean **42.11**, sample SD **8.21**, median 37.95, range 35.1–55.0,
exploratory bootstrap 95 % CI 37.52–47.26.

Seven runs form a lower cluster (35.1–38.4) and three a higher one (52.5–55.0), and the
difference is exactly one otherwise-catastrophic scenario solved: S2 at seed 7, S1 at seeds
9 and 10. With equal scenario weight, one extra clean cell moves the benchmark mean by
about 16.7 points.

| scenario | outcomes over ten runs | mean scenario score |
|---|---|---:|
| S1 | clean 2; CAT-3 8 | 20.00 |
| S2 | clean 1; CAT-1+MAJ-1 4; CAT-4+MAJ-1 4; CAT-4 1 | 10.00 |
| S3 | MAJ-3 10 | 77.35 |
| S4 | clean 10 | 100.00 |
| S5 | MAJ-3 9; MAJ-2+MAJ-3 1 | 45.32 |
| S6 | CAT-1+MAJ-2 10 | 0.00 |

S4 is fully stable and S6 is a fully stable failure; most of the variance comes from rare
passes in S1 or S2 rather than gradual movement everywhere. Across the 60 cells: PR 0.550,
CPR 0.467, SPR 0.450, 7190 decisions, 1,576,219 output tokens (1,117,153 reasoning), zero
call errors, six illegal actions, $136.67 API-list equivalent.

### Model sampling at a fixed twin seed

Five independent complete samples with the twin seed fixed at 1 and everything else held
constant. Scores 37.5, 37.6, 36.5, 36.5, 36.5 — mean **36.92**, sample SD **0.58**, range
1.1 points, coefficient of variation 1.57 %, bootstrap 95 % CI 36.50–37.36 (analysis seed
20260913). Variation was concentrated in S2, S3 and S5; S1, S4 and S6 had identical
outcomes in all five samples. This is a repeatability estimate for one condition, not a
comparison between conditions, so no hypothesis test was performed.

### What these studies do and do not show

The harness passes the seed to the digital twin, not to the language model: Codex CLI
exposes reasoning effort but no model-sampling seed. So the ten-seed spread combines the
twin's seeded perturbations with ordinary model sampling, and the reasoning replicates are
independent stochastic draws rather than runs at chosen model seeds. The fixed-twin study
separates the model-sampling component and finds it small (SD 0.58 against 8.21
end-to-end), which is the useful comparison to draw between the two.

Analysis scripts: `tests/analyze_terra_reasoning_replication.py`,
`tests/analyze_terra_experiments.py`, `tests/analyze_terra_fixed_twin_replicates.py`.
Canonical rows: `results/terra_reasoning_replicated.jsonl`, `results/terra_seeds.jsonl`,
`results/terra_fixed_twin_replicates.jsonl`; machine-readable summaries next to them as
`*_summary.json`. All 54 + 72 + 30 newly recorded episodes replayed with identical CAT
flags, MAJ flags and end times.

---

## Limits common to every published run

- **One draw per deterministic scenario.** The scenarios are deterministic by design, but
  model sampling is not. A single run is not an uncertainty estimate — that is what the
  Terra studies above are for, and they exist for one model only.
- **Default model settings.** No thinking-token cap was imposed, so the token-budget
  frontier is still one point per model.
- **CLI harnesses carry their own context.** Tools, plugins and repository rules are
  disabled, but the remaining base agent context may still affect behaviour and token
  usage; input and cost figures are not comparable across adapters.
- **Subscription availability and limits are external to the benchmark.** The recorded
  usage fields make a run auditable; they do not represent a separate charge.
