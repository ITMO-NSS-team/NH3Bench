# Architecture

~8 800 lines total. The twin is stable and rarely needs changes; most work happens in
`scenarios.py`, `policies.py`, and the trainer.

| Module | Lines | Role |
|---|---|---|
| `nh3twin/plant.py` | 1184 | state vector, integration, fast events, terminal checks |
| `trainer/build_trainer.py` | 835 | assembles the browser trainer HTML |
| `trainer/pix.js` | 833 | pixel-art plant visualization |
| `nh3twin/actions.py` | 653 | action catalog + workforce |
| `viz/build_html.py` | 583 | ISA-101 HMI generator |
| `nh3twin/control.py` | 519 | PLC, alarms, safety system |
| `viz/expert_doc_text.py` | 499 | Russian text of the expert document |
| `viz/build_expert_doc.py` | 459 | expert document assembly + SVG schematics |
| `nh3twin/policies.py` | 358 | five reference policies |
| `nh3twin/faults.py` | 336 | fault injection library |
| `nh3twin/scenarios.py` | 295 | five benchmark scenarios |
| `nh3twin/episode.py` | 289 | observation + episode loop |
| `nh3twin/config.py` | 268 | plant configuration dataclasses |
| `nh3twin/props.py` | 254 | NH3 property tables |
| `trainer/driver.py` | 244 | interactive session driver (runs inside Pyodide) |
| `nh3twin/dispersion.py` | 224 | zone dispersion, operator dose, outcome criteria |
| `nh3twin/piping.py` | 190 | Joukowsky shock, strength, fatigue |

---

## Physics layer

**`props.py`** — pre-tabulated saturation properties on a 400-point log-pressure grid
(0.30–25 bar), interpolated at 0.71 µs/call versus ~110 µs for a direct CoolProp call. At
dt = 0.5 s with ~60 property lookups per step this is the difference between a usable and
an unusable twin. `_nh3_table.npz` is the committed cache; CoolProp is imported only when
it is missing.

**`plant.py`** — 59 state variables integrated with RK4 at dt = 0.5 s: vessel masses and
enthalpies, coil pressures and metal temperatures, frost mass, room air and product
temperatures, oil temperatures, ice bank, non-condensable gas mass. Mass balance closes to
better than 0.1 %.

Between integration steps, `_fast_events()` handles discrete phenomena: condensation-induced
shock, static overload, PRV lift, trapped-line pressurization, leak budgets. Terminal
outcomes are checked in `_check_terminal()`.

Key structures:
- `trapped_lines: dict` — liquid segments that can be locked in with no vapor cushion.
  Each entry carries mass, `UA`, `burst`, and current `T`/`P`. Arms only when closed on
  both sides; rises ~9 bar/K.
- `loto: set` — equipment under a work permit; blocks remote start.
- `isolated: set` — vessels shut off by valve; kills leaks sourced from them.
- `manual_comp` / `manual_pump` — agent commands that override PLC staging.

**`piping.py`** — Joukowsky pressure rise for condensation-induced shock, dynamic burst
limit at 0.45 × static (calibration coefficient — flagged for expert acceptance), and
low-cycle fatigue accumulated **per event** with a 10 s debounce.

**`dispersion.py`** — well-mixed zone model with emergency ventilation, water curtain,
and per-operator dose integration. Zone detectors carry `detector_scale`, `detector_bias`,
and `detector_failed` so a scenario can make an instrument lie. Hosts the CAT/MAJ criteria.

## Control layer

**`control.py`** — `PLC` runs the defrost sequencer (PUMPDOWN → HOTGAS → DRAIN → EQUALIZE →
COOL), level control, compressor staging, and condenser control. `stage_duration` is an
instance dict so scenarios can simulate commissioning errors. `AlarmSystem` tracks
priorities and flags mass acknowledgment as a barrier violation. `SafetySystem` implements
trips (LP cutout with auto-return; HP and discharge-temperature trips needing manual reset)
and ESD.

`_set_stage()` respects `manual_feed_locked` and `scada_feed_lock` — a valve closed by the
agent or padlocked by a worker does not reopen on a stage change. This is what makes S1
solvable.

## Agent layer

**`actions.py`** — 133 actions in categories: control (setpoints, compressors, pumps,
defrost, feed valves, level valves, condensers), dispatch (measurements and manual
operations), safety (ESD, ventilation, curtain, evacuation, PPE, notify), alarms, and
explicit `NO_OP`. Each carries a latency in virtual seconds.

`Workforce` models two operators: travel by a zone-to-zone matrix (control room → machine
room 75 s, LT store 110 s, roof 180 s), work durations (sight glass 70 s, portable gas
analyzer 45 s, manual valve 100–110 s, vessel isolation 220 s, permit closure 240 s), and
refusal to enter above 100 ppm without SCBA. `measure()` returns **ground truth** —
including qualitative reports ("periodic dull knocking in the pipeline", "frost and oil
traces on the fitting, hissing audible").

**`episode.py`** — builds the observation (20 visible tags, equipment state *as the
controller reports it*, alarms, dispatch reports, personnel with doses) and runs the loop:

```
dt = reasoning_tokens / THINK_RATE(40) + action.latency + POLL_PERIOD(10 s)
```

`legal_actions()` filters only physically impossible actions (starting a running
compressor), never scenario-specific ones.

**`policies.py`**
- `NullPolicy` — always NO_OP; calibrates accident-forcing.
- `RandomPolicy(seed)` — uniform over legal actions; the only place seeds vary.
- `RulePolicy` — hand-written rules operating solely on the observation.
- `RegulationPolicy(RulePolicy)` — adds three clauses any real regulation contains
  (abort overrunning defrost, stop on shock/trip, shift-wise sight-glass verification).
  This is π_reg, the benchmark's canonical opponent.
- `OraclePolicy` — per-scenario scripted playbook; proves solvability. Not for evaluation.

## Presentation layer

**`viz/`** — `build_html.py` produces an ISA-101 mnemonic HMI; `expert_data.py` →
`expert_figs.py` → `build_expert_doc.py` produce the Russian expert validation document
(9 sections, 11 figures: 5 inline SVG schematics + 6 matplotlib charts from real runs,
plus a Д/У/Н review sheet).

**`trainer/`** — `driver.py` exposes `start(sid)`, `Session.observe/act/wait/final` as JSON
and is executed **inside the browser by Pyodide over the unmodified twin sources**.
`build_trainer.py` base64-embeds 12 twin files plus the driver into a single HTML, wires a
Web Worker, and renders the panel. `pix.js` draws a 384×216 procedural pixel-art plant:
21 animated pipe runs, detailed machines, 16 px walking operators interpolated from
dispatch timings, gas haze from *detector readings only*, click-to-inspect hit regions.

History is sampled by the driver every 10 simulated seconds independent of polling, so a
60-minute wait still yields a full curve in the history window.
