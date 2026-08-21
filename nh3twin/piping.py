"""
Гидроудар и целостность трубопровода.

Механизм, который моделируется, -- НЕ классический гидроудар от закрытия
задвижки, а конденсационный удар (condensation-induced water hammer), именно он
разрушил трубопровод на Millard Refrigerated Services в 2010 г.

Цепочка:
  1. Змеевик испарителя находится в оттайке: заполнен горячим паром 8...11 бар,
     металл прогрет до +20...+30 C.
  2. Открывается клапан подачи жидкости, в змеевик поступает аммиак -40 C.
  3. Холодная жидкость вызывает лавинную конденсацию пара.
  4. Паровой объём схлопывается, образуется зона пониженного давления.
  5. Столб жидкости разгоняется, заполняя пустоту, и тормозится о тупик/отвод.
  6. Скачок давления по Жуковскому: dP = rho * a * dv.

Волновые процессы имеют характерное время миллисекунды, поэтому они НЕ
интегрируются вместе с медленной тепловой динамикой (dt = 0.25...0.5 с), а
рассчитываются алгебраически как событие внутри шага. Это осознанное разделение
на два временных масштаба -- см. раздел "Численная схема" в README.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from . import props as pr


# Скорость волны в стальной трубе с жидким аммиаком.
# a = sqrt(K/rho) / sqrt(1 + (K*D)/(E*e)), K ~ 1.03 ГПа, E = 2.1e11 Па.
def wave_speed(D: float, wall: float, rho: float,
               K: float = 1.03e9, E: float = 2.1e11) -> float:
    return (K / rho) ** 0.5 / (1.0 + (K * D) / (E * wall)) ** 0.5


def hoop_stress(P: float, D: float, wall: float) -> float:
    """Кольцевое напряжение по формуле Барлоу (тонкостенная труба)."""
    return P * D / (2.0 * wall)


@dataclass
class PipeSegment:
    tag: str
    D: float
    L: float
    wall: float
    sigma_y: float = 235e6
    burst_factor: float = 2.4      # sigma_burst / sigma_y для 09Г2С
    dynamic_derate: float = 0.45   # понижение прочности при ударном нагружении
    wall_loss: float = 0.0         # доля утонения от коррозии (задаётся отказом)
    fatigue: float = 0.0           # накопленное повреждение, 1.0 = разрушение
    cycles: int = 0                # число зарегистрированных циклов нагружения
    last_cycle_t: float = -1e9
    ruptured: bool = False
    P_peak: float = 0.0            # Па, максимум за прогон
    dPdt_peak: float = 0.0         # Па/с, максимум за прогон

    @property
    def wall_eff(self) -> float:
        return max(self.wall * (1.0 - self.wall_loss), 1e-4)

    @property
    def P_burst(self) -> float:
        """Статическое давление разрушения (квазистатическое нагружение)."""
        return 2.0 * self.sigma_y * self.burst_factor * self.wall_eff / self.D

    @property
    def P_burst_dynamic(self) -> float:
        """
        Давление разрушения при ударном нагружении.

        Понижающий коэффициент учитывает концентрацию напряжений на опорах и
        сварных швах и динамическое усиление отклика. Значение 0.45 подобрано
        так, чтобы модель воспроизводила известные случаи разрушения
        трубопроводов холодильных установок от конденсационного удара, и
        подлежит экспертной приёмке (см. раздел валидации).
        """
        return self.P_burst * self.dynamic_derate

    @property
    def area(self) -> float:
        return 3.141592653589793 * self.D ** 2 / 4.0


def joukowsky_spike(seg: PipeSegment, rho_liq: float, dv: float) -> float:
    """Скачок давления по Жуковскому при изменении скорости жидкости на dv."""
    a = wave_speed(seg.D, seg.wall_eff, rho_liq)
    return rho_liq * a * abs(dv)


# Условия возникновения конденсационного удара.
SHOCK_PRESSURE_RATIO = 1.5      # P_змеевика / P_всасывания
SHOCK_METAL_SUPERHEAT = 20.0    # К, перегрев металла над температурой всасывания
SHOCK_MIN_SUBCOOL = 15.0        # К, недогрев поступающей жидкости


def condensation_shock(seg: PipeSegment,
                       P_coil: float, P_feed: float,
                       T_metal: float, m_liq_in_rate: float,
                       dt: float,
                       header: "PipeSegment" = None,
                       t_now: float = 0.0) -> dict:
    """
    Конденсационный удар при поступлении холодной жидкости в горячий змеевик.

    Механизм (Wylie & Streeter; IIAR Bulletin 116):
    холодная жидкость, попадая в объём горячего пара, вызывает лавинную
    конденсацию. Паровая полость схлопывается, и столб жидкости разгоняется
    под действием ПОЛНОГО перепада давления между змеевиком и линией
    всасывания. Скорость столба ограничена соотношением Бернулли
    v = sqrt(2*dP/rho), а последующее торможение о тупик или отвод даёт скачок
    по Жуковскому dP = rho*a*v.

    Существенно, что движущей силой является перепад давления, а НЕ тепловой
    баланс потока жидкости: последний даёт скорости порядка 0.5 м/с и удары в
    единицы бар, что противоречит натурным данным (100...700 бар).

    Аргумент header, если задан, позволяет оценить удар и в общем коллекторе
    всасывания: скорость там масштабируется обратно площади сечения.
    """
    null = {"P_peak": P_coil, "dPdt": 0.0, "dv": 0.0, "rupture": False,
            "segment": None}

    if m_liq_in_rate <= 1e-6:
        return null
    if P_coil <= P_feed * SHOCK_PRESSURE_RATIO:
        return null

    T_feed = pr.Tsat(P_feed)
    if (T_metal - T_feed) < SHOCK_METAL_SUPERHEAT:
        return null
    if (pr.Tsat(P_coil) - T_feed) < SHOCK_MIN_SUBCOOL:
        return null

    rho = pr.rho_l(P_feed)
    dP_drive = P_coil - P_feed
    v = (2.0 * dP_drive / rho) ** 0.5

    # Доля сечения, занятая разогнанным столбом. Пробковый режим не заполняет
    # трубу целиком; коэффициент откалиброван по натурным данным о разрушениях.
    slug_factor = 0.85

    worst = None
    for s in ([seg] if header is None else [seg, header]):
        v_s = v * slug_factor
        if s is not header and header is not None:
            pass
        elif s is header:
            v_s = v * slug_factor * (seg.area / s.area)
        dP_j = joukowsky_spike(s, rho, v_s)
        P_peak = P_coil + dP_j
        a = wave_speed(s.D, s.wall_eff, rho)
        dPdt = dP_j / max(s.L / a, 1e-4)
        s.P_peak = max(s.P_peak, P_peak)
        s.dPdt_peak = max(s.dPdt_peak, dPdt)
        margin = P_peak / s.P_burst_dynamic
        if worst is None or margin > worst[0]:
            worst = (margin, s, P_peak, dPdt, v_s)

    margin, s, P_peak, dPdt, v_s = worst
    rupture = False
    if margin >= 1.0:
        rupture = True
        s.ruptured = True
    elif margin > 0.55:
        # Малоцикловая усталость копится ПО СОБЫТИЯМ, а не по шагам
        # интегрирования: один переходный процесс -- один цикл нагружения.
        if t_now - s.last_cycle_t > 10.0:
            s.fatigue += margin ** 6
            s.last_cycle_t = t_now
            s.cycles += 1
        if s.fatigue >= 1.0:
            rupture = True
            s.ruptured = True

    return {"P_peak": P_peak, "dPdt": dPdt, "dv": v_s,
            "rupture": rupture, "segment": s}


def make_segments(cfg) -> dict:
    """Сегменты трубопровода из конфигурации установки."""
    segs = {}
    for ev in cfg.evaporators:
        segs[ev.tag] = PipeSegment(
            tag=f"PIPE-{ev.tag}", D=ev.pipe_D, L=ev.pipe_L,
            wall=ev.pipe_wall, sigma_y=ev.pipe_sigma_y)
    segs["HEADER-LP"] = PipeSegment(
        tag="PIPE-HEADER-LP", D=cfg.suction_header_D, L=cfg.suction_header_L,
        wall=cfg.suction_header_wall, sigma_y=cfg.suction_header_sigma_y)
    return segs
