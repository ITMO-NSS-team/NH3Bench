"""
The benchmark as an environment driven one call at a time.

Episode.run owns its loop: it asks a policy for (action, tokens) and moves
the plant. A harness on MCP owns its own loop, so here the loop is turned
inside out, as trainer/driver.Session does for a person: each call moves the
plant by what that call costs. On the canonical path -- one `act` per
decision, deliberation charged from the model's tokens -- the plant receives
exactly the advance() calls Episode.run makes, so it cannot tell the two
apart (tests/test_conformance.py checks it against Episode.run).

Two surfaces, kept apart:

  agent    observe, list_actions, act, wait -- what server.py publishes;
  control  reset, charge_tokens, probe_state, finish -- for the stand only
           (rule FR-1.3). Nothing on the agent side reads plant.tags(): the
           panel shows indicated readings (episode.indicated_tags), and the
           truth leaves only through finish() and probe_state().

Time is charged on every call, not only on actions: while the model thinks
the plant runs, whatever tool the thought ends in. A deliberation that ends
in `observe` moves the plant before the reading is taken; one that ends in a
decision (`act`, `wait`) is applied as Episode.run applies it -- always,
even when it is zero, because Episode.advance takes at least one step.
"""

from __future__ import annotations

import copy
import hashlib
import os
import pickle
import time
from pathlib import Path

from nh3twin.actions import CATALOG, CATALOG_BY_ID
from nh3twin.episode import Episode, POLL_PERIOD, StepRecord, build_observation
from nh3twin.scenarios import SCENARIOS

from . import texts
from .instance import Instance

WAIT_MIN, WAIT_MAX = 10.0, 600.0
CATEGORIES = tuple(dict.fromkeys(a.category for a in CATALOG))


def destructive(a) -> bool:
    """
    Whether a command changes the plant (MCP's destructiveHint, per action).

    Only looking is harmless: NO_OP and the measurement dispatches. Everything
    else moves equipment, people or alarms -- including the ESD, which is a
    legal answer in some scenarios and the accident itself in others.
    """
    return not (a.aid == "NO_OP" or a.aid.startswith("MEASURE:"))


# ---------------------------------------------------------------------------
# Warm-up cache
#
# A scenario starts with 1-2 simulated hours of warm-up (~35 s of CPU). The
# warmed episode is computed once per process and deep-copied for every run:
# the copy is the same object state (RNG included), so it continues exactly
# as a fresh warm-up would. Across processes, NH3MCP_CACHE names a directory
# for pickles keyed by a digest of the physics sources -- the same files
# trainer/driver.sources_digest covers, for the same reason: a pickle taken
# before a coefficient changed would load without error and be wrong.
# ---------------------------------------------------------------------------

_DIGEST_FILES = ("props.py", "config.py", "plant.py", "piping.py",
                 "dispersion.py", "control.py", "faults.py", "actions.py",
                 "episode.py", "scenarios.py")
_WARM: dict = {}


def sources_digest() -> str:
    import nh3twin
    base = Path(nh3twin.__file__).parent
    h = hashlib.sha256()
    for name in _DIGEST_FILES:
        h.update(name.encode())
        h.update((base / name).read_bytes())
    return h.hexdigest()[:16]


def warm_episode(sid: str, seed: int = 1) -> Episode:
    """The warmed episode for (scenario, seed). Callers must copy it."""
    key = (sid, seed)
    if key in _WARM:
        return _WARM[key]
    cache = os.environ.get("NH3MCP_CACHE")
    path = None
    if cache:
        path = Path(cache) / f"{sid}_s{seed}_{sources_digest()}.pkl"
        if path.exists():
            with open(path, "rb") as fh:
                _WARM[key] = pickle.load(fh)
            return _WARM[key]
    ep = Episode(SCENARIOS[sid], seed=seed)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(ep, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)
    _WARM[key] = ep
    return ep


class NH3Env:

    def __init__(self, instance: Instance):
        self.inst = instance
        self.reset()

    # ================= control surface =================

    def reset(self) -> None:
        """A clean start (rule R2): a fresh copy of the warmed plant."""
        inst = self.inst
        self.ep = copy.deepcopy(warm_episode(inst.scenario, inst.seed))
        self.ep._policy_name = inst.label
        self.lang = inst.lang
        self.pending_s = 0.0            # deliberation not yet applied, virtual s
        self.tokens_reported = 0        # tokens the stand fed to the clock
        self.calls = {"observe": 0, "list_actions": 0, "act": 0, "wait": 0,
                      "read_regulation": 0}
        self.rejected = []              # [t, aid, why] -- calls that did nothing
        self.waits = []                 # [t, seconds] -- NO_OPs with a dwell
        # Every agent call with the deliberation it was charged: enough to
        # replay the run exactly (replay()), so the outcome does not depend on
        # the server process living until the shift is played out.
        self.journal = []
        self._fed = 0                   # tokens fed for the call in progress
        self._replay_think = None       # set by replay(): the charge to apply
        self._record = None
        self._wall0 = self._wall_last = time.monotonic()
        # The run-up before the first decision, as in Episode.run.
        self.ep.advance(POLL_PERIOD)

    def charge_tokens(self, n: int) -> None:
        """
        Output tokens the model produced since the previous call.

        Only the `tokens` clock reads them. The stand's gateway is the one
        that knows them (the model route counts them); the agent can never
        report its own -- no agent tool takes a token count.
        """
        clk = self.inst.clock
        if clk.mode != "tokens" or n <= 0:
            return
        self.tokens_reported += int(n)
        self._fed += int(n)
        self.pending_s += n / clk.think_rate

    def probe_state(self) -> dict:
        """The true state, for oracles and debugging. Never on the agent side."""
        ep, p = self.ep, self.ep.plant
        return {"t": round(p.t - ep.t0, 1), "done": ep.done(),
                "CAT": sorted(p.cat_flags), "MAJ": sorted(p.maj_flags),
                "released_kg": round(p.disp.m_released_total, 1),
                "esd": bool(p.esd_active),
                "operators": p.summary()["operators"]}

    @property
    def done(self) -> bool:
        return self.ep.done()

    def finish(self) -> dict:
        """
        End the run and return its record.

        Whatever is left of the shift runs with no further commands, as the
        trainer's play-out does: stopping early is inaction, and in most
        scenarios inaction is the accident. The record is Episode.result --
        the row every published run has -- plus how the clock was fed.
        """
        if self._record is not None:
            return self._record
        ep = self.ep
        while not ep.done():
            ep.advance(max(ep.t0 + ep.horizon - ep.plant.t, ep.dt))
        row = ep.result(time.monotonic() - self._wall0)
        clk = self.inst.clock
        row["mcp"] = {
            "instance_id": self.inst.instance_id,
            "prompt_lang": self.lang,
            "clock": clk.model_dump(),
            # A token clock nobody fed charged nothing: the run then had free
            # deliberation (the stand records it as INFRA_ERROR). A harness
            # that never called a tool spent no tokens on the plant, so there
            # was nothing to feed: that is inaction, and it is scored.
            "clock_fed": (clk.mode != "tokens" or self.tokens_reported > 0
                          or not self.journal),
            "tokens_reported": self.tokens_reported,
            "calls": dict(self.calls),
            "rejected": self.rejected,
            "waits": self.waits,
            "history_keep": self.inst.history_keep,
            "journal_len": len(self.journal),
        }
        self._record = row
        return row

    def journal_doc(self) -> dict:
        """What replay() needs, plus the physics it was recorded on."""
        return {"instance": self.inst.model_dump(), "digest": sources_digest(),
                "journal": self.journal}

    # ================= agent surface =================

    def observe(self) -> str:
        self.calls["observe"] += 1
        self._deliberate(False, "observe", {})
        return self._panel()

    def list_actions(self, category: str | None = None) -> list:
        self.calls["list_actions"] += 1
        self._deliberate(False, "list_actions", {"category": category})
        if category is not None and category not in CATEGORIES:
            raise ValueError(texts.ERR[self.lang]["category"].format(
                cat=category, cats=", ".join(CATEGORIES)))
        legal = {a.aid for a in self.ep.legal_actions()} if not self.done else set()
        return [{"id": a.aid, "text": texts.action_text(a, self.lang),
                 "category": a.category, "latency_s": a.latency,
                 "available": a.aid in legal, "destructive": destructive(a)}
                for a in CATALOG if category is None or a.category == category]

    def read_regulation(self) -> str:
        """The written regulation; only offered when the instance has a policy pack."""
        if not self.inst.policy_pack:
            raise ValueError("no regulation is offered in this task")
        self.calls["read_regulation"] += 1
        self._deliberate(False, "read_regulation", {})
        from .regulation import text
        return text(self.lang)

    def act(self, action_id: str) -> str:
        """One decision: deliberation, the command, its latency, the tick."""
        aid = action_id
        self.calls["act"] += 1
        ep = self.ep
        if self.done:
            return texts.OVER[self.lang]
        a = CATALOG_BY_ID.get(aid)
        if a is None or aid not in {x.aid for x in ep.legal_actions()}:
            # A command that does not exist, or that the equipment state
            # rules out, does nothing -- but the thought behind it was spent.
            self._deliberate(False, "act", {"action_id": aid})
            why = "unknown" if a is None else "blocked"
            self.rejected.append([round(ep.plant.t - ep.t0, 1), aid, why])
            raise ValueError(texts.ERR[self.lang][why].format(aid=aid))

        tok, t_think = self._deliberate(True, "act", {"action_id": aid})
        if ep.done():
            ep.log.append(StepRecord(ep.plant.t - ep.t0, aid,
                                     "не исполнено: эпизод завершён",
                                     tok, t_think))
            return texts.OVER[self.lang]
        result = a.fn(ep.ctx)
        ep.advance(a.latency)
        t = ep.plant.t - ep.t0
        ep.log.append(StepRecord(t, aid, result, tok, t_think + a.latency))
        if not ep.done():
            ep.advance(POLL_PERIOD)
        return texts.reply(t, aid, result, self.lang) + "\n\n" + self._panel()

    def wait(self, seconds: float) -> str:
        """
        A decision to do nothing for a while.

        Logged as NO_OP -- which is what it is -- so that the metrics that
        skip NO_OPs (time of the first action) are not fooled by a wait.
        """
        self.calls["wait"] += 1
        ep = self.ep
        if self.done:
            return texts.OVER[self.lang]
        if not WAIT_MIN <= seconds <= WAIT_MAX:
            self._deliberate(False, "wait", {"seconds": seconds})
            raise ValueError(texts.ERR[self.lang]["wait"].format(
                lo=WAIT_MIN, hi=WAIT_MAX))
        tok, t_think = self._deliberate(True, "wait", {"seconds": seconds})
        if not ep.done():
            ep.advance(seconds)
        t = ep.plant.t - ep.t0
        ep.log.append(StepRecord(t, "NO_OP", "наблюдение продолжено",
                                 tok, t_think + seconds))
        self.waits.append([round(t, 1), seconds])
        if ep.done():
            return texts.OVER[self.lang]
        return self._panel()

    # ================= internals =================

    def _deliberate(self, decision: bool, call: str, args: dict) -> tuple:
        """Apply the deliberation owed so far; returns (tokens, seconds)."""
        clk = self.inst.clock
        now = time.monotonic()
        if self._replay_think is not None:
            self.pending_s = self._replay_think
        elif clk.mode == "wall":
            self.pending_s += (now - self._wall_last) * clk.wall_scale
        elif clk.mode == "fixed" and decision:
            self.pending_s += clk.fixed_tokens / clk.think_rate
        t, self.pending_s = self.pending_s, 0.0
        self.journal.append({"call": call, "args": args, "think_s": t,
                             "tokens": self._fed})
        self._fed = 0
        if (decision or t > 0) and not self.ep.done():
            self.ep.advance(t)
        # The twin's own computation is not the agent's thinking.
        self._wall_last = time.monotonic()
        return int(round(t * clk.think_rate)), t

    def _panel(self) -> str:
        if self.done:
            return texts.OVER[self.lang]
        ep = self.ep
        # build_observation drains the workers' inbox: a report is shown once,
        # as in the LLM runs, where every observation was a decision.
        obs = build_observation(ep)
        return texts.panel(obs, ep.legal_actions(), ep, self.lang,
                           self.inst.history_keep)


def replay(doc: dict) -> NH3Env:
    """
    Re-run a journal: the same calls with the same charges give the same run.

    This is how the outcome is computed when the server could not finish the
    shift itself -- a stand stops an MCP server a couple of seconds after the
    harness disconnects, and the play-out takes longer. The world is
    deterministic, so the journal is the run. On physics other than the one
    it was recorded on the replay is refused rather than quietly different.
    """
    if doc.get("digest") != sources_digest():
        raise ValueError("the journal was recorded on other physics sources "
                         f"({doc.get('digest')} != {sources_digest()})")
    env = NH3Env(Instance.model_validate(doc["instance"]))
    for e in doc["journal"]:
        env._replay_think = e["think_s"]
        env.tokens_reported += e.get("tokens", 0)
        try:
            getattr(env, e["call"])(**e["args"])
        except ValueError:
            pass                        # a rejected call: recorded, did nothing
    env._replay_think = None
    return env
