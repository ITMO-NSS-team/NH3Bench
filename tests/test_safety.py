import os

os.environ["NH3BENCH_NO_COOLPROP"] = "1"

from nh3bench.plant import ControlAction, Plant
from nh3bench.safety import apply_safety


def _full_action(plant, **kw):
    action = ControlAction(
        compressor_capacity=[1.0] * len(plant.cfg.compressors),
        room_valves={r.name: True for r in plant.cfg.rooms},
        condenser_fan=0.5,
    )
    for k, v in kw.items():
        setattr(action, k, v)
    return action


def test_min_off_time_blocks_restart():
    plant = Plant()
    cst = plant.state.compressors[0]
    cst.capacity = 0.0
    cst.since_stop_s = 10.0  # just stopped
    clamped, overrides = apply_safety(_full_action(plant), plant.state, plant.cfg)
    assert clamped.compressor_capacity[0] == 0.0
    assert any("min off time" in o for o in overrides)


def test_min_run_time_blocks_stop():
    plant = Plant()
    cst = plant.state.compressors[0]
    cst.capacity = 1.0
    cst.since_start_s = 10.0  # just started
    action = _full_action(plant, compressor_capacity=[0.0, 0.0, 0.0])
    clamped, overrides = apply_safety(action, plant.state, plant.cfg)
    assert clamped.compressor_capacity[0] == 1.0
    assert any("min run time" in o for o in overrides)


def test_overcooled_room_valve_forced_closed():
    plant = Plant()
    plant.state.rooms["chill"].temp_c = plant.cfg.rooms[1].band_lo_c - 0.5
    clamped, overrides = apply_safety(_full_action(plant), plant.state, plant.cfg)
    assert clamped.room_valves["chill"] is False
    assert any("forced closed" in o for o in overrides)


def test_defrost_interval_enforced():
    plant = Plant()
    plant.state.rooms["freezer"].since_defrost_s = 600.0
    action = _full_action(plant, start_defrost=["freezer"])
    clamped, overrides = apply_safety(action, plant.state, plant.cfg)
    assert clamped.start_defrost == []
    assert any("defrost refused" in o for o in overrides)


def test_fan_floor_with_compressors_running():
    plant = Plant()
    for c in plant.state.compressors:
        c.since_stop_s = 1e9
    action = _full_action(plant, condenser_fan=0.0)
    clamped, overrides = apply_safety(action, plant.state, plant.cfg)
    assert clamped.condenser_fan >= 0.15
    assert any("condenser fan raised" in o for o in overrides)


def test_fixed_compressor_rounded_to_binary():
    plant = Plant()
    for c in plant.state.compressors:
        c.since_stop_s = 1e9
    action = _full_action(plant, compressor_capacity=[0.7, 0.3, 0.6])
    clamped, _ = apply_safety(action, plant.state, plant.cfg)
    assert clamped.compressor_capacity[0] == 1.0  # fixed, >= 0.5 -> on
    assert clamped.compressor_capacity[1] == 0.0  # fixed, < 0.5 -> off
    assert clamped.compressor_capacity[2] == 0.6  # variable stays continuous
