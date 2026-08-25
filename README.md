# NH3Bench

A physics-grounded benchmark for LLM agents acting as shift engineers on an industrial
ammonia refrigeration plant. Agents read instruments and issue commands from a fixed
133-action catalog; a digital twin of a dairy's two-stage R717 plant (250 t/day, 4170 kg
charge) decides the consequences.

Three things make it different from scripted operations benchmarks:

- **Accident-forcing** — inaction causes catastrophe, so the metric is prevention, not
  failure rate.
- **The clock never stops** — reasoning tokens convert to virtual seconds (1 token
  ~ 1/40 s), so a slow correct answer can arrive after the rupture. One model died
  mid-thought holding the right answer: it spent 165 virtual seconds writing the
  evacuation order while the gland let go.
- **Partial digitalization** — a third of the truth lives on local gauges and in an
  operator's ears, reachable only by dispatching a human who walks, works, and refuses
  unsafe entry. In most scenarios SCADA disagrees with reality at least once.

## Results — seed 1, six scenarios, four Claude models

Unified score 0–100 (catastrophe = 0; people, economics and discipline multiply — see
`docs/METRICS.md`).

| policy | S1 | S2 | S3 | S4 | S5 | S6 | mean | RegGap |
|---|---|---|---|---|---|---|---|---|
| oracle (scripted solution) | 100 | 100 | 100 | 100 | 100 | 100 | 100.0 | +55.1 |
| Fable 5 | 100 | 100 | 100 | 100 | 78 | 69 | 91.2 | +46.4 |
| Opus 5 | 100 | 100 | 80 | 100 | 67 | 0 | 74.6 | +29.8 |
| always-ESD | 73 | 95 | 57 | 95 | 57 | 0 | 62.8 | +17.9 |
| Sonnet 5 | 0 | 0 | 80 | 53 | 84 | 69 | 47.6 | +2.8 |
| written regulation | 0 | 95 | 80 | 0 | 94 | 0 | 44.9 | — |
| Haiku 4.5 | 0 | 0 | 100 | 0 | 94 | 0 | 32.4 | −12.5 |
| inaction | 0 | 0 | 80 | 0 | 100 | 0 | 30.1 | −14.8 |

**Regulation Gap** = score minus the published checklist-following policy: an agent that
cannot beat the written regulation scores below zero here regardless of raw prevention.
Two of six scenarios are mirrored controls (S5 punishes over-reaction, S6 punishes
trusting a discredited instrument's dismissal): no model passes both, and the per-scenario
rankings invert — fixed dispositions lose one of the two mirrors.

Full per-run analysis: `docs/CALIBRATION.md`, `docs/LLM-BASELINE.md`. Per-decision
transcripts with the models' own reasoning: `results/llm_traces/`.

## Quick start

```bash
python3 -m pip install numpy matplotlib

# reference policies on one scenario
python3 tests/run_baselines.py --scenarios S1 --policies null,oracle --seeds 1

# an LLM agent (needs the Claude Code CLI; ~$0.3-37 valuation per episode)
python3 tests/run_llm.py --scenarios S6 --model haiku

# the full metric report
python3 tests/report_metrics.py
```

## Documentation

| File | Contents |
|---|---|
| `CLAUDE.md` | working context: invariants, conventions, workflows, gotchas |
| `docs/ARCHITECTURE.md` | module map, state vector, key APIs |
| `docs/SCENARIOS.md` | scenario mechanisms, traps, solutions |
| `docs/CALIBRATION.md` | method, acceptance criteria, current matrix, per-model runs |
| `docs/METRICS.md` | the metric set, the unified score, and what it does not mean |
| `docs/LLM-BASELINE.md` | the first agent run, token-clock analysis, metered cost |
| `docs/DECISIONS.md` | why things are the way they are |
| `docs/STATUS.md` | what's done, what's next |
| `docs/DESIGN-original-ru.md` | full design document (Russian) |

Code comments and all expert-facing artifacts are in Russian by design — the validating
audience is a Russian ammonia-plant operator.

> The previous NH3Bench (a single-suction telemetry-control benchmark with a Haiku
> reference agent) is preserved in this repository's git history prior to this tree.
