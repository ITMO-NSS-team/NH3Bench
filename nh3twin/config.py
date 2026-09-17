"""
Configuration of the reference ammonia refrigeration plant of a dairy.

The sizes are chosen for a plant of 250 t of milk per day:
  - cooling milk after pasteurization through ice water (HACCP-critical)
  - finished-product store at +2 C
  - low-temperature store at -20 C
  - blast freezer at -30 C

Two-stage pumped-circulation layout, R717, charge about 3200 kg.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


# =========================================================================
# Compressors
# =========================================================================

@dataclass
class CompressorCfg:
    tag: str
    stage: Literal["LP", "HP"]          # booster / high stage
    V_disp: float                        # m3/rev (swept volume per revolution)
    n_nom: float = 2950.0                # rpm
    n_min: float = 1480.0
    n_max: float = 3550.0
    slide_min: float = 0.25              # minimum slide-valve position
    slide_rate: float = 0.06             # 1/s, slide-valve travel rate
    eta_v_coef: tuple = (0.960, -0.0165, -0.00090)   # a0 + a1*PI + a2*PI^2
    eta_is_coef: tuple = (0.520, 0.1150, -0.01250)   # b0 + b1*PI + b2*PI^2
    oil_charge: float = 180.0            # kg of oil in the separator
    oil_T_nom: float = 318.15            # K, nominal oil temperature
    C_oil: float = 1900.0                # J/(kg*K)
    oil_ratio: float = 4.5               # oil injection ratio (kg of oil per kg of NH3)
    UA_oil_cooler: float = 9000.0        # W/K, oil cooler
    T_dis_trip: float = 373.15           # K (100 C), discharge temperature protection
    P_dis_trip: float = 16.5e5           # Pa, high-pressure cutout
    P_suc_trip: float = 0.45e5           # Pa, low-pressure cutout
    liquid_slug_limit: float = 0.15      # liquid mass fraction at the suction
    liquid_slug_time: float = 10.0       # s to destruction


# =========================================================================
# Vessels
# =========================================================================

@dataclass
class VesselCfg:
    tag: str
    V: float                             # m3, total geometric volume
    L_nom: float = 0.45                  # nominal level (fraction of volume)
    L_hi: float = 0.75                   # high-level alarm
    L_hihi: float = 0.90                 # liquid carry-over to the suction
    L_lo: float = 0.20
    L_lolo: float = 0.08                 # pump cavitation
    P_design: float = 19.0e5             # Pa, design pressure
    P_prv: float = 17.5e5                # Pa, relief valve setting
    prv_capacity: float = 2.2            # kg/s at full opening
    UA_amb: float = 45.0                 # W/K, heat ingress through insulation


# =========================================================================
# Evaporators (air coolers)
# =========================================================================

@dataclass
class EvaporatorCfg:
    tag: str
    room: str
    source: str                          # tag of the feeding vessel
    Q_nom: float                         # W, nominal cooling capacity
    UA_dry: float                        # W/K, coefficient for a clean heat exchanger
    V_coil: float                        # m3, internal coil volume
    m_metal: float                       # kg, mass of metal
    c_metal: float = 480.0               # J/(kg*K), steel
    n_circ: float = 3.0                  # circulation ratio (pumped layout)
    frost_UA_k: float = 0.55             # fraction of UA lost at maximum frost
    frost_max: float = 45.0              # kg, maximum frost mass
    frost_rate_k: float = 2.2e-8         # kg/(s*W), frost formation rate
    defrost_hotgas: float = 0.28         # kg/s of hot gas for defrost
    defrost_needed: bool = True          # whether defrost is needed (for the LT rooms)
    # Hydraulics for the hydraulic-shock computation
    pipe_D: float = 0.150                # m, suction header diameter
    pipe_L: float = 42.0                 # m, length of the run to the common header
    pipe_wall: float = 0.0055            # m, wall thickness
    pipe_sigma_y: float = 235e6          # Pa, yield strength of 09G2S steel
    Cv_feed: float = 0.0                 # filled in automatically from Q_nom


# =========================================================================
# Rooms and thermal load
# =========================================================================

@dataclass
class RoomCfg:
    tag: str
    V: float                             # m3
    T_set: float                         # K, setpoint
    T_alarm_hi: float                    # K, HACCP limit
    UA_env: float                        # W/K, building envelope
    C_air: float                         # J/K, heat capacity of the air
    C_product: float                     # J/K, heat capacity of the product
    UA_product: float                    # W/K, air <-> product
    Q_internal: float = 0.0              # W, lighting, fans, people
    door_load: float = 0.0               # W with the doors open
    product_mass: float = 0.0            # kg


# =========================================================================
# Condensers
# =========================================================================

@dataclass
class CondenserCfg:
    tag: str
    UA_nom: float                        # W/K against the wet-bulb temperature
    n_fans: int = 2
    fan_power: float = 7500.0            # W per fan
    pump_power: float = 2200.0           # W, spray circulation pump
    V: float = 1.8                       # m3, internal volume


# =========================================================================
# Machine room and dispersion
# =========================================================================

@dataclass
class MachineRoomCfg:
    V: float = 1450.0                    # m3
    vent_normal: float = 2.4             # m3/s, normal ventilation
    vent_emergency: float = 14.0         # m3/s, emergency ventilation
    detector_setpoint_lo: float = 25.0   # ppm, warning
    detector_setpoint_hi: float = 100.0  # ppm, alarm
    detector_setpoint_hihi: float = 300.0  # ppm, IDLH, emergency shutdown
    detector_lag: float = 12.0           # s, gas detector time constant


@dataclass
class ProductionHallCfg:
    V: float = 9800.0
    vent_normal: float = 6.0
    vent_emergency: float = 22.0
    detector_setpoint_hi: float = 50.0


@dataclass
class SiteCfg:
    """
    The site: for estimating the fenceline concentration with the plume model.
    """
    fence_distance: float = 160.0        # m to the site boundary
    release_height: float = 9.0          # m, machine room roof height
    stability_class: str = "D"           # Pasquill atmospheric stability class


# =========================================================================
# Assembly
# =========================================================================

@dataclass
class PlantConfig:
    name: str = "dairy_250t_v1"
    charge_total: float = 4170.0         # kg of ammonia in the system (checked by audit)

    compressors: list = field(default_factory=lambda: [
        CompressorCfg("CO-01", "LP", V_disp=0.00600),
        CompressorCfg("CO-02", "LP", V_disp=0.00600),
        CompressorCfg("CO-03", "HP", V_disp=0.00420),
        CompressorCfg("CO-04", "HP", V_disp=0.00420),
    ])

    vessels: list = field(default_factory=lambda: [
        VesselCfg("VE-LP", V=3.0,  P_design=19.0e5, P_prv=17.5e5),   # -40 C
        VesselCfg("VE-IP", V=3.5,  P_design=19.0e5, P_prv=17.5e5),   # -10 C
        VesselCfg("VE-HP", V=5.0, P_design=25.0e5, P_prv=19.0e5),   # liquid receiver
    ])

    condensers: list = field(default_factory=lambda: [
        CondenserCfg("CD-01", UA_nom=62000.0),
        CondenserCfg("CD-02", UA_nom=62000.0),
    ])

    evaporators: list = field(default_factory=lambda: [
        # Ice water: fed from VE-IP, no defrost needed (above-zero temperature)
        EvaporatorCfg("EV-01", room="ICE",   source="VE-IP", Q_nom=620e3,
                      UA_dry=88000.0, V_coil=1.10, m_metal=2400.0,
                      defrost_needed=False, pipe_D=0.200, pipe_L=28.0),
        # Finished-product store at +2 C
        EvaporatorCfg("EV-02", room="CHILL", source="VE-IP", Q_nom=145e3,
                      UA_dry=19500.0, V_coil=0.36, m_metal=760.0,
                      defrost_needed=False, pipe_D=0.125, pipe_L=35.0),
        # LT store at -20 C, two sections
        EvaporatorCfg("EV-03", room="LT", source="VE-LP", Q_nom=98e3,
                      UA_dry=11800.0, V_coil=0.30, m_metal=680.0),
        EvaporatorCfg("EV-04", room="LT", source="VE-LP", Q_nom=98e3,
                      UA_dry=11800.0, V_coil=0.30, m_metal=680.0),
        # Blast freezer at -30 C, two sections
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

    # --- Ice water circuit ------------------------------------------------
    ice_bank_mass_nom: float = 62000.0   # kg of water in the ice bank
    ice_max: float = 34000.0             # kg of ice built up
    ice_water_T_set: float = 274.65      # K (+1.5 C), ice water setpoint
    ice_water_T_alarm: float = 277.15    # K (+4 C), above this milk cooling fails

    # --- Milk ---------------------------------------------------------------
    milk_tank_mass: float = 45000.0      # kg in the intermediate storage tank
    milk_T_set: float = 277.15           # K (+4 C)
    milk_T_haccp: float = 279.15         # K (+6 C), HACCP limit
    milk_c: float = 3930.0               # J/(kg*K)
    milk_inlet_T: float = 348.15         # K (+75 C) after pasteurization
    milk_flow_peak: float = 4.2          # kg/s at peak reception

    # --- Control setpoints -------------------------------------------------
    P_suc_LP_set: float = 0.72e5         # Pa, corresponds to -40 C
    P_suc_IP_set: float = 2.91e5         # Pa, corresponds to -10 C
    P_cond_set: float = 11.5e5           # Pa, floating condensing pressure
    P_cond_min: float = 8.0e5            # Pa, minimum for the expansion valve and defrost to work
    oil_dP_min: float = 1.5e5            # Pa, minimum differential across the oil pump
    Cv_LV_IP: float = 6.0e-5             # capacity of the HP->IP valve
    Cv_LV_LP: float = 4.5e-5             # capacity of the IP->LP valve

    # --- Ammonia pumps -------------------------------------------------------
    pump_flow_LP: float = 3.6            # kg/s per pump
    pump_flow_IP: float = 9.5            # kg/s per pump
    pump_power: float = 5500.0           # W
    pump_head: float = 3.0e5             # Pa, ammonia pump head

    # --- Pipework ------------------------------------------------------------
    suction_header_D: float = 0.300      # m, common LP suction header
    suction_header_L: float = 68.0       # m
    suction_header_wall: float = 0.0071  # m
    suction_header_sigma_y: float = 235e6

    def by_tag(self, tag: str):
        for group in (self.compressors, self.vessels, self.condensers,
                      self.evaporators, self.rooms):
            for item in group:
                if item.tag == tag:
                    return item
        raise KeyError(tag)


DEFAULT = PlantConfig()
