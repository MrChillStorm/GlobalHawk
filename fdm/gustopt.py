#!/usr/bin/env python3
"""The trade-off curve of the approach speed's addition, from the flights fdm/gustsweep.py's `opt` set made (docs/PLAN.md, "Gusts: find out first").

    python3 fdm/gustopt.py [--dir fdm/out/gust]

Reads opt.add<KT>.{off,on}.jsonl (the bench's turbulence, 24 sequences a condition, flown with the addition 0 to 18 kt, the gust system off and on) and prints, for each condition (the wind at 20 ft, with or
without that wind blowing steadily at 45 deg to the runway) and each system state, one row a addition:

    hard     flights with a touchdown over 2 m/s, the structural flag, or none (of the 24)
    sink95   the 95th percentile of the touchdown's sink, m/s
    prot     flights in which the angle-of-attack protection was acting (the margin under 0) somewhere below 500 ft
    marg5    the 5th percentile of the flights' least margin below 500 ft, deg (the margin a bad one of twenty has)
    line95   the 95th percentile of the distance off the centreline at the first wheel, ft
    nose95   the 95th percentile of the nose's heading error at the first wheel, deg
    total    the mean distance from the aiming point to the end of the rollout, ft (what the runway has to be)
    front    * marks the additions no other addition beats in all of: prot, hard, line95, total (the trade-off curve; no weights are chosen)
"""
import glob
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'out', 'gust')
if '--dir' in sys.argv:
    D = sys.argv[sys.argv.index('--dir') + 1]


def load(add, state):
    path = os.path.join(D, 'opt.add%d.%s.jsonl' % (add, state))
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in open(path)]


def klass(name):
    m = re.search(r'lo=(\d+)', name)
    steady = 'hw=' in name
    return (steady, int(m.group(1)))


def metrics(rs):
    down = [r for r in rs if r['down']]
    hard = sum(1 for r in rs if (not r['down']) or r['sink_ms'] > 2.0 or r.get('overstress', 0) > 0)
    mins = np.array([r['below500']['alpha_margin'] for r in down])
    return dict(n=len(rs), hard=hard, sink95=float(np.percentile([r['sink_ms'] for r in down], 95)), prot=int(np.sum(mins < 0)), marg5=float(np.percentile(mins, 5)),
                line95=float(np.percentile([abs(r['xt_td_ft']) for r in down], 95)), nose95=float(np.percentile([r['nose_off_deg'] for r in down], 95)),
                total=float(np.mean([r['total_ft'] for r in down])))


def main():
    adds = sorted(int(re.search(r'add(\d+)', p).group(1)) for p in glob.glob(os.path.join(D, 'opt.add*.off.jsonl')))
    for state in ('off', 'on'):
        data = {a: load(a, state) for a in adds}
        classes = sorted({klass(r['name']) for a in adds for r in data[a]})
        for c in classes:
            rows = {}
            for a in adds:
                rs = [r for r in data[a] if klass(r['name']) == c]
                if rs:
                    rows[a] = metrics(rs)
            if not rows:
                continue
            front = []
            for a, m in rows.items():
                dominated = any(all(o[k] <= m[k] for k in ('prot', 'hard', 'line95', 'total')) and any(o[k] < m[k] for k in ('prot', 'hard', 'line95', 'total')) for b, o in rows.items() if b != a)
                front.append(not dominated)
            print('\nsystem %s, wind at 20 ft %d kt%s (%d flights an addition)' % (state, c[1], ', blowing steadily at 45 deg' if c[0] else '', next(iter(rows.values()))['n']))
            print('  add  hard  sink95  prot  marg5  line95  nose95   total  front')
            for (a, m), f in zip(rows.items(), front):
                print('  %3d  %4d  %6.2f  %4d  %5.2f  %6.1f  %6.1f  %6.0f  %s' % (a, m['hard'], m['sink95'], m['prot'], m['marg5'], m['line95'], m['nose95'], m['total'], '*' if f else ''))


if __name__ == '__main__':
    main()
