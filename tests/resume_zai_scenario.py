"""Resume one interrupted Z.AI scenario from its exact recorded prefix."""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nh3twin.episode import Episode
from nh3twin.llm_policy import ZAIChatPolicy
from nh3twin.scenarios import SCENARIOS


class PrefixThenLivePolicy:
    def __init__(self, trace_path: str, live: ZAIChatPolicy):
        with open(trace_path, encoding="utf-8") as handle:
            self.prefix = [json.loads(line) for line in handle if line.strip()]
        self.i = 0
        self.live = live
        self.stats = live.stats
        self.name = live.name

    def act(self, obs, legal, ep):
        if self.i < len(self.prefix):
            row = self.prefix[self.i]
            if abs(float(row["t_rel"]) - float(obs.t_rel)) >= 0.1:
                raise RuntimeError(
                    f"resume divergence at step {self.i}: "
                    f"trace t={row['t_rel']}, replay t={obs.t_rel}"
                )
            self.i += 1
            return row["action"], int(row.get("tokens") or 0)
        return self.live.act(obs, legal, ep)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, choices=tuple(SCENARIOS))
    parser.add_argument("--trace", required=True)
    parser.add_argument("--old", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="glm-5.3")
    parser.add_argument("--reasoning-effort", default="max")
    parser.add_argument("--history", type=int, default=14)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    interrupted = None
    with open(args.old, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("scenario") == args.scenario and row.get("error"):
                interrupted = row
    if interrupted is None:
        raise RuntimeError("interrupted scenario row not found")

    pol_name = interrupted["policy"]
    live = ZAIChatPolicy(
        model=args.model,
        history=args.history,
        timeout=args.timeout,
        trace_path=args.trace,
        label=pol_name,
        verbose=True,
        reasoning_effort=args.reasoning_effort,
    )
    for key, value in (interrupted.get("llm") or {}).items():
        if hasattr(live.stats, key):
            setattr(live.stats, key, value)
    policy = PrefixThenLivePolicy(args.trace, live)

    ep = Episode(SCENARIOS[args.scenario], seed=int(interrupted["seed"]))
    ep._policy_name = pol_name
    result = ep.run(policy)
    result["policy"] = pol_name
    segment = ep.plant.segments.get("EV-03")
    result["fatigue_EV03"] = round(segment.fatigue, 3) if segment else None
    result["max_dose"] = max(
        [operator["dose"] for operator in result["operators"].values()] or [0.0]
    )
    result["milk_max"] = round(
        max(point[1]["T_MILK"] for point in ep.trace), 2
    ) if ep.trace else None
    result["pcond_max"] = round(
        max(point[1]["P_COND"] for point in ep.trace), 2
    ) if ep.trace else None
    result["action_counts"] = {}
    for record in ep.log:
        key = record.action.split(":")[0]
        result["action_counts"][key] = result["action_counts"].get(key, 0) + 1
    result["llm"] = vars(policy.stats)
    result["llm"]["model"] = args.model
    result["llm"]["history"] = args.history
    result["llm"]["reasoning_effort"] = args.reasoning_effort
    result["llm"]["tokens_per_decision"] = round(
        policy.stats.out_tokens / max(policy.stats.calls, 1), 1
    )
    result["trace"] = os.path.relpath(
        args.trace,
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ).replace("\\", "/")
    result["resumed_from_prefix_steps"] = len(policy.prefix)
    if interrupted.get("usage_prefix_incomplete"):
        result["usage_prefix_incomplete"] = True

    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(
        f"resumed {args.scenario}: prefix={len(policy.prefix)}, "
        f"CAT={result['CAT']} MAJ={result['MAJ']} t_end={result['t_end_s']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
