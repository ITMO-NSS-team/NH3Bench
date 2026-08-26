# -*- coding: utf-8 -*-
"""
Валидация V4-CIHS (docs/VALIDATION.md): огибающая конденсационного удара
против имеющихся опубликованных данных.

Свип модели condensation_shock по сетке условий (давление змеевика в оттайке ×
температура подачи) на геометрии ВО-3 из конфигурации. Точки (скорость столба →
пик давления) сравниваются с тем, что доступно без покупки отчётов:

  * полевой диапазон разрушающих ударов, цитируемый CSB по авариям промышленного
    холода: 100...700 бар (Safety Bulletin 2010-13-A-AL и обзоры IIAR);
  * пиковое значение ~4000 psia (276 бар), измеренное/рассчитанное для клапана
    горячего пара варочного котла (ASME J. Pressure Vessel Technol. 145(4), 2023);
  * теоретическая прямая Жуковского rho*a*v с адиабатическим K_s из NIST --
    после исправления K модель обязана лечь на неё тождественно.

Запуск:  python tests/validate_shock.py
Итог:    results/validation/shock_envelope.json + .png
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

# Полевые ориентиры (см. модульный докстринг).
FIELD_LO, FIELD_HI = 100.0, 700.0        # бар, диапазон CSB
ASME_2023_BAR = 275.8                    # 4000 psia
MILLARD_COIL_BAR_RANGE = (8.0, 11.0)     # давление горячего пара в оттайке


def main():
    ev = DEFAULT.evaporators[2]          # ВО-3 — сценарная геометрия S1
    rows = []
    # Сетка: давление змеевика 4...12 бар изб. пара оттайки, подача -40...-28 C
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
                T_metal=pr.Tsat(P_coil) + 30.0,      # прогретый металл
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

    # Тождество Жуковского с NIST-свойствами при -40 C (референсная прямая).
    P40 = float(pr.Psat(233.15))
    rho40, K40 = float(pr.rho_l(P40)), float(pr.K_liq(P40))
    a40 = wave_speed(DEFAULT.evaporators[2].pipe_D,
                     DEFAULT.evaporators[2].pipe_wall, rho40, K40)
    vv = np.linspace(0, v.max() * 1.05, 50)
    jouk = rho40 * a40 * vv / 1e5

    # Миллардовский коридор условий (оттайка 8-11 бар, подача -40 C)
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

    # Рисунок: точки модели, прямая Жуковского, полевые ориентиры.
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
