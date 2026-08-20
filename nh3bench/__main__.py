"""CLI: run and compare controllers on NH3Bench scenarios.

Examples::

    python -m nh3bench list
    python -m nh3bench run --scenario baseline_day --agent baseline
    python -m nh3bench run --scenario heatwave --agent haiku --log runs/hw.jsonl
    python -m nh3bench compare --scenario compressor_trip
"""

from __future__ import annotations

import argparse
import json
import sys

from .baseline import ThermostatBaseline
from .runner import run_episode
from .scenarios import SCENARIOS
from .scoring import ScoreReport


def _make_agent(kind: str, model: str):
    if kind == "baseline":
        return ThermostatBaseline()
    if kind == "haiku":
        from .agents import HaikuAgent

        return HaikuAgent(model=model)
    raise SystemExit(f"unknown agent '{kind}'")


def _print_report(r: ScoreReport) -> None:
    print(f"\n=== {r.agent} on '{r.scenario}' ({r.duration_h:g} h) ===")
    print(f"  energy            {r.energy_kwh:10.1f} kWh")
    print(f"  temp violations   {r.violation_degc_h:10.3f} degC*h")
    print(f"  safety trips      {r.safety_trips:10d}")
    print(f"  compressor starts {r.compressor_starts:10d}")
    print(f"  SCORE (lower=better) {r.score:10.1f}")
    if r.llm_calls:
        print(
            f"  llm: {r.llm_calls} calls, {r.llm_failures} fallbacks, "
            f"latency p50/p95 {r.latency_p50_s:.2f}/{r.latency_p95_s:.2f} s"
        )
        print(
            f"  tokens: in={r.tokens_in} cached={r.tokens_cached} "
            f"out={r.tokens_out}, est. cost ${r.cost_usd:.4f}"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="nh3bench")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list scenarios")

    for name in ("run", "compare"):
        p = sub.add_parser(name)
        p.add_argument("--scenario", default="baseline_day", choices=SCENARIOS)
        p.add_argument("--hours", type=float, default=None, help="override episode length")
        p.add_argument("--interval", type=float, default=60.0, help="control interval, s")
        p.add_argument("--dt", type=float, default=5.0, help="physics step, s")
        p.add_argument("--log", default=None, help="JSONL step log path")
        p.add_argument("--json", action="store_true", help="print report as JSON")
        p.add_argument("--verbose", action="store_true")
        p.add_argument("--model", default="claude-haiku-4-5")
        if name == "run":
            p.add_argument("--agent", default="baseline", choices=["baseline", "haiku"])

    args = parser.parse_args(argv)

    if args.cmd == "list":
        for s in SCENARIOS.values():
            print(f"{s.name:24s} {s.duration_h:4.0f} h  {s.description}")
        return 0

    scenario = SCENARIOS[args.scenario]
    agents = (
        [args.agent] if args.cmd == "run" else ["baseline", "haiku"]
    )
    reports = []
    for kind in agents:
        agent = _make_agent(kind, args.model)
        log = args.log
        if log and len(agents) > 1:
            log = log.replace(".jsonl", f".{kind}.jsonl")
        report = run_episode(
            scenario,
            agent,
            control_interval_s=args.interval,
            dt_s=args.dt,
            hours=args.hours,
            log_path=log,
            verbose=args.verbose,
        )
        reports.append(report)
        if args.json:
            print(json.dumps(report.as_dict(), ensure_ascii=False))
        else:
            _print_report(report)

    if len(reports) == 2 and not args.json:
        base, llm = reports
        if base.score > 0:
            delta = (base.score - llm.score) / base.score * 100.0
            print(
                f"\nhaiku vs baseline: score {llm.score:.1f} vs {base.score:.1f} "
                f"({delta:+.1f}% {'better' if delta > 0 else 'worse'})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
