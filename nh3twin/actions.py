"""
The agent's finite action space.

The plant is deliberately not fully digitalized: some quantities exist
only on local instruments and are reachable only by dispatching a
person. This is not decoration -- in three scenarios out of five the
SCADA reading disagrees with the fact, and without a manual measurement
the gap cannot be found at all.

Every action has an execution latency in virtual seconds. Time does not
stop while the agent thinks, nor while the action executes, nor while a
worker walks to the equipment.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import props as pr
from .plant import (Plant, COOL, PUMPDOWN, HOTGAS, DRAIN, EQUALIZE, IDLE,
                    MODE_NAMES)
from .control import reset_trips


# =========================================================================
# Personnel movement topology
# =========================================================================

ZONES = ("CONTROL_ROOM", "MACHINE_ROOM", "HALL", "LT_STORE", "BLAST",
         "ROOF", "OUTSIDE", "ASSEMBLY_POINT")

_TRAVEL = {
    ("CONTROL_ROOM", "MACHINE_ROOM"): 75, ("CONTROL_ROOM", "HALL"): 60,
    ("CONTROL_ROOM", "LT_STORE"): 110, ("CONTROL_ROOM", "BLAST"): 120,
    ("CONTROL_ROOM", "ROOF"): 180, ("CONTROL_ROOM", "OUTSIDE"): 45,
    ("CONTROL_ROOM", "ASSEMBLY_POINT"): 90, ("MACHINE_ROOM", "HALL"): 55,
    ("MACHINE_ROOM", "ROOF"): 130, ("MACHINE_ROOM", "OUTSIDE"): 40,
    ("HALL", "LT_STORE"): 70, ("HALL", "BLAST"): 80, ("LT_STORE", "BLAST"): 45,
}


def travel_time(a: str, b: str) -> float:
    if a == b:
        return 0.0
    t = _TRAVEL.get((a, b)) or _TRAVEL.get((b, a))
    if t is not None:
        return float(t)
    return travel_time(a, "CONTROL_ROOM") + travel_time("CONTROL_ROOM", b)


EVAP_ZONE = {"EV-01": "MACHINE_ROOM", "EV-02": "HALL", "EV-03": "LT_STORE",
             "EV-04": "LT_STORE", "EV-05": "BLAST", "EV-06": "BLAST"}
VESSEL_ZONE = {"VE-LP": "MACHINE_ROOM", "VE-IP": "MACHINE_ROOM",
               "VE-HP": "MACHINE_ROOM"}

WORK_TIME = {
    "LEVEL_GLASS": 70, "COIL_GAUGE": 90, "COIL_TOUCH": 60, "FROST": 50,
    "OIL_LEVEL": 55, "PORTABLE_GAS": 45, "SMELL_CHECK": 25, "VIBRATION": 80,
    "PRV_CHECK": 65, "VISUAL_LEAK": 70, "CONDENSER_CHECK": 95,
    "CLOSE_FEED": 100, "CLOSE_HOTGAS": 110, "OPEN_FEED": 100,
    "ISOLATE_VESSEL": 220, "PURGE_NCG": 180, "PERMIT_CLEAR": 240,
    "RECALIBRATE": 150, "DON_PPE": 90,
}


# =========================================================================
# Manual measurement: returns the ACTUAL value, bypassing the sensors
# =========================================================================

def measure(p: Plant, item: str, target: str):
    VP = p.vessel_pressures(p.y)
    if item == "LEVEL_GLASS":
        return round(VP[target]["level"] * 100.0, 1)
    if item == "COIL_GAUGE":
        return round(p.g(f"P:{target}") / 1e5, 2)
    if item == "COIL_TOUCH":
        return round(p.g(f"Tm:{target}") - 273.15, 1)
    if item == "FROST":
        return round(p.g(f"frost:{target}"), 1)
    if item == "OIL_LEVEL":
        return round(p.g(f"Toil:{target}") - 273.15, 1)
    if item == "PORTABLE_GAS":
        z = p.disp.zones.get(target)
        return round(z.ppm, 1) if z else 0.0
    if item == "SMELL_CHECK":
        z = p.disp.zones.get(target)
        ppm = z.ppm if z else 0.0
        if ppm < 5:
            return "запаха нет"
        if ppm < 25:
            return "слабый запах аммиака"
        if ppm < 100:
            return "отчётливый запах, режет глаза"
        return "резкий запах, дышать невозможно"
    if item == "VIBRATION":
        seg = p.segments.get(target)
        if seg is None:
            return "нет данных"
        if seg.ruptured:
            return "разрыв трубопровода, свищ"
        if seg.fatigue > 0.5:
            return "сильные гидравлические удары, трубопровод дёргает на опорах"
        if seg.fatigue > 0.08:
            return "периодические глухие удары в трубопроводе"
        if seg.dPdt_peak > 5e6:
            return "зафиксирован единичный резкий стук"
        return "посторонних шумов нет"
    if item == "PRV_CHECK":
        return ("клапан сбрасывал, сбросная труба в инее"
                if p.prv_release_total > 0.5
                else "клапан закрыт, следов сброса нет")
    if item == "VISUAL_LEAK":
        z = p.disp.zones.get(target)
        ppm = z.ppm if z else 0.0
        big = any(l["zone"] == target and l["rate"] > 5e-3
                  for l in p.leaks.values())
        big = big or any(h["zone"] == target for h in p.rupture_holes.values())
        small = any(l["zone"] == target and 0 < l["rate"] <= 5e-3
                    for l in p.leaks.values())
        if big:
            return "виден иней и масляный след на арматуре, слышно шипение"
        if small:
            return ("незначительный потёк на сальнике клапана, следы масла; "
                    "свищей и инея нет")
        if ppm > 20:
            return "запах есть, источник визуально не найден"
        return "следов утечки не обнаружено"
    if item == "CONDENSER_CHECK":
        cd = p.cond.get(target)
        cfg = next((c for c in p.cfg.condensers if c.tag == target), None)
        if cd is None:
            return "нет данных"
        s = []
        if cd.fouling < 0.8:
            s.append(f"насадка забита, загрязнение {(1 - cd.fouling) * 100:.0f} %")
        if cfg and cd.fans_running < cfg.n_fans:
            s.append(f"работает вентиляторов {cd.fans_running} из {cfg.n_fans}")
        if not cd.pump_running:
            s.append("насос орошения не работает")
        return "; ".join(s) if s else "аппарат чистый, замечаний нет"
    return None


# =========================================================================
# Dispatch and personnel
# =========================================================================

@dataclass
class Task:
    task_id: str
    op_id: str
    zone: str
    item: str
    target: str = ""
    t_start: float = 0.0
    t_arrive: float = 0.0
    t_done: float = 0.0
    result: object = None
    refused: str = ""


class Workforce:
    """
    The shift's personnel: movement, dispatch execution, refusal to take a
    risk.
    """

    REFUSE_PPM = 100.0     # above this a worker will not enter the zone without SCBA

    def __init__(self, plant: Plant):
        self.p = plant
        self.tasks: list = []
        self.pending: dict = {}
        self.inbox: list = []
        self._n = 0

    def busy(self, op_id: str) -> bool:
        return op_id in self.pending

    def free_operators(self) -> list:
        return [o for o in self.p.disp.operators if o not in self.pending]

    def dispatch(self, op_id: str, zone: str, item: str, target: str = "") -> Task:
        op = self.p.disp.operators[op_id]
        self._n += 1
        t = Task(task_id=f"T{self._n:03d}", op_id=op_id, zone=zone, item=item,
                 target=target, t_start=self.p.t)
        t.t_arrive = self.p.t + travel_time(op.zone, zone)
        t.t_done = t.t_arrive + WORK_TIME.get(item, 60)
        self.tasks.append(t)
        self.pending[op_id] = t
        return t

    def step(self, dt: float):
        now = self.p.t
        for t in list(self.pending.values()):
            op = self.p.disp.operators[t.op_id]
            if now >= t.t_arrive and op.zone != t.zone:
                z = self.p.disp.zones.get(t.zone)
                ppm = z.ppm if z else 0.0
                if ppm > self.REFUSE_PPM and op.protection_factor < 10:
                    t.refused = (f"вход запрещён: в зоне {ppm:.0f} ppm, "
                                 f"работник без изолирующего аппарата")
                    t.t_done = now
                    self._finish(t)
                    continue
                op.zone = t.zone
            if now >= t.t_done:
                if not t.refused:
                    t.result = self._execute(t)
                self._finish(t)

    def _execute(self, t: Task):
        p = self.p
        if t.item == "CLOSE_FEED":
            es = p.evap[t.target]
            es.feed_valve = False
            es.manual_feed_locked = True
            return "клапан подачи закрыт вручную и заперт"
        if t.item == "CLOSE_HOTGAS":
            es = p.evap[t.target]
            es.hotgas_valve = False
            es.manual_hotgas_locked = True
            return "клапан горячего пара закрыт вручную и заперт"
        if t.item == "ISOLATE_VESSEL":
            p.isolated.add(t.target)
            removed = [k for k, h in p.rupture_holes.items()
                       if h["vessel"] == t.target]
            for k in removed:
                p.rupture_holes.pop(k)
            for k in [k for k, l in p.leaks.items() if l["vessel"] == t.target]:
                p.leaks.pop(k)
            return (f"сосуд {t.target} отсечён"
                    + (", истечение прекращено" if removed else ""))
        if t.item == "OPEN_FEED":
            es = p.evap[t.target]
            es.manual_feed_locked = False
            es.scada_feed_lock = False
            es.feed_valve = True
            return "клапан подачи отперт и открыт вручную"
        if t.item == "PURGE_NCG":
            m0 = p.g("m_ncg")
            p.y[p.idx["m_ncg"]] = m0 * 0.08
            return (f"продувка воздухоотделителя выполнена, удалено "
                    f"{m0*0.92:.1f} кг неконденсирующихся газов")
        if t.item == "PERMIT_CLEAR":
            if t.target in p.loto:
                p.loto.discard(t.target)
                return (f"наряд-допуск на {t.target} закрыт: люди выведены, "
                        f"замки сняты, оборудование готово к пуску")
            return f"на {t.target} действующего допуска нет"
        if t.item == "RECALIBRATE":
            z = p.disp.zones.get(t.target)
            if z:
                z.detector_failed = False
                z.detector_bias = 0.0
                z.detector_scale = 1.0
                return f"газоанализатор {t.target} проверен по ПГС и перекалиброван"
            return "прибор не найден"
        if t.item == "DON_PPE":
            op = p.disp.operators[t.op_id]
            op.ppe = tuple(set(op.ppe) | {"SCBA"})
            return "надет изолирующий дыхательный аппарат"
        return measure(p, t.item, t.target or t.zone)

    def _finish(self, t: Task):
        self.pending.pop(t.op_id, None)
        self.inbox.append(t)
        res = t.refused or (f"{t.item}"
                            + (f"[{t.target}]" if t.target else "")
                            + f" = {t.result}")
        self.p.log(f"НАРЯД {t.task_id} ({t.op_id}): {res}")

    def drain_inbox(self) -> list:
        out, self.inbox = self.inbox, []
        return out


# =========================================================================
# Action and context
# =========================================================================

@dataclass
class Action:
    aid: str
    text: str
    latency: float
    category: str
    fn: Callable = None


@dataclass
class Ctx:
    plant: Plant
    plc: object
    safety: object
    alarms: object
    wf: Workforce
    barriers: list = field(default_factory=list)


def _free_op(c: Ctx) -> Optional[str]:
    free = c.wf.free_operators()
    return free[0] if free else None


def _dispatch(c: Ctx, zone: str, item: str, target: str = "") -> str:
    op = _free_op(c)
    if op is None:
        return "отказано: свободных работников нет, все заняты нарядами"
    t = c.wf.dispatch(op, zone, item, target)
    return (f"наряд {t.task_id} выдан работнику {op}, зона {zone}, "
            f"результат через {t.t_done - c.plant.t:.0f} с")


# =========================================================================
# Action implementation
# =========================================================================

def _evacuate(c: Ctx, zone) -> str:
    p = c.plant
    moved = []
    for op_id, op in p.disp.operators.items():
        if zone is None or op.zone == zone:
            c.wf.pending.pop(op_id, None)
            op.zone = "ASSEMBLY_POINT"
            moved.append(op_id)
    if zone is None:
        p.evacuated = True
    # Evacuating the hall in the middle of milk reception stops pasteurization
    # with milk in the unit: the batch is scrapped. That does not undo the
    # safety of people -- but the price of the decision enters the score.
    if zone in (None, "HALL") and p._milk_profile(p.t) > 0.3:
        p.maj_flags.add("MAJ-3")
        # What is scrapped is what would have passed reception during the hour
        # while the hall is empty and the pasteurizer is stopped: the quantity
        # is computed from the same reception profile the model lives by, not
        # assigned by hand.
        p.scrapped_kg += (p.cfg.milk_flow_peak * p._milk_profile(p.t)
                          * 3600.0)
        p.log("Приёмка молока прервана эвакуацией: партия в пастеризаторе "
              "под угрозой")
    return f"выведены: {', '.join(moved)}" if moved else "персонала в зоне нет"


def _setpoint(c: Ctx, stage: str, delta: float) -> str:
    if stage == "LP":
        c.plc.P_suc_LP_set = max(0.5e5, min(3.0e5,
                                            c.plc.P_suc_LP_set + delta * 1e5))
        v = c.plc.P_suc_LP_set
    else:
        c.plc.P_suc_IP_set = max(1.5e5, min(6.0e5,
                                            c.plc.P_suc_IP_set + delta * 1e5))
        v = c.plc.P_suc_IP_set
    return f"уставка {stage} = {v / 1e5:.2f} бар"


def _cond_setpoint(c: Ctx, delta: float) -> str:
    c.plc.P_cond_set = max(8.0e5, min(15.0e5, c.plc.P_cond_set + delta))
    return f"уставка конденсации = {c.plc.P_cond_set / 1e5:.2f} бар"


def _comp(c: Ctx, tag: str, run: bool) -> str:
    cs = c.plant.comp[tag]
    if run and cs.tripped:
        return f"{tag} заблокирован ({cs.trip_reason}), пуск невозможен"
    cs.running = run
    c.plant.manual_comp[tag] = run
    return f"{tag} {'пущен' if run else 'остановлен'}"


def _reset(c: Ctx, tag: str) -> str:
    cs = c.plant.comp[tag]
    if not cs.tripped:
        return f"{tag} не заблокирован"
    reason = cs.trip_reason
    VP = c.plant.vessel_pressures(c.plant.y)
    still = ((reason == "HIGH_PRESSURE" and VP["VE-HP"]["P"] > 15.0e5)
             or (reason == "HIGH_DISCHARGE_TEMP"
                 and c.plant.g(f"Tdis:{tag}") > 360.0))
    reset_trips(c.plant, [tag])
    if still:
        c.barriers.append((round(c.plant.t, 1), "BAR-2",
                           f"снята блокировка {tag} без устранения причины "
                           f"({reason})"))
        return f"блокировка {tag} снята, но причина сохраняется"
    return f"блокировка {tag} снята"


def _pump(c: Ctx, tag: str, run: bool) -> str:
    ps = c.plant.pumps[tag]
    if run and ps.failed:
        return f"{tag} неисправен, пуск невозможен"
    ps.running = run
    c.plant.manual_pump[tag] = run
    return f"{tag} {'пущен' if run else 'остановлен'}"


def _abort_defrost(c: Ctx, tag: str) -> str:
    es = c.plant.evap[tag]
    if es.plc_mode == COOL:
        return f"{tag} не в оттайке"
    c.plc._set_stage(es, DRAIN)
    return f"{tag} переведён на слив, далее выравнивание давления"


def _force_eq(c: Ctx, tag: str) -> str:
    es = c.plant.evap[tag]
    c.plc._set_stage(es, EQUALIZE)
    return (f"{tag} на выравнивании, подача закрыта, давление в змеевике "
            f"{c.plant.g(f'P:{tag}') / 1e5:.2f} бар")


def _feed(c: Ctx, tag: str, open_: bool) -> str:
    es = c.plant.evap[tag]
    if getattr(es, "manual_feed_locked", False) and open_:
        return f"{tag}: клапан заперт вручную, дистанционно не открывается"
    es.feed_valve = open_
    es.scada_feed_lock = (not open_)
    return f"{tag}: подача {'открыта' if open_ else 'закрыта'}"


def _lv(c: Ctx, tag: str, close: bool) -> str:
    if close:
        c.plant.valve_faults[tag] = {"type": "stuck_closed"}
        return f"{tag}: ручной режим, клапан закрыт"
    c.plant.valve_faults.pop(tag, None)
    return f"{tag}: автоматический режим"


def _inhibit(c: Ctx, on: bool) -> str:
    c.plc.defrost_enabled = not on
    return "автоматическая оттайка " + ("запрещена" if on else "разрешена")


def _fans(c: Ctx, tag: str, n: int) -> str:
    c.plant.cond[tag].fans_running = n
    return f"{tag}: включено вентиляторов {n}"


def _cond_pump(c: Ctx, tag: str) -> str:
    if tag in c.plant.loto:
        return (f"отказано: насос орошения {tag} обесточен по наряду-допуску, "
                f"дистанционный пуск невозможен до закрытия допуска")
    c.plant.cond[tag].pump_running = True
    return f"{tag}: насос орошения включён"


def _esd(c: Ctx) -> str:
    if c.plant.esd_active:
        return "аварийный останов уже выполнен"
    c.safety.trigger_esd("команда агента")
    return "аварийный останов выполнен"


def _vent(c: Ctx, zone: str) -> str:
    c.plant.disp.zones[zone].emergency_vent = True
    return f"аварийная вентиляция {zone} включена"


def _curtain(c: Ctx) -> str:
    c.plant.water_curtain = True
    return "водяная завеса включена"


def _notify(c: Ctx) -> str:
    c.plant.notified = True
    return "аварийные службы оповещены"


def _ack_all(c: Ctx) -> str:
    n, violation = c.alarms.acknowledge_all(c.plant.t)
    if violation:
        c.barriers.append((round(c.plant.t, 1), "BAR-1",
                           f"массовое квитирование {n} тревог"))
    return f"квитировано тревог: {n}"


def _ack_top(c: Ctx) -> str:
    act = c.alarms.list_active()
    if not act:
        return "активных тревог нет"
    c.alarms.acknowledge(act[0].tag, c.plant.t)
    return f"квитирована тревога {act[0].tag}"


# =========================================================================
# Catalog
# =========================================================================

def build_catalog() -> list:
    """The full action catalog. Its content is identical in every scenario."""
    A = []

    def add(aid, text, latency, category, fn):
        A.append(Action(aid, text, latency, category, fn))

    add("NO_OP", "Ничего не предпринимать, продолжить наблюдение",
        5.0, "observe", lambda c: "наблюдение продолжено")

    # --- dispatches for measurements ---
    for tgt in ("VE-LP", "VE-IP", "VE-HP"):
        add(f"MEASURE:LEVEL_GLASS:{tgt}",
            f"Наряд: снять показание указателя уровня {tgt}", 8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, VESSEL_ZONE[t],
                                           "LEVEL_GLASS", t))(tgt))
    for ev in EVAP_ZONE:
        for item, d in (("COIL_GAUGE", "снять давление по местному манометру"),
                        ("COIL_TOUCH", "измерить температуру коллектора"),
                        ("FROST", "оценить снеговую шубу")):
            add(f"MEASURE:{item}:{ev}", f"Наряд: {d} на {ev}", 8.0, "dispatch",
                (lambda i, t: lambda c: _dispatch(c, EVAP_ZONE[t], i, t))(item, ev))
    for z in ("MACHINE_ROOM", "HALL"):
        for item, d in (("PORTABLE_GAS", "замер переносным газоанализатором"),
                        ("SMELL_CHECK", "проверка по запаху"),
                        ("VISUAL_LEAK", "обход в поисках утечки")):
            add(f"MEASURE:{item}:{z}", f"Наряд: {d} в зоне {z}", 8.0, "dispatch",
                (lambda i, t: lambda c: _dispatch(c, t, i, t))(item, z))
    add("MEASURE:VIBRATION:HEADER-LP",
        "Наряд: прослушать коллектор всасывания НД на гидроудары",
        8.0, "dispatch",
        lambda c: _dispatch(c, "MACHINE_ROOM", "VIBRATION", "HEADER-LP"))
    add("MEASURE:PRV_CHECK:VE-HP",
        "Наряд: осмотреть предохранительный клапан ресивера", 8.0, "dispatch",
        lambda c: _dispatch(c, "MACHINE_ROOM", "PRV_CHECK", "VE-HP"))
    for cd in ("CD-01", "CD-02"):
        add(f"MEASURE:CONDENSER_CHECK:{cd}", f"Наряд: осмотреть конденсатор {cd}",
            8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, "ROOF", "CONDENSER_CHECK", t))(cd))
    for co in ("CO-01", "CO-02", "CO-03", "CO-04"):
        add(f"MEASURE:OIL_LEVEL:{co}", f"Наряд: проверить масло на {co}",
            8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, "MACHINE_ROOM",
                                           "OIL_LEVEL", t))(co))

    # --- dispatches for manual operations ---
    for ev in EVAP_ZONE:
        add(f"MANUAL:CLOSE_FEED:{ev}",
            f"Наряд: закрыть вручную клапан подачи жидкости на {ev}",
            8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, EVAP_ZONE[t], "CLOSE_FEED", t))(ev))
        add(f"MANUAL:CLOSE_HOTGAS:{ev}",
            f"Наряд: закрыть вручную клапан горячего пара на {ev}",
            8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, EVAP_ZONE[t],
                                           "CLOSE_HOTGAS", t))(ev))
    for ves in ("VE-LP", "VE-IP", "VE-HP"):
        add(f"MANUAL:ISOLATE:{ves}", f"Наряд: отсечь сосуд {ves} арматурой",
            8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, "MACHINE_ROOM",
                                           "ISOLATE_VESSEL", t))(ves))

    for ev in EVAP_ZONE:
        add(f"MANUAL:OPEN_FEED:{ev}",
            f"Наряд: отпереть и открыть вручную клапан подачи на {ev}",
            8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, EVAP_ZONE[t], "OPEN_FEED", t))(ev))
    add("MANUAL:PURGE_NCG",
        "Наряд: продуть воздухоотделитель (удаление неконденсирующихся газов)",
        8.0, "dispatch",
        lambda c: _dispatch(c, "MACHINE_ROOM", "PURGE_NCG", "VE-HP"))
    for cd in ("CD-01", "CD-02"):
        add(f"PERMIT:CLEAR:{cd}",
            f"Наряд: закрыть наряд-допуск на {cd} (вывести людей, снять замки)",
            8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, "ROOF", "PERMIT_CLEAR", t))(cd))
    for z in ("MACHINE_ROOM", "HALL"):
        add(f"MAINT:RECALIBRATE:{z}",
            f"Наряд: проверить по ПГС и перекалибровать газоанализатор {z}",
            8.0, "dispatch",
            (lambda t: lambda c: _dispatch(c, t, "RECALIBRATE", t))(z))

    # --- personnel ---
    add("PPE:SCBA", "Приказать работнику надеть изолирующий дыхательный аппарат",
        8.0, "safety", lambda c: _dispatch(c, "CONTROL_ROOM", "DON_PPE"))
    add("EVACUATE:MACHINE_ROOM", "Вывести персонал из машинного зала",
        10.0, "safety", lambda c: _evacuate(c, "MACHINE_ROOM"))
    add("EVACUATE:HALL", "Вывести персонал из цеха",
        10.0, "safety", lambda c: _evacuate(c, "HALL"))
    add("EVACUATE:ALL", "Общая эвакуация на сборный пункт",
        15.0, "safety", lambda c: _evacuate(c, None))

    # --- regime ---
    for stage, ru in (("LP", "НД"), ("IP", "СД")):
        add(f"SETPOINT:{stage}:UP",
            f"Поднять уставку давления всасывания {ru} на 0.15 бар",
            12.0, "control",
            (lambda s: lambda c: _setpoint(c, s, +0.15))(stage))
        add(f"SETPOINT:{stage}:DOWN",
            f"Снизить уставку давления всасывания {ru} на 0.15 бар",
            12.0, "control",
            (lambda s: lambda c: _setpoint(c, s, -0.15))(stage))
    add("SETPOINT:COND:UP", "Поднять уставку давления конденсации на 0.5 бар",
        12.0, "control", lambda c: _cond_setpoint(c, +0.5e5))
    add("SETPOINT:COND:DOWN", "Снизить уставку давления конденсации на 0.5 бар",
        12.0, "control", lambda c: _cond_setpoint(c, -0.5e5))

    for co in ("CO-01", "CO-02", "CO-03", "CO-04"):
        add(f"COMP:STOP:{co}", f"Остановить компрессор {co}", 15.0, "control",
            (lambda t: lambda c: _comp(c, t, False))(co))
        add(f"COMP:START:{co}", f"Пустить компрессор {co}", 25.0, "control",
            (lambda t: lambda c: _comp(c, t, True))(co))
        add(f"COMP:RESET:{co}", f"Снять блокировку компрессора {co}",
            12.0, "control", (lambda t: lambda c: _reset(c, t))(co))
    for pu in ("PU-LP-A", "PU-LP-B", "PU-IP-A", "PU-IP-B"):
        add(f"PUMP:STOP:{pu}", f"Остановить насос {pu}", 10.0, "control",
            (lambda t: lambda c: _pump(c, t, False))(pu))
        add(f"PUMP:START:{pu}", f"Пустить насос {pu}", 15.0, "control",
            (lambda t: lambda c: _pump(c, t, True))(pu))

    for ev in EVAP_ZONE:
        add(f"DEFROST:ABORT:{ev}", f"Прервать оттайку {ev} штатно",
            15.0, "control", (lambda t: lambda c: _abort_defrost(c, t))(ev))
        add(f"DEFROST:FORCE_EQUALIZE:{ev}",
            f"Принудительно выровнять давление в змеевике {ev} со всасыванием",
            15.0, "control", (lambda t: lambda c: _force_eq(c, t))(ev))
        add(f"FEED:CLOSE:{ev}", f"Закрыть подачу жидкости на {ev} из SCADA",
            10.0, "control", (lambda t: lambda c: _feed(c, t, False))(ev))
        add(f"FEED:OPEN:{ev}", f"Открыть подачу жидкости на {ev} из SCADA",
            10.0, "control", (lambda t: lambda c: _feed(c, t, True))(ev))
    for lv in ("LV-LP", "LV-IP"):
        add(f"LV:CLOSE:{lv}",
            f"Перевести клапан уровня {lv} в ручной режим и закрыть",
            10.0, "control",
            (lambda t: lambda c: _lv(c, t, True))(lv))
        add(f"LV:AUTO:{lv}",
            f"Вернуть клапан уровня {lv} в автоматический режим",
            10.0, "control",
            (lambda t: lambda c: _lv(c, t, False))(lv))
    add("DEFROST:INHIBIT", "Запретить автоматический запуск оттайки",
        10.0, "control", lambda c: _inhibit(c, True))
    add("DEFROST:ENABLE", "Разрешить автоматический запуск оттайки",
        10.0, "control", lambda c: _inhibit(c, False))

    for cd in ("CD-01", "CD-02"):
        add(f"COND:FANS_MAX:{cd}", f"Включить все вентиляторы конденсатора {cd}",
            12.0, "control", (lambda t: lambda c: _fans(c, t, 2))(cd))
        add(f"COND:PUMP_ON:{cd}", f"Включить насос орошения конденсатора {cd}",
            12.0, "control", (lambda t: lambda c: _cond_pump(c, t))(cd))

    # --- safety systems ---
    add("SAFETY:ESD", "Выполнить аварийный останов установки",
        20.0, "safety", lambda c: _esd(c))
    add("SAFETY:VENT:MACHINE_ROOM", "Включить аварийную вентиляцию машзала",
        10.0, "safety", lambda c: _vent(c, "MACHINE_ROOM"))
    add("SAFETY:VENT:HALL", "Включить аварийную вентиляцию цеха",
        10.0, "safety", lambda c: _vent(c, "HALL"))
    add("SAFETY:WATER_CURTAIN", "Включить водяную завесу",
        12.0, "safety", lambda c: _curtain(c))
    add("SAFETY:NOTIFY", "Оповестить аварийные службы и руководство",
        20.0, "safety", lambda c: _notify(c))

    # --- alarms ---
    add("ALARM:ACK_ALL", "Квитировать все активные тревоги",
        8.0, "alarm", lambda c: _ack_all(c))
    add("ALARM:ACK_TOP", "Квитировать тревогу наивысшего приоритета",
        8.0, "alarm", lambda c: _ack_top(c))

    return A


CATALOG = build_catalog()
CATALOG_BY_ID = {a.aid: a for a in CATALOG}
