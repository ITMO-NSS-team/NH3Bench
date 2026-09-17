"""
Hydraulic shock and pipe integrity.

The mechanism modelled here is NOT the classical water hammer from
closing a valve but condensation-induced water hammer -- that is what
destroyed the pipework at Millard Refrigerated Services in 2010.

The chain:
  1. An evaporator coil is in defrost: filled with hot gas at 8...11
     bar, the metal warmed to +20...+30 C.
  2. The liquid feed valve opens and -40 C ammonia enters the coil.
  3. The cold liquid causes runaway condensation of the vapour.
  4. The vapour volume collapses and a low-pressure void appears.
  5. The liquid column accelerates into the void and is stopped by a
     dead end or a bend.
  6. Joukowsky pressure surge: dP = rho * a * dv.

Wave processes have a characteristic time of milliseconds, so they are
NOT integrated together with the slow thermal dynamics (dt = 0.25...0.5
s) but computed algebraically as an event inside a step. This split into
two time scales is deliberate -- see the "Numerical scheme" section of
the README.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from . import props as pr


# Wave speed in a steel pipe with liquid ammonia (the Korteweg formula): a =
# sqrt(K/rho) / sqrt(1 + (K*D)/(E*e)), E = 2.1e11 Pa. K is the ADIABATIC bulk
# modulus K_s = rho*a_sound^2, taken from the equation of state through
# props.K_liq(P): 1.6...2.2 GPa over the working range. The previous constant
# of 1.03 GPa was the isothermal modulus (it coincides with K_T at -10 C) and
# underestimated rho*a by 16...37 % -- found by validation against CoolProp
# (docs/VALIDATION.md, V1). K is now passed explicitly so that the isothermal
# value cannot come back as a default.
def wave_speed(D: float, wall: float, rho: float,
               K: float, E: float = 2.1e11) -> float:
    return (K / rho) ** 0.5 / (1.0 + (K * D) / (E * wall)) ** 0.5


def hoop_stress(P: float, D: float, wall: float) -> float:
    """Hoop stress by Barlow's formula (thin-walled pipe)."""
    return P * D / (2.0 * wall)


@dataclass
class PipeSegment:
    tag: str
    D: float
    L: float
    wall: float
    sigma_y: float = 235e6
    burst_factor: float = 2.4      # sigma_burst / sigma_y for 09G2S steel
    dynamic_derate: float = 0.55   # strength reduction under impact loading
    wall_loss: float = 0.0         # fraction of wall thinning from corrosion (set by a fault)
    fatigue: float = 0.0           # accumulated damage, 1.0 = rupture
    cycles: int = 0                # number of recorded loading cycles
    last_cycle_t: float = -1e9
    ruptured: bool = False
    P_peak: float = 0.0            # Pa, maximum over the run
    dPdt_peak: float = 0.0         # Pa/s, maximum over the run

    @property
    def wall_eff(self) -> float:
        return max(self.wall * (1.0 - self.wall_loss), 1e-4)

    @property
    def P_burst(self) -> float:
        """Static burst pressure (quasi-static loading)."""
        return 2.0 * self.sigma_y * self.burst_factor * self.wall_eff / self.D

    @property
    def P_burst_dynamic(self) -> float:
        """
        Burst pressure under impact loading.

        The reducing coefficient accounts for stress concentration at supports
        and welds and for dynamic amplification of the response; the physically
        meaningful band is 0.3...0.7. The value 0.55 was recalibrated together
        with the move to the adiabatic K_s in wave_speed (the peaks grew by a
        factor of about 1.3): the known rupture cases are still reproduced with
        margin, while routine defrost transients accumulate no fatigue. The
        earlier 0.45 was calibrated against peaks that the isothermal modulus
        had underestimated. The parameter is subject to expert acceptance
        (docs/VALIDATION.md).
        """
        return self.P_burst * self.dynamic_derate

    @property
    def area(self) -> float:
        return 3.141592653589793 * self.D ** 2 / 4.0


def joukowsky_spike(seg: PipeSegment, rho_liq: float, dv: float,
                    K: float) -> float:
    """Joukowsky pressure surge for a change of liquid velocity by dv."""
    a = wave_speed(seg.D, seg.wall_eff, rho_liq, K)
    return rho_liq * a * abs(dv)


# Conditions for condensation-induced shock.
SHOCK_PRESSURE_RATIO = 1.5      # P_coil / P_suction
SHOCK_METAL_SUPERHEAT = 20.0    # K, metal superheat above the suction temperature
SHOCK_MIN_SUBCOOL = 15.0        # K, subcooling of the incoming liquid


def condensation_shock(seg: PipeSegment,
                       P_coil: float, P_feed: float,
                       T_metal: float, m_liq_in_rate: float,
                       dt: float,
                       header: "PipeSegment" = None,
                       t_now: float = 0.0) -> dict:
    """
    Condensation-induced shock when cold liquid enters a hot coil.

    The mechanism (Wylie & Streeter; IIAR Bulletin 116): cold liquid
    entering a volume of hot vapour causes runaway condensation. The vapour
    cavity collapses and the liquid column accelerates under the FULL
    pressure difference between the coil and the suction line. The column's
    velocity is bounded by the Bernoulli relation v = sqrt(2*dP/rho), and
    the subsequent stop against a dead end or a bend gives the Joukowsky
    surge dP = rho*a*v.

    It matters that the driving force is the pressure difference and NOT the
    thermal balance of the liquid flow: the latter gives velocities of about
    0.5 m/s and shocks of a few bar, which contradicts field data
    (100...700 bar).

    The header argument, when given, allows the shock in the common suction
    header to be estimated as well: the velocity there scales inversely with
    the cross-sectional area.
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
    # Adiabatic bulk modulus of the liquid at the feed temperature -- the
    # column is accelerated by exactly that cold liquid from the feed side.
    K = pr.K_liq(P_feed)
    dP_drive = P_coil - P_feed
    v = (2.0 * dP_drive / rho) ** 0.5

    # Fraction of the cross-section taken by the accelerated column. Slug flow
    # does not fill the pipe completely; the coefficient is calibrated against
    # field data on ruptures.
    slug_factor = 0.85

    worst = None
    for s in ([seg] if header is None else [seg, header]):
        v_s = v * slug_factor
        if s is not header and header is not None:
            pass
        elif s is header:
            v_s = v * slug_factor * (seg.area / s.area)
        dP_j = joukowsky_spike(s, rho, v_s, K)
        P_peak = P_coil + dP_j
        a = wave_speed(s.D, s.wall_eff, rho, K)
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
        # Low-cycle fatigue accumulates PER EVENT rather than per integration
        # step: one transient is one loading cycle.
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
    """Pipe segments from the plant configuration."""
    segs = {}
    for ev in cfg.evaporators:
        segs[ev.tag] = PipeSegment(
            tag=f"PIPE-{ev.tag}", D=ev.pipe_D, L=ev.pipe_L,
            wall=ev.pipe_wall, sigma_y=ev.pipe_sigma_y)
    segs["HEADER-LP"] = PipeSegment(
        tag="PIPE-HEADER-LP", D=cfg.suction_header_D, L=cfg.suction_header_L,
        wall=cfg.suction_header_wall, sigma_y=cfg.suction_header_sigma_y)
    return segs
