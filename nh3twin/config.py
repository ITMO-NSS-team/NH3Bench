"""
Конфигурация референсной аммиачной холодильной установки молокозавода.

Типоразмеры подобраны под завод 250 т молока/сут:
  - охлаждение молока после пастеризации через ледяную воду (HACCP-критично)
  - камера хранения готовой продукции +2 C
  - низкотемпературный склад -20 C
  - скороморозильный аппарат -30 C

Двухступенчатая насосно-циркуляционная схема, R717, заправка ~3200 кг.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


# =========================================================================
# Компрессоры
# =========================================================================

@dataclass
class CompressorCfg:
    tag: str
    stage: Literal["LP", "HP"]          # бустер / верхняя ступень
    V_disp: float                        # м3/об (объём, описываемый за оборот)
    n_nom: float = 2950.0                # об/мин
    n_min: float = 1480.0
    n_max: float = 3550.0
    slide_min: float = 0.25              # мин. положение золотника
    slide_rate: float = 0.06             # 1/с, скорость перемещения золотника
    eta_v_coef: tuple = (0.960, -0.0165, -0.00090)   # a0 + a1*PI + a2*PI^2
    eta_is_coef: tuple = (0.520, 0.1150, -0.01250)   # b0 + b1*PI + b2*PI^2
    oil_charge: float = 180.0            # кг масла в маслоотделителе
    oil_T_nom: float = 318.15            # К, номинальная температура масла
    C_oil: float = 1900.0                # Дж/(кг*К)
    oil_ratio: float = 4.5               # кратность впрыска масла (кг масла / кг NH3)
    UA_oil_cooler: float = 9000.0        # Вт/К, маслоохладитель
    T_dis_trip: float = 373.15           # К (100 C), защита по температуре нагнетания
    P_dis_trip: float = 16.5e5           # Па, реле высокого давления
    P_suc_trip: float = 0.45e5           # Па, реле низкого давления
    liquid_slug_limit: float = 0.15      # массовая доля жидкости на всасе
    liquid_slug_time: float = 10.0       # с до разрушения


# =========================================================================
# Сосуды
# =========================================================================

@dataclass
class VesselCfg:
    tag: str
    V: float                             # м3, полный геометрический объём
    L_nom: float = 0.45                  # номинальный уровень (доля объёма)
    L_hi: float = 0.75                   # тревога высокого уровня
    L_hihi: float = 0.90                 # унос жидкости на всас
    L_lo: float = 0.20
    L_lolo: float = 0.08                 # кавитация насосов
    P_design: float = 19.0e5             # Па, расчётное давление
    P_prv: float = 17.5e5                # Па, уставка предохранительного клапана
    prv_capacity: float = 2.2            # кг/с при полном открытии
    UA_amb: float = 45.0                 # Вт/К, теплоприток через изоляцию


# =========================================================================
# Испарители (воздухоохладители)
# =========================================================================

@dataclass
class EvaporatorCfg:
    tag: str
    room: str
    source: str                          # тег питающего сосуда
    Q_nom: float                         # Вт, номинальная холодопроизводительность
    UA_dry: float                        # Вт/К, коэффициент при чистом теплообменнике
    V_coil: float                        # м3, внутренний объём змеевика
    m_metal: float                       # кг, масса металла
    c_metal: float = 480.0               # Дж/(кг*К), сталь
    n_circ: float = 3.0                  # кратность циркуляции (насосная схема)
    frost_UA_k: float = 0.55             # доля падения UA при предельном инее
    frost_max: float = 45.0              # кг, предельная масса инея
    frost_rate_k: float = 2.2e-8         # кг/(с*Вт), интенсивность образования инея
    defrost_hotgas: float = 0.28         # кг/с, расход горячего пара на оттайку
    defrost_needed: bool = True          # нужна ли оттайка (для НТ-камер)
    # Гидравлика для расчёта гидроудара
    pipe_D: float = 0.150                # м, диаметр коллектора всасывания
    pipe_L: float = 42.0                 # м, длина участка до общего коллектора
    pipe_wall: float = 0.0055            # м, толщина стенки
    pipe_sigma_y: float = 235e6          # Па, предел текучести стали 09Г2С
    Cv_feed: float = 0.0                 # заполняется автоматически из Q_nom


# =========================================================================
# Помещения и тепловая нагрузка
# =========================================================================

@dataclass
class RoomCfg:
    tag: str
    V: float                             # м3
    T_set: float                         # К, уставка
    T_alarm_hi: float                    # К, граница HACCP
    UA_env: float                        # Вт/К, ограждающие конструкции
    C_air: float                         # Дж/К, теплоёмкость воздуха
    C_product: float                     # Дж/К, теплоёмкость продукта
    UA_product: float                    # Вт/К, воздух <-> продукт
    Q_internal: float = 0.0              # Вт, освещение, вентиляторы, люди
    door_load: float = 0.0               # Вт при открытых воротах
    product_mass: float = 0.0            # кг


# =========================================================================
# Конденсаторы
# =========================================================================

@dataclass
class CondenserCfg:
    tag: str
    UA_nom: float                        # Вт/К относительно температуры мокрого термометра
    n_fans: int = 2
    fan_power: float = 7500.0            # Вт на вентилятор
    pump_power: float = 2200.0           # Вт, циркуляционный насос орошения
    V: float = 1.8                       # м3, внутренний объём


# =========================================================================
# Машинный зал и рассеивание
# =========================================================================

@dataclass
class MachineRoomCfg:
    V: float = 1450.0                    # м3
    vent_normal: float = 2.4             # м3/с, штатная вентиляция
    vent_emergency: float = 14.0         # м3/с, аварийная вентиляция
    detector_setpoint_lo: float = 25.0   # ppm, предупредительная
    detector_setpoint_hi: float = 100.0  # ppm, аварийная
    detector_setpoint_hihi: float = 300.0  # ppm, IDLH, аварийный останов
    detector_lag: float = 12.0           # с, постоянная времени газоанализатора


@dataclass
class ProductionHallCfg:
    V: float = 9800.0
    vent_normal: float = 6.0
    vent_emergency: float = 22.0
    detector_setpoint_hi: float = 50.0


@dataclass
class SiteCfg:
    """Площадка: для оценки заграничной концентрации по факельной модели."""
    fence_distance: float = 160.0        # м до границы площадки
    release_height: float = 9.0          # м, высота кровли машзала
    stability_class: str = "D"           # класс устойчивости атмосферы Пасквилла


# =========================================================================
# Сборка
# =========================================================================

@dataclass
class PlantConfig:
    name: str = "dairy_250t_v1"
    charge_total: float = 4170.0         # кг аммиака в системе (проверено аудитом)

    compressors: list = field(default_factory=lambda: [
        CompressorCfg("CO-01", "LP", V_disp=0.00600),
        CompressorCfg("CO-02", "LP", V_disp=0.00600),
        CompressorCfg("CO-03", "HP", V_disp=0.00420),
        CompressorCfg("CO-04", "HP", V_disp=0.00420),
    ])

    vessels: list = field(default_factory=lambda: [
        VesselCfg("VE-LP", V=3.0,  P_design=19.0e5, P_prv=17.5e5),   # -40 C
        VesselCfg("VE-IP", V=3.5,  P_design=19.0e5, P_prv=17.5e5),   # -10 C
        VesselCfg("VE-HP", V=5.0, P_design=25.0e5, P_prv=19.0e5),   # линейный ресивер
    ])

    condensers: list = field(default_factory=lambda: [
        CondenserCfg("CD-01", UA_nom=62000.0),
        CondenserCfg("CD-02", UA_nom=62000.0),
    ])

    evaporators: list = field(default_factory=lambda: [
        # Ледяная вода: питается от VE-IP, оттайка не нужна (плюсовая температура)
        EvaporatorCfg("EV-01", room="ICE",   source="VE-IP", Q_nom=620e3,
                      UA_dry=88000.0, V_coil=1.10, m_metal=2400.0,
                      defrost_needed=False, pipe_D=0.200, pipe_L=28.0),
        # Камера готовой продукции +2 C
        EvaporatorCfg("EV-02", room="CHILL", source="VE-IP", Q_nom=145e3,
                      UA_dry=19500.0, V_coil=0.36, m_metal=760.0,
                      defrost_needed=False, pipe_D=0.125, pipe_L=35.0),
        # НТ-склад -20 C, две секции
        EvaporatorCfg("EV-03", room="LT", source="VE-LP", Q_nom=98e3,
                      UA_dry=11800.0, V_coil=0.30, m_metal=680.0),
        EvaporatorCfg("EV-04", room="LT", source="VE-LP", Q_nom=98e3,
                      UA_dry=11800.0, V_coil=0.30, m_metal=680.0),
        # Скороморозильный аппарат -30 C, две секции
        EvaporatorCfg("EV-05", room="BLAST", source="VE-LP", Q_nom=155e3,
                      UA_dry=14200.0, V_coil=0.34, m_metal=820.0),
        EvaporatorCfg("EV-06", room="BLAST", source="VE-LP", Q_nom=155e3,
                      UA_dry=14200.0, V_coil=0.34, m_metal=820.0),
    ])

    rooms: list = field(default_factory=lambda: [
        RoomCfg("CHILL", V=4200.0, T_set=275.15, T_alarm_hi=279.15,
                UA_env=1250.0, C_air=5.6e6, C_product=1.15e9,
                UA_product=42000.0, Q_internal=18000.0, door_load=52000.0,
                product_mass=310000.0),
        RoomCfg("LT", V=5600.0, T_set=253.15, T_alarm_hi=258.15,
                UA_env=980.0, C_air=7.5e6, C_product=9.2e8,
                UA_product=26000.0, Q_internal=14000.0, door_load=61000.0,
                product_mass=240000.0),
        RoomCfg("BLAST", V=900.0, T_set=243.15, T_alarm_hi=249.15,
                UA_env=420.0, C_air=1.2e6, C_product=8.0e7,
                UA_product=31000.0, Q_internal=22000.0, door_load=18000.0,
                product_mass=12000.0),
    ])

    machine_room: MachineRoomCfg = field(default_factory=MachineRoomCfg)
    hall: ProductionHallCfg = field(default_factory=ProductionHallCfg)
    site: SiteCfg = field(default_factory=SiteCfg)

    # --- Контур ледяной воды ---------------------------------------------
    ice_bank_mass_nom: float = 62000.0   # кг воды в аккумуляторе льда
    ice_max: float = 34000.0             # кг намораживаемого льда
    ice_water_T_set: float = 274.65      # К (+1.5 C), уставка ледяной воды
    ice_water_T_alarm: float = 277.15    # К (+4 C), выше -- срыв охлаждения молока

    # --- Молоко ------------------------------------------------------------
    milk_tank_mass: float = 45000.0      # кг в танке промежуточного хранения
    milk_T_set: float = 277.15           # К (+4 C)
    milk_T_haccp: float = 279.15         # К (+6 C), граница HACCP
    milk_c: float = 3930.0               # Дж/(кг*К)
    milk_inlet_T: float = 348.15         # К (+75 C) после пастеризации
    milk_flow_peak: float = 4.2          # кг/с в пике приёмки

    # --- Уставки автоматики ------------------------------------------------
    P_suc_LP_set: float = 0.72e5         # Па, соответствует -40 C
    P_suc_IP_set: float = 2.91e5         # Па, соответствует -10 C
    P_cond_set: float = 11.5e5           # Па, плавающее давление конденсации
    P_cond_min: float = 8.0e5            # Па, минимум для работы ТРВ и оттайки
    oil_dP_min: float = 1.5e5            # Па, минимальный перепад на масляном насосе
    Cv_LV_IP: float = 6.0e-5             # пропускная способность клапана HP->IP
    Cv_LV_LP: float = 4.5e-5             # пропускная способность клапана IP->LP

    # --- Насосы аммиака ------------------------------------------------------
    pump_flow_LP: float = 3.6            # кг/с на насос
    pump_flow_IP: float = 9.5            # кг/с на насос
    pump_power: float = 5500.0           # Вт
    pump_head: float = 3.0e5             # Па, напор аммиачного насоса

    # --- Трубопроводы --------------------------------------------------------
    suction_header_D: float = 0.300      # м, общий коллектор всасывания НД
    suction_header_L: float = 68.0       # м
    suction_header_wall: float = 0.0071  # м
    suction_header_sigma_y: float = 235e6

    def by_tag(self, tag: str):
        for group in (self.compressors, self.vessels, self.condensers,
                      self.evaporators, self.rooms):
            for item in group:
                if item.tag == tag:
                    return item
        raise KeyError(tag)


DEFAULT = PlantConfig()
