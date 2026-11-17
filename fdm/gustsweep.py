#!/usr/bin/env python3
"""The gust sweeps (docs/PLAN.md, "Gusts: find out first"): writes fdm/out/gust/<name>.cases, a case a line, for fdm/gustbench.py --from.

    python3 fdm/gustsweep.py            writes them all and prints how many cases each has
    qrun python3 fdm/gustbench.py --out fdm/out/gust/<name>.jsonl --from fdm/out/gust/<name>.cases
"""
import itertools
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'gust')
HEIGHTS = (500, 300, 200, 150, 100, 70, 50, 30, 15)


def one_axis(axis, sizes, weights=(20800,), rises=(2,), holds=(2,), base='', heights=HEIGHTS):
    for w, kt, h, r, hold in itertools.product(weights, sizes, heights, rises, holds):
        yield ('w=%d %s g=%s:%g@%d:%g:%g' % (w, base, axis, kt, h, r, hold)).replace('  ', ' ')


SWEEPS = {
    # (1) one axis at a time, calm background, 20,800 lb
    'a1': list(one_axis('a', (-30, -25, -20, -15, -10, -5, 5, 10, 15, 20, 30))),
    'x1': list(one_axis('x', (-40, -30, -20, -10, 10, 20, 30, 40))),
    'v1': list(one_axis('v', (-20, -15, -10, -5, 5, 10, 15, 20))),
    # (2) the light and the heavy weight
    'a2': list(one_axis('a', (-30, -25, -20, -15, -10, -5, 5, 10, 15, 20, 30), weights=(12000, 26000))),
    'x2': list(one_axis('x', (-40, -30, -20, -10, 10, 20, 30, 40), weights=(12000, 26000))),
    'v2': list(one_axis('v', (-20, -15, -10, -5, 5, 10, 15, 20), weights=(12000, 26000))),
    # (3) rise time: from a step (0.5 s) to a slow one (8 s), the sizes that hurt, three heights
    'r3': list(one_axis('a', (-25, -20, -15, -10), rises=(0.5, 1, 2, 4, 8), heights=(150, 100, 50)))
          + list(one_axis('v', (-20, -15, -10), rises=(0.5, 1, 2, 4, 8), heights=(150, 100, 50)))
          + list(one_axis('x', (-30, 30), rises=(0.5, 1, 2, 4, 8), heights=(100, 50, 15))),
    # (4) a steady wind with the gust on top: headwind 10 and 20, a tailwind of 10, a crosswind of 10, 20 and 30 from the right
    'b4': [c for base in ('hw=10', 'hw=20', 'hw=-10', 'xw=10', 'xw=20', 'xw=30')
           for c in list(one_axis('a', (-20, -10, 10), base=base, heights=(150, 100, 50, 15)))
           + list(one_axis('v', (-15, -10, 10), base=base, heights=(150, 100, 50, 15)))
           + list(one_axis('x', (-20, 20), base=base, heights=(150, 100, 50, 15)))],
    # (5) JSBSim's own turbulence: the wind at 20 ft, the severity, eight sequences
    'tu5': ['w=20800 tu=%d:%d seed=%d' % (w20, sev, seed) for w20 in (15, 25, 35, 45, 60) for sev in (3, 5, 7) for seed in range(1, 9)],
    # (5b) the bench's own low-level turbulence (MIL-F-8785C's Dryden below 1,000 ft): the wind at 20 ft W20, sixteen sequences; and with that wind blowing steadily at 45 degrees to the runway
    'lo6': ['w=20800 lo=%d seed=%d' % (w20, seed) for w20 in (10, 20, 30, 40, 50, 60) for seed in range(1, 17)],
    'lo6w': ['w=20800 hw=%d xw=%d lo=%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, seed) for w20 in (20, 30, 40, 50) for seed in range(1, 13)],
    # (6) the same approach flown by the mission manager (the stabilised-approach gate, the missed approach): the gusts that hurt, five heights, and the low-level turbulence
    'm6': ['w=20800 mgr=1 sec=1500 g=%s:%g@%d:2:2' % (ax, kt, h) for ax, sizes in (('a', (-15, -20, -30)), ('v', (-10, -15, -20)), ('x', (-30, 30))) for kt in sizes for h in (500, 300, 200, 150, 100, 50)]
           + ['w=20800 mgr=1 sec=1500 lo=%d seed=%d' % (w20, seed) for w20 in (40, 50, 60) for seed in range(1, 7)]
           + ['w=20800 mgr=1 sec=1500 hw=%d xw=%d lo=%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, seed) for w20 in (40, 50) for seed in range(1, 7)],
    # (7) the approach speed's addition (fdm/gustbench.py --add KT, flown for 0, 5, 10, 15 and 20 kt, off and on): the gusts that hurt, the bench's turbulence alone and with a steady wind at 45 deg
    'ad': ['w=20800 g=a:%d@%d:2:2' % (kt, h) for kt in (-10, -15, -20, -25, -30) for h in (200, 150, 100, 50)]
          + ['w=20800 g=v:%d@%d:2:2' % (kt, h) for kt in (-10, -15, -20) for h in (150, 100, 50)]
          + ['w=20800 g=x:%d@%d:2:2' % (kt, h) for kt in (-30, 30) for h in (100, 50)]
          + ['w=20800 lo=%d seed=%d' % (w20, seed) for w20 in (30, 40, 50, 60) for seed in range(1, 9)]
          + ['w=20800 hw=%d xw=%d lo=%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, seed) for w20 in (30, 40, 50) for seed in range(1, 9)]
          + ['w=%d' % w for w in (12000, 20800, 26000)]
          + ['w=%d hw=%d g=a:-15@100:2:2' % (w, hw) for w in (12000, 26000) for hw in (0, 15)],
    # (7b) the rules of thumb, applied to the bench's turbulence cases: the addition each case's own wind and gusts ask for. Glider: half the wind and the whole gust spread; airliner: half the headwind
    # component and the whole gust increment, 5 to 20 kt. The gust spread is taken as twice the along sigma at 30 ft (MIL-F-8785C low altitude: sigma_u = 0.1 W20 / (0.177 + 0.000823 h)^0.4), the
    # steady wind as the case's (W20 at 45 deg to the runway: a headwind component 0.7 W20). Both capped at 20 kt (what the aircraft's addition was flown to).
    'rule': [c.replace('w=20800', 'w=20800 add=%d' % round(rule)) for c, rule in (
        ('w=20800 lo=%d seed=%d' % (w20, seed), min(20.0, 2 * 0.1 * w20 / (0.177 + 0.000823 * 30) ** 0.4)) for w20 in (30, 40, 50, 60) for seed in range(1, 9))]
    + [c.replace('w=20800', 'w=20800 add=%d' % round(rule)) for c, rule in (
        ('w=20800 hw=%d xw=%d lo=%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, seed), min(20.0, 0.5 * 0.7 * w20 + 2 * 0.1 * w20 / (0.177 + 0.000823 * 30) ** 0.4)) for w20 in (30, 40, 50) for seed in range(1, 9))],
    # (8) the trade-off curve of the approach speed's addition: the bench's turbulence, 16 sequences each (24 in the first, weak-turbulence flights), alone (wind at 20 ft 30 to 60 kt) and with that wind blowing steadily at 45 deg to the runway
    # (30 to 50 kt); flown with --add 0, 3, 6, 9, 12, 15 and 18, system off and on (docs/PLAN.md, "Gusts: find out first", the optimum)
    'opt': ['w=20800 lo=%d seed=%d' % (w20, seed) for w20 in (30, 40, 50, 60) for seed in range(1, 17)]
           + ['w=20800 hw=%d xw=%d lo=%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, seed) for w20 in (30, 40, 50) for seed in range(1, 17)],
    # (9) the test set of the report's comparison (docs/PLAN.md, "Protocol for the report's comparison"): written before the picker's tables were fitted, flown once, after they were frozen. Discrete gusts of
    # sizes, heights and rise times the design never saw, at three weights; and the bench's turbulence, seeds 101 to 148, the same weathers as `opt` (those flown without a steady wind first)
    'test_d': ['w=%d g=%s:%d@%d:%g:2' % (w, ax, kt, h, rise) for w in (15000, 20800, 25000) for ax, sizes in (('a', (-12, -17, -22, -27)), ('v', (-8, -12, -17)), ('x', (-25, 25)))
               for kt in sizes for h in (180, 130, 80, 40) for rise in (1.5, 3)],
    'test_t': ['w=20800 lo=%d seed=%d' % (w20, seed) for w20 in (30, 40, 50, 60) for seed in range(101, 149)]
              + ['w=20800 hw=%d xw=%d lo=%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, seed) for w20 in (30, 40, 50) for seed in range(101, 149)],
    # (10) the airliners' rules, on fresh seeds (docs/PLAN.md, "Protocol addendum: the airliners' rules"): the seven weathers of the test set, seeds 201 to 248
    'rules_t': ['w=20800 lo=%d seed=%d' % (w20, seed) for w20 in (30, 40, 50, 60) for seed in range(201, 249)]
               + ['w=20800 hw=%d xw=%d lo=%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, seed) for w20 in (30, 40, 50) for seed in range(201, 249)],
    # (11) the FlightGear scenario's weathers, offline (docs/PLAN.md, "The same flight in a gusty crosswind"): the wind from 310 at the surface, runway 22L (heading 227.5): 28 kt (hw 3.7, xw 27.8) and
    # 36 kt (hw 4.8, xw 35.7) abeam, the milspec turbulence at W20 = the surface wind (FlightGear's GUSTS 0.85: 0.1 times the wind at 20 ft), and for the 36 kt the shear: 85 kt at 500 ft (shr 2.36).
    # The landing task alone (48 seeds, the ten arms), and the same flown by the mission manager (mgr=1: the stabilised-approach gate and the missed approach; 24 seeds, three arms)
    'crazy_t': ['w=26750 hw=4 xw=28 lo=28 tua=5 seed=%d' % seed for seed in range(201, 249)] + ['w=26750 hw=5 xw=36 lo=36 shr=2.36 tua=5 seed=%d' % seed for seed in range(201, 249)],
    'crazy_m': ['w=26750 mgr=1 sec=1800 hw=4 xw=28 lo=28 tua=5 seed=%d' % seed for seed in range(201, 225)] + ['w=26750 mgr=1 sec=1800 hw=5 xw=36 lo=36 shr=2.36 tua=5 seed=%d' % seed for seed in range(201, 225)],
    'tu5x': ['w=20800 xw=%d tu=%d:%d seed=%d' % (xw, w20, 5, seed) for xw in (10, 20) for w20 in (25, 35, 45) for seed in range(1, 9)],
}

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for name, cases in SWEEPS.items():
        with open(os.path.join(OUT, name + '.cases'), 'w') as fh:
            fh.write('\n'.join(cases) + '\n')
        print('%-6s %4d cases' % (name, len(cases)))
