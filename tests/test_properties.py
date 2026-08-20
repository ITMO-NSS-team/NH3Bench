import os

os.environ["NH3BENCH_NO_COOLPROP"] = "1"

from nh3bench import properties as props


def test_psat_known_points():
    # NH3 saturation: 0 C -> 429.4 kPa, -20 C -> 190.2 kPa (IIR tables)
    assert abs(props.psat_kpa(0.0) - 429.4) / 429.4 < 0.02
    assert abs(props.psat_kpa(-20.0) - 190.2) / 190.2 < 0.02


def test_tsat_roundtrip():
    for t in (-35.0, -18.0, -5.0, 12.0, 33.0):
        assert abs(props.tsat_c(props.psat_kpa(t)) - t) < 0.2


def test_h_fg_monotone_decreasing():
    assert props.h_fg_kj_kg(-30.0) > props.h_fg_kj_kg(0.0) > props.h_fg_kj_kg(30.0)
    assert 1000.0 < props.h_fg_kj_kg(0.0) < 1500.0


def test_rho_vapor_increases_with_temp():
    assert props.rho_vapor_kg_m3(-30.0) < props.rho_vapor_kg_m3(0.0)
    assert abs(props.rho_vapor_kg_m3(0.0) - 3.457) / 3.457 < 0.05
