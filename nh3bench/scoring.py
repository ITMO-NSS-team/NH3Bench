"""Episode scoring.

The composite score is a cost in abstract units (lower is better):

* energy - every kWh costs 1;
* food safety - every degC*hour outside a room's hard band costs 50;
* safety - every HP/LP cutout trip costs 500;
* wear - every compressor start costs 2 (short-cycling kills valve plates).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .plant import PlantState

W_ENERGY = 1.0
W_VIOLATION = 50.0
W_TRIP = 500.0
W_START = 2.0


@dataclass
class ScoreReport:
    scenario: str
    agent: str
    duration_h: float
    energy_kwh: float
    violation_degc_h: float
    safety_trips: int
    compressor_starts: int
    score: float
    llm_calls: int = 0
    llm_failures: int = 0
    latency_p50_s: float = 0.0
    latency_p95_s: float = 0.0
    tokens_in: int = 0
    tokens_cached: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    extra: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def composite(state: PlantState) -> float:
    return (
        W_ENERGY * state.energy_kwh
        + W_VIOLATION * state.violation_degc_h
        + W_TRIP * state.safety_trips
        + W_START * state.compressor_starts
    )


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    idx = min(int(q * (len(xs) - 1) + 0.5), len(xs) - 1)
    return xs[idx]


def build_report(
    scenario: str,
    agent: str,
    duration_h: float,
    state: PlantState,
    latencies_s: List[float],
    llm_stats: Dict[str, int],
) -> ScoreReport:
    haiku_in = llm_stats.get("tokens_in", 0)
    haiku_cached = llm_stats.get("tokens_cached", 0)
    haiku_out = llm_stats.get("tokens_out", 0)
    # Claude Haiku 4.5: $1/MTok input, $5/MTok output, cache reads ~0.1x input
    cost = (
        haiku_in * 1.0 + haiku_cached * 0.1 + haiku_out * 5.0
    ) / 1_000_000.0
    return ScoreReport(
        scenario=scenario,
        agent=agent,
        duration_h=duration_h,
        energy_kwh=round(state.energy_kwh, 2),
        violation_degc_h=round(state.violation_degc_h, 3),
        safety_trips=state.safety_trips,
        compressor_starts=state.compressor_starts,
        score=round(composite(state), 2),
        llm_calls=llm_stats.get("calls", 0),
        llm_failures=llm_stats.get("failures", 0),
        latency_p50_s=round(_percentile(latencies_s, 0.50), 3),
        latency_p95_s=round(_percentile(latencies_s, 0.95), 3),
        tokens_in=haiku_in,
        tokens_cached=haiku_cached,
        tokens_out=haiku_out,
        cost_usd=round(cost, 4),
    )
