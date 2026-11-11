#!/usr/bin/env python3
"""Phase 3 checks: the generated JSBSim model against the data it was generated from, and whether it flies.

    python3 fdm/phase3_checks.py          both builds; about a minute

The limits were written in the build plan before the first run. Kinds: "generated" compares JSBSim with the
Python model it was generated from (a check of the generator, not of the aircraft); "flies" is a behaviour.
"""
import contextlib
import io
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E          # noqa: E402
import harness as H         # noqa: E402
import strips               # noqa: E402

M = json.load(open(os.path.join(HERE, 'data', 'mass.json')))
G = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
MAC, MAC_LE = G['wing']['mac'], G['wing']['mac_le_x']
CRUISE = dict(alt=60000, mach=0.6, weight=15000)
CLIMB = dict(alt=10000, kcas=150, weight=26750)
rows = []


def check(tag, name, value, target, limit, kind, absolute=False):
    err = (value - target) if absolute else 100.0 * (value - target) / abs(target)
    rows.append((tag, name, value, target, err, limit, abs(err) <= limit, kind, absolute))


def passfail(tag, name, ok, detail, kind):
    rows.append((tag, name, None, None, None, None, bool(ok), kind + ': ' + detail, False))


def main():
    f = H.load('ships')
    # B1 mass
    for st, w in ((M['states'][0], 26750.0), (M['states'][-1], 11450.0)):
        H.state(f, dict(alt=10000, mach=0.3, weight=w), 2.0, 0.0, 0.5)
        lab = 'full' if w > 20000 else 'no fuel'
        check('B1', 'weight, %s, lb' % lab, f['inertia/weight-lbs'], st['weight'], 0.1, 'generated')
        check('B1', 'centre of gravity, %s, %% MAC' % lab, 100 * (f['inertia/cg-x-in'] / 12 - MAC_LE) / MAC, st['cg_percent_mac'], 0.1, 'generated', True)
        for k, p, lim in (('ixx', 'inertia/ixx-slugs_ft2', 5.0), ('iyy', 'inertia/iyy-slugs_ft2', 2.0), ('izz', 'inertia/izz-slugs_ft2', 2.0)):
            check('B1', '%s, %s, slug ft2' % (k, lab), f[p], st[k], lim, 'generated')
    # B3 engine
    with contextlib.redirect_stdout(io.StringIO()):
        eng = E.global_hawk(E.validation()[0])
    for alt, mach in ((0, 0.1), (10000, 0.27), (45000, 0.55), (60000, 0.6)):
        H.state(f, dict(alt=alt, mach=mach, weight=20000), 2.0, 0.0, 1.0)
        hp = f['engine/pressure-altitude-ft']
        o = eng.maximum(hp, mach)
        check('B3', 'maximum thrust at %d ft, Mach %.2f, lbf' % (alt, mach), f['engine/thrust-lbf'], o['thrust'] / E.LBF, 1.0, 'generated')
        check('B3', 'its fuel flow, lb/h', f['engine/fuel-flow-pph'], o['fuel'] / E.LBH, 1.0, 'generated')
    ac = strips.Aircraft()
    trims = {}
    for build in ('ships', 'ref'):
        g = f if build == 'ships' else H.load('ref')
        for label, cond in (('cruise', CRUISE), ('climb', CLIMB)):
            t = H.trim(g, **dict(cond))
            trims[build, label] = t
            ok = t['ok'] and 0.05 <= t['throttle'] <= 0.95 and abs(t['pitch_deg']) <= 10.0
            passfail('B5', '%s build trims at %s' % (build, label), ok, 'throttle %.0f %%, ruddervators %+.1f deg, residual %.3g' % (
                100 * t['throttle'], t['pitch_deg'], t['residual']), 'flies')
            if build == 'ships':
                # B2: the same point straight from the strip model
                o = ac.solve(g['engine/pressure-altitude-ft'], t['mach'], t['alpha'], pitch=t['pitch_deg'],
                             cg=[M['cg_target']['x'], 0, 5.3])
                check('B2', 'lift coefficient at the %s trim' % label, t['CL'], o['CL'], 2.0, 'generated')
                check('B2', 'drag coefficient at the %s trim' % label, t['CD'], o['CD'], 2.0, 'generated')
            log = H.fly(g, t, 120.0)
            done = len(log['t']) > 0 and log['t'][-1] > 119.0 and np.all(np.isfinite(log['alt']))
            dalt, dv = float(np.max(np.abs(log['alt'] - log['alt'][0]))), float(np.max(np.abs(log['kcas'] - log['kcas'][0])))
            passfail('B6', '%s build flies 120 s from the %s trim' % (build, label), done and dalt <= 100 and dv <= 3,
                     'height within %.0f ft, speed within %.1f kt (limits 100 ft, 3 kt)' % (dalt, dv), 'flies')
            t['modes'] = H.modes(g, t)
    # B4 fuel and centre of gravity over ten minutes of cruise
    t = trims['ships', 'cruise']
    log = H.fly(f, t, 600.0)
    used = log['fuel'][0] - log['fuel'][-1]
    integral = float(np.trapezoid(log['flow'], log['t'])) / 3600.0
    check('B4', 'fuel gone from the tanks in 10 min against the flow integrated, lb', used, integral, 0.5, 'generated')
    check('B4', 'centre of gravity moved in those 10 min, % MAC', 100 * (log['cg'][-1] - log['cg'][0]) / 12 / MAC, 0.0, 0.2, 'flies', True)

    print('%-4s %-66s %10s %10s %8s %6s' % ('', 'check', 'JSBSim', 'target', 'error', 'limit'))
    for tag, name, value, target, err, lim, ok, kind, absolute in rows:
        if value is None:
            print('%-4s %-66s %s  (%s)' % (tag, name, 'pass' if ok else 'MISS', kind))
        else:
            print('%-4s %-66s %10.5g %10.5g %+7.2f%s %5.1f  %s  (%s)' % (tag, name, value, target, err, ' ' if absolute else '%', lim,
                                                                       'pass' if ok else 'MISS', kind))
    n = len(rows)
    miss = sum(1 for r in rows if not r[6])
    print('\n%d checks, %d pass, %d miss' % (n, n - miss, miss))
    print('\nB7, reported: the two builds side by side')
    print('  %-22s %8s %8s %10s %9s %9s %8s %7s' % ('', 'alpha', 'rudderv.', 'thrust lbf', 'of max', 'fuel lb/h', 'CL', 'L/D'))
    for (build, label), t in trims.items():
        print('  %-22s %8.2f %+8.2f %10.0f %8.0f%% %9.0f %8.3f %7.1f' % (build + ', ' + label, t['alpha'], t['pitch_deg'], t['thrust'],
                                                                      100 * t['thrust'] / t['thrust_max'], t['fuel_flow'], t['CL'], t['CL'] / t['CD']))
    print('  modes of the bare airframe, controls fixed:')
    for (build, label), t in trims.items():
        for k, v in t['modes'].items():
            print('    %-14s %-13s %s' % (build + ', ' + label, k, '; '.join(H.describe(e) for e in v)))
    c = trims['ships', 'climb']
    roc = (c['thrust_max'] - c['drag']) * c['ktas'] * H.KT / c['weight'] * 60
    print('  climb at 10,000 ft, 150 KIAS, full weight, maximum thrust: %.0f ft/min by the energy balance (Pastor measured 2,357 to '
          '2,538 between 10,000 and 20,000 ft)' % roc)
    return miss


if __name__ == '__main__':
    main()
