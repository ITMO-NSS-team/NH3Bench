"""Съём данных для графиков экспертного описания: штатный режим + 4 аварии."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from nh3twin.runner import Runner
from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode
from nh3twin import props as pr

OUT = {}
D = os.path.dirname(os.path.abspath(__file__))
def save():
    json.dump(OUT, open(os.path.join(D, "expert_data.json"), "w"))

def ds(arr, k):
    return [round(float(x), 3) for x in arr[::k]]

# ---------- Штатный суточный ход ----------
print("штатный режим ...", flush=True)
r = Runner(seed=1, start_hour=2.0, log_every=120.0, dt=0.5)
r.warmup(1.5, defrost=True); r.plc.defrost_enabled = True
res = r.run(7.0, stop_on_cat=False)
H = res.tags_history
OUT["normal"] = {
    "t_h": [round(x["TIME_H"], 3) for x in H],
    "T_LT": [round(x["T_ROOM_LT"], 2) for x in H],
    "T_BLAST": [round(x["T_ROOM_BLAST"], 2) for x in H],
    "T_CHILL": [round(x["T_ROOM_CHILL"], 2) for x in H],
    "T_MILK": [round(x["T_MILK"], 2) for x in H],
    "ICE": [round(x["M_ICE_T"], 2) for x in H],
    "KW": [round(x["POWER_KW"], 0) for x in H],
}
print("  ok", len(H), "точек", flush=True)
save()

# ---------- Общий цикл ручного прогона эпизода с захватом ----------
def run_capture(sid, seconds, cap, stop_on_cat=True):
    ep = Episode(SCENARIOS[sid], seed=1)
    p = ep.plant
    rows = []
    n = int(seconds / ep.dt)
    for i in range(n):
        ep.fm.step(p); ep.plc.step(ep.dt); ep.safety.step()
        p.step(ep.dt); ep.wf.step(ep.dt)
        if i % 10 == 0:                      # каждые 5 с
            rows.append(cap(p, p.t - ep.t0))
        if stop_on_cat and p.cat_flags:
            rows.append(cap(p, p.t - ep.t0))
            break
    events = [(round(t - ep.t0, 1), txt) for t, txt in p.events]
    return rows, events, p

# ---------- S1: давление в батарее ВО-3 ----------
print("S1 ...", flush=True)
rows, events, p = run_capture(
    "S1", 900.0,
    lambda p, t: (t, p.g("P:EV-03") / 1e5, p.g("Tm:EV-03") - 273.15,
                  p.tags()["P_SUC_LP"], int(p.evap["EV-03"].feed_valve)))
OUT["s1"] = {
    "t": [r[0] for r in rows], "P_coil": [round(r[1], 2) for r in rows],
    "T_metal": [round(r[2], 1) for r in rows],
    "P_suc": [round(r[3], 2) for r in rows],
    "feed": [r[4] for r in rows],
    "events": [e for e in events if "SHOCK" in e[1] or "RUPTURE" in e[1]
               or "F-CTRL" in e[1]],
}
print("  ok, событий:", len(OUT["s1"]["events"]), flush=True)
save()

# ---------- S2: показание уровнемера против факта + газ ----------
print("S2 ...", flush=True)
rows, events, p = run_capture(
    "S2", 3600.0,
    lambda p, t: (t, p.tags()["LEVEL_VE_LP"],
                  p.vessel_pressures(p.y)["VE-LP"]["level"] * 100.0,
                  p.disp.zones["MACHINE_ROOM"].ppm,
                  p.tags()["P_SUC_LP"]))
OUT["s2"] = {
    "t": [r[0] for r in rows],
    "L_ind": [round(r[1], 1) for r in rows],
    "L_real": [round(r[2], 1) for r in rows],
    "ppm": [round(r[3], 1) for r in rows],
    "events": [e for e in events if "PRV" in e[1] or "CAT" in e[1]
               or "MAJ" in e[1]][:6],
}
print("  ok", flush=True)
save()

# ---------- S3: давление конденсации и признак воздуха ----------
print("S3 ...", flush=True)
rows, events, p = run_capture(
    "S3", 5400.0,
    lambda p, t: (t, p.tags()["P_COND"], p.tags()["T_COND"],
                  p.tags()["T_MILK"]),
    stop_on_cat=False)
OUT["s3"] = {
    "t": [r[0] for r in rows],
    "P_cond": [round(r[1], 2) for r in rows],
    "T_cond": [round(r[2], 1) for r in rows],
    "T_sat": [round(pr.Tsat(r[1] * 1e5) - 273.15, 1) for r in rows],
    "T_milk": [round(r[3], 2) for r in rows],
}
print("  ok", flush=True)
save()

# ---------- S5: стационарный прибор против факта ----------
print("S5 ...", flush=True)
rows, events, p = run_capture(
    "S5", 2700.0,
    lambda p, t: (t, p.disp.zones["HALL"].ppm_indicated,
                  p.disp.zones["HALL"].ppm),
    stop_on_cat=False)
OUT["s5"] = {
    "t": [r[0] for r in rows],
    "ind": [round(r[1], 1) for r in rows],
    "real": [round(r[2], 1) for r in rows],
}
print("  ok", flush=True)

save()
print("сохранено всё")
