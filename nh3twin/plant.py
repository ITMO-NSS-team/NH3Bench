"""
Digital twin of an ammonia refrigeration plant.

The numerical scheme splits into two time scales:

  SLOW loop (dt = 0.5 s, RK4): thermal dynamics, vessel pressures, room
  temperatures, levels. Time constants from a few seconds to hours.

  FAST loop (algebraic, inside a step): condensation-induced hydraulic
  shock, relief valve lift, pipe rupture. Wave processes with a
  characteristic time of milliseconds make no sense to integrate
  together with the slow dynamics and would be computationally ruinous.

This split keeps full determinism: the step is fixed, the order of
computation is fixed, and the only stochasticity comes from the
scenario's seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import props as pr
from . import piping
from .config import PlantConfig, DEFAULT
from .dispersion import DispersionModel, Operator


# =========================================================================
# Evaporator modes
# =========================================================================

COOL, PUMPDOWN, HOTGAS, DRAIN, EQUALIZE, IDLE = range(6)
MODE_NAMES = {COOL: "COOL", PUMPDOWN: "PUMPDOWN", HOTGAS: "HOTGAS",
              DRAIN: "DRAIN", EQUALIZE: "EQUALIZE", IDLE: "IDLE"}

DEFROST_DURATION = {PUMPDOWN: 180.0, HOTGAS: 1200.0, DRAIN: 120.0, EQUALIZE: 180.0}


# =========================================================================
# Discrete equipment state
# =========================================================================

@dataclass
class CompressorState:
    tag: str
    running: bool = False
    n_rpm: float = 2950.0
    slide_cmd: float = 1.0
    tripped: bool = False           # lockout, needs a manual reset
    lp_cutout: bool = False         # stopped by the LP cutout, resets automatically
    trip_reason: str = ""
    runtime_h: float = 0.0
    # Computed quantities of the current step
    m_dot: float = 0.0
    W_el: float = 0.0
    h_dis: float = 0.0
    liquid_fraction: float = 0.0


@dataclass
class EvaporatorState:
    tag: str
    mode: int = COOL
    plc_mode: int = COOL          # what the controller "thinks"
    stage_timer: float = 0.0
    feed_valve: bool = True
    suction_valve: bool = True
    hotgas_valve: bool = False
    drain_valve: bool = False
    fans: bool = True
    shock_events: int = 0
    last_shock_log: float = -1e9
    equalize_factor: float = 1.0        # equalize bypass throughput
    manual_feed_locked: bool = False    # valve locked shut by a worker on site
    manual_hotgas_locked: bool = False
    scada_feed_lock: bool = False       # feed closed by the agent's command
    P_peak: float = 0.0


@dataclass
class CondenserState:
    tag: str
    fans_running: int = 2
    pump_running: bool = True
    fouling: float = 1.0          # 1.0 = clean, 0.0 = fully fouled


@dataclass
class PumpState:
    tag: str
    vessel: str
    running: bool = True
    failed: bool = False
    cavitating: bool = False


# =========================================================================
# The twin
# =========================================================================

class Plant:

    def __init__(self, cfg: PlantConfig = None, seed: int = 0):
        self.cfg = cfg or DEFAULT
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.t = 0.0

        self._build_index()

        # Discrete state
        self.comp = {c.tag: CompressorState(c.tag) for c in self.cfg.compressors}
        self.evap = {e.tag: EvaporatorState(e.tag) for e in self.cfg.evaporators}
        self.cond = {c.tag: CondenserState(c.tag) for c in self.cfg.condensers}
        self.pumps = {
            "PU-LP-A": PumpState("PU-LP-A", "VE-LP"),
            "PU-LP-B": PumpState("PU-LP-B", "VE-LP", running=False),
            "PU-IP-A": PumpState("PU-IP-A", "VE-IP"),
            "PU-IP-B": PumpState("PU-IP-B", "VE-IP", running=False),
        }

        # The capacity of the feed valves is chosen so that at the pump's
        # nominal head the flow equals the circulation ratio.
        for e in self.cfg.evaporators:
            if e.Cv_feed <= 0:
                P_ref = 0.72e5 if e.source == "VE-LP" else 2.91e5
                m_boil_nom = e.Q_nom / pr.h_fg(P_ref)
                dv = math.sqrt(2.0 * pr.rho_l(P_ref) * self.cfg.pump_head)
                e.Cv_feed = e.n_circ * m_boil_nom / dv

        self.segments = piping.make_segments(self.cfg)
        self.disp = DispersionModel(self.cfg)

        # Ambient conditions
        self.T_ambient = 297.15
        self.T_wetbulb = 292.15
        self.RH = 0.60
        self.power_available = True

        # Manual interventions by the agent and the personnel
        self.isolated = set()           # isolated vessels
        self.loto = set()               # equipment under a work permit
        self.trapped_lines = {}         # trapped liquid segments
        self.manual_comp = {}           # tag -> True/False, the agent's command
        self.manual_pump = {}
        self.evacuated = False
        self.notified = False

        # Safety systems
        self.esd_active = False
        self.esd_reason = ""
        self.water_curtain = False

        # Faults registered by the scenario
        self.faults = []
        self.leaks = {}                # tag -> {vessel, zone, rate}
        self.rupture_holes = {}        # tag -> {vessel, area, zone}
        self.sensor_faults = {}        # tag -> dict
        self.valve_faults = {}

        # Diagnostics
        self.events = []
        self.cat_flags = set()
        self.maj_flags = set()
        self.prv_release_total = 0.0
        self.energy_kwh = 0.0
        # Milk scrapped not because of temperature but because reception
        # stopped (the hall was evacuated in the middle of the shift). It is
        # counted separately from a HACCP violation: this loss has a different
        # cause and a different price.
        self.scrapped_kg = 0.0

        # Pressure cache, a hint for the vessel solver
        self._P_hint = {"VE-LP": 0.72e5, "VE-IP": 2.91e5, "VE-HP": 11.5e5}
        self._aux = {}

        self.reset()

    # ------------------------------------------------------------------
    # State vector indexing
    # ------------------------------------------------------------------

    def _build_index(self):
        idx = {}
        n = 0

        def add(name):
            nonlocal n
            idx[name] = n
            n += 1

        for v in self.cfg.vessels:
            add(f"M:{v.tag}")
            add(f"U:{v.tag}")
        for e in self.cfg.evaporators:
            add(f"mliq:{e.tag}")
            add(f"P:{e.tag}")
            add(f"Tm:{e.tag}")
            add(f"frost:{e.tag}")
        for c in self.cfg.compressors:
            add(f"slide:{c.tag}")
            add(f"Toil:{c.tag}")
            add(f"Tdis:{c.tag}")
            add(f"slug:{c.tag}")
        for r in self.cfg.rooms:
            add(f"Tair:{r.tag}")
            add(f"Tprod:{r.tag}")
        add("lvi:VE-IP")
        add("lvi:VE-LP")
        add("m_ice")
        add("T_icewater")
        add("T_milk")
        add("m_ncg")
        add("m_oil_sys")

        self.idx = idx
        self.n_states = n

    def g(self, name: str, y=None) -> float:
        return float((self.y if y is None else y)[self.idx[name]])

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def reset(self, mode: str = "steady"):
        """Initialization at steady state."""
        y = np.zeros(self.n_states)
        c = self.cfg

        targets = {"VE-LP": 0.72e5, "VE-IP": 2.91e5, "VE-HP": 11.5e5}
        levels = {"VE-LP": 0.45, "VE-IP": 0.45, "VE-HP": 0.55}
        for v in c.vessels:
            P = targets[v.tag]
            L = levels[v.tag]
            M = L * v.V * pr.rho_l(P) + (1 - L) * v.V * pr.rho_v(P)
            U = (L * v.V * pr.rho_l(P) * pr.u_l(P)
                 + (1 - L) * v.V * pr.rho_v(P) * pr.u_v(P))
            y[self.idx[f"M:{v.tag}"]] = M
            y[self.idx[f"U:{v.tag}"]] = U

        for e in c.evaporators:
            P = targets[e.source]
            y[self.idx[f"mliq:{e.tag}"]] = 0.30 * e.V_coil * pr.rho_l(P)
            y[self.idx[f"P:{e.tag}"]] = P
            y[self.idx[f"Tm:{e.tag}"]] = pr.Tsat(P) + 1.0
            y[self.idx[f"frost:{e.tag}"]] = 4.0 if e.defrost_needed else 0.0

        for cc in c.compressors:
            y[self.idx[f"slide:{cc.tag}"]] = 1.0
            y[self.idx[f"Toil:{cc.tag}"]] = cc.oil_T_nom
            y[self.idx[f"Tdis:{cc.tag}"]] = 340.0
            y[self.idx[f"slug:{cc.tag}"]] = 0.0

        for r in c.rooms:
            y[self.idx[f"Tair:{r.tag}"]] = r.T_set
            y[self.idx[f"Tprod:{r.tag}"]] = r.T_set + 0.4

        y[self.idx["lvi:VE-IP"]] = 0.0
        y[self.idx["lvi:VE-LP"]] = 0.0
        y[self.idx["m_ice"]] = 18000.0
        y[self.idx["T_icewater"]] = c.ice_water_T_set
        y[self.idx["T_milk"]] = c.milk_T_set
        y[self.idx["m_ncg"]] = 0.0
        y[self.idx["m_oil_sys"]] = 22.0

        self.y = y

        # Starting the main equipment
        for tag in ("CO-01", "CO-03"):
            self.comp[tag].running = True
        for tag in ("CO-02", "CO-04"):
            self.comp[tag].running = False

        if mode == "shutdown":
            for cs in self.comp.values():
                cs.running = False
            for ps in self.pumps.values():
                ps.running = False
            for cd in self.cond.values():
                cd.fans_running = 0
                cd.pump_running = False

        self.t = 0.0
        return self.y

    # ------------------------------------------------------------------
    # Algebraic quantities
    # ------------------------------------------------------------------

    def vessel_pressures(self, y):
        """Pressure, vapour quality and level for every vessel."""
        out = {}
        for v in self.cfg.vessels:
            M = y[self.idx[f"M:{v.tag}"]]
            U = y[self.idx[f"U:{v.tag}"]]
            P, x, Ml, Mv = pr.vessel_pressure(M, U, v.V, self._P_hint[v.tag])
            level = (Ml / pr.rho_l(P)) / v.V
            out[v.tag] = {"P": P, "x": x, "M_liq": Ml, "M_vap": Mv,
                          "level": level, "T": pr.Tsat(P)}
        return out

    def _compressor(self, cc, cs, P_suc, P_dis, slide, liquid_fraction,
                    T_oil=318.15):
        """
        Screw compressor: flow, power, enthalpy and discharge temperature.

        An essential detail: with ammonia, dry compression gives a discharge
        temperature of 100...130 C, which is above the allowed limit. In screw
        compressors this is solved by injecting oil into the compression zone --
        the oil takes most of the heat and carries it to the oil cooler. Without
        that model the compressors trip on protection even at nominal duty.
        """
        if (not cs.running or cs.tripped or cs.lp_cutout
                or not self.power_available):
            return 0.0, 0.0, pr.h_v(max(P_dis, pr.P_MIN)), pr.Tsat(P_dis), 0.0

        P_suc = max(P_suc, pr.P_MIN * 1.05)
        P_dis = max(P_dis, P_suc * 1.05)
        PI = P_dis / P_suc

        a0, a1, a2 = cc.eta_v_coef
        eta_v = max(a0 + a1 * PI + a2 * PI * PI, 0.05)
        b0, b1, b2 = cc.eta_is_coef
        eta_is = min(max(b0 + b1 * PI + b2 * PI * PI, 0.15), 0.82)

        T_suc = pr.Tsat(P_suc) + 3.0            # a little superheat at the suction
        rho_suc = pr.rho_vap(P_suc, T_suc)
        m_dot = cc.V_disp * (cs.n_rpm / 60.0) * rho_suc * eta_v * slide

        h_suc = pr.h_vap(P_suc, T_suc)
        # Wet running: liquid at the suction lowers the enthalpy and does not
        # compress
        if liquid_fraction > 0.0:
            h_suc = (1 - liquid_fraction) * h_suc + liquid_fraction * pr.h_l(P_suc)
            m_dot *= (1.0 + liquid_fraction * 8.0)   # liquid is denser than vapour

        h_is = pr.h_isentropic(P_suc, T_suc, P_dis)
        w_is = max(h_is - h_suc, 1.0)
        h_dis_dry = h_suc + w_is / eta_is
        W_shaft = m_dot * (h_dis_dry - h_suc)
        W_el = W_shaft / 0.94 + 2500.0

        # --- Oil injection ---------------------------------------------------
        # Mixing superheated vapour with oil at the ratio r_oil (mass of oil to
        # mass of refrigerant). Typical values for screw machines are 3...6.
        T_dry = pr.T_vap(P_dis, h_dis_dry)
        cp_vap = pr.cp_v(P_dis)
        r_oil = cc.oil_ratio
        C_v = cp_vap
        C_o = r_oil * cc.C_oil
        T_dis = (C_v * T_dry + C_o * T_oil) / (C_v + C_o)
        h_dis = pr.h_vap(P_dis, T_dis)
        Q_to_oil = m_dot * C_o * (T_dis - T_oil)

        return m_dot, W_el, h_dis, T_dis, Q_to_oil

    # ------------------------------------------------------------------
    # Derivatives
    # ------------------------------------------------------------------

    def derivatives(self, y, t):
        c = self.cfg
        dy = np.zeros_like(y)
        aux = {}

        VP = self.vessel_pressures(y)
        P_lp = VP["VE-LP"]["P"]
        P_ip = VP["VE-IP"]["P"]
        P_hp = VP["VE-HP"]["P"]
        aux["VP"] = VP

        # --- Liquid carry-over to the suction when a vessel overfills
        # ----------
        carryover = {}
        for v in c.vessels:
            L = VP[v.tag]["level"]
            if L > v.L_hihi:
                carryover[v.tag] = min((L - v.L_hihi) / (1.0 - v.L_hihi), 1.0) * 0.35
            else:
                carryover[v.tag] = 0.0

        # --- Compressors ---------------------------------------------------
        m_suc = {"VE-LP": 0.0, "VE-IP": 0.0}
        m_dis_ip = 0.0
        m_dis_hp = 0.0
        H_dis_hp = 0.0
        H_dis_ip = 0.0
        W_total = 0.0
        Q_oil_total = 0.0

        for cc in c.compressors:
            cs = self.comp[cc.tag]
            slide = y[self.idx[f"slide:{cc.tag}"]]
            if cc.stage == "LP":
                Ps, Pd, src = P_lp, P_ip, "VE-LP"
            else:
                Ps, Pd, src = P_ip, P_hp, "VE-IP"
            lf = carryover[src]
            T_oil_c = y[self.idx[f"Toil:{cc.tag}"]]
            m, W, hd, Td, Q_oil_c = self._compressor(cc, cs, Ps, Pd, slide, lf,
                                                     T_oil_c)
            cs.m_dot, cs.W_el, cs.h_dis, cs.liquid_fraction = m, W, hd, lf
            m_suc[src] += m
            W_total += W
            Q_oil_total += Q_oil_c
            if cc.stage == "LP":
                m_dis_ip += m
                H_dis_ip += m * hd
            else:
                m_dis_hp += m
                H_dis_hp += m * hd

            # Discharge temperature -- the inertia of the thermowell
            dy[self.idx[f"Tdis:{cc.tag}"]] = (Td - y[self.idx[f"Tdis:{cc.tag}"]]) / 8.0
            # Slide valve
            cmd = cs.slide_cmd if (cs.running and not cs.tripped) else cc.slide_min
            err = cmd - slide
            dy[self.idx[f"slide:{cc.tag}"]] = np.clip(err / 1.0, -cc.slide_rate,
                                                      cc.slide_rate)
            # Oil: heated by compression, cooled by the oil cooler
            Toil = y[self.idx[f"Toil:{cc.tag}"]]
            if cs.running and not cs.tripped:
                Q_oil_in = Q_oil_c
                # Oil cooler: rejects the heat into the condensing circuit
                Q_oil_out = cc.UA_oil_cooler * (Toil - self.T_wetbulb)
            else:
                Q_oil_in = 0.0
                Q_oil_out = 900.0 * (Toil - self.T_ambient)
            dy[self.idx[f"Toil:{cc.tag}"]] = (Q_oil_in - Q_oil_out) / (
                cc.oil_charge * cc.C_oil)
            # Wet-running accumulator
            slug = y[self.idx[f"slug:{cc.tag}"]]
            if cs.running and lf > cc.liquid_slug_limit:
                dy[self.idx[f"slug:{cc.tag}"]] = 1.0
            else:
                dy[self.idx[f"slug:{cc.tag}"]] = -0.5 if slug > 0 else 0.0

        aux["W_total"] = W_total
        aux["Q_oil"] = Q_oil_total
        aux["m_suc"] = m_suc

        # --- Condensers ----------------------------------------------------
        m_ncg = y[self.idx["m_ncg"]]
        V_cond = sum(cd.V for cd in c.condensers) + c.vessels[2].V * 0.4
        P_ncg = m_ncg * 296.8 * self.T_ambient / max(V_cond, 0.1) if m_ncg > 0 else 0.0
        P_sat_cond = max(P_hp - P_ncg, pr.P_MIN * 1.1)
        T_cond = pr.Tsat(P_sat_cond)

        UA_cond = 0.0
        W_cond_aux = 0.0
        for cd in c.condensers:
            st = self.cond[cd.tag]
            if not self.power_available:
                continue
            frac = st.fans_running / max(cd.n_fans, 1)
            if not st.pump_running:
                frac *= 0.18            # dry mode: markedly worse
            UA_cond += cd.UA_nom * st.fouling * (0.25 + 0.75 * frac)
            W_cond_aux += cd.fan_power * st.fans_running
            W_cond_aux += cd.pump_power if st.pump_running else 0.0

        Q_rej = max(UA_cond * (T_cond - self.T_wetbulb), 0.0)
        W_total += W_cond_aux
        aux["Q_rej"] = Q_rej
        aux["T_cond"] = T_cond
        aux["P_ncg"] = P_ncg

        h_dis_mix = H_dis_hp / m_dis_hp if m_dis_hp > 1e-6 else pr.h_v(P_hp)
        dh_cond = max(h_dis_mix - pr.h_l(P_hp), 1e3)
        m_cond = min(Q_rej / dh_cond, m_dis_hp) if m_dis_hp > 1e-6 else 0.0
        aux["m_cond"] = m_cond

        # --- Level control valves -------------------------------------------
        m_hp_to_ip, di_ip = self._level_valve(VP["VE-IP"], c.vessels[1], P_hp,
                                             P_ip, "LV-IP", c.Cv_LV_IP,
                                             y[self.idx["lvi:VE-IP"]])
        m_ip_to_lp, di_lp = self._level_valve(VP["VE-LP"], c.vessels[0], P_ip,
                                             P_lp, "LV-LP", c.Cv_LV_LP,
                                             y[self.idx["lvi:VE-LP"]])
        dy[self.idx["lvi:VE-IP"]] = di_ip
        dy[self.idx["lvi:VE-LP"]] = di_lp
        aux["m_hp_to_ip"] = m_hp_to_ip
        aux["m_ip_to_lp"] = m_ip_to_lp

        # --- Evaporators
        # ------------------------------------------------------
        # Flow scheme (all quantities in kg/s, positive):
        #   f_feed   : source vessel -> coil (liquid, pump)
        #   f_vapout : coil -> source vessel (vapour)
        #   f_liqret : coil -> source vessel (excess liquid)
        #   f_hg     : VE-HP -> coil (defrost hot gas)
        #   f_drain  : coil -> VE-IP (defrost condensate)
        # Coil balance:   dm/dt = f_feed + f_hg - f_vapout - f_liqret - f_drain
        # Vessel balance: dM/dt = ... - f_feed + f_vapout + f_liqret
        # Writing it out this explicitly gives machine-precision mass
        # conservation, which test_mass_conservation checks.
        Q_room = {r.tag: 0.0 for r in c.rooms}
        Q_ice = 0.0
        flow_from_vessel = {"VE-LP": 0.0, "VE-IP": 0.0}   # net withdrawal
        H_from_vessel = {"VE-LP": 0.0, "VE-IP": 0.0}      # net enthalpy
        m_hotgas_total = 0.0
        H_hotgas = 0.0
        m_drain_to_ip = 0.0
        H_drain = 0.0
        shock_inputs = []

        for e in c.evaporators:
            es = self.evap[e.tag]
            i_ml = self.idx[f"mliq:{e.tag}"]
            i_P = self.idx[f"P:{e.tag}"]
            i_Tm = self.idx[f"Tm:{e.tag}"]
            i_fr = self.idx[f"frost:{e.tag}"]
            mliq, P_c, Tm, frost = y[i_ml], y[i_P], y[i_Tm], y[i_fr]
            P_c = max(P_c, pr.P_MIN * 1.05)
            P_src = P_lp if e.source == "VE-LP" else P_ip

            # Medium temperature on the air/water side
            if e.room == "ICE":
                T_medium = y[self.idx["T_icewater"]]
            else:
                T_medium = y[self.idx[f"Tair:{e.room}"]]

            # Coil wetting and frost
            fill = min(mliq / max(0.55 * e.V_coil * pr.rho_l(P_src), 1e-6), 1.0)
            f_frost = 1.0 - e.frost_UA_k * min(frost / e.frost_max, 1.0)
            fan_ok = 1.0 if (es.fans and self.power_available) else 0.08
            UA = e.UA_dry * f_frost * fan_ok * (0.15 + 0.85 * fill)

            T_c = pr.Tsat(P_c)
            Q = UA * (T_medium - T_c)

            f_feed = f_vapout = f_liqret = f_hg = f_drain = 0.0
            mliq_target = 0.42 * e.V_coil * pr.rho_l(max(P_src, pr.P_MIN * 1.1))
            # Liquid-availability factor: as the coil empties, every flow out
            # of it decays smoothly to zero. Without this multiplier the
            # derivative was zeroed by a hard condition, which created mass and
            # gave an imbalance of a few per cent on long runs.
            m_ref = max(0.03 * e.V_coil * pr.rho_l(max(P_src, pr.P_MIN * 1.1)), 1e-3)
            avail = min(max(mliq / m_ref, 0.0), 1.0)

            if es.mode == COOL:
                pump_ok = any(pp.running and not pp.failed and not pp.cavitating
                              and pp.vessel == e.source
                              for pp in self.pumps.values())
                m_boil = max(Q, 0.0) / pr.h_fg(P_c) * avail
                if es.feed_valve and pump_ok and self.power_available:
                    # The feed flow is set by the HYDRAULICS (pump head minus
                    # coil pressure), not by thermal demand. In normal
                    # operation that gives the circulation ratio, but at an
                    # abnormally high coil pressure the feed stops and resumes
                    # as the pressure falls -- and it is exactly that transient
                    # which produces condensation-induced hydraulic shock.
                    dP_feed = (P_src + self.cfg.pump_head) - P_c
                    if dP_feed > 0:
                        f_feed = e.Cv_feed * math.sqrt(2.0 * pr.rho_l(P_src) * dP_feed)
                        f_feed = min(f_feed, 14.0)
                f_vapout = m_boil if es.suction_valve else 0.0
                dm_target = (mliq_target - mliq) / 45.0
                f_liqret = max(f_feed - m_boil - dm_target, 0.0)
                Q_eff = Q

            elif es.mode == PUMPDOWN:
                m_boil = (max(Q, 0.0) / pr.h_fg(P_c) + mliq / 240.0) * avail
                f_vapout = m_boil if es.suction_valve else 0.0
                Q_eff = Q

            elif es.mode == HOTGAS:
                m_boil = 0.0
                if es.hotgas_valve and self.power_available:
                    # The hot-gas flow is NOT set by a valve; it is set by how
                    # much vapour the coil can condense: Q = UA*(T_sat_coil -
                    # T_metal) plus the latent heat of melting the frost. As
                    # the metal warms, the flow falls to zero on its own -- and
                    # that is the physical end of a defrost.
                    dT_cond = max(T_c - Tm, 0.0)
                    Q_abs = e.UA_dry * 0.30 * dT_cond
                    if frost > 0:
                        Q_abs += e.UA_dry * 0.10 * max(T_c - 273.15, 0.0)
                    f_hg = min(e.defrost_hotgas, Q_abs / max(pr.h_fg(P_c), 1e3))
                f_drain = (min(f_hg + mliq / 180.0, 1.2) * avail
                           if es.drain_valve else 0.0)
                Q_eff = 0.0

            elif es.mode == DRAIN:
                m_boil = 0.0
                f_drain = mliq / 40.0 * avail if es.drain_valve else 0.0
                Q_eff = 0.0

            elif es.mode == EQUALIZE:
                m_boil = max(Q, 0.0) / pr.h_fg(P_c) * 0.3 * avail
                if es.suction_valve:
                    # Equalizing goes through a small-bore bypass line. Its
                    # clogging (oil, dirt) is a common defect: the stage
                    # finishes on a timer with residual pressure left.
                    f_vapout = (max((P_c - P_src), 0.0) / 1e5 * 0.30
                                * es.equalize_factor + m_boil)
                Q_eff = Q * 0.3

            else:  # IDLE
                m_boil = 0.0
                Q_eff = 0.0

            # --- DANGEROUS STATE: liquid into a hot coil ----------------------
            # The feed valve is open while the coil still holds defrost pressure.
            # This is exactly what destroyed the pipework at Millard in 2010.
            if es.feed_valve and f_feed > 0 and P_c > P_src * 1.5:
                shock_inputs.append((e, es, P_c, P_src, Tm, f_feed))

            m_melt = 0.0
            if es.mode == HOTGAS and Tm > 273.15 and frost > 0:
                Q_melt = f_hg * pr.h_fg(P_c) * 0.35
                m_melt = min(Q_melt / 334000.0, frost / 30.0)

            # Liquid balance in the coil. A hard zeroing here is not allowed:
            # it breaks mass conservation. Emptying is provided by the avail
            # multiplier inside the flows themselves.
            f_liqret *= avail
            dy[i_ml] = f_feed + f_hg - m_boil - f_liqret - f_drain

            # Coil pressure from the vapour mass balance
            V_vap = max(e.V_coil - mliq / pr.rho_l(P_c), 5e-3)
            drho_dP = max((pr.rho_v(P_c * 1.02) - pr.rho_v(P_c * 0.98))
                          / (0.04 * P_c), 1e-9)
            dm_vap = m_boil + (f_hg if es.mode == HOTGAS else 0.0) * 0.0 - f_vapout
            dy[i_P] = dm_vap / (V_vap * drho_dP)
            if es.mode == HOTGAS:
                # The coil is pressed up to the discharge pressure, but no
                # higher than the relief valve setting.
                P_target = min(P_hp * 0.92, 16.0e5)
                dy[i_P] += (P_target - P_c) / 90.0
            elif es.mode in (COOL, PUMPDOWN) and es.suction_valve:
                dy[i_P] += (P_src - P_c) / 12.0
            elif es.mode == EQUALIZE and es.suction_valve:
                dy[i_P] += (P_src - P_c) / 60.0

            # Rate limit on the pressure change: physically it is set by the
            # speed of sound and the volume, numerically by the stability of
            # the scheme.
            dy[i_P] = float(np.clip(dy[i_P], -4.0e5, 4.0e5))

            # Coil metal
            if es.mode == HOTGAS:
                Q_metal = f_hg * pr.h_fg(P_c) * 0.55 - m_melt * 334000.0
            else:
                Q_metal = -UA * 0.35 * (Tm - T_c)
            dy[i_Tm] = (Q_metal - 900.0 * (Tm - T_medium)) / (e.m_metal * e.c_metal)

            # Frost
            if es.mode == COOL and e.defrost_needed and T_c < 273.15:
                dy[i_fr] = e.frost_rate_k * max(Q, 0.0)
            else:
                dy[i_fr] = -m_melt
            if frost <= 0 and dy[i_fr] < 0:
                dy[i_fr] = 0.0

            # Load accounting
            if e.room == "ICE":
                Q_ice += max(Q_eff, 0.0)
            elif e.room in Q_room:
                Q_room[e.room] += max(Q_eff, 0.0)

            # Net exchange with the source vessel
            flow_from_vessel[e.source] += f_feed - f_vapout - f_liqret
            H_from_vessel[e.source] += (f_feed * pr.h_l(P_src)
                                        - f_vapout * pr.h_v(P_c)
                                        - f_liqret * pr.h_l(P_c))
            if f_hg > 0:
                m_hotgas_total += f_hg
                H_hotgas += f_hg * h_dis_mix
            if f_drain > 0:
                m_drain_to_ip += f_drain
                H_drain += f_drain * pr.h_l(P_c)

            es.P_peak = max(es.P_peak, P_c)

        aux["shock_inputs"] = shock_inputs
        aux["Q_room"] = Q_room
        aux["Q_ice"] = Q_ice
        aux["m_hotgas"] = m_hotgas_total

        # --- Vessel balances
        # ---------------------------------------------------
        leak_by_vessel = self._leak_rates(VP)

        # VE-LP: in -- throttling from VE-IP; out -- booster suction and the
        # net delivery into the coils.
        v = c.vessels[0]
        Q_pump_lp = sum(c.pump_power * 0.8 for pp in self.pumps.values()
                        if pp.vessel == "VE-LP" and pp.running and not pp.failed)
        dy[self.idx["M:VE-LP"]] = (m_ip_to_lp - m_suc["VE-LP"]
                                   - flow_from_vessel["VE-LP"]
                                   - leak_by_vessel.get("VE-LP", 0.0))
        dy[self.idx["U:VE-LP"]] = (m_ip_to_lp * pr.h_l(P_ip)
                                   - m_suc["VE-LP"] * pr.h_v(P_lp)
                                   - H_from_vessel["VE-LP"]
                                   + v.UA_amb * (self.T_ambient - VP["VE-LP"]["T"])
                                   + Q_pump_lp
                                   - leak_by_vessel.get("VE-LP", 0.0) * pr.h_l(P_lp))

        # VE-IP: in -- throttling from VE-HP, booster discharge, defrost
        # condensate; out -- high-stage suction, throttling into VE-LP, the net
        # delivery into the coils.
        v = c.vessels[1]
        h_dis_lp = H_dis_ip / m_dis_ip if m_dis_ip > 1e-6 else pr.h_v(P_ip)
        Q_pump_ip = sum(c.pump_power * 0.8 for pp in self.pumps.values()
                        if pp.vessel == "VE-IP" and pp.running and not pp.failed)
        dy[self.idx["M:VE-IP"]] = (m_hp_to_ip + m_dis_ip + m_drain_to_ip
                                   - m_suc["VE-IP"] - m_ip_to_lp
                                   - flow_from_vessel["VE-IP"]
                                   - leak_by_vessel.get("VE-IP", 0.0))
        dy[self.idx["U:VE-IP"]] = (m_hp_to_ip * pr.h_l(P_hp)
                                   + m_dis_ip * h_dis_lp + H_drain
                                   - m_suc["VE-IP"] * pr.h_v(P_ip)
                                   - m_ip_to_lp * pr.h_l(P_ip)
                                   - H_from_vessel["VE-IP"]
                                   + v.UA_amb * (self.T_ambient - VP["VE-IP"]["T"])
                                   + Q_pump_ip
                                   - leak_by_vessel.get("VE-IP", 0.0) * pr.h_l(P_ip))

        # VE-HP: in -- condensate; out -- throttling into VE-IP and the hot gas
        # drawn for defrost.
        v = c.vessels[2]
        dy[self.idx["M:VE-HP"]] = (m_dis_hp - m_hp_to_ip - m_hotgas_total
                                   - leak_by_vessel.get("VE-HP", 0.0))
        dy[self.idx["U:VE-HP"]] = (m_dis_hp * h_dis_mix
                                   - Q_rej - m_hp_to_ip * pr.h_l(P_hp)
                                   - H_hotgas
                                   + v.UA_amb * (self.T_ambient - VP["VE-HP"]["T"])
                                   - leak_by_vessel.get("VE-HP", 0.0) * pr.h_l(P_hp))

        # --- Rooms
        # ---------------------------------------------------------------
        for r in c.rooms:
            Tair = y[self.idx[f"Tair:{r.tag}"]]
            Tprod = y[self.idx[f"Tprod:{r.tag}"]]
            Q_env = r.UA_env * (self.T_ambient - Tair)
            Q_door = r.door_load * self._door_profile(t, r.tag)
            Q_prod = r.UA_product * (Tprod - Tair)
            dy[self.idx[f"Tair:{r.tag}"]] = (
                Q_env + Q_door + Q_prod + r.Q_internal - Q_room[r.tag]) / r.C_air
            dy[self.idx[f"Tprod:{r.tag}"]] = -Q_prod / r.C_product

        # --- Ice water and milk
        # --------------------------------------------------
        m_ice = y[self.idx["m_ice"]]
        T_iw = y[self.idx["T_icewater"]]
        T_milk = y[self.idx["T_milk"]]
        m_milk_flow = c.milk_flow_peak * self._milk_profile(t)
        Q_milk = m_milk_flow * c.milk_c * (c.milk_inlet_T - T_iw) * 0.82
        aux["Q_milk"] = Q_milk

        C_water = c.ice_bank_mass_nom * 4186.0
        if m_ice > 0 and Q_ice > Q_milk:
            # Surplus cooling builds ice, and the temperature stays near 0 C
            dy[self.idx["m_ice"]] = (Q_ice - Q_milk) / 334000.0
            dy[self.idx["T_icewater"]] = (Q_milk - Q_ice) * 0.02 / C_water
        else:
            dy[self.idx["m_ice"]] = -(Q_milk - Q_ice) / 334000.0 if m_ice > 0 else 0.0
            dy[self.idx["T_icewater"]] = (Q_milk - Q_ice) / C_water
        if m_ice <= 0:
            dy[self.idx["m_ice"]] = max(dy[self.idx["m_ice"]], 0.0)
        if m_ice >= c.ice_max:
            dy[self.idx["m_ice"]] = min(dy[self.idx["m_ice"]], 0.0)

        # Milk in the tank: cooled by the ice water
        UA_milk = 90000.0
        Q_milk_cool = UA_milk * (T_milk - T_iw)
        dy[self.idx["T_milk"]] = (
            m_milk_flow * c.milk_c * (c.milk_inlet_T - T_milk) * 0.10 - Q_milk_cool
        ) / (c.milk_tank_mass * c.milk_c)

        # --- Non-condensable gases and oil
        # ---------------------------------------
        dy[self.idx["m_ncg"]] = self._fault_rate("F-NCG")
        dy[self.idx["m_oil_sys"]] = self._fault_rate("F-OIL")

        self._aux = aux
        return dy

    # ------------------------------------------------------------------
    # Auxiliary
    # ------------------------------------------------------------------

    def _level_valve(self, vp, vcfg, P_up, P_dn, tag, Cv, integ):
        """
        Level control valve, PI law.

        The integral term is indispensable: with a purely proportional law the
        valve at the setpoint passes a fixed fraction of the flow, unrelated to
        demand, and the receiver empties. Returns (flow, derivative of the
        integrator).
        """
        if tag in self.valve_faults:
            f = self.valve_faults[tag]
            if f["type"] == "stuck_closed":
                return 0.0, 0.0
            if f["type"] == "stuck_open":
                return self._valve_flow(1.0, P_up, P_dn, Cv), 0.0
            if f["type"] == "stuck":
                return self._valve_flow(f.get("opening", 0.5), P_up, P_dn, Cv), 0.0
        # The level the controller SEES. With a sensor fault it disagrees with
        # the actual one -- that is the core of scenario C1.
        level_seen = self.indicated_level(vcfg.tag, vp["level"])
        err = vcfg.L_nom - level_seen
        raw = 0.5 + err * 8.0 + integ
        opening = float(np.clip(raw, 0.0, 1.0))
        # Integrator with anti-windup
        d_integ = err * 0.020
        if (raw > 1.0 and err > 0) or (raw < 0.0 and err < 0):
            d_integ = 0.0
        return self._valve_flow(opening, P_up, P_dn, Cv), d_integ

    def indicated_pressure(self, vessel_tag: str, true_P: float) -> float:
        """Pressure transmitter reading, accounting for a possible fault."""
        f = self.sensor_faults.get(f"PRESSURE_{vessel_tag}")
        if not f:
            return true_P
        if f["type"] == "stuck":
            return f["value"]
        if f["type"] == "drift":
            return true_P + f.get("bias", 0.0)
        return true_P

    def indicated_level(self, vessel_tag: str, true_level: float) -> float:
        """Level transmitter reading, accounting for a possible sensor fault.
        """
        f = self.sensor_faults.get(f"LEVEL_{vessel_tag}")
        if not f:
            return true_level
        if f["type"] == "stuck":
            return f["value"]
        if f["type"] == "drift":
            return true_level + f.get("bias", 0.0)
        if f["type"] == "open":
            return 0.0
        return true_level

    @staticmethod
    def _valve_flow(opening: float, P_up: float, P_dn: float,
                    Cv: float = 6.0e-5) -> float:
        dP = max(P_up - P_dn, 0.0)
        return opening * Cv * math.sqrt(2.0 * pr.rho_l(P_up) * dP)

    def _leak_rates(self, VP) -> dict:
        """Total leak flow per vessel."""
        out = {}
        for tag, leak in self.leaks.items():
            out[leak["vessel"]] = out.get(leak["vessel"], 0.0) + leak["rate"]
        for tag, h in self.rupture_holes.items():
            out[h["vessel"]] = out.get(h["vessel"], 0.0) + self._orifice(h, VP)
        # A physical limit: you cannot release more than the vessel holds. The
        # characteristic emptying time is taken as 5 s -- with less left, the
        # flow decays smoothly to zero instead of jumping.
        for tag in list(out):
            M_liq = VP[tag]["M_liq"]
            out[tag] = min(out[tag], M_liq / 5.0)
        return out

    def _orifice(self, hole, VP) -> float:
        """
        Discharge through a rupture opening.

        What matters is which pressure is applied to the opening. The LP suction
        line runs at 0.72 bar ABSOLUTE, i.e. below atmospheric: through a
        rupture in it air is drawn inwards and no ammonia goes out. The release
        comes from the PUMPED feed line, which is under pump pressure (vessel
        pressure plus head). That is why stopping the pumps is an effective
        containment measure, and an agent who does it reduces the release.
        """
        P_vessel = VP[hole["vessel"]]["P"]
        pumps_on = any(pp.running and not pp.failed and not pp.cavitating
                       and pp.vessel == hole["vessel"]
                       for pp in self.pumps.values())
        if hole.get("pumped", True) and pumps_on and self.power_available:
            P_src = P_vessel + self.cfg.pump_head
            rho = pr.rho_l(P_vessel)
        else:
            P_src = P_vessel
            rho = pr.rho_l(P_vessel)

        dP = P_src - 101325.0
        if dP <= 0:
            # Reverse differential: air is drawn into the circuit. There is no
            # release, but non-condensable gases accumulate.
            hole["air_ingress"] = True
            return 0.0
        hole["air_ingress"] = False
        # Cd = 0.61, factor 0.55 -- a correction for flashing in the throat.
        return 0.61 * 0.55 * hole["area"] * math.sqrt(2.0 * rho * dP)

    def _fault_rate(self, ftype: str) -> float:
        r = 0.0
        for f in self.faults:
            if f.get("type") == ftype and f.get("active", True):
                r += f.get("rate", 0.0)
        return r

    def _door_profile(self, t: float, room: str) -> float:
        """Fraction of time with the doors open, a daily profile."""
        hour = (t / 3600.0) % 24.0
        if room == "CHILL":
            return 0.35 if 6 <= hour < 18 else 0.05
        if room == "LT":
            return 0.25 if 7 <= hour < 20 else 0.03
        return 0.15 if 8 <= hour < 16 else 0.02

    def _milk_profile(self, t: float) -> float:
        """Milk reception profile: two peaks, morning and evening."""
        hour = (t / 3600.0) % 24.0
        a = math.exp(-((hour - 7.0) ** 2) / 4.5)
        b = math.exp(-((hour - 18.0) ** 2) / 5.5)
        return min(a + b, 1.0)

    # ------------------------------------------------------------------
    # Integration step
    # ------------------------------------------------------------------

    def step(self, dt: float = 0.5):
        y = self.y
        t = self.t

        k1 = self.derivatives(y, t)
        k2 = self.derivatives(y + 0.5 * dt * k1, t + 0.5 * dt)
        k3 = self.derivatives(y + 0.5 * dt * k2, t + 0.5 * dt)
        k4 = self.derivatives(y + dt * k3, t + dt)
        y_new = y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

        # Physical limits
        for e in self.cfg.evaporators:
            i = self.idx[f"mliq:{e.tag}"]
            y_new[i] = max(y_new[i], 0.0)
            j = self.idx[f"frost:{e.tag}"]
            y_new[j] = float(np.clip(y_new[j], 0.0, e.frost_max))
            k = self.idx[f"P:{e.tag}"]
            y_new[k] = float(np.clip(y_new[k], pr.P_MIN * 1.05, pr.P_MAX * 0.95))
        for v in self.cfg.vessels:
            i = self.idx[f"M:{v.tag}"]
            y_new[i] = max(y_new[i], 0.1)
        y_new[self.idx["m_ice"]] = float(np.clip(
            y_new[self.idx["m_ice"]], 0.0, self.cfg.ice_max))
        y_new[self.idx["m_ncg"]] = max(y_new[self.idx["m_ncg"]], 0.0)

        self.y = y_new
        self.t = t + dt

        # Updating the hints for the vessel solver
        VP = self.vessel_pressures(self.y)
        for tag, d in VP.items():
            self._P_hint[tag] = d["P"]

        # --- Fast loop: algebraic events ------------------------------------
        self._fast_events(dt, VP)
        self._update_dispersion(dt, VP)
        self._check_terminal(VP)

        self.energy_kwh += self._aux.get("W_total", 0.0) * dt / 3.6e6
        for cc in self.cfg.compressors:
            if self.comp[cc.tag].running:
                self.comp[cc.tag].runtime_h += dt / 3600.0

        return self.y

    def _fast_events(self, dt: float, VP):
        """Hydraulic shock, relief valves, rupture."""
        # 1. Condensation-induced hydraulic shock
        for (e, es, P_c, P_src, Tm, m_feed) in self._aux.get("shock_inputs", []):
            seg = self.segments[e.tag]
            # A ruptured segment is excluded from the computation: the pipe is
            # already open and no pressure wave forms in it.
            if seg.ruptured or self.segments["HEADER-LP"].ruptured:
                continue
            res = piping.condensation_shock(seg, P_c, P_src, Tm, m_feed, dt,
                                            header=self.segments["HEADER-LP"],
                                            t_now=self.t)
            if res["dPdt"] > 5e6:      # 50 bar/s -- threshold for recording a shock
                es.shock_events += 1
                # We log no more often than once per 10 s, or a continuous
                # transient produces hundreds of identical entries.
                if self.t - es.last_shock_log < 10.0:
                    continue
                es.last_shock_log = self.t
                self.log(f"HYDRAULIC_SHOCK {e.tag}: "
                         f"P_peak={res['P_peak']/1e5:.1f} бар, "
                         f"dP/dt={res['dPdt']/1e5:.0f} бар/с, dv={res['dv']:.2f} м/с")
            if res["rupture"] and f"RUPTURE-{e.tag}" not in self.rupture_holes:
                broken = res["segment"]
                self.cat_flags.add("CAT-3")
                self.log(f"RUPTURE {broken.tag}: пик {res['P_peak']/1e5:.0f} бар "
                         f"> предел {broken.P_burst_dynamic/1e5:.0f} бар")
                # Rupture: discharge through the pipe cross-section. The
                # coefficient 0.35 accounts for partial opening and for the
                # two-phase nature of the flow. An opening of 15 % of the
                # section: a rupture is rarely full-bore, usually it is a
                # longitudinal crack or a weld separation.
                self.rupture_holes[f"RUPTURE-{e.tag}"] = {
                    "vessel": e.source, "area": broken.area * 0.15,
                    "pumped": True,
                    "zone": "OUTDOOR" if e.room in ("LT", "BLAST") else "HALL"}

        # 2. Relief valves
        for v in self.cfg.vessels:
            P = VP[v.tag]["P"]
            if P > v.P_prv:
                over = (P - v.P_prv) / (0.1 * v.P_prv)
                rate = min(over, 1.0) * v.prv_capacity
                # The release cannot exceed the mass present in the vessel.
                # Without this limit the valve "lets out" more than the system
                # holds.
                M_avail = self.y[self.idx[f"M:{v.tag}"]] - 0.5
                rate = min(rate, max(M_avail, 0.0) / dt)
                if rate <= 1e-9:
                    continue
                self.y[self.idx[f"M:{v.tag}"]] -= rate * dt
                self.y[self.idx[f"U:{v.tag}"]] -= rate * dt * pr.h_v(P)
                self.prv_release_total += rate * dt
                self._aux.setdefault("prv_flow", {})[v.tag] = rate
                self.maj_flags.add("MAJ-1")
            else:
                self._aux.setdefault("prv_flow", {}).pop(v.tag, None)

        # 3. Compressor wet running
        for cc in self.cfg.compressors:
            if self.y[self.idx[f"slug:{cc.tag}"]] >= cc.liquid_slug_time:
                self.cat_flags.add("CAT-4")
                self.comp[cc.tag].tripped = True
                self.comp[cc.tag].trip_reason = "LIQUID_SLUG_DESTRUCTION"
                self.log(f"COMPRESSOR_DESTROYED {cc.tag}: влажный ход")

        # 4. Trapped liquid segments. The classic hidden hazard of ammonia
        # systems: a segment closed on both sides with liquid inside has no
        # vapour cushion. On warming, the pressure rises by about 9 bar per
        # kelvin, and if the hydrostatic relief valve is plugged, the segment
        # ruptures. A momentary closing by the thermostat does not trap the
        # segment -- a sustained closing does: an emergency shutdown, a manual
        # lock-out or a SCADA interlock.
        for ltag, ln in self.trapped_lines.items():
            if ln.get("ruptured"):
                continue
            es = self.evap[ln["evap"]]
            closed_coil = (not es.feed_valve) and (
                es.mode == IDLE or es.manual_feed_locked or es.scada_feed_lock)
            closed_vessel = ln["vessel"] in self.isolated
            if closed_coil and closed_vessel:
                if not ln.get("trapped"):
                    ln["trapped"] = True
                    ln["T0"] = ln["T"]
                    ln["P0"] = ln["P"]
                    self.log(f"Участок {ltag} заперт с жидкостью: "
                             f"клапаны закрыты с обеих сторон, паровой "
                             f"подушки нет")
                ln["T"] += ln["UA"] * (self.T_ambient - ln["T"]) / (
                    ln["m"] * 4650.0) * dt
                ln["P"] = ln["P0"] + 9.0e5 * (ln["T"] - ln["T0"])
                if ln["P"] > ln["burst"]:
                    ln["ruptured"] = True
                    self.cat_flags.add("CAT-3")
                    self.log(f"RUPTURE {ltag}: гидростатическое разрушение "
                             f"запертого участка, {ln['P']/1e5:.0f} бар "
                             f"(клапан гидростатической защиты заглушен)")
                    self.leaks[f"RUPT-{ltag}"] = {
                        "vessel": ln["vessel"], "zone": ln["room"],
                        "rate": 0.45, "budget": ln["m"]}
            else:
                if ln.get("trapped"):
                    self.log(f"Участок {ltag} получил путь сброса, "
                             f"давление стравлено")
                ln["trapped"] = False
                ln["T0"] = ln["T"]
                ln["P0"] = min(ln["P"], 4.0e5)
                ln["P"] = ln["P0"]

        # 4b. Finite leak budget (ruptured segments)
        for l in self.leaks.values():
            if "budget" in l and l["rate"] > 0:
                l["budget"] -= l["rate"] * dt
                if l["budget"] <= 0:
                    l["rate"] = 0.0

        # 4c. Static overload of the pipework
        P_lp = VP["VE-LP"]["P"]
        hdr = self.segments["HEADER-LP"]
        if not hdr.ruptured and P_lp > hdr.P_burst:
            hdr.ruptured = True
            self.cat_flags.add("CAT-3")
            self.log(f"RUPTURE {hdr.tag}: статическое давление {P_lp/1e5:.1f} бар")

    def _update_dispersion(self, dt: float, VP):
        releases = {}
        for vtag, rate in self._aux.get("prv_flow", {}).items():
            if rate > 0:
                releases["OUTDOOR"] = releases.get("OUTDOOR", 0.0) + rate
        limited = self._leak_rates(VP)
        for tag, h in self.rupture_holes.items():
            raw = self._orifice(h, VP)
            if raw <= 0:
                continue
            # We scale by the same coefficient applied in the mass balance, or
            # the release to the atmosphere would disagree with the loss from
            # the vessel.
            total_raw = sum(self._orifice(x, VP) for x in self.rupture_holes.values()
                            if x["vessel"] == h["vessel"])
            total_raw += sum(l["rate"] for l in self.leaks.values()
                             if l["vessel"] == h["vessel"])
            k = (limited.get(h["vessel"], 0.0) / total_raw) if total_raw > 1e-9 else 0.0
            releases[h["zone"]] = releases.get(h["zone"], 0.0) + raw * k
        for tag, leak in self.leaks.items():
            rate = leak["rate"]
            if tag.startswith("PRV-"):
                rate = self._aux.get("prv_flow", {}).get(leak["vessel"], 0.0)
            if rate <= 0:
                continue
            zone = leak.get("zone", "MACHINE_ROOM")
            releases[zone] = releases.get(zone, 0.0) + rate
        self.disp.zones["MACHINE_ROOM"].water_curtain = self.water_curtain
        self.disp.step(dt, releases)

    def _check_terminal(self, VP):
        if self.disp.cat1():
            self.cat_flags.add("CAT-1")
        if self.disp.cat2():
            self.cat_flags.add("CAT-2")
        if self.disp.cat5():
            self.cat_flags.add("CAT-5")
        if self.disp.maj4():
            self.maj_flags.add("MAJ-4")
        # HACCP
        if self.g("T_milk") > self.cfg.milk_T_haccp:
            self.maj_flags.add("MAJ-3")
        for r in self.cfg.rooms:
            if self.g(f"Tair:{r.tag}") > r.T_alarm_hi:
                self.maj_flags.add("MAJ-3")

    def log(self, msg: str):
        self.events.append((round(self.t, 2), msg))

    # ------------------------------------------------------------------
    # SCADA output tags
    # ------------------------------------------------------------------

    def tags(self) -> dict:
        VP = self.vessel_pressures(self.y)
        aux = self._aux
        t = {
            "TIME_H": round(self.t / 3600.0, 4),
            "P_SUC_LP": VP["VE-LP"]["P"] / 1e5,
            "P_SUC_IP": VP["VE-IP"]["P"] / 1e5,
            "P_COND": VP["VE-HP"]["P"] / 1e5,
            "T_EVAP_LP": VP["VE-LP"]["T"] - 273.15,
            "T_EVAP_IP": VP["VE-IP"]["T"] - 273.15,
            "T_COND": aux.get("T_cond", 0.0) - 273.15,
            "LEVEL_VE_LP": VP["VE-LP"]["level"] * 100.0,
            "LEVEL_VE_IP": VP["VE-IP"]["level"] * 100.0,
            "LEVEL_VE_HP": VP["VE-HP"]["level"] * 100.0,
            "T_MILK": self.g("T_milk") - 273.15,
            "T_ICEWATER": self.g("T_icewater") - 273.15,
            "M_ICE_T": self.g("m_ice") / 1000.0,
            "POWER_KW": aux.get("W_total", 0.0) / 1000.0,
            "Q_REJ_KW": aux.get("Q_rej", 0.0) / 1000.0,
            "NH3_MACHINEROOM_PPM": self.disp.zones["MACHINE_ROOM"].ppm_indicated,
            "NH3_HALL_PPM": self.disp.zones["HALL"].ppm_indicated,
            "NH3_RELEASED_KG": self.disp.m_released_total,
            "ESD": int(self.esd_active),
        }
        for r in self.cfg.rooms:
            t[f"T_ROOM_{r.tag}"] = self.g(f"Tair:{r.tag}") - 273.15
        for cc in self.cfg.compressors:
            cs = self.comp[cc.tag]
            t[f"{cc.tag}_RUN"] = int(cs.running and not cs.tripped)
            t[f"{cc.tag}_SLIDE"] = self.g(f"slide:{cc.tag}") * 100.0
            t[f"{cc.tag}_TDIS"] = self.g(f"Tdis:{cc.tag}") - 273.15
            t[f"{cc.tag}_TOIL"] = self.g(f"Toil:{cc.tag}") - 273.15
            t[f"{cc.tag}_KW"] = cs.W_el / 1000.0
        for e in self.cfg.evaporators:
            es = self.evap[e.tag]
            t[f"{e.tag}_MODE"] = MODE_NAMES[es.mode]
            t[f"{e.tag}_P"] = self.g(f"P:{e.tag}") / 1e5
            t[f"{e.tag}_TMETAL"] = self.g(f"Tm:{e.tag}") - 273.15
            t[f"{e.tag}_FROST"] = self.g(f"frost:{e.tag}")
        return t

    def summary(self) -> dict:
        return {
            "t_h": self.t / 3600.0,
            "CAT": sorted(self.cat_flags),
            "MAJ": sorted(self.maj_flags),
            "released_kg": round(self.disp.m_released_total, 2),
            "prv_kg": round(self.prv_release_total, 2),
            "fenceline_peak_ppm": round(self.disp.fenceline_peak_ppm, 1),
            "energy_kwh": round(self.energy_kwh, 1),
            "ruptured": [s.tag for s in self.segments.values() if s.ruptured],
            "shock_events": sum(e.shock_events for e in self.evap.values()),
            "operators": {k: {"dose": round(o.dose_ppm_min, 1),
                              "peak_ppm": round(o.peak_ppm, 1),
                              "down": o.incapacitated}
                          for k, o in self.disp.operators.items()},
            "events": self.events[-25:],
        }
