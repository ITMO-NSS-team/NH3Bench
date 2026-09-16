# Codex baseline — GPT-5.6 Sol

One live run per scenario, seed 1, using the same harness and settings as the Luna and
Terra baselines: saved Codex CLI account session, `medium` reasoning effort, 14 prior
actions in history, and a fresh ephemeral process for every decision.

## Result

| scenario | outcome | end, s | decisions | output tokens |
|---|---|---:|---:|---:|
| S1 | clean | 1,800.0 | 91 | 13,527 |
| S2 | CAT-1, MAJ-1 | 2,641.5 | 133 | 23,176 |
| S3 | MAJ-3 | 5,400.0 | 229 | 64,567 |
| S4 | clean | 3,600.0 | 163 | 39,035 |
| S5 | MAJ-3 | 2,700.0 | 128 | 23,378 |
| S6 | MAJ-2 | 1,500.0 | 70 | 12,429 |

Canonical metrics: **score 68.5/100**, **RegGap +27.5**, CPR 0.833, SPR 0.667.
In this single-seed run Sol substantially outperformed Terra (37.5), Luna (18.4), the
written regulation (41.0), and always-ESD (62.8). It is the first tested Codex model to
clear S1 and S6, and it also cleared S4.

Sol recognized the failed defrost sequence in S1 and manually closed hot gas early enough
to prevent the rupture. In S4 it protected personnel while leaving the feed path open,
avoiding the trapped-liquid rupture. In S6 it initially overreacted with ESD, but later
reopened the dismissed leak diagnosis and isolated VE-LP in time to avoid a catastrophe.

The remaining failures were procedural rather than parser or tool failures. In S2 the
model fixated on EV-03 and the visible gas leak, never checked the local VE-LP level glass,
and never isolated the high-pressure vessel. In S3 it correctly cleared the CD-02 permit
and purged non-condensables almost immediately, but never completed the required
`COND:PUMP_ON:CD-02` step, so product was lost. In S5 ventilation and instrument checks
were proportionate, but the unnecessary evacuation caused product loss.

Across all scenarios: 814 calls, 176,112 output tokens (126,959 reasoning), 16,912,265
input tokens (11,036,288 cached), 0 call errors, 0 illegal, unparsed, or snapped actions,
and 0 tool calls. The `$31.4407` stored cost is an API list-price equivalent, not a
separate charge on the signed-in subscription.

## Reproduce and verify

```bash
python3 tests/run_llm.py --provider codex --model gpt-5.6-sol \
  --reasoning-effort medium --scenarios S1,S2,S3,S4,S5,S6 \
  --seeds 1 --history 14 --out results/llm_gpt-5.6-sol.jsonl

python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-5.6-sol_S*_s1.jsonl" \
  --old results/llm_gpt-5.6-sol.jsonl \
  --out results/replay_gpt-5.6-sol.jsonl

python3 tests/report_metrics.py \
  --llm results/llm_gpt-5.6-sol.jsonl \
  --json results/metrics_gpt-5.6-sol.json
```

The replay reproduced all six CAT/MAJ outcomes and end times with zero discrepancies.
The CLI isolation and harness limitations are the same as documented for Luna in
`docs/CODEX-LUNA.md`.
