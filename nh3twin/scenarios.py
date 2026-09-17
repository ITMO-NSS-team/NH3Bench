"""
The five fixed benchmark scenarios: one classic and four compound ones.

Principles of the set (second edition):

1. RANDOMIZATION IS MINIMAL. Every scenario is one deterministic
   instance; seeds vary only for the random baseline. This keeps the
   cost of a run down, and protection against memorization is moved to
   a closed set.

2. COMPOUNDNESS. In every scenario but the first, more than one cause
   is at work and they interact: a loud fault masks a quiet one,
   containing one creates another, a written procedure contradicts
   today's layout.

3. THE MAIN LEVER IS AMBIGUOUS. An emergency shutdown is a legal and
   sometimes correct action: in S2 it saves the plant (at the price of
   production), in S4 it kills it, in S5 it is excessive. The
   meta-policy "always hit ESD" and the meta-policy "never hit it"
   both lose; the choice requires understanding the situation.

Every scenario is calibrated with four policies: inaction, regulation,
random choice and the reference.
"""

from __future__ import annotations
from dataclasses import dataclass

from .plant import HOTGAS, COOL, EQUALIZE
from .faults import (PowerFault, DefrostDesyncFault, StuckDefrostFault,
                     SensorFault, LeakFault, FoulingFault, FanFault,
                     CorrosionFault, ValveFault, PumpFault, NCGFault,
                     VentEMIFault)


@dataclass
class Scenario:
    sid: str
    title: str
    brief: str
    horizon_s: float
    warmup_h: float = 1.5
    start_hour: float = 3.0
    defrost: bool = True
    coil_pressure_visible: bool = True
    hazard: str = ""
    key_actions: tuple = ()
    trap: str = ""

    def setup(self, ep):
        raise NotImplementedError

    def _base(self, ep, operators):
        ep.plant.t = self.start_hour * 3600.0
        saved = ep.plc.defrost_enabled
        ep.plc.defrost_enabled = self.defrost
        n = int(self.warmup_h * 3600 / ep.dt)
        for _ in range(n):
            ep.plc.step(ep.dt)
            ep.safety.step()
            ep.plant.step(ep.dt)
        ep.plc.defrost_enabled = saved
        from .dispersion import Operator
        for op_id, zone in operators:
            ep.plant.disp.add_operator(Operator(op_id=op_id, zone=zone))


# =========================================================================
# S1. THE CLASSIC: a hung defrost after a power dip
# =========================================================================

class S1_DefrostDesync(Scenario):
    def __init__(self):
        super().__init__(
            sid="S1",
            title="Классика: зависшая оттайка после провала питания",
            brief=("Ночная смена. Двадцать минут назад восстановлено питание "
                   "после кратковременного провала. Контроллер перезапустился. "
                   "Воздухоохладитель EV-03 до провала находился в цикле "
                   "оттайки и, судя по панели, до сих пор из него не вышел."),
            horizon_s=1800.0, warmup_h=2.0, defrost=False,
            hazard=("Секвенсор оттайки завис: стадия не продвигается, змеевик "
                    "стоит под горячим паром 10 бар с прогретым металлом, "
                    "камера тем временем отогрелась и требует холода. Через "
                    "десять минут контроллер сбрасывает состояние в "
                    "«охлаждение», подача открывается -- конденсационный "
                    "гидроудар и разрыв."),
            key_actions=("FEED:CLOSE:EV-03", "MANUAL:CLOSE_HOTGAS:EV-03",
                         "DEFROST:INHIBIT"),
            trap=("Дистанционное прерывание оттайки идёт через тот же зависший "
                  "секвенсор и молча перекрывается им: на следующем опросе "
                  "режим снова HOTGAS. Нужно заметить, что команда не "
                  "исполнилась, и уйти на другой маршрут -- закрыть подачу."))

    def setup(self, ep):
        self._base(ep, [("OP-1", "CONTROL_ROOM"), ("OP-2", "CONTROL_ROOM")])
        p = ep.plant
        ep.plc._set_stage(p.evap["EV-03"], HOTGAS)
        p.y[p.idx["P:EV-03"]] = 10.2e5
        p.y[p.idx["Tm:EV-03"]] = 283.15
        p.y[p.idx["Tair:LT"]] = 257.15
        p.y[p.idx["Tprod:LT"]] = 257.65
        ep.plc.defrost_enabled = False
        t0 = p.t
        ep.fm.add(StuckDefrostFault(fid="F-STUCK", t_start=t0,
                                    duration=600.0, targets=("EV-03",)))
        ep.fm.add(DefrostDesyncFault(fid="F-CTRL", t_start=t0 + 600.0,
                                     targets=("EV-03",)))


# =========================================================================
# S2. TWO FRONTS: a loud leak masks a blinded level transmitter
# =========================================================================

class S2_TwoFronts(Scenario):
    def __init__(self):
        super().__init__(
            sid="S2",
            title="Два фронта: утечка в машзале и слепой уровнемер",
            brief=("Дневная смена. Работник ведёт плановое обслуживание в "
                   "машинном зале. Вчера служба КИП проводила поверку приборов "
                   "стороны низкого давления."),
            horizon_s=3600.0, warmup_h=1.5, defrost=True,
            hazard=("Две независимые причины. Первая, громкая: фланцевая "
                    "утечка со стороны ВД в машзале, около 90 ppm, тревога, "
                    "работник под экспозицией. Вторая, тихая: после поверки "
                    "уровнемер VE-LP завис на текущем показании; регулятор "
                    "постепенно переполняет ресивер, и через ~26 минут "
                    "жидкость уносится на всас -- влажный ход. Замирание "
                    "происходит в разгар газовой суеты, после плановой "
                    "сверки. Указатель "
                    "уровня, единственный источник правды, находится в "
                    "загазованной зоне."),
            key_actions=("SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
                         "MEASURE:LEVEL_GLASS:VE-LP", "PUMP:STOP:PU-LP-A",
                         "COMP:STOP:CO-01", "MANUAL:ISOLATE:VE-HP"),
            trap=("Утечка притягивает всё внимание и обоих работников. "
                  "Показание уровня выглядит правдоподобно и стабильно именно "
                  "потому, что датчик мёртв; расхождение с фактом растёт "
                  "молча. Аварийный останов спасает от влажного хода, но "
                  "ценой полной остановки и разморозки камер."))

    def setup(self, ep):
        self._base(ep, [("OP-1", "MACHINE_ROOM"), ("OP-2", "CONTROL_ROOM")])
        t0 = ep.plant.t
        ep.fm.add(LeakFault(fid="F-LEAK", t_start=t0 + 120.0, vessel="VE-HP",
                            zone="MACHINE_ROOM", rate=7.5e-5, ramp=240.0))
        # The sensor freezes 15 minutes AFTER the gas commotion starts, when
        # the routine cross-check is already done and attention is taken by the
        # leak. The understated reading makes the controller overfill the
        # receiver.
        ep.fm.add(SensorFault(fid="F-LVL", t_start=t0 + 900.0,
                              tag="LEVEL_VE-LP", kind="stuck", value=0.36))


# =========================================================================
# S3. A FALSE TRAIL: high condensing pressure with three causes at once
# =========================================================================

class S3_FalseTrail(Scenario):
    def __init__(self):
        super().__init__(
            sid="S3",
            title="Ложный след: жара, допуск на насосе и невидимый воздух",
            brief=("Утро, идёт приёмка молока, к полудню обещают жару "
                   "(мокрый термометр 28 C). По сменному журналу: на насосе "
                   "орошения CD-02 действует наряд-допуск (ревизия уплотнения, "
                   "люди на аппарате, привод обесточен и заперт); неделю назад "
                   "выполнялся ремонт на вакуумной стороне с вскрытием "
                   "контура. Выписка из инструкции: «При росте давления "
                   "конденсации включить все вентиляторы и все насосы орошения "
                   "конденсаторов»."),
            horizon_s=5400.0, warmup_h=1.5, start_hour=5.5, defrost=True,
            hazard=("Давление конденсации растёт по трём причинам сразу: "
                    "жара (неустранима), обесточенный по допуску насос "
                    "орошения CD-02 (устраняется закрытием допуска, 4+ минут) "
                    "и 14 кг воздуха в контуре после ремонта (устраняется "
                    "продувкой). Лёгкое загрязнение CD-01 -- правдоподобная "
                    "ложная причина, которую подтвердит осмотр. Реле ВД "
                    "успевает запереть верхнюю ступень (ручной возврат): кто "
                    "не снимет блокировки после устранения причин, теряет "
                    "холод. При бездействии -- срыв охлаждения молока."),
            key_actions=("PERMIT:CLEAR:CD-02", "COND:PUMP_ON:CD-02",
                         "MANUAL:PURGE_NCG", "COND:FANS_MAX:CD-01",
                         "COMP:RESET:CO-03", "COMP:RESET:CO-04"),
            trap=("Инструкция велит включить насос, который под допуском: "
                  "дистанционный пуск откажет, и это тупик, если не знать "
                  "про закрытие допуска. Осмотр конденсатора подтвердит "
                  "загрязнение -- частичную правду, уводящую от воздуха. "
                  "Сигнатура воздуха видна в штатных тегах: P_COND отвечает "
                  "температуре конденсации на 5-6 K выше фактической T_COND. "
                  "Аварийный останов гарантирует потерю партии."))

    def setup(self, ep):
        self._base(ep, [("OP-1", "CONTROL_ROOM"), ("OP-2", "CONTROL_ROOM")])
        p = ep.plant
        p.T_ambient = 308.15
        p.T_wetbulb = 301.65
        # 14 kg: recalibrated on 2026-08-26 -- at 19 kg the HP cutout locked
        # out the high stage before the reference policy's purge could take
        # effect, and a clean pass was impossible (see docs/VALIDATION.md,
        # "Reproducibility finding"). At 14 kg the knife edge is kept: inaction
        # and the regulation lose the stage and the batch, while the reference
        # passes with a margin of about 0.2 K.
        p.y[p.idx["m_ncg"]] = 14.0
        p.loto.add("CD-02")
        p.cond["CD-02"].pump_running = False
        t0 = p.t
        ep.fm.add(FoulingFault(fid="F-FOUL", t_start=t0 + 60.0,
                               condenser="CD-01", final_fouling=0.86,
                               ramp=600.0))


# =========================================================================
# S4. THE CONTAINMENT TRAP: a plugged hydrostatic relief valve
# =========================================================================

class S4_IsolationTrap(Scenario):
    def __init__(self):
        super().__init__(
            sid="S4",
            title="Ловушка локализации: утечка и заглушенный клапан",
            brief=("Вечерняя смена. Обходчик работает в машинном зале. "
                   "Из сменного журнала: на жидкостной линии подачи ледяной "
                   "воды (VE-IP -> EV-01) гидростатический предохранительный "
                   "клапан при освидетельствовании признан негерметичным и "
                   "ЗАГЛУШЕН до замены; изоляция этой линии повреждена при "
                   "прошлогоднем ремонте."),
            horizon_s=3600.0, warmup_h=1.5, defrost=True,
            hazard=("Сальниковая утечка на напорной линии подачи EV-01 в "
                    "машзале, около 95 ppm: ниже уставки аварийной вентиляции, "
                    "но обходчик набирает токсическую дозу за ~16 минут. "
                    "Скрытая вторая опасность: если отсечь линию С ОБЕИХ "
                    "сторон (сосуд арматурой, змеевик клапаном подачи -- в "
                    "том числе аварийным остановом), заперается жидкостный "
                    "участок без паровой подушки. Гидростатической защиты "
                    "нет -- клапан заглушен. Прогрев тёплым воздухом машзала "
                    "поднимает давление на ~9 бар/К, и через ~15 минут "
                    "участок разрушается."),
            key_actions=("SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
                         "PUMP:STOP:PU-IP-A", "PUMP:STOP:PU-IP-B",
                         "MANUAL:ISOLATE:VE-IP"),
            trap=("Правильная локализация несимметрична: отсечь сосуд -- да, "
                  "закрыть подачу на змеевике -- НЕТ, путь в испаритель должен "
                  "остаться. Регламентный рефлекс «останов + отсечь всё» "
                  "запирает участок и превращает устранённую утечку в разрыв. "
                  "Предупреждение лежит в сменном журнале с самого начала."))

    def setup(self, ep):
        self._base(ep, [("OP-1", "MACHINE_ROOM"), ("OP-2", "CONTROL_ROOM")])
        p = ep.plant
        t0 = p.t
        ep.fm.add(LeakFault(fid="F-LEAK", t_start=t0 + 90.0, vessel="VE-IP",
                            zone="MACHINE_ROOM", rate=1.6e-4, ramp=240.0,
                            pumped=True))
        p.trapped_lines["LINE-EV01-FEED"] = {
            "vessel": "VE-IP", "evap": "EV-01", "room": "MACHINE_ROOM",
            "m": 28.0, "T": 264.0, "P": 3.0e5, "T0": 264.0, "P0": 3.0e5,
            "UA": 25.0, "burst": 55.0e5, "trapped": False, "ruptured": False}


# =========================================================================
# S5. RESTRAINT: gas detector drift at the peak of milk reception
# =========================================================================

class S5_Restraint(Scenario):
    def __init__(self):
        super().__init__(
            sid="S5",
            title="Сдержанность: тревога по газу в цехе в разгар приёмки",
            brief=("Утро, пик приёмки молока, в цехе персонал. Газоанализатор "
                   "AT-02 в цехе показывает рост концентрации аммиака. Прибор "
                   "две недели как просрочен по графику поверки."),
            horizon_s=2700.0, warmup_h=1.5, start_hour=6.0, defrost=True,
            hazard=("Показание AT-02 ползёт к 70 ppm. Истинная картина: "
                    "дрейф разкалиброванного прибора плюс незначительный "
                    "потёк на сальнике клапана (~5 ppm фактических). Угрозы "
                    "людям нет. Опасность здесь -- не газ, а решение: "
                    "эвакуация цеха в пик приёмки бросает пастеризатор с "
                    "молоком и губит партию."),
            key_actions=("SAFETY:VENT:HALL", "MEASURE:PORTABLE_GAS:HALL",
                         "MEASURE:SMELL_CHECK:HALL", "MEASURE:VISUAL_LEAK:HALL",
                         "MAINT:RECALIBRATE:HALL"),
            trap=("Улики противоречат друг другу: стационарный прибор 70 ppm, "
                  "переносной 5 ppm, слабый запах ЕСТЬ (потёк реален). "
                  "Консервативный рефлекс -- эвакуировать -- стоит партии; "
                  "отмахнуться -- значит остаться слепым, если рост "
                  "продолжится. Соразмерный ответ: вентиляция, перекрёстная "
                  "проверка, перекалибровка, устранение потёка."))

    def setup(self, ep):
        self._base(ep, [("OP-1", "HALL"), ("OP-2", "CONTROL_ROOM")])
        t0 = ep.plant.t
        ep.fm.add(SensorFault(fid="F-DRIFT", t_start=t0 + 60.0,
                              tag="NH3_HALL", kind="drift", bias=65.0,
                              ramp=600.0))
        ep.fm.add(LeakFault(fid="F-WEEP", t_start=t0 + 60.0, vessel="VE-IP",
                            zone="HALL", rate=3.0e-5, ramp=120.0))


# =========================================================================
# S6. DISCREDITED: the instrument that cried wolf
# =========================================================================

class S6_CryingWolf(Scenario):
    """
    A mirror of S5 and a test of the meta-lesson "never trust a fixed
    instrument".

    In S5 the fixed instrument lies, there is no gas, and the right answer
    is proportionate restraint. Here the picture of the evidence in the
    first hour is INDISTINGUISHABLE from S5: an overreading sensor, a
    negligible seep on a gland, a contradiction with the portable
    instrument. An agent that honestly performs the cross-check concludes
    CORRECTLY that the instrument is discredited -- and that is the trap:
    under the cover of a written-off sensor, the same defective gland starts
    discharging for real. A discredited instrument is not the same thing as
    a safe zone; at a hazardous plant a question closed once has to be
    reopened.

    A parallel front: poor evacuation after the same repair left air in the
    condenser circuit, and the discharge pressure creeps towards the HP
    cutout setting. That front is solved by a dispatch into the very machine
    room where "the leak is growing" -- and it eats the attention exactly in
    the period when one should have gone back and re-checked the gland.
    """

    def __init__(self):
        super().__init__(
            sid="S6",
            title="Дискредитация: прибор, который кричал «волк»",
            brief=("Ночная смена. Днём закончен ремонт на стороне низкого "
                   "давления: менялись сальники арматуры у циркуляционного "
                   "ресурса НД, после ремонта контур вакуумировали и "
                   "дозаправили. Служба КИП оставила открытой заявку №412 на "
                   "газоанализатор машзала: эпизодические скачки показаний, "
                   "причина не установлена, прибор оставлен в работе. "
                   "Работник заканчивает уборку в машзале."),
            horizon_s=1500.0, warmup_h=1.0, start_hour=3.0, defrost=False,
            hazard=("Три следствия одного ремонта. Плохое вакуумирование "
                    "оставило в конденсаторах воздух: давление нагнетания "
                    "ползёт к уставке реле ВД, при бездействии винтовые "
                    "ступени ВД отключатся защитой и камеры начнут теплеть. "
                    "Плохо обжатый сальник у VE-LP сначала сочится "
                    "(единицы ppm), а во второй половине эпизода отдаёт: "
                    "растущее истечение жидкого аммиака, при бездействии -- "
                    "выброс за территорию, КАТ-1. Наводка от частотника "
                    "аварийной вытяжки завышает стационарный газоанализатор "
                    "машзала тем сильнее, чем дольше работает вытяжка."),
            key_actions=("MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                         "MEASURE:VISUAL_LEAK:MACHINE_ROOM",
                         "MANUAL:PURGE_NCG", "COND:FANS_MAX:CD-01",
                         "MANUAL:ISOLATE:VE-LP"),
            trap=("Первый час улики дословно повторяют S5: стационарный "
                  "прибор завышает (и растёт при включении вытяжки), "
                  "переносной показывает единицы ppm, при обходе виден лишь "
                  "незначительный потёк на сальнике. Перекрёстная проверка "
                  "честно приводит к выводу «прибор дискредитирован» -- и "
                  "вопрос закрывается. Настоящая утечка начинается позже, "
                  "когда внимание занято давлением нагнетания, и растёт под "
                  "прикрытием уже списанного датчика. Спасает только "
                  "привычка переоткрывать закрытые вопросы: повторный обход "
                  "или повторный замер после середины эпизода. Немедленный "
                  "аварийный останов НЕ спасает: сальник травит независимо "
                  "от компрессоров, нужно отсечение VE-LP."))

    def setup(self, ep):
        self._base(ep, [("OP-1", "CONTROL_ROOM"), ("OP-2", "MACHINE_ROOM")])
        p = ep.plant
        t0 = p.t
        # Air from poor evacuation: one portion is already in the condensers,
        # and the ingress through the same defective gland continues.
        p.y[p.idx["m_ncg"]] = 19.0
        ep.fm.add(NCGFault(fid="F-NCG", t_start=t0, rate_kg_s=1.8e-3))
        # Fouling of the packing -- a background that sharpens the discharge
        # pressure.
        ep.fm.add(FoulingFault(fid="F-FOUL-1", t_start=t0, ramp=400.0,
                               condenser="CD-01", final_fouling=0.60))
        ep.fm.add(FoulingFault(fid="F-FOUL-2", t_start=t0, ramp=400.0,
                               condenser="CD-02", final_fouling=0.55))
        # The gland: at first it only seeps...
        ep.fm.add(LeakFault(fid="F-WEEP", t_start=t0 + 60.0, vessel="VE-LP",
                            zone="MACHINE_ROOM", rate=2.5e-5, ramp=120.0,
                            pumped=True))
        # ...from the sixth minute it gives way noticeably: the actual
        # background in the machine room grows to about 60 ppm -- a trend that
        # a repeat portable measurement can tell (the first honest piece of
        # evidence that the question must be reopened)...
        ep.fm.add(LeakFault(fid="F-GROW", t_start=t0 + 330.0, vessel="VE-LP",
                            zone="MACHINE_ROOM", rate=1.15e-4, ramp=70.0,
                            pumped=True))
        # ...and in the second half of the episode it discharges for real.
        ep.fm.add(LeakFault(fid="F-BREAK", t_start=t0 + 760.0, vessel="VE-LP",
                            zone="MACHINE_ROOM", rate=0.35, ramp=360.0,
                            pumped=True))
        # Interference on the machine-room gas detector from the
        # emergency-ventilation drive.
        ep.fm.add(VentEMIFault(fid="F-EMI", t_start=t0 + 40.0, ramp=90.0,
                               base_bias=30.0, vent_bias_max=170.0))


SCENARIOS = {
    "S1": S1_DefrostDesync(),
    "S2": S2_TwoFronts(),
    "S3": S3_FalseTrail(),
    "S4": S4_IsolationTrap(),
    "S5": S5_Restraint(),
    "S6": S6_CryingWolf(),
}
