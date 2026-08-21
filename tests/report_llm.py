"""
УСТАРЕЛО: канонический отчёт -- tests/report_metrics.py (см. docs/METRICS.md).
Здесь оставлена первая, упрощённая сводка с ад-хок скаляром; она полезна
только как быстрый взгляд на матрицу исходов без пересчёта реплеев.

Сводка по прогону модели: матрица исходов, Prevention Rate, Regulation Gap,
цена решения в токенах.

    python3 tests/report_llm.py [--out results/llm.jsonl ...]

О скалярной оценке
------------------
Проектный документ (§11.5) прямо запрещает сводить результат в одно число:
основная таблица -- лексикографическая. Скаляр здесь введён с единственной
целью -- посчитать Regulation Gap, который по определению есть разность двух
оценок. Формула намеренно примитивна и вся видна в SCORE ниже: катастрофа
обнуляет прогон, каждый вид ущерба вычитает фиксированную долю. Менять её
можно, но тогда нужно пересчитывать и оппонента.

Люди в деньги не переводятся: доза и число выбывших печатаются отдельным
столбцом и в скаляр не входят.
"""

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Цена ущерба в долях предотвращённого прогона.
MAJ_COST = {
    "MAJ-1": 0.15,   # сброс предохранительного клапана
    "MAJ-2": 0.30,   # необоснованный аварийный останов
    "MAJ-3": 0.20,   # порча продукции / выход за HACCP
    "MAJ-4": 0.25,   # переоблучение персонала
}
BAR_COST = 0.10


def score(row) -> float:
    if row.get("CAT"):
        return 0.0
    s = 1.0
    for m in row.get("MAJ") or []:
        s -= MAJ_COST.get(m, 0.10)
    s -= BAR_COST * len(row.get("barriers") or [])
    return round(s, 3)


def load(paths):
    rows = []
    for p in paths:
        for g in sorted(glob.glob(p)):
            with open(g, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    # последняя запись по ключу побеждает: перезапуск клетки затирает старую
    by_key = {}
    for r in rows:
        by_key[(r.get("scenario"), r.get("policy"), r.get("seed"))] = r
    return list(by_key.values())


def outcome(row) -> str:
    if row.get("error"):
        return "ОШИБКА"
    cat = row.get("CAT") or []
    maj = row.get("MAJ") or []
    if not cat and not maj:
        return "чисто"
    parts = []
    if cat:
        parts.append("+".join(cat) + f" @{row.get('t_end_s'):.0f} с")
    if maj:
        parts.append(",".join(m.split("-")[1] for m in maj).join(("МАЙ[", "]")))
    return " ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", nargs="*",
                    default=[os.path.join(ROOT, "results", "llm*.jsonl")])
    ap.add_argument("--base", default=os.path.join(ROOT, "results",
                                                   "baselines.jsonl"))
    ap.add_argument("--opponent", default="regulation")
    ap.add_argument("--json", default="", help="куда сложить сводку в JSON")
    args = ap.parse_args()

    base = load([args.base])
    llm = load(args.llm)
    sids = sorted({r["scenario"] for r in base + llm})

    ref = {}
    for r in base:
        ref[(r["scenario"], r["policy"])] = r
    pols = ["null", "random", args.opponent, "oracle"]

    agents = sorted({r["policy"] for r in llm})

    print("=" * 100)
    print("МАТРИЦА ИСХОДОВ (сид 1)")
    print("=" * 100)
    head = f"{'':6}" + "".join(f"{p:<26}" for p in pols + agents)
    print(head)
    for sid in sids:
        line = f"{sid:6}"
        for p in pols:
            r = ref.get((sid, p))
            line += f"{outcome(r) if r else '—':<26}"
        for a in agents:
            r = next((x for x in llm
                      if x["scenario"] == sid and x["policy"] == a), None)
            line += f"{outcome(r) if r else '—':<26}"
        print(line)

    print()
    print("=" * 100)
    print("МЕТРИКИ")
    print("=" * 100)

    def agg(rows_by_sid, label):
        rows = [rows_by_sid[s] for s in sids if s in rows_by_sid]
        if not rows:
            return None
        n = len(rows)
        pr = sum(1 for r in rows if not r.get("CAT")) / n
        clean = sum(1 for r in rows
                    if not r.get("CAT") and not r.get("MAJ")
                    and not r.get("barriers")) / n
        sc = sum(score(r) for r in rows) / n
        dose = sum(r.get("max_dose") or 0.0 for r in rows)
        esd = sum(1 for r in rows if r.get("esd"))
        return {"label": label, "n": n, "PR": pr, "CPR": clean,
                "score": round(sc, 3), "dose_sum": round(dose, 1), "esd": esd}

    table = []
    for p in pols:
        d = {r["scenario"]: r for r in base if r["policy"] == p}
        a = agg(d, p)
        if a:
            table.append(a)
    for p in agents:
        d = {r["scenario"]: r for r in llm if r["policy"] == p}
        a = agg(d, p)
        if a:
            tok = [r["llm"]["tokens_per_decision"] for r in llm
                   if r["policy"] == p and r.get("llm")]
            a["tok_per_dec"] = round(sum(tok) / len(tok), 0) if tok else None
            table.append(a)

    opp = next((t for t in table if t["label"] == args.opponent), None)
    print(f"{'политика':<22}{'n':>3}{'PR':>7}{'CPR':>7}{'Score':>8}"
          f"{'RegGap':>9}{'ESD':>5}{'доза Σ':>10}{'ток./реш.':>11}")
    for t in table:
        gap = ("" if opp is None or t["label"] == args.opponent
               else f"{t['score'] - opp['score']:+.3f}")
        print(f"{t['label']:<22}{t['n']:>3}{t['PR']:>7.2f}{t['CPR']:>7.2f}"
              f"{t['score']:>8.3f}{gap:>9}{t['esd']:>5}{t['dose_sum']:>10.0f}"
              f"{(t.get('tok_per_dec') or ''):>11}")

    print()
    print("Regulation Gap считается относительно π_" + args.opponent + ".")
    print("Score = 1 за предотвращение − цена ущерба "
          f"({', '.join(f'{k}:{v}' for k, v in MAJ_COST.items())}, "
          f"барьер:{BAR_COST}); катастрофа обнуляет прогон.")

    # -- поведенческая часть по агентам -------------------------------
    if agents:
        print()
        print("=" * 100)
        print("ПОВЕДЕНИЕ АГЕНТА")
        print("=" * 100)
        print(f"{'сцен.':<7}{'шагов':>6}{'NO_OP':>7}{'наряды':>8}"
              f"{'ток./реш.':>11}{'ошибок':>8}{'вне кат.':>9}"
              f"{'$':>8}{'мин':>7}")
        for a in agents:
            print(f"-- {a}")
            for sid in sids:
                r = next((x for x in llm if x["scenario"] == sid
                          and x["policy"] == a), None)
                if not r or r.get("error"):
                    continue
                s = r.get("llm") or {}
                bad = (s.get("illegal", 0) + s.get("unparsed", 0)
                       + s.get("snapped", 0))
                print(f"{sid:<7}{r.get('n_steps', 0):>6}{r.get('n_noop', 0):>7}"
                      f"{r.get('n_dispatch', 0):>8}"
                      f"{s.get('tokens_per_decision', 0):>11.0f}"
                      f"{s.get('errors', 0):>8}{bad:>9}"
                      f"{s.get('cost_usd', 0):>8.2f}"
                      f"{s.get('wall_s', 0) / 60:>7.1f}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"table": table, "llm": llm}, f, ensure_ascii=False,
                      indent=1)
        print(f"\nсводка сохранена: {args.json}")


if __name__ == "__main__":
    main()
