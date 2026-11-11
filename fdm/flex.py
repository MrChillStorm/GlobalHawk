#!/usr/bin/env python3
"""The wing's bending: a beam model from stated assumptions, since no stiffness, deflection or frequency of the
Global Hawk's wing is public. Nothing here is checked against the aircraft.

    python3 fdm/flex.py            prints the model; writes fdm/data/flex.json

The half wing is a cantilever from the fuselage side. Its stiffness comes from assuming it is sized by strength:
at 1 g and maximum weight, with full wing tanks, the spar caps are at a strain STRAIN_1G over a box BOX_DEPTH of the
section's thickness deep, falling linearly to TIP_STRAIN of that at the tip (minimum gauge). Then

    curvature = bending moment / EI,   EI = design moment x (half the box depth) / strain

Loads: the lift along the span from the strip model, less the load factor times the weight of the wing's structure
and of its fuel. The deflection is linear in these, so three numbers describe the tip: feet per pound of lift, per
pound of structure and per pound of wing fuel (each times the load factor).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

G = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
M = json.load(open(os.path.join(HERE, 'data', 'mass.json')))
OUT = os.path.join(HERE, 'data', 'flex.json')
STRAIN_1G = 0.0030 / 2.5        # spar-cap strain at 1 g, maximum weight: 0.0030 at a limit load factor of 2.5. Assumptions
TIP_STRAIN = 0.40               # of that, at the tip
BOX_DEPTH = 0.85                # of the section's thickness
DAMPING = 0.15                  # of critical, structure and air together: an estimate
N = 400


def beam():
    import strips
    w = G['wing']
    half = w['span'] / 2
    y0 = G['fuselage']['max_width'] / 2
    y = np.linspace(y0, half, N)
    c = w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * y / half
    depth = BOX_DEPTH * w['tc'] * c
    strain = STRAIN_1G * (1 - (1 - TIP_STRAIN) * (y - y0) / (half - y0))
    # lift per foot of span for one pound of total lift (both wings), from the strip model at cruise
    ac = strips.Aircraft()
    sol = ac.solve(60000, 0.6, 2.0)
    yr = ac.y[ac.y > 0]
    lr = (sol['strips']['gamma'])[ac.y > 0]
    lift = np.interp(y, yr, lr)
    lift = lift / (2 * np.trapezoid(np.interp(np.linspace(0, half, 800), yr, lr), np.linspace(0, half, 800)))
    # weight per foot: structure in proportion to chord squared, fuel in the tanks' span (to 90 % of the semi-span)
    struct = c ** 2 / (2 * np.trapezoid(c ** 2, y))
    wing_struct = [i['weight'] for i in M['items'] if i['name'] == 'wing structure'][0]
    wing_fuel = sum(t['capacity'] for t in M['tanks'] if t['name'].startswith('wing'))
    fmask = y <= 0.9 * half
    fuel = np.where(fmask, c ** 2, 0.0)
    fuel = fuel / (2 * np.trapezoid(fuel, y))

    def moment(p):
        """Bending moment along the span for a load p per foot (up positive)."""
        m = np.zeros(N)
        for i in range(N):
            m[i] = np.trapezoid(p[i:] * (y[i:] - y[i]), y[i:])
        return m

    def deflect(m, EI):
        k = m / EI
        slope = np.concatenate([[0], np.cumsum(0.5 * (k[1:] + k[:-1]) * np.diff(y))])
        return np.concatenate([[0], np.cumsum(0.5 * (slope[1:] + slope[:-1]) * np.diff(y))]), slope
    w_max = M['published']['gross']
    design = moment(w_max * lift - wing_struct * struct - wing_fuel * fuel)
    EI = np.maximum(design, design[-20] * 0 + 1e-9) * (depth / 2) / strain
    EI[-3:] = EI[-4]                                          # the moment goes to nothing at the very tip
    EI = np.maximum(EI, 0.02 * EI[0])                         # a floor: minimum gauge
    unit = {k: deflect(moment(p), EI) for k, p in (('lift', lift), ('structure', -struct), ('fuel', -fuel))}
    return dict(y=y, c=c, EI=EI, unit=unit, lift=lift, struct=struct, fuel=fuel, wing_struct=wing_struct, wing_fuel=wing_fuel, y0=y0, half=half)


def shape(b, lift_lb, nz, wing_fuel_lb):
    """Deflection (ft) and slope along the span."""
    u = b['unit']
    d = lift_lb * u['lift'][0] + nz * (b['wing_struct'] * u['structure'][0] + wing_fuel_lb * u['fuel'][0])
    s = lift_lb * u['lift'][1] + nz * (b['wing_struct'] * u['structure'][1] + wing_fuel_lb * u['fuel'][1])
    return d, s


def frequency(b, wing_fuel_lb):
    """First bending frequency (Hz) by Rayleigh's quotient with the shape under lift."""
    wv, _ = b['unit']['lift']
    y = b['y']
    k = np.gradient(np.gradient(wv, y), y)
    mass = (b['wing_struct'] * b['struct'] + wing_fuel_lb * b['fuel']) / 32.174      # slug per foot
    om2 = np.trapezoid(b['EI'] * k ** 2, y) / np.trapezoid(mass * wv ** 2, y)
    return float(np.sqrt(om2) / (2 * np.pi))


def roll_due_to_sideslip(b):
    """Change of roll due to sideslip per foot of tip deflection, from the strip model with the bent shape."""
    import strips
    ac = strips.Aircraft()
    wv, sl = b['unit']['lift']
    out = []
    for mach, alt in ((0.20, 0.0), (0.45, 30000.0), (0.60, 60000.0)):
        base = ac.solve(alt, mach, 2.0, beta=2.0)['Cl'] - ac.solve(alt, mach, 2.0)['Cl']
        tip = 4.0
        ac.bend(b['y'], wv / wv[-1] * tip, sl / wv[-1] * tip)
        bent = ac.solve(alt, mach, 2.0, beta=2.0)['Cl'] - ac.solve(alt, mach, 2.0)['Cl']
        ac.bend(None, None, None)
        out.append(dict(mach=mach, rigid_per_deg=base / 2, bent_4ft_per_deg=bent / 2, per_ft_per_deg=(bent - base) / 2 / tip))
    return out


def main():
    b = beam()
    gross, wf = M['published']['gross'], b['wing_fuel']
    cases = [('on the ground, full', 0.0, 1.0, wf), ('on the ground, no fuel', 0.0, 1.0, 0.0), ('1 g, 26,750 lb, full wing tanks', gross, 1.0, wf),
             ('1 g, 19,100 lb, half', 19100.0, 1.0, wf / 2), ('1 g, 12,980 lb, tenth', 12980.0, 1.0, wf / 10),
             ('2.5 g, 26,750 lb, full', 2.5 * gross, 2.5, wf)]
    rows = []
    for name, lift, nz, fuel in cases:
        d, s = shape(b, lift, nz, fuel)
        rows.append(dict(case=name, tip_ft=float(d[-1]), tip_slope_deg=float(np.degrees(s[-1])), percent_semispan=float(100 * d[-1] / b['half'])))
        print('%-34s tip %+6.2f ft (%+.1f %% of the semi-span), tip slope %+.1f deg' % (name, d[-1], 100 * d[-1] / b['half'], np.degrees(s[-1])))
    u = b['unit']
    coef = dict(per_lb_lift=float(u['lift'][0][-1]), per_lb_structure=float(u['structure'][0][-1]), per_lb_wing_fuel=float(u['fuel'][0][-1]))
    f_full, f_empty = frequency(b, wf), frequency(b, 0.0)
    print('tip deflection: %.3e ft per lb of lift, %.3e per lb of wing structure, %.3e per lb of wing fuel (times the load factor)' % (
        coef['per_lb_lift'], coef['per_lb_structure'], coef['per_lb_wing_fuel']))
    print('first bending: %.2f Hz with full wing tanks, %.2f Hz empty; EI %.3g lb ft2 at the root, %.3g at mid span' % (
        f_full, f_empty, b['EI'][0], b['EI'][N // 2]))
    clb = roll_due_to_sideslip(b)
    for r in clb:
        print('roll due to sideslip, Mach %.2f: rigid %+.5f per deg, with 4 ft of tip deflection %+.5f, so %+.6f per deg per ft' % (
            r['mach'], r['rigid_per_deg'], r['bent_4ft_per_deg'], r['per_ft_per_deg']))
    wv = u['lift'][0]
    json.dump(dict(assumptions=dict(strain_1g=STRAIN_1G, tip_strain_fraction=TIP_STRAIN, box_depth=BOX_DEPTH, damping=DAMPING,
                                    note='a strength-sized cantilever: none of this is Global Hawk data'),
                   tip_deflection=coef, wing_structure_lb=b['wing_struct'], wing_fuel_lb=wf, frequency_hz=dict(full=f_full, empty=f_empty),
                   damping=DAMPING, cases=rows, roll_due_to_sideslip=clb,
                   shape=dict(y=np.round(b['y'][::20], 3).tolist(), deflection_over_tip=np.round(wv[::20] / wv[-1], 5).tolist())),
              open(OUT, 'w'), indent=1)


if __name__ == '__main__':
    main()
