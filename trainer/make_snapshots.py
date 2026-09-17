# -*- coding: utf-8 -*-
"""
Task snapshots at the moment the shift is accepted.

    py trainer/make_snapshots.py            # build the snapshots
    py trainer/make_snapshots.py --check    # verify they match a warm-up

Why. Every task starts with bringing the plant up to its regime: one and
a half to two hours of model time, 7-14 thousand integration steps. On
CPython that is 20-42 s, in a browser three to five times longer, and
that time is spent again on every "watch again" -- at a stand a visitor
will not wait that long.

The episode state after the warm-up fits entirely into 42 KB and is
restored in a millisecond. The physics does not change in the process: a
snapshot is exactly the object a warm-up would have produced, and the
--check run confirms that continuing the computation from a snapshot
matches continuing from a warm-up step by step.

A snapshot depends on the class layout of the simulator. If that has
changed, an old snapshot cannot be loaded -- the driver then silently
computes the warm-up as before, and it is enough to regenerate the
snapshots. That is why the format version and the commit are written
into them.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import pickle
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

sys.path.insert(0, os.path.join(ROOT, "trainer"))

from nh3twin.episode import Episode                                 # noqa: E402
from nh3twin.scenarios import SCENARIOS                             # noqa: E402
# The physics digest is computed by the driver -- with the same function it
# later verifies with.
from driver import (sources_digest, SNAP_DIR,                       # noqa: E402
                    _mk_array, _mk_rng)

# The directory is taken from the driver rather than set here: otherwise
# snapshots are written to one place and looked for in another -- and the
# snapshot path could not be checked locally.
OUT_DIR = SNAP_DIR
# Protocol 5 exists both in CPython 3.11 and in the Python 3.12 inside Pyodide.
PROTO = 5
VERSION = 1


class _PortablePickler(pickle.Pickler):
    """
    A snapshot independent of the numpy version.

    numpy's internal representations are incompatible between 1.x and 2.x by
    module names, and numpy in the browser is its own. So an array is
    written as a list of numbers, a scalar as a plain float, a generator as
    its state; the driver assembles them back with whatever numpy is there.
    """

    def reducer_override(self, obj):
        import numpy as np
        if isinstance(obj, np.ndarray):
            return (_mk_array, (obj.tolist(), str(obj.dtype)))
        if isinstance(obj, np.random.Generator):
            return (_mk_rng, (obj.bit_generator.state,))
        if isinstance(obj, np.generic):
            v = obj.item()
            return (float, (v,)) if isinstance(v, float) else (int, (v,))
        return NotImplemented


def build_one(sid: str) -> bytes:
    ep = Episode(SCENARIOS[sid], seed=1)
    buf = io.BytesIO()
    _PortablePickler(buf, protocol=PROTO).dump(
        {"v": VERSION, "sid": sid, "ep": ep, "digest": sources_digest()})
    return buf.getvalue()


def build(sids=None) -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    out = {}
    for sid in (sids or list(SCENARIOS)):
        t0 = time.time()
        blob = build_one(sid)
        path = os.path.join(OUT_DIR, sid + ".pkl")
        with open(path, "wb") as fh:
            fh.write(blob)
        out[sid] = blob
        print(f"  {sid}: {len(blob) / 1024:6.0f} КБ "
              f"(прогрев занял {time.time() - t0:5.1f} с)")
    return out


def portability(sid: str) -> list:
    """
    References that may not exist in another numpy version.

    The check is needed because a non-portable snapshot does not break
    visibly: it simply fails to load in the browser, the driver falls back to
    a warm-up, and the whole thing looks like "somehow slow".
    """
    import io as _io
    import pickletools
    bad = []
    with open(os.path.join(OUT_DIR, sid + ".pkl"), "rb") as fh:
        blob = fh.read()
    for op, arg, _pos in pickletools.genops(_io.BytesIO(blob)):
        if not isinstance(arg, str):
            continue
        # numpy internals: private modules and anything related to random.
        if (arg.startswith("numpy._") or arg.startswith("numpy.core")
                or arg.startswith("numpy.random")):
            bad.append(arg)
    return sorted(set(bad))


def check(sids=None) -> int:
    """
    A snapshot must give the same trajectory as a warm-up. Otherwise
    watching a recording would show an episode other than the one the model
    had -- unnoticeably, and therefore dangerously.
    """
    import numpy as np
    bad = 0
    for sid in (sids or list(SCENARIOS)):
        path = os.path.join(OUT_DIR, sid + ".pkl")
        if not os.path.exists(path):
            print(f"  {sid}: снимка нет"); bad += 1; continue
        with open(path, "rb") as fh:
            snap = pickle.load(fh)
        a = snap["ep"]
        b = Episode(SCENARIOS[sid], seed=1)          # an honest warm-up
        d0 = float(np.max(np.abs(a.plant.y - b.plant.y)))
        ta = abs(a.plant.t - b.plant.t)
        # and the continuation: five minutes of the task ahead
        a.advance(300.0); b.advance(300.0)
        d1 = float(np.max(np.abs(a.plant.y - b.plant.y)))
        refs = portability(sid)
        ok = d0 < 1e-9 and ta < 1e-9 and d1 < 1e-9 and not refs
        if not ok:
            bad += 1
        print(f"  {sid}: расхождение на старте {d0:.3e}, "
              f"через 300 с {d1:.3e}, "
              f"непереносимых ссылок {len(refs)} -> "
              f"{'совпало' if ok else 'НЕГОДЕН'}")
        for r in refs[:4]:
            print(f"      зависит от версии numpy: {r}")
    return bad


def as_files() -> dict:
    """Snapshots as {name: base64} for embedding into the trainer HTML."""
    out = {}
    if not os.path.isdir(OUT_DIR):
        return out
    for name in sorted(os.listdir(OUT_DIR)):
        if not name.endswith(".pkl"):
            continue
        with open(os.path.join(OUT_DIR, name), "rb") as fh:
            out["snap/" + name] = base64.b64encode(fh.read()).decode()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    sids = [s for s in args.scenarios.split(",") if s] or None
    if args.check:
        sys.exit(1 if check(sids) else 0)
    print("сборка снимков (каждый требует полного прогрева):")
    build(sids)
    print("\nпроверка:")
    sys.exit(1 if check(sids) else 0)


if __name__ == "__main__":
    main()
