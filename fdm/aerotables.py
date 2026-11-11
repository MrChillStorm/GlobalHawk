#!/usr/bin/env python3
"""Sample an aerodynamic model into the tables the JSBSim model is built from.

    python3 fdm/aerotables.py            the strip model -> fdm/data/aero_tables.json
    python3 fdm/aerotables.py --ref      AeroSandbox's build-up -> fdm/data/aero_tables_ref.json

The tables run over angle of attack and Mach number. Each Mach number is sampled at ONE altitude, the one at which
the aircraft flies that Mach number on its climb schedule, so the Reynolds number is right along the schedule and
approximate off it (a low, fast pass sees the drag of a higher Reynolds number than the table has).

Coefficients are about the reference point: the centre-of-gravity target of fdm/data/mass.json. Sign conventions
are the models' (strips.py): ailerons positive with the right trailing edge down, ruddervators together positive
trailing edge down ("pitch"), against each other positive nose right ("yaw").

The reference build takes its tail-control tables from the strip model: AeroSandbox gave none.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E                               # noqa: E402
import strips                                    # noqa: E402

MACH = [0.15, 0.30, 0.45, 0.55, 0.60, 0.65]
ALT = [0.0, 10000.0, 30000.0, 45000.0, 60000.0, 60000.0]
ALPHA = [-6.0, -4.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0]
ALPHA_D = [0.0, 3.0, 6.0]                        # where the derivatives are taken
PITCH_D = [-10.0, -5.0, 0.0, 5.0, 10.0]          # ruddervator angles for the drag increment
GE_AGL = [0.0, 3.0, 8.0, 15.0, 30.0, 60.0, 120.0, 300.0]   # ft, wheels above the ground; no effect at the last
GE_ALPHA = [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0]
MASS = json.load(open(os.path.join(HERE, 'data', 'mass.json')))
REF = [MASS['cg_target']['x'], 0.0, 5.3]


def models(ref=False):
    ac = strips.Aircraft()
    ours = lambda alt, mach, alpha, **kw: ac.solve(alt, mach, alpha, cg=REF, **kw)
    if not ref:
        return ours, ours, ac
    import aero_ref as R
    return (lambda alt, mach, alpha, **kw: R.buildup(alt, mach, alpha, cg_x=REF[0], **kw)), ours, ac


def sample(ref=False):
    f, tail, ac = models(ref)
    t = dict(mach=MACH, altitude_ft=ALT, alpha=ALPHA, alpha_d=ALPHA_D, pitch_d=PITCH_D, reference_point_ft=REF,
             model='AeroSandbox build-up (tail controls from the strips)' if ref else 'strips')
    names = ('CL', 'CD', 'Cm', 'CYb', 'Clb', 'Cnb', 'Cl_da', 'Cn_da', 'Cm_de', 'CL_de', 'Cn_dr', 'Cl_dr', 'CY_dr', 'Clp', 'Cnp',
             'Clr', 'Cnr', 'Cmq', 'CLq', 'dCD_de')
    for n in names:
        t[n] = []
    for mach, alt in zip(MACH, ALT):
        V = mach * np.sqrt(1.4 * 287.05287 * E.isa(alt)[0]) / 0.3048
        base = [f(alt, mach, a) for a in ALPHA]
        for n in ('CL', 'CD', 'Cm'):
            t[n].append([round(b[n], 5) for b in base])
        col = {n: [] for n in names[3:19]}
        for a in ALPHA_D:
            b = f(alt, mach, a)
            s = f(alt, mach, a, beta=2.0)
            col['CYb'].append((s['CY'] - b['CY']) / 2)
            col['Clb'].append((s['Cl'] - b['Cl']) / 2)
            col['Cnb'].append((s['Cn'] - b['Cn']) / 2)
            c = f(alt, mach, a, aileron=5.0)
            col['Cl_da'].append((c['Cl'] - b['Cl']) / 5)
            col['Cn_da'].append((c['Cn'] - b['Cn']) / 5)
            bt = tail(alt, mach, a)
            up, dn = tail(alt, mach, a, pitch=5.0), tail(alt, mach, a, pitch=-5.0)
            col['Cm_de'].append((up['Cm'] - dn['Cm']) / 10)
            col['CL_de'].append((up['CL'] - dn['CL']) / 10)
            y = tail(alt, mach, a, yaw=5.0)
            col['Cn_dr'].append((y['Cn'] - bt['Cn']) / 5)
            col['Cl_dr'].append((y['Cl'] - bt['Cl']) / 5)
            col['CY_dr'].append((y['CY'] - bt['CY']) / 5)
            hat = 0.02
            w = hat * 2 * V / ac.b
            pr = f(alt, mach, a, p=w)
            col['Clp'].append((pr['Cl'] - b['Cl']) / hat)
            col['Cnp'].append((pr['Cn'] - b['Cn']) / hat)
            rr = f(alt, mach, a, r=w)
            col['Clr'].append((rr['Cl'] - b['Cl']) / hat)
            col['Cnr'].append((rr['Cn'] - b['Cn']) / hat)
            hq = 0.002
            qr = f(alt, mach, a, q=hq * 2 * V / ac.cbar)
            col['Cmq'].append((qr['Cm'] - b['Cm']) / hq)
            col['CLq'].append((qr['CL'] - b['CL']) / hq)
        for n in col:
            t[n].append([round(float(v), 6) for v in col[n]])
        b3 = tail(alt, mach, 3.0)
        t['dCD_de'].append([round(tail(alt, mach, 3.0, pitch=d)['CD'] - b3['CD'], 6) for d in PITCH_D])
        print('Mach %.2f at %5.0f ft done: CL %.3f..%.3f, best L/D %.1f' % (
            mach, alt, t['CL'][-1][0], max(t['CL'][-1]), max(l / d for l, d in zip(t['CL'][-1], t['CD'][-1]))), flush=True)
    # ground effect: the change in lift, drag and moment with the wheels' height, from the strips' image vortices,
    # at takeoff and landing speed (the reference build takes the strips' too)
    t['ge_agl'] = GE_AGL
    t['ge_alpha'] = GE_ALPHA
    free = [tail(0.0, 0.18, a) for a in GE_ALPHA]
    for n in ('CL', 'CD', 'Cm'):
        t['d%s_ge' % n] = []
    for a, fr in zip(GE_ALPHA, free):
        row = {n: [] for n in ('CL', 'CD', 'Cm')}
        for h in GE_AGL[:-1]:
            g = tail(0.0, 0.18, a, agl=h)
            for n in row:
                row[n].append(round(g[n] - fr[n], 6))
        for n in row:
            t['d%s_ge' % n].append(row[n] + [0.0])
    return t


if __name__ == '__main__':
    ref = '--ref' in sys.argv
    t = sample(ref)
    out = os.path.join(HERE, 'data', 'aero_tables_ref.json' if ref else 'aero_tables.json')
    json.dump(t, open(out, 'w'))
    print('wrote', os.path.relpath(out))
