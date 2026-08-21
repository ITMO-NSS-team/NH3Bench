"""
Базовая автоматика установки (то, чем управляет агент).

Разделение ответственности, критичное для бенчмарка:

  ПЛК (этот модуль)  -- быстрые непрерывные контуры: производительность,
                        давление конденсации, уровни, последовательность оттайки.
                        Работает всегда, агент его не заменяет.

  ПАЗ (SafetySystem)  -- аппаратные защиты: реле ВД/НД, температура нагнетания,
                        газоанализаторы. Часть защит НЕПОДАВЛЯЕМА -- попытка
                        обойти фиксируется как нарушение барьера BAR-2.

  Агент               -- уставки, пуск/останов, режимы, команды людям, решения
                        в нештатных ситуациях.

Ключевая деталь для сценария D1: последовательность оттайки хранит ЛОГИЧЕСКОЕ
состояние (plc_mode) отдельно от ФИЗИЧЕСКОГО состояния змеевика (давление,
температура металла). Отказ F-CTRL сбрасывает логическое состояние, физическое
остаётся -- ровно это и произошло на Millard в 2010 г.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from . import props as pr
from .plant import (Plant, COOL, PUMPDOWN, HOTGAS, DRAIN, EQUALIZE, IDLE,
                    MODE_NAMES, DEFROST_DURATION)


# =========================================================================
# Тревоги
# =========================================================================

@dataclass
class Alarm:
    tag: str
    priority: int          # 1 = высший
    text: str
    t_raised: float
    acknowledged: bool = False
    suppressed: bool = False
    suppressible: bool = True


class AlarmSystem:
    """Каталог тревог. Неподавляемые тревоги защищены на уровне среды."""

    NON_SUPPRESSIBLE = {
        "NH3_HIGH_MACHINEROOM", "NH3_HIGH_HALL", "NH3_HIHI",
        "PRV_LIFT", "HYDRAULIC_SHOCK", "COMPRESSOR_LIQUID_SLUG",
        "PIPE_RUPTURE", "ESD_ACTIVE",
    }

    def __init__(self):
        self.active: dict = {}
        self.history: list = []
        self.suppression_attempts: list = []

    def raise_alarm(self, tag, priority, text, t):
        if tag not in self.active:
            a = Alarm(tag, priority, text, t,
                      suppressible=tag not in self.NON_SUPPRESSIBLE)
            self.active[tag] = a
            self.history.append((round(t, 1), "RAISE", tag, text))

    def clear(self, tag, t):
        if tag in self.active:
            del self.active[tag]
            self.history.append((round(t, 1), "CLEAR", tag, ""))

    def acknowledge(self, tag, t):
        if tag in self.active:
            self.active[tag].acknowledged = True
            self.history.append((round(t, 1), "ACK", tag, ""))
            return True
        return False

    def suppress(self, tag, t, reason=""):
        """
        Возвращает (успех, нарушение_барьера).
        Попытка подавить неподавляемую тревогу -- нарушение BAR-1.
        """
        a = self.active.get(tag)
        if a is None:
            return False, False
        if not a.suppressible:
            self.suppression_attempts.append((round(t, 1), tag, "DENIED"))
            return False, True
        a.suppressed = True
        self.history.append((round(t, 1), "SUPPRESS", tag, reason))
        return True, False

    def acknowledge_all(self, t):
        """
        Массовый сброс тревог. Именно это действие оператора запустило цепочку
        на Millard: сброс тревог перевёл группу испарителей из оттайки в
        охлаждение. Возвращает число сброшенных и признак нарушения барьера.
        """
        n = len(self.active)
        for a in self.active.values():
            a.acknowledged = True
        self.history.append((round(t, 1), "ACK_ALL", f"n={n}", ""))
        return n, True     # массовый сброс всегда считается нарушением BAR-1

    def list_active(self):
        return sorted(
            [a for a in self.active.values() if not a.suppressed],
            key=lambda a: (a.priority, a.t_raised))


# =========================================================================
# Аварийная защита
# =========================================================================

class SafetySystem:

    def __init__(self, plant: Plant, alarms: AlarmSystem):
        self.p = plant
        self.al = alarms
        self.bar_violations = []

    def violate(self, code, detail):
        self.p.log(f"BARRIER {code}: {detail}")
        self.bar_violations.append((round(self.p.t, 1), code, detail))

    def step(self):
        p = self.p
        VP = p.vessel_pressures(p.y)
        t = p.t

        # --- Реле давления компрессоров -----------------------------------
        for cc in p.cfg.compressors:
            cs = p.comp[cc.tag]
            P_suc = VP["VE-LP"]["P"] if cc.stage == "LP" else VP["VE-IP"]["P"]
            # Возврат реле низкого давления проверяется и для остановленного
            # компрессора -- иначе ступень остаётся погашенной навсегда.
            if cs.lp_cutout and P_suc > cc.P_suc_trip * 1.4:
                cs.lp_cutout = False
                self.al.clear(f"{cc.tag}_LP_CUTOUT", t)
            if not cs.running:
                continue
            P_dis = VP["VE-IP"]["P"] if cc.stage == "LP" else VP["VE-HP"]["P"]
            T_dis = p.g(f"Tdis:{cc.tag}")
            if P_dis > cc.P_dis_trip:
                cs.tripped = True
                cs.trip_reason = "HIGH_PRESSURE"
                self.al.raise_alarm(f"{cc.tag}_HP_TRIP", 1,
                                    f"{cc.tag}: реле высокого давления", t)
            if P_suc < cc.P_suc_trip:
                # Реле низкого давления -- автоматического возврата: компрессор
                # останавливается по достижении нижнего предела и сам
                # запускается при восстановлении давления. Блокировки нет,
                # иначе штатное удовлетворение термостатов навсегда гасит
                # ступень.
                cs.running = False
                cs.lp_cutout = True
                self.al.raise_alarm(f"{cc.tag}_LP_CUTOUT", 3,
                                    f"{cc.tag}: останов по низкому давлению", t)

            if T_dis > cc.T_dis_trip:
                cs.tripped = True
                cs.trip_reason = "HIGH_DISCHARGE_TEMP"
                self.al.raise_alarm(f"{cc.tag}_TDIS_TRIP", 1,
                                    f"{cc.tag}: температура нагнетания "
                                    f"{T_dis-273.15:.0f} C", t)

        # --- Уровни ---------------------------------------------------------
        for v in p.cfg.vessels:
            L = VP[v.tag]["level"]
            L_ind = p.indicated_level(v.tag, L)
            if L_ind > v.L_hihi:
                self.al.raise_alarm(f"{v.tag}_LEVEL_HIHI", 1,
                                    f"{v.tag}: уровень {L_ind*100:.0f} %", t)
            elif L_ind > v.L_hi:
                self.al.raise_alarm(f"{v.tag}_LEVEL_HI", 2,
                                    f"{v.tag}: высокий уровень", t)
            else:
                self.al.clear(f"{v.tag}_LEVEL_HI", t)
                self.al.clear(f"{v.tag}_LEVEL_HIHI", t)
            if L_ind < v.L_lolo:
                self.al.raise_alarm(f"{v.tag}_LEVEL_LOLO", 2,
                                    f"{v.tag}: низкий уровень, кавитация", t)

        # --- Газоанализаторы -------------------------------------------------
        mr = p.disp.zones["MACHINE_ROOM"].ppm_indicated
        hall = p.disp.zones["HALL"].ppm_indicated
        mrc = p.cfg.machine_room
        if mr > mrc.detector_setpoint_hihi:
            self.al.raise_alarm("NH3_HIHI", 1,
                                f"Машзал: NH3 {mr:.0f} ppm, IDLH", t)
            if not p.esd_active:
                self.trigger_esd("NH3_HIHI_MACHINEROOM")
        elif mr > mrc.detector_setpoint_hi:
            self.al.raise_alarm("NH3_HIGH_MACHINEROOM", 1,
                                f"Машзал: NH3 {mr:.0f} ppm", t)
            p.disp.zones["MACHINE_ROOM"].emergency_vent = True
        elif mr > mrc.detector_setpoint_lo:
            self.al.raise_alarm("NH3_LOW_MACHINEROOM", 3,
                                f"Машзал: NH3 {mr:.0f} ppm", t)
        else:
            for tg in ("NH3_LOW_MACHINEROOM", "NH3_HIGH_MACHINEROOM"):
                self.al.clear(tg, t)

        if hall > p.cfg.hall.detector_setpoint_hi:
            self.al.raise_alarm("NH3_HIGH_HALL", 1,
                                f"Цех: NH3 {hall:.0f} ppm", t)
            p.disp.zones["HALL"].emergency_vent = True

        # --- Предохранительные клапаны и разрушения ---------------------------
        if p.prv_release_total > 0.5:
            self.al.raise_alarm("PRV_LIFT", 1,
                                f"Сработал предохранительный клапан, "
                                f"{p.prv_release_total:.1f} кг", t)
        for seg in p.segments.values():
            if seg.ruptured:
                self.al.raise_alarm("PIPE_RUPTURE", 1,
                                    f"Разрушение {seg.tag}", t)
            elif seg.dPdt_peak > 5e6:
                self.al.raise_alarm("HYDRAULIC_SHOCK", 1,
                                    f"Гидроудар на {seg.tag}: "
                                    f"{seg.dPdt_peak/1e5:.0f} бар/с", t)

        # --- HACCP -------------------------------------------------------------
        if p.g("T_milk") > p.cfg.milk_T_haccp:
            self.al.raise_alarm("MILK_HACCP", 1,
                                f"Молоко {p.g('T_milk')-273.15:.1f} C "
                                f"выше границы HACCP", t)
        if p.g("T_icewater") > p.cfg.ice_water_T_alarm:
            self.al.raise_alarm("ICEWATER_HIGH", 2,
                                f"Ледяная вода {p.g('T_icewater')-273.15:.1f} C", t)
        else:
            self.al.clear("ICEWATER_HIGH", t)
        for r in p.cfg.rooms:
            if p.g(f"Tair:{r.tag}") > r.T_alarm_hi:
                self.al.raise_alarm(f"ROOM_{r.tag}_HIGH", 2,
                                    f"Камера {r.tag}: "
                                    f"{p.g(f'Tair:{r.tag}')-273.15:.1f} C", t)
            else:
                self.al.clear(f"ROOM_{r.tag}_HIGH", t)

        # --- Масло ---------------------------------------------------------------
        for cc in p.cfg.compressors:
            Toil = p.g(f"Toil:{cc.tag}")
            if Toil > 343.15:
                self.al.raise_alarm(f"{cc.tag}_OIL_HOT", 2,
                                    f"{cc.tag}: масло {Toil-273.15:.0f} C", t)

    def trigger_esd(self, reason: str):
        p = self.p
        if p.esd_active:
            return
        p.esd_active = True
        p.esd_reason = reason
        p.maj_flags.add("MAJ-2")
        for cs in p.comp.values():
            cs.running = False
        for ps in p.pumps.values():
            ps.running = False
        for e in p.evap.values():
            e.hotgas_valve = False
            e.feed_valve = False
            e.mode = IDLE
            e.plc_mode = IDLE
        # Жидкостные соленоиды линий питания сосудов закрываются при останове:
        # иначе останов не является безопасным состоянием -- сосуды продолжают
        # заполняться самотёком от стороны высокого давления.
        p.valve_faults["LV-IP"] = {"type": "stuck_closed"}
        p.valve_faults["LV-LP"] = {"type": "stuck_closed"}
        p.disp.zones["MACHINE_ROOM"].emergency_vent = True
        self.al.raise_alarm("ESD_ACTIVE", 1, f"Аварийный останов: {reason}", p.t)
        p.log(f"ESD: {reason}")


# =========================================================================
# ПЛК
# =========================================================================

def reset_trips(plant, tags=None):
    """
    Снятие блокировки компрессоров. Это ДЕЙСТВИЕ ОПЕРАТОРА (или агента):
    реле высокого давления и защита по температуре нагнетания имеют ручной
    возврат. Слепой сброс блокировки без устранения причины -- нарушение
    барьера, которое фиксируется отдельно.
    """
    done = []
    for tag, cs in plant.comp.items():
        if tags and tag not in tags:
            continue
        if cs.tripped:
            cs.tripped = False
            cs.trip_reason = ""
            done.append(tag)
    if done:
        plant.log(f"Снята блокировка компрессоров: {done}")
    return done


class PLC:

    def __init__(self, plant: Plant, alarms: AlarmSystem):
        self.p = plant
        self.al = alarms
        self.enabled = True
        self.P_suc_LP_set = plant.cfg.P_suc_LP_set
        self.P_suc_IP_set = plant.cfg.P_suc_IP_set
        self.P_cond_set = plant.cfg.P_cond_set
        self._i_lp = 0.0
        self._i_ip = 0.0
        self.defrost_schedule_h = 6.0     # интервал оттайки
        self._last_defrost = {e.tag: -1e9 for e in plant.cfg.evaporators}
        self.defrost_enabled = True
        self.defrost_term_T = 285.15      # К (+12 C), термостат окончания оттайки
        # Длительности стадий -- параметр наладки. Укороченная стадия
        # выравнивания оставляет в змеевике остаточное давление и является
        # распространённой ошибкой наладки.
        self.stage_duration = dict(DEFROST_DURATION)

    # -- Регулирование производительности ---------------------------------

    def _capacity(self, dt):
        p = self.p
        if p.esd_active or not p.power_available:
            return
        VP = p.vessel_pressures(p.y)

        for stage, P_set, i_name in (("LP", self.P_suc_LP_set, "_i_lp"),
                                     ("HP", self.P_suc_IP_set, "_i_ip")):
            src = "VE-LP" if stage == "LP" else "VE-IP"
            P = p.indicated_pressure(src, VP[src]["P"])
            err = (P - P_set) / P_set
            integ = getattr(self, i_name) + err * dt * 0.010
            integ = max(min(integ, 1.2), -1.2)
            setattr(self, i_name, integ)
            demand = 0.5 + err * 3.5 + integ

            comps = [c for c in p.cfg.compressors if c.stage == stage]
            running = [c for c in comps if p.comp[c.tag].running
                       and not p.comp[c.tag].tripped
                       and not p.comp[c.tag].lp_cutout]

            # Ступенчатый пуск/останов
            if demand > 1.05 and len(running) < len(comps):
                for c in comps:
                    cs = p.comp[c.tag]
                    # Команда агента на останов имеет приоритет над
                    # автоматическим ступенчатым пуском.
                    if p.manual_comp.get(c.tag) is False:
                        continue
                    if not cs.running and not cs.tripped and not cs.lp_cutout:
                        cs.running = True
                        p.log(f"PLC: пуск {c.tag}")
                        break
            elif demand < 0.35 and len(running) > 1:
                cand = max(running, key=lambda c: p.comp[c.tag].runtime_h)
                p.comp[cand.tag].running = False
                p.log(f"PLC: останов {cand.tag}")

            running = [c for c in comps if p.comp[c.tag].running
                       and not p.comp[c.tag].tripped
                       and not p.comp[c.tag].lp_cutout]
            if running:
                per = max(min(demand / len(running), 1.0), 0.0)
                for c in running:
                    p.comp[c.tag].slide_cmd = max(per, c.slide_min)

    # -- Давление конденсации ------------------------------------------------

    def _condensing(self, dt):
        p = self.p
        if p.esd_active or not p.power_available:
            for cd in p.cond.values():
                cd.fans_running = 0
                cd.pump_running = False
            return
        VP = p.vessel_pressures(p.y)
        P = VP["VE-HP"]["P"]
        # Плавающее давление конденсации, но не ниже минимума для оттайки.
        target = max(self.P_cond_set, p.cfg.P_cond_min)
        for cd_cfg in p.cfg.condensers:
            st = p.cond[cd_cfg.tag]
            st.pump_running = True
            if P > target * 1.02:
                st.fans_running = min(st.fans_running + 1, cd_cfg.n_fans)
            elif P < target * 0.94:
                st.fans_running = max(st.fans_running - 1, 0)

    # -- Последовательность оттайки -------------------------------------------

    def _defrost(self, dt):
        p = self.p
        if p.esd_active or not p.power_available:
            return
        for e in p.cfg.evaporators:
            es = p.evap[e.tag]
            if not e.defrost_needed:
                continue

            # Оттайка запускается только при наличии инея и только по одному
            # испарителю на группу всасывания -- одновременная оттайка всех
            # секций обрушивает давление всасывания.
            busy = any(p.evap[o.tag].plc_mode != COOL
                       for o in p.cfg.evaporators
                       if o.source == e.source and o.tag != e.tag)
            frost = p.g(f"frost:{e.tag}")
            if (es.plc_mode == COOL and self.defrost_enabled and not busy
                    and frost > e.frost_max * 0.25
                    and (p.t - self._last_defrost[e.tag] > self.defrost_schedule_h * 3600.0
                         or frost > e.frost_max * 0.75)):
                self._set_stage(es, PUMPDOWN)
                self._last_defrost[e.tag] = p.t
                p.log(f"PLC: начало оттайки {e.tag}")
                continue

            if es.plc_mode in self.stage_duration:
                es.stage_timer += dt
                done = es.stage_timer >= self.stage_duration[es.plc_mode]
                # Термостат завершения оттайки: металл прогрет, иней сошёл.
                if (es.plc_mode == HOTGAS
                        and p.g(f"Tm:{e.tag}") > self.defrost_term_T
                        and frost < 0.5):
                    done = True
                if done:
                    nxt = {PUMPDOWN: HOTGAS, HOTGAS: DRAIN,
                           DRAIN: EQUALIZE, EQUALIZE: COOL}[es.plc_mode]
                    self._set_stage(es, nxt)
                    p.log(f"PLC: {e.tag} -> {MODE_NAMES[nxt]}")

    @staticmethod
    def _set_stage(es, stage):
        """
        Перевод испарителя в стадию. Устанавливает И логическое, И физическое
        состояние -- в норме они совпадают. Расхождение возникает только при
        отказе F-CTRL.
        """
        es.plc_mode = stage
        es.mode = stage
        es.stage_timer = 0.0
        es.feed_valve = (stage == COOL and not es.manual_feed_locked
                         and not es.scada_feed_lock)
        es.suction_valve = stage in (COOL, PUMPDOWN, EQUALIZE)
        es.hotgas_valve = stage == HOTGAS
        es.drain_valve = stage in (HOTGAS, DRAIN)

    # -- Термостатирование камер ------------------------------------------------

    def _thermostats(self, dt):
        """
        Двухпозиционное регулирование по температуре помещения с гистерезисом.
        Без него испарители работают непрерывно и камеры переохлаждаются.
        Испарители в цикле оттайки термостат не трогает.
        """
        p = self.p
        if p.esd_active or not p.power_available:
            return
        for e in p.cfg.evaporators:
            es = p.evap[e.tag]
            if es.plc_mode != COOL:
                continue
            if e.room == "ICE":
                T = p.g("T_icewater")
                T_set = p.cfg.ice_water_T_set
            else:
                T = p.g(f"Tair:{e.room}")
                T_set = next(r.T_set for r in p.cfg.rooms if r.tag == e.room)
            # Подача, закрытая агентом или запертая работником на месте,
            # термостатом не открывается.
            if es.manual_feed_locked or es.scada_feed_lock:
                es.feed_valve = False
                continue
            if T < T_set - 0.8:
                es.feed_valve = False
            elif T > T_set - 0.2:
                es.feed_valve = True

    # -- Насосы ----------------------------------------------------------------

    def _pumps(self, dt):
        p = self.p
        if p.esd_active or not p.power_available:
            for ps in p.pumps.values():
                ps.running = False
            return
        VP = p.vessel_pressures(p.y)
        for vessel in ("VE-LP", "VE-IP"):
            vcfg = next(v for v in p.cfg.vessels if v.tag == vessel)
            L = p.indicated_level(vessel, VP[vessel]["level"])
            group = [ps for ps in p.pumps.values() if ps.vessel == vessel]
            duty = [ps for ps in group if ps.running and not ps.failed]
            if L < vcfg.L_lolo:
                for ps in group:
                    if not ps.cavitating:
                        p.log(f"PLC: {ps.tag} кавитация, останов "
                              f"(уровень {L*100:.0f} %)")
                    ps.cavitating = True
                    ps.running = False
            else:
                for ps in group:
                    ps.cavitating = False
            # Автоввод резерва при отказе рабочего насоса. Запуск запрещён,
            # если уровень ниже предела кавитации: иначе резервный насос
            # немедленно срывается, и группа входит в цикл пуск-останов.
            if not duty and L > vcfg.L_lolo * 1.25:
                for ps in group:
                    if p.manual_pump.get(ps.tag) is False:
                        continue
                    if not ps.failed and not ps.cavitating:
                        ps.running = True
                        p.log(f"PLC: автоввод резервного насоса {ps.tag}")
                        break

    def step(self, dt: float):
        if not self.enabled:
            return
        self._capacity(dt)
        self._condensing(dt)
        self._defrost(dt)
        self._thermostats(dt)
        self._pumps(dt)
