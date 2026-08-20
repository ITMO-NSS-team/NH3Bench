"""Classic rule-based controller: hysteresis valves + staged compressors.

This is both the benchmark's reference score and the degraded-mode fallback
used by the LLM agent when the API is unavailable - a real plant never stops
being controlled just because a network call failed.
"""

from __future__ import annotations

from typing import Dict

from .plant import ControlAction, PlantConfig, default_plant_config

SUCTION_TARGET_KPA = 150.0
VALVE_HYSTERESIS_K = 0.7


class ThermostatBaseline:
    name = "baseline"

    def __init__(self, config: PlantConfig = None):
        self.cfg = config or default_plant_config()
        self._valves: Dict[str, bool] = {r.name: False for r in self.cfg.rooms}
        self._total_cap = 1.0  # requested total compressor capacity, 0..N

    def decide(self, obs: dict) -> ControlAction:
        rooms = obs["rooms"]

        # room thermostats
        for rcfg in self.cfg.rooms:
            t = rooms[rcfg.name]["temp_c"]
            if t > rcfg.setpoint_c + VALVE_HYSTERESIS_K:
                self._valves[rcfg.name] = True
            elif t < rcfg.setpoint_c - VALVE_HYSTERESIS_K:
                self._valves[rcfg.name] = False

        # compressor staging on suction pressure (integral-ish, rate-limited);
        # pump-down complete (no valves open) -> stop the rack
        n = len(self.cfg.compressors)
        if not any(self._valves.values()):
            self._total_cap = 0.0
        else:
            err = obs["suction_kpa"] - SUCTION_TARGET_KPA
            self._total_cap += min(max(0.01 * err, -0.4), 0.4)
        # high-pressure protection: shed capacity before the HP switch does
        if obs["discharge_kpa"] > 1400.0:
            self._total_cap = min(self._total_cap, max(self._total_cap - 0.5, 0.0))
        self._total_cap = min(max(self._total_cap, 0.0), float(n))
        caps = [0.0] * n
        # fixed stages first (C1, C2 ...), the variable unit trims on top
        fixed = [i for i, c in enumerate(self.cfg.compressors) if not c.variable]
        variable = [i for i, c in enumerate(self.cfg.compressors) if c.variable]
        remaining = self._total_cap
        for i in fixed:
            if remaining >= 1.0:
                caps[i] = 1.0
                remaining -= 1.0
        for i in variable:
            if remaining > 0.05:
                caps[i] = min(max(remaining, 0.25), 1.0)
                remaining = 0.0

        # condenser fan proportional to discharge pressure
        fan = min(max((obs["discharge_kpa"] - 900.0) / 400.0, 0.15), 1.0)

        # defrost when the frost index is high
        defrost = [
            name
            for name, r in rooms.items()
            if r["frost"] > 0.6 and not r["defrost_active"]
        ]

        return ControlAction(
            compressor_capacity=caps,
            room_valves=dict(self._valves),
            start_defrost=defrost,
            condenser_fan=fan,
        )
