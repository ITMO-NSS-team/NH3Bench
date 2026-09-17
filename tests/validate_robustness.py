# -*- coding: utf-8 -*-
"""
Validation V6 (docs/VALIDATION.md): robustness of the signs of the
calibration matrix against model error.

The twin is not required to be accurate "to the point"; what is
required is that the benchmark's verdicts do not depend on a heat
transfer coefficient or a strength derating factor being known to
within ±20 %. The script plays out K "perturbed worlds"
(log-uniform scaling of the uncertain configuration parameters, one
multiplier per parameter -- a systematic model error rather than
manufacturing spread), re-runs the calibration policies and checks
whether the signs of a scenario's admission are preserved relative to
the unperturbed world 0.

Usage (pilot, about 30 min):
  python tests/validate_robustness.py --scenarios S1,S4 \
         --policies null,oracle,regulation --draws 6

It writes line by line into results/validation/robustness.jsonl
(cached by the scenario/policy/world key) -- an interrupted run is
completed by starting it again.
"""

import sys, os, json, time, argparse, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from nh3twin import config
from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode
from nh3twin.policies import (NullPolicy, RandomPolicy, OraclePolicy,
                              RegulationPolicy, ESDPolicy)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results", "validation")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "robustness.jsonl")


def make_policy(name, seed):
    return {"null": lambda: NullPolicy(),
            "random": lambda: RandomPolicy(seed=seed),
            "oracle": lambda: OraclePolicy(),
            "regulation": lambda: RegulationPolicy(),
            "esd": lambda: ESDPolicy()}[name]()


# ---------------------------------------------------------------------------
# Perturbed parameters: (name, multiplier range, application to
# config.DEFAULT). The ranges are justified in docs/VALIDATION.md §V6. One
# multiplier per parameter -- it represents a MODEL error, common to equipment
# of one type.
# ---------------------------------------------------------------------------

def _scale_evap(attr):
    def apply(cfg, f):
        for e in cfg.evaporators:
            setattr(e, attr, getattr(e, attr) * f)
    return apply


def _scale_vessel(attr):
    def apply(cfg, f):
        for v in cfg.vessels:
            setattr(v, attr, getattr(v, attr) * f)
    return apply


def _scale_room(attr):
    def apply(cfg, f):
        for r in cfg.rooms:
            setattr(r, attr, getattr(r, attr) * f)
    return apply


def _scale_comp_a0(attr):
    def apply(cfg, f):
        for c in cfg.compressors:
            a = getattr(c, attr)
            setattr(c, attr, (a[0] * f,) + tuple(a[1:]))
    return apply


PERTURB = [
    ("UA_dry",         0.80, 1.25, _scale_evap("UA_dry")),
    ("defrost_hotgas", 0.80, 1.25, _scale_evap("defrost_hotgas")),
    ("frost_rate_k",   0.70, 1.40, _scale_evap("frost_rate_k")),
    ("UA_amb",         0.80, 1.25, _scale_vessel("UA_amb")),
    ("prv_capacity",   0.80, 1.25, _scale_vessel("prv_capacity")),
    ("UA_env",         0.80, 1.25, _scale_room("UA_env")),
    ("eta_v_a0",       0.95, 1.05, _scale_comp_a0("eta_v_coef")),
    ("eta_is_a0",      0.95, 1.05, _scale_comp_a0("eta_is_coef")),
    # dynamic_derate is applied to the segments of an already built Plant --
    # see run_one
    ("dynamic_derate", 0.75, 1.25, None),
]


def snapshot(cfg):
    """The exact original values of every perturbed attribute."""
    snap = []
    for objs, attrs in ((cfg.evaporators, ("UA_dry", "defrost_hotgas",
                                           "frost_rate_k")),
                        (cfg.vessels, ("UA_amb", "prv_capacity")),
                        (cfg.rooms, ("UA_env",)),
                        (cfg.compressors, ("eta_v_coef", "eta_is_coef"))):
        for o in objs:
            for a in attrs:
                snap.append((o, a, getattr(o, a)))
    return snap


def restore(snap):
    for o, a, v in snap:
        setattr(o, a, v)


def draw_factors(world):
    """
    World 0 -- no perturbations (the reference for the signs). Beyond that,
    deterministically from the world number, log-uniform over the
    parameter's range.
    """
    if world == 0:
        return {name: 1.0 for name, *_ in PERTURB}
    rng = np.random.default_rng(1000 + world)
    return {name: float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
            for name, lo, hi, _ in PERTURB}


def run_one(sid, pol_name, world, seed=1):
    factors = draw_factors(world)
    snap = snapshot(config.DEFAULT)
    try:
        for name, lo, hi, apply in PERTURB:
            if apply is not None:
                apply(config.DEFAULT, factors[name])
        ep = Episode(SCENARIOS[sid], seed=seed)
        # impact strength -- on the segments of an already built plant;
        # perturbing it after the warm-up is correct: the parameter matters
        # only at the moment of the shock
        for seg in ep.plant.segments.values():
            seg.dynamic_derate *= factors["dynamic_derate"]
        r = ep.run(make_policy(pol_name, seed))
        row = {"scenario": sid, "policy": pol_name, "world": world,
               "seed": seed, "factors": factors,
               "CAT": r.get("CAT", []), "MAJ": r.get("MAJ", []),
               "t_end_s": r.get("t_end_s"),
               "prevented": r.get("prevented"),
               "released_kg": r.get("released_kg")}
    except Exception:
        row = {"scenario": sid, "policy": pol_name, "world": world,
               "seed": seed, "factors": factors,
               "error": traceback.format_exc()[-600:]}
    finally:
        restore(snap)
    return row


def already_done():
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["scenario"], r["policy"], r["world"]))
                except json.JSONDecodeError:
                    pass
    return done


def summarize():
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    rows = [r for r in rows if "error" not in r]
    ref = {(r["scenario"], r["policy"]): bool(r["CAT"])
           for r in rows if r["world"] == 0}
    sids = sorted({r["scenario"] for r in rows})
    print("\n===== СВОДКА: доля миров с сохранением знака (против мира 0) =====")
    for sid in sids:
        parts = []
        for pol in ("null", "oracle", "regulation"):
            sel = [r for r in rows
                   if r["scenario"] == sid and r["policy"] == pol
                   and r["world"] > 0]
            if not sel or (sid, pol) not in ref:
                continue
            same = sum(1 for r in sel if bool(r["CAT"]) == ref[(sid, pol)])
            parts.append(f"{pol} {same}/{len(sel)}")
        print(f"  {sid}: " + " · ".join(parts))
    bad = [r for r in rows if r["world"] > 0
           and (r["scenario"], r["policy"]) in ref
           and bool(r["CAT"]) != ref[(r["scenario"], r["policy"])]]
    for r in bad:
        hot = {k: round(v, 2) for k, v in r["factors"].items()
               if abs(v - 1) > 0.12}
        print(f"  ! знак сменился: {r['scenario']}/{r['policy']} мир {r['world']}"
              f" CAT={r['CAT']} факторы {hot}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="S1,S4")
    ap.add_argument("--policies", default="null,oracle,regulation")
    ap.add_argument("--draws", type=int, default=6,
                    help="число возмущённых миров (мир 0 добавляется всегда)")
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()

    if not args.summary_only:
        sids = args.scenarios.split(",")
        pols = args.policies.split(",")
        done = already_done()
        total = len(sids) * len(pols) * (args.draws + 1)
        n = 0
        for world in range(args.draws + 1):
            for sid in sids:
                for pol in pols:
                    n += 1
                    if (sid, pol, world) in done:
                        print(f"[{n}/{total}] {sid}/{pol}/мир{world} уже есть",
                              flush=True)
                        continue
                    t0 = time.time()
                    row = run_one(sid, pol, world)
                    with open(OUT, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(f"[{n}/{total}] {sid}/{pol}/мир{world}: "
                          f"CAT={row.get('CAT')} ({time.time() - t0:.0f} с)",
                          flush=True)
    summarize()


if __name__ == "__main__":
    main()
