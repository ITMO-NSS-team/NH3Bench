"""
Running a language model over the benchmark scenarios.

    # Claude Code (saved subscription session)
    python3 tests/run_llm.py --scenarios S1,S2,S3,S4,S5,S6 --model haiku

    # Codex CLI (saved subscription session)
    python3 tests/run_llm.py --provider codex --model gpt-5.6-luna \
        --reasoning-effort medium --scenarios S1,S2,S3,S4,S5,S6

The result is appended line by line to results/llm.jsonl (cached by
the scenario/policy/seed key, as for the reference policies), and the
per-decision transcript with the model's full replies goes to
results/llm_traces/.

A run is long: every decision is a separate model call, 3-25 s of real
time, and there can be close to a hundred decisions per episode. Run it
in the background and follow the log; after an interruption, starting
again fills in the missing cells.
"""

import argparse
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode
from nh3twin.llm_policy import DEFAULT_CLI
from nh3twin.providers import (PROVIDERS, make_policy, accounting_of,
                              _sanitize)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "results")
TRACE_DIR = os.path.join(OUT_DIR, "llm_traces")
os.makedirs(TRACE_DIR, exist_ok=True)


def already_done(out_path):
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["scenario"], r["policy"], r["seed"]))
                except (json.JSONDecodeError, KeyError):
                    pass
    return done


def _commit() -> str:
    """The benchmark version at the time of the run."""
    try:
        import subprocess
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="S1,S2,S3,S4,S5,S6")
    ap.add_argument("--model", default="haiku")
    # The default provider is the one the published runs were made with: the
    # earlier command has to reproduce verbatim.
    ap.add_argument("--provider", default="claude-cli", choices=PROVIDERS)
    ap.add_argument("--base-url", default="",
                    help="переопределить адрес API провайдера")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--reasoning-effort", default="medium",
                    choices=("none", "low", "medium", "high", "xhigh", "max"))
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--history", type=int, default=14,
                    help="сколько последних действий показывать модели")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--cli", default="")
    ap.add_argument("--tag", default="", help="суффикс имени политики")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "llm.jsonl"))
    # Trial runs must not mix with the published transcripts:
    # tests/replay_llm.py collects them by mask and would append a trial to the
    # matrix.
    ap.add_argument("--trace-dir", default=TRACE_DIR)
    # The canonical task language is Russian: the published runs answered it.
    # The English track is marked in the provenance and compared separately.
    ap.add_argument("--prompt-lang", default="ru", choices=("ru", "en"))
    args = ap.parse_args()

    pol_name = f"llm:{args.model}" + (f":{args.tag}" if args.tag else "")
    sids = [s for s in args.scenarios.split(",") if s]
    seeds = [int(x) for x in args.seeds.split(",")]
    done = already_done(args.out)

    t_all = time.time()
    for sid in sids:
        for seed in seeds:
            if (sid, pol_name, seed) in done:
                print(f"== {sid}/{pol_name}/{seed} уже есть", flush=True)
                continue
            # OpenRouter slugs contain a slash (google/gemini-3.7-flash), so
            # the transcript filename is sanitized separately, or the path
            # would go off into a non-existent subdirectory.
            os.makedirs(args.trace_dir, exist_ok=True)
            trace = os.path.join(
                args.trace_dir, f"{_sanitize(pol_name)}_{sid}_s{seed}.jsonl")
            if os.path.exists(trace):
                os.remove(trace)
            print(f"== {sid}/{pol_name}/{seed}: старт "
                  f"(горизонт {SCENARIOS[sid].horizon_s:.0f} с)", flush=True)
            t0 = time.time()
            pol = None
            try:
                ep = Episode(SCENARIOS[sid], seed=seed)
                ep._policy_name = pol_name
                pol = make_policy(args.provider, args.model, cli=args.cli,
                                  history=args.history,
                                  timeout=args.timeout,
                                  trace_path=trace, label=pol_name,
                                  verbose=True,
                                  base_url=args.base_url or None,
                                  temperature=args.temperature,
                                  max_tokens=args.max_tokens,
                                  prompt_lang=args.prompt_lang,
                                  reasoning_effort=args.reasoning_effort)
                r = ep.run(pol)
                r["policy"] = pol_name
                seg = ep.plant.segments.get("EV-03")
                r["fatigue_EV03"] = round(seg.fatigue, 3) if seg else None
                r["max_dose"] = max(
                    [o["dose"] for o in r["operators"].values()] or [0.0])
                r["milk_max"] = round(
                    max(t[1]["T_MILK"] for t in ep.trace), 2) if ep.trace else None
                r["pcond_max"] = round(
                    max(t[1]["P_COND"] for t in ep.trace), 2) if ep.trace else None
                r["action_counts"] = {}
                for rec in ep.log:
                    key = rec.action.split(":")[0]
                    r["action_counts"][key] = r["action_counts"].get(key, 0) + 1
                r["llm"] = vars(pol.stats)
                r["llm"]["model"] = args.model
                r["llm"]["history"] = args.history
                r["llm"]["reasoning_effort"] = (
                    args.reasoning_effort
                    if args.provider in {"codex", "zai"} else None)
                r["llm"]["tokens_per_decision"] = (
                    round(pol.stats.out_tokens / max(pol.stats.calls, 1), 1))
                # The provenance of a run. Without it a table row cannot be
                # reproduced and there is no way to tell whether it is
                # comparable with the others on time: virtual seconds are
                # computed from tokens, and the way they are accounted for is
                # part of the test conditions.
                r["llm"].update(provider=args.provider,
                                token_accounting=accounting_of(pol),
                                prompt_lang=args.prompt_lang,
                                commit=_commit())
                r["trace"] = os.path.relpath(trace, ROOT).replace("\\", "/")
            except Exception:
                r = {"scenario": sid, "policy": pol_name, "seed": seed,
                     "error": traceback.format_exc()[-800:]}
                if pol is not None:
                    r["llm"] = vars(pol.stats)
            with open(args.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"== {sid}/{pol_name}/{seed}: CAT={r.get('CAT')} "
                  f"MAJ={r.get('MAJ')} t_end={r.get('t_end_s')} "
                  f"шагов={r.get('n_steps')} "
                  f"({(time.time() - t0) / 60:.1f} мин)", flush=True)

    print(f"готово за {(time.time() - t_all) / 60:.1f} мин", flush=True)


if __name__ == "__main__":
    main()
