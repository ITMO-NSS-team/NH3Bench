"""
Fault injection library.

A fault is not "noise in the data" but a physical event that starts a
specific accident trajectory. Every fault has a moment of activation,
parameters and, optionally, a ramp profile.

The accident-forcing principle: the fault set of a scenario is chosen so
that inaction leads to an accident with probability no lower than 0.9.
This is checked by calibration with three reference policies (see
tests/run_baselines.py).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math

from . import props as pr
from .plant import Plant, COOL, PUMPDOWN, HOTGAS, DRAIN, EQUALIZE, IDLE


@dataclass
class Fault:
    """Base fault."""
    fid: str
    t_start: float                 # s since the start of the run
    duration: Optional[float] = None
    ramp: float = 0.0              # s, time to ramp up to full intensity
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
# F-LEAK: an ammonia leak
# =========================================================================

@dataclass
class LeakFault(Fault):
    vessel: str = "VE-LP"
    zone: str = "MACHINE_ROOM"     # MACHINE_ROOM | HALL | OUTDOOR
    rate: float = 0.05             # kg/s at full intensity
    hole_area: Optional[float] = None   # m2; if given, the rate is computed from physics
    pumped: bool = False           # a leak on a pumped feed line: the rate
                                   # depends on the pumps running and drops
                                   # when they stop

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
            # Flashing liquid discharge: discharge coefficient 0.61, and the
            # two-phase nature is accounted for by a reducing factor of 0.55.
            rate = 0.61 * 0.55 * self.hole_area * math.sqrt(2.0 * rho * dP)
        else:
            rate = self.rate
        p.leaks[self.fid] = {"vessel": self.vessel, "zone": self.zone,
                             "rate": rate * k}

    def revert(self, p: Plant):
        p.leaks.pop(self.fid, None)


# =========================================================================
# F-SENSOR: a sensor fault
# =========================================================================

@dataclass
class SensorFault(Fault):
    tag: str = "LEVEL_VE-LP"       # LEVEL_<vessel> | PRESSURE_<vessel> | NH3_<zone>
    kind: str = "stuck"            # stuck | drift | open | scale
    value: float = 0.45            # for stuck; a multiplier for scale
    bias: float = 0.0              # for drift

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
# F-POWER: loss of power
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
# F-CTRL: a control-logic failure
# =========================================================================

@dataclass
class StuckDefrostFault(Fault):
    """
    A hung defrost sequence: the controller does not advance the stage.
    The coil stays under hot-gas pressure for as long as you like. On the
    panel this looks harmless -- the unit is simply "taking a long time to
    defrost".
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
            es.stage_timer = 0.0      # the timer does not run: the stage will not finish


@dataclass
class DefrostDesyncFault(Fault):
    """
    Desynchronization of the logical and the physical state of the defrost
    cycle.

    The controller starts believing that the coil is in cooling mode, while
    physically it still holds high-pressure hot gas and warmed metal. The
    next opening of the feed valve lets -40 C liquid into a hot coil.

    This is a faithful model of the root cause of the accident at Millard
    Refrigerated Services (CSB Safety Bulletin 2010-13-A-AL): restoring
    power and then resetting the alarms moved a group of evaporators from
    defrost into cooling, skipping the hot-gas removal stages.
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
            # The LOGICAL state is reset to COOL; the PHYSICAL one (coil
            # pressure, metal temperature) stays as it was.
            es.plc_mode = COOL
            es.mode = COOL
            es.stage_timer = 0.0
            es.feed_valve = True
            es.suction_valve = True
            es.hotgas_valve = False
            es.drain_valve = False
        p.log(f"F-CTRL: сброс состояния оттайки для {list(self.targets)}")


# =========================================================================
# Other faults
# =========================================================================

@dataclass
class FoulingFault(Fault):
    """Fouling of an evaporative condenser."""
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
    """Accumulation of non-condensable gases."""
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
    """Corrosive thinning of a pipe wall."""
    segment: str = "HEADER-LP"
    wall_loss: float = 0.45

    def apply(self, p: Plant):
        if not self.active(p.t):
            return
        p.segments[self.segment].wall_loss = self.wall_loss * self.intensity(p.t)


# =========================================================================
# Manager
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
# F-EMI: interference on the gas detector's measuring loop
# =========================================================================

@dataclass
class VentEMIFault(Fault):
    """
    Interference from the emergency-ventilation variable-frequency drive on
    the 4-20 mA current loop of the fixed gas detector.

    While the emergency ventilation is off, the detector overreads by a
    small constant amount (poor shield grounding after a repair). With the
    emergency ventilation on, the interference grows with the drive's
    running time and saturates: the amplitude of the disturbance is limited
    by the span of the current loop, so the reading never reaches the IDLH
    setpoint -- the automation will not stop the plant on this fault.

    The offset is ADDED to the true concentration: the instrument is not
    disconnected from the process, it overreads. Recalibration against a
    span gas zeroes the offset, but while the drive runs the interference
    comes back -- exactly the way the drift in S5 already behaves.
    """
    zone: str = "MACHINE_ROOM"
    base_bias: float = 26.0        # ppm, the constant overreading
    vent_bias_max: float = 200.0   # ppm, ceiling of the interference from the ventilation
    rise_rate: float = 0.8         # ppm/s of growth while the ventilation runs
    decay_tau: float = 80.0        # s, decay of the interference after it is switched off
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
