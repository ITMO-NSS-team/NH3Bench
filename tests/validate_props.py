# -*- coding: utf-8 -*-
"""
Validation V1 (docs/VALIDATION.md): the properties of
nh3twin/props.py against CoolProp.

CoolProp implements the Tillner-Roth & Baehr equation of state for
ammonia -- an independent physical model; the twin sees only a table of
400 nodes. What is checked is the interpolation BETWEEN nodes, the
linearization of superheated vapour and isentropic compression.

Usage:  python tests/validate_props.py
Result: results/validation/props.json plus a table in stdout.
Requires CoolProp (needed only for validation and for rebuilding the
table).
"""

import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from nh3twin import props as pr
import CoolProp.CoolProp as CP

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results", "validation")
os.makedirs(OUT_DIR, exist_ok=True)

FLUID = "Ammonia"


def rel(a, b, scale=None):
    """
    Relative error; scale sets the denominator for quantities that pass
    through zero (enthalpies are counted in fractions of h_fg).
    """
    d = np.abs(np.asarray(a) - np.asarray(b))
    s = np.abs(np.asarray(scale if scale is not None else b))
    return d / np.maximum(s, 1e-12)


def main():
    report = {}

    # -- 1. Saturation: 2000 pressures away from the grid nodes ----------
    P = np.geomspace(pr.P_MIN * 1.02, pr.P_MAX * 0.98, 2000)
    hfg_ref = np.array([CP.PropsSI("H", "P", p, "Q", 1, FLUID)
                        - CP.PropsSI("H", "P", p, "Q", 0, FLUID) for p in P])

    def sat_ref(key, q):
        return np.array([CP.PropsSI(key, "P", p, "Q", q, FLUID) for p in P])

    checks = {
        "Tsat":  (pr.Tsat(P),  sat_ref("T", 0), None),
        "rho_l": (pr.rho_l(P), sat_ref("D", 0), None),
        "rho_v": (pr.rho_v(P), sat_ref("D", 1), None),
        "h_l":   (pr.h_l(P),   sat_ref("H", 0), hfg_ref),
        "h_v":   (pr.h_v(P),   sat_ref("H", 1), hfg_ref),
        "u_l":   (pr.u_l(P),   sat_ref("U", 0), hfg_ref),
        "u_v":   (pr.u_v(P),   sat_ref("U", 1), hfg_ref),
        "s_l":   (pr.s_l(P),   sat_ref("S", 0), sat_ref("S", 1)),
        "s_v":   (pr.s_v(P),   sat_ref("S", 1), None),
        "h_fg":  (pr.h_fg(P),  hfg_ref, None),
        "cp_l":  (pr.cp_l(P),  sat_ref("C", 0), None),
    }
    sat = {}
    print(f"{'колонка':8}{'max, %':>10}{'сред., %':>10}")
    for name, (tw, ref, sc) in checks.items():
        e = rel(tw, ref, sc)
        sat[name] = {"max_pct": float(100 * e.max()),
                     "mean_pct": float(100 * e.mean())}
        print(f"{name:8}{100 * e.max():10.4f}{100 * e.mean():10.4f}")
    report["saturation"] = sat

    # -- 2. Superheated vapour: cp linearization against CoolProp ---------
    print("\nПерегрев (h_vap / rho_vap / s_vap), погрешность %:")
    sh_rows = []
    for P1 in (0.72e5, 2.0e5, 5.0e5, 12.0e5):
        Ts = float(pr.Tsat(P1))
        for dT in (5, 20, 40, 60, 80):
            T = Ts + dT
            eh = rel(pr.h_vap(P1, T), CP.PropsSI("H", "P", P1, "T", T, FLUID),
                     CP.PropsSI("H", "P", P1, "Q", 1, FLUID)
                     - CP.PropsSI("H", "P", P1, "Q", 0, FLUID))
            er = rel(pr.rho_vap(P1, T), CP.PropsSI("D", "P", P1, "T", T, FLUID))
            es = rel(pr.s_vap(P1, T), CP.PropsSI("S", "P", P1, "T", T, FLUID))
            sh_rows.append({"P_bar": P1 / 1e5, "dT_K": dT,
                            "h_pct": float(100 * eh), "rho_pct": float(100 * er),
                            "s_pct": float(100 * es)})
    worst = max(sh_rows, key=lambda r: max(r["h_pct"], r["rho_pct"]))
    print(f"  худшая точка: P={worst['P_bar']:.1f} бар, ΔT={worst['dT_K']} К: "
          f"h {worst['h_pct']:.2f} %, rho {worst['rho_pct']:.2f} %, "
          f"s {worst['s_pct']:.2f} %")
    report["superheat"] = sh_rows

    # -- 3. Isentropic compression: the working pressure ratios ----------
    print("\nИзоэнтропное сжатие, погрешность Δh, %:")
    is_rows = []
    for P1, P2 in ((0.72e5, 3.0e5), (2.0e5, 11.0e5), (3.0e5, 14.0e5)):
        T1 = float(pr.Tsat(P1)) + 5.0
        h1 = CP.PropsSI("H", "P", P1, "T", T1, FLUID)
        s1 = CP.PropsSI("S", "P", P1, "T", T1, FLUID)
        h2_ref = CP.PropsSI("H", "P", P2, "S", s1, FLUID)
        h2_tw = pr.h_isentropic(P1, T1, P2)
        e = rel(h2_tw - pr.h_vap(P1, T1), h2_ref - h1)
        is_rows.append({"P1_bar": P1 / 1e5, "P2_bar": P2 / 1e5,
                        "dh_pct": float(100 * e)})
        print(f"  {P1/1e5:5.2f} → {P2/1e5:5.2f} бар: {100 * e:6.2f}")
    report["isentropic"] = is_rows

    # -- 4. Wave speed for hydraulic shock: K from the equation of state --
    # Historically wave_speed took K = 1.03 GPa -- the isothermal modulus (K_T
    # at -10 °C). A compression wave is adiabatic: K_s = rho*a^2. After the fix
    # the model must match NIST to interpolation accuracy.
    from nh3twin.piping import wave_speed
    print("\nСкорость волны (D=150 мм, стенка 5.5 мм), м/с:")
    print(f"{'T,°C':>6}{'a_NIST':>9}{'K_s,ГПа':>9}{'a_твин':>9}"
          f"{'a_NIST+Кортевег':>17}{'твин/NIST':>11}")
    ws_rows = []
    for TC in (-40, -30, -20, -10, 0):
        T = 273.15 + TC
        P1 = CP.PropsSI("P", "T", T, "Q", 0, FLUID)
        rho = CP.PropsSI("D", "T", T, "Q", 0, FLUID)
        a = CP.PropsSI("A", "T", T, "Q", 0, FLUID)
        K_s = rho * a * a
        a_tw = wave_speed(0.150, 0.0055, rho, K=float(pr.K_liq(P1)))
        a_ref = wave_speed(0.150, 0.0055, rho, K=K_s)
        ws_rows.append({"T_C": TC, "a_nist": float(a), "K_s_GPa": K_s / 1e9,
                        "a_twin": float(a_tw), "a_ref_korteweg": float(a_ref),
                        "ratio": float(a_tw / a_ref)})
        print(f"{TC:6d}{a:9.0f}{K_s/1e9:9.2f}{a_tw:9.0f}{a_ref:17.0f}"
              f"{a_tw/a_ref:10.4f}")
    report["wave_speed"] = ws_rows
    ok_ws = all(abs(r["ratio"] - 1.0) < 0.005 for r in ws_rows)

    # -- 5. Reverse consistency of Psat(Tsat(P)) -------------------------
    e_inv = rel(np.array([pr.Psat(float(pr.Tsat(p))) for p in P[::20]]), P[::20])
    report["inverse_roundtrip"] = {"max_pct": float(100 * e_inv.max())}
    print(f"\nPsat(Tsat(P)) кругорейс: max {100 * e_inv.max():.4f} %")

    # -- Verdicts against the acceptance criteria in docs/VALIDATION.md ---
    ok_sat = all(c["max_pct"] < 0.05 for c in sat.values())
    # The claim after the model was reworked (see the twin README): h and s
    # below 1.6 % over the whole range up to 80 K; density with the power
    # correction n(P) below 3 %.
    ok_sh = all(r["h_pct"] < 1.6 and r["s_pct"] < 1.6 and r["rho_pct"] < 3.0
                for r in sh_rows)
    ok_is = all(r["dh_pct"] < 2.0 for r in is_rows)
    ok_inv = report["inverse_roundtrip"]["max_pct"] < 0.05
    report["verdict"] = {"saturation": ok_sat, "superheat": ok_sh,
                         "isentropic": ok_is, "roundtrip": ok_inv,
                         "wave_speed": ok_ws}
    print("\nВЕРДИКТ: насыщение", "OK" if ok_sat else "ПРОВАЛ",
          "· перегрев", "OK" if ok_sh else "ПРОВАЛ",
          "· изоэнтропа", "OK" if ok_is else "ПРОВАЛ",
          "· кругорейс", "OK" if ok_inv else "ПРОВАЛ",
          "· волна", "OK" if ok_ws else "ПРОВАЛ")

    out = os.path.join(OUT_DIR, "props.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("записано:", out)


if __name__ == "__main__":
    main()
