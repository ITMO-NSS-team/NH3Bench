"""
Ammonia (R717) properties, tabulated against pressure.

Why: a direct CoolProp.PropsSI call costs about 110 us. At dt = 0.5 s
and a requirement of 200x real time the twin needs about 50 thousand
property lookups per second of wall time. Tabulation plus numpy
interpolation gives about 0.5 us, i.e. a margin of more than 200-fold.

Accuracy: linear interpolation on a logarithmic pressure grid of 400
nodes over the range 0.3...25 bar gives an error below 0.05 % for every
quantity (checked in tests/test_props.py).

Everything is in SI: Pa, K, kg/m3, J/kg, J/(kg*K).
"""

from __future__ import annotations

import os
import numpy as np

_CACHE = os.path.join(os.path.dirname(__file__), "_nh3_table.npz")

# Table bounds.
P_MIN = 0.30e5     # ~ -50 C
P_MAX = 25.0e5     # ~ +58 C, above the design pressure of the HP side
N_GRID = 400

FLUID = "Ammonia"


def _build_table() -> dict:
    import CoolProp.CoolProp as CP

    P = np.geomspace(P_MIN, P_MAX, N_GRID)
    cols = {"P": P}
    for name, (out, q) in {
        "Tsat":  ("T", 0),
        "rho_l": ("D", 0),
        "rho_v": ("D", 1),
        "h_l":   ("H", 0),
        "h_v":   ("H", 1),
        "s_l":   ("S", 0),
        "s_v":   ("S", 1),
        "cp_l":  ("C", 0),
        "cp_v":  ("C", 1),
        "mu_l":  ("V", 0),
        "k_l":   ("L", 0),
    }.items():
        cols[name] = np.array([CP.PropsSI(out, "P", float(p), "Q", q, FLUID) for p in P])

    # Internal energy: u = h - P/rho
    cols["u_l"] = cols["h_l"] - P / cols["rho_l"]
    cols["u_v"] = cols["h_v"] - P / cols["rho_v"]
    cols["h_fg"] = cols["h_v"] - cols["h_l"]

    # Effective heat capacity of superheated vapour: cp is averaged over 30 K
    # of superheat.
    cpv_sh = []
    for p in P:
        Ts = CP.PropsSI("T", "P", float(p), "Q", 1, FLUID)
        h1 = CP.PropsSI("H", "P", float(p), "T", Ts + 1.0, FLUID)
        h2 = CP.PropsSI("H", "P", float(p), "T", Ts + 31.0, FLUID)
        cpv_sh.append((h2 - h1) / 30.0)
    cols["cp_v_sh"] = np.array(cpv_sh)

    # Speed of sound in the saturated liquid: it gives the ADIABATIC bulk
    # modulus K_s = rho*a^2 for the hydraulic-shock computation. Validation V1
    # showed that the previous constant of 1.03 GPa was the isothermal modulus
    # (K_T at -10 C) and underestimated the product rho*a by 16...37 %.
    cols["a_l"] = np.array(
        [CP.PropsSI("A", "P", float(p), "Q", 0, FLUID) for p in P])

    # Density exponent for superheated vapour: rho = rho_v*(Tsat/T)^n. n = 1 is
    # an ideal gas; real vapour at condensing pressures is more compressible (Z
    # grows with superheat), n ~ 1.2...1.5. Fitting at a point with 40 K of
    # superheat removes the error of up to 9 % in the hot-gas corner that
    # validation V1 found.
    n_sh = []
    for p in P:
        Ts = CP.PropsSI("T", "P", float(p), "Q", 1, FLUID)
        rv = CP.PropsSI("D", "P", float(p), "Q", 1, FLUID)
        T2 = Ts + 40.0
        rho2 = CP.PropsSI("D", "P", float(p), "T", T2, FLUID)
        n_sh.append(float(np.log(rv / rho2) / np.log(T2 / Ts)))
    cols["n_rho_sh"] = np.array(n_sh)

    return cols


def _load() -> dict:
    if os.path.exists(_CACHE):
        with np.load(_CACHE) as z:
            tab = {k: z[k] for k in z.files}
        # A table from an older version without the new columns is rebuilt
        # (this needs CoolProp; a fresh npz is committed, so this branch does
        # not fire for users).
        if "a_l" in tab and "n_rho_sh" in tab:
            return tab
    tab = _build_table()
    np.savez_compressed(_CACHE, **tab)
    return tab


_T = _load()
_P = _T["P"]
_LOGP = np.log(_P)

# The grid is uniform in log(P), so the node index is computed analytically: no
# search is needed and interpolation becomes O(1) arithmetic.
_LOG_LO = float(_LOGP[0])
_DLOG = float(_LOGP[1] - _LOGP[0])
_INV_DLOG = 1.0 / _DLOG
_NMAX = N_GRID - 2

import math as _math


def _interp(col: str, P):
    """Linear interpolation in log(P). Extrapolation is clamped at the edges.
    """
    tab = _T[col]
    if isinstance(P, (float, int)):
        # Fast scalar path: about 0.35 us.
        if P < P_MIN:
            P = P_MIN
        elif P > P_MAX:
            P = P_MAX
        pos = (_math.log(P) - _LOG_LO) * _INV_DLOG
        i = int(pos)
        if i < 0:
            i = 0
        elif i > _NMAX:
            i = _NMAX
        f = pos - i
        a = tab[i]
        return a + (tab[i + 1] - a) * f
    return np.interp(np.log(np.clip(P, P_MIN, P_MAX)), _LOGP, tab)


# --- Saturation: functions of pressure ------------------------------------

def Tsat(P):   return _interp("Tsat", P)
def rho_l(P):  return _interp("rho_l", P)
def rho_v(P):  return _interp("rho_v", P)
def h_l(P):    return _interp("h_l", P)
def h_v(P):    return _interp("h_v", P)
def u_l(P):    return _interp("u_l", P)
def u_v(P):    return _interp("u_v", P)
def s_l(P):    return _interp("s_l", P)
def s_v(P):    return _interp("s_v", P)
def h_fg(P):   return _interp("h_fg", P)
def cp_l(P):   return _interp("cp_l", P)
def cp_v(P):   return _interp("cp_v_sh", P)
def a_l(P):    return _interp("a_l", P)


def K_liq(P):
    """
    Adiabatic bulk modulus of the saturated liquid, K_s = rho*a^2.

    It is what sets the speed of a compression wave in a hydraulic shock.
    The isothermal modulus (1.0...1.4 GPa) does not apply here: the wave is
    a fast adiabatic process; the error was found by validation against
    CoolProp (docs/VALIDATION.md).
    """
    a = _interp("a_l", P)
    return _interp("rho_l", P) * a * a


def Psat(T):
    """The inverse function: saturation pressure from temperature."""
    return np.exp(np.interp(T, _T["Tsat"], _LOGP))


# --- Superheated vapour ---------------------------------------------------
# Model: h(P,T) = h_v(P) + cp_v(P) * (T - Tsat(P)). For superheats up to about
# 80 K the error is below 1.5 %, which is enough for the plant's energy balance
# and entirely enough for the purposes of the benchmark.

def h_vap(P, T):
    return h_v(P) + cp_v(P) * (T - Tsat(P))


def T_vap(P, h):
    return Tsat(P) + (h - h_v(P)) / cp_v(P)


def s_vap(P, T):
    return s_v(P) + cp_v(P) * np.log(np.maximum(T, 1.0) / Tsat(P))


def rho_vap(P, T):
    """
    Density of superheated vapour: rho_v(P) * (Tsat/T)^n(P).

    The exponent n is tabulated from CoolProp (n = 1 is an ideal gas; real
    vapour at condensing pressures gives n up to about 1.5). The earlier
    model with n = 1 overestimated the density by up to 9 % at 12 bar and
    80 K of superheat.
    """
    return rho_v(P) * (Tsat(P) / np.maximum(T, 1.0)) ** _interp("n_rho_sh", P)


def h_isentropic(P1, T1, P2):
    """Enthalpy after isentropic compression from (P1,T1) to P2."""
    s1 = s_vap(P1, T1)
    T2s = Tsat(P2) * np.exp((s1 - s_v(P2)) / cp_v(P2))
    return h_v(P2) + cp_v(P2) * (T2s - Tsat(P2))


# --- Two-phase vessel -----------------------------------------------------
# The problem: given mass M, internal energy U and volume V, find the pressure.
# The monotone equation f(P) = V_calc(P) - V = 0 is solved.

_VESSEL_P_LO = P_MIN * 1.001
_VESSEL_P_HI = P_MAX * 0.999


def vessel_pressure(M: float, U: float, V: float,
                    P_guess: float = 3.0e5, tol: float = 1.0) -> tuple:
    """
    Pressure and vapour quality of a two-phase vessel.

    Returns (P, x, M_liq, M_vap). The method is Brent in log(P) on the
    monotone volume residual. Typically 12-18 iterations, about 15 us.
    """
    if M <= 1e-9:
        return P_guess, 1.0, 0.0, 0.0

    u = U / M

    def resid(P):
        ul = _interp("u_l", P)
        uv = _interp("u_v", P)
        x = (u - ul) / max(uv - ul, 1.0)
        if x < 0.0:
            x = 0.0
        elif x > 1.0:
            x = 1.0
        return (1.0 - x) * M / _interp("rho_l", P) + x * M / _interp("rho_v", P) - V

    # Secant from the previous step's hint: usually 3-5 iterations.
    p0 = min(max(P_guess, _VESSEL_P_LO), _VESSEL_P_HI)
    p1 = min(max(p0 * 1.02, _VESSEL_P_LO), _VESSEL_P_HI)
    f0, f1 = resid(p0), resid(p1)
    converged = False
    for _ in range(20):
        d = f1 - f0
        if abs(d) < 1e-12:
            break
        p2 = p1 - f1 * (p1 - p0) / d
        if not (_VESSEL_P_LO < p2 < _VESSEL_P_HI) or not _math.isfinite(p2):
            break
        p0, f0 = p1, f1
        p1, f1 = p2, resid(p2)
        if abs(p1 - p0) < tol:
            converged = True
            break

    if not converged:
        # Fallback to bisection in log(P) -- reliable, but slower.
        lo, hi = _VESSEL_P_LO, _VESSEL_P_HI
        f_lo, f_hi = resid(lo), resid(hi)
        if f_lo * f_hi > 0:
            p1 = hi if abs(f_hi) < abs(f_lo) else lo
        else:
            for _ in range(50):
                mid = _math.sqrt(lo * hi)
                if hi - lo < tol:
                    break
                if f_lo * resid(mid) <= 0:
                    hi = mid
                else:
                    lo, f_lo = mid, resid(mid)
            p1 = _math.sqrt(lo * hi)

    P = float(min(max(p1, _VESSEL_P_LO), _VESSEL_P_HI))
    ul, uv = _interp("u_l", P), _interp("u_v", P)
    x = min(max((u - ul) / max(uv - ul, 1.0), 0.0), 1.0)
    return P, float(x), (1 - x) * M, x * M


# --- Miscellaneous --------------------------------------------------------

# The historical wave-speed constant (1150 m/s) has been removed: it came from
# the isothermal bulk modulus. The current wave speed is computed through
# K_liq(P) and the Korteweg correction in piping.wave_speed.
M_MOL = 0.017031                   # kg/mol
R_SPEC = 8.314462 / M_MOL          # J/(kg*K)

# Toxicity thresholds, ppm (volume fractions * 1e6)
TLV_TWA = 25.0
STEL = 35.0
IDLH = 300.0
ERPG_2 = 150.0
LFL_VOL = 0.15      # lower flammability limit
UFL_VOL = 0.28


def ppm_from_kg_per_m3(c_kg_m3: float, T: float = 293.15, P: float = 101325.0) -> float:
    """Conversion of a mass concentration into ppm by volume."""
    rho_air = P / (287.05 * T)
    return 1e6 * (c_kg_m3 / rho_air) * (28.96 / 17.031)
