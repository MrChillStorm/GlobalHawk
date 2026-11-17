#!/usr/bin/env python3
"""The landing's lateral law against FlightGear-like turbulence: sets of flights and designs of the law, flown offline on the bench (fdm/gustbench.py), compared by the cross-track at the wheels.

    python3 fdm/latsweep.py list                          the sets and the designs
    python3 fdm/latsweep.py run SET DESIGN [DESIGN ...]   fly the set once per design (each design one queued job: `qrun`, two at a time), results in fdm/out/lat/SET.DESIGN.jsonl
    python3 fdm/latsweep.py report SET DESIGN [DESIGN ...]  the table (the first design is the one the others are compared with, paired by flight)

The air is JSBSim's own MIL-F-8785C turbulence as FlightGear runs it (`GB_ELEV=171`: the field at EFHK's height; `tu=W20:severity`: the wind at 20 ft and the severity), at the steady wind's strength,
from the right and from the left; the cases differ in weight, wind and seed. The measure is the distance from the centreline at the first wheel (`xt_td_ft`, WGS84's tangent plane).
Written 2026-11-17 for docs/PLAN.md, "The lateral law's loop times" (train set: seeds 301 to 306; the test sets use seeds that no design was chosen on).
"""
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out', 'lat')

# --- the designs: the laws' numbers changed for a design, `--set laws.NAME=value`
DESIGNS = {
    'base': dict(FINAL_SCHED=0),                                                                         # the law as it was until 2026-11-17: 25 s, 6 s at every height
    'cur': {},                                                                                           # the law as it is now (the schedule on, 8 s and 2 s low)
    'u20_5': dict(FINAL_T_OUTER_S=20, FINAL_T_INNER_S=5),
    'u15_4': dict(FINAL_T_OUTER_S=15, FINAL_T_INNER_S=4),
    'u10_25': dict(FINAL_T_OUTER_S=10, FINAL_T_INNER_S=2.5),
    'u25_3': dict(FINAL_T_OUTER_S=25, FINAL_T_INNER_S=3),
    's10_25': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=10, FINAL_T_INNER_LAND_S=2.5),                    # short below 300 ft, the old times above 800 ft
    's8_2': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=8, FINAL_T_INNER_LAND_S=2),
    's12_3': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=12, FINAL_T_INNER_LAND_S=3),
    's15_4': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=15, FINAL_T_INNER_LAND_S=4),
    's10_25n': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=10, FINAL_T_INNER_LAND_S=2.5, FINAL_SCHED_LO_FT=150, FINAL_SCHED_HI_FT=500),   # the short times only low
    's8_2n': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=8, FINAL_T_INNER_LAND_S=2, FINAL_SCHED_LO_FT=150, FINAL_SCHED_HI_FT=500),
    's12_3n': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=12, FINAL_T_INNER_LAND_S=3, FINAL_SCHED_LO_FT=150, FINAL_SCHED_HI_FT=500),
    's15_4n': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=15, FINAL_T_INNER_LAND_S=4, FINAL_SCHED_LO_FT=150, FINAL_SCHED_HI_FT=500),
    # round 2: towards the edge of stability, and where the schedule begins
    's6_15': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=6, FINAL_T_INNER_LAND_S=1.5),
    's6_2': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=6, FINAL_T_INNER_LAND_S=2),
    's7_2': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=7, FINAL_T_INNER_LAND_S=2),
    's8_15': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=8, FINAL_T_INNER_LAND_S=1.5),
    's8_2m': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=8, FINAL_T_INNER_LAND_S=2, FINAL_SCHED_LO_FT=200, FINAL_SCHED_HI_FT=600),
    's8_2w': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=8, FINAL_T_INNER_LAND_S=2, FINAL_SCHED_LO_FT=400, FINAL_SCHED_HI_FT=1000),
    # round 3: the decrab begun higher, so the bank can answer the drift the nose's turn gives (8 ft now: the last 150 ft add 4 to 25 ft in a strong crosswind)
    'd15': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=8, FINAL_T_INNER_LAND_S=2, DECRAB_H_START=15),
    'd25': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=8, FINAL_T_INNER_LAND_S=2, DECRAB_H_START=25),
    'd40': dict(FINAL_SCHED=1, FINAL_T_OUTER_LAND_S=8, FINAL_T_INNER_LAND_S=2, DECRAB_H_START=40),    # round 4: the decrab's shape (8 ft and a rudder gain of 2 now)
    'd5': dict(DECRAB_H_START=5),
    'd3': dict(DECRAB_H_START=3),
    'k3': dict(DECRAB_K=3),
    'k15': dict(DECRAB_K=1.5),
}

BASE = 'w=%d lat=60.3 course=227.5'


def winds():
    """(label, weather words) for each side: the scenario's 28 kt abeam, a strong 36 kt abeam, 20 kt from 60 deg"""
    out = []
    for side in (1, -1):
        out.append(('28 kt abeam', 'tu=28:6 hw=4 xw=%d' % (28 * side)))
        out.append(('36 kt abeam', 'tu=36:6 hw=5 xw=%d' % (36 * side)))
        out.append(('20 kt at 60', 'tu=20:5 hw=10 xw=%d' % (17 * side)))
    return out


def make_set(name):
    cases = []
    if name == 'train':             # the design set: seeds 301 to 306, two weights
        for w in (26750, 12450):
            for _, words in winds():
                for seed in range(301, 307):
                    cases.append('%s %s seed=%d' % (BASE % w, words, seed))
    elif name == 'test':            # fresh seeds, three weights, more seeds: no design was chosen on these
        for w in (26750, 20800, 12450):
            for _, words in winds():
                for seed in range(401, 409):
                    cases.append('%s %s seed=%d' % (BASE % w, words, seed))
    elif name == 'robust':          # calm air: the intercepts, a fuel imbalance, a straight final: what a faster law must not spoil
        for off in (-2000, -1000, -300, 300, 1000, 2000):
            cases.append('%s hw=0 xw=0 off=%d' % (BASE % 26750, off))
        for imb in (-0.3, 0.3):
            cases.append('%s hw=0 xw=0 imb=%g' % (BASE % 26750, imb))
        cases.append('%s hw=0 xw=0' % (BASE % 26750))
        cases.append('%s hw=0 xw=0' % (BASE % 12450))
    else:
        raise SystemExit('no set %s' % name)
    return cases


def path(setname, design, ext):
    return os.path.join(OUT, '%s.%s.%s' % (setname, design, ext))


def run(setname, designs):
    os.makedirs(OUT, exist_ok=True)
    cases = make_set(setname)
    procs = []
    for d in designs:
        cf = path(setname, d, 'cases')
        open(cf, 'w').write('\n'.join(cases) + '\n')
        of = path(setname, d, 'jsonl')
        if os.path.exists(of):
            os.remove(of)
        sets = []
        for k, v in DESIGNS[d].items():
            sets += ['--set', 'laws.%s=%g' % (k, v)]
        cmd = ['qrun', 'env', 'GB_ELEV=171', sys.executable, os.path.join(HERE, 'gustbench.py')] + sets + ['--from', cf, '--out', of]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(path(setname, d, 'log'), 'w'), cwd=os.path.dirname(HERE)))
    for p in procs:
        p.wait()


def load(setname, design):
    rows = {}
    for line in open(path(setname, design, 'jsonl')):
        r = json.loads(line)
        rows[r['name']] = r
    return rows


def boot(d, n=10000, seed=1):
    rng = np.random.default_rng(seed)
    d = np.asarray(d, float)
    b = [rng.choice(d, len(d)).mean() for _ in range(n)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def report(setname, designs):
    data = {d: load(setname, d) for d in designs}
    keys = [k for k in data[designs[0]] if all(k in data[d] for d in designs)]
    print('%s: %d flights a design; cross-track at the first wheel, ft (right positive)' % (setname, len(keys)))
    print('%-9s %7s %6s %7s %7s %7s %6s %6s %6s %5s %6s %6s' % ('design', 'mean', 'sd', 'mean|x|', 'p90|x|', 'p95|x|', 'worst', '>15 ft', '>30 ft', 'hard', 'bank', 'dVs base'))
    base = np.array([abs(data[designs[0]][k]['xt_td_ft']) for k in keys], float)
    for d in designs:
        x = np.array([data[d][k]['xt_td_ft'] for k in keys], float)
        sk = np.array([data[d][k]['sink_ms'] for k in keys], float)
        bk = np.array([data[d][k]['below500']['bank'] for k in keys], float)
        ax = abs(x)
        diff = ax - base
        lo, hi = boot(diff)
        tail = '' if d == designs[0] else '%+.1f [%.1f, %.1f], better %d of %d' % (diff.mean(), lo, hi, (diff < 0).sum(), len(diff))
        print('%-9s %7.1f %6.1f %7.1f %7.1f %7.1f %6.1f %6d %6d %5d %6.1f  %s' % (d, x.mean(), x.std(), ax.mean(), np.percentile(ax, 90), np.percentile(ax, 95), ax.max(), (ax > 15).sum(), (ax > 30).sum(), (sk > 2).sum(), bk.mean(), tail))


def main():
    a = sys.argv[1:]
    if not a or a[0] == 'list':
        print('sets:', 'train', 'test', 'robust')
        for k, v in DESIGNS.items():
            print('  %-9s %s' % (k, v or 'the law as it is'))
    elif a[0] == 'run':
        run(a[1], a[2:])
    elif a[0] == 'report':
        report(a[1], a[2:])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
