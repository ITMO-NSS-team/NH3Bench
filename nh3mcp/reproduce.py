# -*- coding: utf-8 -*-
"""
A recorded LLM run, played back through the MCP server.

Every decision of a published transcript -- the command and the tokens it
cost -- goes through a real MCP client session, the tokens in the call's
`_meta` exactly as the stand's gateway would pass them. Two things must
hold for the MCP form to be the published benchmark:

  * every panel the server returns is the observation the model saw, as
    recorded in the transcript (`obs`);
  * the run ends as recorded: end time, CAT, MAJ, release, the decision
    times.

No model is called: the model is not deterministic, its transcript is.

The four Claude runs were recorded on the v2.0 physics (isothermal K_s) and
re-derived on v2.1: their outcomes match, but the readings they saw differ
in the second decimal, so only runs recorded on the current physics (GPT,
GLM, the user runs) can match panel for panel. The panel check is reported,
the outcome check decides.

    py -m nh3mcp.reproduce "results/llm_traces/llm_haiku_S*_s1.jsonl"
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from .env import NH3Env
from .instance import Instance
from .oracle import ROOT
from .server import META_TOKENS_LOCAL, build_server

KEYS = ("t_end_s", "CAT", "MAJ", "released_kg", "actions", "t_per_step",
        "tokens_per_step")


def recorded_row(trace: str) -> dict | None:
    """The result row that names this transcript."""
    rel = Path(trace).resolve().relative_to(ROOT).as_posix()
    for f in glob.glob(str(ROOT / "results" / "**" / "*.jsonl"), recursive=True):
        if "traces" in Path(f).parts:
            continue
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("trace") == rel:
                    return r
    return None


def reproduce(trace: str) -> dict:
    row = recorded_row(trace)
    if row is None:
        raise SystemExit(f"{trace}: no result row names this transcript")
    steps = [json.loads(l) for l in open(trace, encoding="utf-8")]
    steps = [s for s in steps if "action" in s]
    lang = (row.get("llm") or {}).get("prompt_lang", "ru")
    env = NH3Env(Instance(instance_id=Path(trace).stem, scenario=row["scenario"],
                          seed=row["seed"], lang=lang, label=row["policy"]))
    app = build_server(env)
    mismatched = []

    async def go():
        async with create_connected_server_and_client_session(app) as s:
            panel = (await s.call_tool("observe", {})).content[0].text
            for i, st in enumerate(steps):
                # The recorded observation is obs.render(); the panel adds the
                # time line and the blocked list around it.
                if lang == "ru" and st["obs"] not in panel:
                    mismatched.append(i)
                res = await s.call_tool("act", {"action_id": st["action"]},
                                        meta={META_TOKENS_LOCAL: st["tokens"]})
                panel = res.content[0].text

    asyncio.run(go())
    got = env.finish()
    # Older rows lack some fields (`actions`): only what was recorded is compared.
    diff = {k: (row[k], got.get(k)) for k in KEYS if k in row and row[k] != got.get(k)}
    return {"trace": Path(trace).name, "scenario": row["scenario"],
            "decisions": len(steps), "panels_mismatched": mismatched,
            "diff": diff, "t_end_s": got["t_end_s"], "CAT": got["CAT"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="nh3mcp.reproduce",
                                 description="опубликованный прогон через MCP")
    ap.add_argument("traces", nargs="+")
    args = ap.parse_args(argv)
    import logging
    logging.getLogger("mcp").setLevel(logging.WARNING)   # one line per request otherwise
    bad = 0
    for pat in args.traces:
        for t in sorted(glob.glob(pat)):
            r = reproduce(t)
            bad += bool(r["diff"])
            n_bad = len(r["panels_mismatched"])
            print(f"{r['scenario']} {r['trace']}: решений {r['decisions']}, "
                  f"панелей совпало {r['decisions'] - n_bad}/{r['decisions']}, "
                  f"итог {'совпал' if not r['diff'] else r['diff']} "
                  f"(t_end {r['t_end_s']}, {','.join(r['CAT']) or 'без КАТ'})")
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
