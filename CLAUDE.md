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
   SCBA. In three of six scenarios SCADA disagrees with reality, and only a manual
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
  scenarios.py      the six benchmark scenarios (v2 + S6)
  runner.py         plain simulation runs without an agent
  providers.py      provider layer: OpenRouter adapter + factory; llm_policy.py untouched
benchmark.py        user-facing CLI: run / replay / report / validate / list-*
tests/              run_baselines.py (calibration matrix), run_regimes.py (regime sanity),
                    run_llm.py (LLM episodes), replay_llm.py (re-derive from traces),
                    report_metrics.py (the §11 table), report_llm.py (older compact report),
                    calibrate_ponr.py, validate_props.py / _shock.py / _robustness.py
results/           baselines.jsonl + base_S6.jsonl (current matrix), baselines_v1.jsonl,
                    llm.jsonl + llm_traces/ (agent runs, per-decision transcripts),
                    ponr.json + ponr_S6.json, validation/, *_isoK_archive.* (pre-v2.1)
viz/                HMI visualization + the expert-facing Russian document generator
trainer/            browser trainer and demo, one self-contained HTML:
                    driver.py (Pyodide session), pix.js (pixel-art plant),
                    watch.js (replay of recorded runs + Compare), quick.js (quick try),
                    i18n.js (EN/RU), demo_manifest.py (what runs exist),
                    make_snapshots.py (task start states), build_trainer.py
paper/              built AAAI-27 demo paper; LaTeX source is a separate repository
docs/               architecture, scenarios, calibration, decisions, status, BENCHMARK.md
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

On this machine Python is reached as `py` (3.11); there is no `python`/`python3` on PATH.
`requirements.txt` covers numpy, requests and matplotlib.

```bash
# Calibration matrix (the core check). Caches by (scenario, policy, seed).
# NOTE: --scenarios defaults to S1..S5 in every script -- S6 must be named.
python3 tests/run_baselines.py --scenarios S1,S2,S3,S4,S5,S6 \
        --policies null,regulation,oracle,random --seeds 1

# Single cell while iterating
python3 tests/run_baselines.py --scenarios S4 --policies regulation --seeds 1

# Regime sanity runs (no agent)
python3 tests/run_regimes.py

# LLM episode. One model call per decision, 4-36 min per scenario -- run them
# as separate background processes with separate --out files, then concatenate.
python3 tests/run_llm.py --scenarios S1 --model haiku --out results/llm_S1.jsonl

# Same thing through the user-facing CLI (what README documents). --provider
# defaults to claude-cli, i.e. exactly how the published runs were made.
python benchmark.py run --provider openrouter --model <slug> --scenarios S1
python benchmark.py validate          # simulator sanity; --run also plays S1
python benchmark.py report            # compact table; --full for every metric

# Metrics (docs/METRICS.md). PONR calibration is slow (~10 min/scenario) but cached.
python3 tests/calibrate_ponr.py --scenarios S1 --out results/ponr_S1.json
python3 tests/replay_llm.py      # re-derive agent episodes from transcripts
python3 tests/report_metrics.py  # the full §11 table
python3 tests/report_llm.py      # older compact report (kept for quick checks)

# Rebuild expert artifacts
python3 viz/expert_data.py && python3 viz/expert_figs.py && python3 viz/build_expert_doc.py

# Trainer + demo. Snapshots are generated, not committed: without them every task
# start costs a full plant warm-up (23-50 s on CPython, minutes in the browser).
python3 trainer/make_snapshots.py            # once, ~4 min; --check verifies them
python3 trainer/build_trainer.py             # add --llm/--out/--label for your runs
```

Runtime: one episode is 30–80 s wall clock (warmup of 1.5–2 simulated hours dominates).
The full 24-cell matrix is ~18 minutes. Prefer running cells in the background and
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
- **The panel shows indicated readings, `plant.tags()` stays truth.** Sensor faults are
  applied in `episode.indicated_tags()` (used by `build_observation` and the trainer's
  history sampler), never inside `plant.tags()` — physical metrics and the episode trace
  read the latter and must not inherit the lie. Publishing raw levels/pressures to the
  agent silently disabled S2's whole second front once; see `docs/VALIDATION.md`.
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
- **Watch replays through the same worker commands the human player uses**
  (`{cmd:'act', aid, think}`), and renders with the same `renderObs()`. It has no physics
  and no renderer of its own, so it cannot drift from the run it claims to show. The
  thinking phase is advanced in chunks that match `Session._adv`'s own chunking — verified
  to reproduce `t_end`, outcome and release mass exactly.
- **A saved trace is evidence and is never rewritten.** New metrics come from
  `replay_llm.py`; the model is not deterministic, so calling it again would give a
  different episode. The recorded reasoning is shown verbatim in any language.
- **Snapshots must carry a digest of the physics sources** (`driver.sources_digest`). A
  snapshot taken before a coefficient changed loads without error — the class layout is
  the same — and would silently show stale physics. On any mismatch the driver computes
  the warm-up instead, and says which of the two it did.
- **Snapshots must not embed numpy internals.** Ordinary pickle of a numpy 2.x array
  references `numpy._core.multiarray`, which does not exist in the numpy Pyodide ships;
  the snapshot then fails to load, the driver falls back to a warm-up, and the only
  symptom is "somehow slow". `make_snapshots.py` writes arrays as lists and the generator
  as its state, and `--check` refuses a snapshot holding version-specific references.
- **A row measured on part of the scenarios is marked, and gets no Regulation Gap.** A
  mean over two tasks is not comparable with a mean over six, and a difference of such
  means is not a gap. Enforced in `demo_manifest` (`complete`, `n_scored`).
- **One result cell, one run.** S6 lives in both `baselines.jsonl` and `base_S6.jsonl`, so
  anything globbing both must de-duplicate by (scenario, policy, seed) or the scenario is
  counted twice.
- **Test runs must not write into `results/llm_traces/`.** `replay_llm.py` collects that
  directory by mask, so a trial run would be appended to the published matrix as a
  full-fledged row. Use `--trace-dir` (`benchmark.py` derives it from `--out`).
- **The plant's replies are translated on the way out, never in the simulator**
  (`i18n.js` `plantReply`, 117 rules). If no rule matches, the Russian original is shown:
  an incomplete translation is better than an invented one. A rule must consume the whole
  string — a pattern ending in `(.*)` that passes the tail through produces half-English
  lines, which the coverage check counts as translated and a reader sees as a bug.
- **A screen assembled in code must be re-rendered when the language changes.**
  `applyLang` only substitutes markup labels; everything built by JS is redrawn by
  `redrawForLang`, which must know about every such screen (hub, results, run picker, task
  list, briefing, play panel, quick try, outcome, instrument history). The briefing screen
  serves three modes and `mode` is still `"play"` on all three, so `BRIEFKIND` records who
  opened it. A screen missing from `redrawForLang` keeps the language it was drawn in —
  which is exactly how the task briefing stayed Russian under an English interface.

---

## 5. Conventions

**Language.** All code comments, docstrings, log messages, and every expert-facing
artifact are in **Russian** and must stay that way — the validating audience is a Russian
ammonia-plant operator. These `docs/*.md` handoff files are in English. When writing
Russian prose, use plain engineering register: no LLM-ish hedging, no marketing tone.

**The trainer interface is bilingual, the simulator is not.** Four layers, and they are
easy to confuse:

| layer | Russian | English |
|---|---|---|
| interface labels | in the markup, under `data-i18n` | `I18N` in `trainer/i18n.js` |
| labels built in code | `WL` / `QL` | `I18N_JS`, reached through `L("key")` |
| data (commands, tasks, zones, modes, instruments) | from the simulator | `I18N_ACT`, `I18N_SCEN`, `TRMAP_EN`, `STATE_EN`, `TAGMETA.en/.ue`, `ITEM_EN` |
| the plant's replies and recorded model reasoning | as produced | replies by rule (`plantReply`); reasoning **never** translated |

Russian stays in the markup and in `WL`/`QL`, and English is substituted on top — so a
missing key shows Russian rather than an empty slot. When adding a label, add both sides;
`grep 'L("' ` against the dictionaries catches omissions. Grepping alone is not enough,
though: run the bundle under `quickjs` (see §8) and assert that no output of `L`,
`actText`, `scenBrief` or `plantReply` still contains Cyrillic in English mode, and that
none of them has *lost* Cyrillic in Russian mode. Two classes of bug are invisible to a
static check and were both real here — an English task briefing that was never written
(only `S1` had one, so S2–S6 fell back to Russian), and 19 command names whose key was
spelled differently from the action id.

The reverse direction matters just as much: the Russian interface is the canonical one, so
after touching bilingual text diff it against `git show HEAD:` **by words**, not by whole
literals — splitting a caption into keys changes the literals but must not change a single
word the operator sees.

**Notation.** Internals are SI and absolute (Pa, K, kg). Expert-facing surfaces convert:
gauge pressure in kgf/cm², concentrations in mg/m³ (with ppm in parentheses), Russian tags
КМ1–КМ4 / ЦР-НД / ЦР-СД / РЛ / ВО-1…ВО-6 / НА1–НА4 / ГПК / СВ / ЗВ, outcome codes
КАТ-1…4 and УЩ-1…4. Conversion helpers live in the trainer JS (`izb`, `mg`) and in
`viz/expert_figs.py`.

The English interface keeps the **same numbers and the same conversions** — pressure in
`kgf/cm²`, concentration in `mg/m³` — because those are the figures the model sees in its
task; switching to bar would make the demo disagree with the run it is showing. Equipment
tags become the Latin identifiers used inside the simulator (`CO-01`, `VE-LP`, `EV-03`),
and outcome codes become `CAT-n` / `MAJ-n`.

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

### Measuring a new model
`benchmark.py run` wraps `tests/run_llm.py`; the provider layer is `nh3twin/providers.py`
and `llm_policy.py` is deliberately untouched (`OpenRouterPolicy` inherits `act`, the
parser, the stats and the trace format, and overrides only the transport and the token
accounting). Adding a provider means one class plus one branch in `make_policy`.

Two things decide whether the resulting row is comparable: `prompt_lang` (the canonical
task is Russian) and `token_accounting`. Virtual time comes from tokens alone, so a
provider that does not report hidden reasoning gives its model less virtual time than it
actually spent — it reaches the accident early and scores too well. Both fields are
written into every result, and the report prints them.

### Rebuilding expert artifacts
`viz/expert_data.py` runs the twin and dumps `viz/expert_data.json` (split into
`_p1/_p2/_p3` helpers if it exceeds a call timeout); `viz/expert_figs.py` renders
matplotlib figures to base64; `viz/build_expert_doc.py` assembles the HTML with inline
SVG schematics. All plot data comes from real runs — never hand-drawn.

### Changing the demo
`trainer/demo_manifest.py` is the single source of what the interface knows: it scans
`results/`, and the score comes from `metrics.bench_score_run` plus
`report_metrics.esd_justification` — the same functions that print the published table, so
the demo cannot drift into showing numbers of its own. `--selftest` checks the recorded
traces against the canonical clock (`t_action = t_obs + tokens/40 + latency`).

After changing physics, regenerate snapshots (`make_snapshots.py`), or the digest check
will silently send every task start back to a full warm-up.

---

## 8. Gotchas

- **Background jobs.** Plain `nohup ... &` does not survive between tool calls in some
  environments; `setsid nohup ... < /dev/null &` does. On Windows the Bash tool's
  `run_in_background` is the mechanism instead. Always write results incrementally so a
  killed run is resumable — and note that a background job finishing *after* you built an
  artifact means the artifact holds the previous data; compare the embedded bytes with the
  files on disk before trusting a build.
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
- **Pyodide now works in a real browser** — the trainer has been played end to end. The
  built-in self-test (S1 with no intervention must give CAT-3 at ~614 s) is still the way
  to check it, and it now also reports whether the task started from a snapshot or a
  warm-up.
- **No `node` in this dev environment, but the trainer JS can still be *run*.** Syntax:
  the `esprima` pip package (`py -m pip install esprima`, then parse the scripts out of
  the built HTML). Behaviour: the `quickjs` pip package executes the whole bundle under a
  ~60-line browser shim (`document.getElementById` returning a persistent stub object,
  with `querySelector("#id")` resolving to the *same* object — return a fresh one and
  every write is silently lost), after which `setLang`, `plantReply`, `actText`,
  `showBrief`, `showFinal` and the rest can be called directly and the resulting
  `textContent` read back. This is the only check that catches a rule which matches but
  leaves half the line in Russian, or a screen that never gets redrawn; static grepping
  rates both as translated. What the shim cannot cover is layout and the `data-i18n`
  sweep over the real DOM — those still need a browser.
- **Beware bulk find-and-replace in the trainer JS.** Two ways it bites: the first match
  of a UI string is often inside the `WL`/`QL` dictionary, which produces
  `key: L("key")` — infinite recursion that hangs the page on load; and replacing a
  fragment that ends mid-string swallows a quote. Split the file at the end of the
  dictionary before substituting, and parse afterwards.
- **`data-i18n` goes on the element that holds the text and nothing else.** Put it on a
  container and `textContent` wipes out the child elements along with their handlers —
  which is how the "history" button disappeared. `applyLang` now skips elements that have
  children, so a mis-placed key leaves the label untranslated instead of breaking the
  screen, but the marker still belongs on a leaf (wrap the text in a `<span>`).
- **Don't substitute a long instrument name where a short panel label was.** The panel
  had its own short captions ("Молоко", "Уровень ЦР-НД"); reusing `TAGMETA.ru`
  ("t молока", "Уровень ЦР-НД (датчик)") silently rewrote the Russian interface. Adding
  English is not a licence to restyle the Russian — see the word-level diff in §5.
- **`№` is Russian typography.** "Task №4" reads as a typo in English; the number is
  formatted by `scenNo(sid)`, which drops the sign outside Russian. Same class of thing as
  the units, which deliberately do *not* change (§5).

---

## 9. Where to pick up

See `docs/STATUS.md` for the backlog. Short version of where things stand:

- Six scenarios calibrated at seed 1; four Claude models measured across all six
  (`results/llm.jsonl`, transcripts in `results/llm_traces/`).
- Anyone can measure their own model: `benchmark.py` plus the OpenRouter provider, with
  `docs/BENCHMARK.md` as the guide. Verified end to end on a live model.
- The demo ships in the trainer HTML: Watch, Compare, Quick try, plus the full task, in
  English or Russian. Both languages were checked by executing the bundle (§8): every
  `L` key, all 133 command names, all six briefings, all 117 reply rules and every screen
  built in code, in both directions.

Open, in rough priority order: the token-budget frontier (§11.6 — the safety-latency
trade-off is still supported by a single point per model), the expert validation round,
three seeds for π_random, and an English prompt track (`--prompt-lang en`) — which would
be a second, separately labelled column, not a replacement, since the 24 published runs
answered a Russian task.
