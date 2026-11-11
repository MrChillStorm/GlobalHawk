#!/usr/bin/env python3
"""Phase 5 checks: standing, taxi, takeoff and landing of the JSBSim model against what was measured.

    python3 fdm/phase5_checks.py            the checks
    python3 fdm/phase5_checks.py --fit      fit the spoilers to the measured 2013 approach first (calibration.json)

Measured: Pastor and others (2018) for the takeoff roll and first climb; the ATTREX records (two landings, 19 starts
just after liftoff) for the rest. The pilot is plain Python at the model's rate (fdm/harness.py), standing in for
the flight laws. The takeoff weight is assumed (25,600 lb). The landing weights are full tanks at takeoff less the fuel
our engine model burns along each recorded flight (fdm/attrex_lift.py): 20,800 lb after the 6 h flight of 2013 and
17,100 lb after the 17 h flight of 2014. The two approach speeds, 133 and 120 KEAS, are in the ratio of the square
roots of those weights within half a percent, which a single assumed landing weight could not explain.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H          # noqa: E402

CAL = os.path.join(HERE, 'data', 'calibration.json')
M = json.load(open(os.path.join(HERE, 'data', 'mass.json')))
SPOILER_APPROACH = 30.0 / 45.0
# ATTREX: approach speed (KEAS), glide (deg), angle of attack (deg), field height (ft)
A2013 = dict(keas=133.0, gamma=-4.46, aoa=4.66, field=2357.0, decel=0.235, roll_to_43kt=3485.0, touchdown_keas=130.0, weight=20800.0)
A2014 = dict(keas=120.0, gamma=-4.44, aoa=4.29, field=574.0, weight=17100.0)
rows = []


def check(tag, name, value, target, limit, kind, absolute=False):
    err = (value - target) if absolute else 100.0 * (value - target) / abs(target)
    rows.append((tag, name, '%.4g' % value, '%.4g' % target, ('%+.2f' % err) + ('' if absolute else ' %'), ('%g' % limit) + ('' if absolute else ' %'),
                 abs(err) <= limit, kind))


def yes(tag, name, ok, detail, kind):
    rows.append((tag, name, '', '', '', '', bool(ok), kind + ': ' + detail))


def fit_spoilers(f):
    """The lift dumped and the drag added by the spoilers at the approach setting, so that the model, gear down
    and at idle, sits on the measured 2013 approach: its speed, its glide angle and its angle of attack."""
    from scipy.optimize import fsolve
    cond = dict(alt=A2013['field'] + 400.0, kcas=A2013['keas'], weight=A2013['weight'], gamma=A2013['gamma'], gear=1.0, spoiler=SPOILER_APPROACH)

    def res(v):
        f['cal/spoiler-lift'], f['cal/spoiler-drag'] = v[1], v[2]
        a = H.state(f, cond, A2013['aoa'], v[0], 0.0)
        return [a[0], a[2], a[4] * 50]
    v = fsolve(res, [0.0, -0.5, 0.05])
    cal = json.load(open(CAL))
    cal['spoiler_lift'], cal['spoiler_drag'] = round(float(v[1]), 4), round(float(v[2]), 5)
    json.dump(cal, open(CAL, 'w'), indent=1)
    print('spoilers fitted: lift %.3f and drag %.4f at 45 deg (%.3f and %.4f at the approach setting, 30 deg); ruddervators %.1f deg' % (
        v[1], v[2], v[1] * SPOILER_APPROACH, v[2] * SPOILER_APPROACH, 20 * v[0]))


def main():
    f = H.load()
    if '--fit' in sys.argv:
        fit_spoilers(f)
        f = H.load()
    # G1 standing
    for w in (26750.0, 11450.0):
        H.on_ground(f, w)
        x0 = f['position/distance-from-start-mag-mt']
        for _ in range(int(60 * H.HZ)):
            f.run()
        moved = (f['position/distance-from-start-mag-mt'] - x0) / 0.3048
        yes('G1', 'stands 60 s at %.0f lb' % w, abs(moved) < 0.5 and abs(f['attitude/phi-deg']) < 0.5,
            'moved %.2f ft, pitch %.2f deg, bank %.2f deg' % (moved, f['attitude/theta-deg'], f['attitude/phi-deg']), 'flies')
    # G2 taxi
    H.on_ground(f, 20000.0)
    H.brakes(f, 0)
    worst_bank, phase, hdg, finite = 0.0, 0, None, True
    for i in range(int(180 * H.HZ)):
        v = f['velocities/vg-fps'] / H.KT
        psi = f['attitude/psi-deg']
        if phase == 0:                                         # to 15 kt straight
            f['fcs/throttle-cmd-norm'] = 0.25 if v < 15 else 0.0
            f['fcs/steer-cmd-norm'] = float(np.clip(-0.012 * H.heading_error(f, 0.0) - 0.8 * f['velocities/r-rad_sec'], -0.1, 0.1))
            if v >= 15:
                phase = 1
        elif phase == 1:                                       # turn right through 90 deg at 15 kt or less
            f['fcs/throttle-cmd-norm'] = 0.15 if v < 10 else 0.0
            e = H.heading_error(f, 90.0)
            f['fcs/steer-cmd-norm'] = float(np.clip(-0.03 * e - 0.8 * f['velocities/r-rad_sec'], -0.5, 0.5))
            if abs(e) < 1.0:
                phase = 2
        else:                                                  # stop
            f['fcs/throttle-cmd-norm'] = 0.0
            f['fcs/steer-cmd-norm'] = 0.0
            H.brakes(f, 0.5)
            if v < 0.2:
                break
        f.run()
        worst_bank = max(worst_bank, abs(f['attitude/phi-deg']))
        finite = finite and np.isfinite(f['attitude/phi-deg'])
    yes('G2', 'taxi to 15 kt, turn 90 deg, stop', phase == 2 and finite and worst_bank < 3.0 and f['velocities/vg-fps'] / H.KT < 0.5,
        'reached phase %d of 2, bank up to %.2f deg, heading %.1f deg, %.0f s' % (phase, worst_bank, f['attitude/psi-deg'], f['simulation/sim-time-sec']), 'flies')
    # takeoff
    log = H.takeoff(f)
    i130, ilo = int(np.argmax(log['kcas'] >= 130)), int(np.argmax(log['agl'] > 7.0))
    check('T1', 'brake release to 130 KIAS, s', log['t'][i130], 37.5, 15.0, 'predicted')
    yes('T2', 'liftoff between 120 and 140 KEAS, pitch under 8 deg', 120 <= log['keas'][ilo] <= 140 and log['theta'][ilo] < 8,
        '%.0f KEAS, pitch %.1f deg, angle of attack %.1f deg, after %.0f ft' % (log['keas'][ilo], log['theta'][ilo], log['alpha'][ilo], log['x'][ilo] / 0.3048), 'predicted')
    k = (log['t'] > log['t'][ilo] + 30) & (log['t'] < log['t'][ilo] + 40)
    roc = float(log['vs'][k].mean() * 60)
    yes('T3', 'climb 30-40 s after liftoff inside 2,250-3,650 ft/min', 2250 <= roc <= 3650,
        '%.0f ft/min at %.0f KEAS, pitch %.1f deg (ATTREX: 10-14 deg)' % (roc, log['keas'][k].mean(), log['theta'][k].mean()), 'predicted')
    check('T3', '2,500 to 5,000 ft, s', float(np.interp(5000, log['alt'], log['t']) - np.interp(2500, log['alt'], log['t'])), 61.0, 15.0, 'predicted')
    finite_to = bool(np.all(np.isfinite(log['alt'])))
    # L1 the 2014 approach with the spoilers fitted on 2013
    t14 = H.trim(f, alt=A2014['field'] + 400.0, kcas=A2014['keas'], weight=A2014['weight'], gamma=A2014['gamma'], gear=1.0, spoiler=SPOILER_APPROACH)
    check('L1', '2014 approach: angle of attack, deg', t14['alpha'], A2014['aoa'], 1.0, 'predicted', True)
    # at idle the trim may be left with a little acceleration along the path: under 0.02 g counts as holding the approach
    yes('L1', '2014 approach: throttle between idle and 30 %', t14['throttle'] <= 0.30 and t14['residual'] < 0.02 * 32.174,
        'throttle %.0f %%, left over %.3f g, ruddervators %+.1f deg' % (100 * t14['throttle'], t14['residual'] / 32.174, t14['pitch_deg']), 'predicted')
    # the 2013 landing, flown
    t13 = H.trim(f, alt=A2013['field'] + 400.0, kcas=A2013['keas'], weight=A2013['weight'], gamma=A2013['gamma'], gear=1.0, spoiler=SPOILER_APPROACH)
    land = H.landing(f, t13, weight=A2013['weight'], elevation=A2013['field'], decel_g=A2013['decel'])
    td = land['touchdown']
    stopped = td is not None and land['gs'][-1] < 2.0
    yes('L2', 'touchdown: sink under 1.5 m/s, stays down', td is not None and td['sink'] < 1.5 and stopped,
        ('%.0f KEAS (measured 130), sink %.2f m/s (measured 0.66), pitch %.1f deg (measured 2.4)' % (td['keas'], td['sink'], td['theta'])) if td else 'never touched down', 'flies')
    if td:
        i43 = int(np.argmax((land['t'] > td['t']) & (land['gs'] / H.KT < 43.0)))
        check('L3', 'rollout from touchdown to 43 kt, ft', (land['x'][i43] - td['x']) / 0.3048, A2013['roll_to_43kt'], 15.0, 'after setting the deceleration')
        total = (land['x'][-1] - td['x']) / 0.3048
    yes('L4', 'rest to rest without NaN', finite_to and bool(np.all(np.isfinite(land['alt']))) and stopped,
        'landing run to a stop: %.0f ft' % total if td else 'no touchdown', 'flies')

    print('%-4s %-52s %9s %9s %9s %7s' % ('', 'check', 'model', 'measured', 'error', 'limit'))
    for tag, name, val, ref, err, lim, ok, kind in rows:
        print('%-4s %-52s %9s %9s %9s %7s  %s  (%s)' % (tag, name, val, ref, err, lim, 'pass' if ok else 'MISS', kind))
    miss = sum(1 for r in rows if not r[6])
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))


if __name__ == '__main__':
    main()
