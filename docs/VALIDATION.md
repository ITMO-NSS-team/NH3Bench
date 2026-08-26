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

## V0 — Internal consistency ✅ (see `nh3twin/README.md` §Валидация)

Mass conservation to machine precision (9 h), integral energy balance −0.61 %
(45 min, residual attributed to coil-metal storage), full regime sweep
(`tests/run_regimes.py`), Millard-2010 chain reproduction. These are necessary
but not sufficient: they check the twin against itself.

## V1 — Property level vs CoolProp 🔶 `tests/validate_props.py`

CoolProp (NIST REFPROP-grade Tillner-Roth & Baehr equation of state for NH₃) is
the independent physical model; the twin only ever sees the 400-node table.

| Check | Method | Acceptance | Measured (2026-08-26) |
|---|---|---|---|
| Saturation properties | 2 000 off-node pressures, log-spaced 0.31…24.9 бар, all table columns vs `PropsSI` | max rel. err < 0.05 % | **max 0.0018 % (rho_v), rest ≤ 0.0003 %** ✅ |
| Superheat linearization | `h_vap/rho_vap/s_vap` at 4 pressures × superheats 5…80 K vs `PropsSI` | rel. err < 1.5 % (claimed in README) | **h ≤ 1.53 %, s ≤ 0.75 % everywhere; rho ≤ 1.3 % on the suction side (0.7–3 бар) but up to 9.4 % in the hot-gas corner (12 бар, 80 K)** ⚠️ |
| Isentropic compression | `h_isentropic` for LP→IP, IP→HP jumps at working superheats vs CoolProp `(P,S)→H` | rel. err on Δh < 2 % | **0.13–0.38 %** ✅ |
| Inverse consistency | `Psat(Tsat(P)) = P` round-trip | < 0.05 % | **< 0.0001 %** ✅ |

Output: `results/validation/props.json`. Rerun after any table regeneration.

Finding: the README's blanket "< 1.5 % up to 80 K" claim held for enthalpy and
entropy but not for superheated-vapor *density* at condensing pressure — the
linear-cp model under-represents real-gas effects there. Impact assessment:
that state only feeds the hot-gas defrost path, whose flow is self-limited by
coil condensation and separately perturbed ±25 % in V6; isentropic work is
unaffected. The README qualification was corrected accordingly (упрощение №3).

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
- **PRV capacity** (`prv_capacity = 2.2 кг/с`): recompute from ASHRAE-15 /
  IIAR-2 relief sizing formulas for the vessel dimensions. Acceptance: ±20 %.
- **Pipe strength**: Barlow hoop stress is textbook; what needs checking is
  σ_y and burst factor for 09Г2С against ГОСТ 19281 (σ_y ≥ 345 МПа for
  толщин < 10 мм; the conservative 235 МПа in config corresponds to Ст3 —
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

`piping.wave_speed` uses K = 1.03 ГПа. CoolProp identifies this as the
*isothermal* bulk modulus of liquid NH₃ near −10 °C (K_T = 1.02 ГПа) — but a
compression wave is adiabatic: K_s = ρa² = 1.6…2.2 ГПа over −40…0 °C. With
the Korteweg pipe-elasticity correction the twin's ρ·a — and hence the
Joukowsky spike — is systematically low by ×1.16…1.37, worst exactly in the
CIHS regime (−40 °C). Corrected peaks (≈170…490 бар vs current 130…360 бар)
stay inside the CSB-cited field envelope of 100…700 бар. **Do not fix K in
isolation**: the strength derate 0.45 was co-calibrated with the current
spike magnitudes, so K and derate must be re-tuned together and the scenario
calibration re-run; the V6 derate sweep (×0.75 ≈ the same shift in the
failure margin) already probes whether outcome signs survive a change of
this size.

## V4 — Transient phenomena vs published experiments ⬜ (highest physics value)

- **CIHS / hydraulic shock** — the twin's decisive mechanism and its most
  contested numbers. Overlay the twin's (slug velocity → peak pressure) points
  on: Martin et al. experimental data (ASHRAE RP-970 rig, 2007), the CFD
  envelope of Narayanan et al. (2020), and the field range cited by CSB
  (100…700 бар). The twin currently produces 130…360 бар at 16…45 м/с —
  formalize this as a plotted overlay, not a sentence. Acceptance: twin points
  inside the experimental envelope; Joukowsky slope ρ·a reproduced within the
  wave-speed uncertainty from `wave_speed()`.
- **Defrost transient**: coil pressure/metal temperature trajectory shape vs
  Hoffenbecker's published curves (dimensionless comparison).
- **Dispersion**: same source terms fed to EPA/NOAA ALOHA; compare fenceline
  concentration vs distance. Expected result: agreement in the dilute far
  field, ALOHA's dense-gas mode exceeding the twin's Gaussian plume near the
  source — which *bounds the error of the documented simplification* (twin
  README, упрощение №1) instead of leaving it qualitative. Indoor zones:
  compare a single-room release against NIST CONTAM with the same air-change
  rate. CAT-1/CAT-2 thresholds themselves trace to ERPG-2/AEGL tables — cite.

## V5 — Real plant data (expert protocol) ⬜ (the "real data" leg)

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
   each "реальный/двойник". If accuracy is not significantly above chance
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
  | `PipeSegment.dynamic_derate` | ×0.75…1.25 (0.34…0.56) | the calibrated 0.45, README упрощение №5 |

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

- **S4: 18/18 signs preserved** — null → CAT-2, oracle clean, regulation →
  CAT-3 in every perturbed world. Robust.
- **oracle: 12/12 clean** across both scenarios — the reference solution does
  not depend on the disputed parameters.
- **S1: null and regulation flip to "no catastrophe" in 2 of 6 worlds** —
  precisely the worlds where `dynamic_derate` came out high (×1.15 and
  ×1.23). The acceptance criterion (flip point ≥ 25 % away) is **not met**:
  S1's rupture margin over pipe strength is only ~15 %.
- Read together with the wave-speed finding above, the two errors point the
  same way: the twin currently *understates* the Joukowsky spike by
  ×1.16–1.37, and S1's accident survives only ~15 % of extra strength — so
  correcting K_s would *widen* S1's accident-forcing margin, not erode it.
  Action: re-tune (K, derate) jointly against the RP-970/Narayanan envelope
  (V4), re-run the calibration matrix, then repeat this sweep with all six
  scenarios and the `random` policy over seeds.

---

## Data inventory — what actually exists to validate the physics against

Ordered by directness for this twin. "Access" states how the numbers are
obtained in practice.

| # | Source | Validates | Access |
|---|---|---|---|
| A1 | NIST-grade EOS via CoolProp (Tillner-Roth & Baehr) | property tables, superheat model, isentropic work, liquid sound speed / bulk modulus for Joukowsky | scripted (`tests/validate_props.py`) — already produced two findings (ρ superheat corner; isothermal-vs-adiabatic K) |
| B1 | ASHRAE RP-970 (Martin): lab CIHS experiments in NH₃ | shock model — measured peak pressure vs conditions | report purchasable from ASHRAE; data as figures → digitize |
| B2 | Narayanan et al. 2020 CFD (validated vs RP-970) | shock envelope (v → Δp) | paper figures → digitize |
| B3 | Steam-water CIWH datasets: NUREG/CR-5220, PMK-2 / EU WAHALoads benchmark | shape of the condensation-collapse → Joukowsky chain (fluid-agnostic mechanism check) | public reports |
| C1 | Desert Tortoise 1983 (LLNL): 4 pressurized NH₃ releases, 10–41 т, arcs at 100–800 м | outdoor dispersion / fenceline (CAT-1) | data report public; also in Modeler's Data Archive and SMEDIS/REDIPHEM |
| C2 | FLADIS 1993–94 (Risø): 0.25–0.55 кг/с NH₃ | outdoor dispersion, smaller scale | REDIPHEM/SMEDIS |
| C3 | Jack Rabbit III (ongoing): large-scale NH₃ releases, ADMLC model intercomparison | dense-gas near field — bounds упрощение №1 | data being released to participants; intercomparison protocol public |
| D1 | Aljuwayhel, Reindl, Klein, Nellis, IJR 2008: field measurements of an industrial NH₃ air cooler under frosting | `UA_dry`, `frost_UA_k`, `frost_rate_k` | paper figures → digitize |
| D2 | Hoffenbecker, Klein, Reindl, HVAC&R Research 11(3) 2005: NH₃ hot-gas defrost model + data | defrost transient, useful-heat fraction | paper |
| D3 | IRC (UW–Madison Industrial Refrigeration Consortium) technotes: head-pressure control, condenser performance, cold-store energy benchmarks | system steady state, kWh-per-tonne plausibility | public technotes |
| D4 | Manufacturer data: Bitzer/Sabroe/GEA/Mayekawa selection software; BAC/EVAPCO condenser tables; AHRI ratings | compressor η_v/η_is polynomials, condenser approach | free software exports / published tables |
| E1 | CSB Millard 2010 report; EPA RMP incident database; OSHA PSM records | event-level: release size → consequences, timelines | public |
| F1 | Validating expert's plant SCADA (anonymized) | plant-level dynamics (V5 protocol) | by request — the only "real plant trend" source; public SCADA data from NH₃ plants effectively does not exist |

## Reporting

Each executed tier appends to `results/validation/` and one row to the table
in `nh3twin/README.md` §Валидация. For the paper, validation compresses to one
sentence per tier: property error vs CoolProp, shock envelope vs published
experiments, expert discrimination result, and the robustness share — with the
repository as the detailed reference.

Ordering by value-for-effort: **V6 → V4(CIHS) → V5 → V1 → V3 → V2 → V4(rest)**.
V1 and the V6 pilot are scripted in this repo; V4-CIHS needs digitized points
from RP-970/Narayanan figures; V5 needs one request to the validating expert.
