"""
Hidden truth and the verdict. Never imported by server.py (rule R3).

The verdict is computed by the benchmark's own functions, never by a formula
of its own: the score is metrics.bench_score_run on the Episode.result row.
Its two scenario constants -- whether an emergency stop is justified, and
π_reg's score, the pass threshold -- come from results/ (through
report_metrics.esd_justification, as the published table does) only when
the templates are generated. At run time they are read from the frozen
templates/S*.yaml (DMCP-IH decision 0002): retuning a scenario then cannot
move a threshold silently; `nh3mcp.templates --check` fails until the
templates are regenerated on purpose.

DMCP scores a run pass / fail, while the benchmark grades it 0..100. The
binary verdict is therefore a rule the stand chooses, and the graded score
always travels with it:

  no_cat         pass = no catastrophe (the Prevention Rate view);
  beats_reg      pass = no catastrophe and a score above π_reg's on that
                 scenario (the Regulation Gap view, per scenario).

Under `no_cat`, S3 and S5 pass by doing nothing and fail only by causing an
accident -- they are the restraint scenarios, where the question is the
price of the answer. `beats_reg` is the default: it is the rule under which
every scenario separates the reference solver from a scripted wrong answer
(admission gate 2), and it is the benchmark's own bar -- an agent that does
not beat the written regulation has not earned a pass.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

from nh3twin.metrics import bench_score_run
from nh3twin.scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"
# One result cell, one run: S6 is in both files, so rows are keyed by
# (scenario, policy, seed) and the later file does not double it.
BASELINES = ("results/baselines.jsonl", "results/base_S6.jsonl")
RULES = ("no_cat", "beats_reg")


@lru_cache(maxsize=1)
def _baselines() -> dict:
    rows = {}
    for name in BASELINES:
        with open(ROOT / name, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                rows[(r["scenario"], r["policy"], r["seed"])] = r
    return rows


@lru_cache(maxsize=1)
def esd_justified() -> dict:
    sys.path.insert(0, str(ROOT / "tests"))
    try:
        from report_metrics import esd_justification
    finally:
        sys.path.pop(0)
    return esd_justification(_baselines())[0]


def reference_score(sid: str, policy: str) -> float | None:
    r = _baselines().get((sid, policy, 1))
    if r is None:
        return None
    return bench_score_run(dict(r, esd_justified=esd_justified().get(sid, False)))


@lru_cache(maxsize=None)
def frozen(sid: str) -> dict:
    """The oracle block of the scenario's template, as frozen with the task set."""
    import yaml
    with open(TEMPLATES / f"{sid}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["oracle"]


def truth(sid: str) -> dict:
    """What the scenario is about. Oracle-side only: the title alone names the answer."""
    sc = SCENARIOS[sid]
    return {"sid": sid, "title": sc.title, "hazard": sc.hazard,
            "key_actions": list(sc.key_actions), "trap": sc.trap,
            "horizon_s": sc.horizon_s,
            "esd_justified": bool(esd_justified().get(sid, False))}


def verdict(row: dict, rule: str = "beats_reg") -> dict:
    """The verdict on one finished run (the row env.finish() returns)."""
    if rule not in RULES:
        raise ValueError(f"rule {rule!r}: {RULES}")
    sid = row["scenario"]
    spec = frozen(sid)
    just = bool(spec["esd_justified"])
    score = bench_score_run(dict(row, esd_justified=just))
    reg = float(spec["pass"]["score_strictly_above"])
    prevented = not row.get("CAT")
    passed = prevented if rule == "no_cat" else (prevented and score > reg)
    mcp = row.get("mcp") or {}
    # A token clock nobody fed: the model route could not count, so there is
    # no verdict on the agent (decision 0002) -- not a failure.
    status = ("INFRA_ERROR" if not mcp.get("clock_fed", True)
              else "VALID_PASS" if passed else "VALID_FAIL")
    return {
        "status": status,
        "rule": rule,
        "prevented": prevented,
        "CAT": row.get("CAT", []), "MAJ": row.get("MAJ", []),
        "score": score,
        "regulation_score": reg,
        "regulation_gap": None if reg is None else round(score - reg, 1),
        "esd_justified": just,
        # Only a fed token clock is the published rule. A `fixed` clock is
        # comparable across harnesses, not with the published matrix; a token
        # clock nobody fed gave the agent free deliberation.
        "clock": (mcp.get("clock") or {}).get("mode", "tokens"),
        "clock_fed": bool(mcp.get("clock_fed", True)),
        "comparable_with_published": bool(
            (mcp.get("clock") or {}).get("mode", "tokens") == "tokens"
            and mcp.get("clock_fed", True)),
    }


def record_of(doc: dict) -> dict:
    """The run record from a record itself or from a server journal."""
    if "journal" not in doc:
        return doc
    from .env import replay
    return replay(doc).finish()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="nh3mcp.oracle",
        description="вердикт по журналу или итогу прогона MCP-сервера")
    ap.add_argument("path", help="<out>.journal.json или <out>")
    ap.add_argument("--rule", default="beats_reg", choices=RULES)
    ap.add_argument("--record", default="",
                    help="записать восстановленный итог прогона сюда")
    args = ap.parse_args(argv)
    row = record_of(json.loads(Path(args.path).read_text(encoding="utf-8")))
    if args.record:
        Path(args.record).write_text(json.dumps(row, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print(json.dumps(verdict(row, args.rule), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
