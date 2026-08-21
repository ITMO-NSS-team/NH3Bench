"""
Библиотека инжекции отказов.

Отказ -- это не «шум в данных», а физическое событие, запускающее конкретную
аварийную траекторию. Каждый отказ имеет момент активации, параметры и,
опционально, профиль нарастания.

Принцип accident-forcing: набор отказов сценария подбирается так, чтобы при
бездействии авария наступала с вероятностью не ниже 0.9. Проверяется
калибровкой тремя эталонными политиками (см. calibrate.py).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math

from . import props as pr
from .plant import Plant, COOL, PUMPDOWN, HOTGAS, DRAIN, EQUALIZE, IDLE


@dataclass
class Fault:
    """Базовый отказ."""
    fid: str
    t_start: float                 # с от начала прогона
    duration: Optional[float] = None
    ramp: float = 0.0              # с, время нарастания до полной интенсивности
    applied: bool = False
    ended: bool = False

    def active(self, t: float) -> bool:
        if t < self.t_start:
            return False
        if self.duration is not None and t > self.t_start + self.duration:
            return False
        return True

    def intensity(self, t: float) -> float:
        if not self.active(t):
            return 0.0
        if self.ramp <= 0:
            return 1.0
        return min((t - self.t_start) / self.ramp, 1.0)

    def apply(self, p: Plant):
        raise NotImplementedError

    def revert(self, p: Plant):
        pass


# =========================================================================
# F-LEAK: утечка аммиака
# =========================================================================

@dataclass
class LeakFault(Fault):
    vessel: str = "VE-LP"
    zone: str = "MACHINE_ROOM"     # MACHINE_ROOM | HALL | OUTDOOR
    rate: float = 0.05             # кг/с при полной интенсивности
    hole_area: Optional[float] = None   # м2; если задано, расход считается по физике
    pumped: bool = False           # утечка на напорной линии: расход зависит
                                   # от работы насосов и падает при их останове

    def apply(self, p: Plant):
        k = self.intensity(p.t)
        if k <= 0 or self.vessel in p.isolated:
            p.leaks.pop(self.fid, None)
            return
        if self.pumped:
            pumps_on = any(ps.running and not ps.failed and not ps.cavitating
                           and ps.vessel == self.vessel
                           for ps in p.pumps.values())
            k *= 1.0 if pumps_on else 0.55
        if self.hole_area is not None:
            VP = p.vessel_pressures(p.y)
            P = VP[self.vessel]["P"]
            dP = max(P - 101325.0, 0.0)
            rho = pr.rho_l(P)
            # Истечение вскипающей жидкости: коэффициент расхода 0.61,
            # двухфазность учитывается понижающим множителем 0.55.
            rate = 0.61 * 0.55 * self.hole_area * math.sqrt(2.0 * rho * dP)
        else:
            rate = self.rate
        p.leaks[self.fid] = {"vessel": self.vessel, "zone": self.zone,
                             "rate": rate * k}

    def revert(self, p: Plant):
        p.leaks.pop(self.fid, None)


# =========================================================================
# F-SENSOR: отказ датчика
# =========================================================================

@dataclass
class SensorFault(Fault):
    tag: str = "LEVEL_VE-LP"       # LEVEL_<vessel> | PRESSURE_<vessel> | NH3_<zone>
    kind: str = "stuck"            # stuck | drift | open | scale
    value: float = 0.45            # для stuck; множитель для scale
    bias: float = 0.0              # для drift

    def apply(self, p: Plant):
        if not self.active(p.t):
            p.sensor_faults.pop(self.tag, None)
            self._clear_zone(p)
            return
        if self.tag.startswith("NH3_"):
            zone = self.tag[4:]
            z = p.disp.zones.get(zone)
            if z:
                if self.kind == "scale":
                    z.detector_scale = self.value
                else:
                    z.detector_failed = (self.kind in ("stuck", "open"))
                    z.detector_bias = (self.bias * self.intensity(p.t)
                                       if self.kind == "drift"
                                       else (self.value if self.kind == "stuck"
                                             else 0.0))
            return
        p.sensor_faults[self.tag] = {
            "type": self.kind, "value": self.value,
            "bias": self.bias * self.intensity(p.t)}

    def _clear_zone(self, p: Plant):
        if self.tag.startswith("NH3_"):
            z = p.disp.zones.get(self.tag[4:])
            if z:
                z.detector_failed = False
                z.detector_bias = 0.0

    def revert(self, p: Plant):
        p.sensor_faults.pop(self.tag, None)
        self._clear_zone(p)


# =========================================================================
# F-POWER: обесточивание
# =========================================================================

@dataclass
class PowerFault(Fault):
    def apply(self, p: Plant):
        p.power_available = not self.active(p.t)
        if self.active(p.t):
            for cs in p.comp.values():
                cs.running = False
            for ps in p.pumps.values():
                ps.running = False
            for cd in p.cond.values():
                cd.fans_running = 0
                cd.pump_running = False

    def revert(self, p: Plant):
        p.power_available = True


# =========================================================================
# F-CTRL: сбой логики управления
# =========================================================================

@dataclass
class StuckDefrostFault(Fault):
    """
    Зависшая последовательность оттайки: контроллер не продвигает стадию.
    Змеевик остаётся под давлением горячего пара сколь угодно долго. На панели
    это выглядит безобидно -- аппарат просто «долго оттаивает».
    """
    targets: tuple = ()
    stage: int = HOTGAS

    def apply(self, p: Plant):
        if not self.active(p.t):
            return
        for tag in self.targets:
            es = p.evap.get(tag)
            if es is None:
                continue
            if es.plc_mode != self.stage:
                es.plc_mode = self.stage
                es.mode = self.stage
                es.hotgas_valve = self.stage == HOTGAS
                es.suction_valve = False
                es.feed_valve = False
                es.drain_valve = self.stage == HOTGAS
            es.stage_timer = 0.0      # таймер не идёт: стадия не завершится


@dataclass
class DefrostDesyncFault(Fault):
    """
    Рассинхронизация логического и физического состояния цикла оттайки.

    Контроллер начинает считать, что змеевик в режиме охлаждения, тогда как
    физически в нём остаётся горячий пар высокого давления и прогретый металл.
    Следующее открытие клапана подачи впускает жидкость -40 C в горячий змеевик.

    Это точная модель первопричины аварии на Millard Refrigerated Services
    (CSB Safety Bulletin 2010-13-A-AL): восстановление питания и последующий
    сброс тревог перевели группу испарителей из оттайки в охлаждение, минуя
    стадии удаления горячего газа.
    """
    targets: tuple = ()

    def apply(self, p: Plant):
        if self.applied or not self.active(p.t):
            return
        self.applied = True
        for tag in self.targets:
            es = p.evap.get(tag)
            if es is None:
                continue
            # ЛОГИЧЕСКОЕ состояние сбрасывается в COOL, ФИЗИЧЕСКОЕ (давление
            # в змеевике, температура металла) остаётся прежним.
            es.plc_mode = COOL
            es.mode = COOL
            es.stage_timer = 0.0
            es.feed_valve = True
            es.suction_valve = True
            es.hotgas_valve = False
            es.drain_valve = False
        p.log(f"F-CTRL: сброс состояния оттайки для {list(self.targets)}")


# =========================================================================
# Прочие отказы
# =========================================================================

@dataclass
class FoulingFault(Fault):
    """Загрязнение испарительного конденсатора."""
    condenser: str = "CD-01"
    final_fouling: float = 0.45

    def apply(self, p: Plant):
        if not self.active(p.t):
            return
        k = self.intensity(p.t)
        p.cond[self.condenser].fouling = 1.0 - (1.0 - self.final_fouling) * k


@dataclass
class FanFault(Fault):
    condenser: str = "CD-01"
    fans_lost: int = 2

    def apply(self, p: Plant):
        if not self.active(p.t):
            return
        st = p.cond[self.condenser]
        cfg = next(c for c in p.cfg.condensers if c.tag == self.condenser)
        st.fans_running = max(0, min(st.fans_running, cfg.n_fans - self.fans_lost))


@dataclass
class PumpFault(Fault):
    pump: str = "PU-LP-A"

    def apply(self, p: Plant):
        if not self.active(p.t):
            return
        ps = p.pumps[self.pump]
        ps.failed = True
        ps.running = False

    def revert(self, p: Plant):
        p.pumps[self.pump].failed = False


@dataclass
class ValveFault(Fault):
    valve: str = "LV-LP"
    kind: str = "stuck_open"
    opening: float = 1.0

    def apply(self, p: Plant):
        if not self.active(p.t):
            p.valve_faults.pop(self.valve, None)
            return
        p.valve_faults[self.valve] = {"type": self.kind, "opening": self.opening}

    def revert(self, p: Plant):
        p.valve_faults.pop(self.valve, None)


@dataclass
class NCGFault(Fault):
    """Накопление неконденсирующихся газов."""
    rate_kg_s: float = 2.0e-4

    def apply(self, p: Plant):
        entry = {"type": "F-NCG", "rate": self.rate_kg_s if self.active(p.t) else 0.0,
                 "active": True, "fid": self.fid}
        for f in p.faults:
            if f.get("fid") == self.fid:
                f.update(entry)
                return
        p.faults.append(entry)


@dataclass
class CorrosionFault(Fault):
    """Коррозионное утонение стенки трубопровода."""
    segment: str = "HEADER-LP"
    wall_loss: float = 0.45

    def apply(self, p: Plant):
        if not self.active(p.t):
            return
        p.segments[self.segment].wall_loss = self.wall_loss * self.intensity(p.t)


# =========================================================================
# Менеджер
# =========================================================================

class FaultManager:
    def __init__(self, faults=None):
        self.faults = list(faults or [])

    def add(self, f: Fault):
        self.faults.append(f)
        return f

    def step(self, p: Plant):
        for f in self.faults:
            if f.active(p.t):
                f.apply(p)
                if not f.applied:
                    f.applied = True
                    p.log(f"FAULT ACTIVE: {f.fid} ({type(f).__name__})")
            elif f.applied and not f.ended and p.t > f.t_start:
                f.revert(p)
                f.ended = True
                p.log(f"FAULT ENDED: {f.fid}")


# =========================================================================
# F-EMI: наводка на измерительную петлю газоанализатора
# =========================================================================

@dataclass
class VentEMIFault(Fault):
    """
    Наводка от частотного привода аварийной вытяжки на токовую петлю 4-20 мА
    стационарного газоанализатора.

    Пока аварийная вытяжка выключена, датчик завышает показание на небольшую
    постоянную величину (плохое заземление экрана после ремонта). При
    включённой аварийной вытяжке наводка растёт со временем работы привода и
    насыщается: амплитуда помехи ограничена размахом токовой петли, поэтому
    показание не доходит до уставки IDLH -- автоматика от этой неисправности
    установку не остановит.

    Смещение СКЛАДЫВАЕТСЯ с истинной концентрацией: прибор не отключён от
    процесса, он завышает. Перекалибровка по ПГС обнуляет смещение, но пока
    частотник работает, наводка возвращается -- ровно так уже ведёт себя
    дрейф в S5.
    """
    zone: str = "MACHINE_ROOM"
    base_bias: float = 26.0        # ppm, постоянное завышение
    vent_bias_max: float = 200.0   # ppm, потолок наводки от вытяжки
    rise_rate: float = 0.8         # ppm/с роста при работающей вытяжке
    decay_tau: float = 80.0        # с, спад наводки после отключения
    _extra: float = 0.0
    _last_t: Optional[float] = None

    def apply(self, p: Plant):
        z = p.disp.zones.get(self.zone)
        if z is None:
            return
        if not self.active(p.t):
            z.detector_bias = 0.0
            return
        if self._last_t is None:
            self._last_t = p.t
        dt = max(p.t - self._last_t, 0.0)
        self._last_t = p.t
        if z.emergency_vent:
            self._extra = min(self._extra + self.rise_rate * dt,
                              self.vent_bias_max)
        else:
            self._extra -= self._extra * dt / max(self.decay_tau, 1.0)
        z.detector_bias = (self.base_bias + self._extra) * self.intensity(p.t)

    def revert(self, p: Plant):
        z = p.disp.zones.get(self.zone)
        if z:
            z.detector_bias = 0.0
