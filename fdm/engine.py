#!/usr/bin/env python3
"""Engine model: a two-spool, separate-flow turbofan cycle for the AE 3007 family.

No thrust or fuel-flow map of the Global Hawk's AE 3007H is public. This is the textbook performance analysis of a
turbofan with separate exhausts (Mattingly, Elements of Propulsion, chapter 8): a reference point fixes the cycle,
and away from it both turbines stay choked, so their temperature and pressure ratios hold and the spools' power
balances give the fan and compressor pressure ratios, the bypass ratio and the mass flow. Component efficiencies
are fixed. It is not a component-map model: it is poor at idle and knows nothing of Reynolds number effects.

The family is treated as one engine at different ratings. Its reference point is fitted to the row of the
highest-rated variant, the AE 3007A2, in the ICAO Engine Emissions Databank (sea level, static, takeoff: thrust,
fuel flow, pressure ratio, bypass ratio); the Citation X's AE 3007C1 is the check. fdm/data/README.md, "Engine",
has the sources, the choices, the fits and the checks.

    python3 fdm/engine.py            validation build (AE 3007C1), then the AE 3007H; writes fdm/data/engine.json
"""
import json
import os
import sys

import numpy as np
from scipy.optimize import brentq, fsolve

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'data', 'engine.json')

GC, CPC = 1.4, 1004.5            # cold stream
GT, CPT = 1.33, 1156.0           # hot stream
RC, RT = CPC * (GC - 1) / GC, CPT * (GT - 1) / GT
HPR = 42.8e6                     # J/kg, kerosene
ETA_B, PI_B = 0.995, 0.96        # burner
PI_D, PI_N, PI_FN = 0.98, 0.99, 0.99
ETA_M = 0.99
E_C, E_F, E_T = 0.90, 0.90, 0.90  # polytropic efficiencies: typical of the engine's generation, not published
LBF, LBH, FT, KT = 4.4482216, 0.45359237 / 3600.0, 0.3048, 0.514444

# ICAO Engine Emissions Databank rows (through TU Delft's OpenAP): thrust N, bypass ratio, pressure ratio,
# fuel flow kg/s at 100, 85, 30 and 7 % thrust
ICAO = {
    'AE3007C1': dict(thrust=31460.0, bpr=5.10, opr=16.58, ff=(0.3222, 0.2689, 0.0991, 0.0418)),
    'AE3007A2': dict(thrust=42230.0, bpr=4.79, opr=20.20, ff=(0.4660, 0.3880, 0.1380, 0.0550)),
}
# Ghazi (PhD, ETS Montreal), table 2.1: Citation X, one AE 3007C1 at maximum climb, ISA
GHAZI = [dict(alt=1500, mach=0.234, fn=4475, wf=2376, n1=82.31), dict(alt=2274, mach=0.236, fn=4430, wf=2342, n1=82.63),
         dict(alt=3051, mach=0.241, fn=4363, wf=2307, n1=82.93), dict(alt=3798, mach=0.243, fn=4315, wf=2274, n1=83.22),
         dict(alt=43835, mach=0.559, fn=1335, wf=828.5, n1=92.70), dict(alt=44012, mach=0.562, fn=1320, wf=821.6, n1=92.64),
         dict(alt=45000, mach=0.564, fn=1308, wf=814.2, n1=92.59)]
JET_VELOCITY_RATIO = 0.8         # bypass over core jet speed at the reference point: usual design practice (a choice)
# Air flow at the A2's takeoff: the 38.5 in fan (hub at a third of the tip radius) with Mach 0.55 at its face.
# An estimate; no air flow figure is in our sources.
FAN_FLOW = 129.0                 # kg/s
FLAT_RATING_LBF = 7500.0         # NASA: "flat rated at 7500 lbs thrust at sea level"


def isa(alt_ft, dT=0.0):
    """Temperature (K) and pressure (Pa) of the standard atmosphere, with a temperature offset."""
    h = alt_ft * FT
    if h < 11000:
        T = 288.15 - 0.0065 * h
        p = 101325.0 * (T / 288.15) ** 5.25588
    elif h < 20000:
        T = 216.65
        p = 22632.06 * np.exp(-9.80665 * (h - 11000) / (287.05287 * 216.65))
    else:
        T = 216.65 + 0.001 * (h - 20000)
        p = 5474.889 * (T / 216.65) ** (-34.16320)
    return T + dT, p


def mfp(M, g):
    return M * (1 + (g - 1) / 2 * M * M) ** (-(g + 1) / (2 * (g - 1)))


def nozzle(pt_p0, Tt, g, R):
    """A convergent nozzle: exit Mach, speed, and the pressure-thrust term R T (1 - p0/p) / V."""
    crit = ((g + 1) / 2) ** (g / (g - 1))
    if pt_p0 >= crit:
        M, p_p0 = 1.0, pt_p0 / crit
    else:
        M, p_p0 = np.sqrt(max(2 / (g - 1) * (pt_p0 ** ((g - 1) / g) - 1), 0.0)), 1.0
    T = Tt / (1 + (g - 1) / 2 * M * M)
    V = M * np.sqrt(g * R * T)
    pressure = R * T / V * (1 - 1 / p_p0) if V > 1e-6 else 0.0
    return M, V, pressure


class Turbofan:
    """One engine. reference(): fix the cycle at a point. run(): any other flight condition and throttle."""

    def reference(self, thrust, bpr, opr, pi_f, Tt4, M0=0.0, alt=0.0):
        T0, P0 = isa(alt)
        r = dict(M0=M0, T0=T0, P0=P0, alpha=bpr, pi_f=pi_f, pi_ch=opr / pi_f, Tt4=Tt4)
        r['tau_r'] = 1 + (GC - 1) / 2 * M0 * M0
        r['pi_r'] = r['tau_r'] ** (GC / (GC - 1))
        r['tau_l'] = CPT * Tt4 / (CPC * T0)
        r['tau_f'] = pi_f ** ((GC - 1) / (GC * E_F))
        r['tau_ch'] = r['pi_ch'] ** ((GC - 1) / (GC * E_C))
        f = (r['tau_l'] - r['tau_r'] * r['tau_f'] * r['tau_ch']) / (ETA_B * HPR / (CPC * T0) - r['tau_l'])
        r['tau_th'] = 1 - r['tau_r'] * r['tau_f'] * (r['tau_ch'] - 1) / (ETA_M * (1 + f) * r['tau_l'])
        r['pi_th'] = r['tau_th'] ** (GT / ((GT - 1) * E_T))
        r['tau_tl'] = 1 - r['tau_r'] * (r['tau_f'] - 1) * (1 + bpr) / (ETA_M * (1 + f) * r['tau_l'] * r['tau_th'])
        r['pi_tl'] = r['tau_tl'] ** (GT / ((GT - 1) * E_T))
        self.ref = r
        out = self._thrust(r, f)
        r['M19'] = out['M19']
        r['mdot'] = thrust / out['specific_thrust']          # total air flow, kg/s
        r['mdot_core'] = r['mdot'] / (1 + bpr)
        out['thrust'], out['fuel'] = thrust, f * r['mdot_core']
        return out

    def _thrust(self, s, f):
        """Specific thrust (per unit of total air flow) and the nozzle states for a cycle state s."""
        V0 = s['M0'] * np.sqrt(GC * RC * s['T0'])
        r = self.ref
        core_p = s['pi_r'] * PI_D * s['pi_f'] * s['pi_ch'] * PI_B * r['pi_th'] * r['pi_tl'] * PI_N
        M9, V9, pt9 = nozzle(core_p, s['Tt4'] * r['tau_th'] * r['tau_tl'], GT, RT)
        byp_p = s['pi_r'] * PI_D * s['pi_f'] * PI_FN
        M19, V19, pt19 = nozzle(byp_p, s['T0'] * s['tau_r'] * s['tau_f'], GC, RC)
        a = s['alpha']
        core = (1 + f) * (V9 + pt9) - V0
        byp = V19 + pt19 - V0
        return dict(specific_thrust=(core + a * byp) / (1 + a), V9=V9, V19=V19, M9=M9, M19=M19)

    def run(self, alt, M0, Tt4, dT=0.0):
        """The engine at a flight condition and turbine entry temperature: thrust N, fuel kg/s and the cycle."""
        r = self.ref
        T0, P0 = isa(alt, dT)
        s = dict(M0=M0, T0=T0, P0=P0, Tt4=Tt4)
        s['tau_r'] = 1 + (GC - 1) / 2 * M0 * M0
        s['pi_r'] = s['tau_r'] ** (GC / (GC - 1))
        s['tau_l'] = CPT * Tt4 / (CPC * T0)
        alpha, tau_f = r['alpha'], r['tau_f']
        for _ in range(200):
            tau_ch = 1 + (s['tau_l'] / (s['tau_r'] * tau_f)) / (r['tau_l'] / (r['tau_r'] * r['tau_f'])) * (r['tau_ch'] - 1)
            pi_ch = tau_ch ** (GC * E_C / (GC - 1))
            pi_f = tau_f ** (GC * E_F / (GC - 1))
            M19 = nozzle(s['pi_r'] * PI_D * pi_f * PI_FN, 1.0, GC, RC)[0]
            # flows: the core through the choked turbine, the bypass through its nozzle
            core = (P0 * s['pi_r'] * pi_f * pi_ch) / (r['P0'] * r['pi_r'] * r['pi_f'] * r['pi_ch']) * np.sqrt(r['Tt4'] / Tt4)
            byp = (P0 * s['pi_r'] * pi_f) / (r['P0'] * r['pi_r'] * r['pi_f']) * \
                np.sqrt((r['T0'] * r['tau_r'] * r['tau_f']) / (T0 * s['tau_r'] * tau_f)) * mfp(max(M19, 1e-3), GC) / mfp(r['M19'], GC)
            alpha_new = r['alpha'] * byp / core
            tau_f_new = 1 + (r['tau_f'] - 1) * (s['tau_l'] / s['tau_r']) / (r['tau_l'] / r['tau_r']) * (1 + r['alpha']) / (1 + alpha_new)
            if abs(alpha_new - alpha) < 1e-9 and abs(tau_f_new - tau_f) < 1e-10:
                break
            alpha, tau_f = 0.5 * (alpha + alpha_new), 0.5 * (tau_f + tau_f_new)
        s.update(alpha=alpha, tau_f=tau_f, pi_f=pi_f, tau_ch=tau_ch, pi_ch=pi_ch)
        f = (s['tau_l'] - s['tau_r'] * tau_f * tau_ch) / (ETA_B * HPR / (CPC * T0) - s['tau_l'])
        out = self._thrust(s, f)
        mcore = r['mdot_core'] * core
        mdot = mcore * (1 + alpha)
        fan_speed = np.sqrt(max(tau_f - 1, 0.0) / (r['tau_f'] - 1))
        k = self.fuel_factor(alt)
        out.update(thrust=out['specific_thrust'] * mdot, fuel=f * mcore * k, fuel_cycle=f * mcore, fuel_factor=k, mdot=mdot, bpr=alpha, opr=pi_f * pi_ch, pi_f=pi_f,
                   Tt4=Tt4, f=f, fan_speed=np.sqrt((tau_f - 1) / (r['tau_f'] - 1)),      # corrected, over the reference
                   corrected_flow=mdot * np.sqrt(T0 * s['tau_r'] / 288.15) / (P0 * s['pi_r'] / 101325.0) / r['mdot'])
        return out

    # Two fits lie on top of the cycle's fuel flow:
    #   installation  the engine in an aircraft (bleed, power offtake, inlet) against the bare engine of the ICAO
    #                 test: a factor against altitude from Ghazi's Citation X table, held above 45,000 ft.
    #                 1 until validation() sets it.
    #   part power    the cycle keeps its turbines choked and its efficiencies fixed, which fails when throttled
    #                 well back (at 30 % thrust it is 40 to 60 % low on fuel). Below X_CYCLE of the thrust at the
    #                 reference fan speed the fuel flow follows the shape of the ICAO points instead: fuel over
    #                 fuel at the reference fan speed, against thrust over thrust there.
    installation = None
    X_CYCLE, X_ICAO = 0.60, 0.30          # the cycle alone above the first, the ICAO shape alone below the second
    PHI_X = (0.0, 0.07, 0.30, 0.85, 1.0)  # thrust fraction: the ICAO points of the AE 3007A2 ...
    PHI = (0.094, 0.118, 0.296, 0.833, 1.0)  # ... and its fuel-flow fraction (0.094 at no thrust: the line carried on)

    def fuel_factor(self, alt):
        return 1.0 if self.installation is None else float(np.interp(alt, self.installation[0], self.installation[1]))

    def at_thrust(self, alt, M0, thrust, dT=0.0):
        """The engine throttled to a thrust (N)."""
        ref = self.at_fan_speed(alt, M0, 1.0, dT)
        x = thrust / ref['thrust']
        phi = ref['fuel'] * float(np.interp(x, self.PHI_X, self.PHI))
        if x <= self.X_ICAO:
            return dict(thrust=thrust, fuel=phi, x=x, fan_speed=np.nan, opr=np.nan, bpr=np.nan, Tt4=np.nan, law='ICAO shape')
        T0 = isa(alt, dT)[0]
        lo = 1.6 * T0 * (1 + 0.2 * M0 * M0)
        g = lambda t: self.run(alt, M0, t, dT)['thrust'] - thrust
        o = self.run(alt, M0, brentq(g, lo, 2200.0, xtol=1e-4), dT)
        o['x'], o['law'] = x, 'cycle'
        if x < self.X_CYCLE:
            w = (x - self.X_ICAO) / (self.X_CYCLE - self.X_ICAO)
            o['fuel'], o['law'] = w * o['fuel'] + (1 - w) * phi, 'blend'
        return o

    def at_fan_speed(self, alt, M0, speed, dT=0.0):
        T0 = isa(alt, dT)[0]
        g = lambda t: self.run(alt, M0, t, dT)['fan_speed'] - speed
        lo = 1.6 * T0 * (1 + 0.2 * M0 * M0)
        if g(lo) > 0:                                       # windmilling faster than that already
            return self.run(alt, M0, lo, dT)
        return self.run(alt, M0, brentq(g, lo, 2200.0, xtol=1e-4), dT)

    def maximum(self, alt, M0, dT=0.0):
        """Maximum thrust: the lowest of the fan corrected-speed limit, the temperature limit and the flat rating."""
        cands = [self.at_fan_speed(alt, M0, self.fan_speed_max, dT)]
        if cands[0]['Tt4'] > self.Tt4_max:
            cands = [self.run(alt, M0, self.Tt4_max, dT)]
            cands[0]['limit'] = 'temperature'
        else:
            cands[0]['limit'] = 'fan speed'
        out = cands[0]
        if self.rating and out['thrust'] > self.rating:
            out = self.at_thrust(alt, M0, self.rating, dT)
            out['limit'] = 'rating'
        return out

    def idle(self, alt, M0, dT=0.0):
        """Idle: 7 % of the thrust at the reference fan speed, as the ICAO idle point. A class estimate."""
        return self.at_thrust(alt, M0, 0.07 * self.at_fan_speed(alt, M0, 1.0, dT)['thrust'], dT)


def build():
    """The AE 3007 as one piece of hardware, its reference point fitted to the ICAO takeoff row of the AE 3007A2.

    The A2 is the highest-rated member of the family; the others are treated as the same engine at lower ratings
    (their ICAO rows are then checks). Three unknowns, three conditions:
      fan pressure ratio, turbine entry temperature   so that the air flow is FAN_FLOW and the bypass jet runs at
                                                      JET_VELOCITY_RATIO of the core jet
      the level of the component efficiencies         so that the fuel flow is the ICAO figure
    """
    global E_C, E_F, E_T
    row = ICAO['AE3007A2']
    e = Turbofan()

    def tt4_for(pf):
        def g(t):
            with np.errstate(all='ignore'):
                o = e.reference(row['thrust'], row['bpr'], row['opr'], pf, t)
                v = o['V19'] / o['V9'] - JET_VELOCITY_RATIO if o['V9'] > 1.0 else np.nan
            return v
        ts = np.linspace(1000.0, 2100.0, 111)               # the low end has no core jet at all: find the bracket
        gs = [g(t) for t in ts]
        for t0, t1, g0, g1 in zip(ts[:-1], ts[1:], gs[:-1], gs[1:]):
            if np.isfinite(g0) and np.isfinite(g1) and g0 * g1 < 0:
                return brentq(g, t0, t1)
        raise ValueError('no turbine entry temperature gives the jet velocity ratio at fan pressure ratio %.2f' % pf)

    def fit(eff):
        global E_C, E_F, E_T
        E_C = E_F = E_T = eff
        pf = brentq(lambda x: (e.reference(row['thrust'], row['bpr'], row['opr'], x, tt4_for(x)), e.ref['mdot'])[1] - FAN_FLOW, 1.45, 2.1)
        return pf, tt4_for(pf)

    def fuel_miss(eff):
        pf, t = fit(eff)
        return e.reference(row['thrust'], row['bpr'], row['opr'], pf, t)['fuel'] / row['ff'][0] - 1
    eff = brentq(fuel_miss, 0.86, 0.95)
    pf, t = fit(eff)
    o = e.reference(row['thrust'], row['bpr'], row['opr'], pf, t)
    e.name, e.icao, e.takeoff, e.efficiency = 'AE3007', row, o, eff
    e.Tt4_takeoff, e.Tt4_max, e.rating = t, t, None
    e.fan_speed_max = 1.0
    return e


def validation():
    """The family model against every ICAO row and Ghazi's maximum-climb table for the AE 3007C1."""
    e = build()
    rows = []
    r = e.ref
    print('AE 3007 reference (fitted to the ICAO takeoff row of the A2): fan pressure ratio %.3f, turbine entry %.0f K, '
          'air flow %.1f kg/s (%.0f lb/s), polytropic efficiencies %.3f, jet speeds %.0f and %.0f m/s' % (
              r['pi_f'], r['Tt4'], r['mdot'], r['mdot'] / 0.45359, e.efficiency, e.takeoff['V9'], e.takeoff['V19']))
    c1 = ICAO['AE3007C1']
    o = e.at_thrust(0, 0, c1['thrust'])
    rows.append(('C1a', 'C1 takeoff as a rating: fuel flow, kg/s', o['fuel'], c1['ff'][0], 5.0, 'predicted'))
    rows.append(('C1b', 'C1 takeoff as a rating: pressure ratio', o['opr'], c1['opr'], 5.0, 'predicted'))
    rows.append(('C1c', 'C1 takeoff as a rating: bypass ratio', o['bpr'], c1['bpr'], 5.0, 'predicted'))
    for frac, k, lim, tag in ((0.85, 1, 5.0, 'V1'), (0.30, 2, 15.0, 'V2'), (0.07, 3, None, 'V3')):
        o = e.at_thrust(0, 0, frac * c1['thrust'])
        rows.append((tag, 'C1 fuel flow at ICAO %.0f %% thrust, kg/s' % (100 * frac), o['fuel'], c1['ff'][k], lim, 'predicted'))
    a2 = ICAO['AE3007A2']
    for frac, k, lim, tag in ((0.85, 1, 5.0, 'A2a'), (0.30, 2, 15.0, 'A2b'), (0.07, 3, None, 'A2c')):
        o = e.at_thrust(0, 0, frac * a2['thrust'])
        rows.append((tag, 'A2 fuel flow at ICAO %.0f %% thrust, kg/s' % (100 * frac), o['fuel'], a2['ff'][k], lim, 'predicted'))
    lo, hi = GHAZI[0], GHAZI[-1]
    olo = e.at_thrust(lo['alt'], lo['mach'], lo['fn'] * LBF)
    ohi = e.at_thrust(hi['alt'], hi['mach'], hi['fn'] * LBF)
    rows.append(('V4', 'TSFC at 1,500 ft, M 0.234, lb/h/lbf', olo['fuel'] / LBH / lo['fn'], lo['wf'] / lo['fn'], 8.0, 'predicted'))
    rows.append(('V5', 'TSFC at 45,000 ft, M 0.564, lb/h/lbf', ohi['fuel'] / LBH / hi['fn'], hi['wf'] / hi['fn'], 8.0, 'predicted'))
    th = lambda g: (isa(g['alt'])[0] * (1 + 0.2 * g['mach'] ** 2)) / 288.15
    n1 = (hi['n1'] / np.sqrt(th(hi))) / (lo['n1'] / np.sqrt(th(lo)))
    rows.append(('V7', 'fan corrected speed, 45,000 ft over 1,500 ft', ohi['fan_speed'] / olo['fan_speed'], n1, 5.0, 'predicted'))
    e.fan_speed_max = ohi['fan_speed']                      # V6: the fit
    mid = GHAZI[4]
    om = e.at_fan_speed(mid['alt'], mid['mach'], e.fan_speed_max)
    rows.append(('V6b', 'thrust at 43,835 ft at the fitted limit, lbf', om['thrust'] / LBF, mid['fn'], 2.0, 'after the fit'))
    # the installation fit, then the fuel flow at Ghazi's other rows
    e.installation = ([lo['alt'], hi['alt']], [lo['wf'] * LBH / olo['fuel'], hi['wf'] * LBH / ohi['fuel']])
    after = []
    for gz in GHAZI[1:-1]:
        o = e.at_thrust(gz['alt'], gz['mach'], gz['fn'] * LBF)
        after.append(('', 'fuel flow at %d ft, M %.3f, lb/h' % (gz['alt'], gz['mach']), o['fuel'] / LBH, gz['wf'], None, 'after the fit'))
    e.after = after
    report(rows)
    print('  installation fit: fuel flow factor %.3f at %d ft, %.3f at %d ft; then:' % (
        e.installation[1][0], e.installation[0][0], e.installation[1][1], e.installation[0][1]))
    report(e.after)
    print('  V6 (a fit): maximum climb at altitude is the fan corrected speed %.3f of the A2 takeoff; there OPR %.1f, '
          'bypass ratio %.2f, turbine entry %.0f K (A2 takeoff %.0f K)' % (e.fan_speed_max, ohi['opr'], ohi['bpr'],
                                                                         ohi['Tt4'], e.Tt4_takeoff))
    print('  at 1,500 ft Ghazi\'s climb thrust needs fan speed %.3f, turbine entry %.0f K: below both limits, a rating'
          % (olo['fan_speed'], olo['Tt4']))
    return e, rows, dict(climb_45000=ohi, climb_1500=olo)


def report(rows):
    print('  %-4s %-48s %9s %9s %7s %6s' % ('', 'check', 'model', 'source', 'err %', 'limit'))
    for tag, name, val, ref, lim, kind in rows:
        err = 100 * (val - ref) / ref
        res = '' if lim is None else ('pass' if abs(err) <= lim else 'MISS')
        print('  %-4s %-48s %9.4g %9.4g %+7.1f %6s  %s  (%s)' % (tag, name, val, ref, err, '-' if lim is None else '%.0f' % lim, res, kind))


def global_hawk(e):
    """The AE 3007H: the same hardware and limits, with NASA's flat rating."""
    e.name = 'AE3007H'
    e.rating = FLAT_RATING_LBF * LBF
    return e


def tables(e):
    """The engine as tables for the flight model.

    max_thrust_lbf[dT][altitude][mach]     maximum thrust, at temperature offsets from standard
    idle_thrust_lbf[altitude][mach]        idle, standard day
    fuel_lbh[altitude][mach][fraction]     fuel flow at a fraction of the standard-day maximum thrust, standard day;
                                           off standard the flight model scales it with the square root of temperature
    """
    alts = list(range(0, 70001, 5000))
    machs = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    fracs = [0.0, 0.07, 0.2, 0.4, 0.6, 0.8, 1.0]
    dts = [-20.0, 0.0, 20.0]
    t = dict(altitude_ft=alts, mach=machs, thrust_fraction=fracs, delta_T_K=dts, max_thrust_lbf=[], limit=[],
             idle_thrust_lbf=[], fuel_lbh=[], opr_at_max=[])
    for dt in dts:
        t['max_thrust_lbf'].append([[round(e.maximum(a, m, dt)['thrust'] / LBF, 1) for m in machs] for a in alts])
    for a in alts:
        lim, opr, idle, fuel = [], [], [], []
        for m in machs:
            o = e.maximum(a, m)
            lim.append(o['limit'])
            opr.append(round(o['opr'], 2))
            idle.append(round(e.idle(a, m)['thrust'] / LBF, 1))
            fuel.append([round(e.at_thrust(a, m, fr * o['thrust'])['fuel'] / LBH, 1) for fr in fracs])
        t['limit'].append(lim)
        t['opr_at_max'].append(opr)
        t['idle_thrust_lbf'].append(idle)
        t['fuel_lbh'].append(fuel)
    return t


def main():
    c1, vrows, _ = validation()
    h = global_hawk(c1)
    r = h.ref
    print('\nAE 3007H: the same engine, flat rated at %.0f lbf' % FLAT_RATING_LBF)
    rating, h.rating = h.rating, None
    sl = h.maximum(0, 0)
    h.rating = rating
    print('  sea level static without the rating: %.0f lbf (%s limit)' % (sl['thrust'] / LBF, sl['limit']))
    hrows = []
    top = h.maximum(60000, 0.6)
    hrows.append(('H1', 'OPR at the limit, 60,000 ft, M 0.6', top['opr'], 23.0, 10.0, 'predicted'))
    report(hrows)
    print('  H2 window: fuel flow at 60,000 ft, M 0.6, 15,000 lb:')
    for ld in (25, 30, 35):
        o = h.at_thrust(60000, 0.6, 15000.0 / ld * LBF)
        print('     L/D %d: thrust %.0f lbf, fuel %.0f lb/h, TSFC %.3f (window 300 to 600 lb/h); maximum there %.0f lbf'
              % (ld, o['thrust'] / LBF, o['fuel'] / LBH, o['fuel'] / LBH / (o['thrust'] / LBF), top['thrust'] / LBF))
    print('  maximum thrust, lbf (limit):')
    for a in (0, 10000, 20000, 30000, 40000, 50000, 55000, 60000, 65000):
        m = {0: 0.0, 10000: 0.27, 20000: 0.33, 30000: 0.42, 40000: 0.50}.get(a, 0.6)
        o = h.maximum(a, m)
        print('     %6d ft M %.2f: %6.0f lbf, %5.0f lb/h, TSFC %.3f, OPR %.1f, BPR %.2f, Tt4 %.0f K (%s)' % (
            a, m, o['thrust'] / LBF, o['fuel'] / LBH, o['fuel'] / LBH / (o['thrust'] / LBF), o['opr'], o['bpr'], o['Tt4'], o['limit']))
    t = tables(h)
    json.dump(dict(engine='AE 3007H (F137-RR-100), cycle model', reference=dict(icao_row='AE3007A2', fan_pressure_ratio=round(r['pi_f'], 4),
                   turbine_entry_K=round(r['Tt4'], 1), air_flow_kg_s=round(r['mdot'], 2), bpr=r['alpha'], opr=round(r['pi_f'] * r['pi_ch'], 2)),
                   fuel_fits=dict(installation_altitude_ft=h.installation[0], installation_factor=np.round(h.installation[1], 4).tolist(),
                                  part_power_thrust_fraction=list(h.PHI_X), part_power_fuel_fraction=list(h.PHI),
                                  cycle_above=h.X_CYCLE, icao_shape_below=h.X_ICAO),
                   limits=dict(fan_speed_max=round(h.fan_speed_max, 4), idle_thrust_fraction=0.07,
                               turbine_entry_max_K=round(h.Tt4_max, 1), flat_rating_lbf=FLAT_RATING_LBF),
                   atmosphere='ISA', tables=t), open(OUT, 'w'), indent=1)
    print('wrote', os.path.relpath(OUT))


if __name__ == '__main__':
    main()
