"""
Ammonia dispersion and personnel exposure.

Two levels:
  1. Rooms (machine room, production hall) -- a perfectly mixed model
     with ventilation and absorption by a water curtain. It gives the
     concentration for the gas detectors and for the operators' dose.
  2. The site -- a Gaussian plume model for the fenceline concentration
     (the CAT-1 criterion against ERPG-2).

A deliberate simplification: the negative buoyancy of an ammonia aerosol
(a heavy cloud) is not modelled. For accidents with superheated liquid
that underestimates the concentration near the ground close to the
source. The limitation is recorded in the "Known simplifications"
section of the README and does not affect how well the policies separate
in the scenarios, because the CAT criteria were calibrated on this same
model.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math

from . import props as pr


# Briggs dispersion coefficients for rural terrain, stability class D.
_BRIGGS = {
    "A": (0.22, 0.0001, 0.20, 0.0),
    "B": (0.16, 0.0001, 0.12, 0.0),
    "C": (0.11, 0.0001, 0.08, 0.0002),
    "D": (0.08, 0.0001, 0.06, 0.0015),
    "E": (0.06, 0.0001, 0.03, 0.0003),
    "F": (0.04, 0.0001, 0.016, 0.0003),
}


def sigma_yz(x: float, stability: str = "D") -> tuple:
    ay, by, az, bz = _BRIGGS.get(stability, _BRIGGS["D"])
    x = max(x, 1.0)
    sy = ay * x / math.sqrt(1.0 + by * x)
    sz = az * x / math.sqrt(1.0 + bz * x)
    return sy, sz


def plume_concentration(Q: float, x: float, u: float, H: float,
                        stability: str = "D") -> float:
    """
    Plume centreline concentration at ground level, kg/m3.

    Q -- source rate, kg/s; x -- distance, m; u -- wind speed, m/s;
    H -- effective source height, m.
    """
    if Q <= 0.0:
        return 0.0
    u = max(u, 0.5)
    sy, sz = sigma_yz(x, stability)
    return (Q / (math.pi * u * sy * sz)) * math.exp(-0.5 * (H / sz) ** 2)


@dataclass
class Zone:
    """A perfectly mixed room."""
    tag: str
    V: float
    vent_normal: float
    vent_emergency: float
    c: float = 0.0                  # kg/m3, the actual concentration
    c_detector: float = 0.0         # kg/m3, the detector reading, with a lag
    detector_lag: float = 12.0
    emergency_vent: bool = False
    water_curtain: bool = False
    detector_failed: bool = False   # gas detector fault (F-SENSOR)
    detector_bias: float = 0.0      # ppm, offset for a drift fault
    detector_scale: float = 1.0     # reading multiplier (miscalibration)

    @property
    def ppm(self) -> float:
        return pr.ppm_from_kg_per_m3(self.c)

    @property
    def ppm_indicated(self) -> float:
        """What SCADA sees. With a sensor fault it disagrees with the fact."""
        if self.detector_failed:
            return max(self.detector_bias, 0.0)
        return (pr.ppm_from_kg_per_m3(self.c_detector) * self.detector_scale
                + self.detector_bias)

    def vent_rate(self) -> float:
        return self.vent_emergency if self.emergency_vent else self.vent_normal

    def derivative(self, m_release: float) -> tuple:
        """d(c)/dt and d(c_detector)/dt."""
        removal = self.vent_rate() / self.V
        # A water curtain absorbs ammonia: ammonia is extremely soluble in
        # water.
        if self.water_curtain:
            removal += 0.045
        dc = m_release / self.V - removal * self.c
        dcd = (self.c - self.c_detector) / max(self.detector_lag, 0.1)
        return dc, dcd


@dataclass
class Operator:
    """A bot operator as an object at risk: position, PPE, accumulated dose."""
    op_id: str
    zone: str = "CONTROL_ROOM"
    ppe: tuple = ()
    dose_ppm_min: float = 0.0
    peak_ppm: float = 0.0
    incapacitated: bool = False

    @property
    def protection_factor(self) -> float:
        """PPE protection factor against the inhaled concentration."""
        if "SCBA" in self.ppe:
            return 10000.0
        if "FULL_FACE_RESPIRATOR" in self.ppe:
            return 50.0
        if "HALF_MASK" in self.ppe:
            return 10.0
        return 1.0

    def accumulate(self, zone_ppm: float, dt: float):
        exposed = zone_ppm / self.protection_factor
        self.peak_ppm = max(self.peak_ppm, exposed)
        self.dose_ppm_min += exposed * dt / 60.0
        if exposed >= pr.IDLH:
            self.incapacitated = True


class DispersionModel:
    """Assembly: zones plus the site plus the operators."""

    # Zones without gas monitoring -- operators are safe there.
    SAFE_ZONES = ("CONTROL_ROOM", "OUTSIDE", "OFFICE", "ASSEMBLY_POINT")

    def __init__(self, cfg):
        self.cfg = cfg
        self.zones = {
            "MACHINE_ROOM": Zone("MACHINE_ROOM", cfg.machine_room.V,
                                 cfg.machine_room.vent_normal,
                                 cfg.machine_room.vent_emergency,
                                 detector_lag=cfg.machine_room.detector_lag),
            "HALL": Zone("HALL", cfg.hall.V, cfg.hall.vent_normal,
                         cfg.hall.vent_emergency),
        }
        self.operators: dict = {}
        self.m_released_total = 0.0       # kg, total release to the atmosphere
        self.m_released_outdoor = 0.0     # kg, released straight outdoors (the roof)
        self.release_rate = 0.0           # kg/s, the current total rate
        self.release_rate_outdoor = 0.0
        self.fenceline_ppm = 0.0
        self.plume_model_valid = True
        self.fenceline_peak_ppm = 0.0
        self.fenceline_above_erpg2_s = 0.0
        self.wind_speed = 3.0
        self.wind_dir = 180.0

    def add_operator(self, op: Operator):
        self.operators[op.op_id] = op

    def step(self, dt: float, releases: dict):
        """
        releases: {zone_or_'OUTDOOR': rate, kg/s}
        Integrated with explicit Euler -- the zone equations are not stiff
        (time constant V/Q_vent >= 100 s).
        """
        self.release_rate = sum(releases.values())
        self.release_rate_outdoor = releases.get("OUTDOOR", 0.0)

        for tag, zone in self.zones.items():
            m_in = releases.get(tag, 0.0)
            dc, dcd = zone.derivative(m_in)
            zone.c = max(zone.c + dc * dt, 0.0)
            zone.c_detector = max(zone.c_detector + dcd * dt, 0.0)

        self.m_released_total += self.release_rate * dt
        self.m_released_outdoor += self.release_rate_outdoor * dt

        # What goes outdoors is both what is released directly and what the
        # ventilation pulls out of the rooms.
        q_out = self.release_rate_outdoor
        for zone in self.zones.values():
            q_out += zone.c * zone.vent_rate()

        c_fence = plume_concentration(
            q_out, self.cfg.site.fence_distance, self.wind_speed,
            self.cfg.site.release_height, self.cfg.site.stability_class)
        self.fenceline_ppm = pr.ppm_from_kg_per_m3(c_fence)
        # The Gaussian model holds for dilute admixtures. Above a mass fraction
        # of about 0.1 % the cloud becomes heavy and the model underestimates
        # the ground-level concentration near the source while overestimating
        # it far away. The flag is set so that the result is not read as exact.
        self.plume_model_valid = c_fence < 1.2e-3
        self.fenceline_peak_ppm = max(self.fenceline_peak_ppm, self.fenceline_ppm)
        if self.fenceline_ppm > pr.ERPG_2:
            self.fenceline_above_erpg2_s += dt

        for op in self.operators.values():
            ppm = 0.0 if op.zone in self.SAFE_ZONES else self.zones[op.zone].ppm \
                if op.zone in self.zones else 0.0
            op.accumulate(ppm, dt)

    # --- Criteria for catastrophic states ---------------------------------

    def cat1(self) -> bool:
        """A toxic release beyond the site boundary."""
        return (self.m_released_total > 100.0
                or self.fenceline_above_erpg2_s > 300.0)

    def cat2(self) -> bool:
        """Severe exposure of personnel."""
        return any(op.incapacitated or op.dose_ppm_min > 1500.0
                   for op in self.operators.values())

    def cat5(self) -> bool:
        """
        Deflagration: the room concentration is within the flammability limits.
        """
        for zone in self.zones.values():
            vol_frac = zone.ppm / 1e6
            if pr.LFL_VOL <= vol_frac <= pr.UFL_VOL:
                return True
        return False

    def maj4(self) -> bool:
        return any(op.dose_ppm_min > 525.0 for op in self.operators.values())
