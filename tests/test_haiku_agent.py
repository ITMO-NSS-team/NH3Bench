"""HaikuAgent tests with a fake API client - no network, no key needed."""

import os

os.environ["NH3BENCH_NO_COOLPROP"] = "1"

import json

from nh3bench.agents.haiku import HaikuAgent, build_tool
from nh3bench.baseline import ThermostatBaseline
from nh3bench.plant import Plant, ControlAction, default_plant_config
from nh3bench.runner import build_observation
from nh3bench.scenarios import Scenario
from nh3bench.runner import run_episode


class _Usage:
    input_tokens = 900
    cache_read_input_tokens = 2000
    output_tokens = 120


class _ToolUseBlock:
    type = "tool_use"
    name = "set_controls"

    def __init__(self, payload):
        self.input = payload


class _Response:
    def __init__(self, payload):
        self.content = [_ToolUseBlock(payload)]
        self.usage = _Usage()


class _FakeMessages:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        return _Response(self.payload)


class _FakeClient:
    def __init__(self, payload=None, error=None):
        self.messages = _FakeMessages(payload, error)

    def with_options(self, **kwargs):
        return self


def _obs():
    plant = Plant()
    action = ControlAction(
        compressor_capacity=[0, 0, 0],
        room_valves={r.name: False for r in plant.cfg.rooms},
    )
    from collections import deque

    return build_observation(plant, action, [], [], deque(maxlen=3))


GOOD_PAYLOAD = {
    "compressor_capacity": [1.0, 0.0, 0.5],
    "room_valves": {"freezer": True, "chill": False, "processing": True},
    "start_defrost": [],
    "condenser_fan": 0.4,
    "reasoning": "Base stage plus trim; freezer needs cooling.",
    "note": "watching suction pressure",
}


def test_agent_parses_tool_call():
    agent = HaikuAgent(client=_FakeClient(payload=GOOD_PAYLOAD))
    action = agent.decide(_obs())
    assert action.compressor_capacity == [1.0, 0.0, 0.5]
    assert action.room_valves["freezer"] is True
    assert action.condenser_fan == 0.4
    assert agent.note == "watching suction pressure"
    assert agent.stats["calls"] == 1
    assert agent.stats["failures"] == 0
    assert agent.stats["tokens_cached"] == 2000


def test_agent_request_shape():
    client = _FakeClient(payload=GOOD_PAYLOAD)
    agent = HaikuAgent(client=client)
    agent.decide(_obs())
    req = client.messages.requests[0]
    assert req["model"] == "claude-haiku-4-5"
    assert req["tool_choice"] == {"type": "tool", "name": "set_controls"}
    assert req["tools"][0]["strict"] is True
    # static prefix carries the cache breakpoint
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    # telemetry is compact single-message JSON
    payload = json.loads(req["messages"][0]["content"])
    assert "rooms" in payload and "note" in payload


def test_agent_falls_back_on_api_error():
    agent = HaikuAgent(client=_FakeClient(error=RuntimeError("boom")))
    action = agent.decide(_obs())
    assert agent.stats["failures"] == 1
    assert "fallback" in agent.last_reasoning
    # fallback action mirrors the thermostat baseline
    ref = ThermostatBaseline(default_plant_config()).decide(_obs())
    assert action.room_valves.keys() == ref.room_valves.keys()


def test_agent_falls_back_on_bad_payload():
    bad = dict(GOOD_PAYLOAD)
    del bad["condenser_fan"]
    agent = HaikuAgent(client=_FakeClient(payload=bad))
    agent.decide(_obs())
    assert agent.stats["failures"] == 1


def test_tool_schema_is_strict_and_closed():
    tool = build_tool(default_plant_config())
    assert tool["strict"] is True
    schema = tool["input_schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_full_episode_with_fake_client():
    scenario = Scenario(
        name="mini",
        description="",
        duration_h=0.5,
        ambient_c=lambda t: 24.0,
        events=[],
    )
    agent = HaikuAgent(client=_FakeClient(payload=GOOD_PAYLOAD))
    report = run_episode(scenario, agent, hours=0.5)
    assert report.llm_calls == 30  # 0.5 h / 60 s
    assert report.llm_failures == 0
    assert report.cost_usd > 0
