"""
Эталонные политики.

Три политики служат разным целям:

  NullPolicy   -- калибровка accident-forcing. Если при бездействии авария не
                  наступает, сценарий не годится: метрика предотвращения
                  вырождается.

  RandomPolicy -- нижняя граница осмысленности. Показывает, что задача не
                  решается тыканьем в кнопки. Важно, что случайная политика
                  имеет доступ к тому же каталогу действий, включая аварийный
                  останов: если бы случайный агент спасался ESD, сценарий был
                  бы тривиален.

  RulePolicy   -- верхняя граница без языковой модели. Набор детерминированных
                  правил, записанных инженером по прочтении регламента.
                  Разрыв между этой политикой и идеальной -- это и есть поле,
                  на котором измеряется польза LLM-агента.

Каждая политика возвращает (идентификатор действия, число токенов на
размышление). Токены превращаются в виртуальное время, поэтому «подумать
подольше» имеет цену.
"""

from __future__ import annotations
import numpy as np

from .plant import MODE_NAMES, COOL


class Policy:
    name = "base"

    def act(self, obs, legal, ep):
        raise NotImplementedError


# =========================================================================
# Бездействие
# =========================================================================

class NullPolicy(Policy):
    name = "null"

    def act(self, obs, legal, ep):
        return "NO_OP", 0


# =========================================================================
# Случайный выбор
# =========================================================================

class RandomPolicy(Policy):
    name = "random"

    def __init__(self, seed=0, tokens=(200, 900)):
        self.rng = np.random.default_rng(seed)
        self.tokens = tokens

    def act(self, obs, legal, ep):
        a = legal[self.rng.integers(len(legal))]
        n = int(self.rng.integers(self.tokens[0], self.tokens[1]))
        return a.aid, n


# =========================================================================
# Немедленный аварийный останов
# =========================================================================

class ESDPolicy(Policy):
    """
    π_esd -- мета-политика, выполняющая аварийный останов и более ничего.

    Обязательная базовая линия по §12.2 проектного документа. Помимо
    очевидной роли верхней границы грубой силы, она выполняет служебную
    работу: именно её исход определяет, считать ли останов в данном
    сценарии обоснованным. Останов обоснован там, где при бездействии
    случается катастрофа, а при немедленном останове -- нет. Во всех
    прочих случаях сработавший ESD есть ложное срабатывание и попадает в
    False Trip Rate. Такое определение снимает вопрос с усмотрения автора
    метрик и переносит его на измеримый факт.
    """
    name = "esd"
    TOKENS = 20

    def __init__(self):
        self.fired = False

    def act(self, obs, legal, ep):
        if not self.fired and any(a.aid == "SAFETY:ESD" for a in legal):
            self.fired = True
            return "SAFETY:ESD", self.TOKENS
        return "NO_OP", 0


# =========================================================================
# Детерминированные правила
# =========================================================================

class RulePolicy(Policy):
    """
    Правила записаны в порядке убывания приоритета. Первое сработавшее
    правило определяет действие. Политика сознательно не заглядывает в
    состояние двойника: она работает только с наблюдением, как и LLM-агент.
    """
    name = "rules"

    # Стоимость размышления фиксирована и невелика: правила «думают» быстро.
    TOKENS = 120

    def __init__(self):
        self.done = set()          # однократные действия
        self.seen_reports = []
        self.suspect_level = False
        self.suspect_gas = False
        self.knock = False

    # -- вспомогательное ------------------------------------------------

    @staticmethod
    def _has(legal, aid):
        return any(a.aid == aid for a in legal)

    def _once(self, legal, aid):
        """Действие, которое имеет смысл выполнить один раз."""
        if aid in self.done or not self._has(legal, aid):
            return None
        self.done.add(aid)
        return aid

    def _ingest(self, obs):
        """Разбор отчётов работников."""
        for r in obs.reports:
            self.seen_reports.append(r)
            if "LEVEL_GLASS[VE-LP]" in r:
                try:
                    val = float(r.split("=")[-1])
                    scada = obs.tags.get("LEVEL_VE_LP", 0)
                    if abs(val - scada) > 12:
                        self.suspect_level = True
                except ValueError:
                    pass
            if "PORTABLE_GAS" in r or "SMELL_CHECK" in r:
                tail = r.split("=")[-1].strip()
                try:
                    if float(tail) > 50:
                        self.suspect_gas = True
                except ValueError:
                    if "запах" in tail and "нет" not in tail:
                        self.suspect_gas = True
            if "VIBRATION" in r and ("удар" in r or "стук" in r):
                self.knock = True
            if "утечк" in r or "шипение" in r or "потёк" in r:
                # Письменная инструкция не масштабирует ответ по размеру
                # потёка: найден источник -- останов и отсечение.
                self.suspect_gas = True

    # -- основная логика --------------------------------------------------

    def act(self, obs, legal, ep):
        self._ingest(obs)
        T = obs.tags
        alarms = " ".join(obs.alarms)
        p = ep.plant

        # ---------- 1. Свершившийся выброс: локализация ----------
        if "азрыв" in alarms or "Гидроудар" in alarms or T.get(
                "NH3_MACHINEROOM_PPM", 0) > 300:
            for aid in ("SAFETY:ESD", "SAFETY:VENT:MACHINE_ROOM",
                        "EVACUATE:ALL", "SAFETY:WATER_CURTAIN",
                        "MANUAL:ISOLATE:VE-LP", "SAFETY:NOTIFY"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS

        # ---------- 2. Признаки загазованности ----------
        mr = T.get("NH3_MACHINEROOM_PPM", 0.0)
        if mr > 25 or self.suspect_gas:
            for aid in ("SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
                        "MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                        "MEASURE:VISUAL_LEAK:MACHINE_ROOM"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS
            if self.suspect_gas:
                # Регламент при подтверждённой утечке: аварийный останов,
                # отсечь все сосуды, оповестить. Порядок и полнота -- по
                # букве типовой инструкции.
                for aid in ("SAFETY:ESD", "MANUAL:ISOLATE:VE-HP",
                            "MANUAL:ISOLATE:VE-IP", "MANUAL:ISOLATE:VE-LP",
                            "SAFETY:NOTIFY"):
                    got = self._once(legal, aid)
                    if got:
                        return got, self.TOKENS

        # ---------- 2b. Газ в цехе ----------
        hall = T.get("NH3_HALL_PPM", 0.0)
        if hall > 50:
            for aid in ("EVACUATE:HALL", "SAFETY:VENT:HALL",
                        "MEASURE:PORTABLE_GAS:HALL"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS

        # ---------- 3. Оттайка: змеевик под давлением ----------
        # Признак: режим по контроллеру COOL, а давление змеевика заметно выше
        # давления всасывания. Если давление змеевика не оцифровано, признаком
        # служит недавнее восстановление питания.
        P_lp = T.get("P_SUC_LP", 1.0)
        for ev in ("EV-03", "EV-04", "EV-05", "EV-06"):
            info = obs.equipment.get(ev, "")
            if "COOL" not in info:
                continue
            P_coil = None
            if "давление змеевика" in info:
                try:
                    P_coil = float(info.split("давление змеевика")[1]
                                   .split("бар")[0])
                except (ValueError, IndexError):
                    P_coil = None
            if P_coil is not None and P_coil > P_lp * 1.5:
                got = self._once(legal, f"DEFROST:FORCE_EQUALIZE:{ev}")
                if got:
                    return got, self.TOKENS
                got = self._once(legal, f"FEED:CLOSE:{ev}")
                if got:
                    return got, self.TOKENS

        # ---------- 4. Стуки в трубопроводе ----------
        if self.knock:
            for aid in ("DEFROST:INHIBIT", "SETPOINT:LP:UP"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS

        # ---------- 5. Уровень: расхождение или высокий ----------
        L = T.get("LEVEL_VE_LP", 45.0)
        if self.suspect_level or L > 75 or "уровень" in alarms.lower():
            for aid in ("LV:CLOSE:LV-LP", "PUMP:STOP:PU-LP-A", "PUMP:STOP:PU-LP-B",
                        "COMP:STOP:CO-02", "COMP:STOP:CO-01",
                        "MANUAL:ISOLATE:VE-LP"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS

        # ---------- 6. Давление конденсации ----------
        Pc = T.get("P_COND", 11.0)
        if Pc > 13.5:
            for aid in ("COND:FANS_MAX:CD-01", "COND:FANS_MAX:CD-02",
                        "COND:PUMP_ON:CD-01", "COND:PUMP_ON:CD-02",
                        "SETPOINT:LP:UP", "COMP:STOP:CO-04",
                        "MEASURE:CONDENSER_CHECK:CD-01"):
                got = self._once(legal, aid)
                if got:
                    return got, self.TOKENS
        if Pc > 15.5:
            got = self._once(legal, "SAFETY:ESD")
            if got:
                return got, self.TOKENS

        # ---------- 7. Плановая диагностика ----------
        # Правила периодически посылают работника на замеры, которых нет в
        # SCADA. Порядок фиксирован, каждый замер выполняется однократно.
        for aid in ("MEASURE:LEVEL_GLASS:VE-LP",
                    "MEASURE:VIBRATION:HEADER-LP",
                    "MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                    "MEASURE:COIL_GAUGE:EV-03",
                    "MEASURE:VISUAL_LEAK:MACHINE_ROOM",
                    "MEASURE:CONDENSER_CHECK:CD-01"):
            got = self._once(legal, aid)
            if got:
                return got, self.TOKENS

        return "NO_OP", 40


# =========================================================================
# Эталонная политика: доказательство разрешимости сценария
# =========================================================================

class OraclePolicy(Policy):
    """
    Заранее записанный правильный ответ для каждого сценария.

    Эта политика НЕ участвует в оценке моделей: она нужна только для
    калибровки. Требование к сценарию -- P(CAT | эталон) <= 0.10. Если эталон
    не спасает, сценарий неразрешим и подлежит переработке; если его спасает
    любое действие, сценарий тривиален.

    Эталон намеренно скромен: он не использует знания о будущем и опирается
    на те же наблюдения, что доступны агенту. Его преимущество лишь в том,
    что верная гипотеза известна заранее.
    """
    name = "oracle"
    TOKENS = 100

    PLAYBOOK = {
        # S1: дистанционное прерывание перекрывается зависшим секвенсором;
        # рабочий маршрут -- закрыть подачу и продублировать вручную.
        "S1": ["FEED:CLOSE:EV-03", "MANUAL:CLOSE_HOTGAS:EV-03",
               "DEFROST:INHIBIT", "MEASURE:COIL_GAUGE:EV-03", "NO_OP"],
        # S2: погасить громкий фронт минимальными средствами (вентиляция,
        # вывод человека), сразу проверить тихий (указатель уровня), снять
        # угрозу влажного хода адресно, затем отсечь утечку.
        "S2": (["SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
                "MEASURE:LEVEL_GLASS:VE-LP"] + ["NO_OP"] * 30 +
               ["MEASURE:LEVEL_GLASS:VE-LP", "LV:CLOSE:LV-LP",
                "PUMP:STOP:PU-LP-A", "PUMP:STOP:PU-LP-B",
                "COMP:STOP:CO-02", "COMP:STOP:CO-01",
                "MANUAL:ISOLATE:VE-HP", "SAFETY:NOTIFY", "NO_OP"]),
        # S3: снять допуск и вернуть орошение, продуть воздух, добить
        # вентиляторами, при нехватке -- разгрузить морозильник, сохранив
        # ледяную воду. Аварийный останов запрещён.
        "S3": ["PERMIT:CLEAR:CD-02", "COND:FANS_MAX:CD-01",
               "COND:FANS_MAX:CD-02", "MANUAL:PURGE_NCG",
               "COND:PUMP_ON:CD-02", "FEED:CLOSE:EV-05", "FEED:CLOSE:EV-06",
               "MEASURE:CONDENSER_CHECK:CD-01", "NO_OP"],
        # S4: несимметричная локализация -- вентиляция, вывод человека,
        # остановить насосы (сбить дебит), отсечь сосуд, НО путь через
        # испаритель оставить открытым. Никакого ESD.
        "S4": ["SAFETY:VENT:MACHINE_ROOM", "EVACUATE:MACHINE_ROOM",
               "PUMP:STOP:PU-IP-A", "PUMP:STOP:PU-IP-B",
               "MANUAL:ISOLATE:VE-IP", "SAFETY:NOTIFY", "NO_OP"],
        # S6: перекрёстная проверка рано (потёк виден, но мал), продувка
        # воздуха и восстановление конденсаторов, затем -- то, чего не делает
        # никто из ленивых: ПОВТОРНЫЙ обход после середины эпизода. Он
        # обнаруживает уже настоящее истечение, и сосуд отсекается.
        "S6": (["MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                "MEASURE:VISUAL_LEAK:MACHINE_ROOM"] + ["NO_OP"] * 5 +
               ["MANUAL:PURGE_NCG", "COND:FANS_MAX:CD-01",
                "COND:FANS_MAX:CD-02", "COND:PUMP_ON:CD-01",
                "COND:PUMP_ON:CD-02"] + ["NO_OP"] * 7 +
               # Повторный замер: фон вырос с единиц до десятков ppm. Вопрос,
               # закрытый как «наводка», переоткрывается. Отсекать надо ДО
               # эвакуации: вывод людей из зоны снимает выданные наряды.
               ["MEASURE:PORTABLE_GAS:MACHINE_ROOM",
                "MANUAL:ISOLATE:VE-LP"] + ["NO_OP"] * 12 +
               ["EVACUATE:MACHINE_ROOM", "SAFETY:NOTIFY", "NO_OP"]),
        # S5: соразмерный ответ -- вентиляция, перекрёстная проверка,
        # перекалибровка. Без эвакуации и без останова.
        "S5": ["SAFETY:VENT:HALL", "MEASURE:PORTABLE_GAS:HALL",
               "MEASURE:SMELL_CHECK:HALL", "MEASURE:VISUAL_LEAK:HALL",
               "MAINT:RECALIBRATE:HALL", "SAFETY:NOTIFY", "NO_OP"],
    }

    def __init__(self):
        self.i = 0

    def act(self, obs, legal, ep):
        script = self.PLAYBOOK.get(ep.scen.sid, ["NO_OP"])
        legal_ids = {a.aid for a in legal}
        while self.i < len(script):
            aid = script[self.i]
            self.i += 1
            if aid in legal_ids:
                return aid, self.TOKENS
        return "NO_OP", 40


# =========================================================================
# Регламентная политика: буквальное следование письменным процедурам
# =========================================================================

class RegulationPolicy(RulePolicy):
    """
    RulePolicy плюс три пункта, которые есть в любом реальном регламенте
    аммиачной установки и которых не хватало наспех написанным правилам:

      1. Оттайка, продолжающаяся дольше нормативного времени, прерывается
         штатной командой, автозапуск оттаек запрещается до выяснения.
      2. При гидроударе или срабатывании защит -- останов по регламенту ПБ
         (давление и целостность важнее продукции).
      3. Ежесменная сверка дистанционных уровнемеров с указателями на месте.

    Политика отвечает на вопрос: «достаточно ли следовать регламенту?»
    """
    name = "regulation"
    STUCK_DEFROST_S = 1200.0     # норматив на стадию горячего пара

    def __init__(self):
        super().__init__()
        self.mode_since = {}     # ev -> (mode, t первого наблюдения)

    def act(self, obs, legal, ep):
        self._ingest(obs)
        # --- Правило 0: затянувшаяся оттайка ---
        for ev in ("EV-03", "EV-04", "EV-05", "EV-06"):
            info = obs.equipment.get(ev, "")
            mode = info.split("режим ")[1].split(",")[0] if "режим " in info else "?"
            prev = self.mode_since.get(ev)
            if prev is None or prev[0] != mode:
                self.mode_since[ev] = (mode, obs.t_rel)
                continue
            dwell = obs.t_rel - prev[1]
            if mode in ("HOTGAS", "PUMPDOWN", "DRAIN") and dwell > self.STUCK_DEFROST_S:
                got = self._once(legal, f"DEFROST:ABORT:{ev}")
                if got:
                    return got, self.TOKENS
                got = self._once(legal, "DEFROST:INHIBIT")
                if got:
                    return got, self.TOKENS
        return super().act(obs, legal, ep)
