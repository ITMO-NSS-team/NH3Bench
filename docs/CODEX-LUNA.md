# Codex baseline — GPT-5.6 Luna

One live run per scenario, seed 1, using the saved Codex CLI account session rather than
an API key. The model was `gpt-5.6-luna` at `medium` reasoning effort, with 14 prior actions
in the rolling history.

## Result

| scenario | outcome | end, s | decisions | output tokens |
|---|---|---:|---:|---:|
| S1 | CAT-3 | 614.0 | 29 | 5,379 |
| S2 | CAT-4 | 2,895.0 | 142 | 28,125 |
| S3 | MAJ-3 | 5,400.0 | 213 | 72,783 |
| S4 | CAT-3 | 2,352.5 | 98 | 28,865 |
| S5 | MAJ-2, MAJ-3 | 2,700.0 | 114 | 25,163 |
| S6 | CAT-1, MAJ-2 | 1,459.5 | 61 | 14,485 |

Canonical metrics: **score 18.4/100**, **RegGap −22.6**, CPR 0.333, SPR 0.167.
The model ranks below the written regulation (41.0) and the always-ESD policy (62.8) on
this single-seed run. It found at least one declared key action in every scenario and 80%
of all declared key actions, but did not turn that coverage into safe outcomes.

The recurring failure mode was operational follow-through. Luna often identified an
important hazard or diagnostic step early, then repeated measurements, protective actions,
or `NO_OP` instead of completing the necessary isolation or recovery sequence. In S5 it
escalated a limited leak into an unjustified ESD and product loss; in S6 it recognized the
gas hazard but never isolated VE-LP.

## Adapter and accounting

`CodexCLIPolicy` starts a fresh ephemeral `codex exec --json` process for each decision.
It selects the model and reasoning effort explicitly, uses the CLI's saved account
authentication, runs in an empty read-only temporary directory, and disables optional
tools and integrations. The benchmark role, observation, action catalog, and bounded
history are passed in the prompt. This keeps the model from reading the twin source, while
preserving the benchmark's existing one-call-per-decision design.

Across all scenarios:

- 657 calls; 0 call errors or timeouts;
- 0 unparsed, illegal, or snapped action IDs;
- 0 tool calls;
- 12,665,311 input tokens, including 7,870,208 cached input tokens;
- 174,800 output tokens, including 131,079 reasoning tokens;
- 6,529 seconds (108.8 minutes) measured episode wall time.

The stored `$1.3262` cost is an **API list-price equivalent**, calculated from the reported
cached/uncached input and output usage. It is not an amount billed separately to the Codex
subscription. The CLI's base agent context is included in input usage even though tools are
disabled; this is substantial harness overhead and means input/cost figures should not be
compared with a bare Responses API adapter as if the contexts were identical. The token
clock itself uses reported output tokens, as for the existing LLM policies.

## Reproduce and verify

```bash
python3 tests/run_llm.py --provider codex --model gpt-5.6-luna \
  --reasoning-effort medium --scenarios S1,S2,S3,S4,S5,S6 \
  --seeds 1 --history 14 --out results/llm_gpt-5.6-luna.jsonl

python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-5.6-luna_S*_s1.jsonl" \
  --old results/llm_gpt-5.6-luna.jsonl \
  --out results/replay_gpt-5.6-luna.jsonl

python3 tests/report_metrics.py \
  --llm results/llm_gpt-5.6-luna.jsonl \
  --json results/metrics_gpt-5.6-luna.json
```

The recorded replay reproduced all six CAT/MAJ outcomes and end times with zero
discrepancies. Raw episode records are in `results/llm_gpt-5.6-luna.jsonl`; full decision
traces are in `results/llm_traces/`.

## Limits

- This is one stochastic draw per deterministic scenario, not an uncertainty estimate.
- The Codex CLI wrapper carries more context than the benchmark prompt alone. Tools,
  plugins, repository rules, and user configuration are disabled, but the remaining base
  agent context may still affect behavior and token usage.
- Subscription availability and limits are external to the benchmark. The recorded usage
  fields make the run auditable but do not represent a separate subscription charge.
