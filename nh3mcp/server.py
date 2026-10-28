"""
NH3Ops-Bench as an MCP server (agent surface only).

One process per run. Started by the stand::

    DMCP_IH_INSTANCE=<instance.json> DMCP_IH_OUTPUT=<record.json> \
        python -m nh3mcp.server

or by hand::

    python -m nh3mcp.server --scenario S1 --clock fixed --out record.json

Agent tools: ``observe``, ``list_actions``, ``act``, ``wait``. Resources:
the plant description and the catalog. Prompt: ``task`` (the text a harness
starts with). There is no control tool on this connection (FR-1.3): the
setup is the instance given at start. Two files leave the server, both for
the stand and never for the agent:

  <out>.journal.json   rewritten after every call: the calls and what each
                       was charged. `py -m nh3mcp.oracle <journal>` replays
                       it into the run's outcome -- the stand needs nothing
                       else, even if it killed the server mid-shift;
  <out>                the run record with the outcome, when the episode
                       ends or the server exits cleanly.

The token clock. Virtual time is the model's output tokens / 40 per
decision, and only the stand sees the model. Its gateway passes the tokens
produced since the previous call in the call's ``_meta`` under
``nh3bench/tokens`` (and must drop that key if the harness sets it). No
agent tool takes a token count: an agent cannot set its own clock.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .env import WAIT_MAX, WAIT_MIN, NH3Env
from .instance import Instance
from . import texts

META_TOKENS = "nh3bench/tokens"

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                       idempotentHint=False, openWorldHint=False)
# `act` covers the whole catalog, ESD included; the per-command flag is in
# list_actions and in this tool's meta.
ACT = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                      idempotentHint=False, openWorldHint=False)
WAIT = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                       idempotentHint=False, openWorldHint=False)


def _cost(units: int, time: str) -> dict:
    # cost: decisions (the unit a stand budgets); time: what moves the clock.
    return {"dmcp_ih": {"cost": units, "virtual_time": time}}


def tokens_from_meta(ctx: Context | None) -> int:
    """Tokens the gateway attached to this call; 0 when there is no gateway."""
    try:
        meta = ctx.request_context.meta
    except (AttributeError, ValueError, LookupError):
        return 0
    extra = getattr(meta, "model_extra", None) or {}
    try:
        return max(int(extra.get(META_TOKENS, 0)), 0)
    except (TypeError, ValueError):
        return 0


def build_server(env: NH3Env, on_call=None, on_done=None) -> FastMCP:
    lang = env.lang
    doc = texts.TOOL_DOC[lang]
    app = FastMCP("nh3bench", instructions=texts.instructions(lang))

    def fed(ctx):
        env.charge_tokens(tokens_from_meta(ctx))

    def after():
        if on_call is not None:
            on_call(env)
        if on_done is not None and env.done:
            on_done(env)

    @app.tool(description=doc["observe"], annotations=READ,
              meta=_cost(0, "deliberation"))
    def observe(ctx: Context) -> str:
        fed(ctx)
        out = env.observe()
        after()
        return out

    @app.tool(description=doc["list_actions"], annotations=READ,
              meta=_cost(0, "deliberation"))
    def list_actions(ctx: Context, category: str | None = None) -> list[dict]:
        fed(ctx)
        out = env.list_actions(category)
        after()
        return out

    @app.tool(description=doc["act"], annotations=ACT,
              meta=_cost(1, "deliberation + command latency + 10 s tick"))
    def act(action_id: str, ctx: Context) -> str:
        fed(ctx)
        try:
            return env.act(action_id)
        finally:
            after()

    @app.tool(description=doc["wait"], annotations=WAIT,
              meta=_cost(1, "deliberation + the wait"))
    def wait(seconds: float, ctx: Context) -> str:
        fed(ctx)
        try:
            return env.wait(seconds)
        finally:
            after()

    @app.resource("nh3bench://plant", name="plant", mime_type="text/plain",
                  description="the shift engineer's role and the plant")
    def plant() -> str:
        return texts.role(lang)

    @app.resource("nh3bench://catalog", name="catalog", mime_type="text/plain",
                  description="the full command catalog")
    def catalog() -> str:
        return texts.catalog(lang)

    @app.prompt(name="task", description="the task this server was started with")
    def task() -> str:
        return texts.task_prompt(env.ep.scen, lang, env.inst.clock)

    return app


def _write(path: Path, obj) -> None:
    # Atomic: a stand that kills the server mid-write still finds a whole file.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def journal_path(out: Path) -> Path:
    return out.with_name(out.stem + ".journal.json")


def write_journal(env: NH3Env, out: Path | None) -> None:
    if out is not None:
        _write(journal_path(out), env.journal_doc())


def write_record(env: NH3Env, out: Path | None) -> dict:
    row = env.finish()
    if out is not None:
        write_journal(env, out)
        _write(out, row)
    return row


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        prog="nh3mcp.server",
        description="NH3Ops-Bench как MCP-сервер: одна смена на процесс.")
    ap.add_argument("--instance", default=os.environ.get("DMCP_IH_INSTANCE"),
                    help="instance.json (иначе собирается из флагов ниже)")
    ap.add_argument("--out", default=os.environ.get("DMCP_IH_OUTPUT"),
                    help="куда записать итог прогона (скрыт от агента)")
    ap.add_argument("--scenario", default="S1")
    ap.add_argument("--lang", default="ru", choices=("ru", "en"))
    ap.add_argument("--clock", default="tokens", choices=("tokens", "fixed", "wall"))
    ap.add_argument("--history", type=int, default=0)
    ap.add_argument("--label", default="mcp")
    ap.add_argument("--http", type=int, default=0,
                    help="порт streamable-http; по умолчанию stdio")
    args = ap.parse_args(argv)

    if args.instance:
        inst = Instance.load(Path(args.instance))
    else:
        inst = Instance(instance_id=f"{args.scenario}-{args.clock}-{args.lang}",
                        scenario=args.scenario, lang=args.lang,
                        clock={"mode": args.clock}, history_keep=args.history,
                        label=args.label)
    out = Path(args.out) if args.out else None
    env = NH3Env(inst)
    write_journal(env, out)             # an empty journal is a valid run: inaction
    app = build_server(env, on_call=lambda e: write_journal(e, out),
                       on_done=lambda e: write_record(e, out))
    try:
        if args.http:
            app.settings.port = args.http
            app.run(transport="streamable-http")
        else:
            app.run()
    finally:
        # The connection is closed: the rest of the shift runs without the
        # agent, and the record is written.
        write_record(env, out)


if __name__ == "__main__":
    main()
