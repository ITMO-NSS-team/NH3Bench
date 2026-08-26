# Decision log

Why things are the way they are. Most entries came from a calibration failure; changing
any of them without reading the rationale will likely reintroduce a bug we already fixed.

---

## 1. Physics discoveries that shaped scenario design

**The room thermostat is an unintended safety interlock.** During S1 calibration the
hydraulic shock refused to occur: with a cold room, the thermostat never opens the feed
valve, so no liquid enters the hot coil regardless of how badly the defrost hung. Both
shock scenarios must explicitly warm the room — which is also realistic, since a room does
warm up during a power outage. This is a genuinely interesting finding about the plant, not
just a modeling artifact: **cold rooms are self-protecting against this accident class.**

**Emergency stop was not a safe state.** In S2, ESD stopped compressors and pumps but left
the self-acting liquid feed solenoids open, so the vessel kept filling by gravity from the
high side and overfilled anyway. Real installations close these on trip. Fixed in
`control.py` by forcing `LV-IP`/`LV-LP` closed on ESD. Without this fix, "stop the plant"
is not a valid answer to an overfill — which would have been a false lesson to teach.

**Equalize duration does not control residual coil pressure.** The coil drains in seconds
whether the stage lasts 8 s or 25 s. Residual pressure — and therefore shock severity —
is controlled by the bypass line restriction, added as `EvapState.equalize_factor`. This
also gave a physically honest defect to build a scenario on: a fouled equalization bypass,
a real commissioning/maintenance fault.

**The wave-speed bulk modulus must be adiabatic, and it travels with the derate.**
Validation against CoolProp (2026-08-26) showed the original K = 1.03 ГПа was the
*isothermal* bulk modulus of liquid NH₃ (K_T at −10 °C); a compression wave is adiabatic,
K_s = ρa² = 1.6…2.2 ГПа, so ρ·a — and the Joukowsky spike — was low by ×1.16…1.37.
Fixed by tabulating the saturated-liquid sound speed (`props.a_l`, `props.K_liq`) and
passing K explicitly through `piping.wave_speed` (no default, so the isothermal constant
cannot silently return). Because the strength derate 0.45 had been calibrated *against
the understated spikes*, it was re-anchored to 0.55 in the same change: known failure
cases still reproduce (S1: CAT-3 at the same 614 s), normal defrost transients still do
not accumulate fatigue, and the value stays inside the physically defensible 0.3…0.7
band. Do not change either constant alone — they are a calibrated pair.

**Fatigue must accumulate per event.** Originally low-cycle fatigue integrated per
timestep, making time-to-rupture a function of `dt`. Now each transient counts as one
loading cycle with a 10 s debounce. Calibrated so a healthy pipe (186 bar limit) survives
~17 cycles at 115 bar shocks and a wall-thinned one (125 bar limit) fails on the second.

**S4's condenser scenario could not be made accident-forcing by CAT.** The HP trip fires
before the relief valve, cutting off the pressure runaway. Rather than defeating the trip,
the scenario was reclassified as a *product-damage* scenario (now S3): inaction gives
MAJ-3, and so does ESD. Benchmarks where emergency stop always wins measure nothing.

---

## 2. Why the scenario set was rebuilt (v1 → v2)

A direct challenge — "won't top models just follow the regulation?" — was tested rather
than argued. `RegulationPolicy` was written as a faithful checklist and run against v1:
it solved S2 outright and prevented catastrophe elsewhere. The concern was correct.

Diagnosed weaknesses of v1: famous accidents are in training data (recall, not reasoning);
one root cause per scenario with the brief nearly naming the suspect; a fixed
scenario→answer mapping learnable in two runs; and paranoia being free, since false alarms
carried no cost.

v2 fixes: compound causes that interact; one classic kept deliberately as a calling card;
a decoy cause that inspection honestly confirms; conflicting written procedure (S3's SOP
orders starting a locked-out pump); a localization action that itself creates the accident
(S4); and a control scenario where the correct answer is *not* to raise an alarm (S5).

Randomization was considered and rejected on the user's cost constraint: single
deterministic instances, seeds only for the random policy. Protection against memorization
is deferred to a **closed scenario set** using mechanisms without famous bulletins
(non-condensable accumulation masquerading as fouling, oil-fouled coils masquerading as
frost, inversions of classic signatures where the failed instrument is the coil gauge).

---

## 3. Deliberate constraints

**No physics in JavaScript.** The expert trainer runs the real Python twin under Pyodide.
A reimplementation would drift, and an expert validating a drifted trainer validates
nothing. Cost: ~15 MB one-time download and no offline use.

**The pixel map shows only agent-visible data.** Gas haze is drawn from *detector
readings*, so in S5 the hall visibly "smokes" from a lying instrument — the same trap the
agent faces, preserved visually.

**Manual measurement returns ground truth.** This is the entire justification of the
workforce layer. Three of five scenarios turn on SCADA disagreeing with reality.

**The action catalog is scenario-independent.** Otherwise the legal-action list leaks the
answer, and the random baseline stops being a fair lower bound.

---

## 4. Known soft spots

- **Dynamic burst coefficient 0.45 × static.** Calibration constant fitted to known
  ruptures. Flagged for expert acceptance in the review sheet; it materially sets when
  pipes fail.
- **Well-mixed zone dispersion.** No floor-level pooling, no cold dense cloud outdoors.
  Understates near-source concentration for large releases; declared in the expert document.
- **S1 recall risk.** Millard is the most-cited ammonia incident in existence; the model may
  remember rather than reason. Mitigated only by the silent-command-failure twist.
- **Single-instance scenarios are, in principle, solvable by a lookup table.** For a fixed
  seed no policy claim like "rules can never solve this" is theoretically sound —
  difficulty lives in the distribution. Acknowledged; the closed set is the answer.
- **Pyodide path never executed in a browser** from the dev environment.
