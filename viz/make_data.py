"""Генерация данных прогонов для визуализации."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nh3twin.runner import Runner
from nh3twin.plant import HOTGAS, MODE_NAMES
from nh3twin.faults import PowerFault, DefrostDesyncFault

def capture(r, res, name, title, t0):
    p = r.plant
    frames = []
    for row in res.tags_history:
        frames.append({k: (round(v, 3) if isinstance(v, float) else v)
                       for k, v in row.items()})
    ev = [{"t": round(e[0] - t0, 1), "text": e[1]} for e in res.events]
    al = [{"t": round(a[0] - t0, 1), "act": a[1], "tag": a[2], "text": a[3]}
          for a in res.alarms]
    return {"name": name, "title": title, "t0": t0,
            "dt_log": r.log_every, "frames": frames,
            "events": ev, "alarms": al,
            "summary": {k: v for k, v in res.summary.items() if k != "events"}}

OUT = {}

# --- Штатный режим -------------------------------------------------------
r = Runner(seed=1, start_hour=3.0, log_every=60.0, dt=0.5)
r.warmup(1.5, defrost=True); r.plc.defrost_enabled = True
t0 = r.plant.t
res = r.run(6.0, stop_on_cat=False)
OUT["normal"] = capture(r, res, "normal", "Штатный режим с циклами оттайки, 6 ч", t0)
print("штатный:", len(res.tags_history), "кадров")

# --- D1: авария ----------------------------------------------------------
r = Runner(seed=1, start_hour=3.0, log_every=5.0, dt=0.5)
r.warmup(2.0, defrost=False)
r.plc._set_stage(r.plant.evap["EV-03"], HOTGAS)
r.plant.y[r.plant.idx["P:EV-03"]] = 10.2e5
r.plant.y[r.plant.idx["Tm:EV-03"]] = 283.15
r.plc.defrost_enabled = False
r.add_operator("OP-1", zone="MACHINE_ROOM")
r.add_operator("OP-2", zone="CONTROL_ROOM")
t0 = r.plant.t
r.add_fault(PowerFault(fid="F-POWER", t_start=t0 + 60.0, duration=600.0))
r.add_fault(DefrostDesyncFault(fid="F-CTRL", t_start=t0 + 690.0, targets=("EV-03",)))
res = r.run(0.45, stop_on_cat=False)
OUT["d1"] = capture(r, res, "d1", "D1: гидроудар после пуска с рассинхронизацией оттайки", t0)
print("D1:", len(res.tags_history), "кадров,", res.summary["CAT"])

json.dump(OUT, open(os.path.join(os.path.dirname(__file__), "runs.json"), "w"),
          ensure_ascii=False)
print("готово")
