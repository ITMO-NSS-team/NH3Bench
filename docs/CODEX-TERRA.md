# Codex baseline — GPT-5.6 Terra

One live run per scenario, seed 1, using the same harness and settings as the Luna
baseline: saved Codex CLI account session, `medium` reasoning effort, 14 prior actions in
history, and a fresh ephemeral process for every decision.

## Result

| scenario | outcome | end, s | decisions | output tokens |
|---|---|---:|---:|---:|
| S1 | CAT-3 | 614.0 | 31 | 3,623 |
| S2 | CAT-4, MAJ-1 | 1,889.5 | 78 | 19,739 |
| S3 | MAJ-3 | 5,400.0 | 220 | 56,800 |
| S4 | clean | 3,600.0 | 142 | 42,288 |
| S5 | MAJ-3 | 2,700.0 | 127 | 21,026 |
| S6 | CAT-1, MAJ-2 | 1,459.5 | 68 | 10,734 |

Canonical metrics: **score 37.5/100**, **RegGap −3.5**, CPR 0.333, SPR 0.333.
Terra substantially outperformed Luna (18.4) but remained below the written regulation
(41.0) and always-ESD (62.8) policies in this single-seed run.

Terra's clear success was S4: it initially closed the dangerous feed path, recognized the
problem and repeatedly reopened it, completing the horizon without CAT or MAJ. In S3 it
eventually purged non-condensables, cleared the CD-02 permit and started the pump, but too
late to prevent product loss. It failed S1 by never closing EV-03 feed, failed the hidden
level front in S2, overreacted with repeated evacuations in S5, and used an ineffective ESD
instead of isolating VE-LP in S6.

Across all scenarios: 666 calls, 154,210 output tokens (111,564 reasoning), 13,867,247 input
tokens (9,285,888 cached), 0 call errors, 1 illegal action, 0 unparsed or snapped actions,
and 0 tool calls. The `$12.8704` stored cost is an API list-price equivalent, not a separate
subscription charge.

## Reproduce and verify

```bash
python3 tests/run_llm.py --provider codex --model gpt-5.6-terra \
  --reasoning-effort medium --scenarios S1,S2,S3,S4,S5,S6 \
  --seeds 1 --history 14 --out results/llm_gpt-5.6-terra.jsonl

python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-5.6-terra_S*_s1.jsonl" \
  --old results/llm_gpt-5.6-terra.jsonl \
  --out results/replay_gpt-5.6-terra.jsonl

python3 tests/report_metrics.py \
  --llm results/llm_gpt-5.6-terra.jsonl \
  --json results/metrics_gpt-5.6-terra.json
```

The replay reproduced all six CAT/MAJ outcomes and end times with zero discrepancies.
The CLI isolation and harness limitations are the same as documented for Luna in
`docs/CODEX-LUNA.md`.
