# NH3Bench

A benchmark for **real-time LLM control of an industrial ammonia (NH₃/R717)
refrigeration plant** serving a food-processing workshop — plus a reference
agent built on **Claude Haiku 4.5**.

The controller (LLM or classic) sees one telemetry snapshot per control step
and must keep three cold rooms inside their food-safety temperature bands
while minimising energy, avoiding safety cutouts and not short-cycling the
compressors. The workshop's *demands* — production deliveries of warm
product, door openings, heat waves, equipment faults — are defined by the
benchmark scenarios, not by the controller.

## The plant

Pumped-recirculation ammonia system with a single suction level (a deliberate
simplification of the classic two-stage industrial layout — and a real
control challenge: warm rooms held open raise the suction pressure and starve
the freezer):

| | |
|---|---|
| Cold rooms | freezer (−20 °C), chill store (0 °C), processing hall (+8 °C), each with a flooded air cooler behind a liquid-supply solenoid valve |
| Compressors | 2 fixed-speed + 1 VFD reciprocating units on a common suction accumulator, min-run/min-off times |
| Condenser | evaporative, variable-speed fan (power ∝ speed³), thermal inertia |
| Interlocks | HP cutout 1650 kPa, LP cutout 60 kPa — trip **all** compressors with a lockout, exactly like real pressure switches, on every physics substep |
| Extras | frost build-up degrading cooler UA, hot-gas-style defrost that injects heat, warm-product pull-down loads, door infiltration |

The lumped-parameter model follows the structure of the supermarket
refrigeration benchmark (Larsen et al.) — display case ↔ suction manifold ↔
compressor rack mass balance — with NH₃ saturation properties (tabulated IIR
data, CoolProp used automatically if installed) and polytropic compressor
work as in NIST CYCLE_D-HX / the Rasmussen dynamic-modelling tutorials.

## Scoring

Episode cost, lower is better:

```
score = energy_kWh · 1  +  °C·h outside hard bands · 50  +  safety trips · 500  +  compressor starts · 2
```

## Scenarios

| scenario | the demand |
|---|---|
| `baseline_day` | ordinary shift, four warm-product deliveries |
| `heatwave` | 37 °C peak — condenser margin becomes the binding constraint |
| `compressor_trip` | C1 lost for 3 h mid-shift, capacity must be rationed |
| `door_left_open` | freezer door open 40 min twice — infiltration + frosting |
| `fouled_condenser_surge` | 30 % condenser fouling + double-size delivery surge |

The rule-based thermostat baseline handles the easy scenarios cleanly
(score ≈ 480 on `baseline_day`) and falls apart on the hard ones
(≈ 9 800 on `heatwave` with 17 HP trips) — that gap is the benchmark.

## The Haiku agent

`nh3bench/agents/haiku.py` — a real-time operator on `claude-haiku-4-5`:

* **One request per control step, no agentic loop.** The action space is a
  single strict tool (`set_controls`) and `tool_choice` forces it, so every
  step is one round-trip returning schema-validated JSON.
* **Prompt caching.** The tool definition + static "operator manual" system
  prompt form a stable cached prefix (`cache_control: ephemeral`); only a
  compact telemetry JSON changes between steps → ~10× cheaper input and
  faster TTFT from step 2 onward.
* **Bounded memory.** No growing history: the agent carries state in a
  ≤500-char self-written scratchpad (`note`) echoed back in the next
  observation. Requests never grow, the cache prefix never breaks.
* **Deterministic degradation.** 30 s timeout, one SDK retry; any API error
  or malformed reply falls back to the thermostat baseline *for that step* —
  the plant is never left uncontrolled. Below the agent sits a hard safety
  layer (min-run/off times, lockouts, defrost hygiene, fan floor) that clamps
  every command and reports its overrides back to the model, and the plant
  itself enforces HP/LP pressure switches. The LLM proposes; interlocks
  dispose.

A 12-hour episode at a 60 s control interval is ~720 calls ≈ $0.5 with
caching.

## Quickstart

```bash
pip install -e .[llm]           # or: pip install -e . (baseline only, no SDK)

python -m nh3bench list
python -m nh3bench run --scenario baseline_day --agent baseline

export ANTHROPIC_API_KEY=sk-ant-...
python -m nh3bench run --scenario heatwave --agent haiku --log runs/hw.jsonl
python -m nh3bench compare --scenario compressor_trip
```

Useful flags: `--hours 2` (short episode), `--interval 60` (control step, s),
`--verbose` (live trace), `--json` (machine-readable report), `--model`
(any Claude model id, default `claude-haiku-4-5`).

Every step is logged to JSONL (`--log`): observation, action, safety
overrides, alarms, the model's one-line reasoning, its scratchpad and call
latency — enough to audit any decision after the fact.

## Tests

```bash
pip install -e .[dev]
pytest
```

The agent tests use a fake API client — no key or network needed; they pin
the request shape (model id, forced strict tool choice, cache breakpoints)
and the fallback behaviour.

## Layout

```
nh3bench/
  properties.py   NH3 saturation properties (table + optional CoolProp)
  plant.py        lumped-parameter plant ODEs + hard pressure interlocks
  scenarios.py    demand profiles: deliveries, doors, faults, weather
  safety.py       command-clamping safety layer between agent and actuators
  baseline.py     thermostat + staged-compressor reference controller
  scoring.py      episode cost and report
  runner.py       episode loop, observation builder, JSONL logging
  agents/haiku.py Claude Haiku 4.5 operator
tests/
```
