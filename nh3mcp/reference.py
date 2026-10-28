"""
Scripted solvers, driven through the MCP surface (rule R11, admission gate 2).

They play the benchmark's reference policies -- no LLM -- the way a harness
would: by calling the server's tools. The stand's part (feeding the token
clock) is played by charging the policy's own token figures, so the oracle
solver here is the same run as OraclePolicy through Episode.run.

    py -m nh3mcp.reference                 # all six: oracle passes, wrong fails
    py -m nh3mcp.reference --scenarios S1 --rule no_cat
"""

from __future__ import annotations

import argparse
import asyncio
import json

from nh3twin.policies import OraclePolicy

from . import oracle
from .env import NH3Env
from .instance import Instance
from .server import build_server

SOLVERS = ("oracle", "null", "esd")


def _call(app, name, args):
    return asyncio.run(app.call_tool(name, args))


def _available(app) -> set:
    res = _call(app, "list_actions", {})
    rows = res[1]["result"] if isinstance(res, tuple) else json.loads(res[0].text)
    return {r["id"] for r in rows if r["available"]}


def run_oracle(env: NH3Env, app) -> None:
    """OraclePolicy's playbook: skip what is unavailable, then NO_OP to the end."""
    script = OraclePolicy.PLAYBOOK.get(env.inst.scenario, [])
    i = 0
    while not env.done:
        legal = _available(app)
        aid, tokens = "NO_OP", 40
        while i < len(script):
            cand = script[i]
            i += 1
            if cand in legal:
                aid, tokens = cand, OraclePolicy.TOKENS
                break
        env.charge_tokens(tokens)
        _call(app, "act", {"action_id": aid})


def run_null(env: NH3Env, app) -> None:
    """The harness looks once and leaves: the rest of the shift is inaction."""
    _call(app, "observe", {})


def run_esd(env: NH3Env, app) -> None:
    """The blunt answer: an emergency stop at once."""
    _call(app, "act", {"action_id": "SAFETY:ESD"})


def solve(sid: str, solver: str, lang: str = "ru") -> dict:
    env = NH3Env(Instance(instance_id=f"{sid}-{solver}", scenario=sid, lang=lang,
                          label=f"mcp-ref:{solver}"))
    app = build_server(env)
    {"oracle": run_oracle, "null": run_null, "esd": run_esd}[solver](env, app)
    return env.finish()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="nh3mcp.reference",
                                 description="эталонные решатели через MCP")
    ap.add_argument("--scenarios", default="S1,S2,S3,S4,S5,S6")
    ap.add_argument("--rule", default="beats_reg", choices=oracle.RULES)
    args = ap.parse_args(argv)
    from .templates import WRONG
    bad = 0
    for sid in args.scenarios.split(","):
        # Admission gate 2: the reference passes and the template's scripted
        # wrong answer fails. Under no_cat the restraint scenarios (S3, S5)
        # cannot meet it -- nothing short of an accident fails there.
        for solver, want in (("oracle", "VALID_PASS"), (WRONG[sid], "VALID_FAIL")):
            v = oracle.verdict(solve(sid, solver), args.rule)
            ok = v["status"] == want
            bad += not ok
            print(f"{sid} {solver:6s} {v['status']:10s} score {v['score']:5.1f} "
                  f"CAT {','.join(v['CAT']) or '-':6s} gap "
                  f"{v['regulation_gap']:+6.1f}  {'ok' if ok else 'НЕ ТАК'}")
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
