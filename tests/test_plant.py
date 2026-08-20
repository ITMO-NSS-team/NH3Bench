import os

os.environ["NH3BENCH_NO_COOLPROP"] = "1"

from nh3bench.plant import ControlAction, Plant
from nh3bench.runner import run_episode
from nh3bench.baseline import ThermostatBaseline
from nh3bench.scenarios import SCENARIOS, Scenario


def _idle_action(plant):
    return ControlAction(
        compressor_capacity=[0.0] * len(plant.cfg.compressors),
        room_valves={r.name: False for r in plant.cfg.rooms},
        condenser_fan=0.2,
    )


def test_rooms_warm_up_without_cooling():
    plant = Plant()
    t0 = {n: r.temp_c for n, r in plant.state.rooms.items()}
    action = _idle_action(plant)
    for _ in range(720):  # 1 h
        plant.step(action, 5.0, ambient_c=28.0)
    for name, rs in plant.state.rooms.items():
        assert rs.temp_c > t0[name], f"{name} did not warm up"
    assert plant.state.energy_kwh >= 0.0


def test_cooling_pulls_freezer_down_and_uses_energy():
    plant = Plant()
    plant.state.rooms["freezer"].temp_c += 3.0
    # single suction level: cool the freezer alone so the suction pressure
    # can float low enough (warm rooms open would starve it - by design)
    action = ControlAction(
        compressor_capacity=[1.0, 0.0, 0.0],
        room_valves={"freezer": True, "chill": False, "processing": False},
        condenser_fan=0.8,
    )
    t0 = plant.state.rooms["freezer"].temp_c
    for _ in range(720):  # 1 h
        plant.step(action, 5.0, ambient_c=25.0)
    assert plant.state.rooms["freezer"].temp_c < t0
    assert plant.state.energy_kwh > 5.0
    # suction pressure must stay in a physically sane window
    assert 25.0 <= plant.state.p_suction_kpa <= 600.0


def test_lp_cutout_trips_compressors():
    plant = Plant()
    # compressors on with all valves closed -> suction collapses -> LP trip
    action = ControlAction(
        compressor_capacity=[1.0, 1.0, 1.0],
        room_valves={r.name: False for r in plant.cfg.rooms},
        condenser_fan=0.8,
    )
    for _ in range(720):
        plant.step(action, 5.0, ambient_c=25.0)
        if plant.state.safety_trips:
            break
    assert plant.state.safety_trips >= 1
    assert all(c.capacity == 0.0 for c in plant.state.compressors)


def test_hp_cutout_on_dead_condenser_fan():
    plant = Plant()
    plant.set_condenser_fouling(0.6)
    action = ControlAction(
        compressor_capacity=[1.0, 1.0, 1.0],
        room_valves={r.name: True for r in plant.cfg.rooms},
        condenser_fan=0.0,  # plant model floors fan effect at 0.05
    )
    tripped = False
    for _ in range(2880):  # up to 4 h
        plant.step(action, 5.0, ambient_c=36.0)
        if any("HP CUTOUT" in a for a in plant.state.alarms):
            tripped = True
            break
    assert tripped


def test_baseline_keeps_bands_on_calm_day():
    scenario = Scenario(
        name="calm",
        description="no events",
        duration_h=4.0,
        ambient_c=lambda t: 22.0,
        events=[],
    )
    report = run_episode(scenario, ThermostatBaseline(), hours=4.0)
    assert report.safety_trips == 0
    assert report.violation_degc_h < 1.0
    assert report.energy_kwh > 10.0


def test_all_registered_scenarios_run_with_baseline():
    for scenario in SCENARIOS.values():
        report = run_episode(scenario, ThermostatBaseline(), hours=1.0)
        assert report.score >= 0.0
