#!/usr/bin/env python3
"""The trims for a start in the air: writes GlobalHawk/Nasal/trimtable.nas.

    python3 fdm/trimtable.py          a few minutes (a queue job)

FlightGear puts an aircraft into the air at a height and a speed with its nose level, its engine at idle and its
surfaces neutral: not a flight condition, and the first minute is the aircraft finding one (a wobble in height and
speed that the laws take long to damp). Here the flight model is trimmed for level flight over a grid of height,
calibrated airspeed and weight, and the angle of attack, the pitch command and the throttle of each trim are written
as a table. Nasal/globalhawk.nas starts the aircraft from it. Points that have no level trim (too slow for the
weight, or more thrust than there is) are left out; the start burns fuel down, then changes speed, to one that has.
The lowest height is 1,000 ft: at none the wheels are on the ground. A trim counts when the solver says so and what is
left of the accelerations is under 0.2 (ft/s2 and deg/s2: the solver leaves a few hundredths).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402
import laws                     # noqa: E402

ALT = [1000, 5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000, 55000, 60000, 65000]
KCAS = [100, 115, 130, 145, 160, 180, 200]
WEIGHT = [12000, 16000, 20000, 24000, 26750]
OUT = os.path.join(HERE, '..', 'GlobalHawk', 'Nasal', 'trimtable.nas')


def main():
    f = H.load()
    shape = (len(ALT), len(KCAS), len(WEIGHT))
    alpha, elev, thr, ok = (np.full(shape, np.nan) for _ in range(4))
    for i, a in enumerate(ALT):
        for j, v in enumerate(KCAS):
            for k, w in enumerate(WEIGHT):
                try:
                    t = H.trim(f, alt=float(a), kcas=float(v), weight=float(w))
                except Exception:
                    continue
                good = t["ok"] and t["residual"] < 0.2 and 0.0 <= t['throttle'] <= 0.999 and t['mach'] < 0.66
                if good:
                    alpha[i, j, k], elev[i, j, k], thr[i, j, k] = t['alpha'], t['pitch_cmd'], t['throttle']
                ok[i, j, k] = 1.0 if good else 0.0
        print('%5d ft: %d of %d trimmed' % (a, int(np.nansum(ok[i])), len(KCAS) * len(WEIGHT)), flush=True)
    vec = lambda x: '[' + ', '.join('nil' if np.isnan(q) else '%.4g' % q for q in x) + ']'
    cube = lambda c: '[\n' + ',\n'.join('        [' + ', '.join(vec(c[i, j]) for j in range(shape[1])) + ']' for i in range(shape[0])) + '\n    ]'
    with open(OUT, 'w') as fh:
        fh.write('# Level-flight trims of the flight model, written by fdm/trimtable.py: do not edit. By height (ft), calibrated\n'
                 '# airspeed (kt) and weight (lb): the angle of attack (deg), the pitch command (the stick, -1 to 1) and the throttle\n'
                 '# (0 to 1). nil: no level trim there. And the laws\' speed schedule: the airspeed low down, and the height from which\n# it is a Mach number instead. Nasal/globalhawk.nas starts the aircraft in the air from these.\n'
                 'var TRIM = {\n    schedule_kcas: %g,\n    schedule_mach_from_ft: %g,\n    alt: %s,\n    kcas: %s,\n    weight: %s,\n    alpha: %s,\n    elevator: %s,\n    throttle: %s,\n};\n'
                 % (laws.SCHEDULE_KCAS, laws.SCHEDULE[1][0], vec(ALT), vec(KCAS), vec(WEIGHT), cube(alpha), cube(elev), cube(thr)))
    print('wrote %s: %d of %d points trimmed' % (os.path.relpath(OUT, os.path.join(HERE, '..')), int(np.nansum(ok)), ok.size))
    json.dump(dict(alt=ALT, kcas=KCAS, weight=WEIGHT, alpha=np.where(np.isnan(alpha), None, alpha).tolist(), throttle=np.where(np.isnan(thr), None, thr).tolist()),
              open(os.path.join(HERE, 'out', 'trimtable.json'), 'w'))


if __name__ == '__main__':
    main()
