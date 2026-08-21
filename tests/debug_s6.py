import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode
from nh3twin.policies import NullPolicy, OraclePolicy, ESDPolicy

pol_name = sys.argv[1] if len(sys.argv) > 1 else "null"
pol = {"null": NullPolicy, "oracle": OraclePolicy, "esd": ESDPolicy}[pol_name]()
ep = Episode(SCENARIOS["S6"], seed=1)
ep._policy_name = pol_name
r = ep.run(pol)
print("исход:", r["CAT"], r["MAJ"], "t_end", r["t_end_s"], "выброс", r["released_kg"], "кг, ESD", r["esd"])
print("дозы:", {k: round(v["dose"]) for k, v in r["operators"].items()},
      "лёг:", [k for k, v in r["operators"].items() if v["down"]])
print("%6s %8s %9s %9s %8s" % ("t", "P_COND", "ppm_ind", "выбр.кг", "T_LT"))
for t, tg in ep.trace[::240]:
    print("%6.0f %8.2f %9.1f %9.1f %8.2f" % (t, tg["P_COND"], tg["NH3_MACHINEROOM_PPM"], tg.get("NH3_RELEASED_KG", 0), tg["T_ROOM_LT"]))
t, tg = ep.trace[-1]
print("%6.0f %8.2f %9.1f %9.1f %8.2f  (конец)" % (t, tg["P_COND"], tg["NH3_MACHINEROOM_PPM"], tg.get("NH3_RELEASED_KG", 0), tg["T_ROOM_LT"]))
trips = [(k, v.trip_reason) for k, v in ep.plant.comp.items() if v.tripped]
print("трипы:", trips, " действия:", [a for a in r["actions"] if a != "NO_OP"][:14])
