# -*- coding: utf-8 -*-
"""
The written regulation: π_reg as a text an agent can read (DMCP-IH rule R9).

π_reg (policies.RegulationPolicy on top of RulePolicy) is the benchmark's
"faithful checklist-following" baseline; until now the checklist existed only
as code. Here it is written down clause by clause -- the conditions, the
thresholds and the actions in the order the code takes them -- and nothing
the code does not do. The correspondence is checked, not asserted:
tests/test_regulation.py parses policies.py and requires every action list
and every threshold of those two classes to be a clause here, and every
clause to be in the code.

The regulation is deliberately the plant's own instruction, not a hint: it
is the checklist π_reg follows, so it fails where π_reg fails (the
emergency stop and full isolation that rupture the blanked line in S4, the
condenser instruction of S3). Offering it is an experiment (instance
`policy_pack`), off by default: the published task had no regulation.

Draft for the validating expert: the wording is new, the content is π_reg.
"""

from __future__ import annotations

from dataclasses import dataclass

from nh3twin.actions import CATALOG_BY_ID

EVS = ("EV-03", "EV-04", "EV-05", "EV-06")    # the coolers π_reg watches


@dataclass(frozen=True)
class Clause:
    cid: str
    title: dict          # {"ru", "en"}
    when: dict
    actions: tuple       # action ids; "{ev}" stands for the cooler in question
    thresholds: tuple    # the numbers of the code this clause states
    source: str          # where in policies.py


CLAUSES = (
    Clause(
        "П0",
        {"ru": "Затянувшаяся оттайка",
         "en": "A defrost that takes too long"},
        {"ru": "Воздухоохладитель EV-03…EV-06 находится в стадии HOTGAS, PUMPDOWN "
               "или DRAIN дольше нормативных 1200 с.",
         "en": "Air cooler EV-03…EV-06 has been in the HOTGAS, PUMPDOWN or DRAIN "
               "stage longer than the standard 1200 s."},
        ("DEFROST:ABORT:{ev}", "DEFROST:INHIBIT"),
        (1200.0,),
        "RegulationPolicy.act, rule 0"),
    Clause(
        "П1",
        {"ru": "Произошедший выброс",
         "en": "A release has happened"},
        {"ru": "Тревога о разрыве или гидроударе, либо концентрация NH3 в машинном "
               "зале выше 300 ppm.",
         "en": "An alarm of a rupture or a hydraulic shock, or NH3 in the machine "
               "room above 300 ppm."},
        ("SAFETY:ESD", "SAFETY:VENT:MACHINE_ROOM", "EVACUATE:ALL",
         "SAFETY:WATER_CURTAIN", "MANUAL:ISOLATE:VE-LP", "SAFETY:NOTIFY"),
        (300,),
        "RulePolicy.act, rule 1"),
    Clause(
        "П2",
        {"ru": "Признаки аммиака в машинном зале",
         "en": "Signs of ammonia in the machine room"},
        {"ru": "NH3 в машинном зале выше 25 ppm, либо сообщение работника: "
               "переносной газоанализатор выше 50 ppm, запах аммиака, обнаружена "
               "утечка, шипение или потёк.",
         "en": "NH3 in the machine room above 25 ppm, or a worker's report: the "
               "portable analyser above 50 ppm, a smell of ammonia, a leak, hissing "
               "or a seep found."},
        ("SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
         "MEASURE:PORTABLE_GAS:MACHINE_ROOM", "MEASURE:VISUAL_LEAK:MACHINE_ROOM"),
        (25, 50),
        "RulePolicy.act, rule 2; RulePolicy._ingest"),
    Clause(
        "П2.1",
        {"ru": "Утечка, подтверждённая работником",
         "en": "A leak confirmed by a worker"},
        {"ru": "Сообщение работника из п. 2 (замер, запах, утечка) — независимо от "
               "размера утечки. Выполняется после действий п. 2.",
         "en": "A worker's report of point 2 (a reading, a smell, a leak) -- "
               "whatever the size of the leak. Carried out after the actions of "
               "point 2."},
        ("SAFETY:ESD", "MANUAL:ISOLATE:VE-HP", "MANUAL:ISOLATE:VE-IP",
         "MANUAL:ISOLATE:VE-LP", "SAFETY:NOTIFY"),
        (),
        "RulePolicy.act, rule 2"),
    Clause(
        "П3",
        {"ru": "Аммиак в производственном цехе",
         "en": "Ammonia in the production hall"},
        {"ru": "NH3 в цехе выше 50 ppm.",
         "en": "NH3 in the hall above 50 ppm."},
        ("EVACUATE:HALL", "SAFETY:VENT:HALL", "MEASURE:PORTABLE_GAS:HALL"),
        (50,),
        "RulePolicy.act, rule 2b"),
    Clause(
        "П4",
        {"ru": "Змеевик под давлением после оттайки",
         "en": "A coil under pressure after a defrost"},
        {"ru": "Воздухоохладитель EV-03…EV-06 в режиме COOL, а давление его "
               "змеевика более чем в 1.5 раза выше давления всасывания НД (P_SUC_LP).",
         "en": "Air cooler EV-03…EV-06 in COOL mode while its coil pressure is more "
               "than 1.5 times the LP suction pressure (P_SUC_LP)."},
        ("DEFROST:FORCE_EQUALIZE:{ev}", "FEED:CLOSE:{ev}"),
        (1.5,),
        "RulePolicy.act, rule 3"),
    Clause(
        "П5",
        {"ru": "Стук в трубопроводах",
         "en": "Knocking in the pipework"},
        {"ru": "Работник при прослушивании коллектора сообщил об ударах или стуке.",
         "en": "A worker listening to the header reported blows or knocking."},
        ("DEFROST:INHIBIT", "SETPOINT:LP:UP"),
        (),
        "RulePolicy.act, rule 4"),
    Clause(
        "П6",
        {"ru": "Уровень в циркуляционном ресивере НД",
         "en": "The level in the LP circulation vessel"},
        {"ru": "Указатель уровня VE-LP (замер работника) расходится с показанием "
               "SCADA более чем на 12 процентных пунктов, или уровень по SCADA выше "
               "75 %, или есть тревога по уровню.",
         "en": "The VE-LP sight glass (a worker's reading) differs from the SCADA "
               "reading by more than 12 percentage points, or the SCADA level is "
               "above 75 %, or there is a level alarm."},
        ("LV:CLOSE:LV-LP", "PUMP:STOP:PU-LP-A", "PUMP:STOP:PU-LP-B",
         "COMP:STOP:CO-02", "COMP:STOP:CO-01", "MANUAL:ISOLATE:VE-LP"),
        (12, 75),
        "RulePolicy.act, rule 5; RulePolicy._ingest"),
    Clause(
        "П7",
        {"ru": "Высокое давление конденсации",
         "en": "High condensing pressure"},
        {"ru": "P_COND выше 13.5 бар.",
         "en": "P_COND above 13.5 bar."},
        ("COND:FANS_MAX:CD-01", "COND:FANS_MAX:CD-02", "COND:PUMP_ON:CD-01",
         "COND:PUMP_ON:CD-02", "SETPOINT:LP:UP", "COMP:STOP:CO-04",
         "MEASURE:CONDENSER_CHECK:CD-01"),
        (13.5,),
        "RulePolicy.act, rule 6"),
    Clause(
        "П7.1",
        {"ru": "Предельное давление конденсации",
         "en": "Limiting condensing pressure"},
        {"ru": "P_COND выше 15.5 бар.",
         "en": "P_COND above 15.5 bar."},
        ("SAFETY:ESD",),
        (15.5,),
        "RulePolicy.act, rule 6"),
    Clause(
        "П8",
        {"ru": "Плановый обход",
         "en": "Routine rounds"},
        {"ru": "Ни один из пунктов выше не требует действий. Каждый замер — один "
               "раз за смену, в указанном порядке.",
         "en": "None of the points above calls for action. Each measurement once "
               "per shift, in the order given."},
        ("MEASURE:LEVEL_GLASS:VE-LP", "MEASURE:VIBRATION:HEADER-LP",
         "MEASURE:PORTABLE_GAS:MACHINE_ROOM", "MEASURE:COIL_GAUGE:EV-03",
         "MEASURE:VISUAL_LEAK:MACHINE_ROOM", "MEASURE:CONDENSER_CHECK:CD-01"),
        (),
        "RulePolicy.act, rule 7"),
)

_HEAD = {
    "ru": ("ИНСТРУКЦИЯ ОПЕРАТОРА АММИАЧНОЙ ХОЛОДИЛЬНОЙ УСТАНОВКИ\n"
           "Действия при отклонениях режима\n\n"
           "Общие положения.\n"
           "1. Пункты расположены по убыванию приоритета. При каждом опросе "
           "выполняется первый пункт, условие которого выполнено.\n"
           "2. Действия пункта выполняются по порядку, каждое — один раз за смену. "
           "Действие, уже выполненное или недоступное по состоянию оборудования, "
           "пропускается.\n"
           "3. Если ни один пункт не требует действий, оператор продолжает "
           "наблюдение (NO_OP).\n"
           "4. Показания — по приборам панели SCADA и по отчётам работников о "
           "выполненных нарядах."),
    "en": ("OPERATING INSTRUCTION OF THE AMMONIA REFRIGERATION PLANT\n"
           "Actions on abnormal conditions\n\n"
           "General provisions.\n"
           "1. The points are in descending order of priority. At every poll the "
           "first point whose condition holds is carried out.\n"
           "2. A point's actions are carried out in order, each once per shift. An "
           "action already done, or unavailable in the equipment's state, is "
           "skipped.\n"
           "3. If no point calls for action, the operator keeps observing "
           "(NO_OP).\n"
           "4. Readings are those of the SCADA panel and of the workers' reports on "
           "completed dispatches."),
}
_WHEN = {"ru": "Условие", "en": "Condition"}
_DO = {"ru": "Действия", "en": "Actions"}
_EV = {"ru": "(для того воздухоохладителя, о котором идёт речь)",
       "en": "(for the air cooler in question)"}


def _action_line(aid: str, lang: str) -> str:
    probe = aid.replace("{ev}", "EV-03")
    a = CATALOG_BY_ID[probe]
    if lang == "ru":
        text = a.text
    else:
        from nh3twin.prompt_en import act_text
        text = act_text(a.aid, a.text)
    if "{ev}" in aid:
        text = text.replace("EV-03", "<EV>") + " " + _EV[lang]
        aid = aid.replace("{ev}", "<EV>")
    return f"{aid} — {text}"


def text(lang: str = "ru") -> str:
    out = [_HEAD[lang]]
    for c in CLAUSES:
        cid = c.cid if lang == "ru" else c.cid.replace("П", "P")
        out += ["", f"{cid}. {c.title[lang]}",
                f"{_WHEN[lang]}: {c.when[lang]}", f"{_DO[lang]}:"]
        out += [f"  {i}) {_action_line(a, lang)}" for i, a in enumerate(c.actions, 1)]
    return "\n".join(out)
