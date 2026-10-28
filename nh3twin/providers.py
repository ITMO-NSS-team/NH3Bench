# -*- coding: utf-8 -*-
"""
Connecting an arbitrary model to the episode loop.

The benchmark originally spoke only to Claude Code in non-interactive
mode, and the first published runs were made with it. For the benchmark
to measure somebody else's model, a second transport is needed -- but in
such a way that the first stays byte for byte the same: `llm_policy.py`
is not modified here, it is reused.

What every transport has in common and therefore does NOT override:

    * the system part of the prompt (role plus the catalog of 133
      actions);
    * the user part (briefing, observation, history);
    * the answer parsing (`parse_action`) and the statistics;
    * the format of the per-decision transcript.

Only the model call differs, and the way of learning how many tokens the
model spent on deliberation. The second matters more than the first:
virtual time is computed FROM TOKENS and not from the real network
latency, so a provider that does not report hidden reasoning tokens
gives its model a head start -- it arrives at the accident earlier than
it actually thought. The accounting mode is therefore written into the
result and must appear in the table next to the score.
"""

from __future__ import annotations

import json
import os
import time

from .llm_policy import (ClaudeCLIPolicy, CodexCLIPolicy, ZAIChatPolicy,
                         DEFAULT_CLI, DEFAULT_CODEX_CLI, system_prompt)


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Modes of accounting for deliberation tokens. They are written into the run
# result; a table row without this field is not comparable with the others on
# time.
ACC_OUTPUT = "output_tokens"                  # Anthropic: includes the hidden ones
ACC_COMPLETION = "completion_tokens"          # OpenAI-compatible, reasoning included
ACC_COMPLETION_PLUS = "completion+reasoning"  # reasoning arrived as a separate figure
ACC_NO_REASONING = "completion_tokens_only"   # hidden deliberation not reported
# A decision model (OpenRouter Decisions API) generates no text at all. Its
# reported output tokens are the scoring of the option labels -- constant for a
# given catalog, independent of the situation -- so by default they are not
# deliberation; the second mode charges them anyway, as an upper bound.
ACC_DECISION = "decision_no_generation"
ACC_DECISION_SCORING = "decision_scoring_tokens"


# =========================================================================
# Local keys
# =========================================================================

def load_dotenv(path=".env") -> dict:
    """
    Reading .env without an external dependency.

    Provider keys must reach neither the repository nor the command line
    (which is visible in the process list and in the shell history), so the
    only supported way to pass them is a file or an environment variable.
    """
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            out[k.strip()] = v
            os.environ.setdefault(k.strip(), v)
    return out


# =========================================================================
# OpenRouter
# =========================================================================

class OpenRouterPolicy(ClaudeCLIPolicy):
    """
    A model through OpenRouter (OpenAI-compatible response format).

    The inheritance here is not a claim that "this is a kind of CLI policy"
    but a way to keep a single copy of the answer parsing, the statistics
    and the transcript: `act` and `_trace` in `llm_policy.py` do not depend
    on the transport, and that file must not be edited -- the published runs
    were made with it.
    """

    def __init__(self, model, api_key=None, base_url=OPENROUTER_URL,
                 history=14, timeout=240, retries=2, trace_path=None,
                 label=None, verbose=False, temperature=None,
                 max_tokens=None, extra_body=None, prompt_lang="ru"):
        # The parent constructor is not called: it prepares the system-prompt
        # file for the CLI, while here the system part goes in the request
        # body.
        self.prompt_lang = prompt_lang
        self.verbose = verbose
        self.model = model
        self.history = history
        self.timeout = timeout
        self.retries = retries
        self.trace_path = trace_path
        self.name = label or f"llm:{model}"
        from .llm_policy import LLMStats
        self.stats = LLMStats()

        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_body = extra_body or {}
        self._system = system_prompt(prompt_lang)
        # The accounting mode is determined from the very first response and
        # only refined afterwards: it cannot be declared in advance, it depends
        # on the provider.
        self.token_accounting = None

        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            load_dotenv()
            self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "нет ключа OpenRouter: положите OPENROUTER_API_KEY в .env "
                "или в переменную среды")

    # -- token accounting -----------------------------------------------

    def _deliberation_tokens(self, usage: dict) -> tuple:
        """
        (deliberation tokens, accounting mode).

        Everything the model produced is counted: both the visible answer and
        the hidden reasoning. The plant makes no distinction between "thought
        out loud" and "thought silently".
        """
        comp = int(usage.get("completion_tokens") or 0)
        det = usage.get("completion_tokens_details") or {}
        reas = int(det.get("reasoning_tokens")
                   or usage.get("reasoning_tokens") or 0)
        if not reas:
            # Either there was no hidden reasoning, or it was not reported.
            # These cases cannot be told apart from a single response, so the
            # mode is marked as incomplete -- more honest than silently
            # assuming the model did not think.
            return comp, ACC_NO_REASONING
        if comp > reas:
            # The usual OpenAI-compatible case: reasoning is already included.
            return comp, ACC_COMPLETION
        # reasoning was reported as a separate figure -- we add it.
        return comp + reas, ACC_COMPLETION_PLUS

    # -- calling the model ----------------------------------------------

    def _call(self, prompt: str) -> tuple:
        """Returns (text, deliberation tokens, cost, error)."""
        import requests

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system},
                {"role": "user", "content": prompt},
            ],
            # The cost is needed for the run-cost metric, not for judging
            # quality: OpenRouter reports it in the same response.
            "usage": {"include": True},
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        body.update(self.extra_body)

        try:
            r = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    # OpenRouter asks the application to identify itself; this
                    # does not affect token accounting.
                    "HTTP-Referer": "https://github.com/nicl-nno/nh3bench",
                    "X-Title": "NH3Bench",
                },
                data=json.dumps(body).encode("utf-8"),
                timeout=self.timeout,
            )
        except Exception as e:                      # network, DNS, timeout
            return "", 0, 0.0, f"{type(e).__name__}: {str(e)[:160]}"

        if r.status_code != 200:
            return "", 0, 0.0, f"http {r.status_code}: {r.text[:200]}"
        try:
            j = r.json()
        except ValueError:
            return "", 0, 0.0, f"bad json: {r.text[:200]}"
        if j.get("error"):
            return "", 0, 0.0, f"api: {str(j['error'])[:200]}"

        choices = j.get("choices") or []
        if not choices:
            return "", 0, 0.0, f"нет choices: {str(j)[:200]}"
        msg = choices[0].get("message") or {}
        text = msg.get("content") or ""
        # Some models return their reasoning in a separate field. It is not
        # part of the answer text, but it was paid for in time -- and it has to
        # be visible in the transcript, or Inspect would show a decision
        # without its justification.
        think = msg.get("reasoning") or ""
        if think:
            # The section markers are ours, not the model's, so they follow the
            # task language: in the English track a transcript must not be half
            # Russian. The model's own text is not touched.
            if getattr(self, "prompt_lang", "ru") == "en":
                head, body = "[reasoning]", "[answer]"
            else:
                head, body = "[рассуждение]", "[ответ]"
            text = f"{head}\n{think}\n\n{body}\n{text}"

        usage = j.get("usage") or {}
        tokens, mode = self._deliberation_tokens(usage)
        if self.token_accounting is None:
            self.token_accounting = mode
        elif self.token_accounting != mode:
            # The provider changed its way of reporting in the middle of an
            # episode: we count the run under the least complete mode.
            self.token_accounting = ACC_NO_REASONING

        cost = 0.0
        if isinstance(usage.get("cost"), (int, float)):
            cost = float(usage["cost"])
        return text, tokens, cost, None


OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"


class OpenRouterDecisionPolicy(OpenRouterPolicy):
    """
    A decision model (TypeSafe Jev) through OpenRouter's Decisions API.

    Such a model does not accept chat messages and does not write text: it
    takes a `state` and a typed `choice` question and returns one label with a
    probability distribution. The task is kept as close to the LLM runs as the
    format allows:

        * `state` is the very text an LLM receives -- the system part and the
          user part, byte for byte, joined by a blank line;
        * the options are the whole catalog (133 identifiers with their
          descriptions), not only the currently legal ones: an LLM may also
          name a blocked command, and it turns into NO_OP the same way;
        * the answer goes through the same `parse_action`, so the statistics
          and the transcript are those of any other run.

    The clock. Measured on the live endpoint, the reported `output_tokens`
    are ~16 per option (60 for 3 options, 580 for 32, 2183 for 133) and do
    not move with the state at all: that is label scoring, not deliberation
    about the plant. By default a decision is therefore charged zero tokens
    (`ACC_DECISION`) -- it still pays the polling tick and the action latency,
    like every run. `charge_scoring=True` charges the reported figure instead
    (~55 s a decision), which bounds the effect of that choice from above.
    """

    QUESTION = {
        "ru": "Какое одно действие из каталога выполнить сейчас?",
        "en": "Which single action from the catalog should be taken now?",
    }
    # The gate of the `gated` harness: whether to act at all. Asked in the same
    # request as the choice, so it costs no extra latency.
    GATE = {
        "ru": {"type": "noul",
               "instructions": "Нужно ли прямо сейчас выполнить какое-то "
                               "действие, а не просто продолжать наблюдение?",
               "criteria": {
                   "true": "обстановка требует вмешательства, замера или "
                           "реакции на полученные сведения",
                   "false": "угрозы нет, либо меры уже приняты и нужно "
                            "дождаться их результата"}},
        "en": {"type": "noul",
               "instructions": "Does some action need to be taken right now, "
                               "rather than simply continuing to observe?",
               "criteria": {
                   "true": "the situation calls for intervention, a "
                           "measurement or a response to what has been "
                           "reported",
                   "false": "there is no threat, or measures are already "
                            "taken and their result must be awaited"}},
    }
    HARNESSES = ("plain", "gate", "gated")

    def __init__(self, model, base_url=OPENROUTER_DECISIONS_URL,
                 charge_scoring=False, harness="plain", **kw):
        super().__init__(model, base_url=base_url, **kw)
        self.charge_scoring = charge_scoring
        # `plain` is the LLM's task verbatim. `gate` adds the act/wait
        # question; `gated` also presents the state the way a model with no
        # memory and no reasoning needs it (see `_gated_state`).
        if harness not in self.HARNESSES:
            raise ValueError(f"harness {harness!r}: {self.HARNESSES}")
        if harness != "plain" and self.prompt_lang != "ru":
            raise ValueError("the gated harness exists for the Russian task")
        self.harness = harness
        self._reports, self._hist, self._fed = [], [], None
        from .actions import CATALOG
        if self.prompt_lang == "en":
            from .prompt_en import act_text
            self._criteria = {a.aid: act_text(a.aid, a.text) for a in CATALOG}
        else:
            self._criteria = {a.aid: a.text for a in CATALOG}
        self.stats.provider = "openrouter-decisions"
        # Not deliberation, but reported by the provider: kept, not dropped.
        self.stats.scoring_tokens = 0

    def _call(self, prompt: str) -> tuple:
        """Returns (text, deliberation tokens, cost, error)."""
        import requests

        state = (self._system + "\n\n" + prompt if self.harness != "gated"
                 else self._gated_state(prompt))
        crit = self._criteria
        questions = {}
        if self.harness != "plain":
            # NO_OP is what the gate answers; left among the options it
            # collects ~0.4 of a 133-way distribution and wins by default.
            crit = {k: v for k, v in crit.items() if k != "NO_OP"}
            questions["act"] = self.GATE[self.prompt_lang]
        questions["action"] = {"type": "choice",
                               "instructions": self.QUESTION[self.prompt_lang],
                               "criteria": crit}
        body = {"model": self.model, "state": state, "questions": questions}
        body.update(self.extra_body)
        try:
            r = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/nicl-nno/nh3bench",
                    "X-Title": "NH3Bench",
                },
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                timeout=self.timeout,
            )
        except Exception as e:
            return "", 0, 0.0, f"{type(e).__name__}: {str(e)[:160]}"
        if r.status_code != 200:
            return "", 0, 0.0, f"http {r.status_code}: {r.text[:200]}"
        try:
            j = r.json()
        except ValueError:
            return "", 0, 0.0, f"bad json: {r.text[:200]}"
        if j.get("error"):
            return "", 0, 0.0, f"api: {str(j['error'])[:200]}"
        ans = (j.get("answers") or {}).get("action") or {}
        choice = ans.get("choice")
        if not choice:
            return "", 0, 0.0, f"нет answers.action: {str(j)[:200]}"
        gate = None
        if self.harness != "plain":
            gate = ((j.get("answers") or {}).get("act") or {}).get("noul")
            if not isinstance(gate, (int, float)):
                return "", 0, 0.0, f"нет answers.act: {str(j)[:200]}"
            # 0.5 is the model's own yes/no boundary, not a tuned threshold.
            if gate < 0.5:
                choice = "NO_OP"

        # The transcript needs something in place of reasoning, and the model
        # has none: the distribution is the whole of its "why". The section
        # markers are ours, the figures are the model's.
        probs = sorted((ans.get("probabilities") or {}).items(),
                       key=lambda kv: -kv[1])[:5]
        top = "; ".join(f"{k} {v:.2f}" for k, v in probs)
        if self.prompt_lang == "en":
            head, tail = "[distribution]", "ACTION"
        else:
            head, tail = "[распределение]", "ДЕЙСТВИЕ"
        text = (f"{head}\n"
                + (f"act {gate:.2f}\n" if gate is not None else "")
                + f"{top}\nconfidence {ans.get('confidence')}\n\n"
                f"{tail}: {choice}")

        usage = j.get("usage") or {}
        scoring = int(usage.get("output_tokens") or 0)
        self.stats.scoring_tokens += scoring
        self.stats.input_tokens += int(usage.get("input_tokens") or 0)
        if self.charge_scoring:
            tokens, self.token_accounting = scoring, ACC_DECISION_SCORING
        else:
            tokens, self.token_accounting = 0, ACC_DECISION
        cost = float(usage["cost"]) if isinstance(
            usage.get("cost"), (int, float)) else 0.0
        return text, tokens, cost, None

    # -- the gated harness: the same facts, kept where a reflex can see them

    _REPORTS_HEAD = "ОТЧЁТЫ РАБОТНИКОВ:"
    _ASK_LINE = "\n\nВыбери одно действие. Последняя строка -- ДЕЙСТВИЕ: <ид>."

    def _gated_state(self, prompt: str) -> str:
        """
        The LLM's prompt, re-laid for a model that neither reasons nor
        remembers. Nothing is added that the plant has not already told the
        agent in this episode; three things are moved:

          * a worker's report is shown by the episode exactly once (the
            observation after the dispatch completes). An LLM reacts to it in
            that one decision; a reflex that polls every 15 s sees it for 15 s
            and then re-issues the measurement. Here every report of the shift
            stays in the state;
          * history is 14 *decisions*, which for a 15-second decision maker is
            3.5 minutes of its own NO_OPs. Runs of NO_OP collapse into one
            line, so the 14 entries are events;
          * the catalog and the answer format leave the state -- the catalog
            is the question's option list, and there is no text to format.
        """
        import re
        from .llm_policy import _ROLE
        a = prompt.index("[t = ")
        b = prompt.index("\n\nТВОИ ПРЕДЫДУЩИЕ" if "ТВОИ ПРЕДЫДУЩИЕ" in prompt
                         else "\n\nИСТОРИЯ:")
        head, obs = prompt[:a], prompt[a:b]
        hist, _, tail = prompt[b + 2:].partition("\n\n")
        tail = ("\n\n" + tail) if tail else ""

        # A retry sends the same prompt again: it must not be remembered twice.
        if prompt != self._fed:
            self._fed = prompt
            t = re.search(r"\[t = (\d+) с\]", obs).group(1)
            if self._REPORTS_HEAD in obs:
                for ln in obs.split(self._REPORTS_HEAD + "\n", 1)[1].split("\n"):
                    if not ln.startswith("  "):
                        break
                    self._reports.append(f"  [t={t} с] {ln.strip()}")
            for ln in hist.split("\n")[1:]:
                if ln not in self._hist:
                    self._hist.append(ln)

        obs = re.sub(r"\n" + self._REPORTS_HEAD + r"\n(  .*(\n|$))+", "\n",
                     obs).rstrip()
        reports = ("ОТЧЁТЫ РАБОТНИКОВ ЗА СМЕНУ (все, по времени):\n"
                   + "\n".join(self._reports) if self._reports
                   else "ОТЧЁТЫ РАБОТНИКОВ ЗА СМЕНУ: пока нет")

        runs = []                     # [first line, last line, count]
        for ln in self._hist:
            if "NO_OP" in ln and runs and "NO_OP" in runs[-1][0]:
                runs[-1][1] = ln
                runs[-1][2] += 1
            else:
                runs.append([ln, ln, 1])
        lines = []
        for first, last, n in runs[-self.history:]:
            if n == 1:
                lines.append(first)
            else:
                t0 = re.search(r"t=(\d+)", first).group(1)
                t1 = re.search(r"t=(\d+)", last).group(1)
                lines.append(f"  [t={t0}–{t1} с] NO_OP ×{n} -> "
                             f"наблюдение продолжено")
        hist = ("ТВОИ ПРЕДЫДУЩИЕ ДЕЙСТВИЯ (события; NO_OP подряд свёрнуты):\n"
                + "\n".join(lines) if lines
                else "ИСТОРИЯ: ты ещё ничего не предпринимал.")

        role = _ROLE.split("ФОРМАТ ОТВЕТА")[0].rstrip()
        return (role + "\n\n" + head + obs + "\n\n" + reports + "\n\n" + hist
                + tail.replace(self._ASK_LINE, ""))


# =========================================================================
# Factory
# =========================================================================

PROVIDERS = ("claude-cli", "openrouter", "openrouter-decisions", "codex", "zai")


def make_policy(provider, model, *, cli=DEFAULT_CLI, history=14, timeout=240,
                trace_path=None, label=None, verbose=False, retries=None,
                base_url=None, temperature=None, max_tokens=None,
                prompt_lang="ru", reasoning_effort="medium",
                charge_scoring=False, harness="plain"):
    """
    A policy by provider name.

    `claude-cli` is the default behaviour and the same configuration the
    published runs were made with: the arguments are passed exactly as
    before, so that the old command can be repeated verbatim.
    """
    if provider == "claude-cli":
        return ClaudeCLIPolicy(
            model=model, cli=cli, history=history, timeout=timeout,
            trace_path=trace_path, label=label, verbose=verbose,
            **({"prompt_lang": prompt_lang} if prompt_lang != "ru" else {}),
            **({"retries": retries} if retries is not None else {}))
    if provider == "openrouter":
        return OpenRouterPolicy(
            model=model, history=history, timeout=timeout,
            trace_path=trace_path, label=label, verbose=verbose,
            retries=2 if retries is None else retries,
            base_url=base_url or OPENROUTER_URL,
            temperature=temperature, max_tokens=max_tokens,
            prompt_lang=prompt_lang)
    if provider == "openrouter-decisions":
        return OpenRouterDecisionPolicy(
            model=model, history=history, timeout=timeout,
            trace_path=trace_path, label=label, verbose=verbose,
            retries=2 if retries is None else retries,
            base_url=base_url or OPENROUTER_DECISIONS_URL,
            prompt_lang=prompt_lang, charge_scoring=charge_scoring,
            harness=harness)
    if provider == "codex":
        return CodexCLIPolicy(
            model=model, cli=cli or DEFAULT_CODEX_CLI, history=history,
            timeout=timeout, trace_path=trace_path, label=label,
            verbose=verbose, reasoning_effort=reasoning_effort,
            **({"retries": retries} if retries is not None else {}))
    if provider == "zai":
        return ZAIChatPolicy(
            model=model, history=history, timeout=timeout,
            trace_path=trace_path, label=label, verbose=verbose,
            reasoning_effort=reasoning_effort,
            **({"retries": retries} if retries is not None else {}))
    raise ValueError(f"неизвестный провайдер {provider!r}; "
                     f"известны: {', '.join(PROVIDERS)}")


def accounting_of(policy) -> str:
    """The token accounting mode, as it should be written into the run result.
    """
    return getattr(policy, "token_accounting", None) or ACC_OUTPUT


def _sanitize(model: str) -> str:
    """A model name fit for a filename: slashes in OpenRouter slugs."""
    return model.replace("/", "_").replace(":", "_")
