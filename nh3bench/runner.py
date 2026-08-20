"""Episode runner: scenario -> agent -> plant, with logging and scoring."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import List, Optional

from .plant import ControlAction, Plant, PlantConfig
from .safety import apply_safety
from .scenarios import Scenario
from .scoring import ScoreReport, build_report

TREND_LEN = 6


def build_observation(
    plant: Plant,
    last_action: ControlAction,
    alarms: List[str],
    overrides: List[str],
    trend: deque,
) -> dict:
    st, cfg = plant.state, plant.cfg
    from . import properties as props

    rooms = {}
    for rcfg in cfg.rooms:
        rs = st.rooms[rcfg.name]
        rooms[rcfg.name] = {
            "temp_c": round(rs.temp_c, 2),
            "setpoint_c": rcfg.setpoint_c,
            "band": [rcfg.band_lo_c, rcfg.band_hi_c],
            "valve_open": bool(last_action.room_valves.get(rcfg.name, False)),
            "frost": round(rs.frost, 3),
            "defrost_active": rs.defrost_left_s > 0,
            "since_defrost_h": round(min(rs.since_defrost_s, 360000.0) / 3600.0, 2),
            "door_open": rs.door_open_left_s > 0,
            "product_mass_kg": round(rs.product_mass_kg, 0),
            "product_temp_c": round(rs.product_temp_c, 1),
        }
    compressors = []
    for ccfg, cst in zip(cfg.compressors, st.compressors):
        compressors.append(
            {
                "name": ccfg.name,
                "variable": ccfg.variable,
                "capacity": round(cst.capacity, 2),
                "available": cst.tripped_left_s <= 0 and cst.lockout_left_s <= 0,
                "lockout_s": round(cst.lockout_left_s, 0),
                "can_stop": cst.since_start_s >= ccfg.min_run_s,
                "can_start": cst.since_stop_s >= ccfg.min_off_s,
            }
        )
    return {
        "time_h": round(st.time_s / 3600.0, 3),
        "ambient_c": round(st.ambient_c, 1),
        "rooms": rooms,
        "suction_kpa": round(st.p_suction_kpa, 1),
        "t_evap_sat_c": round(props.tsat_c(st.p_suction_kpa), 1),
        "discharge_kpa": round(st.p_discharge_kpa, 1),
        "t_cond_c": round(st.t_cond_c, 1),
        "compressors": compressors,
        "condenser_fan": round(st.cond_fan, 2),
        "electrical_kw": round(st.electrical_kw, 1),
        "cooling_kw": round(st.q_evap_kw, 1),
        "energy_kwh": round(st.energy_kwh, 1),
        "violation_degc_h": round(st.violation_degc_h, 3),
        "safety_trips": st.safety_trips,
        "compressor_starts": st.compressor_starts,
        "alarms": alarms[-5:],
        "overrides_last_step": overrides[-6:],
        "trend": {k: list(v) for k, v in _trend_dict(trend).items()},
    }


def _trend_dict(trend: deque) -> dict:
    out: dict = {}
    for sample in trend:
        for k, v in sample.items():
            out.setdefault(k, []).append(v)
    return out


def run_episode(
    scenario: Scenario,
    agent,
    control_interval_s: float = 60.0,
    dt_s: float = 5.0,
    hours: Optional[float] = None,
    log_path: Optional[str] = None,
    config: Optional[PlantConfig] = None,
    verbose: bool = False,
) -> ScoreReport:
    plant = Plant(config)
    cfg = plant.cfg
    duration_s = (hours if hours is not None else scenario.duration_h) * 3600.0
    events = sorted(scenario.events, key=lambda e: e[0])
    next_event = 0

    action = ControlAction(
        compressor_capacity=[0.0] * len(cfg.compressors),
        room_valves={r.name: False for r in cfg.rooms},
        condenser_fan=0.3,
    )
    alarms: List[str] = []
    overrides: List[str] = []
    trend: deque = deque(maxlen=TREND_LEN)
    latencies: List[float] = []
    log_file = None
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "w", encoding="utf-8")

    try:
        t = 0.0
        while t < duration_s - 1e-6:
            trend.append(
                {
                    "suction_kpa": round(plant.state.p_suction_kpa, 1),
                    "discharge_kpa": round(plant.state.p_discharge_kpa, 0),
                    **{
                        f"{name}_c": round(rs.temp_c, 2)
                        for name, rs in plant.state.rooms.items()
                    },
                }
            )
            obs = build_observation(plant, action, alarms, overrides, trend)

            t0 = time.perf_counter()
            proposed = agent.decide(obs)
            latency = time.perf_counter() - t0
            latencies.append(latency)

            action, overrides = apply_safety(proposed, plant.state, cfg)

            step_alarms: List[str] = []
            sub_t = t
            while sub_t < min(t + control_interval_s, duration_s) - 1e-6:
                while next_event < len(events) and events[next_event][0] <= sub_t:
                    _, kind, args = events[next_event]
                    if kind == "product":
                        plant.add_product(*args)
                    elif kind == "door":
                        plant.open_door(*args)
                    elif kind == "comp_trip":
                        plant.trip_compressor(*args)
                    elif kind == "fouling":
                        plant.set_condenser_fouling(*args)
                    next_event += 1
                step_alarms += plant.step(action, dt_s, scenario.ambient_c(sub_t))
                sub_t += dt_s
            alarms = step_alarms
            t = sub_t

            if log_file:
                log_file.write(
                    json.dumps(
                        {
                            "t_h": round(t / 3600.0, 3),
                            "obs": obs,
                            "action": {
                                "compressor_capacity": action.compressor_capacity,
                                "room_valves": action.room_valves,
                                "start_defrost": action.start_defrost,
                                "condenser_fan": action.condenser_fan,
                            },
                            "reasoning": getattr(agent, "last_reasoning", ""),
                            "note": getattr(agent, "note", ""),
                            "overrides": overrides,
                            "alarms": step_alarms,
                            "latency_s": round(latency, 3),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            if verbose:
                rooms_str = " ".join(
                    f"{n}={rs.temp_c:+.1f}C" for n, rs in plant.state.rooms.items()
                )
                print(
                    f"[{t / 3600.0:5.2f}h] {rooms_str} suc={plant.state.p_suction_kpa:5.0f}kPa "
                    f"dis={plant.state.p_discharge_kpa:6.0f}kPa "
                    f"P={plant.state.electrical_kw:5.1f}kW "
                    f"E={plant.state.energy_kwh:6.1f}kWh"
                    + (f" ALARM:{step_alarms[-1]}" if step_alarms else "")
                )
    finally:
        if log_file:
            log_file.close()

    return build_report(
        scenario=scenario.name,
        agent=getattr(agent, "name", type(agent).__name__),
        duration_h=duration_s / 3600.0,
        state=plant.state,
        latencies_s=latencies,
        llm_stats=getattr(agent, "stats", {}),
    )
