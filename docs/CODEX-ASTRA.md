# Codex baseline — GPT-6 Astra

One live run per scenario, seed 1, using the same logical harness settings as the Luna,
Terra, and Sol baselines: saved Codex CLI account session, `medium` reasoning effort, 14
prior actions in history, and a fresh ephemeral process for every decision. The independent
episodes S1–S3 and S4–S6 were run concurrently to reduce wall-clock time; virtual time,
observations, model context, and seeds are unaffected by wall-clock concurrency.

## Result

| scenario | outcome | end, s | decisions | output tokens |
|---|---|---:|---:|---:|
| S1 | clean | 1,800.0 | 104 | 6,206 |
| S2 | clean | 3,600.0 | 209 | 12,554 |
| S3 | MAJ-3 | 5,400.0 | 308 | 24,146 |
| S4 | clean | 3,600.0 | 200 | 14,492 |
| S5 | MAJ-3 | 2,700.0 | 147 | 10,877 |
| S6 | MAJ-2 | 1,500.0 | 83 | 5,591 |

Canonical metrics: **score 81.5/100**, **RegGap +40.5**, CPR 1.000, SPR 0.833.
In this single-seed run Astra outperformed Sol (68.5), Terra (37.5), Luna (18.4), the
written regulation (41.0), and always-ESD (62.8). It is the first tested Codex model to
prevent catastrophe in all six scenarios and the first to clear S2.

In S1 Astra recognized the failed defrost sequence and manually closed hot gas by 57 s.
In S2 it checked the local VE-LP level glass at 290 s and closed LV-LP at 1,286 s; that
non-oracle but effective route prevented both compressor damage and relief discharge.
In S4 it protected personnel while keeping the feed path open, avoiding the trapped-liquid
rupture.

The weaknesses were still procedural. In S3 Astra repeatedly cleared the CD-02 permit and
purged non-condensables but never issued `COND:PUMP_ON:CD-02`, causing product loss. In S5
it correctly cross-checked and recalibrated the detector, then evacuated the hall anyway,
also losing product. In S6 it reopened the dismissed diagnosis, visually confirmed the
real leak at 740 s, and isolated VE-LP at 826 s, but NH3 had already reached the automatic
high-high trip threshold; MAJ-2 was caused by `NH3_HIHI_MACHINEROOM`, not a model-issued
ESD command.

Across all scenarios: 1,051 calls, 73,866 output tokens (5,720 reasoning), 23,161,305
input tokens (15,725,696 cached), 0 call errors, 0 illegal, unparsed, or snapped actions,
and 0 tool calls. The `$93.7751` stored cost is an API list-price equivalent, not a
separate charge on the signed-in subscription.

## Reproduce and verify

```bash
python3 tests/run_llm.py --provider codex --model gpt-6-astra \
  --reasoning-effort medium --scenarios S1,S2,S3,S4,S5,S6 \
  --seeds 1 --history 14 --out results/llm_gpt-6-astra.jsonl

python3 tests/report_metrics.py \
  --llm results/llm_gpt-6-astra.jsonl \
  --json results/metrics_gpt-6-astra.json
```

For the recorded concurrent run, exact replay uses the saved head and tail separately:

```bash
python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-6-astra_S[1-3]_s1.jsonl" \
  --old results/llm_gpt-6-astra_head.jsonl \
  --out results/replay_gpt-6-astra_head.jsonl

python3 tests/replay_llm.py \
  --traces "results/llm_traces/llm_gpt-6-astra_tail_S[4-6]_s1.jsonl" \
  --old results/llm_gpt-6-astra_tail.jsonl \
  --out results/replay_gpt-6-astra_tail.jsonl
```

The two replay passes reproduced all six CAT/MAJ outcomes and end times with zero
discrepancies. The CLI isolation and harness limitations are the same as documented for
Luna in `docs/CODEX-LUNA.md`.
