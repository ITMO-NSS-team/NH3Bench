"""
Episode runner: the single place where the twin, the PLC, the safety
layer and the fault injection are wired together.

The order of computation inside one step is fixed, which is what makes
a run deterministic:
    1. fault injection
    2. PLC
    3. safety system (ESD)
    4. twin integration
    5. history recording
"""

from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np

from .plant import Plant
from .control import PLC, AlarmSystem, SafetySystem
from .faults import FaultManager
from .dispersion import Operator
from .config import PlantConfig, DEFAULT


@dataclass
class RunResult:
    tags_history: list
    events: list
    alarms: list
    summary: dict
    wall_time: float
    steps: int

    def series(self, key: str):
        return np.array([row.get(key, np.nan) for row in self.tags_history])

    def time_h(self):
        return self.series("TIME_H")


class Runner:

    def __init__(self, cfg: PlantConfig = None, seed: int = 0,
                 dt: float = 0.5, log_every: float = 30.0,
                 start_hour: float = 3.0, plant: Plant = None):
        self.plant = plant or Plant(cfg or DEFAULT, seed=seed)
        self.plant.t = start_hour * 3600.0
        self.alarms = AlarmSystem()
        self.plc = PLC(self.plant, self.alarms)
        self.safety = SafetySystem(self.plant, self.alarms)
        self.fm = FaultManager()
        self.dt = dt
        self.log_every = log_every
        self.history = []
        self._t_next_log = self.plant.t

    def add_operator(self, op_id, zone="CONTROL_ROOM", ppe=(), role="technician"):
        op = Operator(op_id=op_id, zone=zone, ppe=tuple(ppe))
        self.plant.disp.add_operator(op)
        return op

    def add_fault(self, f):
        return self.fm.add(f)

    def warmup(self, hours: float = 1.0, defrost: bool = False):
        """Warm up to steady state: no faults, no history recorded."""
        saved = self.plc.defrost_enabled
        self.plc.defrost_enabled = defrost
        n = int(hours * 3600 / self.dt)
        for _ in range(n):
            self.plc.step(self.dt)
            self.safety.step()
            self.plant.step(self.dt)
        self.plc.defrost_enabled = saved
        self._t_next_log = self.plant.t
        return self

    def run(self, hours: float, stop_on_cat: bool = True) -> RunResult:
        import time
        p = self.plant
        n = int(hours * 3600 / self.dt)
        t0 = time.time()
        steps = 0
        for _ in range(n):
            self.fm.step(p)
            self.plc.step(self.dt)
            self.safety.step()
            p.step(self.dt)
            steps += 1
            if p.t >= self._t_next_log:
                self.history.append(p.tags())
                self._t_next_log += self.log_every
            if stop_on_cat and p.cat_flags:
                self.history.append(p.tags())
                break
        wall = time.time() - t0
        return RunResult(
            tags_history=self.history,
            events=list(p.events),
            alarms=list(self.alarms.history),
            summary=p.summary(),
            wall_time=wall,
            steps=steps,
        )
