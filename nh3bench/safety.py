"""Local safety layer between any controller (LLM or classic) and the plant.

An LLM controlling physical equipment must sit behind a deterministic
interlock layer: the model *proposes*, the interlocks *dispose*.  This layer
clamps every proposed action before it reaches the actuators and reports what
it overrode, so the agent can learn from the feedback on the next step.

Hard pressure cutouts additionally live inside :mod:`nh3bench.plant` itself
and fire on every physics substep - this layer only shapes *commands*.
"""

from __future__ import annotations

from typing import List, Tuple

from .plant import ControlAction, PlantConfig, PlantState

MIN_DEFROST_INTERVAL_S = 2 * 3600.0
MIN_FAN_WITH_COMPRESSORS = 0.15


def apply_safety(
    action: ControlAction, state: PlantState, cfg: PlantConfig
) -> Tuple[ControlAction, List[str]]:
    """Return a clamped copy of ``action`` and the list of overrides made."""
    overrides: List[str] = []
    caps = list(action.compressor_capacity) + [0.0] * len(cfg.compressors)
    caps = [min(max(c, 0.0), 1.0) for c in caps[: len(cfg.compressors)]]
    valves = dict(action.room_valves)
    defrost = list(action.start_defrost)
    fan = min(max(action.condenser_fan, 0.0), 1.0)

    for i, (ccfg, cst) in enumerate(zip(cfg.compressors, state.compressors)):
        want = caps[i] if ccfg.variable else (1.0 if caps[i] >= 0.5 else 0.0)
        is_on = cst.capacity > 0
        if is_on and want == 0 and cst.since_start_s < ccfg.min_run_s:
            caps[i] = cst.capacity
            overrides.append(
                f"{ccfg.name}: stop refused, min run time "
                f"({cst.since_start_s:.0f}s < {ccfg.min_run_s:.0f}s)"
            )
        elif not is_on and want > 0 and cst.since_stop_s < ccfg.min_off_s:
            caps[i] = 0.0
            overrides.append(
                f"{ccfg.name}: start refused, min off time "
                f"({cst.since_stop_s:.0f}s < {ccfg.min_off_s:.0f}s)"
            )
        elif not ccfg.variable:
            caps[i] = want
        if cst.lockout_left_s > 0 and caps[i] > 0:
            caps[i] = 0.0
            overrides.append(
                f"{ccfg.name}: in safety lockout for {cst.lockout_left_s:.0f}s more"
            )
        if cst.tripped_left_s > 0 and caps[i] > 0:
            caps[i] = 0.0
            overrides.append(f"{ccfg.name}: tripped (fault), unavailable")

    # a room already below its hard band must not be cooled further
    for rcfg in cfg.rooms:
        rs = state.rooms[rcfg.name]
        if valves.get(rcfg.name, False) and rs.temp_c <= rcfg.band_lo_c + 0.3:
            valves[rcfg.name] = False
            overrides.append(
                f"{rcfg.name}: liquid valve forced closed, room at "
                f"{rs.temp_c:.1f}C near hard minimum {rcfg.band_lo_c:.1f}C"
            )

    # defrost hygiene: not too often, not while one is running
    cleaned = []
    for name in defrost:
        rs = state.rooms.get(name)
        if rs is None:
            overrides.append(f"defrost: unknown room '{name}' ignored")
        elif rs.defrost_left_s > 0:
            overrides.append(f"{name}: defrost already running")
        elif rs.since_defrost_s < MIN_DEFROST_INTERVAL_S:
            overrides.append(
                f"{name}: defrost refused, last one "
                f"{rs.since_defrost_s / 3600.0:.1f}h ago (< 2h)"
            )
        else:
            cleaned.append(name)

    if any(c > 0 for c in caps) and fan < MIN_FAN_WITH_COMPRESSORS:
        fan = MIN_FAN_WITH_COMPRESSORS
        overrides.append(
            f"condenser fan raised to {MIN_FAN_WITH_COMPRESSORS} - "
            "compressors running"
        )

    return (
        ControlAction(
            compressor_capacity=caps,
            room_valves=valves,
            start_defrost=cleaned,
            condenser_fan=fan,
        ),
        overrides,
    )
