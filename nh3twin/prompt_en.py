# -*- coding: utf-8 -*-
"""
Английский трек задания.

Канонический язык задачи -- русский: 24 опубликованных прогона отвечали на
русское задание, и их столбец остаётся как есть. Этот модуль добавляет
второй, отдельно помеченный трек: то же задание по-английски, для моделей,
которых сравнивают в англоязычной среде, и для демонстрации, где
рассуждение модели должно быть читаемо на конференции.

Устройство намеренно такое же, как в интерфейсе тренажёра: имитатор не
переписывается, английский подставляется на выходе. Разметка наблюдения
остаётся за episode.py -- здесь переводится уже собранный текст, построчно
и по правилам. Непереведённый обрывок не должен уйти в промпт молча,
поэтому есть check(): она гоняет наблюдения всех шести задач, весь каталог
и все ответы имитатора и требует, чтобы кириллицы не осталось ни одной.

    py -c "from nh3twin import prompt_en; prompt_en.check()"
"""

from __future__ import annotations

import re

from .actions import CATALOG

# =========================================================================
# Роль и правила игры
# =========================================================================

ROLE_EN = """\
You are the shift engineer of an ammonia refrigeration plant at a dairy.
The plant: a two-stage pumped-circulation R717 system, charge 4170 kg,
evaporating at -40/-10 °C, four screw compressors (CO-01..CO-04), two
evaporative condensers (CD-01, CD-02), three vessels (VE-HP receiver, VE-IP
intermediate-stage circulation vessel, VE-LP the low-stage one), six air
coolers (EV-01..EV-06), an ice-water circuit, hot-gas defrost.

WHAT MATTERS

1. Time does not stop while you think. Every answer of yours costs virtual
   seconds: roughly one output token = 1/40 second, plus the execution
   latency of the action, plus a 10 s polling tick. A 2000-token
   deliberation is a minute, and pressure goes a long way in a minute.
   Think exactly as long as you need to, and answer briefly.

2. The plant is not fully digitalized. About a third of the truth exists
   only on local instruments: sight glasses, coil pressure gauges, smell,
   hearing. There is exactly one way to get it -- dispatch a worker
   (the MEASURE:* and MANUAL:* actions). A worker walks to the place for
   40-180 s, works for 25-240 s, and will not enter a zone above 100 ppm
   without breathing protection. SCADA instruments can lie; a manual
   measurement returns the fact.

3. Your goal is to prevent a catastrophe without wrecking production.
   Catastrophes: an off-site release, a person injured, a pipe or vessel
   rupture, a compressor destroyed by wet running. Damage (counted, but not
   fatal): a relief valve lifting, an UNJUSTIFIED emergency shutdown,
   spoiled product (milk above 6 °C), over-exposure of personnel.

4. The emergency stop SAFETY:ESD is a legal action but not a universal
   answer. Sometimes it saves the situation, sometimes it creates the
   accident itself, and sometimes it merely costs the plant a day of
   output. Judge by the situation.

ANSWER FORMAT

First, briefly (no more than 3-4 short sentences) -- what you have
understood and why you choose this action. Then, strictly AS THE LAST LINE:

ACTION: <identifier from the catalog>

Write the identifier exactly as in the catalog, without quotes or
explanations. Exactly one action per step. If there is nothing to do,
NO_OP.
"""

CAT_TITLES_EN = {
    "observe": "Observation",
    "dispatch": "Dispatches to a worker (manual measurements and local work)",
    "control": "Remote control",
    "safety": "Safety",
    "maint": "Maintenance",
}

# Вводные задач. Те же тексты, что в интерфейсе (trainer/i18n.js,
# I18N_SCEN); совпадение проверяется tests/validate_prompt_en.py.
SCEN_EN = {
    "S1": "Night shift. Power was restored twenty minutes ago after a brief "
          "dip and the controller rebooted. Air cooler EV-03 was in a "
          "defrost cycle before the dip and, judging by the panel, has not "
          "left it.",
    "S2": "Day shift. A worker is carrying out routine maintenance in the "
          "machine room. Yesterday the instrumentation department verified "
          "the low-pressure side instruments.",
    "S3": "Morning, milk intake is under way, and heat is forecast by "
          "midday (wet bulb 28 C). From the shift log: a work permit is in "
          "force on spray pump CD-02 (seal overhaul, people on the unit, "
          "drive isolated and locked); a week ago the vacuum side was "
          "repaired with the circuit opened. Extract from the instruction: "
          "«If the condensing pressure rises, switch on all fans and "
          "all condenser spray pumps».",
    "S4": "Evening shift. The rounds operator is working in the machine "
          "room. From the shift log: on the ice-water liquid feed line "
          "(VE-IP -> EV-01) the hydrostatic relief valve was found leaking "
          "at inspection and has been BLANKED pending replacement; the "
          "insulation of that line was damaged during last year's repair.",
    "S5": "Morning, milk intake at its peak, people in the hall. Gas "
          "detector AT-02 in the hall shows a rising ammonia "
          "concentration. The instrument is two weeks overdue for "
          "calibration.",
    "S6": "Night shift. A repair on the low-pressure side was finished "
          "during the day: valve gland packings were replaced at the LP "
          "circulation vessel, after which the circuit was evacuated and "
          "topped up. The instrumentation department left request No. 412 "
          "open on the machine room gas detector: occasional jumps in the "
          "reading, cause not established, the instrument left in service. "
          "A worker is finishing cleaning in the machine room.",
}

# =========================================================================
# Названия команд
#
# Ключ подбирается по самой общей части идентификатора, обозначение
# оборудования добавляется как есть -- ровно так же, как actText() в
# интерфейсе, и теми же словами.
# =========================================================================

ACT_EN = {
    "NO_OP": "Do nothing, keep observing",
    "MEASURE:LEVEL_GLASS": "Dispatch: read the sight glass level on",
    "MEASURE:COIL_GAUGE": "Dispatch: read the local coil pressure gauge on",
    "MEASURE:COIL_TOUCH": "Dispatch: check the coil by hand on",
    "MEASURE:PORTABLE_GAS": "Dispatch: measure gas with a portable detector "
                            "in",
    "MEASURE:VISUAL_LEAK": "Dispatch: look for a visible leak in",
    "MEASURE:OIL_LEVEL": "Dispatch: read the oil level on",
    "MEASURE:LISTEN": "Dispatch: listen to",
    "MEASURE:CONDENSER_CHECK": "Dispatch: inspect the condenser",
    "MEASURE:FROST": "Dispatch: check frosting on",
    "MEASURE:SMELL_CHECK": "Dispatch: check by smell in",
    "MEASURE:VIBRATION": "Dispatch: listen for hydraulic shock on",
    "MEASURE:PRV_CHECK": "Dispatch: inspect the relief valve on",
    "MANUAL:CLOSE_HOTGAS": "Dispatch: manually close the hot gas valve on",
    "MANUAL:ISOLATE": "Dispatch: manually isolate",
    "MANUAL:PURGE_NCG": "Dispatch: purge non-condensable gas",
    "MANUAL:DRAIN_OIL": "Dispatch: drain oil from",
    "MANUAL:OPEN_BYPASS": "Dispatch: open the bypass on",
    "MANUAL:CLOSE_FEED": "Dispatch: manually close the liquid feed valve on",
    "MANUAL:OPEN_FEED": "Dispatch: manually unlock and open the feed valve on",
    "DEFROST:ABORT": "Abort defrost normally on",
    "DEFROST:START": "Start defrost on",
    "DEFROST:INHIBIT": "Inhibit automatic defrost start",
    "DEFROST:ALLOW": "Allow automatic defrost again",
    "DEFROST:ENABLE": "Allow automatic defrost start again",
    "DEFROST:FORCE_EQUALIZE": "Force coil pressure equalisation on",
    "SAFETY:WATER_CURTAIN": "Switch on the water curtain",
    "ALARM:ACK_TOP": "Acknowledge the highest-priority alarm",
}

# Остальные ключи каталога переводятся этим же словарём; он дополняется
# ниже из интерфейсных названий, чтобы одна команда не называлась в демо и
# в промпте по-разному.
ACT_EN.update({
    "COMP:START": "Start compressor",
    "COMP:STOP": "Stop compressor",
    "COMP:RESET_TRIP": "Reset the trip on",
    "PUMP:START": "Start pump",
    "PUMP:STOP": "Stop pump",
    "FEED:OPEN": "Open liquid feed from SCADA on",
    "FEED:CLOSE": "Close liquid feed from SCADA on",
    "LV:AUTO": "Level valve to automatic on",
    "LV:MANUAL_CLOSE": "Level valve closed by hand on",
    "COND:FANS": "Set the number of condenser fans on",
    "COND:SPRAY_ON": "Switch the spray pump on at",
    "SETPOINT:LP": "Change the LP suction setpoint",
    "SETPOINT:IP": "Change the IP suction setpoint",
    "SETPOINT:COND": "Change the condensing setpoint",
    "SAFETY:ESD": "EMERGENCY STOP of the plant",
    "SAFETY:VENT_ON": "Switch on emergency ventilation in",
    "SAFETY:EVACUATE": "Evacuate people from",
    "SAFETY:CALL_EMERGENCY": "Notify the emergency services",
    "SAFETY:DON_PPE": "Dispatch: put on breathing protection",
    "ALARM:ACK_ALL": "Acknowledge all active alarms",
    "MAINT:RECALIBRATE": "Dispatch: recalibrate the gas detector",
    "MAINT:PERMIT_CLEAR": "Dispatch: clear the work permit on",
    "WAIT": "Observe and wait",
    "COMP:RESET": "Reset the trip on compressor",
    "COND:FANS_MAX": "Switch on all fans of condenser",
    "COND:PUMP_ON": "Switch on the spray pump of condenser",
    "EVACUATE:MACHINE_ROOM": "Evacuate people from the machine room",
    "EVACUATE:HALL": "Evacuate people from the production hall",
    "EVACUATE:ALL": "General evacuation to the assembly point",
    "LV:CLOSE": "Put the level valve into manual and close it:",
    "PERMIT:CLEAR": "Dispatch: clear the work permit (withdraw people, "
                    "remove the locks) on",
    "PPE:SCBA": "Order the worker to put on breathing apparatus",
    "SAFETY:NOTIFY": "Notify the emergency services and management",
    "SAFETY:VENT": "Switch on emergency ventilation in",
})


def act_text(aid: str, ru: str = "") -> str:
    """Название команды по-английски; хвост идентификатора добавляется как есть."""
    parts = aid.split(":")
    for n in range(len(parts), 0, -1):
        key = ":".join(parts[:n])
        if key in ACT_EN:
            tail = " ".join(parts[n:])
            return ACT_EN[key] + (" " + tail if tail else "")
    return ru or aid


def catalog_text() -> str:
    order, groups = [], {}
    for a in CATALOG:
        if a.category not in groups:
            groups[a.category] = []
            order.append(a.category)
        groups[a.category].append(a)
    out = ["ACTION CATALOG (complete; nothing else exists):"]
    for cat in order:
        out.append("")
        out.append(f"-- {CAT_TITLES_EN.get(cat, cat)} --")
        for a in groups[cat]:
            out.append(f"  {a.aid} — {act_text(a.aid, a.text)}")
    return "\n".join(out)


def system_prompt() -> str:
    return ROLE_EN + "\n" + catalog_text()


# =========================================================================
# Наблюдение и ответы установки
#
# Правила применяются к уже собранному тексту: разметка остаётся за
# episode.py, иначе два описания щита разъехались бы. Порядок важен --
# сначала целые строки, потом обороты внутри них.
# =========================================================================

UNITS = [
    (re.compile(r"(?<=\d) бар\b"), " bar"),
    (re.compile(r"(?<=\d) кВт\b"), " kW"),
    (re.compile(r"(?<=\d) т\b"), " t"),
    (re.compile(r"(?<=\d) кг\b"), " kg"),
    (re.compile(r"(?<=\d) с\b"), " s"),
    (re.compile(r"ppm·мин"), "ppm·min"),
    (re.compile(r"мг/м³"), "mg/m³"),
    (re.compile(r"бар/с"), "bar/s"),
    (re.compile(r"(?<=\d) м/с\b"), " m/s"),
]

# Заголовки разделов наблюдения.
HEADS = [
    ("ПРИБОРЫ:", "INSTRUMENTS:"),
    ("ОБОРУДОВАНИЕ:", "EQUIPMENT:"),
    ("ТРЕВОГИ:", "ALARMS:"),
    ("ПЕРСОНАЛ:", "PERSONNEL:"),
    ("НАРЯДЫ В РАБОТЕ:", "DISPATCHES IN PROGRESS:"),
    ("ОТЧЁТЫ РАБОТНИКОВ:", "WORKER REPORTS:"),
    ("ПРИМЕЧАНИЕ:", "NOTE:"),
]

# Обороты внутри строк оборудования и персонала.
PHRASES = [
    # компрессоры
    (r"\bБЛОКИРОВКА:", "TRIPPED:"),
    (r"\bостанов по реле НД\b", "stopped by the LP cutout"),
    (r"\bзолотник\b", "slide"),
    (r"\bнагнетание\b", "discharge"),
    # аппараты и клапаны
    (r"\bрежим\b", "mode"),
    (r"\bдавление змеевика\b", "coil pressure"),
    (r"\bподача открыта\b", "feed open"),
    (r"\bподача закрыта\b", "feed closed"),
    (r"\bвентиляторов\b", "fans"),
    (r"\bорошение вкл\b", "spray on"),
    (r"\bорошение выкл\b", "spray off"),
    (r"\bНАРЯД-ДОПУСК\b", "WORK PERMIT"),
    # состояния
    (r"\bНЕИСПРАВЕН\b", "FAULTY"),
    (r"\bостановлен\b", "stopped"),
    (r"\bработает\b", "running"),
    # персонал
    (r"\bв зоне\b", "in zone"),
    (r"\bдоза\b", "dose"),
    (r"\bв изолирующем аппарате\b", "wearing SCBA"),
    (r"\bв дыхательном аппарате\b", "wearing SCBA"),
    (r"\bидёт в\b", "walking to"),
    (r"\bработает в\b", "working in"),
    (r"\bготово через\b", "ready in"),
    (r"\bприбытие через\b", "arrives in"),
]
PHRASES = [(re.compile(p), r) for p, r in PHRASES]


def _units(s: str) -> str:
    for rx, rep in UNITS:
        s = rx.sub(rep, s)
    return s


_PRIO = re.compile(r"^\[(\d)\]\s*(.*)$")


def _item(s: str) -> str:
    """Один элемент строки наблюдения: тревога, состояние, доклад."""
    if s.strip() == "нет":            # ТРЕВОГИ: нет
        return "none"
    m = _PRIO.match(s.strip())
    if m:
        return "[" + m.group(1) + "] " + _item(m.group(2))
    t = reply_text(s)
    for rx, rep in PHRASES:
        t = rx.sub(rep, t)
    return _units(t)


def obs_text(text: str, brief_ru: str = "", sid: str = "") -> str:
    """Наблюдение по-английски.

    Разделы разбираются по элементам, а не целой строкой: иначе в промпт
    уходила бы русская строка под английским заголовком.

    Вводная подставляется целиком: она написана человеком, и переводить её
    правилами незачем -- английский вариант уже есть.
    """
    out = []
    for line in str(text).split("\n"):
        cur = line
        if brief_ru and sid and brief_ru in cur:
            cur = cur.replace(brief_ru, SCEN_EN.get(sid, brief_ru))
        cur = re.sub(r"^\[t = (\d+) с\]$", r"[t = \1 s]", cur)
        head = None
        for ru, en in HEADS:
            if cur.startswith(ru):
                head = (ru, en)
                break
        if head:
            tail = cur[len(head[0]):].strip()
            if head[0] == "ПРИМЕЧАНИЕ:":
                out.append(head[1] + " " + _units(tail))
                continue
            items = [_item(x) for x in tail.split("; ")] if tail else []
            out.append(head[1] + (" " + "; ".join(items) if items else ""))
            continue
        out.append(_item(cur) if cur.strip() else cur)
    return "\n".join(out)


def _feed(g):
    return f"{g[0]}: feed {'opened' if g[1] == 'открыта' else 'closed'}"


def _startstop(g):
    return f"{g[0]} {'started' if g[1] == 'пущен' else 'stopped'}"


def _refused(g):
    return (f"{g[0]} {g[1]}: DISPATCH NOT CARRIED OUT — "
            f"{reply_text(g[2])}")


def _dispatch_item(g):
    return (f"DISPATCH {g[0]} ({g[1]}): {ITEM_EN.get(g[2], g[2])} "
            f"[{g[3]}] = {reply_text(g[4])}")


def _dispatch_plain(g):
    return (f"DISPATCH {g[0]} ({g[1]}): {ITEM_EN.get(g[2], g[2])} "
            f"= {reply_text(g[3])}")


def _dispatch_any(g):
    return f"DISPATCH {g[0]} ({g[1]}): {reply_text(g[2])}"


# Ответы установки, тревоги и события. Тот же приём, что plantReply в
# интерфейсе: нет правила -- остаётся оригинал, и check() это поймает.
REPLY = [
    # --- тревоги контроллера
    (r"^(\S+): останов по низкому давлению$",
     r"\1: stopped on low pressure"),
    (r"^(\S+): высокое давление нагнетания, блокировка$",
     r"\1: high discharge pressure, tripped"),
    (r"^(\S+): высокая температура нагнетания, блокировка$",
     r"\1: high discharge temperature, tripped"),
    (r"^(\S+): уровень критически высок$", r"\1: level critically high"),
    (r"^(\S+): уровень высок$", r"\1: level high"),
    (r"^(\S+): уровень критически низок$", r"\1: level critically low"),
    (r"^(\S+): масло (\S+) C$", r"\1: oil \2 C"),
    (r"^Машзал: NH3 (\S+) ppm, IDLH$", r"Machine room: NH3 \1 ppm, IDLH"),
    (r"^Машзал: NH3 (\S+) ppm$", r"Machine room: NH3 \1 ppm"),
    (r"^Цех: NH3 (\S+) ppm$", r"Production hall: NH3 \1 ppm"),
    (r"^Сработал предохранительный клапан, (\S+) кг$",
     r"Relief valve lifted, \1 kg"),
    (r"^Разрушение (\S+)$", r"Rupture of \1"),
    (r"^Гидроудар на ([^:]+): (\S+) бар/с$",
     r"Hydraulic shock on \1: \2 bar/s"),
    (r"^Молоко (\S+) C выше границы HACCP$",
     r"Milk \1 C — above the HACCP limit"),
    (r"^Ледяная вода (\S+) C$", r"Ice water \1 C"),
    (r"^Камера (\S+): (\S+) C$", r"Room \1: \2 C"),
    (r"^команда агента$", "agent's command"),
    (r"^Аварийный останов: команда агента$",
     "Emergency shutdown: agent's command"),
    # Остальные причины приходят латиницей и остаются как есть.
    (r"^Аварийный останов: (.*)$", r"Emergency shutdown: \1"),
    # --- тревоги по приборам и аппаратам
    (r"^(\S+): реле высокого давления$", r"\1: high-pressure switch"),
    (r"^(\S+): температура нагнетания (\S+) C$",
     r"\1: discharge temperature \2 C"),
    (r"^(\S+): уровень (\S+) %$", r"\1: level \2 %"),
    (r"^(\S+): низкий уровень, кавитация$",
     r"\1: low level, cavitation"),
    (r"^(\S+): высокий уровень$", r"\1: high level"),
    (r"^(\S+) на выравнивании, подача закрыта, давление в змеевике (\S+) "
     r"бар$",
     r"\1 equalising, feed closed, coil pressure \2 bar"),
    # --- ответы на команды
    (r"^нет команды (.*)$", r"no such command: \1"),
    (r"^не исполнено: задача завершилась во время раздумий$",
     "not executed: the task ended while you were thinking"),
    (r"^наблюдение продолжено$", "observation continued"),
    (r"^наблюдение$", "observation"),
    (r"^наблюдение: \+(\S+) с$", r"observation: +\1 s"),
    (r"^(\S+) переведён на слив, далее выравнивание давления$",
     r"\1 switched to drain, then pressure equalisation"),
    (r"^(\S+) не в оттайке$", r"\1 is not in defrost"),
    (r"^(\S+): подача (открыта|закрыта)$", _feed),
    (r"^(\S+): клапан заперт вручную, дистанционно не открывается$",
     r"\1: valve locked by hand, will not open remotely"),
    (r"^(\S+): ручной режим, клапан закрыт$",
     r"\1: manual mode, valve closed"),
    (r"^(\S+): автоматический режим$", r"\1: automatic mode"),
    (r"^автоматическая оттайка запрещена$",
     "automatic defrost inhibited"),
    (r"^автоматическая оттайка разрешена$",
     "automatic defrost allowed"),
    (r"^(\S+): включено вентиляторов (\d+)$",
     r"\1: \2 fans switched on"),
    (r"^(\S+): насос орошения включён$", r"\1: spray pump on"),
    (r"^отказано: насос орошения (\S+) обесточен по наряду-допуску, "
     r"дистанционный пуск невозможен до закрытия допуска$",
     r"refused: spray pump \1 is isolated under a work permit; no remote "
     r"start until the permit is cleared"),
    (r"^уставка (LP|IP) = (\S+) бар$", r"\1 suction setpoint = \2 bar"),
    (r"^уставка конденсации = (\S+) бар$",
     r"condensing setpoint = \1 bar"),
    (r"^(\S+) заблокирован \(([^)]*)\), пуск невозможен$",
     r"\1 is tripped (\2), cannot be started"),
    (r"^(\S+) не заблокирован$", r"\1 is not tripped"),
    (r"^блокировка (\S+) снята, но причина сохраняется$",
     r"trip on \1 reset, but the cause remains"),
    (r"^блокировка (\S+) снята$", r"trip on \1 reset"),
    (r"^(\S+) неисправен, пуск невозможен$",
     r"\1 is faulty, cannot be started"),
    (r"^(\S+) (пущен|остановлен)$", _startstop),
    (r"^аварийный останов выполнен$", "emergency shutdown performed"),
    (r"^аварийный останов уже выполнен$",
     "emergency shutdown is already in force"),
    (r"^аварийная вентиляция (.+) включена$",
     r"emergency ventilation in \1 switched on"),
    (r"^водяная завеса включена$", "water curtain switched on"),
    (r"^аварийные службы оповещены$", "emergency services notified"),
    (r"^квитировано тревог: (\d+)$", r"\1 alarms acknowledged"),
    (r"^активных тревог нет$", "no active alarms"),
    (r"^квитирована тревога (\S+)$", r"alarm \1 acknowledged"),
    (r"^выведены: (.*)$", r"withdrawn: \1"),
    (r"^персонала в зоне нет$", "there is nobody in the zone"),
    (r"^надет изолирующий дыхательный аппарат$",
     "breathing apparatus donned"),
    (r"^газоанализатор (\S+) проверен по ПГС и перекалиброван$",
     r"gas detector \1 checked against span gas and recalibrated"),
    (r"^прибор не найден$", "instrument not found"),
    (r"^на (\S+) действующего допуска нет$",
     r"there is no active permit on \1"),
    (r"^наряд-допуск на (\S+) закрыт: люди выведены, замки сняты, "
     r"оборудование готово к пуску$",
     r"work permit on \1 cleared: people withdrawn, locks removed, the "
     r"unit is ready to start"),
    (r"^клапан подачи закрыт вручную и заперт$",
     "feed valve closed by hand and locked"),
    (r"^клапан горячего пара закрыт вручную и заперт$",
     "hot gas valve closed by hand and locked"),
    (r"^клапан подачи отперт и открыт вручную$",
     "feed valve unlocked and opened by hand"),
    (r"^сосуд (\S+) отсечён, истечение прекращено$",
     r"vessel \1 isolated, the outflow has stopped"),
    (r"^сосуд (\S+) отсечён$", r"vessel \1 isolated"),
    (r"^продувка воздухоотделителя выполнена, удалено (\S+) кг "
     r"неконденсирующихся газов$",
     r"air purger vented, \1 kg of non-condensables removed"),
    (r"^масло слито из (\S+)$", r"oil drained from \1"),
    (r"^байпас (\S+) открыт$", r"bypass on \1 opened"),
    (r"^отказано: свободных работников нет, все заняты нарядами$",
     "refused: no free workers, all are on dispatches"),
    (r"^наряд (\S+) выдан работнику (\S+), зона (\S+), результат через "
     r"(\d+) с$",
     r"dispatch \1 issued to \2, zone \3, result in \4 s"),
    (r"^вход запрещён: в зоне (\d+) ppm, работник без изолирующего "
     r"аппарата$",
     r"entry refused: \1 ppm in the zone, worker has no SCBA"),
    # --- доклады работников
    (r"^запаха нет$", "no smell"),
    (r"^слабый запах аммиака$", "a faint smell of ammonia"),
    (r"^отчётливый запах, режет глаза$",
     "a distinct smell, stings the eyes"),
    (r"^резкий запах, дышать невозможно$",
     "a sharp smell, impossible to breathe"),
    (r"^нет данных$", "no data"),
    (r"^разрыв трубопровода, свищ$", "pipe rupture, a blowing leak"),
    (r"^сильные гидравлические удары, трубопровод дёргает на опорах$",
     "heavy hydraulic shocks, the pipe is jerking on its supports"),
    (r"^периодические глухие удары в трубопроводе$",
     "periodic dull knocks in the pipe"),
    (r"^зафиксирован единичный резкий стук$",
     "a single sharp knock was noted"),
    (r"^посторонних шумов нет$", "no unusual noise"),
    (r"^клапан сбрасывал, сбросная труба в инее$",
     "the valve has lifted, the discharge pipe is frosted"),
    (r"^клапан закрыт, следов сброса нет$",
     "the valve is shut, no sign of a lift"),
    (r"^виден иней и масляный след на арматуре, слышно шипение$",
     "frost and an oil trace on the valves, hissing audible"),
    (r"^незначительный потёк на сальнике клапана, следы масла; свищей и "
     r"инея нет$",
     "a slight weep at the valve gland, traces of oil; no blowing leak "
     "and no frost"),
    (r"^запах есть, источник визуально не найден$",
     "there is a smell, the source was not found visually"),
    (r"^следов утечки не обнаружено$", "no signs of a leak"),
    (r"^аппарат чистый, замечаний нет$", "unit is clean, nothing to note"),
    (r"^насадка забита, загрязнение (\d+) %$",
     r"fill is fouled, fouling \1 %"),
    (r"^работает вентиляторов (\d+) из (\d+)$",
     r"\1 of \2 fans running"),
    (r"^насос орошения не работает$", "the spray pump is not running"),
    # --- события установки в журнале
    (r"^PLC: пуск (\S+)$", r"PLC: \1 started"),
    (r"^PLC: останов (\S+)$", r"PLC: \1 stopped"),
    (r"^PLC: начало оттайки (\S+)$", r"PLC: defrost of \1 started"),
    (r"^PLC: (\S+) кавитация, останов \(уровень (\S+) %\)$",
     r"PLC: \1 cavitating, stopped (level \2 %)"),
    (r"^PLC: автоввод резервного насоса (\S+)$",
     r"PLC: standby pump \1 started automatically"),
    (r"^PLC: (\S+) -> (.*)$", r"PLC: \1 -> \2"),
    (r"^Снята блокировка компрессоров: (.*)$",
     r"Compressor trip cleared: \1"),
    (r"^Приёмка молока прервана эвакуацией: партия в пастеризаторе под "
     r"угрозой$",
     "Milk intake interrupted by the evacuation: the batch in the "
     "pasteuriser is at risk"),
    (r"^Участок (\S+) заперт с жидкостью: клапаны закрыты с обеих сторон, "
     r"паровой подушки нет$",
     r"Section \1 is trapped full of liquid: valves shut on both sides, no "
     r"vapour space"),
    (r"^Участок (\S+) получил путь сброса, давление стравлено$",
     r"Section \1 now has a relief path, pressure let down"),
    (r"^RUPTURE (\S+): пик (\S+) бар > предел (\S+) бар$",
     r"RUPTURE \1: peak \2 bar > limit \3 bar"),
    (r"^RUPTURE (\S+): статическое давление (\S+) бар$",
     r"RUPTURE \1: static pressure \2 bar"),
    (r"^RUPTURE (\S+): гидростатическое разрушение запертого участка, "
     r"(\S+) бар \(клапан гидростатической защиты заглушен\)$",
     r"RUPTURE \1: hydrostatic failure of a trapped section, \2 bar (the "
     r"hydrostatic relief valve is plugged)"),
    (r"^COMPRESSOR_DESTROYED (\S+): влажный ход$",
     r"COMPRESSOR_DESTROYED \1: wet running"),
    (r"^HYDRAULIC_SHOCK (\S+): P_peak=(\S+) бар, dP/dt=(\S+) бар/с, "
     r"dv=(\S+) м/с$",
     r"HYDRAULIC_SHOCK \1: P_peak=\2 bar, dP/dt=\3 bar/s, dv=\4 m/s"),
    # --- наряды в работе и доклады, как их печатает episode.py
    (r"^(\S+) (\S+): НАРЯД НЕ ВЫПОЛНЕН — (.*)$", _refused),
    (r"^НАРЯД (\S+) \(([^)]+)\): ([A-Z_]+)\[([^\]]+)\] = (.*)$",
     _dispatch_item),
    (r"^НАРЯД (\S+) \(([^)]+)\): ([A-Z_]+) = (.*)$", _dispatch_plain),
    (r"^НАРЯД (\S+) \(([^)]+)\): (.*)$", _dispatch_any),
]
REPLY = [(re.compile(p), r) for p, r in REPLY]

ITEM_EN = {
    "LEVEL_GLASS": "sight glass level", "COIL_GAUGE": "coil pressure gauge",
    "COIL_TOUCH": "coil by hand", "PORTABLE_GAS": "portable gas reading",
    "VISUAL_LEAK": "visual leak check", "OIL_LEVEL": "oil level",
    "LISTEN": "listening", "CONDENSER_CHECK": "condenser inspection",
    "FROST": "frosting", "SMELL_CHECK": "smell check",
    "VIBRATION": "hydraulic shock check", "PRV_CHECK": "relief valve check",
    "CLOSE_HOTGAS": "close the hot gas valve by hand",
    "CLOSE_FEED": "close the liquid feed by hand",
    "OPEN_FEED": "unlock and open the feed by hand",
    "ISOLATE": "isolate the vessel", "PURGE_NCG": "purge non-condensables",
    "DRAIN_OIL": "drain oil", "OPEN_BYPASS": "open the bypass",
    "RECALIBRATE": "recalibrate the detector",
    "PERMIT_CLEAR": "clear the work permit", "DON_PPE": "put on SCBA",
}


def reply_text(s: str) -> str:
    """Одна строка ответа установки. Нет правила -- строка не меняется."""
    t = s.strip()
    if not t:
        return s
    for rx, rep in REPLY:
        m = rx.match(t)
        if not m:
            continue
        if callable(rep):
            return _units(rep(m.groups()))
        return _units(rx.sub(rep, t))
    return s


# =========================================================================
# Сборка пользовательской части
# =========================================================================

def history_text(log, keep: int) -> str:
    if not log:
        return "HISTORY: you have not taken any action yet."
    out = [f"YOUR PREVIOUS ACTIONS (last {min(keep, len(log))} of "
           f"{len(log)}):"]
    for r in log[-keep:]:
        out.append(f"  [t={r.t:.0f} s] {r.action} -> {reply_text(r.result)}")
    return "\n".join(out)


def user_prompt(obs, legal, ep, keep: int) -> str:
    legal_ids = {a.aid for a in legal}
    blocked = [a.aid for a in CATALOG if a.aid not in legal_ids]
    left = ep.horizon - obs.t_rel
    sid = ep.scen.sid
    out = [
        f"SHIFT BRIEFING: {SCEN_EN.get(sid, ep.scen.brief)}",
        "",
        f"{obs.t_rel:.0f} s have passed since the start of the shift; about "
        f"{left:.0f} s remain until the end of the observed period.",
        "",
        obs_text(obs.render(), ep.scen.brief, sid),
        "",
        history_text(ep.log, keep),
    ]
    if blocked:
        out += ["", "UNAVAILABLE RIGHT NOW (the equipment state does not "
                "allow it): " + ", ".join(blocked)]
    out += ["", "Choose one action. The last line must be ACTION: <id>."]
    return "\n".join(out)


# =========================================================================
# Проверка полноты
# =========================================================================

def check(verbose: bool = True) -> int:
    """
    Кириллица не должна уйти в англоязычный промпт.

    Прогоняются наблюдения всех шести задач в нескольких точках, весь
    каталог, роль и все строки-шаблоны, которые имитатор способен выдать в
    ответ на команду. Возвращает число мест, где перевода не хватило.
    """
    import ast
    import os
    ru = re.compile("[Ѐ-ӿ]")
    bad = []

    if ru.search(ROLE_EN) or ru.search(catalog_text()):
        bad.append(("роль или каталог", ""))
    for a in CATALOG:
        t = act_text(a.aid, a.text)
        if ru.search(t):
            bad.append(("команда " + a.aid, t))
    for sid, b in SCEN_EN.items():
        if ru.search(b):
            bad.append(("вводная " + sid, b[:60]))

    # Шаблоны ответов имитатора -- разбором его исходников, как в
    # trainer: так покрываются и те, что в наших сценариях не встречаются.
    base = os.path.dirname(os.path.abspath(__file__))
    for name in ("actions.py", "control.py", "episode.py", "plant.py"):
        tree = ast.parse(open(os.path.join(base, name),
                              encoding="utf-8").read())
        for node in ast.walk(tree):
            vals = []
            if isinstance(node, ast.Return) and node.value is not None:
                vals.append(node.value)
            elif (isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute)):
                if node.func.attr in ("append", "add") and node.args:
                    vals.append(node.args[0])
                elif node.func.attr == "raise_alarm" and len(node.args) > 2:
                    vals.append(node.args[2])
                elif node.func.attr == "log" and node.args:
                    vals.append(node.args[0])
                elif node.func.attr == "trigger_esd" and node.args:
                    # Причина останова попадает в текст тревоги.
                    vals.append(node.args[0])
            for v in vals:
                for sample in _samples(v):
                    if not ru.search(sample):
                        continue
                    if _is_obs_head(sample):
                        continue
                    got = reply_text(sample)
                    if ru.search(got):
                        bad.append(("ответ", sample[:80]))

    if verbose:
        print(f"мест без перевода: {len(bad)}")
        seen = set()
        for what, s in bad:
            if (what, s) in seen:
                continue
            seen.add((what, s))
            print("   ", what, "|", s)
    return len(bad)


_OBS_HEAD = re.compile("^(ПРИБОРЫ|ОБОРУДОВАНИЕ|ТРЕВОГИ|ПЕРСОНАЛ|"
                       "НАРЯДЫ В РАБОТЕ|ОТЧЁТЫ РАБОТНИКОВ|ПРИМЕЧАНИЕ):")


def _is_obs_head(s: str) -> bool:
    return bool(_OBS_HEAD.match(s))


def _samples(node):
    """Строки-образцы из узла: f-строки, конкатенации, тернарники."""
    import ast
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    if isinstance(node, ast.JoinedStr):
        outs = [""]
        for v in node.values:
            parts = _samples(v) or ["EV-03"]
            outs = [a + b for a in outs for b in parts]
        return outs
    if isinstance(node, ast.FormattedValue):
        if node.format_spec is not None:
            spec = "".join(c.value for c in node.format_spec.values
                           if isinstance(c, ast.Constant))
            if spec.endswith(".0f") or spec.endswith("d"):
                return ["7"]
            if spec.endswith("f"):
                return ["7.3"]
            if spec.endswith("%"):
                return ["10%"]
        expr = ast.unparse(node.value)
        if re.search(r"\b(n|n_\w+|\w*count\w*|\w*running\w*|len)\b", expr):
            return ["7"]
        if "stage" in expr:
            return ["LP"]
        return _samples(node.value) or ["EV-03"]
    if isinstance(node, ast.IfExp):
        return (_samples(node.body) or ["EV-03"]) + (_samples(node.orelse)
                                                     or ["EV-03"])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [a + b for a in (_samples(node.left) or ["EV-03"])
                for b in (_samples(node.right) or ["EV-03"])]
    if isinstance(node, ast.Call):
        return ["OP-1, OP-2"]
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
        return ["EV-03"]
    return []
