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


# =========================================================================
# Factory
# =========================================================================

PROVIDERS = ("claude-cli", "openrouter", "codex", "zai")


def make_policy(provider, model, *, cli=DEFAULT_CLI, history=14, timeout=240,
                trace_path=None, label=None, verbose=False, retries=None,
                base_url=None, temperature=None, max_tokens=None,
                prompt_lang="ru", reasoning_effort="medium"):
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
