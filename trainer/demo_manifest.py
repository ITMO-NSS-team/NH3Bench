# -*- coding: utf-8 -*-
"""
Манифест демонстрации: что интерфейсу известно о существующих прогонах.

    py trainer/demo_manifest.py                      # собрать манифест
    py trainer/demo_manifest.py --selftest           # проверить часы replay
    py trainer/demo_manifest.py --traces-out DIR     # выгрузить лёгкие трейсы

Зачем отдельный слой. Тренажёр до сих пор знал об эталонных исходах из
вписанного руками словаря REF в build_trainer.py, а о 24 сохранённых трейсах
не знал вообще. Пока список моделей и сценариев живёт в коде интерфейса,
каждый новый прогон требует правки JS; с манифестом достаточно пересобрать
HTML. Это прямое требование: набор сценариев не закрыт (ожидается пересъёмка
S3), и появление седьмой строки в матрице не должно быть работой программиста.

Счёт НЕ пересчитывается здесь заново. Обоснованность аварийного останова
берётся из tests/report_metrics.esd_justification, а сам балл -- из
nh3twin.metrics.bench_score_run, то есть ровно теми же функциями, что печатают
официальную таблицу. Иначе демонстрация со временем начала бы показывать числа,
расходящиеся с публикацией, причём незаметно.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Логика счёта живёт в tests/ и переиспользуется, а не дублируется: скопированная
# формула разъедется с официальной таблицей при первой же правке метрик.
sys.path.insert(0, os.path.join(ROOT, "tests"))

from nh3twin import metrics as M                                    # noqa: E402
from nh3twin.episode import POLL_PERIOD, THINK_RATE                 # noqa: E402
from nh3twin.actions import CATALOG, CATALOG_BY_ID                  # noqa: E402
from nh3twin.scenarios import SCENARIOS                             # noqa: E402
import report_metrics as R                                          # noqa: E402


# Пути по умолчанию повторяют дефолты report_metrics: прогоны нового сценария
# законно лежат в собственном файле (base_S6.jsonl, ponr_S6.json).
BASE_GLOBS = ["results/baselines.jsonl", "results/base_S*.jsonl"]
LLM_GLOBS = ["results/llm.jsonl"]
PONR_GLOBS = ["results/ponr.json", "results/ponr_S*.json"]
OUT = "trainer/demo_manifest.json"

# Поля трейса, нужные интерфейсу. `obs` сознательно отброшен: наблюдение
# генерирует сам твин при воспроизведении (он детерминирован), а хранение
# 24 копий текста щита раздувает манифест с 1.3 до 6.4 МБ. Воссоздать нельзя
# только ответ модели -- он и остаётся.
TRACE_KEEP = ("t_rel", "action", "status", "tokens", "wall_s", "error", "reply")


# =========================================================================
# Загрузка
# =========================================================================

def _load_rows(globs):
    rows = []
    for pat in globs:
        for path in sorted(glob.glob(os.path.join(ROOT, pat))):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
    return rows


def _load_ponr(globs):
    out = {}
    for pat in globs:
        for path in sorted(glob.glob(os.path.join(ROOT, pat))):
            with open(path, encoding="utf-8") as fh:
                out.update(json.load(fh))
    return out


def _commit() -> str:
    """Версия бенчмарка. Без неё запись в таблице невозможно воспроизвести."""
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# =========================================================================
# Сборка
# =========================================================================

def _trace_stats(path):
    """Сводка по трейсу: сколько решений и насколько дорого думала модель."""
    if not path:
        return None
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None
    toks, steps = [], 0
    with open(full, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            steps += 1
            toks.append(int(json.loads(line).get("tokens") or 0))
    if not steps:
        return None
    return {
        "n_decisions": steps,
        "tokens_total": sum(toks),
        "tokens_median": int(statistics.median(toks)),
        "tokens_max": max(toks),
        # Виртуальные секунды, купленные размышлением. Главная величина
        # демонстрации: именно она объясняет, почему верный ответ опоздал.
        "think_s_total": round(sum(toks) / THINK_RATE, 1),
    }


def _run_id(row) -> str:
    return f"{row['policy']}|{row['scenario']}|{row.get('seed', 1)}"


def _dedup(rows):
    """
    Одна клетка -- один прогон, побеждает последний прочитанный.

    Клетки S6 лежат и в общем baselines.jsonl, и в собственном base_S6.jsonl
    (так их и считали), поэтому без склейки сценарий попадал в манифест
    дважды и число доступных записей оказывалось завышенным.
    """
    out = {}
    for r in rows:
        out[(r.get("scenario"), r.get("policy"), r.get("seed"))] = r
    return list(out.values())


def build(base_globs=BASE_GLOBS, llm_globs=LLM_GLOBS, ponr_globs=PONR_GLOBS):
    base = _load_rows(base_globs)
    llm = _load_rows(llm_globs)
    allrows = _dedup(base + llm)

    by = {(r.get("scenario"), r.get("policy"), r.get("seed")): r
          for r in allrows}
    just, just_why = R.esd_justification(by)
    ponr = _load_ponr(ponr_globs)

    runs = []
    for row in allrows:
        sid = row["scenario"]
        # bench_score_run требует признак обоснованности на строке; он выводится
        # из прогонов π_null/π_esd, а не назначается мнением.
        row = dict(row, esd_justified=just.get(sid, False))
        pol = row["policy"]
        is_model = pol.startswith("llm:")
        trace = row.get("trace")
        runs.append({
            "id": _run_id(row),
            "kind": "model" if is_model else "policy",
            "agent": pol[4:] if is_model else pol,
            "policy": pol,
            "scenario": sid,
            "seed": row.get("seed", 1),
            "score": M.bench_score_run(row),
            "outcome": R.outcome(row),
            "prevented": bool(row.get("prevented")),
            "clean": M.clean(row),
            "CAT": row.get("CAT") or [],
            "MAJ": row.get("MAJ") or [],
            "barriers": row.get("barriers") or [],
            "esd": bool(row.get("esd")),
            "esd_justified": just.get(sid, False),
            "t_end_s": row.get("t_end_s"),
            "horizon_s": row.get("horizon_s"),
            "n_steps": row.get("n_steps"),
            "trace": trace,
            "watchable": bool(_trace_stats(trace)),
            "trace_stats": _trace_stats(trace),
        })

    scenarios = []
    for sid, scen in SCENARIOS.items():
        p = ponr.get(sid) or {}
        scenarios.append({
            "sid": sid,
            "title": scen.title,
            "brief": scen.brief,
            "hazard": scen.hazard,
            "trap": scen.trap,
            "key_actions": list(scen.key_actions),
            "horizon_s": scen.horizon_s,
            "ponr_cat_s": p.get("ponr_cat_s"),
            "ponr_clean_s": p.get("ponr_clean_s"),
        })
    # Сценарии, встреченные в данных, но отсутствующие в реестре, тоже попадают
    # в манифест: пересъёмка S3 может приехать как отдельная строка.
    known = {s["sid"] for s in scenarios}
    for sid in sorted({r["scenario"] for r in runs} - known):
        scenarios.append({"sid": sid, "title": sid, "brief": "",
                          "hazard": "", "trap": "", "key_actions": [],
                          "horizon_s": None, "ponr_cat_s": None,
                          "ponr_clean_s": None})

    agents = {}
    for r in runs:
        a = agents.setdefault(r["agent"], {
            "id": r["agent"], "kind": r["kind"],
            "scores": {}, "watchable": 0,
        })
        a["scores"][r["scenario"]] = r["score"]
        a["watchable"] += 1 if r["watchable"] else 0
    n_total = len({s["sid"] for s in scenarios})
    for a in agents.values():
        vals = list(a["scores"].values())
        a["score_mean"] = round(sum(vals) / len(vals), 1) if vals else None
        a["score_worst"] = min(vals) if vals else None
        # Полнота строки. Среднее по двум задачам из шести -- не то же число,
        # что среднее по шести, и ставить их в один столбец без пометки
        # значит вводить в заблуждение тем вернее, чем аккуратнее таблица.
        a["n_scored"] = len(vals)
        a["n_total"] = n_total
        a["complete"] = len(vals) == n_total
        name, desc = R.policy_legend(a["id"] if a["kind"] == "policy"
                                     else "llm:" + a["id"])
        a["label"], a["desc"] = name, desc

    # Regulation Gap считается относительно того же оппонента, что в отчёте,
    # и только для полных строк: разность средних по разным наборам задач --
    # не разрыв с регламентом, а бессмыслица.
    reg = agents.get("regulation", {}).get("score_mean")
    for a in agents.values():
        a["reg_gap"] = (round(a["score_mean"] - reg, 1)
                        if (reg is not None and a["score_mean"] is not None
                            and a["complete"])
                        else None)

    return {
        "built_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "benchmark": {
            "commit": _commit(),
            "think_rate_tok_per_s": THINK_RATE,
            "poll_period_s": POLL_PERIOD,
            "catalog_size": len(CATALOG),
            # Канонический язык промпта сохранённых прогонов. Английский трек
            # добавляется отдельно и помечается здесь же, иначе сравнивать
            # строки таблицы между языками будет нельзя.
            "prompt_lang": "ru",
            "token_accounting": "output_tokens",
        },
        "scenarios": sorted(scenarios, key=lambda s: s["sid"]),
        "agents": sorted(agents.values(),
                         key=lambda a: (a["kind"] != "model",
                                        -(a["score_mean"] or 0))),
        "runs": sorted(runs, key=lambda r: (r["scenario"], r["agent"])),
    }


def light_traces(manifest):
    """Трейсы без поля obs -- источник истины для Watch."""
    out = {}
    for r in manifest["runs"]:
        if not r["watchable"]:
            continue
        path = r["trace"]
        full = path if os.path.isabs(path) else os.path.join(ROOT, path)
        steps = []
        with open(full, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                steps.append({k: rec.get(k) for k in TRACE_KEEP})
        out[r["id"]] = steps
    return out


# =========================================================================
# Самопроверка часов
# =========================================================================

def selftest(manifest) -> int:
    """
    Проверка, без которой Watch показывал бы вымысел: время в трейсе и время
    воспроизведения должны быть связаны каноническими часами

        t_действия = t_наблюдения + токены/THINK_RATE + задержка команды

    Последний шаг исключён: эпизод мог кончиться, пока модель думала (именно
    это и произошло у Haiku в S1 -- верное решение опоздало на 17 с).
    """
    rows = {r["id"]: r for r in manifest["runs"]}
    worst, checked, bad = 0.0, 0, []
    for rid, steps in light_traces(manifest).items():
        row = rows[rid]
        tp = None
        for src in _load_rows(LLM_GLOBS):
            if _run_id(src) == rid:
                tp = src.get("t_per_step")
                break
        if not tp:
            continue
        for i, (s, t) in enumerate(list(zip(steps, tp))[:-1]):
            a = CATALOG_BY_ID.get(s["action"])
            exp = s["t_rel"] + (s["tokens"] or 0) / THINK_RATE + (a.latency if a else 0)
            d = abs(exp - t)
            worst = max(worst, d)
            checked += 1
            if d > 1.0:
                bad.append((rid, i, round(d, 1)))
        _ = row
    print(f"проверено шагов: {checked}; макс. отклонение {worst:.2f} с; "
          f"вне допуска: {len(bad)}")
    for b in bad[:10]:
        print("  расхождение:", b)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--traces-out", default="",
                    help="каталог для лёгких трейсов (по одному JSON на прогон)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    man = build()
    if args.selftest:
        sys.exit(selftest(man))

    path = os.path.join(ROOT, args.out)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)
    n_watch = sum(1 for r in man["runs"] if r["watchable"])
    print(f"манифест: {args.out} "
          f"({os.path.getsize(path) / 1024:.0f} КБ); "
          f"сценариев {len(man['scenarios'])}, "
          f"агентов {len(man['agents'])}, "
          f"прогонов {len(man['runs'])}, из них для показа {n_watch}")

    if args.traces_out:
        d = os.path.join(ROOT, args.traces_out)
        os.makedirs(d, exist_ok=True)
        tot = 0
        for rid, steps in light_traces(man).items():
            name = rid.replace(":", "_").replace("|", "_") + ".json"
            p = os.path.join(d, name)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(steps, fh, ensure_ascii=False)
            tot += os.path.getsize(p)
        print(f"трейсы: {args.traces_out} ({tot / 1e6:.1f} МБ без obs)")


if __name__ == "__main__":
    main()
