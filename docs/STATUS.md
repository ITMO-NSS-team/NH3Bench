# Status and backlog

Snapshot at handoff.

## Done

- **Digital twin** — stable, ~5 600 lines, mass balance <0.1 %, reproduces the Millard-class
  shock (201 bar vs 186 bar limit).
- **Agent layer** — 133-action catalog, workforce with travel/work/refusal, token clock,
  observation interface emitting both structured JSON and rendered text.
- **Scenario set v2** — five scenarios, calibrated 20/20 cells at seed 1.
- **Five reference policies** including π_reg, the published opponent for Regulation Gap.
- **Expert validation document** (Russian, HTML, 11 figures, review sheet) — for a plant
  operator to validate realism.
- **Browser trainer** (Russian, HTML, Pyodide) — lets the same expert *play* the scenarios
  under the same time pressure agents face, with a pixel-art plant view, per-indicator
  history with axes, wait options up to 60 min, and click-to-inspect.
- **Design document** updated with the v2 section: compound scenarios, calibration quartet,
  acceptance criteria, Regulation Gap. (`docs/DESIGN-original-ru.md`, Russian.)
- **S6 "Discreditation"** — sixth scenario, designed from the measured failure modes of
  the four-model sweep: mirrors S5's evidence picture, then the discredited detector
  starts telling the truth. Immediate ESD does *not* save it (closes the smart-ESD
  loophole); the regulation's isolate-everything order is too slow by construction;
  cheapest scenario in the set (1500 s horizon, ~40 frontier decisions). Calibrated
  5/5 at seed 1 and run against all four models: zero clean passes (oracle only) —
  Fable/Sonnet prevent with MAJ-2 (69), Opus and Haiku end in catastrophe. See
  `docs/CALIBRATION.md` § S6.
- **LLM adapter + first agent run** — `nh3twin/llm_policy.py` drives a real model through
  the episode loop; Haiku 4.5 has run all five scenarios. Results in
  `results/llm.jsonl`, per-decision transcripts in `results/llm_traces/`, analysis in
  `docs/LLM-BASELINE.md`.
- **The §11 metric set** — `nh3twin/metrics.py` + `tests/report_metrics.py`: CPR by the
  document's definition, Human Harm Index (never monetized), Cost of Prevention with
  published prices, energy per tonne, tokens per decision, Margin-to-PONR and Overthinking
  Cost. π_esd added as the mandatory §12.2 baseline; ESD justification is derived from
  π_null/π_esd runs, not assigned. PONR calibrated for all five scenarios
  (`tests/calibrate_ponr.py`, `results/ponr.json`) — closes former backlog item 5.
  Agent runs are re-derived from transcripts by `tests/replay_llm.py` (twin is
  deterministic, model is not). Definitions and caveats: `docs/METRICS.md`.

## Next up — in priority order

### 1. Token-budget frontier
The first run answered the headline question and raised a sharper one. Haiku spent
**4670 tokens per decision** — 117 virtual seconds of thinking before any action — and lost
S1 with 87 % of its window consumed by deliberation. The design document (§11.6) already
specifies budgets B ∈ {256, 1k, 4k, 16k}; the adapter needs a cap (`MAX_THINKING_TOKENS`
for the Claude Code backend, or an explicit instruction plus truncation) and a re-run at
two or three points. The expected shape — a safety-latency frontier where accuracy and
timeliness trade off — is the benchmark's most publishable claim and is currently
supported by a single point.

Second models are cheap now that the adapter exists: `--model sonnet` / `--model opus`
change one flag.

### 2. Expert validation round
Send both HTML artifacts to an ammonia-plant operator. The review sheet (Д/У/Н per item)
returns structured feedback; the trainer emits a JSON protocol per playthrough. Highest
priority items for them: the 0.45 burst coefficient, alarm thresholds (should they be
brought to the Russian PB values 20/60 mg/m³?), the ~9 bar/K trapped-liquid figure, and
whether the S4 asymmetric isolation is what they'd actually do.

### 3. Three seeds for π_random
Deferred by decision, but needed before publication — one seed does not bound the chance a
random agent stumbles into ESD.

### 4. Closed scenario set
Memorization defense. Mechanisms without famous bulletins; see `docs/DECISIONS.md` §2.

### 5. Unit tests
Mass balance, property-table accuracy against CoolProp, shock model, fatigue accumulation.

### 6. Browser verification of the trainer
Open it, run the built-in self-test (S1 with no intervention must yield CAT-3 at ~614 s),
confirm the pixel map and history window render. Never done from the dev environment.

## Environment notes carried over

- Episodes cost 30–80 s wall clock; the 20-cell matrix ~15 min. Run in background with
  `setsid nohup ... < /dev/null &` and poll the log; plain `nohup &` did not always survive.
- **LLM episodes cost 4–36 min wall clock each** — one model call per decision, 20–110 s
  apiece. Run the five scenarios as five parallel processes writing to separate `--out`
  files, then concatenate into `results/llm.jsonl`; five concurrent Claude Code processes
  produced no rate-limit errors in 97 calls.
- Always write results incrementally (`run_baselines.py` already appends per cell) so an
  interrupted run resumes.
- `viz/expert_data.py` may exceed a single call timeout; it was split into `_p1/_p2/_p3`
  parts with incremental JSON saving during development.
