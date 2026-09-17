# -*- coding: utf-8 -*-
"""
The demo manifest: what the interface knows about the existing runs.

    py trainer/demo_manifest.py                      # build the manifest
    py trainer/demo_manifest.py --selftest           # check the replay clock
    py trainer/demo_manifest.py --traces-out DIR     # export light traces

Why a separate layer. The trainer used to know the reference outcomes
from a REF dictionary typed by hand into build_trainer.py, and knew
nothing at all about the saved transcripts. While the list of models and
scenarios lives in the interface code, every new run requires editing
JS; with a manifest it is enough to rebuild the HTML. This is a direct
requirement: the scenario set is not closed (a re-measurement of S3 is
expected), and a seventh row in the matrix must not be a programmer's
job.

The score is NOT recomputed here. Whether an emergency shutdown was
justified comes from tests/report_metrics.esd_justification, and the
score itself from nh3twin.metrics.bench_score_run -- i.e. from exactly
the functions that print the official table. Otherwise the demo would
in time start showing numbers that disagree with the publication, and do
so unnoticed.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# The scoring logic lives in tests/ and is reused rather than duplicated: a
# copied formula would drift from the official table with the first edit to the
# metrics.
sys.path.insert(0, os.path.join(ROOT, "tests"))

from nh3twin import metrics as M                                    # noqa: E402
from nh3twin.episode import POLL_PERIOD, THINK_RATE                 # noqa: E402
from nh3twin.actions import CATALOG, CATALOG_BY_ID                  # noqa: E402
from nh3twin.scenarios import SCENARIOS                             # noqa: E402
import report_metrics as R                                          # noqa: E402


# The default paths repeat those of report_metrics: the runs of a new scenario
# legitimately live in a file of their own (base_S6.jsonl, ponr_S6.json).
# Перечислено явно, а не маской: results/base_S*.jsonl захватывает и
# base_S6_isoK_archive.jsonl -- прогон прежней версии физики, который в
# склейке победил бы текущий (побеждает последний прочитанный).
BASE_GLOBS = ["results/baselines.jsonl", "results/base_S6.jsonl"]
# Published model runs: one file per model, listed explicitly. A glob will not
# do -- next to them lie single-task shards (…_S3.jsonl), pieces of a resumed
# run (…_head/…_tail/…_partial/…_resumed), re-derivations (…_replayed) and
# archives of earlier twin versions (…_archive, …_v1). A new file is noticed by
# the build itself (_unlisted_llm), which says so out loud.
LLM_GLOBS = [
    "results/llm.jsonl",                    # four Claude models, 24 runs
    "results/llm_gpt-5.6-luna.jsonl",
    "results/llm_gpt-5.6-sol.jsonl",
    "results/llm_gpt-5.6-terra.jsonl",
    "results/llm_gpt-6-astra.jsonl",
    "results/glm-5.3_zai_r1.jsonl",
]
# What in results/ is certainly not a final run file.
LLM_SKIP = re.compile(r"(_S\d+|_head|_tail|_partial|_resumed|_replayed"
                      r"|_archive|_v\d+)\.jsonl$")
# Runs the repo owner measured themselves (benchmark.py run). They live apart
# from the published matrix and are marked in the table as their own: the
# published runs were made in the earlier order and are not to be re-measured.
USER_GLOBS = ["results/user/*.jsonl"]
PONR_GLOBS = ["results/ponr.json", "results/ponr_S*.json"]
OUT = "trainer/demo_manifest.json"

# The trace fields the interface needs. `obs` is deliberately dropped: the twin
# generates the observation itself on replay (it is deterministic), while
# storing dozens of copies of the panel text inflates the manifest from 1.3 to
# 6.4 MB. The one thing that cannot be recreated is the model's answer -- and
# that is what stays.
TRACE_KEEP = ("t_rel", "action", "status", "tokens", "wall_s", "error", "reply")


# =========================================================================
# Loading
# =========================================================================

def _load_rows(globs, src="base"):
    """
    Run rows tagged with their source.

    The source is needed for de-duplication: the same model slug measured by
    the repo owner must not merge with a published row.
    """
    rows = []
    for pat in globs:
        for path in sorted(glob.glob(os.path.join(ROOT, pat))):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        r = json.loads(line)
                        r["_src"] = src
                        rows.append(r)
    return rows


def _base_model(policy: str) -> str:
    """
    The model without a run label: llm:gpt-5.6-terra:re-high ->
    gpt-5.6-terra.

    The third segment is a label of one particular run (reasoning level,
    repeat number, provider subscription), not a different model.
    """
    parts = (policy or "").split(":")
    return parts[1] if len(parts) > 1 and parts[0] == "llm" else ""


def _unlisted_llm(globs=None):
    """
    Files that contain a model the demo does not show at all.

    The file list is maintained by hand, and that is right: shards and
    archives lie next to them. But a new model must not disappear silently.
    Sensitivity studies (the same models under other run labels) stay
    quiet: they are not separate participants of the table but the spread
    of one that is already shown.
    """
    listed_files, shown = set(), set()
    for pat in (globs or LLM_GLOBS):
        for path in glob.glob(os.path.join(ROOT, pat)):
            listed_files.add(path)
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        shown.add(_base_model(json.loads(line).get("policy")))
    shown.discard("")
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "results", "*.jsonl"))):
        if path in listed_files or LLM_SKIP.search(os.path.basename(path)):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                new_models = {
                    _base_model(json.loads(line).get("policy"))
                    for line in fh if line.strip()}
        except (ValueError, OSError):
            continue
        new_models -= shown | {""}
        if new_models:
            out.append("%s (%s)"
                       % (os.path.relpath(path, ROOT).replace(os.sep, "/"),
                          ", ".join(sorted(new_models))))
    return out


def _load_ponr(globs):
    out = {}
    for pat in globs:
        for path in sorted(glob.glob(os.path.join(ROOT, pat))):
            with open(path, encoding="utf-8") as fh:
                out.update(json.load(fh))
    return out


def _commit() -> str:
    """
    The benchmark version. Without it a row in the table cannot be reproduced.
    """
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# =========================================================================
# Assembly
# =========================================================================

def _trace_stats(path):
    """
    Trace summary: how many decisions there were and how expensively the model
    thought.
    """
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
        # Virtual seconds bought with deliberation. The main quantity of the
        # demo: it is what explains why a correct answer arrived late.
        "think_s_total": round(sum(toks) / THINK_RATE, 1),
    }


def _run_id(row) -> str:
    return f"{row['policy']}|{row['scenario']}|{row.get('seed', 1)}"


def _dedup(rows):
    """
    One cell, one run; the last one read wins.

    The S6 cells lie both in the shared baselines.jsonl and in its own
    base_S6.jsonl (that is how they were computed), so without
    de-duplication the scenario entered the manifest twice and the number of
    available recordings came out too high.
    """
    out = {}
    for r in rows:
        out[(r.get("scenario"), r.get("policy"), r.get("seed"),
             r.get("_src", "base"), _lang(r))] = r
    return list(out.values())


def _lang(row) -> str:
    """
    The task language of a run. Reference policies never see the prompt -- ru.
    """
    return ((row.get("llm") or {}).get("prompt_lang") or "ru")


def _run_key(row) -> str:
    """
    The run identifier in the manifest: source plus policy plus task.

    It is assembled in one place: the self-test looks up a trace by this
    same key, and a mismatch would leave it without data -- silently, with
    zero checked steps instead of two thousand.
    """
    lang = _lang(row)
    return (row.get("_src", "base") + "/" + _run_id(row)
            + ("" if lang == "ru" else "@" + lang))


def build(base_globs=BASE_GLOBS, llm_globs=LLM_GLOBS, ponr_globs=PONR_GLOBS,
          user_globs=USER_GLOBS):
    for f in _unlisted_llm(llm_globs):
        print("ВНИМАНИЕ: в демо нет модели из %s -- допишите файл в "
              "LLM_GLOBS (trainer/demo_manifest.py)" % f, file=sys.stderr)
    base = _load_rows(base_globs, "base")
    llm = _load_rows(llm_globs, "llm")
    user = _load_rows(user_globs, "user")
    allrows = _dedup(base + llm + user)

    by = {(r.get("scenario"), r.get("policy"), r.get("seed")): r
          for r in allrows}
    just, just_why = R.esd_justification(by)
    ponr = _load_ponr(ponr_globs)

    runs = []
    for row in allrows:
        sid = row["scenario"]
        # bench_score_run needs the justification flag on the row; it is
        # derived from the pi_null / pi_esd runs rather than assigned by
        # opinion.
        row = dict(row, esd_justified=just.get(sid, False))
        pol = row["policy"]
        is_model = pol.startswith("llm:")
        trace = row.get("trace")
        runs.append({
            "id": _run_key(row),
            "kind": ("user" if row.get("_src") == "user"
                     else "model" if is_model else "policy"),
            "agent": pol[4:] if is_model else pol,
            "policy": pol,
            "scenario": sid,
            "seed": row.get("seed", 1),
            "prompt_lang": _lang(row),
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
    # Scenarios met in the data but absent from the registry also reach the
    # manifest: a re-measurement of S3 may arrive as a separate row.
    known = {s["sid"] for s in scenarios}
    for sid in sorted({r["scenario"] for r in runs} - known):
        scenarios.append({"sid": sid, "title": sid, "brief": "",
                          "hazard": "", "trap": "", "key_actions": [],
                          "horizon_s": None, "ponr_cat_s": None,
                          "ponr_clean_s": None})

    agents = {}
    for r in runs:
        a = agents.setdefault(
            r["kind"] + "|" + r["prompt_lang"] + "|" + r["agent"], {
                "id": r["agent"], "kind": r["kind"],
                "prompt_lang": r["prompt_lang"],
                "scores": {}, "watchable": 0,
            })
        a["scores"][r["scenario"]] = r["score"]
        a["watchable"] += 1 if r["watchable"] else 0
    n_total = len({s["sid"] for s in scenarios})
    for a in agents.values():
        vals = list(a["scores"].values())
        a["score_mean"] = round(sum(vals) / len(vals), 1) if vals else None
        a["score_worst"] = min(vals) if vals else None
        # Completeness of a row. A mean over two tasks out of six is not the
        # same number as a mean over six, and putting them in one column
        # without a mark misleads all the more surely the tidier the table
        # looks.
        a["n_scored"] = len(vals)
        a["n_total"] = n_total
        a["complete"] = len(vals) == n_total
        name, desc = R.policy_legend(a["id"] if a["kind"] == "policy"
                                     else "llm:" + a["id"])
        if a["kind"] == "user":
            name = f"{a['id']} (свой прогон)"
            desc = ("измерено пользователем через benchmark.py run; не часть "
                    "опубликованной матрицы")
        if a.get("prompt_lang", "ru") != "ru":
            # A task in another language is another column, not the same row:
            # the published runs answered the Russian task.
            name += f", задание {a['prompt_lang'].upper()}"
            desc += ("; задание на языке " + a["prompt_lang"].upper()
                     + ", напрямую с русским треком не сравнивается")
        a["label"], a["desc"] = name, desc

    # The Regulation Gap is computed against the same opponent as in the
    # report, and only for complete rows: a difference of means over different
    # task sets is not a gap but nonsense.
    reg = agents.get("policy|ru|regulation", {}).get("score_mean")
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
            # The canonical prompt language of the saved runs. The English
            # track is added separately and is marked right here, or table rows
            # could not be compared across languages.
            "prompt_lang": "ru",
            "token_accounting": "output_tokens",
        },
        # Whether an emergency shutdown was justified, per scenario. A person's
        # run is scored in the browser by that same bench_score_run, which
        # needs this flag; it is derived from the reference policies, so it
        # comes from here rather than being assigned in the interface.
        "esd_just": {sid: bool(just.get(sid, False))
                     for sid in sorted({s["sid"] for s in scenarios})},
        "esd_just_why": {sid: just_why.get(sid, "")
                         for sid in sorted({s["sid"] for s in scenarios})},
        "scenarios": sorted(scenarios, key=lambda s: s["sid"]),
        "agents": sorted(agents.values(),
                         key=lambda a: (a["kind"] == "user",
                                        a["kind"] != "model",
                                        -(a["score_mean"] or 0))),
        "runs": sorted(runs, key=lambda r: (r["scenario"], r["agent"])),
    }


def light_traces(manifest):
    """Traces without the obs field -- the source of truth for Watch."""
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
# Clock self-test
# =========================================================================

def selftest(manifest) -> int:
    """
    The check without which Watch would be showing fiction: the time in a
    trace and the time of a replay must be related by the canonical clock

        t_action = t_observation + tokens/THINK_RATE + command latency

    The last step is excluded: an episode could end while the model was
    still thinking (which is exactly what happened to Haiku in S1 -- the
    correct decision was 17 s late).
    """
    rows = {r["id"]: r for r in manifest["runs"]}
    worst, checked, bad = 0.0, 0, []
    for rid, steps in light_traces(manifest).items():
        row = rows[rid]
        tp = None
        for src in (_load_rows(LLM_GLOBS, "llm")
                    + _load_rows(USER_GLOBS, "user")):  # noqa: E501
            if _run_key(src) == rid:
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
