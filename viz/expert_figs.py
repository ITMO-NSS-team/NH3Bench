# -*- coding: utf-8 -*-
"""Charts for the expert description: a black-and-white engineering manner."""
import json, os, io, base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

D = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(D, "expert_data.json")))
FIGS = {}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10.5,
    "axes.edgecolor": "#111", "axes.labelcolor": "#111",
    "xtick.color": "#111", "ytick.color": "#111",
    "axes.grid": True, "grid.color": "#999", "grid.linewidth": 0.4,
    "grid.linestyle": ":", "figure.facecolor": "white",
    "axes.facecolor": "white", "savefig.dpi": 135,
})
K = "#111111"      # the main curve
G = "#666666"      # the second curve
R = "#8b1a1a"      # accident/limit (dark red, like a stamp)


def save(name, fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    FIGS[name] = base64.b64encode(buf.getvalue()).decode()
    print(name, round(len(FIGS[name]) / 1024), "КБ")


def izb(p_abs):
    """bar abs -> kgf/cm2 gauge"""
    return (np.asarray(p_abs) - 1.013) * 1.0197


# ================= Fig. 2: normal daily cycle =================
d = DATA["normal"]
t = np.array(d["t_h"])
fig, ax = plt.subplots(3, 1, figsize=(8.4, 6.6), sharex=True,
                       gridspec_kw={"hspace": 0.14})
ax[0].plot(t, d["T_CHILL"], color=K, lw=1.4, label="камера +2 °С")
ax[0].plot(t, d["T_LT"], color=G, lw=1.4, ls="--", label="НТ-склад −20 °С")
ax[0].plot(t, d["T_BLAST"], color=K, lw=1.0, ls=":", label="морозильная −30 °С")
ax[0].set_ylabel("t камер, °С")
ax[0].legend(loc="center left", fontsize=9, framealpha=1.0)
ax[1].plot(t, d["T_MILK"], color=K, lw=1.6, label="молоко после охладителя")
ax[1].axhline(6.0, color=R, lw=1.1, ls="--")
ax[1].text(t[3], 6.15, "граница по регламенту +6 °С", color=R, fontsize=9)
ax2 = ax[1].twinx()
ax2.plot(t, d["ICE"], color=G, lw=1.2, ls="--", label="запас льда")
ax2.set_ylabel("лёд, т", color=G)
ax2.tick_params(axis="y", labelcolor=G)
ax2.grid(False)
ax[1].set_ylabel("t молока, °С")
ax[1].legend(loc="upper left", fontsize=9, framealpha=1.0)
ax[2].plot(t, d["KW"], color=K, lw=1.2)
ax[2].set_ylabel("потребление, кВт")
ax[2].set_xlabel("время суток, ч")
ax[2].annotate("пик приёмки молока", xy=(7.0, max(d["KW"]) * 0.97),
               fontsize=9, color=K,
               xytext=(4.6, max(d["KW"]) * 0.90),
               arrowprops=dict(arrowstyle="->", color=K, lw=0.8))
save("fig_normal", fig)

# ================= Fig. 6: task 1, coil pressure =================
d = DATA["s1"]
t = np.array(d["t"])
fig, ax = plt.subplots(2, 1, figsize=(8.4, 5.4), sharex=True,
                       gridspec_kw={"hspace": 0.12, "height_ratios": [3, 1.4]})
ax[0].plot(t, izb(d["P_coil"]), color=K, lw=1.6,
           label="давление в батарее ВО-3 (по манометру)")
ax[0].plot(t, izb(d["P_suc"]), color=G, lw=1.2, ls="--",
           label="давление всасывания НД")
ev = {txt.split(":")[0].split()[0]: tt for tt, txt in d["events"]}
t_ctrl = next((tt for tt, txt in d["events"] if "F-CTRL" in txt), 600)
t_rupt = next((tt for tt, txt in d["events"] if "RUPTURE" in txt), 614)
ax[0].axvline(t_ctrl, color=R, lw=1.0, ls="--")
ax[0].text(t_ctrl - 12, 7.6, "контроллер сбросил секцию\nв «охлаждение»",
           color=R, fontsize=9, ha="right")
ax[0].plot([t_rupt], [izb([201.4 / 1.0197 + 1.013])[0] * 0 + 10.5], marker="v",
           color=R, ms=7)
ax[0].annotate(f"гидроудар: пик 201 кгс/см²\nразрыв на {t_rupt:.0f}-й с",
               xy=(t_rupt, 10.3), xytext=(t_rupt - 250, 11.6), color=R,
               fontsize=9, arrowprops=dict(arrowstyle="->", color=R, lw=0.9))
ax[0].set_ylabel("кгс/см², изб.")
ax[0].set_ylim(-1, 13)
ax[0].legend(loc="center left", fontsize=9, framealpha=1.0)
ax[1].step(t, d["feed"], where="post", color=K, lw=1.4)
ax[1].set_yticks([0, 1], ["закрыт", "открыт"])
ax[1].set_ylabel("соленоид\nподачи")
ax[1].set_ylim(-0.15, 1.3)
ax[1].set_xlabel("время от начала задачи, с")
ax[1].axvline(t_ctrl, color=R, lw=1.0, ls="--")
save("fig_s1", fig)

# ================= Fig. 7: task 2, level transmitter against the fact
# =================
d = DATA["s2"]
t = np.array(d["t"]) / 60.0
fig, ax = plt.subplots(2, 1, figsize=(8.4, 5.6), sharex=True,
                       gridspec_kw={"hspace": 0.12, "height_ratios": [3, 1.8]})
ax[0].plot(t, d["L_real"], color=K, lw=1.6,
           label="фактический уровень (по указателю)")
ax[0].plot(t, d["L_ind"], color=G, lw=1.6, ls="--",
           label="дистанционный уровнемер (на щите)")
ax[0].axhline(90, color=R, lw=1.0, ls="--")
ax[0].text(0.5, 91.5, "унос на всас компрессоров", color=R, fontsize=9)
i_st = next(i for i, x in enumerate(np.array(d["t"])) if x >= 900)
ax[0].axvline(15.0, color=R, lw=0.9, ls=":")
ax[0].text(15.3, 42, "уровнемер замер\n(15-я мин)", color=R, fontsize=9)
ax[0].set_ylabel("уровень ЦР-НД, %")
ax[0].set_ylim(20, 105)
ax[0].legend(loc="upper left", fontsize=9, framealpha=1.0)
ax[1].plot(t, np.array(d["ppm"]) * 0.71, color=K, lw=1.4)
ax[1].axhline(18, color=G, lw=0.9, ls="--")
ax[1].text(0.5, 19.5, "предупредительная 18 мг/м³", color=G, fontsize=8.5)
ax[1].set_ylabel("NH₃ в машзале,\nмг/м³")
ax[1].set_xlabel("время от начала задачи, мин")
save("fig_s2", fig)

# ================= Fig. 8: task 3, the sign of air =================
d = DATA["s3"]
t = np.array(d["t"]) / 60.0
fig, ax = plt.subplots(3, 1, figsize=(8.4, 6.8), sharex=True,
                       gridspec_kw={"hspace": 0.14, "height_ratios": [3, 2, 2]})
ax[0].plot(t, izb(d["P_cond"]), color=K, lw=1.6,
           label="давление конденсации (по манометру)")
ax[0].axhline(15.5, color=R, lw=1.1, ls="--")
ax[0].text(1, 15.7, "защита верхней ступени 15,5 кгс/см²", color=R, fontsize=9)
ax[0].set_ylabel("кгс/см², изб.")
ax[0].legend(loc="lower right", fontsize=9, framealpha=1.0)
dTn = np.array(d["T_sat"]) - np.array(d["T_cond"])
ax[1].plot(t, d["T_sat"], color=G, lw=1.3, ls="--",
           label="t конденсации ПО МАНОМЕТРУ (из p по таблице насыщения)")
ax[1].plot(t, d["T_cond"], color=K, lw=1.3,
           label="t конденсации ПО ТЕРМОМЕТРУ (фактическая)")
ax[1].set_ylabel("°С")
ax[1].legend(loc="lower right", fontsize=8.5, framealpha=1.0)
i = len(t) * 2 // 3
ax[1].annotate(f"расхождение {dTn[i]:.1f} К — признак воздуха",
               xy=(t[i], (d["T_sat"][i] + d["T_cond"][i]) / 2),
               xytext=(t[i] - 42, d["T_sat"][i] + 4), color=R, fontsize=9.5,
               arrowprops=dict(arrowstyle="->", color=R, lw=0.9))
ax[2].plot(t, d["T_milk"], color=K, lw=1.6, label="молоко")
ax[2].axhline(6.0, color=R, lw=1.0, ls="--")
ax[2].text(1, 6.3, "граница +6 °С", color=R, fontsize=9)
ax[2].set_ylabel("t молока, °С")
ax[2].set_xlabel("время от начала задачи, мин")
save("fig_s3", fig)

# ================= Fig. 10: task 4, a trapped segment =================
# Model curve: T(t) towards +24 °C, P = P0 + 9 bar/K
tt = np.linspace(0, 25, 300)          # min
T0, Tamb, m, UA, c = -9.0, 24.0, 28.0, 25.0, 4650.0
tau = m * c / UA / 60.0
T = Tamb - (Tamb - T0) * np.exp(-tt / tau)
P = 2.0 + 9.0 * 1.0197 * (T - T0)     # kgf/cm2 gauge
fig, ax = plt.subplots(figsize=(8.4, 4.2))
ax.plot(tt, P, color=K, lw=1.7, label="давление запертого участка (расчёт)")
ax.axhline(55 * 1.0197 - 1, color=R, lw=1.2, ls="--")
ax.text(0.6, 56.5, "разрушение фланцевого соединения ≈ 55 кгс/см²",
        color=R, fontsize=9.5)
i_b = int(np.argmax(P >= 55 * 1.0197 - 1))
ax.plot([tt[i_b]], [P[i_b]], marker="v", color=R, ms=8)
ax.annotate(f"разрыв через ≈{tt[i_b]:.0f} мин после запирания",
            xy=(tt[i_b], P[i_b]), xytext=(tt[i_b] - 9.5, P[i_b] - 22),
            color=R, fontsize=9.5,
            arrowprops=dict(arrowstyle="->", color=R, lw=0.9))
ax.text(12.5, 12, "≈ 9 кгс/см² на каждый градус прогрева\n"
        "(жидкость без паровой подушки)", fontsize=9.5, color=K)
ax.set_xlabel("время после запирания участка, мин")
ax.set_ylabel("кгс/см², изб.")
ax.set_ylim(0, 70)
ax.legend(loc="upper left", fontsize=9, framealpha=1.0)
save("fig_s4", fig)

# ================= Fig. 11: task 5, instruments apart =================
d = DATA["s5"]
t = np.array(d["t"]) / 60.0
fig, ax = plt.subplots(figsize=(8.4, 4.2))
ax.plot(t, np.array(d["ind"]) * 0.71, color=K, lw=1.7,
        label="стационарный АТ-2 (просрочен по поверке)")
ax.plot(t, np.array(d["real"]) * 0.71, color=G, lw=1.5, ls="--",
        label="фактическая концентрация (её покажет переносной)")
ax.axhline(18, color=G, lw=0.9, ls=":")
ax.text(0.5, 19, "предупредительная 18 мг/м³", color=G, fontsize=8.5)
ax.axhline(36, color=R, lw=1.0, ls="--")
ax.text(0.5, 37.5, "аварийная сигнализация по цеху", color=R, fontsize=9)
ax.annotate("дрейф нуля прибора", xy=(28, 46), xytext=(15, 52), color=K,
            fontsize=9.5, arrowprops=dict(arrowstyle="->", color=K, lw=0.9))
ax.annotate("настоящий потёк на сальнике ≈ 3,5 мг/м³", xy=(30, 3.6),
            xytext=(9, 10.5), color=G, fontsize=9.5,
            arrowprops=dict(arrowstyle="->", color=G, lw=0.9))
ax.set_xlabel("время от начала задачи, мин")
ax.set_ylabel("NH₃ в цехе, мг/м³")
ax.set_ylim(0, 58)
ax.legend(loc="center right", fontsize=9, framealpha=1.0)
save("fig_s5", fig)

json.dump(FIGS, open(os.path.join(D, "expert_figs.json"), "w"))
print("итого рисунков:", len(FIGS))
