"""Benchmark scenarios: the workshop's *demands* live here.

A scenario defines everything the controller does not choose: the ambient
temperature profile, the production schedule (warm product loaded into
rooms), door openings, and equipment faults.  Scenario events are injected
into the plant by the runner at the prescribed times.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

# event kinds: ("product", room, mass_kg, temp_c) | ("door", room, duration_s)
#              | ("comp_trip", index, duration_s) | ("fouling", factor)
Event = Tuple[float, str, tuple]


@dataclass
class Scenario:
    name: str
    description: str
    duration_h: float
    ambient_c: Callable[[float], float]  # t_s -> degC
    events: List[Event] = field(default_factory=list)


def _diurnal(base: float, amp: float) -> Callable[[float], float]:
    def f(t_s: float) -> float:
        # minimum at 05:00, maximum at 17:00; episode starts at 08:00
        hours = 8.0 + t_s / 3600.0
        return base + amp * math.sin(math.pi * (hours - 5.0) / 12.0)

    return f


def _shift_loads(rooms_kg: Dict[str, float], temp_c: float) -> List[Event]:
    """A day shift: product arrives every 2 h from t=+30 min, 4 deliveries."""
    events: List[Event] = []
    for k in range(4):
        t = 1800.0 + k * 7200.0
        for room, mass in rooms_kg.items():
            events.append((t, "product", (room, mass, temp_c)))
        events.append((t + 60.0, "door", (list(rooms_kg)[0], 180.0)))
    return events


SCENARIOS: Dict[str, Scenario] = {}


def _register(s: Scenario) -> Scenario:
    SCENARIOS[s.name] = s
    return s


_register(
    Scenario(
        name="baseline_day",
        description="Ordinary production day: 22C ambient, four deliveries "
        "of warm product to the chill store and processing hall.",
        duration_h=12.0,
        ambient_c=_diurnal(22.0, 5.0),
        events=_shift_loads({"chill": 2500.0, "processing": 1200.0}, 18.0),
    )
)

_register(
    Scenario(
        name="heatwave",
        description="Heat wave: 34C ambient peak; condenser margin becomes "
        "the binding constraint (HP cutout risk).",
        duration_h=12.0,
        ambient_c=_diurnal(31.0, 6.0),
        events=_shift_loads({"chill": 2500.0, "processing": 1200.0}, 24.0),
    )
)

_register(
    Scenario(
        name="compressor_trip",
        description="Compressor C1 trips for 3 h in the middle of the shift; "
        "remaining capacity must be rationed between rooms.",
        duration_h=12.0,
        ambient_c=_diurnal(24.0, 5.0),
        events=_shift_loads({"chill": 2500.0, "processing": 1200.0}, 18.0)
        + [(4.0 * 3600.0, "comp_trip", (0, 3.0 * 3600.0))],
    )
)

_register(
    Scenario(
        name="door_left_open",
        description="Freezer door left open for 40 min twice during the "
        "shift - infiltration load plus rapid frosting.",
        duration_h=12.0,
        ambient_c=_diurnal(23.0, 5.0),
        events=_shift_loads({"chill": 2000.0, "processing": 1000.0}, 18.0)
        + [
            (2.5 * 3600.0, "door", ("freezer", 2400.0)),
            (7.5 * 3600.0, "door", ("freezer", 2400.0)),
        ],
    )
)

_register(
    Scenario(
        name="fouled_condenser_surge",
        description="30 % condenser fouling all day plus a double-size "
        "delivery surge in the afternoon.",
        duration_h=12.0,
        ambient_c=_diurnal(26.0, 5.0),
        events=[(0.0, "fouling", (0.30,))]
        + _shift_loads({"chill": 2500.0, "processing": 1200.0}, 18.0)
        + [
            (6.0 * 3600.0, "product", ("chill", 5000.0, 20.0)),
            (6.0 * 3600.0, "product", ("freezer", 1500.0, -8.0)),
        ],
    )
)
