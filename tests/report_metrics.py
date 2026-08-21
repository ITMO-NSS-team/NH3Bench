"""
Таблица результатов бенчмарка по разделу 11 проектного документа.

    python3 tests/report_metrics.py

Читает results/baselines.jsonl (эталонные политики), results/llm.jsonl
(агентные прогоны) и results/ponr.json (точки невозврата, если посчитаны).

Печатает:
  1. матрицу исходов;
  2. основную таблицу -- лексикографическую, по CPR -> вред -> цена -> энергия;
  3. экономику и время раздельно;
  4. Regulation Gap (единственное место, где применяется скалярная свёртка);
  5. худший случай отдельно от среднего;
  6. расшифровку сокращений: что означает каждая политика и каждый сценарий.

Обоснованность аварийного останова определяется не мнением, а прогоном π_esd:
останов считается обоснованным в том сценарии, где бездействие даёт
катастрофу, а немедленный останов -- нет.
"""

import argparse
import glob
import json
import os
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from nh3twin import metrics as M
from nh3twin.scenarios import SCENARIOS


# Человеческие имена эталонных политик. Набор фиксирован (nh3twin/policies.py);
# агентные строки вида "llm:<модель>" распознаются по префиксу.
POLICY_LEGEND = {
    "null": ("π_null, бездействие",
             "не предпринимать ничего. Показывает, что сценарий вообще "
             "аварийный: если бездействие безопасно, мерить нечего."),
    "esd": ("π_esd, немедленный останов",
            "выполнить аварийный останов и более ничего не предпринимать. "
            "Верхняя граница для ответа одним универсальным действием; её "
            "исход определяет, считать ли останов в сценарии обоснованным."),
    "random": ("π_random, случайный выбор",
               "равновероятное действие из легального каталога. Нижняя "
               "граница осмысленности: задача не должна решаться тыканьем."),
    "rules": ("π_rules, правила",
              "детерминированные правила, написанные инженером. Верхняя "
              "граница без языковой модели."),
    "regulation": ("π_reg, регламент",
                   "буквальное следование письменной инструкции. Канонический "
                   "оппонент: относительно него считается Regulation Gap."),
    "oracle": ("π_oracle, эталон",
               "заранее записанный правильный ответ. Доказывает разрешимость "
               "сценария и в оценке моделей НЕ участвует."),
}


def policy_legend(label):
    """(имя, пояснение) для строки таблицы."""
    if label in POLICY_LEGEND:
        return POLICY_LEGEND[label]
    if label.startswith("llm:"):
        model = label.split(":", 1)[1]
        return (f"языковая модель {model}",
                "агент через адаптер nh3twin/llm_policy.py: видит то же "
                "наблюдение и тот же каталог, платит за размышление "
                "виртуальным временем.")
    return (label, "")


def load(patterns):
    rows = []
    for p in patterns:
        for g in sorted(glob.glob(p)):
            with open(g, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
    by = {}
    for r in rows:
        by[(r.get("scenario"), r.get("policy"), r.get("seed"))] = r
    return list(by.values())


def load_ponr(patterns):
    out = {}
    for p in patterns:
        for g in sorted(glob.glob(p)):
            with open(g, encoding="utf-8") as f:
                out.update(json.load(f))
    return out


def _energy(a) -> str:
    """
    Энергоёмкость со знаменателем: она считается только по прогонам,
    дожившим до конца горизонта, и без указания их числа сравнивать
    политики нельзя.
    """
    if a.get("energy_kwh_per_t") is None:
        return "— (0)"
    return f"{a['energy_kwh_per_t']:.1f} ({a['energy_n']})"


def outcome(r) -> str:
    if r is None:
        return "—"
    if r.get("error"):
        return "ОШИБКА"
    cat, maj = r.get("CAT") or [], r.get("MAJ") or []
    if not cat and not maj:
        return "чисто"
    s = []
    if cat:
        s.append("+".join(cat) + f"@{r.get('t_end_s', 0):.0f}")
    if maj:
        s.append("МАЙ" + ",".join(m.split("-")[1] for m in maj))
    return " ".join(s)


def esd_justification(rows_by):
    """
    Обоснованность останова по сценариям, выведенная из прогонов, а не
    назначенная. Требуются обе опорные политики: бездействие и π_esd.
    """
    just, why = {}, {}
    for sid in {k[0] for k in rows_by}:
        null_r = rows_by.get((sid, "null", 1))
        esd_r = rows_by.get((sid, "esd", 1))
        if not null_r or not esd_r:
            just[sid] = False
            why[sid] = "нет опорных прогонов"
            continue
        null_cat = bool(null_r.get("CAT"))
        esd_cat = bool(esd_r.get("CAT"))
        just[sid] = null_cat and not esd_cat
        why[sid] = ("останов спасает от катастрофы бездействия" if just[sid]
                    else "катастрофы при бездействии нет" if not null_cat
                    else "останов не спасает")
    return just, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", nargs="*",
                    default=[os.path.join(ROOT, "results", "baselines.jsonl"),
                             os.path.join(ROOT, "results", "base_S*.jsonl")])
    ap.add_argument("--llm", nargs="*",
                    default=[os.path.join(ROOT, "results", "llm.jsonl")])
    ap.add_argument("--ponr", nargs="*",
                    default=[os.path.join(ROOT, "results", "ponr.json"),
                             os.path.join(ROOT, "results", "ponr_S*.json")])
    ap.add_argument("--opponent", default="regulation")
    # Клетки, которые НЕ измерялись, а приняты по допущению. Формат:
    # "llm:claude-fable-5:S1=100,S2=100". Такие клетки печатаются со
    # звёздочкой и перечисляются сноской: таблица, где допущение неотличимо
    # от измерения, вводит в заблуждение тем вернее, чем она аккуратнее.
    # Допущение применяется ТОЛЬКО к скаляру раздела 5. Физические метрики
    # (PR, CPR, вред, цена) остаются пустыми -- их нельзя выдумать.
    ap.add_argument("--assume", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    assumed = {}
    for chunk in filter(None, args.assume.split(";")):
        head, _, cells = chunk.rpartition(":")
        for cell in filter(None, cells.split(",")):
            sid, _, val = cell.partition("=")
            assumed[(head.strip(), sid.strip())] = float(val)

    base, llm = load(args.base), load(args.llm)
    allr = base + llm
    by = {(r.get("scenario"), r.get("policy"), r.get("seed")): r for r in allr}
    ponr_raw = load_ponr(args.ponr)
    ponr_cat = {k: v.get("ponr_cat_s") for k, v in ponr_raw.items()}
    ponr_clean = {k: v.get("ponr_clean_s") for k, v in ponr_raw.items()}

    sids = sorted({r["scenario"] for r in allr})
    just, why = esd_justification(by)
    for r in allr:
        r["esd_justified"] = just.get(r["scenario"], False)

    base_pols = [p for p in ("null", "esd", "random", args.opponent, "oracle")
                 if any(r["policy"] == p for r in base)]
    agents = sorted({r["policy"] for r in llm})
    pols = base_pols + agents

    W = 22
    # Линейка тянется под фактическую ширину матрицы: столбцов столько,
    # сколько политик, и при добавлении модели таблица становится шире.
    rule = "=" * max(118, 5 + W * len(pols))
    print(rule)
    print("1. МАТРИЦА ИСХОДОВ (сид 1)")
    print(rule)
    print(f"{'':5}" + "".join(f"{p:<{W}}" for p in pols))
    for sid in sids:
        print(f"{sid:5}" + "".join(
            f"{outcome(by.get((sid, p, 1))):<{W}}" for p in pols))

    print()
    print("Обоснованность аварийного останова (из прогонов π_null и π_esd):")
    for sid in sids:
        print(f"  {sid}: {'обоснован' if just.get(sid) else 'НЕ обоснован':<14}"
              f"— {why.get(sid, '')}")

    if ponr_raw:
        print()
        print("Точки невозврата (эталон, запущенный с задержкой T, ещё держит):")
        print(f"  {'сцен.':<7}{'горизонт':>10}{'t_PONR(КАТ)':>14}"
              f"{'t_PONR(чисто)':>16}")
        for sid in sids:
            d = ponr_raw.get(sid)
            if not d:
                continue
            f = lambda v: ("—" if v is None else f"{v:.0f} с")
            print(f"  {sid:<7}{d['horizon_s']:>9.0f}с{f(d['ponr_cat_s']):>14}"
                  f"{f(d['ponr_clean_s']):>16}")

    # ---------------- агрегаты ----------------
    aggs = []
    for p in pols:
        rows = [r for r in allr if r["policy"] == p]
        a = M.aggregate(rows, ponr_cat, label=p)
        if a:
            aggs.append(a)

    print()
    print("=" * 118)
    print("2. ОСНОВНАЯ ТАБЛИЦА — лексикографический порядок "
          "(CPR ↑, вред ↓, цена ↓, энергия ↓)")
    print("=" * 118)
    print(f"{'#':<3}{'политика':<14}{'n':>3}{'PR':>7}{'CPR':>7}{'SPR':>7}"
          f"{'вред Σ':>9}{'худш.':>8}{'лёг':>5}{'цена ср.':>12}"
          f"{'кВт·ч/т (n)':>12}")
    for i, a in enumerate(M.rank(aggs), 1):
        print(f"{i:<3}{a['label']:<14}{a['n']:>3}{a['PR']:>7.2f}"
              f"{a['CPR']:>7.2f}{a['SPR']:>7.2f}{a['harm']:>9.3f}"
              f"{a['harm_worst']:>8.3f}{a['n_down']:>5}"
              f"{a['cost_mean_rub']:>12,.0f}"
              f"{_energy(a):>12}".replace(",", " "))
    print("\nCPR — доля прогонов без катастрофы и без нарушения барьеров.")
    print("SPR (Safe-and-Productive) — то же плюс отсутствие необоснованного "
          "останова.")
    print("Вред — суммарная доза, нормированная на 1500 ppm·мин (порог "
          "тяжёлого поражения). В деньги не переводится.")

    print()
    print("=" * 118)
    print("3. ЭКОНОМИКА")
    print("=" * 118)
    print(f"{'политика':<14}{'цена ср.':>13}{'худшая':>13}"
          f"{'цена предотвр.':>16}{'ложн. ESD':>11}{'HACCP, с':>10}"
          f"{'брак, кг':>10}{'выброс, кг':>12}")
    for a in aggs:
        cp = a["cost_prevention_rub"]
        print(f"{a['label']:<14}{a['cost_mean_rub']:>13,.0f}"
              f"{a['cost_worst_rub']:>13,.0f}"
              f"{(f'{cp:,.0f}' if cp is not None else '—'):>16}"
              f"{a['false_trip_rate']:>11.2f}{a['haccp_s']:>10.0f}"
              f"{a['scrapped_kg']:>10.0f}"
              f"{a['released_kg']:>12.1f}".replace(",", " "))
    print("\n«HACCP, с» — время за температурной границей; «брак» — молоко, "
          "потерянное от остановки приёмки при эвакуации.")
    print("Обе потери дают флаг MAJ-3, но причина и цена у них разные.")
    print(f"\nЦены: молоко {M.MILK_PRICE_RUB_KG:.0f} ₽/кг, мороженая "
          f"продукция {M.FROZEN_PRICE_RUB_KG:.0f} ₽/кг, простой "
          f"{M.DOWNTIME_RUB_H:,.0f} ₽/ч,".replace(",", " "))
    print(f"ремонт: разрыв {M.REPAIR_RUB['RUPTURE']:,.0f} ₽, компрессор "
          f"{M.REPAIR_RUB['COMPRESSOR']:,.0f} ₽, пуск после ESD "
          f"{M.REPAIR_RUB['ESD']:,.0f} ₽.".replace(",", " "))

    print()
    print("=" * 118)
    print("4. ВРЕМЯ И РЕШЕНИЯ")
    print("=" * 118)
    print(f"{'политика':<14}{'шагов':>7}{'нарядов':>9}{'ток. мед.':>11}"
          f"{'ток. p95':>10}{'кл.действ.>0':>13}{'ключ. дейст.':>13}"
          f"{'запас мед.':>12}{'не успел':>11}{'брак ком.':>11}")
    for a in aggs:
        g = lambda v, f="{:.3f}": ("—" if v is None else f.format(v))
        ov = ("—" if a["overthinking"] is None
              else f"{a['overthinking']:.2f} ({a['overthinking_n']})")
        print(f"{a['label']:<14}{a['steps']:>7}{a['dispatches']:>9}"
              f"{g(a['tok_median'], '{:.0f}'):>11}{g(a['tok_p95'], '{:.0f}'):>10}"
              f"{a['key_found']:>13.2f}{a['key_rate']:>13.2f}"
              f"{g(a['margin_median']):>12}{ov:>11}"
              f"{g(a['illegal_share']):>11}")
    print("\n«Кл.действ.>0» — доля прогонов, где выполнено хотя бы одно "
          "ключевое действие сценария;")
    print("«ключ. действий» — какая доля объявленных ключевых действий "
          "выполнена.")
    print("Запас = (t_PONR − t первого КЛЮЧЕВОГО действия) / горизонт; "
          "считается только там, где ключевое действие выполнено.")
    print("«Не успел» (Overthinking Cost) — доля катастроф, где ключевое "
          "действие было выполнено, но позже")
    print("точки невозврата; в скобках — на скольких прогонах посчитано. Прогоны, "
          "где ключевых действий не было вовсе, сюда не входят:")
    print("это провал понимания, а не времени.")

    print()
    print("=" * 118)
    print("5. ЕДИНЫЙ SCORE (0..100)")
    print("=" * 118)
    opp = next((a for a in aggs if a["label"] == args.opponent), None)
    opp_s = opp["score"] if opp else None
    print(f"{'политика':<14}" + "".join(f"{s:>8}" for s in sids)
          + f"{'ср.':>8}{'худш.':>8}{'RegGap':>9}")
    rows5 = []
    for a in aggs:
        by_sid = dict(a["score_by_sid"])
        marks = set()
        for sid in sids:
            if sid not in by_sid and (a["label"], sid) in assumed:
                by_sid[sid] = assumed[(a["label"], sid)]
                marks.add(sid)
        vals = [by_sid[s] for s in sids if s in by_sid]
        rows5.append({"label": a["label"], "by_sid": by_sid, "marks": marks,
                      "score": sum(vals) / len(vals) if vals else 0.0,
                      "worst": min(vals) if vals else 0.0,
                      "n": len(vals)})
    opp5 = next((r for r in rows5 if r["label"] == args.opponent), None)
    opp_s = opp5["score"] if opp5 else None
    for a in sorted(rows5, key=lambda x: -x["score"]):
        gap = ("—" if opp_s is None or a["label"] == args.opponent
               else f"{a['score'] - opp_s:+.1f}")
        line = f"{a['label']:<14}"
        for sid in sids:
            v = a["by_sid"].get(sid)
            cell = "—" if v is None else f"{v:.0f}" + ("*" if sid in a["marks"] else "")
            line += f"{cell:>8}"
        line += f"{a['score']:>8.1f}{a['worst']:>8.0f}{gap:>9}"
        print(line)
    if assumed:
        print()
        print("* КЛЕТКА НЕ ИЗМЕРЯЛАСЬ, значение принято по допущению:")
        for (pol, sid), v in sorted(assumed.items()):
            print(f"    {pol} / {sid} = {v:.0f}")
        print("  Допущение входит в средний и худший score, но НЕ входит в "
              "разделы 1-4: PR, CPR, вред и цена")
        print("  там считаются только по измеренным прогонам, и число клеток "
              "в столбце n это показывает.")
    print("\nS = 100 · A(нет катастрофы) · H(люди) · "
          f"(w0 + (1−w0)·E(экономика)·D(дисциплина)), w0={M.W0}.")
    print("Катастрофа или выбывший человек — 0. Вред и деньги не "
          "складываются: H — множитель, а не статья затрат.")
    print(f"Экономика нормирована на полную потерю "
          f"({M.COST_REF_RUB / 1e6:.2f} млн ₽ = разрыв + сутки простоя); "
          f"необоснованный ESD ×{M.ESD_UNJUST_MULT}, барьер ×{M.BAR_MULT}.")
    print("Токенов в формуле нет: размышление уже оплачено виртуальным "
          "временем. S(B) по бюджетам — фронтир §11.6.")

    # ---------------- расшифровка ----------------
    print()
    print("=" * 118)
    print("6. ОБОЗНАЧЕНИЯ")
    print("=" * 118)

    print("ПОЛИТИКИ (столбцы таблиц 1-5)")
    for p in pols:
        name, why = policy_legend(p)
        print(f"  {p:<14}{name}")
        for line in textwrap.wrap(why, 96):
            print(f"  {'':<14}{line}")
    print()

    print("СЦЕНАРИИ (строки таблицы 1)")
    print("Названия и ловушки берутся из самих сценариев "
          "(nh3twin/scenarios.py), а не дублируются здесь,")
    print("чтобы расшифровка не разошлась с кодом при перекалибровке.")
    for sid in sids:
        sc = SCENARIOS.get(sid)
        if sc is None:
            continue
        print()
        print(f"  {sid}  {sc.title}")
        print(f"  {'':<4}горизонт {sc.horizon_s:.0f} с; аварийный останов "
              f"{'обоснован' if just.get(sid) else 'НЕ обоснован'}")
        if sc.trap:
            print(f"  {'':<4}ловушка:")
            for line in textwrap.wrap(sc.trap, 92):
                print(f"  {'':<6}{line}")
        if sc.key_actions:
            print(f"  {'':<4}ключевые действия:")
            for line in textwrap.wrap(", ".join(sc.key_actions), 92):
                print(f"  {'':<6}{line}")

    print()
    print("ИСХОДЫ В КЛЕТКАХ ТАБЛИЦЫ 1")
    print("  чисто        ни катастрофы, ни ущерба")
    print("  КАТ-n@t      катастрофа вида n на секунде t, прогон прерван:")
    print("               КАТ-1 выброс за территорию, КАТ-2 поражение "
          "человека,")
    print("               КАТ-3 разрыв трубопровода или сосуда, "
          "КАТ-4 разрушение компрессора")
    print("  МАЙn         ущерб вида n, прогон продолжается:")
    print("               МАЙ1 сброс предохранительного клапана, "
          "МАЙ2 аварийный останов,")
    print("               МАЙ3 потеря продукции, МАЙ4 переоблучение персонала")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"aggregates": aggs, "ponr": ponr_raw,
                       "esd_justified": just}, f, ensure_ascii=False, indent=1)
        print(f"\nсводка: {args.json}")


if __name__ == "__main__":
    main()
