"""
Shared helpers. Warm-ups are the cost here (~35 s per scenario): set
NH3MCP_CACHE to a directory and they are paid once across sessions.
"""

from __future__ import annotations

import asyncio

from nh3mcp.env import NH3Env
from nh3mcp.instance import Instance
from nh3mcp.server import build_server


def make(sid: str = "S1", **kw):
    env = NH3Env(Instance(instance_id=f"test-{sid}", scenario=sid, **kw))
    return env, build_server(env)


def call(app, name, args=None):
    return asyncio.run(app.call_tool(name, args or {}))


def text_of(result) -> str:
    content = result[0] if isinstance(result, tuple) else result
    return "".join(getattr(c, "text", "") for c in content)
