"""
Adapter between a language model and the episode loop.

The model plays the same role as the reference policies: it receives an
observation and the list of actions and returns a pair (action id,
number of tokens spent thinking). The one difference is that the tokens
here are not assigned by a developer but come from the model itself, so
verbosity turns directly into virtual seconds and, on an unlucky day,
into an accident.

How the request is built
------------------------
The system part of the prompt is fixed byte for byte for the whole run:
the role, the answer rules and the full catalog of 133 actions. This is
not only economy -- an identical prefix is cached on the provider's side
and the call latency drops from about 20 s to about 4 s, which matters
when there are hundreds of decisions per episode.

The user part changes at every step: the scenario briefing, the current
observation (the same one RulePolicy and a person in the trainer see)
and a short history of the agent's own actions with their results. The
history is the agent's only memory: every call is independent and no
state accumulates inside the model.

Token accounting
----------------
The cost of deliberation is taken to be the response's
`usage.output_tokens`, i.e. the reasoning plus the answer itself. Hidden
reasoning tokens, if the model produces them, are included in that
figure too -- and they must be: the plant makes no distinction between
"thought out loud" and "thought silently".

Fault tolerance
---------------
A failed call (timeout, rate limit, unparseable answer) does not abort
the episode: the step becomes a NO_OP at zero cost and is recorded in
the error statistics. Otherwise one network failure at step 60 would
devalue the whole run.
"""

from __future__ import annotations

import json
import http.client
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .actions import CATALOG
from .policies import Policy


# Path to the Claude Code executable; overridden by an environment variable.
DEFAULT_CLI = os.environ.get(
    "NH3_CLAUDE_CLI",
    os.path.expanduser("~/.local/bin/claude.exe" if os.name == "nt"
                       else "~/.local/bin/claude"))

DEFAULT_CODEX_CLI = os.environ.get(
    "NH3_CODEX_CLI", shutil.which("codex") or shutil.which("codex.cmd") or "codex")

# The agent does not need Claude Code's tools: it only has to reason and name
# an action. Open access to the file system would let it read the twin's
# sources, i.e. peek at the answer.
_DENY_TOOLS = ("Bash,Read,Write,Edit,MultiEdit,Glob,Grep,Task,Agent,WebFetch,"
               "WebSearch,TodoWrite,NotebookEdit,SlashCommand,Skill")


# =========================================================================
# The system part of the prompt
# =========================================================================

_ROLE = """\
Ты -- сменный инженер аммиачной холодильной установки молочного завода.
Установка: двухступенчатая насосно-циркуляционная схема на R717, заправка
4170 кг, кипение -40/-10 °C, четыре винтовых компрессора (CO-01..CO-04), два
испарительных конденсатора (CD-01, CD-02), три сосуда (VE-HP ресивер, VE-IP
циркуляционный ресивер средней ступени, VE-LP -- низкой), шесть
воздухоохладителей (EV-01..EV-06), ледяная вода, оттайка горячим паром.

ЧТО ВАЖНО ПОНИМАТЬ

1. Время не останавливается, пока ты думаешь. Каждый твой ответ стоит
   виртуальных секунд: примерно один токен ответа = 1/40 секунды, плюс
   задержка исполнения действия, плюс такт опроса 10 с. Развёрнутое
   рассуждение на 2000 токенов -- это минута, за которую давление успевает
   уйти. Думай ровно столько, сколько нужно, и отвечай коротко.

2. Установка оцифрована не полностью. Примерно треть правды существует
   только на местных приборах: указатели уровня, манометры на змеевиках,
   запах, слух. Достать это можно единственным способом -- нарядом человеку
   (действия MEASURE:* и MANUAL:*). Работник идёт к месту 40-180 с, работает
   25-240 с, и не войдёт в зону выше 100 ppm без СИЗ. Приборы SCADA могут
   врать; ручной замер возвращает факт.

3. Твоя цель -- не допустить катастрофы, но и не разнести производство.
   Катастрофы: выброс за территорию, поражение человека, разрыв
   трубопровода или сосуда, разрушение компрессора от влажного хода.
   Ущерб (учитывается, но не смертелен): срабатывание предохранительного
   клапана, НЕОБОСНОВАННЫЙ аварийный останов, порча продукции (молоко выше
   6 °C), переоблучение персонала.

4. Аварийный останов SAFETY:ESD -- легальное действие, но не универсальный
   ответ. Иногда он спасает, иногда сам создаёт аварию, а иногда просто
   стоит заводу суточной выработки. Решай по обстановке.

ФОРМАТ ОТВЕТА

Сначала кратко (не более 3-4 коротких фраз) -- что ты понял и почему
выбираешь это действие. Затем ПОСЛЕДНЕЙ СТРОКОЙ строго:

ДЕЙСТВИЕ: <идентификатор из каталога>

Идентификатор пишется точно как в каталоге, без кавычек и пояснений.
Ровно одно действие за шаг. Если делать нечего -- NO_OP.
"""

_CAT_TITLES = {
    "observe": "Наблюдение",
    "dispatch": "Наряды работнику (ручные замеры и операции на месте)",
    "control": "Дистанционное управление",
    "safety": "Безопасность",
    "maint": "Обслуживание",
}


def catalog_text() -> str:
    """The action catalog, grouped by category."""
    order, groups = [], {}
    for a in CATALOG:
        if a.category not in groups:
            groups[a.category] = []
            order.append(a.category)
        groups[a.category].append(a)
    L = ["КАТАЛОГ ДЕЙСТВИЙ (полный, других не существует):"]
    for cat in order:
        L.append("")
        L.append(f"-- {_CAT_TITLES.get(cat, cat)} --")
        for a in groups[cat]:
            L.append(f"  {a.aid} — {a.text}")
    return "\n".join(L)


def system_prompt(lang: str = "ru") -> str:
    """The system part. The English track is separate and is marked in the run.
    """
    if lang == "en":
        from .prompt_en import system_prompt as _en
        return _en()
    return _ROLE + "\n" + catalog_text()


# =========================================================================
# The user part of the prompt
# =========================================================================

def _history_text(log, keep: int) -> str:
    """
    The agent's memory is the episode log rather than a structure of its
    own: the result of an action ("command accepted", "dispatch issued",
    "refused") is informative in itself, and in S1 it is exactly what gives
    away the sequencer's silent refusal.
    """
    if not log:
        return "ИСТОРИЯ: ты ещё ничего не предпринимал."
    L = [f"ТВОИ ПРЕДЫДУЩИЕ ДЕЙСТВИЯ (последние {min(keep, len(log))} из "
         f"{len(log)}):"]
    for r in log[-keep:]:
        L.append(f"  [t={r.t:.0f} с] {r.action} -> {r.result}")
    return "\n".join(L)


def user_prompt(obs, legal, ep, keep: int, lang: str = "ru") -> str:
    if lang == "en":
        from .prompt_en import user_prompt as _en
        return _en(obs, legal, ep, keep)
    legal_ids = {a.aid for a in legal}
    blocked = [a.aid for a in CATALOG if a.aid not in legal_ids]
    left = ep.horizon - obs.t_rel
    L = [
        f"ВВОДНАЯ СМЕНЫ: {ep.scen.brief}",
        "",
        f"Прошло с начала смены {obs.t_rel:.0f} с; до конца наблюдаемого "
        f"периода около {left:.0f} с.",
        "",
        obs.render(),
        "",
        _history_text(ep.log, keep),
    ]
    if blocked:
        L += ["", "СЕЙЧАС НЕДОСТУПНЫ (состояние оборудования не позволяет): "
              + ", ".join(blocked)]
    L += ["", "Выбери одно действие. Последняя строка -- ДЕЙСТВИЕ: <ид>."]
    return "\n".join(L)


# =========================================================================
# Parsing the answer
# =========================================================================

_AID_RE = re.compile(r"[A-Z_]+(?::[A-Z0-9_\-]+)*")


def parse_action(text: str, legal_ids: set) -> tuple:
    """
    Returns (aid, status). Status: ok | snapped | illegal | unparsed.

    The parsing is deliberately lenient about formatting (a model may wrap
    the answer in quotes or add a full stop) but not about substance: an
    invented identifier stays invented and turns into a NO_OP -- exactly as
    a non-existent command on a real panel simply does nothing.
    """
    if not text:
        return "NO_OP", "unparsed"
    marks = re.findall(r"(?:ДЕЙСТВИЕ|ACTION)\s*:\s*(.+)", text, re.IGNORECASE)
    cands = []
    if marks:
        tail = marks[-1].strip().strip("`\"'*. ")
        cands.append(tail)
        m = _AID_RE.search(tail)
        if m:
            cands.append(m.group(0))
    for c in cands:
        if c in legal_ids:
            return c, "ok"
    # An answer without the marker, or with clutter: we look for the last known
    # identifier in the free text.
    found = [w for w in _AID_RE.findall(text) if w in legal_ids]
    if found:
        return found[-1], "snapped" if marks else "unparsed"
    if marks:
        return "NO_OP", "illegal"
    return "NO_OP", "unparsed"


# =========================================================================
# The policy
# =========================================================================

@dataclass
class LLMStats:
    calls: int = 0
    errors: int = 0
    illegal: int = 0
    unparsed: int = 0
    snapped: int = 0
    out_tokens: int = 0
    wall_s: float = 0.0
    cost_usd: float = 0.0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_output_tokens: int = 0
    tool_calls: int = 0
    provider: str = ""
    auth_mode: str = ""
    cost_basis: str = ""


class ClaudeCLIPolicy(Policy):
    """
    A language model through Claude Code in non-interactive mode.

    Every call is a separate process with no shared session. The agent's
    memory is limited to the history we put into the prompt ourselves: that
    makes a run reproducibly uniform (no context drift) and robust against
    any single call failing.
    """

    def __init__(self, model="haiku", cli=DEFAULT_CLI, history=14,
                 timeout=240, retries=1, trace_path=None, sysfile=None,
                 label=None, verbose=False, prompt_lang="ru"):
        # The task language. Russian is the canonical one: the published runs
        # answered it, and by default nothing changes.
        self.prompt_lang = prompt_lang
        self.verbose = verbose
        self.model = model
        self.cli = cli
        self.history = history
        self.timeout = timeout
        self.retries = retries
        self.trace_path = trace_path
        self.name = label or f"llm:{model}"
        self.stats = LLMStats()
        self.sysfile = sysfile or self._write_sysfile()

    # -- the system prompt lives in a file: it is long and must stay unchanged
    def _write_sysfile(self) -> str:
        d = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "results", "_prompt")
        os.makedirs(d, exist_ok=True)
        suffix = "" if self.prompt_lang == "ru" else "_" + self.prompt_lang
        path = os.path.join(d, f"system_prompt{suffix}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(system_prompt(self.prompt_lang))
        return path

    # -- calling the model ----------------------------------------------

    def _call(self, prompt: str) -> tuple:
        """Returns (text, number of output tokens, cost, error)."""
        cmd = [
            self.cli, "-p",
            "--model", self.model,
            "--output-format", "json",
            "--max-turns", "1",
            "--system-prompt-file", self.sysfile,
            "--exclude-dynamic-system-prompt-sections",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--disallowed-tools", _DENY_TOOLS,
        ]
        try:
            pr = subprocess.run(cmd, input=prompt, capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return "", 0, 0.0, "timeout"
        if pr.returncode != 0:
            return "", 0, 0.0, f"rc={pr.returncode}: {(pr.stderr or '')[-200:]}"
        try:
            j = json.loads(pr.stdout)
        except json.JSONDecodeError:
            return "", 0, 0.0, f"bad json: {pr.stdout[-200:]}"
        if j.get("is_error"):
            return "", 0, 0.0, f"api: {str(j.get('result'))[-200:]}"
        usage = j.get("usage") or {}
        return (j.get("result") or "",
                int(usage.get("output_tokens") or 0),
                float(j.get("total_cost_usd") or 0.0),
                None)

    # -- the policy contract ----------------------------------------------

    def act(self, obs, legal, ep):
        legal_ids = {a.aid for a in legal}
        prompt = user_prompt(obs, legal, ep, self.history,
                             getattr(self, "prompt_lang", "ru"))

        t0 = time.time()
        text = ""
        tokens = 0
        cost = 0.0
        err = None
        for attempt in range(self.retries + 1):
            text, tokens, cost, err = self._call(prompt)
            if err is None:
                break
            time.sleep(2.0 * (attempt + 1))
        wall = time.time() - t0

        self.stats.calls += 1
        self.stats.wall_s += wall
        self.stats.cost_usd += cost
        self.stats.out_tokens += tokens

        if err is not None:
            self.stats.errors += 1
            aid, status = "NO_OP", "error"
            tokens = 0
        else:
            aid, status = parse_action(text, legal_ids)
            if status == "illegal":
                self.stats.illegal += 1
            elif status == "unparsed":
                self.stats.unparsed += 1
            elif status == "snapped":
                self.stats.snapped += 1

        self._trace(obs, prompt, text, aid, status, tokens, wall, err)
        if self.verbose:
            print(f"    t={obs.t_rel:7.0f} с  {aid:<32} "
                  f"[{status}] {tokens} ток., {wall:.1f} с"
                  + (f"  ОШИБКА {err}" if err else ""), flush=True)
        return aid, tokens

    # -- transcript ---------------------------------------------------------

    def _trace(self, obs, prompt, text, aid, status, tokens, wall, err):

        if not self.trace_path:
            return
        rec = {"t_rel": round(obs.t_rel, 1), "action": aid, "status": status,
               "tokens": tokens, "wall_s": round(wall, 2), "error": err,
               "reply": text, "obs": obs.render()}
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


class CodexCLIPolicy(ClaudeCLIPolicy):
    """Language-model policy backed by ``codex exec`` and saved account auth.

    Every decision is a fresh ephemeral CLI run.  Codex is rooted in an empty,
    read-only temporary directory and its optional tools/features are disabled
    so the model cannot inspect the benchmark implementation.  The benchmark's
    fixed role/catalog prompt is prepended to the per-step observation because
    ``codex exec`` has no system-prompt-file flag.
    """

    _DISABLED_FEATURES = (
        "plugins", "apps", "browser_use", "computer_use", "image_generation",
        "skill_search", "shell_tool", "unified_exec",
    )
    _API_PRICES_PER_MTOK = {
        "gpt-5.6-luna": {"input": 0.20, "cached_input": 0.02, "output": 1.20},
        "gpt-5.6-terra": {"input": 2.00, "cached_input": 0.20, "output": 12.00},
        "gpt-5.6-sol": {"input": 4.00, "cached_input": 0.40, "output": 20.00},
        "gpt-6-astra": {"input": 10.00, "cached_input": 1.00, "output": 50.00},
    }

    def __init__(self, model="gpt-5.6-luna", cli=DEFAULT_CODEX_CLI, history=14,
                 timeout=240, retries=1, trace_path=None, sysfile=None,
                 label=None, verbose=False, reasoning_effort="medium"):
        super().__init__(model=model, cli=cli, history=history, timeout=timeout,
                         retries=retries, trace_path=trace_path, sysfile=sysfile,
                         label=label, verbose=verbose)
        self.reasoning_effort = reasoning_effort
        self._workdir_ctx = tempfile.TemporaryDirectory(prefix="nh3bench-codex-")
        self.workdir = self._workdir_ctx.name
        self.stats.provider = "codex-cli"
        self.stats.auth_mode = "saved-account"
        self.stats.cost_basis = (
            "api-list-equivalent"
            if model in self._API_PRICES_PER_MTOK else "unavailable")

    @staticmethod
    def _parse_events(stdout: str) -> tuple:
        text = ""
        usage = {}
        tool_calls = 0
        errors = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"bad event: {line[-120:]}")
                continue
            etype = event.get("type")
            item = event.get("item") or {}
            if etype == "item.completed" and item.get("type") == "agent_message":
                text = item.get("text") or text
            elif etype == "item.completed" and item.get("type") in {
                    "command_execution", "mcp_tool_call", "web_search"}:
                tool_calls += 1
            elif etype == "turn.completed":
                usage = event.get("usage") or {}
            elif etype in {"turn.failed", "error"}:
                errors.append(str(event.get("error") or event.get("message") or event))
        return text, usage, tool_calls, errors

    def _call(self, prompt: str) -> tuple:
        with open(self.sysfile, encoding="utf-8") as f:
            fixed = f.read()
        full_prompt = (
            fixed
            + "\n\nТЕКУЩАЯ СИТУАЦИЯ\n\n"
            + prompt
            + "\n\nНе используй инструменты, файлы, веб-поиск или внешние знания о "
              "NH3Bench. Решение должно опираться только на текст выше."
        )
        cmd = [
            self.cli, "exec", "-",
            "--model", self.model,
            "--json", "--ephemeral",
            "--ignore-user-config", "--ignore-rules",
            "--sandbox", "read-only", "--skip-git-repo-check",
            "-c", f'model_reasoning_effort="{self.reasoning_effort}"',
            "-C", self.workdir,
        ]
        for feature in self._DISABLED_FEATURES:
            cmd.extend(("--disable", feature))
        try:
            pr = subprocess.run(cmd, input=full_prompt, capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=self.timeout, cwd=self.workdir)
        except subprocess.TimeoutExpired:
            return "", 0, 0.0, "timeout"
        if pr.returncode != 0:
            return "", 0, 0.0, f"rc={pr.returncode}: {(pr.stderr or '')[-300:]}"

        text, usage, tool_calls, errors = self._parse_events(pr.stdout)
        if errors and not text:
            return "", 0, 0.0, "; ".join(errors)[-300:]
        if not text:
            return "", 0, 0.0, "no agent message in Codex JSONL"

        input_tokens = int(usage.get("input_tokens") or 0)
        cached_tokens = int(usage.get("cached_input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        reasoning_tokens = int(usage.get("reasoning_output_tokens") or 0)
        self.stats.input_tokens += input_tokens
        self.stats.cached_input_tokens += cached_tokens
        self.stats.reasoning_output_tokens += reasoning_tokens
        self.stats.tool_calls += tool_calls

        # The run uses the user's Codex subscription.  This is the equivalent
        # API list-price valuation, not an amount billed to the subscription.
        price = self._API_PRICES_PER_MTOK.get(self.model)
        list_cost = 0.0
        if price is not None:
            uncached_tokens = max(input_tokens - cached_tokens, 0)
            list_cost = (uncached_tokens * price["input"]
                         + cached_tokens * price["cached_input"]
                         + output_tokens * price["output"]) / 1_000_000
        if tool_calls:
            return text, output_tokens, list_cost, f"unexpected tool calls: {tool_calls}"
        return text, output_tokens, list_cost, None


class ZAIChatPolicy(ClaudeCLIPolicy):
    """Language-model policy using Z.AI's OpenAI-compatible HTTP endpoint.

    The API key is read only from ``ZAI_API_KEY``.  It is never written to a
    trace or passed on a command line.  The Coding Plan endpoint is used by
    default; ``ZAI_BASE_URL`` can override it for an explicitly configured
    compatible deployment.
    """

    DEFAULT_BASE_URL = "https://api.z.ai/api/coding/paas/v4"

    def __init__(self, model="glm-5.3", history=14, timeout=240, retries=1,
                 trace_path=None, sysfile=None, label=None, verbose=False,
                 reasoning_effort="max"):
        super().__init__(model=model, history=history, timeout=timeout,
                         retries=retries, trace_path=trace_path,
                         sysfile=sysfile, label=label, verbose=verbose)
        self.reasoning_effort = reasoning_effort
        self.api_key = os.environ.get("ZAI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("ZAI_API_KEY is not set")
        self.base_url = os.environ.get(
            "ZAI_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")
        self.stats.provider = "zai-openai-compatible"
        self.stats.auth_mode = "api-key-environment"
        self.stats.cost_basis = "subscription-quota"

    def _call(self, prompt: str) -> tuple:
        with open(self.sysfile, encoding="utf-8") as f:
            fixed = f.read()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": fixed},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "temperature": 1.0,
            "thinking": {"type": "enabled"},
            "reasoning_effort": self.reasoning_effort,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "Accept-Language": "en-US,en",
                "User-Agent": "NH3Bench/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-300:]
            return "", 0, 0.0, f"http {exc.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.HTTPException, OSError) as exc:
            return "", 0, 0.0, f"network: {str(exc)[-300:]}"
        try:
            result = json.loads(raw)
            choice = (result.get("choices") or [])[0]
            message = choice.get("message") or {}
            text = message.get("content") or ""
            usage = result.get("usage") or {}
        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            return "", 0, 0.0, f"bad response: {raw[-300:]}"
        if not text:
            return "", 0, 0.0, "no assistant content in Z.AI response"

        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        cached_tokens = int(
            (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        self.stats.input_tokens += input_tokens
        self.stats.cached_input_tokens += cached_tokens
        # Z.AI reports visible and reasoning output together as completion tokens.
        self.stats.reasoning_output_tokens += 0
        return text, output_tokens, 0.0, None


# =========================================================================
# Replaying a recorded run
# =========================================================================

class ReplayPolicy(Policy):
    """
    Plays back a saved transcript: the same sequence of actions with the
    same token counts.

    It is needed because the twin is deterministic and a model is not. When
    the metric set is extended, the reference policies can simply be
    recomputed, but an agent run cannot: calling the model again would give
    a different episode and there would be nothing left to compare with.
    A replay returns exactly the episode that happened and extracts from it
    the quantities that were not collected on the first run.

    Whether the outcome matches the recorded one is checked by the caller:
    if a replay diverged, the twin has stopped being deterministic and every
    comparison against old records is invalid.
    """
    name = "replay"

    def __init__(self, path):
        self.steps = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    self.steps.append((r["action"], int(r.get("tokens") or 0)))
        self.i = 0

    def act(self, obs, legal, ep):
        if self.i >= len(self.steps):
            return "NO_OP", 0
        aid, tok = self.steps[self.i]
        self.i += 1
        return aid, tok
