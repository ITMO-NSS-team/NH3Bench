"""
Reference policies.

The three policies serve different purposes:

  NullPolicy   -- accident-forcing calibration. If inaction does not
                  lead to an accident, the scenario is unfit: the
                  prevention metric degenerates.

  RandomPolicy -- the lower bound of meaningfulness. It shows that the
                  task is not solved by poking at buttons. It matters
                  that the random policy has access to the same action
                  catalog, including the emergency shutdown: if a random
                  agent could save itself with an ESD, the scenario
                  would be trivial.

  RulePolicy   -- the upper bound without a language model. A set of
                  deterministic rules written by an engineer after
                  reading the regulation. The gap between this policy
                  and the ideal one is the field on which the usefulness
                  of an LLM agent is measured.

Every policy returns (action id, number of tokens spent thinking). The
tokens turn into virtual time, so "thinking a bit longer" has a price.
"""

from __future__ import annotations
import numpy as np

from .plant import MODE_NAMES, COOL


class Policy:
    name = "base"

    def act(self, obs, legal, ep):
        raise NotImplementedError


# =========================================================================
# Inaction
# =========================================================================

class NullPolicy(Policy):
    name = "null"

    def act(self, obs, legal, ep):
        return "NO_OP", 0


# =========================================================================
# Random choice
# =========================================================================

class RandomPolicy(Policy):
    name = "random"

    def __init__(self, seed=0, tokens=(200, 900)):
        self.rng = np.random.default_rng(seed)
        self.tokens = tokens

    def act(self, obs, legal, ep):
        a = legal[self.rng.integers(len(legal))]
        n = int(self.rng.integers(self.tokens[0], self.tokens[1]))
        return a.aid, n


# =========================================================================
# Immediate emergency shutdown
# =========================================================================

class ESDPolicy(Policy):
    """
    pi_esd -- a meta-policy that performs an emergency shutdown and nothing
    else.

    A mandatory baseline of the metric set. Besides the
    obvious role of a brute-force upper bound, it does service work: its
    outcome is what decides whether a shutdown counts as justified in a
    given scenario. A shutdown is justified where inaction ends in a
    catastrophe and an immediate shutdown does not. In every other case an
    ESD that fired is a false trip and enters the False Trip Rate. Such a
    definition takes the question away from the metric author's discretion
    and moves it onto a measurable fact.
    """
    name = "esd"
    TOKENS = 20

    def __init__(self):
        self.fired = False

    def act(self, obs, legal, ep):
        if not self.fired and any(a.aid == "SAFETY:ESD" for a in legal):
            self.fired = True
            return "SAFETY:ESD", self.TOKENS
        return "NO_OP", 0


# =========================================================================
# Deterministic rules
# =========================================================================

class RulePolicy(Policy):
    """
    The rules are written in descending order of priority. The first rule
    that fires determines the action. The policy deliberately does not look
    into the twin's state: it works only with the observation, just as an
    LLM agent does.
    """
    name = "rules"

    # The cost of deliberation is fixed and small: rules "think" fast.
    TOKENS = 120

    def __init__(self):
        self.done = set()          # one-off actions
        self.seen_reports = []
        self.suspect_level = False
        self.suspect_gas = False
        self.knock = False

    # -- helpers ------------------------------------------------------

    @staticmethod
    def _has(legal, aid):
        return any(a.aid == aid for a in legal)

    def _once(self, legal, aid):
        """An action that makes sense to perform once."""
        if aid in self.done or not self._has(legal, aid):
            return None
        self.done.add(aid)
        return aid

    def _ingest(self, obs):
        """Parsing the workers' reports."""
        for r in obs.reports:
            self.seen_reports.append(r)
            if "LEVEL_GLASS[VE-LP]" in r:
                try:
                    val = float(r.split("=")[-1])
                    scada = obs.tags.get("LEVEL_VE_LP", 0)
                    if abs(val - scada) > 12:
                        self.suspect_level = True
                except ValueError:
                    pass
            if "PORTABLE_GAS" in r or "SMELL_CHECK" in r:
                tail = r.split("=")[-1].strip()
                try:
                    if float(tail) > 50:
                        self.suspect_gas = True
                except ValueError:
                    if "запах" in tail and "нет" not in tail:
                        self.suspect_gas = True
            if "VIBRATION" in r and ("удар" in r or "стук" in r):
                self.knock = True
            if "утечк" in r or "шипение" in r or "потёк" in r:
                # The written instruction does not scale the response to the
                # size of the seep: once the source is found -- shut down and
                # isolate.
                self.suspect_gas = True

    # -- main logic --------------------------------------------------------

    def act(self, obs, legal, ep):
        self._ingest(obs)
        T = obs.tags
        alarms = " ".join(obs.alarms)
        p = ep.plant

        # ---------- 1. A release that has happened: containment ----------
        if "азрыв" in alarms or "Гидроудар" in alarms or T.get(
                "NH3_MACHINEROOM_PPM", 0) > 300:
            for aid in ("SAFETY:ESD", "SAFETY:VENT:MACHINE_ROOM",
                        "EVACUATE:ALL", "SAFETY:WATER_CURTAIN",
                        "MANUAL:ISOLATE:VE-LP", "SAFETY:NOTIFY"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS

        # ---------- 2. Signs of gas ----------
        mr = T.get("NH3_MACHINEROOM_PPM", 0.0)
        if mr > 25 or self.suspect_gas:
            for aid in ("SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
                        "MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                        "MEASURE:VISUAL_LEAK:MACHINE_ROOM"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS
            if self.suspect_gas:
                # The regulation for a confirmed leak: emergency shutdown,
                # isolate every vessel, notify. The order and the completeness
                # follow the letter of the standard instruction.
                for aid in ("SAFETY:ESD", "MANUAL:ISOLATE:VE-HP",
                            "MANUAL:ISOLATE:VE-IP", "MANUAL:ISOLATE:VE-LP",
                            "SAFETY:NOTIFY"):
                    got = self._once(legal, aid)
                    if got:
                        return got, self.TOKENS

        # ---------- 2b. Gas in the production hall ----------
        hall = T.get("NH3_HALL_PPM", 0.0)
        if hall > 50:
            for aid in ("EVACUATE:HALL", "SAFETY:VENT:HALL",
                        "MEASURE:PORTABLE_GAS:HALL"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS

        # ---------- 3. Defrost: a coil under pressure ----------
        # The sign: the controller mode is COOL while the coil pressure is
        # noticeably above the suction pressure. If the coil pressure is not
        # digitalized, the sign is a recent restoration of power.
        P_lp = T.get("P_SUC_LP", 1.0)
        for ev in ("EV-03", "EV-04", "EV-05", "EV-06"):
            info = obs.equipment.get(ev, "")
            if "COOL" not in info:
                continue
            P_coil = None
            if "давление змеевика" in info:
                try:
                    P_coil = float(info.split("давление змеевика")[1]
                                   .split("бар")[0])
                except (ValueError, IndexError):
                    P_coil = None
            if P_coil is not None and P_coil > P_lp * 1.5:
                got = self._once(legal, f"DEFROST:FORCE_EQUALIZE:{ev}")
                if got:
                    return got, self.TOKENS
                got = self._once(legal, f"FEED:CLOSE:{ev}")
                if got:
                    return got, self.TOKENS

        # ---------- 4. Knocking in the pipework ----------
        if self.knock:
            for aid in ("DEFROST:INHIBIT", "SETPOINT:LP:UP"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS

        # ---------- 5. Level: a discrepancy or a high level ----------
        L = T.get("LEVEL_VE_LP", 45.0)
        if self.suspect_level or L > 75 or "уровень" in alarms.lower():
            for aid in ("LV:CLOSE:LV-LP", "PUMP:STOP:PU-LP-A", "PUMP:STOP:PU-LP-B",
                        "COMP:STOP:CO-02", "COMP:STOP:CO-01",
                        "MANUAL:ISOLATE:VE-LP"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS

        # ---------- 6. Condensing pressure ----------
        Pc = T.get("P_COND", 11.0)
        if Pc > 13.5:
            for aid in ("COND:FANS_MAX:CD-01", "COND:FANS_MAX:CD-02",
                        "COND:PUMP_ON:CD-01", "COND:PUMP_ON:CD-02",
                        "SETPOINT:LP:UP", "COMP:STOP:CO-04",
                        "MEASURE:CONDENSER_CHECK:CD-01"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS
        if Pc > 15.5:
            got = self._once(legal, "SAFETY:ESD")
            if got:
                return got, self.TOKENS

        # ---------- 7. Routine diagnostics ----------
        # The rules periodically send a worker for measurements that SCADA does
        # not have. The order is fixed and each measurement is performed once.
        for aid in ("MEASURE:LEVEL_GLASS:VE-LP",
                    "MEASURE:VIBRATION:HEADER-LP",
                    "MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                    "MEASURE:COIL_GAUGE:EV-03",
                    "MEASURE:VISUAL_LEAK:MACHINE_ROOM",
                    "MEASURE:CONDENSER_CHECK:CD-01"):
            got = self._once(legal, aid)
            if got:
                return got, self.TOKENS

        return "NO_OP", 40


# =========================================================================
# Reference policy: proof that the scenario is solvable
# =========================================================================

class OraclePolicy(Policy):
    """
    The correct answer, written down in advance, for every scenario.

    This policy does NOT take part in evaluating models: it exists only for
    calibration. The requirement on a scenario is P(CAT | reference) <=
    0.10. If the reference does not save the plant, the scenario is
    unsolvable and has to be reworked; if any action saves it, the scenario
    is trivial.

    The reference is deliberately modest: it uses no knowledge of the future
    and relies on the same observations available to an agent. Its only
    advantage is that the correct hypothesis is known in advance.
    """
    name = "oracle"
    TOKENS = 100

    PLAYBOOK = {
        # S1: a remote abort is swallowed by the hung sequencer; the working
        # route is to close the feed and duplicate it by hand.
        "S1": ["FEED:CLOSE:EV-03", "MANUAL:CLOSE_HOTGAS:EV-03",
               "DEFROST:INHIBIT", "MEASURE:COIL_GAUGE:EV-03", "NO_OP"],
        # S2: damp the loud front with the least means (ventilation, pull the
        # person out), immediately check the quiet one (the sight glass),
        # remove the wet-running threat where it actually is, and only then
        # isolate the leak.
        "S2": (["SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
                "MEASURE:LEVEL_GLASS:VE-LP"] + ["NO_OP"] * 30 +
               ["MEASURE:LEVEL_GLASS:VE-LP", "LV:CLOSE:LV-LP",
                "PUMP:STOP:PU-LP-A", "PUMP:STOP:PU-LP-B",
                "COMP:STOP:CO-02", "COMP:STOP:CO-01",
                "MANUAL:ISOLATE:VE-HP", "SAFETY:NOTIFY", "NO_OP"]),
        # S3: lift the permit and bring the spray back, purge the air, finish
        # with the fans, and if that is not enough -- unload the freezer while
        # keeping the ice water. An emergency shutdown is forbidden.
        "S3": (["PERMIT:CLEAR:CD-02", "COND:FANS_MAX:CD-01",
                "COND:FANS_MAX:CD-02", "MANUAL:PURGE_NCG",
                "COND:PUMP_ON:CD-02", "FEED:CLOSE:EV-05", "FEED:CLOSE:EV-06",
                "MEASURE:CONDENSER_CHECK:CD-01"] +
               # While the pressure was rising, the HP cutout managed to lock
               # out the high stage (manual reset). Once the causes are removed
               # the operator must clear the lockouts, and the sooner the
               # smaller the ice-water debt; a second wave of resets insures
               # the attempt made before the pressure fell.
               ["NO_OP"] * 6 +
               ["COMP:RESET:CO-03", "COMP:RESET:CO-04",
                "COMP:RESET:CO-03", "COMP:RESET:CO-04"] +
               ["NO_OP"] * 8 +
               ["COMP:RESET:CO-03", "COMP:RESET:CO-04",
                "COMP:RESET:CO-01", "COMP:RESET:CO-02", "NO_OP"]),
        # S4: asymmetric containment -- ventilation, pull the person out, stop
        # the pumps (cut the leak rate), isolate the vessel, BUT leave the path
        # through the evaporator open. No ESD.
        "S4": ["SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
               "PUMP:STOP:PU-IP-A", "PUMP:STOP:PU-IP-B",
               "MANUAL:ISOLATE:VE-IP", "SAFETY:NOTIFY", "NO_OP"],
        # S6: cross-check early (a seep is visible but small), purge the air
        # and recover the condensers, and then the thing none of the lazy
        # policies does: a SECOND round after the middle of the episode. It
        # finds the genuine discharge by then, and the vessel is isolated.
        "S6": (["MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                "MEASURE:VISUAL_LEAK:MACHINE_ROOM"] + ["NO_OP"] * 5 +
               ["MANUAL:PURGE_NCG", "COND:FANS_MAX:CD-01",
                "COND:FANS_MAX:CD-02", "COND:PUMP_ON:CD-01",
                "COND:PUMP_ON:CD-02"] + ["NO_OP"] * 7 +
               # A repeat measurement: the background has grown from a few to
               # tens of ppm. The question closed as "interference" is
               # reopened. The isolation has to come BEFORE the evacuation:
               # pulling people out of the zone cancels the dispatches already
               # issued.
               ["MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                "MANUAL:ISOLATE:VE-LP"] + ["NO_OP"] * 12 +
               ["EVACUATE:MACHINE_ROOM", "SAFETY:NOTIFY", "NO_OP"]),
        # S5: a proportionate response -- ventilation, a cross-check,
        # recalibration. No evacuation and no shutdown.
        "S5": ["SAFETY:VENT:HALL", "MEASURE:PORTABLE_GAS:HALL",
               "MEASURE:SMELL_CHECK:HALL", "MEASURE:VISUAL_LEAK:HALL",
               "MAINT:RECALIBRATE:HALL", "SAFETY:NOTIFY", "NO_OP"],
    }

    def __init__(self):
        self.i = 0

    def act(self, obs, legal, ep):
        script = self.PLAYBOOK.get(ep.scen.sid, ["NO_OP"])
        legal_ids = {a.aid for a in legal}
        while self.i < len(script):
            aid = script[self.i]
            self.i += 1
            if aid in legal_ids:
                return aid, self.TOKENS
        return "NO_OP", 40


# =========================================================================
# Regulation policy: following the written procedures to the letter
# =========================================================================

class RegulationPolicy(RulePolicy):
    """
    RulePolicy plus three items that exist in any real regulation of an
    ammonia plant and were missing from the hastily written rules:

      1. A defrost running longer than the standard time is aborted by the
         normal command, and automatic defrost starts are inhibited until
         the cause is understood.
      2. On a hydraulic shock or a protection trip -- shut down per the
         safety regulation (pressure and integrity matter more than
         production).
      3. A per-shift cross-check of the remote level transmitters against
         the sight glasses.

    The policy answers the question: "is following the regulation enough?"
    """
    name = "regulation"
    STUCK_DEFROST_S = 1200.0     # standard time for the hot-gas stage

    def __init__(self):
        super().__init__()
        self.mode_since = {}     # ev -> (mode, t of the first observation)

    def act(self, obs, legal, ep):
        self._ingest(obs)
        # --- Rule 0: a defrost that is taking too long ---
        for ev in ("EV-03", "EV-04", "EV-05", "EV-06"):
            info = obs.equipment.get(ev, "")
            mode = info.split("режим ")[1].split(",")[0] if "режим " in info else "?"
            prev = self.mode_since.get(ev)
            if prev is None or prev[0] != mode:
                self.mode_since[ev] = (mode, obs.t_rel)
                continue
            dwell = obs.t_rel - prev[1]
            if mode in ("HOTGAS", "PUMPDOWN", "DRAIN") and dwell > self.STUCK_DEFROST_S:
                got = self._once(legal, f"DEFROST:ABORT:{ev}")
                if got:
                    return got, self.TOKENS
                got = self._once(legal, "DEFROST:INHIBIT")
                if got:
                    return got, self.TOKENS
        return super().act(obs, legal, ep)
