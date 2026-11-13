#!/usr/bin/env python3
"""The checks of the aerodynamic model against measurements that no other script prints as checks:

    python3 fdm/phase4_checks.py

S  the wing section's table (NeuralFoil's LRN 1015, fdm/data/section_tables.json) against NASA's tunnel test of the
   section (TM 102840, digitised by fdm/digitise_lrn1015.py), at equal lift coefficient between 0.4 and 1.0, as the
   report itself compares: profile drag within 15 %, moment about the quarter chord within 0.02, maximum lift
   within 10 %.
A  the JSBSim model's trimmed lift-curve slope against the ATTREX flights' (fdm/attrex_lift.py), within 10 %; and
   the flights' bank in their long turns against the bank that speed times turn rate gives, the mean within 1 deg
   (a check of the reading of the data, not of the model).
The limits are the ones written in the plan before each was first run; the figures are in fdm/data/README.md.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402
import strips as S              # noqa: E402

D = os.path.join(HERE, 'data')
rows = []


def add(tag, name, value, ref, err, lim, ok, kind):
    rows.append((tag, name, value, ref, err, lim, ok, kind))


def section(mach, reynolds):
    """cl, cd, cm of the wing's section against angle of attack at a Mach and a Reynolds number, as the strips read it."""
    cl, cd, cm = S.Section(S.section_tables()['wing'], mach)(S.ALPHAS, np.full(len(S.ALPHAS), reynolds))
    return S.ALPHAS, cl, cd, cm


def sections():
    tunnel = json.load(open(os.path.join(D, 'lrn1015_tunnel.json')))
    for c in tunnel['cases']:
        name = 'Mach %.1f, Re %.0f million' % (c['mach'], c['reynolds'] / 1e6)
        alpha, cl, cd, cm = section(c['mach'], c['reynolds'])
        top = int(np.argmax(cl))
        up = slice(int(np.argmin(np.abs(alpha + 4))), top + 1)                 # the attached branch, where lift rises
        at = lambda y, x: float(np.interp(x, cl[up], y[up]))
        pts = [p for p in c['cd'] if 0.4 <= p[1] <= 1.0]
        t_cd, m_cd = np.mean([p[0] for p in pts]), np.mean([at(cd, p[1]) for p in pts])
        add('S1', 'section drag at lift 0.4 to 1.0, %s' % name, m_cd, t_cd, 100 * (m_cd / t_cd - 1), 15.0, abs(m_cd / t_cd - 1) <= 0.15, 'predicted')
        pts = [p for p in c['cm'] if 0.4 <= p[1] <= 1.0]
        t_cm, m_cm = np.mean([p[0] for p in pts]), np.mean([at(cm, p[1]) for p in pts])
        add('S2', 'section moment at lift 0.4 to 1.0, %s' % name, m_cm, t_cm, m_cm - t_cm, 0.02, abs(m_cm - t_cm) <= 0.02, 'predicted')
        t_max = max(p[1] for p in c['alpha'])
        add('S3', 'section maximum lift, %s' % name, float(cl[top]), t_max, 100 * (cl[top] / t_max - 1), 10.0, abs(cl[top] / t_max - 1) <= 0.10, 'predicted')


def lift_curve():
    data = json.load(open(os.path.join(D, 'attrex_lift.json')))
    f = H.load(rebuild=False)
    for fit in data['lift_fits']:
        seg = [p for p in data['points'] if fit['mach_lo'] <= p['mach'] <= fit['mach_hi'] and p['flight'] in fit['flights']]
        mach, alt = float(np.mean([p['mach'] for p in seg])), float(np.mean([p['alt_ft'] for p in seg]))
        w = np.linspace(min(p['weight'] for p in seg), max(p['weight'] for p in seg), 6)
        a, c = [], []
        for weight in w:
            t = H.trim(f, alt=alt, mach=mach, weight=float(weight))
            if t['ok']:
                a.append(t['alpha'])
                c.append(t['CL'])
        slope = float(np.polyfit(a, c, 1)[0])
        add('A1', 'trimmed lift-curve slope, Mach %.2f to %.2f, per deg' % (fit['mach_lo'], fit['mach_hi']), slope, fit['slope_per_deg'],
            100 * (slope / fit['slope_per_deg'] - 1), 10.0, abs(slope / fit['slope_per_deg'] - 1) <= 0.10, 'predicted: %d trims at %.0f ft, %d segments of %d flights' % (
                len(a), alt, fit['segments'], len(fit['flights'])))
    t = data['turn_fit']
    add('A2', 'bank in %d long turns less speed times turn rate, deg' % t['n'], t['mean_bank'] + t['mean_error_deg'], t['mean_bank'], t['mean_error_deg'], 1.0,
        abs(t['mean_error_deg']) <= 1.0, 'the data against kinematics, scatter %.2f deg' % t['scatter_deg'])


if __name__ == '__main__':
    sections()
    lift_curve()
    print('     %-58s %9s %9s %8s %6s' % ('check', 'model', 'measured', 'error', 'limit'))
    for tag, name, value, ref, err, lim, ok, kind in rows:
        print('%-4s %-58s %9.4g %9.4g %+8.3g %6.3g  %s  (%s)' % (tag, name, value, ref, err, lim, 'pass' if ok else 'MISS', kind))
    miss = sum(not r[6] for r in rows)
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))
