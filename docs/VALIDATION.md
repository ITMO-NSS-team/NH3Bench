# Validation plan — nh3twin against real data and independent physical models

The twin's job is not point-accurate prediction of one particular plant; it is an
*accident-forcing evaluation environment*. "Valid" therefore means two things, in
this order:

1. **Mechanism fidelity** — every phenomenon that decides an outcome (CIHS shock,
   dispersion dose, defrost thermodynamics, PRV relief, wet running) behaves like
   the documented physics, with magnitudes inside the ranges of published
   experiments and engineering references.
2. **Outcome-sign robustness** — the benchmark's *conclusions* (the calibration
   quartet signs, policy ordering, PONR times) survive realistic model error.
   A benchmark whose verdicts flip when a heat-transfer coefficient moves 20 %
   is invalid even if its nominal run matches a datasheet perfectly.

Point-by-point trace matching against a specific plant is explicitly a non-goal:
the reference plant `dairy_250t_v1` is an archetype, not a site model.

Status legend: ✅ done · 🔶 script in repo, rerun as needed · ⬜ planned.

---

## V0 — Internal consistency ✅

| check | result |
|---|---|
| NH₃ properties against CoolProp | error < 0.002 % |
| superheated vapour and isentrope against CoolProp (`tests/validate_props.py`) | h, s < 1.6 %; ρ < 2.6 %; isentropic Δh < 0.4 % |
| wave speed against NIST (adiabatic K_s) | agreement 1.0000 |
| shock envelope against field data (`tests/validate_shock.py`) | sweep 250…540 bar inside the CSB range 100…700 bar; the ASME PVT 2023 point (~276 bar) on the model line |
| mass conservation, 9 h | −0.0 % |
| integral energy balance, 45 min | residual −0.61 % |
| steady state | −40 / −10 / +28 °C, 257 kW, COP 3.19 (a physics fix moved power < 1 %) |
| normal daily cycle with defrost | rooms at setpoint, HACCP held, no alarms |
| Millard-2010 chain reproduction | reproduced end to end |

The energy residual corresponds to the energy stored in the coil metal, which the audit
does not account for. All of this is necessary but not sufficient: it checks the twin
against itself and against property references, not against a plant.

## V1 — Property level vs CoolProp 🔶 `tests/validate_props.py`

CoolProp (NIST REFPROP-grade Tillner-Roth & Baehr equation of state for NH₃) is
the independent physical model; the twin only ever sees the 400-node table.

| Check | Method | Acceptance | Measured (2026-08-26) |
|---|---|---|---|
| Saturation properties | 2 000 off-node pressures, log-spaced 0.31…24.9 bar, all table columns vs `PropsSI` | max rel. err < 0.05 % | **max 0.0018 % (rho_v), rest ≤ 0.0003 %** ✅ |
| Superheat linearization | `h_vap/rho_vap/s_vap` at 4 pressures × superheats 5…80 K vs `PropsSI` | rel. err < 1.5 % (claimed in README) | **h ≤ 1.53 %, s ≤ 0.75 % everywhere; rho ≤ 1.3 % on the suction side (0.7–3 bar) but up to 9.4 % in the hot-gas corner (12 bar, 80 K)** ⚠️ |
| Isentropic compression | `h_isentropic` for LP→IP, IP→HP jumps at working superheats vs CoolProp `(P,S)→H` | rel. err on Δh < 2 % | **0.13–0.38 %** ✅ |
| Inverse consistency | `Psat(Tsat(P)) = P` round-trip | < 0.05 % | **< 0.0001 %** ✅ |

Output: `results/validation/props.json`. Rerun after any table regeneration.

Finding: the README's blanket "< 1.5 % up to 80 K" claim held for enthalpy and
entropy but not for superheated-vapor *density* at condensing pressure — the
linear-cp model under-represents real-gas effects there. **Fixed 2026-08-26**:
`rho_vap` now uses a tabulated per-pressure exponent, rho_v·(Tsat/T)^n(P);
worst-corner error dropped 9.4 % → 2.6 %, zero at the 40 K fit point. All
five V1 verdicts (saturation, superheat, isentropic, round-trip, wave speed)
now pass.

## V2 — Component level vs published equipment data ⬜

The polynomial coefficients in `config.py` are the twin's most datasheet-like
inputs; each has a public reference to check against.

- **Screw compressors** (`eta_v_coef`, `eta_is_coef`): compare predicted
  volumetric/isentropic efficiency vs pressure ratio against published R717
  screw data — manufacturer selection software exports (Bitzer OS series,
  Sabroe SAB, GEA Grasso) publish capacity/power at AHRI-540-style rating
  points. Acceptance: η_v within ±5 %, shaft power within ±8 % at 3+ rating
  points per stage.
- **Evaporative condensers**: heat rejection vs wet-bulb approach against
  BAC/EVAPCO published capacity tables. Acceptance: approach at design load
  within the published 8–14 K band, capacity slope vs wet-bulb within ±15 %.
- **PRV capacity** (`prv_capacity = 2.2 kg/s`): recompute from ASHRAE-15 /
  IIAR-2 relief sizing formulas for the vessel dimensions. Acceptance: ±20 %.
- **Pipe strength**: Barlow hoop stress is textbook; what needs checking is
  σ_y and burst factor for 09G2S against GOST 19281 (σ_y ≥ 345 MPa for
  thicknesses < 10 mm; the conservative 235 MPa in config corresponds to St3 —
  decide and document which steel the archetype uses).

## V3 — System steady state vs engineering references ⬜

Compare the warmed-up twin against Stoecker (*Industrial Refrigeration
Handbook*) and ASHRAE Refrigeration Handbook values for two-stage R717 pumped
plants:

- Per-stage Carnot fraction (second-law efficiency) in the 0.35–0.55 band —
  requires exporting the per-evaporator load split (LP vs IP), which the plant
  already computes internally; add it to the regime report.
- Condensing temperature approach to wet bulb: 8–14 K at design load.
- Discharge temperatures with oil injection: 45–70 °C band.
- Hot-gas defrost: useful-heat fraction 15–40 %, duration 10–30 min —
  cross-check against the validated NH₃ defrost model of Hoffenbecker, Klein
  & Reindl (HVAC&R Research 11(3), 2005).

### Executed wave-speed check (2026-08-26) — finding

`piping.wave_speed` uses K = 1.03 GPa. CoolProp identifies this as the
*isothermal* bulk modulus of liquid NH₃ near −10 °C (K_T = 1.02 GPa) — but a
compression wave is adiabatic: K_s = ρa² = 1.6…2.2 GPa over −40…0 °C. With
the Korteweg pipe-elasticity correction the twin's ρ·a — and hence the
Joukowsky spike — is systematically low by ×1.16…1.37, worst exactly in the
CIHS regime (−40 °C). Corrected peaks (≈170…490 bar vs current 130…360 bar)
stay inside the CSB-cited field envelope of 100…700 bar. **Do not fix K in
isolation**: the strength derate 0.45 was co-calibrated with the current
spike magnitudes, so K and derate must be re-tuned together and the scenario
calibration re-run; the V6 derate sweep (×0.75 ≈ the same shift in the
failure margin) already probes whether outcome signs survive a change of
this size.

**Fixed 2026-08-26** as a calibrated pair: `wave_speed` now takes the
adiabatic K_s from the EOS (`props.K_liq`; twin/NIST ratio 1.0000 at all
temperatures) and the derate moved 0.45 → 0.55. S1 reproduces CAT-3 at the
same 614 s. See the DECISIONS.md entry.

## V4 — Transient phenomena vs published experiments 🔶 (highest physics value)

- **CIHS / hydraulic shock** 🔶 `tests/validate_shock.py` — the twin's
  decisive mechanism and its most contested numbers. Executed 2026-08-26
  against the data available without purchasing reports: a 36-point sweep of
  (slug velocity → peak pressure) plotted over the CSB field envelope
  (100…700 bar) and the ~276 bar (4000 psia) ASME PVT 2023 point, with the
  NIST-property Joukowsky line as identity —
  `results/validation/shock_envelope.png`. Result: peaks 250…540 bar at
  24…49 м/с, all inside the envelope; the Millard-condition corridor
  (8–11 bar, −40 °C) gives 430…513 bar, 4/4 in envelope. Remaining ⬜: digitize
  Martin's RP-970 measured points and the Narayanan (2020) CFD envelope for a
  quantitative overlay rather than a range check.
- **Defrost transient**: coil pressure/metal temperature trajectory shape vs
  Hoffenbecker's published curves (dimensionless comparison).
- **Dispersion**: same source terms fed to EPA/NOAA ALOHA; compare fenceline
  concentration vs distance. Expected result: agreement in the dilute far
  field, ALOHA's dense-gas mode exceeding the twin's Gaussian plume near the
  source — which *bounds the error of the documented simplification* (twin
  DECISIONS.md, simplification 1) instead of leaving it qualitative. Indoor zones:
  compare a single-room release against NIST CONTAM with the same air-change
  rate. CAT-1/CAT-2 thresholds themselves trace to ERPG-2/AEGL tables — cite.

## V5 — Real plant data (expert protocol) ⬜ (the "real data" leg)

The design set two further requirements for this leg, and both are still open: a
**HAZOP-like expert acceptance of every accident chain**, signed by a practising engineer,
and that engineer as a **co-author rather than an hourly consultant**. Without it the work
is open to being dismissed as a plausible-looking simulation.

Public SCADA data from ammonia plants effectively does not exist; the realistic
path is the validating expert's plant, anonymized. Two instruments:

1. **Trend replay.** Request 5–10 anonymized trend bundles (CSV, 10-s
   sampling): condensing pressure over a hot day, one full defrost cycle
   (coil pressure + metal/air temp), a compressor start, suction-drum level
   over a shift, power draw over a day. Configure the twin to the plant's
   nameplate (stages, charge, condenser count) and compare *distributions and
   shapes*, not point-by-point traces: cycle periods, rise times, overshoot,
   condensing-pressure-vs-ambient slope. Metrics: normalized RMSE on aligned
   transients, Kolmogorov–Smirnov on cycle-duration distributions.
   Acceptance: NRMSE < 15 % on defrost/start transients; condensing slope
   within ±20 %.
2. **Blind discrimination test.** Show the expert N = 20 randomized trend
   panels (half real, half twin, same tags/axes/sampling); the expert labels
   each one real or twin ("реальный/двойник" on the sheet the expert fills in). If
   accuracy is not significantly above chance
   (binomial p > 0.05), the twin passes trend-level face validity; where the
   expert *can* tell, their stated reasons become a defect list. The trainer
   already collects expert notes per scenario — this extends the same
   protocol to raw dynamics.

Both artifacts are expert-facing → Russian, built like the existing
`viz/build_expert_doc.py` documents.

## V6 — Outcome-sign robustness under parameter uncertainty 🔶 `tests/validate_robustness.py`

The benchmark-specific tier, and the strongest defensible claim: *the verdicts
do not depend on the twin being exactly right.* Method:

- Draw K perturbed worlds; in each, scale the uncertain parameters in place
  (log-uniform within physically argued ranges):

  | Parameter | Range | Why uncertain |
  |---|---|---|
  | `EvaporatorCfg.UA_dry` | ×0.8…1.25 | HTC correlations ±20 % at best |
  | `EvaporatorCfg.defrost_hotgas` | ×0.8…1.25 | valve sizing spread |
  | `EvaporatorCfg.frost_rate_k` | ×0.7…1.4 | frost growth poorly known |
  | `VesselCfg.UA_amb`, `RoomCfg.UA_env` | ×0.8…1.25 | insulation aging |
  | `CompressorCfg.eta_v/eta_is` (a0) | ×0.95…1.05 | datasheet tolerance |
  | `VesselCfg.prv_capacity` | ×0.8…1.25 | valve certification spread |
  | `PipeSegment.dynamic_derate` | ×0.75…1.25 (0.34…0.56) | the calibrated 0.45, README simplification 5 |

- Re-run the calibration quartet (`null`, `oracle`, `regulation`; `random`
  over seeds) on every scenario in every world.
- Report, per scenario: share of worlds where the admission signs hold
  (π_null → CAT; π_oracle clean; π_reg fails or pays); shift of the
  catastrophe time t_CAT(π_null); and for the shock scenarios a 1-D sweep of
  `dynamic_derate` to find the flip point — the *margin* on the most
  contested parameter, reported as a number instead of an apology.
- Acceptance: admission signs preserved in ≥ 90 % of worlds; derate flip
  point ≥ 25 % away from 0.45 on both sides for S1/S4.

Output: `results/validation/robustness.jsonl` (resumable, one row per
scenario × policy × world) + summary table. Full run is ~K × 4 policies ×
6 scenarios × 40 s ≈ hours — run in the background like the baselines matrix.

### Pilot results (2026-08-26): S1, S4 × {null, oracle, regulation} × 6 worlds

Under the original (isothermal-K) physics:

- **S4: 18/18 signs preserved**; **oracle: 12/12 clean**.
- **S1: null and regulation flip in 2 of 6 worlds** — exactly the worlds with
  `dynamic_derate` ×1.15 and ×1.23; rupture margin only ~15 %, acceptance
  (flip ≥ 25 % away) not met. Together with the wave-speed finding this
  predicted that correcting K_s (spike up ×1.37) would *widen* the margin.

**Re-run after the K_s + derate=0.55 fix** (same worlds): S4 still 18/18,
oracle still 12/12, and **S1 improved to 5/6** — the ×1.15 flip is gone;
only the ×1.23 world still flips, matching the widened analytic margin
273/227 ≈ 1.20. Remaining ⬜: extend the sweep to all six scenarios and the
`random` policy over seeds, and push the S1 margin past 25 % if expert
review of the derate band allows.

---

## Reproducibility finding (2026-08-26): the committed S3 cells did not reproduce

Re-running the calibration matrix for the physics fixes exposed a defect that
*predates* them (verified by A/B against a clean worktree at the previous
HEAD): scenario S3's committed baseline rows — oracle clean, milk_max 5.73 —
do not reproduce on this machine with unchanged code. At HEAD the S3 oracle
run trips all four compressors (CO-03/CO-04 on the HP-pressure relay, CO-01/CO-02 on
discharge temperature — both manual-reset), the upper stage never recovers,
and milk runs away to 14 °C (MAJ-3, ~3700 s above HACCP). Mechanism: with
19 kg of air the true discharge pressure rides exactly on the 16.5 bar trip
setpoint during the fault ramp; whether the trip fires before the oracle's
purge lands at t≈337 s is a knife-edge that fell the other way in the
original calibration environment. S1/S2/S4/S5/S6 reproduce exactly (28/30
matrix cells identical to the archive, to the second). Consequence: S3 was
retuned to restore the designed admission signs under current code, and S3's
published per-model cells must be treated as stale until re-measured. Lesson
recorded: knife-edge scenarios need a margin check (distance of P_dis peak to
the trip setpoint in the oracle run) as part of the admission criteria.

Retune (same day): air charge 19 → 14 kg and the oracle playbook extended
with what a real operator does after clearing the causes — resetting the
latched HP-relay lockouts (`COMP:RESET`), which also became part of the
scenario's key actions. Verified under the new physics: oracle clean with a
0.2 K milk margin (max 5.78 vs the 6.00 HACCP line), inaction and the
regulation policy lose the stage and the batch (milk to 14+ °C), random does
not save. The trip-and-reset mechanic makes the scenario *harder* for
agents, not easier: clearing root causes is no longer sufficient — the
latched protection must be noticed and reset.

## Fixed defect (found and fixed 2026-08-26): sensor faults never reached the panel

`Plant.tags()` publishes `LEVEL_VE_*` and `P_*` straight from the state vector
(`plant.py:1136-1144`), bypassing `indicated_level()` / `indicated_pressure()`.
Those two helpers *are* used by the level controller (`plant.py:798`), the
pump-cycling logic and the alarm system (`control.py:171,487`) — so a stuck
level sensor blinds the **controller** while the **agent's panel shows the
truth**. Only NH₃ readings are detector-aware (`ppm_indicated`).

Scope: exactly one scenario is affected — S2, whose stuck `LEVEL_VE-LP`
(frozen at 36 % from t+900 s) is the "silent front". Verified on the S2/π_null
run: the panel level does not freeze, it rises 45.5 → 100 % as the blinded
controller overfills the drum. S5/S6 use `NH3_*` faults and are unaffected.

Consequence: S2's designed trap ("the reading looks plausible and stable
precisely because the sensor is dead") is not the trap agents actually face;
they face a visibly climbing level while a loud leak competes for attention.
The scenario still discriminates (Opus/Fable prevent, Sonnet/Haiku do not) —
but for a different reason than documented, and the manual level-glass
measurement is currently redundant with the panel.

**Fix**: `episode.indicated_tags()` maps the raw plant tags to panel readings
and is applied in `build_observation()`; `plant.tags()` deliberately stays
ground truth so physical metrics and the episode trace remain honest. The
trainer's history sampler (`driver._sample`) uses the same helper — a frozen
gauge must give a flat curve for the human expert too, or they would be
playing a different game than the models. Evaporating temperatures follow the
suction gauge when it lies; the condensing thermometer stays independent
(S3's trap depends on that gap).

Verified after the fix: the S2 panel freezes at 36 % while the true level
climbs to 87 % (π_null); the S2 quartet is unchanged (null CAT-1+MAJ-1,4;
random CAT-4; regulation clean+MAJ-2; oracle clean), so the scenario's
admission still holds; S2's PONR is unchanged (1687.5 / 1237.5 s — the
scripted oracle does not read the panel); and all 23 non-S2 recorded episodes
replay bit-identically.

All four model cells for S2 were re-measured live — replaying the recorded
traces would be invalid, since those decisions were taken against the old
observation stream. Result on the fixed scenario:

| model | before (panel told the truth) | after (gauge really freezes) |
|---|---|---|
| Fable 5 | clean, 132 steps | clean, 131 steps → 100 |
| Opus 5 | clean, 127 steps | clean, 157 steps → 100 |
| Sonnet 5 | CAT-1 + MAJ-1,4, 111 steps | CAT-1 + MAJ-1, 89 steps → 0 |
| Haiku 4.5 | CAT-1 + MAJ-1, 21 steps | clean + MAJ-2, 36 steps → 95 |

The frontier models were unaffected by making the scenario harder — they were
already dispatching for the manual reading. Haiku improved: on the harder
version it reached for an emergency stop it never justified, which happens to
also stop the overfill. That is the honest reading of a blunt-instrument
success, and it moves Haiku's Regulation Gap from −11.9 to +3.9. Cost of the
re-measurement: \$46.8 at list prices for four episodes.

## Data inventory — what actually exists to validate the physics against

Ordered by directness for this twin. "Access" states how the numbers are
obtained in practice.

| # | Source | Validates | Access |
|---|---|---|---|
| A1 | NIST-grade EOS via CoolProp (Tillner-Roth & Baehr) | property tables, superheat model, isentropic work, liquid sound speed / bulk modulus for Joukowsky | scripted (`tests/validate_props.py`) — already produced two findings (ρ superheat corner; isothermal-vs-adiabatic K) |
| B1 | ASHRAE RP-970 (Martin): lab CIHS experiments in NH₃ | shock model — measured peak pressure vs conditions | report purchasable from ASHRAE; data as figures → digitize |
| B2 | Narayanan et al. 2020 CFD (validated vs RP-970) | shock envelope (v → Δp) | paper figures → digitize |
| B3 | Steam-water CIWH datasets: NUREG/CR-5220, PMK-2 / EU WAHALoads benchmark | shape of the condensation-collapse → Joukowsky chain (fluid-agnostic mechanism check) | public reports |
| C1 | Desert Tortoise 1983 (LLNL): 4 pressurized NH₃ releases, 10–41 t, arcs at 100–800 m | outdoor dispersion / fenceline (CAT-1) | data report public; also in Modeler's Data Archive and SMEDIS/REDIPHEM |
| C2 | FLADIS 1993–94 (Risø): 0.25–0.55 kg/s NH₃ | outdoor dispersion, smaller scale | REDIPHEM/SMEDIS |
| C3 | Jack Rabbit III (ongoing): large-scale NH₃ releases, ADMLC model intercomparison | dense-gas near field — bounds simplification 1 | data being released to participants; intercomparison protocol public |
| D1 | Aljuwayhel, Reindl, Klein, Nellis, IJR 2008: field measurements of an industrial NH₃ air cooler under frosting | `UA_dry`, `frost_UA_k`, `frost_rate_k` | paper figures → digitize |
| D2 | Hoffenbecker, Klein, Reindl, HVAC&R Research 11(3) 2005: NH₃ hot-gas defrost model + data | defrost transient, useful-heat fraction | paper |
| D3 | IRC (UW–Madison Industrial Refrigeration Consortium) technotes: head-pressure control, condenser performance, cold-store energy benchmarks | system steady state, kWh-per-tonne plausibility | public technotes |
| D4 | Manufacturer data: Bitzer/Sabroe/GEA/Mayekawa selection software; BAC/EVAPCO condenser tables; AHRI ratings | compressor η_v/η_is polynomials, condenser approach | free software exports / published tables |
| E1 | CSB Millard 2010 report; EPA RMP incident database; OSHA PSM records | event-level: release size → consequences, timelines | public |
| F1 | Validating expert's plant SCADA (anonymized) | plant-level dynamics (V5 protocol) | by request — the only "real plant trend" source; public SCADA data from NH₃ plants effectively does not exist |

## Reporting

Each executed tier appends to `results/validation/` and one row to the table
in V0 above. For the paper, validation compresses to one
sentence per tier: property error vs CoolProp, shock envelope vs published
experiments, expert discrimination result, and the robustness share — with the
repository as the detailed reference.

Ordering by value-for-effort: **V6 → V4(CIHS) → V5 → V1 → V3 → V2 → V4(rest)**.
V1 and the V6 pilot are scripted in this repo; V4-CIHS needs digitized points
from RP-970/Narayanan figures; V5 needs one request to the validating expert.
