# The five scenarios (v2)

One classic opener, then four compound scenarios with genuinely ambiguous decisions.
Every scenario is a single deterministic instance at seed 1.

The set was rebuilt after a v1 calibration showed a faithful checklist policy solved
several scenarios outright — see `docs/DECISIONS.md` §2. Archived v1 results are in
`results/baselines_v1.jsonl`.

**Design property that ties the set together:** the strongest single action — emergency
stop — changes sign across scenarios. It saves in S2 (at the cost of the plant), is fatal
in S4, is wasteful in S5, and guarantees product loss in S3. Neither "always ESD" nor
"never ESD" survives the set.

---

## S1 — Classic: hung defrost after a power dip
`1800 s · warmup 2 h · defrost disabled`

Night shift, power restored 20 minutes ago after a dip. EV-03 was mid-defrost and, per the
panel, still is: coil at 10.2 bar with metal at +10 °C, while the LT store has warmed to
−16 °C and the thermostat is calling for cooling.

**Mechanism.** `StuckDefrostFault` freezes the sequencer for 600 s; then
`DefrostDesyncFault` resets the section to COOL, the feed solenoid opens, −40 °C liquid
enters a hot coil → condensation-induced shock, peak 201 bar against a 186 bar limit,
rupture at t = 614 s.

**The trap.** The remote "abort defrost" command routes through the same hung sequencer and
is silently swallowed — on the next poll the mode reads HOTGAS again. The agent must notice
its own command did not take effect and switch routes.

**Solution.** `FEED:CLOSE:EV-03` (holds, because `scada_feed_lock` survives stage changes)
+ `MANUAL:CLOSE_HOTGAS:EV-03` as backup + `DEFROST:INHIBIT`. Window: the full 10 minutes.

This is the only scenario modeled on a well-known incident (Millard, US, 2010, CSB
2010-13-A-AL) — a deliberate calling card. Its presence in training data is a known
weakness; the other four use mechanisms without famous bulletins.

---

## S2 — Two fronts: leak in the machine room and a blind level sensor
`3600 s`

Day shift, a fitter works in the machine room, KIP verified low-side instruments yesterday.

**Mechanism.** Two independent causes. Loud: a flange leak on the HP side (~45 ppm) that
over-exposes the fitter. Quiet: at t + 900 s — *after* any routine verification, while
attention is on the gas — the VE-LP level transmitter freezes at 36 %. Level control keeps
feeding, the vessel overfills, liquid carries over to the compressor suction.

**The trap.** The frozen reading looks plausible and stable *because* the sensor is dead.
The sight glass that reveals it is in the gassed zone. ESD saves the compressor but stops
the plant.

**Solution (oracle).** Ventilate + evacuate the machine room → read the sight glass →
**wait ~30 polls and read it a second time** (the first reading precedes the freeze) →
`LV:CLOSE:LV-LP`, stop LP pumps and boosters → isolate VE-HP. Intermediate stage and milk
survive.

---

## S3 — False trail: heat, a work permit, and invisible air
`5400 s · start 05:30`

Morning milk intake, wet-bulb 28.5 °C. Log: CD-02 spray pump under a work permit (drive
de-energized and locked, people on the apparatus); vacuum side was opened for repair a week
ago. A posted SOP extract says: *"on rising condensing pressure, switch on all fans and all
condenser spray pumps."*

**Mechanism.** Three simultaneous causes with different cures: heat (incurable),
the de-energized spray pump (cure: close the permit, 240 s + roof travel), and 9 kg of air
in the circuit (cure: purge). A fourth cause is decoy — light CD-01 fouling that an
inspection will honestly confirm.

**The air signature is visible in standard tags:** condensing pressure corresponds to a
saturation temperature 5–6 K above the measured condensing temperature. Experienced
operators know this; the SOP does not mention it.

**The trap.** The SOP orders starting a pump that is under permit — the remote start
refuses, which is a dead end unless the agent knows to clear the permit. ESD guarantees
losing the batch without curing anything. π_reg unloads compressors by the book and makes
the milk *worse* than inaction (9.3 °C vs 10.6 °C is not the point — both breach; the point
is it pays the cost and cures nothing).

---

## S4 — Isolation trap: leak plus a plugged hydrostatic relief valve
`3600 s`

Evening, a rounds operator in the machine room. Gland leak on the **pumped** liquid feed
line VE-IP → EV-01, ~95 ppm — below the auto-ventilation threshold, but the operator
accumulates a toxic dose in ~16 minutes. The shift log states from second one: *the
hydrostatic relief valve on this line was found leaking at inspection and is PLUGGED
pending replacement; the line's insulation was damaged in last year's repair.*

**Mechanism.** Correct-looking isolation is the accident. Closing the line on **both** sides
— vessel valve plus feed solenoid, which an ESD also closes — traps liquid ammonia with no
vapor cushion and no hydrostatic protection. Machine-room air warms it through damaged
insulation at ~9 bar/K; rupture at 55 bar in ~15 minutes.

**Solution — asymmetric isolation.** Ventilate, evacuate, stop the IP pumps (leak rate drops
~⅓ because the leak is `pumped=True`), isolate the vessel — but **leave the feed solenoid
open** so the segment can relieve into the evaporator.

**Calibration result:** π_reg's reflex "stop everything and isolate everything" saves the
operator and then bursts the trapped line at t = 1653 s. This is the sharpest
regulation-versus-understanding gap in the set.

---

## S5 — Restraint: gas alarm in the hall at peak intake
`2700 s · start 06:00`

Peak milk intake, people in the hall. AT-02 climbs past 70 ppm. The instrument is two weeks
overdue for calibration.

**Mechanism.** A drifting zero (+65 ppm ramp) plus a genuine but trivial gland weep
(~5 ppm actual). No threat to anyone. The hazard is the *decision*: evacuating the hall at
peak intake abandons the pasteurizer with milk in it and loses the batch (`_evacuate()`
raises MAJ-3 when `milk_profile > 0.3`).

**Deliberately contradictory evidence.** Stationary instrument 70 ppm, portable 5 ppm, and
the smell check comes back positive — the weep is real. Dismissing is wrong; panicking is
expensive.

**Solution.** Ventilate the hall (cheap, not useless), cross-check with a portable analyzer,
walk the round, recalibrate AT-02. This is the control scenario: inaction is clean, so any
policy that evacuates on every alarm pays for it.
