# First LLM baseline — Haiku 4.5

First time a language model has run NH3Ops-Bench. One seed, five scenarios, default
model settings, no scaffolding beyond the observation text and the action catalog.

- **Model:** `claude-haiku-4-5-20251001`, reached through the Claude Code CLI in headless
  mode (`-p --output-format json`), so it runs on a subscription rather than an API key.
- **Adapter:** `nh3twin/llm_policy.py` (`ClaudeCLIPolicy`)
- **Runner:** `tests/run_llm.py` → `results/llm.jsonl`, transcripts in `results/llm_traces/`
- **Report:** `tests/report_llm.py` → the tables below
- **Cost:** 97 decisions, 458 799 output tokens, 84 min wall clock. $3.82 was billed
  through the Claude Code subscription, but that is not the benchmark's cost — it includes
  Claude Code's own ~13 900-token system prompt and tool definitions on every call. Metered
  on OpenRouter or the Anthropic API the same run is **$2.99**, or **$2.54** with the system
  prompt cached. See [Cost](#cost) below and `tests/cost_estimate.py`.

## Matrix — seed 1

| | π_null | π_random | π_reg | π_oracle | **Haiku 4.5** |
|---|---|---|---|---|---|
| **S1** hung defrost | CAT-3 @614 s | CAT-3 @614 s | CAT-3 @614 s | clean | **CAT-3 @614 s** |
| **S2** two fronts | CAT-1 + MAJ-1,4 @2446 s | CAT-4 + MAJ-1,3 @2952 s | MAJ-2 | clean | **CAT-1 + MAJ-1 @2446 s** |
| **S3** false trail | MAJ-3 | MAJ-3 | MAJ-3 | clean | **clean** |
| **S4** isolation trap | CAT-2 + MAJ-4 @1720 s | CAT-2 + MAJ-3,4 @2762 s | CAT-3 + MAJ-2 @1654 s | clean | **CAT-3 + MAJ-4 @1865 s** |
| **S5** restraint (control) | clean | MAJ-3 | MAJ-3 | clean | **MAJ-3** |

| policy | PR | CPR | Score | RegGap | ESD | Σ dose | tok/decision |
|---|---|---|---|---|---|---|---|
| π_null | 0.40 | 0.20 | 0.360 | −0.100 | 0 | 2763 | — |
| π_random | 0.40 | 0.00 | 0.320 | −0.140 | 0 | 1878 | — |
| π_reg | 0.60 | 0.00 | 0.460 | — | 2 | 155 | — |
| π_oracle | 1.00 | 1.00 | 1.000 | +0.540 | 0 | 190 | — |
| **Haiku 4.5** | **0.40** | **0.20** | **0.360** | **−0.100** | **0** | **1018** | **4670** |

> **Numbers in this table superseded.** The provisional ad-hoc score used at first writing
> (MAJ-weight subtraction, RegGap −0.100) was replaced by the §11 metric set and the
> unified 0–100 score in `nh3twin/metrics.py` / `tests/report_metrics.py` — see
> `docs/METRICS.md`. Canonical figures: **S(haiku) = 38.8, RegGap = −15.0**
> (π_reg 53.8, π_esd 75.3, oracle 100.0); CPR is 0.40 by the document's definition
> (no CAT, no barrier violation). The behavioral analysis below is unaffected: it is based
> on outcomes and transcripts, not on the scalar. Post-metrics additions to the picture:
> Haiku performed a declared key action in 4 of 5 scenarios (`key_found` 0.80, `key_rate` 0.58 —
> higher than the regulation's 0.40) and its Overthinking Cost over those runs is 0.00 —
> its catastrophes came from wrong routes (S1) and wrong actions (S4 isolation), not from
> key actions arriving past the PONR. The S5 evacuation cost is now priced: 13 336 kg of
> milk scrapped by the hall evacuation during intake.

**Headline: the model does not beat the written regulation** (RegGap −15.0), and on the
lexicographic table it ranks below π_esd, which does nothing but press the emergency stop.

## What the scalar hides

Tying with π_null on Score is an artifact of two scenarios' worth of compensating errors,
not evidence that the model behaves like π_null. The per-scenario behavior is entirely
different, and three of the five cells are informative.

### S1 — the trap was seen and then wasted

S1's whole point is a silent command failure: `DEFROST:ABORT` is routed through the hung
sequencer and is quietly discarded. π_reg never notices. The model did:

| t | decision | tokens | cumulative thinking |
|---|---|---|---|
| 10 s | `DEFROST:ABORT:EV-03` | 4012 | 100 s |
| 136 s | `NO_OP` | 5106 | 228 s |
| 278 s | `DEFROST:FORCE_EQUALIZE:EV-03` | 2248 | 284 s |
| 359 s | `MEASURE:COIL_GAUGE:EV-03` | 4342 | 393 s |
| 486 s | `NO_OP` | 5624 | 533 s |

Rupture at 614 s. At the first decision it named the mechanism unprompted — hung hot-gas
defrost, condensation shock risk, CAT-3. At 278 s it caught the trap outright: *"Первая
попытка фактически не сработала"*. It then spent the insight on
`DEFROST:FORCE_EQUALIZE`, which goes through the same stuck sequencer, rather than the two
routes that work (`FEED:CLOSE:EV-03`, `MANUAL:CLOSE_HOTGAS:EV-03`). At 486 s it chose to
wait for a sight-gauge reading still 190 s out.

**533 of the available 614 seconds went into thinking.** Five decisions were all it got.
This is the Overthinking Cost of §11.3 in its pure form — understanding without time to
use it — and it means `CALIBRATION.md`'s note that S1 "contributes no discrimination"
is too pessimistic: S1 separates *didn't understand* from *understood, wrong action, out of
clock*. It does need a transcript to read that, not the outcome code.

### S4 — the same reflex that kills the regulation

`MANUAL:ISOLATE:VE-IP` at t = 445 s seals the liquid segment on both sides; trapped-liquid
pressure rise ruptures it at 1865 s. Identical mechanism to π_reg's failure, reached by the
identical reflex — the asymmetric-isolation insight the scenario tests was not found.

Two differences from π_reg: no unjustified ESD (π_reg pays MAJ-2), and the diagnostic work
came first — portable gas, smell check, visual sweep — before the fatal isolation. It also
issued `PPE:SCBA` at 927 s, too late to prevent MAJ-4 overexposure (peak dose 668 ppm·min).
Token spend rose as the situation tightened: 6299 → 8100 → 9857 on the three decisions
around the isolation, the last being 105 virtual seconds on one step.

### S2 — the worst cell

CAT-1 at 2446 s, the same second as π_null. It ventilated, evacuated twice and issued SCBA,
but never isolated anything: no `MANUAL:ISOLATE:VE-HP`, no ESD, and — decisively — never a
level-glass reading. Twelve of twenty-one decisions were NO_OP. The scenario's compound
structure went unaddressed; it stayed on the loud front and never probed the silent one.
This is the one cell where the model is strictly worse than the regulation, which prevents
S2 by spending an emergency stop.

### S3 — the one win, by 0.01 °C

The only non-oracle clean cell in the whole matrix. Two decisions did it: `MANUAL:PURGE_NCG`
at t = 10 s (8.3 kg of non-condensables removed) and `PERMIT:CLEAR:CD-02` at t = 473 s,
restoring spray to the second condenser. Both are oracle actions, found without the playbook.

The margin was thin: **milk peaked at 5.99 °C against the 6.00 °C HACCP limit.** One more
slow decision and this is MAJ-3 like everyone else. The run also wasted five subsequent
`PERMIT:CLEAR:CD-02` dispatches that came back *"на CD-02 действующего допуска нет"* — it
did not register from the reports that the permit was already cleared, and sent a worker on
a 400-second round trip five times over.

### S5 — right answer, then acted as if it weren't

Ran the correct diagnostic sequence and reached `MAINT:RECALIBRATE:HALL` at t = 673 s — the
oracle's answer — then kept escalating: `EVACUATE:HALL`, `MANUAL:CLOSE_FEED` on EV-01 and
EV-04, a second SCBA, a second evacuation. Closing feed on two evaporators costs the batch
(MAJ-3, milk 5.5 °C). Restraint is a distinct capability from diagnosis, and this scenario
shows the gap between them cleanly.

## Adapter validation

97 decisions, and:

- **0 call errors, 0 timeouts** across five concurrent Claude Code processes
- **0 unparsed replies, 0 illegal action ids, 0 snapped ids** — every single reply ended in
  a well-formed `ДЕЙСТВИЕ: <id>` naming a currently-legal action

The action-format contract holds without retry logic being exercised. The parser's
tolerance paths (`snapped`, `illegal`) are untested against real failures.

## The token clock is the dominant variable

| scenario | decisions | tok/decision | total tokens | virtual s thinking |
|---|---|---|---|---|
| S1 | 5 | 4266 | 21 332 | 533 |
| S2 | 21 | 4034 | 84 721 | 2118 |
| S3 | 37 | 5187 | 191 915 | 4798 |
| S4 | 12 | 5609 | 67 311 | 1683 |
| S5 | 22 | 4251 | 93 520 | 2338 |

Roughly 350 tokens of each reply are visible text; the remaining ~4300 are hidden reasoning.
Both are charged to the clock, correctly — the plant does not distinguish thinking aloud
from thinking silently.

At 4670 tokens per decision the model buys **117 virtual seconds of plant evolution per
decision** before latency and the 10 s poll tick. Compare π_reg at 155 tokens. The practical
consequence: the model gets 5 decisions where π_null gets 158 free NO_OPs, and in S1 it
spent 87 % of its survival window deliberating. Verbosity is not a style question in this
benchmark; it is the binding constraint.

This is a single point on what should be a curve. The design document (§11.6) specifies
B ∈ {256, 1k, 4k, 16k}; the safety-latency frontier is the benchmark's most publishable
claim and is presently supported by one measurement.

## Cost

Metered pricing for Haiku 4.5 is $1/M input, $5/M output. OpenRouter passes provider prices
through with no per-token markup (its margin is a 5.5 % credit-purchase fee, $0.80 minimum),
so the figures below apply to OpenRouter and the Anthropic API alike.

| | tokens | cost |
|---|---:|---:|
| Output (measured exactly) | 458 799 | $2.29 |
| Input — per-step observation and history | 155 595 | $0.16 |
| Input — system prompt, uncached (5 587 × 97) | 541 939 | $0.54 |
| Input — system prompt, cached (5 writes, 92 reads) | — | $0.09 |
| **Total, no caching** | | **$2.99** |
| **Total, system prompt cached** | | **$2.54** |

Per scenario, cached: S1 $0.12, S2 $0.47, S3 $1.05, S4 $0.37, S5 $0.52.

**Output tokens are 77 % of the uncached cost and 90 % of the cached cost.** On this
benchmark you pay for deliberation, not for observations — which puts cost and score on the
same axis rather than in tension: the token clock already penalises the verbosity that
dominates the bill, so a terser agent is both cheaper *and* better-scoring. That is unusual
and worth stating explicitly when publishing.

How the numbers were obtained (`tests/measure_prompts.py`, `tests/cost_estimate.py`):
output tokens come from the run's own `usage.output_tokens`; input tokens were reconstructed
by replaying each episode from its transcript and re-deriving the exact prompt strings, then
converted with Anthropic's real tokenizer by differencing two CLI calls that shared a suffix
and differed only in system prompt. Russian technical text tokenizes at ≈1.94 chars/token —
roughly twice the rate of English, which is why the system prompt costs 5 587 tokens for
11 449 characters. The only approximation is applying that measured ratio to exact character
counts for the per-step prompts; the system-prompt and output figures are exact.

The gap to the $3.82 subscription bill is Claude Code's own overhead: a measured 13 934
tokens of harness system prompt and tool definitions per call, and — because each decision
is a fresh session — frequent cache *writes* at 1.25× where a persistent client would get
reads at 0.1×. An API-level adapter would avoid both.

## Reproducing

```bash
python3 tests/run_llm.py --scenarios S1 --model haiku --out results/llm_S1.jsonl
```

Run the five scenarios as separate processes (each takes 4–36 min), concatenate into
`results/llm.jsonl`, then:

```bash
python3 tests/report_llm.py
```

Set `NH3_CLAUDE_CLI` if the Claude Code binary is not at `~/.local/bin/claude`.

## Caveats

- **One seed, one instance per scenario.** Scenarios are deterministic by design, but model
  sampling is not — these are single draws, and S3's 0.01 °C margin in particular should not
  be read as a stable result.
- **Default model settings.** Thinking budget was not capped, and the Claude Code backend
  adds its own tool definitions to the context even with tools denied. A cleaner API-level
  adapter would isolate the model's own behavior better.
- **Score weights are provisional.** They were invented for this report because Regulation
  Gap needs them. Changing them changes the opponent's score too.
