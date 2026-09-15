"""
Переходник между языковой моделью и циклом эпизода.

Модель играет ту же роль, что и эталонные политики: получает наблюдение и
список действий, возвращает пару (идентификатор действия, число токенов на
размышление). Отличие одно -- токены здесь не назначены разработчиком, а
приходят от самой модели, поэтому многословие напрямую превращается в
виртуальные секунды и, при неудачном стечении, в аварию.

Устройство запроса
------------------
Системная часть промпта фиксирована побайтно на весь прогон: роль, правила
ответа и полный каталог из 133 действий. Это не только экономия -- одинаковый
префикс кэшируется на стороне провайдера, и задержка вызова падает с ~20 с до
~4 с, что важно при сотнях решений за эпизод.

Пользовательская часть меняется на каждом шаге: вводная сценария, текущее
наблюдение (то же самое, что видят RulePolicy и человек в тренажёре) и
короткая история собственных действий с результатами. История -- единственная
память агента: каждый вызов независим, состояние в модели не накапливается.

Учёт токенов
------------
За стоимость размышления принимается `usage.output_tokens` ответа, то есть
рассуждение плюс сам ответ. Скрытые рассуждающие токены, если модель их
порождает, тоже входят в эту величину -- и должны входить: установка не
делает различия между «думал вслух» и «думал молча».

Отказоустойчивость
------------------
Сбой вызова (таймаут, лимит, непарсимый ответ) не прерывает эпизод: шаг
превращается в NO_OP с нулевой стоимостью и записывается в статистику ошибок.
Иначе один сетевой сбой на 60-м шаге обесценивал бы весь прогон.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field

from .actions import CATALOG
from .policies import Policy


# Путь к исполняемому файлу Claude Code; переопределяется переменной среды.
DEFAULT_CLI = os.environ.get(
    "NH3_CLAUDE_CLI",
    os.path.expanduser("~/.local/bin/claude.exe" if os.name == "nt"
                       else "~/.local/bin/claude"))

# Инструменты Claude Code агенту не нужны: он должен только рассуждать и
# называть действие. Открытый доступ к файловой системе позволил бы ему
# прочитать исходники двойника, то есть подглядеть ответ.
_DENY_TOOLS = ("Bash,Read,Write,Edit,MultiEdit,Glob,Grep,Task,Agent,WebFetch,"
               "WebSearch,TodoWrite,NotebookEdit,SlashCommand,Skill")


# =========================================================================
# Системная часть промпта
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
    """Каталог действий, сгруппированный по категориям."""
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
    """Системная часть. Английский трек -- отдельный, помечается в прогоне."""
    if lang == "en":
        from .prompt_en import system_prompt as _en
        return _en()
    return _ROLE + "\n" + catalog_text()


# =========================================================================
# Пользовательская часть промпта
# =========================================================================

def _history_text(log, keep: int) -> str:
    """
    Память агента -- это журнал эпизода, а не отдельная структура: результат
    действия («команда принята», «наряд выдан», «отказано») сам по себе
    информативен, и в S1 именно он выдаёт молчаливый отказ секвенсора.
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
# Разбор ответа
# =========================================================================

_AID_RE = re.compile(r"[A-Z_]+(?::[A-Z0-9_\-]+)*")


def parse_action(text: str, legal_ids: set) -> tuple:
    """
    Возвращает (aid, статус). Статус: ok | snapped | illegal | unparsed.

    Разбор намеренно снисходителен к оформлению (модель может обернуть ответ
    в кавычки или дописать точку), но не к сути: выдуманный идентификатор
    остаётся выдуманным и превращается в NO_OP -- ровно так же, как несуществующая
    команда на реальной панели просто ничего не сделает.
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
    # Ответ без маркера или с мусором: ищем последний известный идентификатор
    # в свободном тексте.
    found = [w for w in _AID_RE.findall(text) if w in legal_ids]
    if found:
        return found[-1], "snapped" if marks else "unparsed"
    if marks:
        return "NO_OP", "illegal"
    return "NO_OP", "unparsed"


# =========================================================================
# Политика
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


class ClaudeCLIPolicy(Policy):
    """
    Языковая модель через Claude Code в неинтерактивном режиме.

    Каждый вызов -- отдельный процесс без общей сессии. Память агента
    ограничена историей, которую мы сами кладём в промпт: это делает прогон
    воспроизводимо-однородным (нет дрейфа контекста) и устойчивым к падению
    любого отдельного вызова.
    """

    def __init__(self, model="haiku", cli=DEFAULT_CLI, history=14,
                 timeout=240, retries=1, trace_path=None, sysfile=None,
                 label=None, verbose=False, prompt_lang="ru"):
        # Язык задания. Русский -- канонический: 24 опубликованных прогона
        # отвечали на него, и по умолчанию ничего не меняется.
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

    # -- системный промпт живёт в файле: он длинный и должен быть неизменным
    def _write_sysfile(self) -> str:
        d = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "results", "_prompt")
        os.makedirs(d, exist_ok=True)
        suffix = "" if self.prompt_lang == "ru" else "_" + self.prompt_lang
        path = os.path.join(d, f"system_prompt{suffix}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(system_prompt(self.prompt_lang))
        return path

    # -- вызов модели ----------------------------------------------------

    def _call(self, prompt: str) -> tuple:
        """Возвращает (текст, число выходных токенов, стоимость, ошибка)."""
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

    # -- контракт политики ------------------------------------------------

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

    # -- протокол ---------------------------------------------------------

    def _trace(self, obs, prompt, text, aid, status, tokens, wall, err):

        if not self.trace_path:
            return
        rec = {"t_rel": round(obs.t_rel, 1), "action": aid, "status": status,
               "tokens": tokens, "wall_s": round(wall, 2), "error": err,
               "reply": text, "obs": obs.render()}
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# =========================================================================
# Воспроизведение записанного прогона
# =========================================================================

class ReplayPolicy(Policy):
    """
    Проигрывает сохранённый протокол: та же последовательность действий с
    тем же числом токенов.

    Нужна затем, что двойник детерминирован, а модель -- нет. Когда набор
    метрик расширяется, эталонные политики можно просто пересчитать, а
    агентный прогон -- нельзя: повторный вызов модели дал бы другой эпизод,
    и сравнивать было бы уже не с чем. Воспроизведение возвращает ровно тот
    эпизод, который был, и добывает из него величины, которых при первом
    прогоне не собирали.

    Совпадение исхода с записанным проверяется вызывающей стороной: если
    воспроизведение разошлось, значит двойник перестал быть детерминированным
    и все сравнения по старым записям недействительны.
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
