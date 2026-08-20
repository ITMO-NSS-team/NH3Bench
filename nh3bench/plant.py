"""Lumped-parameter dynamic model of an industrial NH3 refrigeration plant.

The modelled plant is a pumped-recirculation ammonia system serving a
food-processing workshop:

* several cold rooms (freezer storage, chill store, processing hall), each
  with a flooded air cooler fed through a liquid-supply solenoid valve;
* one low-pressure suction accumulator (single suction level - a deliberate
  simplification of the classic two-stage industrial layout);
* a rack of reciprocating compressors (fixed-speed stages + one VFD unit);
* an evaporative condenser with a variable-speed fan.

The structure follows the supermarket-refrigeration benchmark of Larsen et
al. (display case <-> suction manifold <-> compressor rack mass balance) with
NH3 saturation properties and industrial-scale parameters; compressor work
uses a polytropic model as in vapour-compression cycle references (NIST
CYCLE_D-HX and the Rasmussen dynamic-modelling tutorials).

Hard safety interlocks (HP/LP cutouts, lockouts) live *inside* the physics
step: they act every physics substep, exactly like pressure switches on a
real plant, regardless of what any controller asked for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import properties as props

CP_PRODUCT_KJ_KG_K = 3.2  # typical foodstuff above freezing


@dataclass
class RoomConfig:
    name: str
    setpoint_c: float
    band_lo_c: float  # hard food-safety band
    band_hi_c: float
    ua_wall_kw_k: float
    thermal_mass_kj_k: float
    evap_ua_kw_k: float
    internal_load_kw: float = 0.0


@dataclass
class CompressorConfig:
    name: str
    max_flow_m3_h: float  # suction volumetric flow at 100 % capacity
    variable: bool = False  # False -> only 0/1 allowed
    min_run_s: float = 180.0
    min_off_s: float = 300.0


@dataclass
class PlantConfig:
    rooms: List[RoomConfig]
    compressors: List[CompressorConfig]
    # effective vapour buffer of the LP accumulator: geometric vapour space
    # plus the strong self-buffering of liquid flash-off as pressure drops
    suction_volume_m3: float = 12.0
    evap_approach_k: float = 2.0
    cond_ua_max_kw_k: float = 22.0
    cond_fan_max_kw: float = 7.5
    cond_tau_s: float = 90.0  # thermal inertia of the condenser
    pump_kw: float = 3.0
    polytropic_n: float = 1.31
    isentropic_eff: float = 0.72
    hp_cutout_kpa: float = 1650.0  # ~43 C condensing
    hp_reset_kpa: float = 1350.0
    lp_cutout_kpa: float = 60.0  # ~ -43 C saturation
    lp_reset_kpa: float = 90.0
    trip_lockout_s: float = 300.0
    defrost_heat_kw: float = 8.0
    defrost_duration_s: float = 900.0
    frost_rate_per_h: float = 0.06  # frost index growth per valve-open hour
    frost_ua_penalty: float = 0.8  # UA /= (1 + penalty * frost)


def default_plant_config() -> PlantConfig:
    """The reference NH3Bench plant: 3 rooms, 2 fixed + 1 VFD compressor."""
    return PlantConfig(
        rooms=[
            RoomConfig(
                name="freezer",
                setpoint_c=-20.0,
                band_lo_c=-25.0,
                band_hi_c=-18.0,
                ua_wall_kw_k=0.55,
                thermal_mass_kj_k=180_000.0,
                evap_ua_kw_k=9.0,
            ),
            RoomConfig(
                name="chill",
                setpoint_c=0.0,
                band_lo_c=-1.5,
                band_hi_c=4.0,
                ua_wall_kw_k=0.65,
                thermal_mass_kj_k=110_000.0,
                evap_ua_kw_k=6.0,
            ),
            RoomConfig(
                name="processing",
                setpoint_c=8.0,
                band_lo_c=2.0,
                band_hi_c=12.0,
                ua_wall_kw_k=1.1,
                thermal_mass_kj_k=45_000.0,
                evap_ua_kw_k=5.0,
                internal_load_kw=9.0,
            ),
        ],
        compressors=[
            CompressorConfig(name="C1", max_flow_m3_h=170.0),
            CompressorConfig(name="C2", max_flow_m3_h=170.0),
            CompressorConfig(name="C3", max_flow_m3_h=210.0, variable=True),
        ],
    )


@dataclass
class ControlAction:
    """One control decision, applied until the next control step."""

    compressor_capacity: List[float] = field(default_factory=list)  # 0..1 each
    room_valves: Dict[str, bool] = field(default_factory=dict)
    start_defrost: List[str] = field(default_factory=list)
    condenser_fan: float = 0.5  # 0..1


@dataclass
class RoomState:
    temp_c: float
    frost: float = 0.0
    defrost_left_s: float = 0.0
    since_defrost_s: float = 1e9
    product_mass_kg: float = 0.0
    product_temp_c: float = 0.0
    door_open_left_s: float = 0.0


@dataclass
class CompressorState:
    capacity: float = 0.0  # applied capacity 0..1
    since_start_s: float = 1e9
    since_stop_s: float = 1e9
    tripped_left_s: float = 0.0  # scenario fault
    lockout_left_s: float = 0.0  # safety lockout after HP/LP trip


@dataclass
class PlantState:
    time_s: float = 0.0
    rooms: Dict[str, RoomState] = field(default_factory=dict)
    compressors: List[CompressorState] = field(default_factory=list)
    p_suction_kpa: float = 190.0
    p_discharge_kpa: float = 1100.0
    t_cond_c: float = 30.0
    cond_fan: float = 0.5
    cond_fouling: float = 0.0  # 0..1, scenario fault
    ambient_c: float = 25.0
    # accumulators
    energy_kwh: float = 0.0
    electrical_kw: float = 0.0
    q_evap_kw: float = 0.0
    violation_degc_h: float = 0.0
    safety_trips: int = 0
    compressor_starts: int = 0
    alarms: List[str] = field(default_factory=list)


class Plant:
    """Explicit-Euler integration of the plant ODEs (dt of a few seconds)."""

    def __init__(self, config: Optional[PlantConfig] = None):
        self.cfg = config or default_plant_config()
        self.state = PlantState(
            rooms={r.name: RoomState(temp_c=r.setpoint_c) for r in self.cfg.rooms},
            compressors=[CompressorState() for _ in self.cfg.compressors],
        )
        self._lp_tripped = False

    # ------------------------------------------------------------------ events

    def add_product(self, room: str, mass_kg: float, temp_c: float) -> None:
        rs = self.state.rooms[room]
        total = rs.product_mass_kg + mass_kg
        if total > 0:
            rs.product_temp_c = (
                rs.product_temp_c * rs.product_mass_kg + temp_c * mass_kg
            ) / total
        rs.product_mass_kg = total

    def open_door(self, room: str, duration_s: float) -> None:
        self.state.rooms[room].door_open_left_s = duration_s

    def trip_compressor(self, index: int, duration_s: float) -> None:
        self.state.compressors[index].tripped_left_s = duration_s

    def set_condenser_fouling(self, fouling: float) -> None:
        self.state.cond_fouling = min(max(fouling, 0.0), 0.9)

    # ------------------------------------------------------------------- step

    def step(self, action: ControlAction, dt: float, ambient_c: float) -> List[str]:
        """Advance the plant by ``dt`` seconds under ``action``.

        Returns the list of alarm/interlock messages raised during this step.
        """
        cfg, st = self.cfg, self.state
        st.ambient_c = ambient_c
        alarms: List[str] = []

        # ---- apply compressor commands (respecting trips and lockouts)
        for i, (ccfg, cst) in enumerate(zip(cfg.compressors, st.compressors)):
            cap = action.compressor_capacity[i] if i < len(action.compressor_capacity) else 0.0
            cap = min(max(cap, 0.0), 1.0)
            if not ccfg.variable:
                cap = 1.0 if cap >= 0.5 else 0.0
            if cst.tripped_left_s > 0 or cst.lockout_left_s > 0:
                cap = 0.0
            was_on = cst.capacity > 0
            if cap > 0 and not was_on:
                st.compressor_starts += 1
                cst.since_start_s = 0.0
            if cap == 0 and was_on:
                cst.since_stop_s = 0.0
            cst.capacity = cap
            cst.since_start_s += dt
            cst.since_stop_s += dt
            cst.tripped_left_s = max(0.0, cst.tripped_left_s - dt)
            cst.lockout_left_s = max(0.0, cst.lockout_left_s - dt)

        st.cond_fan = min(max(action.condenser_fan, 0.0), 1.0)

        # ---- defrost triggers
        for name in action.start_defrost:
            rs = st.rooms.get(name)
            if rs is not None and rs.defrost_left_s <= 0:
                rs.defrost_left_s = cfg.defrost_duration_s
                rs.since_defrost_s = 0.0

        # ---- evaporators
        t_evap = props.tsat_c(st.p_suction_kpa) + cfg.evap_approach_k
        h_fg = props.h_fg_kj_kg(t_evap)
        q_evap_total = 0.0
        m_evap = 0.0  # kg/s vapour generated into the suction accumulator
        any_valve = False
        for rcfg in cfg.rooms:
            rs = st.rooms[rcfg.name]
            q_evap = 0.0
            q_extra = 0.0
            if rs.defrost_left_s > 0:
                rs.defrost_left_s = max(0.0, rs.defrost_left_s - dt)
                q_extra += cfg.defrost_heat_kw
                rs.frost = max(0.0, rs.frost - dt / cfg.defrost_duration_s)
            elif action.room_valves.get(rcfg.name, False):
                any_valve = True
                ua_eff = rcfg.evap_ua_kw_k / (1.0 + cfg.frost_ua_penalty * rs.frost)
                q_evap = max(0.0, ua_eff * (rs.temp_c - t_evap))
                m_evap += q_evap / h_fg
                if t_evap < 0:
                    rs.frost += cfg.frost_rate_per_h * dt / 3600.0
            rs.since_defrost_s += dt

            # heat loads
            ua_wall = rcfg.ua_wall_kw_k
            if rs.door_open_left_s > 0:
                ua_wall += 2.5  # infiltration through an open door
                rs.door_open_left_s = max(0.0, rs.door_open_left_s - dt)
            q_leak = ua_wall * (ambient_c - rs.temp_c)
            q_product = 0.0
            if rs.product_mass_kg > 1.0:
                # first-order pull-down of the warm product lump (tau ~ 2 h)
                q_product = (
                    rs.product_mass_kg
                    * CP_PRODUCT_KJ_KG_K
                    * (rs.product_temp_c - rs.temp_c)
                    / 7200.0
                )
                rs.product_temp_c -= q_product * dt / (
                    rs.product_mass_kg * CP_PRODUCT_KJ_KG_K
                )
            q_net = q_leak + q_product + rcfg.internal_load_kw + q_extra - q_evap
            rs.temp_c += q_net * dt / rcfg.thermal_mass_kj_k  # kW*s / (kJ/K) = K
            q_evap_total += q_evap

            # food-safety violation integral
            if rs.temp_c > rcfg.band_hi_c:
                st.violation_degc_h += (rs.temp_c - rcfg.band_hi_c) * dt / 3600.0
            elif rs.temp_c < rcfg.band_lo_c:
                st.violation_degc_h += (rcfg.band_lo_c - rs.temp_c) * dt / 3600.0

        # ---- compressor rack
        t_suc = props.tsat_c(st.p_suction_kpa)
        rho_suc = props.rho_vapor_kg_m3(t_suc)
        n = cfg.polytropic_n
        ratio = max(st.p_discharge_kpa / st.p_suction_kpa, 1.05)
        m_comp = 0.0
        w_el_kw = 0.0
        for ccfg, cst in zip(cfg.compressors, st.compressors):
            if cst.capacity <= 0:
                continue
            eta_vol = max(0.45, 1.0 - 0.05 * (ratio ** (1.0 / n) - 1.0))
            v_dot = cst.capacity * ccfg.max_flow_m3_h / 3600.0  # m3/s
            m_dot = v_dot * rho_suc * eta_vol
            # polytropic specific work, kJ/kg
            w_spec = (
                n
                / (n - 1.0)
                * (st.p_suction_kpa / rho_suc)
                * (ratio ** ((n - 1.0) / n) - 1.0)
            ) / cfg.isentropic_eff
            m_comp += m_dot
            w_el_kw += m_dot * w_spec

        # ---- suction accumulator vapour mass balance (isothermal ideal-gas)
        dp = (m_evap - m_comp) / max(rho_suc, 0.05) * (
            st.p_suction_kpa / cfg.suction_volume_m3
        ) * dt
        st.p_suction_kpa = min(max(st.p_suction_kpa + dp, 25.0), 600.0)

        # ---- condenser (evaporative, wet-bulb approx = ambient - 4 K)
        q_cond = q_evap_total + w_el_kw
        t_wb = ambient_c - 4.0
        ua_cond = (
            cfg.cond_ua_max_kw_k
            * max(st.cond_fan, 0.05) ** 0.7
            * (1.0 - st.cond_fouling)
        )
        t_cond_target = t_wb + q_cond / max(ua_cond, 0.5)
        st.t_cond_c += (t_cond_target - st.t_cond_c) * min(dt / cfg.cond_tau_s, 1.0)
        st.p_discharge_kpa = props.psat_kpa(max(st.t_cond_c, t_wb))

        # ---- hard interlocks (pressure switches)
        if st.p_discharge_kpa > cfg.hp_cutout_kpa:
            if any(c.capacity > 0 for c in st.compressors):
                st.safety_trips += 1
                alarms.append(
                    f"HP CUTOUT: discharge {st.p_discharge_kpa:.0f} kPa > "
                    f"{cfg.hp_cutout_kpa:.0f} kPa - all compressors tripped, "
                    f"{cfg.trip_lockout_s:.0f}s lockout"
                )
            for cst in st.compressors:
                if cst.capacity > 0:
                    cst.capacity = 0.0
                    cst.since_stop_s = 0.0
                cst.lockout_left_s = max(cst.lockout_left_s, cfg.trip_lockout_s)
        if st.p_suction_kpa < cfg.lp_cutout_kpa and not self._lp_tripped:
            self._lp_tripped = True
            if any(c.capacity > 0 for c in st.compressors):
                st.safety_trips += 1
                alarms.append(
                    f"LP CUTOUT: suction {st.p_suction_kpa:.0f} kPa < "
                    f"{cfg.lp_cutout_kpa:.0f} kPa - all compressors tripped"
                )
            for cst in st.compressors:
                if cst.capacity > 0:
                    cst.capacity = 0.0
                    cst.since_stop_s = 0.0
                cst.lockout_left_s = max(cst.lockout_left_s, cfg.trip_lockout_s)
        elif st.p_suction_kpa > cfg.lp_reset_kpa:
            self._lp_tripped = False

        # ---- energy metering
        fan_kw = cfg.cond_fan_max_kw * st.cond_fan**3
        pump_kw = cfg.pump_kw if any_valve else 0.0
        st.electrical_kw = w_el_kw + fan_kw + pump_kw
        st.q_evap_kw = q_evap_total
        st.energy_kwh += st.electrical_kw * dt / 3600.0

        st.time_s += dt
        st.alarms = alarms
        return alarms
