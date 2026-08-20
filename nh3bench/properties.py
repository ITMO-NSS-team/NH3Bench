"""Saturation properties of ammonia (R717).

Tabulated saturation data (IIR reference tables, rounded) with interpolation:
pressure is interpolated log-linearly in temperature, everything else linearly.
Accuracy within the -50..+50 C range is ~1-2 % against REFPROP, which is far
below the modelling error of the lumped plant model itself.

If CoolProp is installed it is used instead of the table (set
``NH3BENCH_NO_COOLPROP=1`` to force the table).
"""

from __future__ import annotations

import bisect
import math
import os

# T (degC), Psat (kPa), h_fg (kJ/kg), rho_vapor (kg/m3)
_SAT_TABLE = [
    (-50.0, 40.9, 1416.0, 0.381),
    (-40.0, 71.7, 1390.0, 0.644),
    (-30.0, 119.5, 1360.0, 1.037),
    (-20.0, 190.2, 1329.0, 1.604),
    (-10.0, 290.9, 1297.0, 2.391),
    (0.0, 429.4, 1262.0, 3.457),
    (10.0, 615.2, 1226.0, 4.868),
    (20.0, 857.5, 1187.0, 6.703),
    (30.0, 1167.0, 1145.0, 9.045),
    (40.0, 1555.0, 1099.0, 12.03),
    (50.0, 2033.0, 1046.0, 15.78),
]

_T = [row[0] for row in _SAT_TABLE]
_LOGP = [math.log(row[1]) for row in _SAT_TABLE]
_HFG = [row[2] for row in _SAT_TABLE]
_RHOV = [row[3] for row in _SAT_TABLE]

_coolprop = None
if not os.environ.get("NH3BENCH_NO_COOLPROP"):
    try:  # pragma: no cover - optional dependency
        from CoolProp.CoolProp import PropsSI as _coolprop  # type: ignore
    except ImportError:
        _coolprop = None


def _clamp_t(t_c: float) -> float:
    return min(max(t_c, _T[0]), _T[-1])


def _interp(t_c: float, ys: list) -> float:
    t_c = _clamp_t(t_c)
    i = min(max(bisect.bisect_right(_T, t_c) - 1, 0), len(_T) - 2)
    frac = (t_c - _T[i]) / (_T[i + 1] - _T[i])
    return ys[i] + frac * (ys[i + 1] - ys[i])


def psat_kpa(t_c: float) -> float:
    """Saturation pressure of NH3, kPa."""
    if _coolprop is not None:  # pragma: no cover
        return _coolprop("P", "T", t_c + 273.15, "Q", 1, "Ammonia") / 1000.0
    return math.exp(_interp(t_c, _LOGP))


def tsat_c(p_kpa: float) -> float:
    """Saturation temperature of NH3 at pressure ``p_kpa``, degC."""
    if _coolprop is not None:  # pragma: no cover
        return _coolprop("T", "P", p_kpa * 1000.0, "Q", 1, "Ammonia") - 273.15
    logp = math.log(min(max(p_kpa, math.exp(_LOGP[0])), math.exp(_LOGP[-1])))
    i = min(max(bisect.bisect_right(_LOGP, logp) - 1, 0), len(_LOGP) - 2)
    frac = (logp - _LOGP[i]) / (_LOGP[i + 1] - _LOGP[i])
    return _T[i] + frac * (_T[i + 1] - _T[i])


def h_fg_kj_kg(t_c: float) -> float:
    """Latent heat of vaporisation of NH3, kJ/kg."""
    if _coolprop is not None:  # pragma: no cover
        t_k = t_c + 273.15
        return (
            _coolprop("H", "T", t_k, "Q", 1, "Ammonia")
            - _coolprop("H", "T", t_k, "Q", 0, "Ammonia")
        ) / 1000.0
    return _interp(t_c, _HFG)


def rho_vapor_kg_m3(t_c: float) -> float:
    """Saturated-vapour density of NH3, kg/m3."""
    if _coolprop is not None:  # pragma: no cover
        return _coolprop("D", "T", t_c + 273.15, "Q", 1, "Ammonia")
    return _interp(t_c, _RHOV)
