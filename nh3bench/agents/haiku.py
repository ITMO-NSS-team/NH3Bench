"""Claude Haiku 4.5 real-time plant operator.

Design choices for *real-time* control with an LLM:

* **One request per control step, no agentic loop.**  The action schema is a
  single strict tool (``set_controls``) and ``tool_choice`` forces it, so
  every step costs exactly one round-trip and the reply is schema-validated
  JSON - no retries for malformed output.
* **Prompt caching.**  The tool definition and the static "operator manual"
  system prompt form a stable prefix marked with ``cache_control``; only the
  compact telemetry JSON changes between steps.  After the first step the
  bulk of the input is served from cache (~10x cheaper, faster TTFT).
* **Bounded memory instead of growing history.**  The agent carries state
  between steps in a small self-written scratchpad (``note``) that is echoed
  back in the next observation, so requests never grow and the cache prefix
  never breaks.
* **Deterministic fallback.**  A tight timeout and one SDK retry; any API
  error or missing tool call degrades to the rule-based
  :class:`~nh3bench.baseline.ThermostatBaseline` for that step.  The plant
  is never left uncontrolled, and hard interlocks live below this layer
  anyway (see :mod:`nh3bench.safety` and :mod:`nh3bench.plant`).
"""

from __future__ import annotations

import json
from typing import Optional

from ..baseline import ThermostatBaseline
from ..plant import ControlAction, PlantConfig, default_plant_config

DEFAULT_MODEL = "claude-haiku-4-5"
MAX_NOTE_CHARS = 500


def build_system_prompt(cfg: PlantConfig) -> str:
    rooms = "\n".join(
        f"- {r.name}: setpoint {r.setpoint_c:g} C, hard food-safety band "
        f"[{r.band_lo_c:g}; {r.band_hi_c:g}] C, cooler UA {r.evap_ua_kw_k:g} kW/K"
        + (f", internal load {r.internal_load_kw:g} kW" if r.internal_load_kw else "")
        for r in cfg.rooms
    )
    comps = "\n".join(
        f"- {c.name}: {'variable speed 0..1' if c.variable else 'fixed speed (0 or 1)'}, "
        f"{c.max_flow_m3_h:g} m3/h swept volume, min run {c.min_run_s:g}s, "
        f"min off {c.min_off_s:g}s"
        for c in cfg.compressors
    )
    return f"""You are the shift operator of an industrial ammonia (NH3, R717) refrigeration \
plant serving a food-processing workshop. Every control step you receive one JSON \
telemetry snapshot and must call set_controls exactly once with your decision, which \
holds until the next step.

PLANT
Pumped-recirculation NH3 system, single suction level. Cold rooms (liquid supply \
valve each):
{rooms}
Compressor rack (suction from common accumulator):
{comps}
Evaporative condenser with variable-speed fan (power ~ speed^3, max {cfg.cond_fan_max_kw:g} kW). \
NH3 pump {cfg.pump_kw:g} kW runs while any valve is open.

PHYSICS YOU MUST RESPECT
- Suction pressure rises when evaporators generate more vapour than compressors \
swallow, falls otherwise. Saturation temp at suction defines cooler temperature: \
coolers deliver UA * (T_room - T_evap), T_evap = Tsat(p_suction) + {cfg.evap_approach_k:g} K. \
Typical NH3 saturation points: 100 kPa ~ -33 C, 150 kPa ~ -25 C, 190 kPa ~ -20 C, \
290 kPa ~ -10 C, 430 kPa ~ 0 C.
- Keep suction roughly 120-190 kPa. Below {cfg.lp_cutout_kpa:g} kPa the LP switch trips ALL \
compressors (safety event, {cfg.trip_lockout_s:g}s lockout). Running compressors with closed \
valves crashes suction pressure fast.
- Discharge pressure follows condensing temperature: Pd = Psat(T_cond), \
T_cond = wet_bulb + Q_rejected / (UA_cond * fan^0.7). Above {cfg.hp_cutout_kpa:g} kPa the HP \
switch trips ALL compressors. In hot weather raise the fan BEFORE adding compressors.
- Frost on coolers running below 0 C degrades UA (factor 1/(1+{cfg.frost_ua_penalty:g}*frost)). \
Defrost takes {cfg.defrost_duration_s:g}s, injects {cfg.defrost_heat_kw:g} kW of heat into the room and \
blocks cooling there; do it when the room has thermal margin, not during load peaks.
- Warm product deliveries add a heat load that decays over ~2 h. Doors left open add \
~2.5 kW/K of infiltration.

OBJECTIVE (episode cost, lower is better)
energy_kWh * 1 + degC-hours outside hard bands * 50 + safety trips * 500 + \
compressor starts * 2.
So: food safety comes first, then energy, and do not short-cycle compressors. \
Floating the suction pressure as high as the warmest active room allows saves \
energy; run the condenser fan only as fast as HP margin requires.

RULES OF THUMB
- Stage fixed compressors for base load, trim with the variable one.
- Close a room's valve near the bottom of its band, open near the setpoint's top.
- A hard safety layer clamps illegal commands (min run/off times, lockouts); its \
overrides are reported back to you in `overrides_last_step` - adapt instead of \
repeating refused commands.
- Watch `alarms` and trends; act before cutouts, not after.
- Use `note` (max {MAX_NOTE_CHARS} chars) as your working memory: plan, pending defrosts, \
what you are watching. It is returned to you verbatim next step. You have no other \
memory between steps.

Keep `reasoning` to one or two short sentences."""


def build_tool(cfg: PlantConfig) -> dict:
    room_names = [r.name for r in cfg.rooms]
    n = len(cfg.compressors)
    return {
        "name": "set_controls",
        "description": "Apply control outputs to the refrigeration plant for "
        "the next control interval.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "compressor_capacity": {
                    "type": "array",
                    "description": f"Capacity 0..1 for compressors in order "
                    f"{[c.name for c in cfg.compressors]}. Fixed-speed units "
                    "are rounded to 0/1.",
                    "items": {"type": "number", "minimum": 0, "maximum": 1},
                    "minItems": n,
                    "maxItems": n,
                },
                "room_valves": {
                    "type": "object",
                    "description": "Liquid-supply valve state per room.",
                    "properties": {
                        name: {"type": "boolean"} for name in room_names
                    },
                    "required": room_names,
                    "additionalProperties": False,
                },
                "start_defrost": {
                    "type": "array",
                    "description": "Rooms in which to start a defrost now.",
                    "items": {"type": "string", "enum": room_names},
                },
                "condenser_fan": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Condenser fan speed 0..1.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "One or two short sentences.",
                },
                "note": {
                    "type": "string",
                    "description": f"Scratchpad carried to the next step, "
                    f"max {MAX_NOTE_CHARS} chars.",
                },
            },
            "required": [
                "compressor_capacity",
                "room_valves",
                "start_defrost",
                "condenser_fan",
                "reasoning",
                "note",
            ],
            "additionalProperties": False,
        },
    }


class HaikuAgent:
    """LLM plant operator on Claude Haiku 4.5 with a rule-based fallback."""

    def __init__(
        self,
        config: Optional[PlantConfig] = None,
        model: str = DEFAULT_MODEL,
        client=None,
        timeout_s: float = 30.0,
        max_output_tokens: int = 700,
    ):
        self.cfg = config or default_plant_config()
        self.model = model
        self.timeout_s = timeout_s
        self.max_output_tokens = max_output_tokens
        if client is None:
            import anthropic  # deferred so the bench runs without the SDK

            # zero-arg: resolves ANTHROPIC_API_KEY / auth profile from the env
            client = anthropic.Anthropic()
        self.client = client
        self.fallback = ThermostatBaseline(self.cfg)
        self.system = [
            {
                "type": "text",
                "text": build_system_prompt(self.cfg),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        self.tool = build_tool(self.cfg)
        self.note = ""
        self.last_reasoning = ""
        self.stats = {
            "calls": 0,
            "failures": 0,
            "tokens_in": 0,
            "tokens_cached": 0,
            "tokens_out": 0,
        }

    @property
    def name(self) -> str:
        return f"haiku({self.model})"

    # ------------------------------------------------------------------ decide

    def decide(self, obs: dict) -> ControlAction:
        # keep the fallback controller's internal state warm so a degraded
        # step continues smoothly from the real plant state
        fallback_action = self.fallback.decide(obs)

        payload = dict(obs)
        payload["note"] = self.note
        user_content = json.dumps(payload, separators=(",", ":"), sort_keys=True)

        self.stats["calls"] += 1
        try:
            response = self.client.with_options(
                timeout=self.timeout_s, max_retries=1
            ).messages.create(
                model=self.model,
                max_tokens=self.max_output_tokens,
                system=self.system,
                tools=[self.tool],
                tool_choice={"type": "tool", "name": "set_controls"},
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as err:  # noqa: BLE001 - classified right below
            self._record_failure(err)
            return fallback_action

        usage = getattr(response, "usage", None)
        if usage is not None:
            self.stats["tokens_in"] += getattr(usage, "input_tokens", 0) or 0
            self.stats["tokens_cached"] += (
                getattr(usage, "cache_read_input_tokens", 0) or 0
            )
            self.stats["tokens_out"] += getattr(usage, "output_tokens", 0) or 0

        block = next(
            (
                b
                for b in response.content
                if getattr(b, "type", None) == "tool_use"
                and getattr(b, "name", None) == "set_controls"
            ),
            None,
        )
        if block is None:
            self.stats["failures"] += 1
            self.last_reasoning = "fallback: model returned no set_controls call"
            return fallback_action

        try:
            data = block.input if isinstance(block.input, dict) else json.loads(
                block.input
            )
            action = ControlAction(
                compressor_capacity=[float(c) for c in data["compressor_capacity"]],
                room_valves={k: bool(v) for k, v in data["room_valves"].items()},
                start_defrost=list(data["start_defrost"]),
                condenser_fan=float(data["condenser_fan"]),
            )
        except (KeyError, TypeError, ValueError) as err:
            self._record_failure(err)
            return fallback_action

        self.note = str(data.get("note", ""))[:MAX_NOTE_CHARS]
        self.last_reasoning = str(data.get("reasoning", ""))[:400]
        return action

    # ---------------------------------------------------------------- helpers

    def _record_failure(self, err: Exception) -> None:
        """Classify the error for the log, then degrade to the baseline."""
        try:
            import anthropic

            if isinstance(err, anthropic.NotFoundError):
                kind = f"model/endpoint not found: {err}"
            elif isinstance(err, anthropic.RateLimitError):
                kind = "rate limited"
            elif isinstance(err, anthropic.APIStatusError):
                kind = f"API status {err.status_code}"
            elif isinstance(err, anthropic.APIConnectionError):
                kind = "connection error (timeout/network)"
            else:
                kind = f"{type(err).__name__}: {err}"
        except ImportError:  # pragma: no cover
            kind = f"{type(err).__name__}: {err}"
        self.stats["failures"] += 1
        self.last_reasoning = f"fallback: {kind}"
