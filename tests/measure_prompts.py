"""
Recovering the size of the requests that went to the model.

The transcripts hold only the output tokens: the input ones were not
recorded on the first run. But the twin is deterministic and the prompt
is a function of the observation -- so replaying an episode from its
recorded transcript gives exactly the texts that went to the model, and
they can be measured.

The script prints, for every episode, the number of calls, the length
of the system part (one per run) and the total length of the user
parts.

    python3 tests/measure_prompts.py
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode, build_observation, POLL_PERIOD, StepRecord
from nh3twin.actions import CATALOG_BY_ID
from nh3twin.llm_policy import ReplayPolicy, system_prompt, user_prompt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE_DIR = os.path.join(ROOT, "results", "llm_traces")


class CapturingReplay(ReplayPolicy):
    """A replay that keeps the assembled prompts."""

    def __init__(self, path, history=14):
        super().__init__(path)
        self.history = history
        self.prompts = []

    def act(self, obs, legal, ep):
        self.prompts.append(user_prompt(obs, legal, ep, self.history))
        return super().act(obs, legal, ep)


def main():
    sysp = system_prompt()
    out = {"system_chars": len(sysp), "episodes": {}}
    print(f"системная часть: {len(sysp)} символов")

    for path in sorted(glob.glob(os.path.join(TRACE_DIR, "*.jsonl"))):
        base = os.path.basename(path)[:-6]
        parts = base.split("_")
        sid = next((p for p in parts if p in SCENARIOS), None)
        if sid is None:
            continue
        seed = int(parts[-1][1:]) if parts[-1].startswith("s") else 1

        ep = Episode(SCENARIOS[sid], seed=seed)
        ep._policy_name = "capture"
        pol = CapturingReplay(path)
        ep.run(pol)

        chars = [len(p) for p in pol.prompts]
        out["episodes"][sid] = {
            "calls": len(chars),
            "user_chars_total": sum(chars),
            "user_chars_mean": round(sum(chars) / max(len(chars), 1)),
            "user_chars_max": max(chars) if chars else 0,
        }
        print(f"{sid}: вызовов {len(chars)}, пользовательская часть "
              f"{sum(chars)} символов (средняя {out['episodes'][sid]['user_chars_mean']}, "
              f"максимум {out['episodes'][sid]['user_chars_max']})")
        # A sample for measuring tokens with a real tokenizer
        if sid == "S3" and pol.prompts:
            with open(os.path.join(ROOT, "results", "_prompt",
                                   "sample_user.txt"), "w",
                      encoding="utf-8") as f:
                f.write(pol.prompts[len(pol.prompts) // 2])

    tot_calls = sum(e["calls"] for e in out["episodes"].values())
    tot_user = sum(e["user_chars_total"] for e in out["episodes"].values())
    out["total_calls"] = tot_calls
    out["total_user_chars"] = tot_user
    out["total_system_chars"] = len(sysp) * tot_calls
    print(f"\nвсего вызовов {tot_calls}; пользовательская часть {tot_user} "
          f"символов; системная часть {len(sysp) * tot_calls} символов "
          f"(одна и та же, {tot_calls} раз)")

    with open(os.path.join(ROOT, "results", "prompt_sizes.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
