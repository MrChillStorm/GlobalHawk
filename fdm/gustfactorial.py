#!/usr/bin/env python3
"""The effect of the approach speed's addition and of the gust system, alone and together, with its uncertainty (docs/PLAN.md, "Gusts: find out first", "Protocol for the report's comparison").

    python3 fdm/gustfactorial.py [--set test|train] [--dir fdm/out/gust] [--out fdm/report/results/gust_factorial.json]

Four arms of the same cases: neither; the speed alone (the aircraft's own pick of the addition, ap/approach-add-auto 1); the stabilisation alone (the gust system, ap/gust-sys 1); both. For the discrete gusts,
in which the pick is nothing (calm air), a fixed +10 kt is flown as well, alone and with the system (arms `fixed`, `fixedboth`), as a supplement. The cases are the bench's (fdm/gustbench.py: the landing
from 5 nmi out in the landing task's laws):
  --set test    the frozen test set (fdm/out/gust/test_d.cases, test_t.cases): discrete gusts the design never saw, at three weights, and turbulence seeds 101 to 148. Files test_d.<arm>.jsonl, test_t.<arm>.jsonl
  --set train   the flights the picker's tables were fitted on (opt.cases, seeds 1 to 16; opt.add0.* and opt.auto.*): descriptive only, not evidence of the effect (it is where the design was made)
Per arm and weather: the flights that landed hard (a sink over 2 m/s, the structural flag, or no touchdown), the sink's mean and 95th percentile, the flights in which the angle-of-attack protection acted
below 500 ft (a margin under 0), the distance off the centreline and the nose's heading error at the first wheel (95th percentiles) and the distance from the aiming point to the end of the rollout (mean).
Per contrast (each arm against neither, both against each alone), paired by case: the difference in the hard landings with the exact McNemar test on the discordant pairs (a Bonferroni level of 0.05 / 3
for the primary measure), and the mean paired differences of the sink, the distance off the line and the landing's length with 95 % bootstrap intervals (10,000 resamples of the cases).
"""
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'out', 'gust')
OUT = os.path.join(HERE, 'report', 'results', 'gust_factorial.json')
SET = 'test'
if '--dir' in sys.argv:
    D = sys.argv[sys.argv.index('--dir') + 1]
if '--out' in sys.argv:
    OUT = sys.argv[sys.argv.index('--out') + 1]
if '--set' in sys.argv:
    SET = sys.argv[sys.argv.index('--set') + 1]

ARMS = (('neither', 'neither'), ('speed', 'the speed alone'), ('stab', 'the stabilisation alone'), ('both', 'both'), ('fixed', 'fixed +10 kt alone'), ('fixedboth', 'fixed +10 kt and the system'))
CONTRASTS = (('speed', 'neither'), ('stab', 'neither'), ('both', 'neither'), ('both', 'speed'), ('both', 'stab'), ('fixed', 'neither'), ('fixedboth', 'stab'))
BOOT = 10000


def rows(path):
    return [json.loads(line) for line in open(path)] if os.path.exists(path) else []


def hard(r):
    return (not r['down']) or r['sink_ms'] > 2.0 or r.get('overstress', 0) > 0


def metrics(rs):
    down = [r for r in rs if r['down']]
    mins = np.array([r['below500']['alpha_margin'] for r in down]) if down else np.array([0.0])
    return dict(n=len(rs), hard=int(sum(hard(r) for r in rs)), flag=int(sum(1 for r in rs if r.get('overstress', 0) > 0)), sink_mean=float(np.mean([r['sink_ms'] for r in down])),
                sink50=float(np.percentile([r['sink_ms'] for r in down], 50)), sink95=float(np.percentile([r['sink_ms'] for r in down], 95)), events=int(np.sum(mins < 0)),
                line95=float(np.percentile([abs(r['xt_td_ft']) for r in down], 95)), nose95=float(np.percentile([r['nose_off_deg'] for r in down], 95)), total=float(np.mean([r['total_ft'] for r in down])))


def mcnemar_exact(b, c):
    """two-sided exact p for the discordant pairs b (hard in the first arm only) and c (in the second only)"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n)


def boot(d, rng):
    d = np.asarray(d, float)
    if len(d) == 0:
        return (float('nan'),) * 3
    idx = rng.integers(0, len(d), (BOOT, len(d)))
    m = d[idx].mean(axis=1)
    return (float(d.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)))


def contrast(ra, rb, rng):
    """arm A against arm B, paired by case name"""
    a = {r['name'].replace(' gs=1', '').replace(' auto=1', '').replace(' add=10', '').strip(): r for r in ra}
    b = {r['name'].replace(' gs=1', '').replace(' auto=1', '').replace(' add=10', '').strip(): r for r in rb}
    names = [n for n in a if n in b]
    ba = sum(1 for n in names if hard(a[n]) and not hard(b[n]))
    bb = sum(1 for n in names if hard(b[n]) and not hard(a[n]))
    both_down = [n for n in names if a[n]['down'] and b[n]['down']]
    return dict(pairs=len(names), hard_a=int(sum(hard(a[n]) for n in names)), hard_b=int(sum(hard(b[n]) for n in names)), only_a=ba, only_b=bb, p_hard=mcnemar_exact(ba, bb),
                d_sink=boot([a[n]['sink_ms'] - b[n]['sink_ms'] for n in both_down], rng), d_line=boot([abs(a[n]['xt_td_ft']) - abs(b[n]['xt_td_ft']) for n in both_down], rng),
                d_total=boot([a[n]['total_ft'] - b[n]['total_ft'] for n in both_down if 'total_ft' in a[n] and 'total_ft' in b[n]], rng))


def weathers():
    """[(name, {arm: [records]})]"""
    out = []
    if SET == 'test':
        arms_of = lambda base: {k: rows(os.path.join(D, '%s.%s.jsonl' % (base, k))) for k, _ in ARMS}
        d = arms_of('test_d')
        for kind, tag in (('a', 'a lost or gained headwind'), ('v', 'a downdraught'), ('x', 'a gust across')):
            sub = {k: [r for r in v if ' g=%s:' % kind in r['name']] for k, v in d.items()}
            if sub['neither']:
                out.append(('discrete: %s (%d cases)' % (tag, len(sub['neither'])), sub))
        t = arms_of('test_t')
        for steady, label in ((False, 'turbulence'), (True, 'turbulence with a steady wind at 45 deg')):
            for w20 in (30, 40, 50, 60) if not steady else (30, 40, 50):
                sub = {k: [r for r in v if ('hw=' in r['name']) == steady and re.search(r'lo=%d ' % w20, r['name'] + ' ')] for k, v in t.items()}
                if sub['neither']:
                    out.append(('%s, a wind at 20 ft of %d kt (%d sequences)' % (label, w20, len(sub['neither'])), sub))
    else:
        for steady, label in ((False, 'turbulence'), (True, 'turbulence with a steady wind at 45 deg')):
            for w20 in (30, 40, 50, 60) if not steady else (30, 40, 50):
                def pick(f):
                    return [r for r in rows(os.path.join(D, f)) if ('hw=' in r['name']) == steady and re.search(r'lo=%d ' % w20, r['name'] + ' ')]
                sub = {'neither': pick('opt.add0.off.jsonl'), 'stab': pick('opt.add0.on.jsonl'), 'speed': pick('opt.auto.off.jsonl'), 'both': pick('opt.auto.on.jsonl')}
                if sub['neither']:
                    out.append(('%s, a wind at 20 ft of %d kt (%d sequences; fitting set)' % (label, w20, len(sub['neither'])), sub))
    return out


def main():
    rng = np.random.default_rng(20261116)
    result = []
    for name, arms in weathers():
        entry = dict(weather=name, set=SET, arms={}, contrasts={})
        print('\n%s' % name)
        print('  %-30s %4s  %5s  %6s  %6s  %6s  %6s  %7s  %7s  %7s' % ('', 'n', 'hard', 'sink', 'median', 'sink95', 'events', 'line95', 'nose95', 'total'))
        for key, label in ARMS:
            rs = arms.get(key) or []
            if not rs:
                continue
            m = metrics(rs)
            entry['arms'][key] = m
            print('  %-30s %4d  %5d  %6.2f  %6.2f  %6.2f  %6d  %7.1f  %7.1f  %7.0f' % (label, m['n'], m['hard'], m['sink_mean'], m['sink50'], m['sink95'], m['events'], m['line95'], m['nose95'], m['total']))
        for a, b in CONTRASTS:
            if arms.get(a) and arms.get(b):
                c = contrast(arms[a], arms[b], rng)
                entry['contrasts']['%s-%s' % (a, b)] = c
                print('    %-18s hard %3d vs %3d (only %d / only %d, p %.3f)   d sink %+.2f [%+.2f, %+.2f] m/s   d line %+.1f [%+.1f, %+.1f] ft   d landing %+.0f [%+.0f, %+.0f] ft' % (
                    '%s - %s' % (a, b), c['hard_a'], c['hard_b'], c['only_a'], c['only_b'], c['p_hard'], *c['d_sink'], *c['d_line'], *c['d_total']))
        result.append(entry)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, 'w'), indent=1)
    print('\nwritten', OUT)


if __name__ == '__main__':
    main()
