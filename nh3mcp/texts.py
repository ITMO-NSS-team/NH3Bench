# -*- coding: utf-8 -*-
"""
What the agent reads over MCP: the task prompt, the panel, the replies.

The role and the plant description are the benchmark's own texts, cut
before their "answer format" section -- over MCP the answer is a tool call,
not a last line. Everything else the agent reads is rendered by the
simulator and, on the English track, translated by ``prompt_en`` exactly as
for the English LLM runs: the layout keeps one definition.

The few strings that exist only because of the protocol (tool usage, the
clock note, errors) are written here in both languages. Russian is the
canonical one, as everywhere in the task.
"""

from __future__ import annotations

from nh3twin import prompt_en
from nh3twin.llm_policy import _ROLE, _history_text, catalog_text as _catalog_ru

# The role without its text-protocol tail. The split marker is checked by the
# tests: if the role is ever reworded, the cut must not silently grab it all.
_ROLE_CUT = {"ru": "ФОРМАТ ОТВЕТА", "en": "ANSWER FORMAT"}


def role(lang: str) -> str:
    text = _ROLE if lang == "ru" else prompt_en.ROLE_EN
    head, sep, _ = text.partition(_ROLE_CUT[lang])
    assert sep, "the role text lost its answer-format section"
    return head.rstrip()


def catalog(lang: str) -> str:
    return _catalog_ru() if lang == "ru" else prompt_en.catalog_text()


def brief(scen, lang: str) -> str:
    return scen.brief if lang == "ru" else prompt_en.SCEN_EN.get(scen.sid, scen.brief)


_TOOLS = {
    "ru": """\
КАК РАБОТАТЬ

Установкой управляют через инструменты:
  observe      -- показания панели в текущий момент;
  list_actions -- каталог команд и какие из них сейчас доступны;
  act          -- выполнить одну команду каталога; в ответе её результат и
                  новые показания панели;
  wait         -- ничего не предпринимать заданное число секунд.
Отчёт работника о выполненном наряде показывается один раз -- в первых
показаниях панели после того, как наряд выполнен.
Смена длится до конца наблюдаемого периода. Если ты закончишь раньше,
установка доработает остаток смены без твоих команд.""",
    "en": """\
HOW TO WORK

The plant is operated through tools:
  observe      -- the panel readings right now;
  list_actions -- the command catalog and which commands are available now;
  act          -- execute one catalog command; the reply holds its result
                  and the new panel readings;
  wait         -- do nothing for a given number of seconds.
A worker's report on a completed dispatch is shown once -- in the first
panel reading after the dispatch is done.
The shift lasts until the end of the observed period. If you finish
earlier, the plant runs the rest of the shift without your commands.""",
}

# The role's point 1 states the token clock. When a run uses another clock,
# the prompt says so rather than rewording the canonical role.
_CLOCK = {
    "ru": {"fixed": "ВАЖНО: в этом прогоне время раздумий считается иначе, "
                    "чем сказано в п. 1: каждое решение (act, wait) стоит "
                    "{s:.1f} с, сколько бы ты ни рассуждал.",
           "wall": "ВАЖНО: в этом прогоне время раздумий считается иначе, "
                   "чем сказано в п. 1: оно реальное, секунда твоей работы "
                   "-- {k:g} с на установке."},
    "en": {"fixed": "IMPORTANT: in this run thinking time is counted "
                    "differently from point 1: every decision (act, wait) "
                    "costs {s:.1f} s, however long you reason.",
           "wall": "IMPORTANT: in this run thinking time is counted "
                   "differently from point 1: it is real time, one second "
                   "of your work is {k:g} s at the plant."},
}

_BRIEF_HEAD = {"ru": "ВВОДНАЯ СМЕНЫ: ", "en": "SHIFT BRIEFING: "}


def task_prompt(scen, lang: str, clock) -> str:
    """The text a harness is started with. No title, no hazard: only the brief."""
    parts = [role(lang), "", _TOOLS[lang]]
    if clock.mode != "tokens":
        parts += ["", _CLOCK[lang][clock.mode].format(
            s=clock.fixed_tokens / clock.think_rate, k=clock.wall_scale)]
    parts += ["", _BRIEF_HEAD[lang] + brief(scen, lang)]
    return "\n".join(parts)


def instructions(lang: str) -> str:
    """Server instructions: the protocol only, the same for every scenario."""
    return _TOOLS[lang]


# ---------------------------------------------------------------------------
# The panel. The lines are those of llm_policy.user_prompt / prompt_en
# .user_prompt minus the closing "choose one action" request.
# ---------------------------------------------------------------------------

def panel(obs, legal, ep, lang: str, keep: int) -> str:
    from nh3twin.actions import CATALOG
    legal_ids = {a.aid for a in legal}
    blocked = [a.aid for a in CATALOG if a.aid not in legal_ids]
    left = ep.horizon - obs.t_rel
    if lang == "ru":
        L = [f"Прошло с начала смены {obs.t_rel:.0f} с; до конца наблюдаемого "
             f"периода около {left:.0f} с.", "", obs.render()]
        if keep:
            L += ["", _history_text(ep.log, keep)]
        if blocked:
            L += ["", "СЕЙЧАС НЕДОСТУПНЫ (состояние оборудования не позволяет): "
                  + ", ".join(blocked)]
    else:
        L = [f"{obs.t_rel:.0f} s have passed since the start of the shift; about "
             f"{left:.0f} s remain until the end of the observed period.", "",
             prompt_en.obs_text(obs.render(), ep.scen.brief, ep.scen.sid)]
        if keep:
            L += ["", prompt_en.history_text(ep.log, keep)]
        if blocked:
            L += ["", "UNAVAILABLE RIGHT NOW (the equipment state does not "
                  "allow it): " + ", ".join(blocked)]
    return "\n".join(L)


def reply(t: float, aid: str, result: str, lang: str) -> str:
    """One executed command, in the form of the LLM runs' history lines."""
    if lang == "ru":
        return f"[t={t:.0f} с] {aid} -> {result}"
    return f"[t={t:.0f} s] {aid} -> {prompt_en.reply_text(result)}"


def action_text(a, lang: str) -> str:
    return a.text if lang == "ru" else prompt_en.act_text(a.aid, a.text)


OVER = {"ru": "СМЕНА ЗАВЕРШЕНА: команды больше не исполняются.",
        "en": "THE SHIFT IS OVER: commands are no longer executed."}

ERR = {
    "ru": {"unknown": "нет такой команды: {aid}; каталог -- list_actions",
           "blocked": "команда {aid} сейчас недоступна (состояние оборудования "
                      "не позволяет)",
           "category": "нет такой категории: {cat}; есть: {cats}",
           "wait": "ожидание задаётся от {lo:.0f} до {hi:.0f} с"},
    "en": {"unknown": "no such command: {aid}; see list_actions",
           "blocked": "command {aid} is unavailable right now (the equipment "
                      "state does not allow it)",
           "category": "no such category: {cat}; there are: {cats}",
           "wait": "a wait is from {lo:.0f} to {hi:.0f} s"},
}

# Tool descriptions, in the task language: they are part of what the model
# reads. Nothing here may depend on the scenario.
TOOL_DOC = {
    "ru": {
        "observe": "Показания панели SCADA в текущий момент: приборы, "
                   "оборудование, тревоги, наряды, отчёты работников, персонал.",
        "list_actions": "Каталог команд (133, одинаков во всех задачах): "
                        "идентификатор, описание, категория, время исполнения, "
                        "доступна ли сейчас. Можно ограничить категорией: "
                        "observe, dispatch, control, safety, alarm.",
        "act": "Выполнить одну команду каталога по её идентификатору, "
               "например FEED:CLOSE:EV-03. Время на установке идёт: раздумья, "
               "исполнение команды и такт опроса 10 с. Возвращает результат "
               "и новые показания панели.",
        "wait": "Ничего не предпринимать заданное число секунд (10..600) и "
                "вернуть новые показания панели.",
    },
    "en": {
        "observe": "The SCADA panel right now: instruments, equipment, alarms, "
                   "dispatches in progress, workers' reports, personnel.",
        "list_actions": "The command catalog (133 commands, the same in every "
                        "task): id, description, category, execution time, "
                        "whether it is available now. Optionally limited to "
                        "one category: observe, dispatch, control, safety, alarm.",
        "act": "Execute one catalog command by its id, e.g. FEED:CLOSE:EV-03. "
               "Plant time runs: deliberation, the command's execution and the "
               "10 s polling tick. Returns the result and the new panel.",
        "wait": "Do nothing for the given number of seconds (10..600) and "
                "return the new panel.",
    },
}
