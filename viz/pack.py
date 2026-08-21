"""Уплотнение данных: колоночный формат вместо списка словарей."""
import json, os
d = os.path.dirname(os.path.abspath(__file__))
raw = json.load(open(os.path.join(d, "runs.json")))
out = {}
for key, run in raw.items():
    frames = run["frames"]
    cols = {}
    for k in frames[0]:
        vals = [f.get(k) for f in frames]
        if isinstance(vals[0], (int, float)):
            cols[k] = [round(float(v), 2) for v in vals]
        else:
            cols[k] = vals
    out[key] = {"title": run["title"], "n": len(frames), "cols": cols,
                "events": run["events"], "alarms": run["alarms"],
                "summary": run["summary"]}
json.dump(out, open(os.path.join(d, "packed.json"), "w"),
          ensure_ascii=False, separators=(",", ":"))
print("кадров:", {k: v["n"] for k, v in out.items()})
print("размер:", round(os.path.getsize(os.path.join(d, "packed.json"))/1024), "КБ")
