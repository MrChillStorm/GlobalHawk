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
FLAGS = os.environ.get('LAT_FLAGS', '').split()         # LAT_FLAGS="--gs --auto": the bench's flags for every flight (the aircraft as it flies now: the stabilisation and the picker on); the files go to out/lat_on
OUT = os.path.join(HERE, 'out', 'lat_on' if FLAGS else 'lat')

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
    # round 5 (2026-11-17, after the wing tip was found at the ground in a 5.4 deg touchdown): the loops' times in the flare, 5 ft and under (the landing times above 40 ft), no bank limiter
    'o15': dict(FINAL_T_OUTER_TD_S=15), 'o30': dict(FINAL_T_OUTER_TD_S=30), 'o100': dict(FINAL_T_OUTER_TD_S=100),
    'i3': dict(FINAL_T_INNER_TD_S=3), 'i4': dict(FINAL_T_INNER_TD_S=4), 'i6': dict(FINAL_T_INNER_TD_S=6),
    'o30i4': dict(FINAL_T_OUTER_TD_S=30, FINAL_T_INNER_TD_S=4),
    'o100i4': dict(FINAL_T_OUTER_TD_S=100, FINAL_T_INNER_TD_S=4),
    # round 6: the position loop (nearly) off in a longer flare window, FINAL_TD_H_LO_FT / FINAL_TD_H_HI_FT, with the rate loop as it is or a little slower
    'p10': dict(FINAL_T_OUTER_TD_S=100, FINAL_TD_H_LO_FT=10, FINAL_TD_H_HI_FT=60), 'p20': dict(FINAL_T_OUTER_TD_S=100, FINAL_TD_H_LO_FT=20, FINAL_TD_H_HI_FT=100),
    'p30': dict(FINAL_T_OUTER_TD_S=100, FINAL_TD_H_LO_FT=30, FINAL_TD_H_HI_FT=150),
    'p10i3': dict(FINAL_T_OUTER_TD_S=100, FINAL_T_INNER_TD_S=3, FINAL_TD_H_LO_FT=10, FINAL_TD_H_HI_FT=60), 'p20i4': dict(FINAL_T_OUTER_TD_S=100, FINAL_T_INNER_TD_S=4, FINAL_TD_H_LO_FT=20, FINAL_TD_H_HI_FT=100),
    # round 7 (the user, 2026-11-17: wash the bank out so it is 0 deg when the wheels touch): the final's bank command faded to nothing by FINAL_BANK_W_LO_FT of wheel height (the wheel height reads about 1 ft at the first touch), all there at _HI_
    'w1_6': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=6), 'w1_10': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=10), 'w1_15': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15),
    'w2_12': dict(FINAL_BANK_W_LO_FT=2, FINAL_BANK_W_HI_FT=12), 'w3_20': dict(FINAL_BANK_W_LO_FT=3, FINAL_BANK_W_HI_FT=20), 'w1_25': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=25),
    # round 8: with the bank command washed out (1 to 15 ft) the bank at the first wheel still has a spread of 2.7 deg: the turbulence rolling the aircraft; a stiffer roll loop (bank gain K_PHI, rate gain K_P times) under 20 ft, gone at 60 ft
    'g2': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=2, ROLL_LAND_K_P=1.4), 'g3': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=3, ROLL_LAND_K_P=1.7),
    'g4': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=4, ROLL_LAND_K_P=2.0), 'g3k1': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=3, ROLL_LAND_K_P=1.0),
    'g3k25': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=3, ROLL_LAND_K_P=2.5),
    # round 9: round 8's best (g4: bank gain 4, rate gain 2 under 20 ft, washout 1 to 15 ft) around itself: more gain, the damping, the washout (none or shorter), the height window
    'g5': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=5, ROLL_LAND_K_P=2.2), 'g6': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=6, ROLL_LAND_K_P=2.5),
    'g4k15': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=4, ROLL_LAND_K_P=1.5), 'g4k3': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=4, ROLL_LAND_K_P=3.0),
    'g4n': dict(ROLL_LAND_K_PHI=4, ROLL_LAND_K_P=2.0), 'g4w6': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=6, ROLL_LAND_K_PHI=4, ROLL_LAND_K_P=2.0),
    'g4w10': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=10, ROLL_LAND_K_PHI=4, ROLL_LAND_K_P=2.0),
    'g4h40': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=4, ROLL_LAND_K_P=2.0, ROLL_LAND_H_LO_FT=40, ROLL_LAND_H_HI_FT=100),
    'g4h10': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=15, ROLL_LAND_K_PHI=4, ROLL_LAND_K_P=2.0, ROLL_LAND_H_LO_FT=10, ROLL_LAND_H_HI_FT=40),
    # round 10: the combination (bank gain and rate gain, the stiffer loop from 40 ft (all at 40, none at 100), the washout 1 to 10 or 1 to 6 ft) and where the gain stops helping
    'c1': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=10, ROLL_LAND_K_PHI=6, ROLL_LAND_K_P=2.5, ROLL_LAND_H_LO_FT=40, ROLL_LAND_H_HI_FT=100),
    # 2026-11-17, for the report: the same two laws flown again with the wing's bending in the tip heights (gustbench tip_min_flex_ft): law2 = the version-2 landing law (no stiffer roll loop, no washout:
    # the files `cur` were flown with it before c1 became the default), law3 = the laws as they are now (c1's numbers are the defaults)
    'law2': dict(FINAL_BANK_W_LO_FT=0, FINAL_BANK_W_HI_FT=0, ROLL_LAND_K_PHI=1, ROLL_LAND_K_P=1),
    'law3': {},                                                                                          # (flown before the decrab change below)
    'law4': {},                                                                                          # 2026-11-17: the same, after the decrab's clip went to 20 deg in the air (laws.py DECRAB_CLIP_DEG): laws version 4
    'c2': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=10, ROLL_LAND_K_PHI=8, ROLL_LAND_K_P=3.0, ROLL_LAND_H_LO_FT=40, ROLL_LAND_H_HI_FT=100),
    'c3': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=6, ROLL_LAND_K_PHI=6, ROLL_LAND_K_P=2.5, ROLL_LAND_H_LO_FT=40, ROLL_LAND_H_HI_FT=100),
    'c5': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=10, ROLL_LAND_K_PHI=10, ROLL_LAND_K_P=3.5, ROLL_LAND_H_LO_FT=40, ROLL_LAND_H_HI_FT=100),
    'c6': dict(FINAL_BANK_W_LO_FT=1, FINAL_BANK_W_HI_FT=10, ROLL_LAND_K_PHI=6, ROLL_LAND_K_P=2.5, ROLL_LAND_H_LO_FT=60, ROLL_LAND_H_HI_FT=150),
    # the aim offset for the flare's drift (the user, 2026-11-17: offset the drift and the bank is not needed at touchdown): the line steered to is moved upwind by k ft per kt of the crosswind component;
    # early = from 1,000 ft of wheel height, all of it at 700 (the law's own shape); late = from 400, all at 150 ft (it comes in just before the flare)
    'a01': dict(_aim=1, FINAL_AIM_FT_PER_KT=0.1), 'a02': dict(_aim=1, FINAL_AIM_FT_PER_KT=0.2), 'a03': dict(_aim=1, FINAL_AIM_FT_PER_KT=0.3), 'a05': dict(_aim=1, FINAL_AIM_FT_PER_KT=0.5),
    'a02L': dict(_aim=1, FINAL_AIM_FT_PER_KT=0.2, FINAL_AIM_FROM_FT=400, FINAL_AIM_FULL_FT=150),
    'a03L': dict(_aim=1, FINAL_AIM_FT_PER_KT=0.3, FINAL_AIM_FROM_FT=400, FINAL_AIM_FULL_FT=150),
    'a05L': dict(_aim=1, FINAL_AIM_FT_PER_KT=0.5, FINAL_AIM_FROM_FT=400, FINAL_AIM_FULL_FT=150),
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
    elif name == 'final':           # the confirmation set (2026-11-17): seeds 701 to 712, three weights, nothing was chosen on these
        for w in (26750, 20800, 12450):
            for _, words in winds():
                for seed in range(701, 713):
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
        word = ' aim=1' if DESIGNS[d].get('_aim') else ''
        open(cf, 'w').write('\n'.join(c + word for c in cases) + '\n')
        of = path(setname, d, 'jsonl')
        if os.path.exists(of):
            os.remove(of)
        sets = []
        for k, v in DESIGNS[d].items():
            if not k.startswith('_'):
                sets += ['--set', 'laws.%s=%g' % (k, v)]
        cmd = ['qrun', 'env', 'GB_ELEV=171', sys.executable, os.path.join(HERE, 'gustbench.py')] + FLAGS + sets + ['--from', cf, '--out', of]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(path(setname, d, 'log'), 'w'), cwd=os.path.dirname(HERE)))
    for p in procs:
        p.wait()


def load(setname, design):
    rows = {}
    for line in open(path(setname, design, 'jsonl')):
        r = json.loads(line)
        rows[r['name'].replace(' aim=1', '')] = r              # the aim designs' case names carry the word
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
    print('%-9s %7s %6s %7s %7s %7s %6s %6s %6s %5s %6s | %7s %7s %6s %6s %6s | %s' % ('design', 'mean', 'sd', 'mean|x|', 'p90|x|', 'p95|x|', 'worst', '>15 ft', '>30 ft', 'hard', 'bank', 'bank td', 'td max', 'tip<.5', 'tip<0', 'tip min', 'x change vs the first design (paired)'))
    base = np.array([abs(data[designs[0]][k]['xt_td_ft']) for k in keys], float)
    for d in designs:
        x = np.array([data[d][k]['xt_td_ft'] for k in keys], float)
        sk = np.array([data[d][k]['sink_ms'] for k in keys], float)
        bk = np.array([data[d][k]['below500']['bank'] for k in keys], float)
        ax = abs(x)
        diff = ax - base
        lo, hi = boot(diff)
        tail = '' if d == designs[0] else '%+.1f [%.1f, %.1f], better %d of %d' % (diff.mean(), lo, hi, (diff < 0).sum(), len(diff))
        tip = np.array([(data[d][k].get('tip_min_ft') if data[d][k].get('tip_min_ft') is not None else 99.0) for k in keys], float)
        btd = np.array([abs(data[d][k].get('phi_td_deg', 0.0)) for k in keys], float)
        print('%-9s %7.1f %6.1f %7.1f %7.1f %7.1f %6.1f %6d %6d %5d %6.1f | %7.2f %7.2f %6d %6d %6.2f | %s' % (d, x.mean(), x.std(), ax.mean(), np.percentile(ax, 90), np.percentile(ax, 95), ax.max(), (ax > 15).sum(), (ax > 30).sum(), (sk > 2).sum(), bk.mean(), btd.mean(), btd.max(), (tip < 0.5).sum(), (tip < 0).sum(), tip.min(), tail))


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
