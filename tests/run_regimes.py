"""
Прогон цифрового двойника во всех характерных режимах.

Запуск:  python3 tests/run_regimes.py
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nh3twin.runner import Runner
from nh3twin.plant import HOTGAS, COOL
from nh3twin.faults import (LeakFault, SensorFault, PowerFault, FoulingFault,
                            PumpFault, DefrostDesyncFault, FanFault, ValveFault)

RESULTS = []


def audit_mass(p):
    return (sum(p.g(f"M:{v.tag}") for v in p.cfg.vessels)
            + sum(p.g(f"mliq:{e.tag}") for e in p.cfg.evaporators))


def record(name, r, res, m0, note=""):
    p = r.plant
    m1 = audit_mass(p)
    bal = 100.0 * (m1 + p.disp.m_released_total - m0) / m0
    RESULTS.append({
        "режим": name,
        "CAT": ",".join(res.summary["CAT"]) or "-",
        "MAJ": ",".join(res.summary["MAJ"]) or "-",
        "выброс,кг": round(p.disp.m_released_total, 1),
        "дисб.массы,%": round(bal, 3),
        "уск.": int(res.steps * r.dt / max(res.wall_time, 1e-6)),
        "примечание": note,
    })


def base(seed=1, hour=3.0, warm=1.5, defrost=False, log=60.0):
    r = Runner(seed=seed, start_hour=hour, log_every=log, dt=0.5)
    r.warmup(warm, defrost=defrost)
    r.plc.defrost_enabled = defrost
    return r


# =====================================================================
print("1/10  Установившийся режим, 6 ч ...")
r = base(defrost=True); m0 = audit_mass(r.plant)
res = r.run(6.0, stop_on_cat=False)
tg = r.plant.tags()
record("Установившийся, 6 ч", r, res, m0,
       f"молоко {tg['T_MILK']:.1f} C, LT {tg['T_ROOM_LT']:.1f} C, {tg['POWER_KW']:.0f} кВт")

# =====================================================================
print("2/10  Пик приёмки молока ...")
r = base(hour=5.5, defrost=True); m0 = audit_mass(r.plant)
res = r.run(3.5, stop_on_cat=False)
tg = r.plant.tags()
record("Пик приёмки молока", r, res, m0,
       f"молоко max {max(x['T_MILK'] for x in res.tags_history):.2f} C, "
       f"лёд {tg['M_ICE_T']:.1f} т")

# =====================================================================
print("3/10  Штатная оттайка ...")
r = base(defrost=True, warm=2.0)
r.plant.y[r.plant.idx["frost:EV-03"]] = 40.0
r.plc.defrost_schedule_h = 0.001
m0 = audit_mass(r.plant)
res = r.run(1.0, stop_on_cat=False)
record("Штатная оттайка", r, res, m0,
       f"ударов {res.summary['shock_events']}, иней "
       f"{r.plant.g('frost:EV-03'):.1f} кг")

# =====================================================================
print("4/10  Отказ насоса, автоввод резерва ...")
r = base(defrost=True); m0 = audit_mass(r.plant); t0 = r.plant.t
r.add_fault(PumpFault(fid="F-PUMP", t_start=t0 + 300.0, pump="PU-LP-A"))
res = r.run(2.0, stop_on_cat=False)
sw = [e for e in res.events if "автоввод" in e[1]]
record("Отказ насоса НД", r, res, m0,
       f"автоввод {'да' if sw else 'НЕТ'}, LT {r.plant.tags()['T_ROOM_LT']:.1f} C")

# =====================================================================
print("5/10  Утечка в машзале ...")
r = base(); m0 = audit_mass(r.plant); t0 = r.plant.t
r.add_operator("OP-1", zone="MACHINE_ROOM")
r.add_operator("OP-2", zone="CONTROL_ROOM")
r.add_fault(LeakFault(fid="F-LEAK", t_start=t0 + 120.0, vessel="VE-HP",
                      zone="MACHINE_ROOM", rate=0.055, ramp=60.0))
res = r.run(1.5, stop_on_cat=False)
op = r.plant.disp.operators["OP-1"]
record("Утечка 55 г/с в машзале", r, res, m0,
       f"пик {max(x['NH3_MACHINEROOM_PPM'] for x in res.tags_history):.0f} ppm, "
       f"доза OP-1 {op.dose_ppm_min:.0f} ppm*мин, ESD={int(r.plant.esd_active)}")

# =====================================================================
print("6/10  Залипший датчик уровня (C1) ...")
r = base(); m0 = audit_mass(r.plant); t0 = r.plant.t
r.add_fault(SensorFault(fid="F-LVL", t_start=t0 + 120.0, tag="LEVEL_VE-LP",
                        kind="stuck", value=0.30))
res = r.run(2.5, stop_on_cat=False)
lv = max(x["LEVEL_VE_LP"] for x in res.tags_history)
record("Залипший уровнемер VE-LP", r, res, m0,
       f"факт. уровень max {lv:.0f} %, показание 30 %")

# =====================================================================
print("7/10  Загрязнение конденсатора ...")
r = base(defrost=True); m0 = audit_mass(r.plant); t0 = r.plant.t
r.add_fault(FoulingFault(fid="F-FOUL", t_start=t0 + 60.0, condenser="CD-01",
                         final_fouling=0.25, ramp=1800.0))
r.add_fault(FanFault(fid="F-FAN", t_start=t0 + 60.0, condenser="CD-02",
                     fans_lost=1))
res = r.run(3.0, stop_on_cat=False)
pc = max(x["P_COND"] for x in res.tags_history)
trips = [c.tag for c in r.plant.comp.values() if c.tripped]
record("Загрязнение конденсатора", r, res, m0,
       f"P_конд max {pc:.1f} бар, отключено {trips or 'нет'}")

# =====================================================================
print("8/10  Обесточивание без рассинхронизации ...")
r = base(defrost=True); m0 = audit_mass(r.plant); t0 = r.plant.t
r.add_operator("OP-1", zone="MACHINE_ROOM")
r.add_fault(PowerFault(fid="F-POWER", t_start=t0 + 120.0, duration=3600.0))
res = r.run(3.0, stop_on_cat=False)
record("Обесточивание 1 ч, штатный пуск", r, res, m0,
       f"LT {r.plant.tags()['T_ROOM_LT']:.1f} C, "
       f"молоко {r.plant.tags()['T_MILK']:.1f} C")

# =====================================================================
print("9/10  D1: рассинхронизация оттайки после пуска ...")
r = base(warm=2.0)
r.plc._set_stage(r.plant.evap["EV-03"], HOTGAS)
r.plant.y[r.plant.idx["P:EV-03"]] = 10.2e5
r.plant.y[r.plant.idx["Tm:EV-03"]] = 283.15
m0 = audit_mass(r.plant); t0 = r.plant.t
r.add_operator("OP-1", zone="MACHINE_ROOM")
r.add_fault(PowerFault(fid="F-POWER", t_start=t0 + 60.0, duration=600.0))
r.add_fault(DefrostDesyncFault(fid="F-CTRL", t_start=t0 + 690.0,
                               targets=("EV-03",)))
res = r.run(0.5, stop_on_cat=False)
sh = [e for e in res.events if "SHOCK" in e[1]]
record("D1: гидроудар (авария)", r, res, m0,
       sh[0][1][:58] if sh else "удара нет")

# =====================================================================
print("10/10 Детерминизм и быстродействие ...")


def d1_run():
    r = base(warm=1.0)
    r.plc._set_stage(r.plant.evap["EV-03"], HOTGAS)
    r.plant.y[r.plant.idx["P:EV-03"]] = 10.2e5
    r.plant.y[r.plant.idx["Tm:EV-03"]] = 283.15
    t0 = r.plant.t
    r.add_fault(PowerFault(fid="F-POWER", t_start=t0 + 60.0, duration=600.0))
    r.add_fault(DefrostDesyncFault(fid="F-CTRL", t_start=t0 + 690.0,
                                   targets=("EV-03",)))
    return r, r.run(0.3, stop_on_cat=False)


r1, a = d1_run()
r2, b = d1_run()
same_state = bool((r1.plant.y == r2.plant.y).all())
same_events = [e[1] for e in a.events] == [e[1] for e in b.events]
same_rel = abs(r1.plant.disp.m_released_total - r2.plant.disp.m_released_total) < 1e-9

print()
print("=" * 118)
hdr = ["режим", "CAT", "MAJ", "выброс,кг", "дисб.массы,%", "уск.", "примечание"]
w = [30, 13, 7, 10, 13, 6, 34]
print(" ".join(h.ljust(x) for h, x in zip(hdr, w)))
print("-" * 118)
for row in RESULTS:
    print(" ".join(str(row[h]).ljust(x) for h, x in zip(hdr, w)))
print("=" * 118)
print()
print(f"Детерминизм: вектор состояния идентичен = {same_state}, "
      f"журнал событий идентичен = {same_events}, выброс идентичен = {same_rel}")
print(f"Быстродействие: {min(r['уск.'] for r in RESULTS)}..."
      f"{max(r['уск.'] for r in RESULTS)}x реального времени "
      f"(требование >= 200x)")
