"""
Episode: the "observe -> decide -> act" loop in pseudo-real time.

The key property is that time does not stop while the agent thinks. The
virtual time of a step is made of three parts:

    dt = deliberation (tokens / R) + action execution + polling tick

where R is the deliberation rate in tokens per virtual second. At
R = 40, reasoning of 4000 tokens costs 100 virtual seconds, and the
plant travels far in that time. This carries a known result onto model
ground: under real-time evaluation, excessive deliberation turns from an
advantage into a burden.

The agent sees NOT the state of the plant but the instrument readings --
with faults, lags and gaps. The gap between a reading and the fact is
closed only by dispatching a person for a manual measurement.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import time

from . import props as pr
from .plant import Plant, MODE_NAMES
from .control import PLC, AlarmSystem, SafetySystem
from .faults import FaultManager
from .dispersion import Operator
from .actions import CATALOG, CATALOG_BY_ID, Workforce, Ctx


# Deliberation rate, tokens per virtual second.
THINK_RATE = 40.0
# Polling tick: the minimum interval between decisions, s.
POLL_PERIOD = 10.0


# =========================================================================
# Observation
# =========================================================================

# The tags the agent sees. Deliberately not all of them: some quantities on the
# plant are simply not digitalized.
VISIBLE_TAGS = [
    "P_SUC_LP", "P_SUC_IP", "P_COND", "T_EVAP_LP", "T_EVAP_IP", "T_COND",
    "LEVEL_VE_LP", "LEVEL_VE_IP", "LEVEL_VE_HP",
    "T_MILK", "T_ICEWATER", "M_ICE_T",
    "T_ROOM_CHILL", "T_ROOM_LT", "T_ROOM_BLAST",
    "POWER_KW", "Q_REJ_KW",
    "NH3_MACHINEROOM_PPM", "NH3_HALL_PPM", "ESD",
]
UNITS = {
    "P_SUC_LP": "бар", "P_SUC_IP": "бар", "P_COND": "бар",
    "T_EVAP_LP": "°C", "T_EVAP_IP": "°C", "T_COND": "°C",
    "LEVEL_VE_LP": "%", "LEVEL_VE_IP": "%", "LEVEL_VE_HP": "%",
    "T_MILK": "°C", "T_ICEWATER": "°C", "M_ICE_T": "т",
    "T_ROOM_CHILL": "°C", "T_ROOM_LT": "°C", "T_ROOM_BLAST": "°C",
    "POWER_KW": "кВт", "Q_REJ_KW": "кВт",
    "NH3_MACHINEROOM_PPM": "ppm", "NH3_HALL_PPM": "ppm", "ESD": "",
}


@dataclass
class Observation:
    t_rel: float                       # s since the start of the episode
    tags: dict
    equipment: dict
    alarms: list
    reports: list                      # reports on completed dispatches
    operators: dict
    pending_tasks: list
    note: str = ""

    def render(self) -> str:
        """Text rendering for an LLM agent."""
        L = [f"[t = {self.t_rel:.0f} с]"]
        L.append("ПРИБОРЫ:")
        L.append("  " + "; ".join(
            f"{k} {self.tags[k]:.2f} {UNITS.get(k, '')}".strip()
            for k in VISIBLE_TAGS if k in self.tags))
        L.append("ОБОРУДОВАНИЕ:")
        for k, v in self.equipment.items():
            L.append(f"  {k}: {v}")
        L.append("ТРЕВОГИ: " + ("нет" if not self.alarms
                                else "; ".join(self.alarms)))
        if self.pending_tasks:
            L.append("НАРЯДЫ В РАБОТЕ: " + "; ".join(self.pending_tasks))
        if self.reports:
            L.append("ОТЧЁТЫ РАБОТНИКОВ:")
            for r in self.reports:
                L.append(f"  {r}")
        L.append("ПЕРСОНАЛ: " + "; ".join(
            f"{k} в зоне {v['zone']}, доза {v['dose']:.0f} ppm·мин"
            + (", СИЗ" if v["ppe"] else "")
            for k, v in self.operators.items()))
        if self.note:
            L.append("ПРИМЕЧАНИЕ: " + self.note)
        return "\n".join(L)


# Panel instruments whose reading can disagree with the fact when a sensor
# fails. The key is the observation tag, the value is (vessel, instrument
# kind).
_INSTRUMENTS = {
    "LEVEL_VE_LP": ("VE-LP", "level"), "LEVEL_VE_IP": ("VE-IP", "level"),
    "LEVEL_VE_HP": ("VE-HP", "level"),
    "P_SUC_LP": ("VE-LP", "pressure"), "P_SUC_IP": ("VE-IP", "pressure"),
    "P_COND": ("VE-HP", "pressure"),
}
# Evaporating temperatures on the panel are read off the suction gauge, so when
# the gauge lies they lie with it. The condensing thermometer (T_COND) is a
# separate instrument and stays truthful: S3 is built on that discrepancy.
_EVAP_T_FROM_P = {"T_EVAP_LP": "P_SUC_LP", "T_EVAP_IP": "P_SUC_IP"}


def indicated_tags(p: Plant, tg: dict) -> dict:
    """
    Panel instrument readings derived from the plant's true tags.

    The panel shows READINGS, not the state: when a level or pressure sensor
    fails, the disagreement with the fact is seen only by whoever sends a
    person for a manual measurement. Without a fault indicated_* returns the
    fact, so in normal operation this is the identity. plant.tags()
    deliberately stays the truth -- the physical metrics and the episode
    trace are computed on it.

    The function is used both by the benchmark (build_observation) and by
    the trainer (driver._sample): the instrument history in the trainer must
    lie exactly as the panel does, or the expert is playing a different game
    than the models.
    """
    out = dict(tg)
    for tag, (vessel, kind) in _INSTRUMENTS.items():
        if tag not in out:
            continue
        if kind == "level":
            out[tag] = p.indicated_level(vessel, out[tag] / 100.0) * 100.0
        else:
            out[tag] = p.indicated_pressure(vessel, out[tag] * 1e5) / 1e5
    for t_tag, p_tag in _EVAP_T_FROM_P.items():
        if t_tag in out and p.sensor_faults.get(
                f"PRESSURE_{_INSTRUMENTS[p_tag][0]}"):
            out[t_tag] = float(pr.Tsat(out[p_tag] * 1e5)) - 273.15
    return out


def build_observation(ep: "Episode") -> Observation:
    p = ep.plant
    tg = indicated_tags(p, p.tags())
    tags = {k: tg[k] for k in VISIBLE_TAGS if k in tg}

    eq = {}
    for co in ("CO-01", "CO-02", "CO-03", "CO-04"):
        cs = p.comp[co]
        st = ("работает" if cs.running and not cs.tripped and not cs.lp_cutout
              else "БЛОКИРОВКА: " + cs.trip_reason if cs.tripped
              else "останов по реле НД" if cs.lp_cutout else "остановлен")
        eq[co] = (f"{st}, золотник {tg[co + '_SLIDE']:.0f} %, "
                  f"нагнетание {tg[co + '_TDIS']:.0f} °C")
    for ev in ("EV-01", "EV-02", "EV-03", "EV-04", "EV-05", "EV-06"):
        es = p.evap[ev]
        # The agent sees THE MODE AS THE CONTROLLER REPORTS IT, not the
        # physical state.
        eq[ev] = (f"режим {MODE_NAMES[es.plc_mode]}, "
                  f"подача {'открыта' if es.feed_valve else 'закрыта'}")
        if ep.coil_pressure_visible:
            eq[ev] += f", давление змеевика {tg[ev + '_P']:.2f} бар"
    for pu, ps in p.pumps.items():
        eq[pu] = ("работает" if ps.running and not ps.failed
                  else "неисправен" if ps.failed else "остановлен")
    for cd, st in p.cond.items():
        eq[cd] = f"вентиляторов {st.fans_running}/2, орошение " + \
                 ("вкл" if st.pump_running else "выкл")

    alarms = [f"[{a.priority}] {a.text}" for a in ep.alarms.list_active()]
    reports = []
    for t in ep.wf.drain_inbox():
        if t.refused:
            reports.append(f"{t.task_id} {t.op_id}: НАРЯД НЕ ВЫПОЛНЕН — {t.refused}")
        else:
            reports.append(f"{t.task_id} {t.op_id}: {t.item}"
                           + (f"[{t.target}]" if t.target else "")
                           + f" = {t.result}")
    pend = [f"{t.task_id} {t.op_id} {t.item} (ещё {max(t.t_done - p.t, 0):.0f} с)"
            for t in ep.wf.pending.values()]
    ops = {k: {"zone": o.zone, "dose": o.dose_ppm_min, "ppe": bool(o.ppe)}
           for k, o in p.disp.operators.items()}
    return Observation(t_rel=p.t - ep.t0, tags=tags, equipment=eq,
                       alarms=alarms, reports=reports, operators=ops,
                       pending_tasks=pend, note=ep.note)


# =========================================================================
# Episode
# =========================================================================

@dataclass
class StepRecord:
    t: float
    action: str
    result: str
    think_tokens: int
    dt_virtual: float


class Episode:

    def __init__(self, scenario, seed: int = 0, dt: float = 0.5,
                 think_rate: float = THINK_RATE):
        self.scen = scenario
        self.seed = seed
        self.dt = dt
        self.think_rate = think_rate
        self.note = scenario.brief
        self.coil_pressure_visible = scenario.coil_pressure_visible

        self.plant = Plant(seed=seed)
        self.alarms = AlarmSystem()
        self.plc = PLC(self.plant, self.alarms)
        self.safety = SafetySystem(self.plant, self.alarms)
        self.fm = FaultManager()
        self.wf = Workforce(self.plant)
        self.barriers = []

        scenario.setup(self)

        self.t0 = self.plant.t
        self.horizon = scenario.horizon_s
        self.ctx = Ctx(self.plant, self.plc, self.safety, self.alarms,
                       self.wf, self.barriers)
        self.log: list = []
        self.trace: list = []

    # -- advancing time ---------------------------------------------------

    def advance(self, seconds: float):
        n = max(int(round(seconds / self.dt)), 1)
        for _ in range(n):
            self.fm.step(self.plant)
            self.plc.step(self.dt)
            self.safety.step()
            self.plant.step(self.dt)
            self.wf.step(self.dt)
            self.trace.append((round(self.plant.t - self.t0, 1),
                               self.plant.tags()))
            if self.done():
                return

    def done(self) -> bool:
        return (self.plant.t - self.t0 >= self.horizon
                or bool(self.plant.cat_flags))

    def legal_actions(self) -> list:
        """
        The catalog is fixed; only actions that are certainly unexecutable are
        filtered out.
        """
        p = self.plant
        out = []
        for a in CATALOG:
            if a.aid.startswith("COMP:START:"):
                tag = a.aid.split(":")[2]
                if p.comp[tag].running or p.comp[tag].tripped:
                    continue
            if a.aid.startswith("COMP:STOP:"):
                if not p.comp[a.aid.split(":")[2]].running:
                    continue
            if a.aid.startswith("COMP:RESET:"):
                if not p.comp[a.aid.split(":")[2]].tripped:
                    continue
            if a.aid.startswith("PUMP:START:"):
                if p.pumps[a.aid.split(":")[2]].running:
                    continue
            if a.aid.startswith("PUMP:STOP:"):
                if not p.pumps[a.aid.split(":")[2]].running:
                    continue
            if a.aid == "SAFETY:ESD" and p.esd_active:
                continue
            out.append(a)
        return out

    # -- main loop --------------------------------------------------------

    def run(self, policy) -> dict:
        wall0 = time.time()
        # A short run-up before the first decision
        self.advance(POLL_PERIOD)
        while not self.done():
            obs = build_observation(self)
            legal = self.legal_actions()
            aid, tokens = policy.act(obs, legal, self)
            act = CATALOG_BY_ID.get(aid)
            if act is None:
                aid, act, tokens = "NO_OP", CATALOG_BY_ID["NO_OP"], tokens

            # Thinking time -- the real part of a step
            t_think = tokens / self.think_rate
            self.advance(t_think)
            if self.done():
                self.log.append(StepRecord(self.plant.t - self.t0, aid,
                                           "не исполнено: эпизод завершён",
                                           tokens, t_think))
                break

            result = act.fn(self.ctx)
            self.advance(act.latency)
            self.log.append(StepRecord(self.plant.t - self.t0, aid, result,
                                       tokens, t_think + act.latency))
            if self.done():
                break
            self.advance(POLL_PERIOD)

        return self.result(time.time() - wall0)

    # -- result -----------------------------------------------------------

    def result(self, wall: float) -> dict:
        p = self.plant
        s = p.summary()
        acts = [r.action for r in self.log]
        out = {
            "scenario": self.scen.sid,
            "seed": self.seed,
            "policy": getattr(self, "_policy_name", ""),
            "t_end_s": round(p.t - self.t0, 1),
            "horizon_s": self.horizon,
            "CAT": sorted(p.cat_flags),
            "MAJ": sorted(p.maj_flags),
            "prevented": not bool(p.cat_flags),
            "released_kg": round(p.disp.m_released_total, 1),
            "esd": bool(p.esd_active),
            "esd_reason": getattr(p, "esd_reason", ""),
            "barriers": list(self.barriers) + list(self.safety.bar_violations),
            "n_steps": len(self.log),
            "n_noop": sum(1 for a in acts if a == "NO_OP"),
            "n_dispatch": sum(1 for a in acts if a.startswith(("MEASURE", "MANUAL"))),
            "tokens": sum(r.think_tokens for r in self.log),
            "operators": s["operators"],
            "wall_s": round(wall, 2),
            "actions": acts,
            # Below are the quantities summary() always computed and result()
            # silently lost. Without them neither the cost of prevention, nor
            # the energy, nor the integrity of the product can be computed.
            "energy_kwh": s["energy_kwh"],
            "prv_kg": s["prv_kg"],
            "fenceline_peak_ppm": s["fenceline_peak_ppm"],
            "ruptured": s["ruptured"],
            "shock_events": s["shock_events"],
            "scrapped_kg": round(p.scrapped_kg, 1),
            # Tokens per decision: a sum is not enough for the median and p95.
            "tokens_per_step": [r.think_tokens for r in self.log],
            "t_per_step": [round(r.t, 1) for r in self.log],
        }
        from .metrics import trace_metrics
        out.update(trace_metrics(self))
        return out
