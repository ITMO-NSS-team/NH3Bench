# -*- coding: utf-8 -*-
"""
Подключение произвольной модели к циклу эпизода.

Бенчмарк изначально умел только Claude Code в неинтерактивном режиме, и
опубликованные 24 прогона получены именно им. Чтобы бенчмарк мог измерить
чужую модель, нужен второй транспорт -- но так, чтобы первый остался
побайтно тем же: `llm_policy.py` здесь не меняется, а переиспользуется.

Что общего у всех транспортов и потому НЕ переопределяется:

    * системная часть промпта (роль + каталог 133 действий);
    * пользовательская часть (вводная, наблюдение, история);
    * разбор ответа (`parse_action`) и снятие статистики;
    * формат пошагового протокола.

Различается только вызов модели и способ узнать, сколько токенов она
израсходовала на размышление. Второе важнее первого: виртуальное время
считается ИЗ ТОКЕНОВ, а не из реальной задержки сети, поэтому провайдер,
который не сообщает скрытые рассуждающие токены, отдаёт своей модели фору --
она приезжает к аварии раньше, чем думала в действительности. Режим учёта
поэтому записывается в результат и обязан попадать в таблицу рядом с баллом.
"""

from __future__ import annotations

import json
import os
import time

from .llm_policy import (ClaudeCLIPolicy, CodexCLIPolicy, ZAIChatPolicy,
                         DEFAULT_CLI, DEFAULT_CODEX_CLI, system_prompt)


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Режимы учёта токенов размышления. Пишутся в результат прогона; строка
# таблицы без этого признака несопоставима с остальными по времени.
ACC_OUTPUT = "output_tokens"                  # Anthropic: включает скрытые
ACC_COMPLETION = "completion_tokens"          # OpenAI-совместимые, reasoning внутри
ACC_COMPLETION_PLUS = "completion+reasoning"  # reasoning пришёл отдельной суммой
ACC_NO_REASONING = "completion_tokens_only"   # скрытое размышление не сообщено


# =========================================================================
# Локальные ключи
# =========================================================================

def load_dotenv(path=".env") -> dict:
    """
    Чтение .env без внешней зависимости.

    Ключи провайдеров не должны попадать ни в репозиторий, ни в командную
    строку (она видна в списке процессов и в истории оболочки), поэтому
    единственный поддерживаемый способ их передать -- файл или переменная
    среды.
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
    Модель через OpenRouter (совместимый с OpenAI формат ответа).

    Наследование здесь -- не утверждение «это разновидность CLI-политики», а
    способ иметь единственную копию разбора ответа, статистики и протокола:
    `act` и `_trace` в `llm_policy.py` от транспорта не зависят, а править тот
    файл нельзя -- им получены опубликованные прогоны.
    """

    def __init__(self, model, api_key=None, base_url=OPENROUTER_URL,
                 history=14, timeout=240, retries=2, trace_path=None,
                 label=None, verbose=False, temperature=None,
                 max_tokens=None, extra_body=None, prompt_lang="ru"):
        # Родительский конструктор не вызывается: он готовит файл системного
        # промпта для CLI, а здесь системная часть идёт в теле запроса.
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
        # Режим учёта выясняется по первому же ответу и далее только
        # уточняется: заявлять его заранее нельзя, он зависит от провайдера.
        self.token_accounting = None

        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            load_dotenv()
            self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "нет ключа OpenRouter: положите OPENROUTER_API_KEY в .env "
                "или в переменную среды")

    # -- учёт токенов -----------------------------------------------------

    def _deliberation_tokens(self, usage: dict) -> tuple:
        """
        (токены размышления, режим учёта).

        Считается всё, что модель породила: и видимый ответ, и скрытое
        рассуждение. Установка не различает «думал вслух» и «думал молча».
        """
        comp = int(usage.get("completion_tokens") or 0)
        det = usage.get("completion_tokens_details") or {}
        reas = int(det.get("reasoning_tokens")
                   or usage.get("reasoning_tokens") or 0)
        if not reas:
            # Скрытого размышления либо не было, либо о нём не сообщили.
            # Различить эти случаи по одному ответу невозможно, поэтому режим
            # помечается как неполный -- честнее, чем молча считать, что
            # модель не думала.
            return comp, ACC_NO_REASONING
        if comp > reas:
            # Обычный для OpenAI-совместимых случай: reasoning уже внутри.
            return comp, ACC_COMPLETION
        # reasoning сообщён отдельной суммой -- складываем.
        return comp + reas, ACC_COMPLETION_PLUS

    # -- вызов модели -----------------------------------------------------

    def _call(self, prompt: str) -> tuple:
        """Возвращает (текст, токены размышления, стоимость, ошибка)."""
        import requests

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system},
                {"role": "user", "content": prompt},
            ],
            # Стоимость нужна для метрики цены прогона, а не для оценки
            # качества: OpenRouter сообщает её в том же ответе.
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
                    # OpenRouter просит идентифицировать приложение; на учёт
                    # токенов это не влияет.
                    "HTTP-Referer": "https://github.com/nicl-nno/nh3bench",
                    "X-Title": "NH3Bench",
                },
                data=json.dumps(body).encode("utf-8"),
                timeout=self.timeout,
            )
        except Exception as e:                      # сеть, DNS, таймаут
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
        # Некоторые модели отдают рассуждение отдельным полем. В текст ответа
        # оно не входит, но оплачено временем -- и должно быть видно в
        # протоколе, иначе Inspect покажет решение без его обоснования.
        think = msg.get("reasoning") or ""
        if think:
            # Пометки разделов ставим мы, а не модель, поэтому они идут на
            # языке задания: в англоязычном треке протокол не должен быть
            # полурусским. Текст самой модели не трогается.
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
            # Провайдер сменил способ отчётности посреди эпизода: считаем
            # прогон учтённым по наименее полному режиму.
            self.token_accounting = ACC_NO_REASONING

        cost = 0.0
        if isinstance(usage.get("cost"), (int, float)):
            cost = float(usage["cost"])
        return text, tokens, cost, None


# =========================================================================
# Фабрика
# =========================================================================

PROVIDERS = ("claude-cli", "openrouter", "codex", "zai")


def make_policy(provider, model, *, cli=DEFAULT_CLI, history=14, timeout=240,
                trace_path=None, label=None, verbose=False, retries=None,
                base_url=None, temperature=None, max_tokens=None,
                prompt_lang="ru", reasoning_effort="medium"):
    """
    Политика по имени провайдера.

    `claude-cli` -- поведение по умолчанию и та же конфигурация, которой
    получены опубликованные прогоны: аргументы передаются в точности как
    раньше, чтобы старую команду можно было повторить дословно.
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
    """Режим учёта токенов, как его следует записать в результат прогона."""
    return getattr(policy, "token_accounting", None) or ACC_OUTPUT


def _sanitize(model: str) -> str:
    """Имя модели, пригодное для имени файла: слеши в слагах OpenRouter."""
    return model.replace("/", "_").replace(":", "_")
