# -*- coding: utf-8 -*-
"""
Conformance of the NH3Ops-Bench MCP server.

The DMCP-IH rules (its docs/server-recipe.md §3: R1, R2, R3, R5, R6, R11,
FR-1.3) and the benchmark's own: the MCP form is the same benchmark --
the oracle playbook through the tools gives the run Episode.run gives, and
inaction is still the accident.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session

from nh3twin.llm_policy import _ROLE
from nh3twin.policies import OraclePolicy
from nh3twin.scenarios import SCENARIOS
from nh3mcp import oracle, reference, templates, texts
from nh3mcp.env import replay, warm_episode
from nh3mcp.server import META_TOKENS, META_TOKENS_LOCAL, journal_path, write_record

from conftest import call, make, text_of

AGENT_TOOLS = {"observe", "list_actions", "act", "wait"}

# A short session touching every tool, the rejections included.
SEQUENCE = [
    ("observe", {}),
    ("list_actions", {"category": "control"}),
    ("act", {"action_id": "DEFROST:ABORT:EV-03"}),
    ("wait", {"seconds": 60}),
    ("act", {"action_id": "MEASURE:COIL_GAUGE:EV-03"}),
    ("wait", {"seconds": 200}),
    ("observe", {}),
]


def run_sequence(app) -> list:
    return [text_of(call(app, n, a)) for n, a in SEQUENCE]


def surface_text(app, outputs) -> str:
    """Everything the agent side can read: tools, resources, prompt, replies."""
    tools = asyncio.run(app.list_tools())
    parts = [t.description or "" for t in tools]
    parts += [json.dumps(t.inputSchema) for t in tools]
    parts.append(app.instructions or "")
    for uri in ("nh3bench://plant", "nh3bench://catalog"):
        parts += [c.content for c in asyncio.run(app.read_resource(uri))]
    parts += [m.content.text for m in asyncio.run(app.get_prompt("task")).messages]
    return "\n".join(parts + outputs)


# ---------------------------------------------------------------- stand rules

def test_fr13_only_agent_tools_on_the_connection():
    _, app = make()
    assert {t.name for t in asyncio.run(app.list_tools())} == AGENT_TOOLS


def test_r5_annotations_and_cost():
    _, app = make()
    for t in asyncio.run(app.list_tools()):
        assert t.annotations is not None and t.annotations.readOnlyHint is not None, t.name
        assert t.annotations.destructiveHint is not None, t.name
        assert "cost" in (t.meta or {}).get("dmcp_ih", {}), t.name
    by_id = {r["id"]: r for r in call(app, "list_actions")[1]["result"]}
    assert len(by_id) == 133
    assert by_id["SAFETY:ESD"]["destructive"] and not by_id["NO_OP"]["destructive"]
    assert not by_id["MEASURE:LEVEL_GLASS:VE-LP"]["destructive"]


def test_agent_cannot_set_its_own_clock():
    _, app = make()
    for t in asyncio.run(app.list_tools()):
        assert not ({"tokens", "think", "think_s"} & set(t.inputSchema.get("properties", {})))


def test_r1_same_instance_same_responses():
    _, a = make(clock={"mode": "fixed"})
    _, b = make(clock={"mode": "fixed"})
    assert run_sequence(a) == run_sequence(b)


def test_r2_reset_gives_the_initial_state():
    env, app = make(clock={"mode": "fixed"})
    first = text_of(call(app, "observe"))
    run_sequence(app)
    env.reset()
    assert text_of(call(app, "observe")) == first


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("pack", [False, True])
def test_r3_no_truth_on_the_agent_side(lang, pack):
    _, app = make(lang=lang, clock={"mode": "fixed"}, policy_pack=pack)
    outputs = run_sequence(app)
    if pack:
        outputs.append(text_of(call(app, "read_regulation")))
        outputs += [c.content for c in asyncio.run(app.read_resource("nh3bench://regulation"))]
    text = surface_text(app, outputs)
    leaks = ["F-STUCK", "F-CTRL", "StuckDefrost", "DefrostDesync", "CAT-", "MAJ-",
             "esd_justified", "key_actions", "hazard", "trap"]
    for sc in SCENARIOS.values():
        leaks += [sc.title, sc.hazard[:60], sc.trap[:60]]
    for leak in leaks:
        assert leak not in text, leak


# ------------------------------------------------- the same benchmark as before

def test_oracle_through_mcp_is_the_published_oracle_run():
    """The canonical path makes exactly Episode.run's advance() calls."""
    a = reference.solve("S1", "oracle")
    b = copy.deepcopy(warm_episode("S1", 1)).run(OraclePolicy())
    for k in ("t_end_s", "CAT", "MAJ", "released_kg", "actions",
              "tokens_per_step", "t_per_step", "energy_kwh", "operators"):
        assert a[k] == b[k], k
    pub = oracle._baselines()[("S1", "oracle", 1)]
    assert (a["t_end_s"], a["CAT"], a["released_kg"]) == (
        pub["t_end_s"], pub["CAT"], pub["released_kg"])
    v = oracle.verdict(a)
    assert v["status"] == "VALID_PASS" and v["score"] == 100.0


def test_leaving_early_is_inaction():
    """S1 with no command: CAT-3 at 614 s, 8.8 kg -- the published null run."""
    row = reference.solve("S1", "null")
    assert (row["CAT"], row["t_end_s"], row["released_kg"]) == (["CAT-3"], 614.0, 8.8)
    v = oracle.verdict(row)
    assert v["status"] == "VALID_FAIL" and v["score"] == 0.0


def test_a_published_llm_run_reproduces_through_mcp():
    """
    gpt-5.6-luna on S1, decision by decision, tokens in _meta: every panel is
    the observation the model saw, and the run ends as recorded.
    """
    from nh3mcp.reproduce import reproduce
    r = reproduce(str(oracle.ROOT / "results/llm_traces/llm_gpt-5.6-luna_S1_s1.jsonl"))
    assert r["decisions"] == 29
    assert r["panels_mismatched"] == [] and r["diff"] == {}


def test_immediate_esd_scores_as_published():
    assert oracle.verdict(reference.solve("S1", "esd"))["score"] == \
        oracle.reference_score("S1", "esd") == 72.9


# ---------------------------------------------------------------------- clock

def test_tokens_arrive_through_the_gateway_meta():
    """Over a real MCP session: tokens in _meta move the plant, none do not."""
    env, app = make()

    async def go():
        async with create_connected_server_and_client_session(app) as s:
            ts = [env.ep.plant.t]
            for meta in (None,                                       # no gateway
                         {META_TOKENS: 4000},                        # the stand's key
                         {META_TOKENS_LOCAL: 400},                   # the synonym
                         {META_TOKENS: 800, META_TOKENS_LOCAL: 800}):  # both: not twice
                await s.call_tool("observe", {}, meta=meta)
                ts.append(env.ep.plant.t)
            return [b - a for a, b in zip(ts, ts[1:])]

    assert asyncio.run(go()) == pytest.approx([0.0, 100.0, 10.0, 20.0])
    assert env.tokens_reported == 4000 + 400 + 800


def test_fixed_clock_charges_every_decision():
    env, app = make(clock={"mode": "fixed"})
    t0 = env.ep.plant.t
    call(app, "act", {"action_id": "NO_OP"})
    # 221 tokens / 40 = 5.5 s (in 0.5 s steps) + NO_OP's 5 s + the 10 s tick
    assert env.ep.plant.t - t0 == pytest.approx(5.5 + 5.0 + 10.0)
    t1 = env.ep.plant.t
    call(app, "observe")
    assert env.ep.plant.t == t1                     # reading is not a decision


def test_unfed_token_clock_is_no_verdict():
    """Decision 0002: the route could not count -- INFRA_ERROR, not a failure."""
    env, app = make()
    call(app, "act", {"action_id": "NO_OP"})
    v = oracle.verdict(env.finish())
    assert v["status"] == "INFRA_ERROR"
    assert v["clock_fed"] is False and v["comparable_with_published"] is False
    # a harness that never called a tool had nothing to feed: inaction, scored
    env, _ = make()
    assert oracle.verdict(env.finish())["status"] == "VALID_FAIL"


def test_verdict_reads_frozen_numbers_not_results(monkeypatch):
    """A retune that moves π_reg must not move a threshold in silence."""
    row = reference.solve("S3", "esd")                 # 57.1, exactly π_reg's
    assert oracle.verdict(row)["status"] == "VALID_FAIL"
    monkeypatch.setattr(oracle, "reference_score", lambda *a: 0.0)
    monkeypatch.setattr(oracle, "esd_justified", lambda: {"S3": True})
    v = oracle.verdict(row)
    assert v["status"] == "VALID_FAIL" and v["regulation_score"] == 57.1
    assert v["esd_justified"] is False


# ------------------------------------------------------------------- protocol

def test_rejected_commands_do_nothing_and_are_recorded():
    env, app = make(clock={"mode": "fixed"})
    n = len(env.ep.log)
    with pytest.raises(ToolError, match="нет такой команды"):
        call(app, "act", {"action_id": "VALVE:OPEN:EVERYTHING"})
    with pytest.raises(ToolError, match="недоступна"):
        call(app, "act", {"action_id": "COMP:RESET:CO-01"})     # not tripped
    with pytest.raises(ToolError):
        call(app, "wait", {"seconds": 5})
    assert len(env.ep.log) == n
    assert [r[2] for r in env.rejected] == ["unknown", "blocked"]


def test_wait_is_a_noop_with_a_dwell():
    env, app = make(clock={"mode": "fixed"})
    t0 = env.ep.plant.t
    call(app, "wait", {"seconds": 120})
    assert env.ep.log[-1].action == "NO_OP"
    assert env.ep.plant.t - t0 == pytest.approx(5.5 + 120.0)
    # the first-action metric is not fooled by a wait
    assert env.finish()["t_first_action_s"] is None


def test_record_is_written_for_the_oracle(tmp_path):
    env, app = make(clock={"mode": "fixed"})
    call(app, "act", {"action_id": "FEED:CLOSE:EV-03"})
    out = tmp_path / "rec.json"
    write_record(env, out)
    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["scenario"] == "S1" and row["actions"][0] == "FEED:CLOSE:EV-03"
    assert row["mcp"]["calls"]["act"] == 1 and row["t_end_s"] > 0
    assert text_of(call(app, "act", {"action_id": "NO_OP"})) == texts.OVER["ru"]


def test_stdio_process_is_one_shift(tmp_path):
    """
    As a stand starts it: a process on stdio. Closing the connection ends the
    shift -- the rest runs without the agent and the record is written.
    """
    import os
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    out = tmp_path / "rec.json"
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "nh3mcp.server", "--scenario", "S1", "--clock", "fixed",
              "--out", str(out)],
        env={**os.environ, "PYTHONPATH": root, "PYTHONIOENCODING": "utf-8"},
        cwd=root)

    async def go():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                res = await s.call_tool("act", {"action_id": "FEED:CLOSE:EV-03"})
                return names, res.content[0].text

    names, reply = asyncio.run(go())
    assert names == AGENT_TOOLS and "FEED:CLOSE:EV-03 ->" in reply
    # The client stops the server ~2 s after closing; the play-out takes
    # longer, so the journal -- not the record -- is what the stand relies on.
    doc = json.loads(journal_path(out).read_text(encoding="utf-8"))
    row = oracle.record_of(doc)
    assert row["actions"] == ["FEED:CLOSE:EV-03"]
    assert row["t_end_s"] == 1800.0 or row["CAT"]          # played out to the end
    if out.exists():                                       # a clean exit made it
        assert json.loads(out.read_text(encoding="utf-8"))["t_end_s"] == row["t_end_s"]


def test_journal_replays_the_run_exactly():
    """Even on the wall clock, which no second run could reproduce."""
    env, app = make(clock={"mode": "wall", "wall_scale": 50.0})
    run_sequence(app)
    with pytest.raises(ToolError):
        call(app, "act", {"action_id": "COMP:RESET:CO-01"})
    a = env.finish()
    b = replay(json.loads(json.dumps(env.journal_doc()))).finish()
    for k in ("t_end_s", "CAT", "MAJ", "released_kg", "actions", "t_per_step",
              "tokens_per_step", "energy_kwh"):
        assert a[k] == b[k], k
    assert a["mcp"]["rejected"] == b["mcp"]["rejected"]


# --------------------------------------------------------------------- texts

_CYR = re.compile("[А-Яа-яЁё]")


def test_english_track_reads_no_russian():
    _, app = make(lang="en", clock={"mode": "fixed"})
    text = surface_text(app, run_sequence(app))
    assert not _CYR.findall(text), sorted(set(_CYR.findall(text)))[:20]


def test_task_prompt_keeps_the_canonical_role():
    sc = SCENARIOS["S1"]
    from nh3mcp.instance import Clock
    p = texts.task_prompt(sc, "ru", Clock())
    assert p.startswith(_ROLE.split("ФОРМАТ ОТВЕТА")[0].rstrip())
    assert "ДЕЙСТВИЕ:" not in p and sc.brief in p and sc.title not in p
    assert "иначе, чем сказано" in texts.task_prompt(sc, "ru", Clock(mode="fixed"))


def test_templates_match_the_generator():
    assert templates.main(["--check"]) == 0
