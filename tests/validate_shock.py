# -*- coding: utf-8 -*-
"""
Validation V4-CIHS (docs/VALIDATION.md): the envelope of
condensation-induced shock against the published data available.

A sweep of the condensation_shock model over a grid of conditions
(defrost coil pressure x feed temperature) on the EV-03 geometry from
the configuration. The points (column velocity -> pressure peak) are
compared with what is available without buying reports:

  * the field range of destructive shocks cited by the CSB for
    industrial refrigeration accidents: 100...700 bar (Safety Bulletin
    2010-13-A-AL and IIAR reviews);
  * a peak value of about 4000 psia (276 bar), measured/computed for a
    hot-gas valve of a cooking kettle (ASME J. Pressure Vessel Technol.
    145(4), 2023);
  * the theoretical Joukowsky line rho*a*v with the adiabatic K_s from
    NIST -- after the K fix the model must lie on it identically.

Usage:  python tests/validate_shock.py
Result: results/validation/shock_envelope.json plus .png
"""

import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from nh3twin import props as pr
from nh3twin.piping import (PipeSegment, condensation_shock, wave_speed,
                            SHOCK_PRESSURE_RATIO)
from nh3twin.config import DEFAULT

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results", "validation")
os.makedirs(OUT_DIR, exist_ok=True)

# Field reference points (see the module docstring).
FIELD_LO, FIELD_HI = 100.0, 700.0        # bar, the CSB range
ASME_2023_BAR = 275.8                    # 4000 psia
MILLARD_COIL_BAR_RANGE = (8.0, 11.0)     # hot-gas pressure during defrost


def main():
    ev = DEFAULT.evaporators[2]          # EV-03 -- the geometry of scenario S1
    rows = []
    # Grid: coil pressure 4...12 bar gauge of defrost vapour, feed -40...-28 C
    for P_coil_bar in np.linspace(4.0, 12.0, 9):
        for T_feed_C in (-40.0, -36.0, -32.0, -28.0):
            P_feed = float(pr.Psat(273.15 + T_feed_C))
            P_coil = P_coil_bar * 1e5
            if P_coil <= P_feed * SHOCK_PRESSURE_RATIO:
                continue
            seg = PipeSegment(tag="PIPE-EV", D=ev.pipe_D, L=ev.pipe_L,
                              wall=ev.pipe_wall, sigma_y=ev.pipe_sigma_y)
            res = condensation_shock(
                seg, P_coil=P_coil, P_feed=P_feed,
                T_metal=pr.Tsat(P_coil) + 30.0,      # warmed metal
                m_liq_in_rate=0.5, dt=0.5)
            if res["dv"] <= 0:
                continue
            rows.append({"P_coil_bar": float(P_coil_bar),
                         "T_feed_C": T_feed_C,
                         "v_ms": float(res["dv"]),
                         "P_peak_bar": float(res["P_peak"] / 1e5),
                         "dP_j_bar": float((res["P_peak"] - P_coil) / 1e5)})

    v = np.array([r["v_ms"] for r in rows])
    pk = np.array([r["P_peak_bar"] for r in rows])

    # The Joukowsky identity with NIST properties at -40 C (the reference
    # line).
    P40 = float(pr.Psat(233.15))
    rho40, K40 = float(pr.rho_l(P40)), float(pr.K_liq(P40))
    a40 = wave_speed(DEFAULT.evaporators[2].pipe_D,
                     DEFAULT.evaporators[2].pipe_wall, rho40, K40)
    vv = np.linspace(0, v.max() * 1.05, 50)
    jouk = rho40 * a40 * vv / 1e5

    # The Millard corridor of conditions (defrost 8-11 bar, feed -40 C)
    mill = [r for r in rows if MILLARD_COIL_BAR_RANGE[0] <= r["P_coil_bar"]
            <= MILLARD_COIL_BAR_RANGE[1] and r["T_feed_C"] == -40.0]

    in_env = [r for r in mill if FIELD_LO <= r["P_peak_bar"] <= FIELD_HI]
    report = {
        "n_points": len(rows),
        "peak_range_bar": [float(pk.min()), float(pk.max())],
        "v_range_ms": [float(v.min()), float(v.max())],
        "wave_speed_minus40": a40,
        "millard_corridor_peaks_bar": sorted(round(r["P_peak_bar"], 1)
                                             for r in mill),
        "field_envelope_bar": [FIELD_LO, FIELD_HI],
        "asme2023_bar": ASME_2023_BAR,
        "millard_in_envelope": f"{len(in_env)}/{len(mill)}",
        "verdict": bool(mill) and len(in_env) == len(mill),
        "rows": rows,
    }

    # Figure: the model points, the Joukowsky line, the field reference points.
    fig, ax = plt.subplots(figsize=(7, 4.6))
    ax.axhspan(FIELD_LO, FIELD_HI, color="#f2c1a0", alpha=0.35,
               label="полевой диапазон CSB (100–700 бар)")
    ax.axhline(ASME_2023_BAR, color="#a05f2c", ls="--", lw=1,
               label="ASME PVT 2023 (~276 бар)")
    ax.plot(vv, jouk, color="#5a7a94", lw=1.2,
            label=f"Жуковского ρ·a·v (NIST, −40 °C, a={a40:.0f} м/с)")
    sc = ax.scatter(v, pk, c=[r["P_coil_bar"] for r in rows], cmap="viridis",
                    s=26, zorder=3, label="модель: свип условий")
    fig.colorbar(sc, ax=ax, label="Р змеевика, бар")
    ax.set_xlabel("скорость столба жидкости, м/с")
    ax.set_ylabel("пик давления, бар")
    ax.set_title("Конденсационный удар: модель против имеющихся данных")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    png = os.path.join(OUT_DIR, "shock_envelope.png")
    fig.savefig(png, dpi=150)

    with open(os.path.join(OUT_DIR, "shock_envelope.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print(f"точек: {len(rows)}; пики {pk.min():.0f}…{pk.max():.0f} бар "
          f"при v {v.min():.0f}…{v.max():.0f} м/с")
    print(f"миллардовский коридор (8-11 бар, -40 C): "
          f"{report['millard_corridor_peaks_bar']} бар; "
          f"в полевой огибающей {report['millard_in_envelope']}")
    print("ВЕРДИКТ:", "OK" if report["verdict"] else "ПРОВАЛ")
    print("записано:", png)


if __name__ == "__main__":
    main()
