#!/usr/bin/env python3
"""The bank's response delay against the calibrated airspeed, measured (the way the MV-22B's roll delay is: aptest.py rolldelay,
data/roll_delay_v22.json, read by its law generator).

    python3 fdm/rolltest.py [--write]       --write: data/roll_delay_gh.json, which fdm/laws.py reads

A 20 deg bank step through the bank law (roll mode 0, ap/bank-cmd-deg), level flight at 4,000 ft, at 12,000 and 26,000 lb and
110, 150 and 200 KEAS. The law's bank target ramps at 5 deg/s, so it reaches 10 deg 2 s after the step; the delay is how much
later than that the aircraft's bank reaches 10 deg, going in and coming out, the mean of the two and of the two weights. The laws
take it as the time the roll in and the roll out are late by, besides the ramp itself, when they work out where a turn starts
and where it is rolled out. Limits and results: docs/PLAN.md, "Turns onto a new leg".
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402

SPEEDS = (110.0, 150.0, 200.0)
WEIGHTS = (12000.0, 26000.0)
RAMP_TO_10 = 2.0                # s: 10 deg at the bank target's 5 deg/s


def delays(f, weight, kcas):
    t = H.trim(f, alt=4000.0, kcas=kcas, weight=weight, lat=60.0, lon=25.0, psi=90.0, terrain=174.0)
    H.engage(f, t, pitch_mode=2, thrust_mode=3, roll_mode=0)
    f['ap/bank-cmd-deg'] = 20.0
    a, t0 = [], f['simulation/sim-time-sec']
    for i in range(int(30 * H.HZ)):
        if i == int(14 * H.HZ):
            f['ap/bank-cmd-deg'] = 0.0
        f.run()
        a.append((f['simulation/sim-time-sec'] - t0, f['attitude/phi-deg']))
    a = np.array(a)
    t_in = float(a[np.argmax(a[:, 1] >= 10.0), 0])
    j = int(14 * H.HZ)
    t_out = float(a[j + np.argmax(a[j:, 1] <= 10.0), 0]) - 14.0
    return t_in - RAMP_TO_10, t_out - RAMP_TO_10


def main():
    f = H.load()
    out = []
    print('%8s %12s %12s' % ('KEAS', 'in, s', 'out, s'))
    for k in SPEEDS:
        ins, outs = zip(*[delays(f, w, k) for w in WEIGHTS])
        print('%8.0f %12.2f %12.2f' % (k, np.mean(ins), np.mean(outs)))
        out.append(round(float(np.mean(ins + outs)), 2))
    rows = {'kcas': list(SPEEDS), 'delay_s': out,
            'note': 'rolltest.py: the bank\'s delay behind its 5 deg/s target, s: going in and coming out, two weights (fdm/laws.py roll_delay)'}
    print('table:', list(zip(rows['kcas'], rows['delay_s'])))
    if '--write' in sys.argv:
        json.dump(rows, open(os.path.join(HERE, 'data', 'roll_delay_gh.json'), 'w'), indent=1)
        print('written')


if __name__ == '__main__':
    main()
