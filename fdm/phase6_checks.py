#!/usr/bin/env python3
"""Phase 6 checks: the wing's bending in the JSBSim model against the beam model it comes from (fdm/flex.py).
Consistency only: the beam model stands on assumptions, not on data of the aircraft."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import flex          # noqa: E402
import harness as H  # noqa: E402

rows = []


def main():
    f = H.load()
    b = flex.beam()
    out = []
    for label, cond in (('cruise, 15,000 lb', dict(alt=60000, mach=0.6, weight=15000)), ('climb, 26,750 lb', dict(alt=10000, kcas=150, weight=26750))):
        t = H.trim(f, **dict(cond))
        wf = f['flex/wing-fuel-lbs']
        d, _ = flex.shape(b, t['lift'], f['accelerations/Nz'], wf)
        js = f['flex/tip-deflection-ft']
        err = 100 * (js - d[-1]) / d[-1]
        out.append(('F1', 'tip deflection at the %s trim, ft' % label, js, d[-1], err, 3.0, abs(err) <= 3.0))
        # roll due to sideslip, with and without
        res = {}
        for en in (1, 0):
            f['flex/enable'] = en
            x = list(t['x'])
            V = np.hypot(x[0], x[2])
            x1 = list(x)
            x1[1] = V * np.sin(np.radians(2.0))
            a1 = H.state(f, t['cond'], t['alpha'], t['pitch_cmd'], t['throttle'], x=x1)
            a0 = H.state(f, t['cond'], t['alpha'], t['pitch_cmd'], t['throttle'], x=x)
            S, bw = f['metrics/Sw-sqft'], f['metrics/bw-ft']
            res[en] = (a1[3] - a0[3]) * f['inertia/ixx-slugs_ft2'] / (t['qbar'] * S * bw) / 2.0
            t['modes_%d' % en] = H.modes(f, t)
        f['flex/enable'] = 1
        print('%s: tip %+.2f ft; roll due to sideslip %.5f per deg rigid, %.5f bent' % (label, js, res[0], res[1]))
        for en, name in ((0, 'rigid'), (1, 'bent ')):
            print('   lateral modes, %s: %s' % (name, '; '.join(H.describe(e) for e in t['modes_%d' % en]['lateral'])))
    H.on_ground(f, 26750.0)
    for _ in range(int(10 * H.HZ)):
        f.run()
    ground = f['flex/tip-deflection-ft']
    dg, _ = flex.shape(b, 0.0, 1.0, f['flex/wing-fuel-lbs'])
    out.append(('F2', 'tip deflection standing with full tanks, ft', ground, dg[-1], 100 * (ground - dg[-1]) / dg[-1], 3.0, abs(ground - dg[-1]) <= 0.03 * abs(dg[-1]) and ground < 0))
    # in flight under the attitude hold: the mode settles on its static value
    t = H.trim(f, alt=60000, mach=0.6, weight=15000)
    H.fly(f, t, 20.0, lag=True)
    dyn, sta = f['flex/tip-dynamic-ft'], f['flex/tip-static-ft']
    out.append(('F1', 'the mode 20 s after release at cruise against its settled value, ft', dyn, sta, 100 * (dyn - sta) / sta, 1.0, abs(dyn - sta) <= 0.01 * abs(sta)))
    print('\n%-4s %-52s %9s %9s %8s %6s' % ('', 'check', 'JSBSim', 'beam', 'error', 'limit'))
    for tag, name, v, r, e, lim, ok in out:
        print('%-4s %-52s %9.3f %9.3f %+7.2f%% %5.1f%%  %s' % (tag, name, v, r, e, lim, 'pass' if ok else 'MISS'))
    print('%d checks, %d pass' % (len(out), sum(1 for o in out if o[6])))


if __name__ == '__main__':
    main()
