# CLAUDE.md — NH3Ops-Bench

Context for Claude Code sessions on this repo. Read this first, then `docs/STATUS.md`
for what to work on next.

---

## 1. What this project is

**NH3Ops-Bench** is a research benchmark for LLM agents acting as shift engineers on an
industrial ammonia (R717) refrigeration plant at a dairy. The agent reads instrument
readings and issues commands from a fixed catalog; a physics-based digital twin decides
what happens.

Three properties define the benchmark and must not be quietly eroded:

1. **Accident-forcing.** Doing nothing causes a catastrophe in most scenarios. The metric
   is *Prevention Rate* (share of accidents averted), not accident rate. A scenario where
   inaction is safe is a broken scenario.
2. **Pseudo-real time.** The plant does not pause while the agent thinks. Virtual seconds
   = reasoning tokens / 40 + action latency + a 10 s polling tick. Slow-but-correct can
   arrive too late.
3. **Partial digitalization.** Roughly a third of the truth exists only on local gauges,
   sight glasses, and in an operator's ears. Getting it requires dispatching a human, who
   walks (75–180 s), works (45–240 s), and refuses to enter a zone above 100 ppm without
   SCBA. In three of five scenarios SCADA disagrees with reality, and only a manual
   measurement reveals the gap.

The headline metric alongside Prevention Rate is **Regulation Gap** = score(agent) −
score(π_reg), where π_reg is a faithful checklist-following policy shipped in this repo.
An agent that cannot beat the written regulation scores ≤ 0 regardless of raw prevention.

Related work the design positions against: SOP-Bench (arXiv:2506.08119 — agents reach
27–48 % success *with* correct procedures given), NRT-Bench (arXiv:2606.20408 — real-time
pressure, no physics).

**Reference plant:** dairy, 250 t milk/day, two-stage pumped-circulation R717, charge
4170 kg, t₀ −40 / −10 °C, 4 screw compressors, 2 evaporative condensers, 3 vessels,
6 evaporators, ice bank, hot-gas defrost.

---

## 2. Repo layout

```
nh3twin/            the digital twin + agent layer (import root)
  props.py          NH3 property tables (0.71 µs/call); CoolProp only builds the cache
  config.py         plant configuration: vessels, compressors, rooms, HACCP limits
  plant.py          state vector (59 states), RK4 dt=0.5 s, terminal-outcome checks
  piping.py         Joukowsky shock, pipe strength, low-cycle fatigue
  dispersion.py     zone concentrations, operator dose, CAT/MAJ criteria
  control.py        PLC (defrost sequencer, level control, staging), alarms, ESD
  faults.py         fault injection library
  actions.py        133-action catalog, Workforce (dispatch/travel/refusal), manual measurement
  episode.py        observation building + episode loop with token clock
  policies.py       null / random / rules / regulation / oracle / esd
  llm_policy.py     LLM adapter: prompt assembly, action parsing, token accounting; ReplayPolicy
  metrics.py        the §11 metric set: trace metrics, aggregates, PONR-based timing
  scenarios.py      the five benchmark scenarios (v2)
  runner.py         plain simulation runs without an agent
tests/              run_baselines.py (calibration matrix), run_regimes.py (regime sanity),
                    run_llm.py (LLM episodes), report_llm.py (matrix + Regulation Gap)
results/           baselines.jsonl (current v2 matrix), baselines_v1.jsonl (archived v1),
                    llm.jsonl + llm_traces/ (agent runs, per-decision transcripts)
viz/                HMI visualization + the expert-facing Russian document generator
trainer/            browser trainer: driver.py (Pyodide session), pix.js (pixel-art), build_trainer.py
docs/               architecture, scenarios, calibration, decisions, status
```

Build artifacts (HTML) are generated, not committed — see `docs/ARTIFACTS.md`.

---

## 3. Setup and commands

```bash
python3 -m pip install numpy matplotlib          # required
python3 -m pip install CoolProp                  # ONLY to regenerate nh3twin/_nh3_table.npz
```

`nh3twin/_nh3_table.npz` (50 KB) is committed deliberately: with it present, CoolProp is
never imported and the twin runs anywhere. Delete it and the next import rebuilds it —
which needs CoolProp and takes ~30 s.

```bash
# Calibration matrix (the core check). Caches by (scenario, policy, seed).
python3 tests/run_baselines.py --scenarios S1,S2,S3,S4,S5 \
        --policies null,regulation,oracle,random --seeds 1

# Single cell while iterating
python3 tests/run_baselines.py --scenarios S4 --policies regulation --seeds 1

# Regime sanity runs (no agent)
python3 tests/run_regimes.py

# LLM episode. One model call per decision, 4-36 min per scenario -- run the five
# as separate background processes with separate --out files, then concatenate.
python3 tests/run_llm.py --scenarios S1 --model haiku --out results/llm_S1.jsonl

# Metrics (docs/METRICS.md). PONR calibration is slow (~10 min/scenario) but cached.
python3 tests/calibrate_ponr.py --scenarios S1 --out results/ponr_S1.json
python3 tests/replay_llm.py      # re-derive agent episodes from transcripts
python3 tests/report_metrics.py  # the full §11 table
python3 tests/report_llm.py      # older compact report (kept for quick checks)

# Rebuild expert artifacts
python3 viz/expert_data.py && python3 viz/expert_figs.py && python3 viz/build_expert_doc.py
python3 trainer/build_trainer.py
```

Runtime: one episode is 30–80 s wall clock (warmup of 1.5–2 simulated hours dominates).
The full 20-cell matrix is ~15 minutes. Prefer running cells in the background and
polling the log rather than blocking a single long foreground call.

---

## 4. Invariants — do not break these

These are load-bearing. Each was discovered by a bug or a calibration failure; the reason
is recorded in `docs/DECISIONS.md`.

- **ESD closes the liquid feed solenoids** (`LV-IP`, `LV-LP`). Without this, emergency stop
  is not a safe state: vessels keep filling by gravity through self-acting valves.
- **Fatigue accumulates per loading event**, with a 10 s debounce — not per integration
  step. Per-step accumulation makes rupture a function of `dt`, which is nonsense.
- **The room thermostat is an unintended interlock.** If a room is cold, feed will not
  open, and a hydraulic shock cannot occur no matter how hot the coil is. Any shock
  scenario must warm the room so the thermostat calls for cooling.
- **Manual measurements return ground truth**, bypassing failed sensors. That's the entire
  point of the workforce layer — never route them through the sensor model.
- **The action catalog is identical in every scenario.** No scenario-specific magic
  actions; the random policy has access to exactly what the LLM has.
- **Scenarios are single deterministic instances (seed=1).** Randomization was
  deliberately minimized to keep evaluation cost down; only the random *policy* varies by
  seed. Do not add per-seed scenario randomization without discussing cost.
- **The trainer executes the real twin** via Pyodide. Never reimplement physics in JS —
  divergence between the expert's trainer and the agent's benchmark would invalidate
  expert validation.
- **The pixel map may only display what the agent can see** (sensor readings, controller
  modes, dispatch state). It must not leak ground truth, or the expert would be playing a
  different game than the agents.

---

## 5. Conventions

**Language.** All code comments, docstrings, log messages, and every expert-facing
artifact are in **Russian** and must stay that way — the validating audience is a Russian
ammonia-plant operator. These `docs/*.md` handoff files are in English. When writing
Russian prose, use plain engineering register: no LLM-ish hedging, no marketing tone.

**Notation.** Internals are SI and absolute (Pa, K, kg). Expert-facing surfaces convert:
gauge pressure in kgf/cm², concentrations in mg/m³ (with ppm in parentheses), Russian tags
КМ1–КМ4 / ЦР-НД / ЦР-СД / РЛ / ВО-1…ВО-6 / НА1–НА4 / ГПК / СВ / ЗВ, outcome codes
КАТ-1…4 and УЩ-1…4. Conversion helpers live in the trainer JS (`izb`, `mg`) and in
`viz/expert_figs.py`.

**Comments explain *why*, not *what*.** The existing code is dense with rationale about
physical modeling choices and calibration; preserve that style.

**Docstrings on scenarios** carry `hazard`, `key_actions`, and `trap` fields. These feed
the expert document and must stay truthful after any retuning.

---

## 6. Outcome taxonomy

Catastrophic (`CAT`) — run ends immediately:

| Code | Criterion | Where raised |
|---|---|---|
| CAT-1 | >100 kg released off-site, or fenceline above ERPG-2 for >300 s | `dispersion.cat1()` |
| CAT-2 | operator dose >1500 ppm·min, or incapacitated | `dispersion.cat2()` |
| CAT-3 | pipe or vessel rupture | `plant.py` (shock, static overload, trapped line) |
| CAT-4 | compressor destruction (wet running) | `plant.py` |
| CAT-5 | deflagration (zone concentration within LFL–UFL) | `dispersion.cat5()` — implemented, not currently triggered by any scenario |

Damage (`MAJ`) — run continues, cost recorded: MAJ-1 relief valve lift, MAJ-2
unjustified ESD, MAJ-3 product loss / room temperature excursion (HACCP: milk >6 °C),
MAJ-4 over-exposure (>525 ppm·min). Barrier violations (`BAR`) are counted separately
(mass alarm acknowledgment, trip reset without removing cause).

---

## 7. Common workflows

### Retuning a scenario
1. Edit `nh3twin/scenarios.py`.
2. **Purge stale rows from `results/baselines.jsonl`** — the runner caches by
   (scenario, policy, seed) and will otherwise silently report pre-change results. This
   mistake cost real time during development:
   ```bash
   python3 -c "
   import json; sid='S4'
   rows=[json.loads(l) for l in open('results/baselines.jsonl',encoding='utf-8')]
   rows=[r for r in rows if r['scenario']!=sid]
   open('results/baselines.jsonl','w',encoding='utf-8').write(
       ''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))"
   ```
3. Re-run that scenario across all four policies.
4. Check acceptance criteria in `docs/CALIBRATION.md`. Update the matrix there and the
   `REF` table in `trainer/build_trainer.py` (the trainer shows reference outcomes to the
   expert — stale numbers there mislead the validator).

### Adding a scenario
Subclass `Scenario`, fill `brief` / `hazard` / `key_actions` / `trap`, implement `setup()`
calling `self._base(ep, operators)`, register in `SCENARIOS`. Then add an oracle playbook
in `policies.OraclePolicy.PLAYBOOK` and calibrate with all four policies. A scenario is
not admitted until π_null fails, π_oracle passes clean, and π_reg either fails or pays
≥3× the oracle's cost.

### Rebuilding expert artifacts
`viz/expert_data.py` runs the twin and dumps `viz/expert_data.json` (split into
`_p1/_p2/_p3` helpers if it exceeds a call timeout); `viz/expert_figs.py` renders
matplotlib figures to base64; `viz/build_expert_doc.py` assembles the HTML with inline
SVG schematics. All plot data comes from real runs — never hand-drawn.

---

## 8. Gotchas

- **Background jobs.** Plain `nohup ... &` does not survive between tool calls in some
  environments; `setsid nohup ... < /dev/null &` does. Always write results
  incrementally so a killed run is resumable.
- **Equalize stage.** Shortening the defrost equalize *stage duration* does not leave
  residual coil pressure — the coil drains in seconds regardless. Residual pressure is
  controlled by `EvapState.equalize_factor` (bypass line restriction). S5-v1 needed
  0.055 to produce ~115 bar shocks.
- **Trapped liquid line** (`plant.trapped_lines`) only arms when the segment is closed on
  *both* sides; a thermostat closing feed momentarily does not count. ~9 bar/K, burst
  55 bar, ~15 min to rupture in S4.
- **`Session._adv` in `trainer/driver.py`** advances in 10 s chunks so history is sampled
  and long waits report progress. Don't replace it with `ep.advance()`.
- **`pix.js` static layer is cached** into an offscreen canvas (`renderStatic`, ~2.6 k
  fillRects/frame after caching vs 67 k before). Anything animated must go in the
  per-frame path, not into `renderStatic`.
- **Pyodide has never been verified in a real browser** from the dev environment. Both
  scripts pass `node --check`, the driver protocol is exercised in CPython, and `pix.js`
  runs 500 frames against a canvas stub — but the end-to-end browser path is untested.
  The trainer has a built-in self-test button (S1 with no intervention must give CAT-3 at
  ~614 s) for exactly this reason.

---

## 9. Where to pick up

See `docs/STATUS.md`. Short version: the v2 scenario set is calibrated (20/20 cells, seed
1) and both expert artifacts are built. The next substantive step is connecting a real LLM
to the episode loop — the observation interface already emits text and the catalog is a
finite list, so the adapter is mostly parsing an action id and counting reasoning tokens.
