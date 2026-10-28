"""
A task instance: which scenario the server plays and how its clock runs.

Written by whoever starts the server (the stand's runner, a script, a
person), read once at start. It carries no truth: the scenario id names a
task, its title and hazard stay in ``oracle.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nh3twin.episode import THINK_RATE

# The six benchmark scenarios. A scenario is a single deterministic instance
# (seed 1, CLAUDE.md §4); the seed is still exposed because the twin-seed
# sensitivity studies vary it.
SCENARIO_IDS = ("S1", "S2", "S3", "S4", "S5", "S6")

# Deliberation charged per decision in the `fixed` clock: the median, over
# the nine published models, of each model's median output tokens per
# decision (221; per-model medians 65..3679, results/ as of 677083e). It is
# a typical decision, not a recommendation.
FIXED_TOKENS = 221


class Clock(BaseModel):
    """
    How the agent's deliberation becomes plant time.

    ``tokens`` is the benchmark's own rule: output tokens / 40 per decision,
    reported by whoever sees the model (the stand's model route, through the
    gateway). ``fixed`` charges every decision the same, which keeps the
    world deterministic when nobody reports tokens. ``wall`` charges real
    time between calls, for live play; it is not reproducible.
    """
    model_config = ConfigDict(extra="forbid")

    mode: Literal["tokens", "fixed", "wall"] = "tokens"
    think_rate: float = Field(default=THINK_RATE, gt=0,
                              description="tokens per virtual second")
    fixed_tokens: int = Field(default=FIXED_TOKENS, ge=0,
                              description="tokens charged per decision in `fixed`")
    wall_scale: float = Field(default=1.0, gt=0,
                              description="virtual seconds per wall second in `wall`")


class Instance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    scenario: Literal["S1", "S2", "S3", "S4", "S5", "S6"]
    seed: int = 1
    # The canonical task is Russian; English is the separately labelled
    # track (CLAUDE.md §4: the language is part of a run's identity).
    lang: Literal["ru", "en"] = "ru"
    clock: Clock = Clock()
    # How many of the agent's own past actions each panel reading repeats.
    # The LLM runs needed this (each call was stateless); a harness keeps its
    # own memory, and whether the server should supply one is an experiment.
    history_keep: int = Field(default=0, ge=0, le=50)
    # The written regulation (π_reg as text, regulation.py) offered to the
    # agent: the policy-pack experiment (rule R9). Off in the published task.
    policy_pack: bool = False
    # Who is at the panel, for the run record (`policy` field).
    label: str = "mcp"

    @classmethod
    def load(cls, path: Path) -> "Instance":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
