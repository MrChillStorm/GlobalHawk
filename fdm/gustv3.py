#!/usr/bin/env python3
"""The airliners' rule arms flown again on the laws as they stand now, at two weights, on fresh seeds (docs/PLAN.md, "The airliners' rules, again"; the user, 2026-11-17: "Yes, run the four arms again").

    python3 fdm/gustv3.py cases      writes fdm/out/gust_v3/rules_t.cases
    python3 fdm/gustv3.py run        records the laws' checksums, queues the flights (`qrun`, two at a time; run it with run_in_background) and waits
    python3 fdm/gustv3.py count      the flights
    python3 fdm/gustv3.py summary    the table per weight and pooled, written to fdm/report/results/gust_factorial_v3.json

Why: the version 2 flights of the rules (fdm/gustv2.py) were flown on the laws before the stiffer roll loop and the bank washout (version 3), at one weight (20,800 lb) in the turbulence set. This set has the same
seven weathers (the turbulence alone at a wind at 20 ft of 20, 30, 40 and 50 kt, and with a steady wind at 45 deg at 30, 40 and 50 kt, JSBSim's own MIL-F-8785C turbulence at the field's height, `GB_ELEV=171`),
at 12,450 and 26,750 lb, 24 seeds a weather and weight (801 to 824: version 2 used 501 to 548 and 601 to 648; the lateral sets 301 to 306, 401 to 408 and 701 to 712), so 168 sequences a weight and 336 in all.
The arms are the ones the report's argument rests on: no addition; the aircraft's own pick with the stabilisation; Boeing's rule and Airbus's, each alone and with the stabilisation (fdm/gustv2.py ARMS).
The laws are frozen for the run (the checksums are written to fdm/out/gust_v3/laws.md5): the aim offset is off, as it ships.
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gustv2  # noqa: E402

OUT = os.path.join(HERE, 'out', 'gust_v3')
REPORT = os.path.join(HERE, 'report', 'results', 'gust_factorial_v3.json')
WEIGHTS = (12450, 26750)
SEEDS = range(801, 825)
ARMS = ('neither', 'both', 'boeing', 'boeingstab', 'airbus', 'airbusstab')
SET = 'rules_t'


def cases():
    out = []
    for w in WEIGHTS:
        out += ['w=%d tu=%d:%d seed=%d' % (w, w20, gustv2.SEV, seed) for w20 in (20, 30, 40, 50) for seed in SEEDS]
        out += ['w=%d hw=%d xw=%d tu=%d:%d seed=%d' % (w, round(w20 * 0.7), round(w20 * 0.7), w20, gustv2.SEV, seed) for w20 in (30, 40, 50) for seed in SEEDS]
    return out


def write_cases():
    os.makedirs(OUT, exist_ok=True)
    c = cases()
    open(os.path.join(OUT, SET + '.cases'), 'w').write('\n'.join(c) + '\n')
    print('%s %d cases' % (SET, len(c)))


def freeze():
    lines = []
    for rel in ('fdm/laws.py', 'GlobalHawk/Systems/laws.xml', 'GlobalHawk/Nasal/defaults.nas', 'fdm/gustbench.py'):
        p = os.path.join(HERE, '..', rel)
        lines.append('%s  %s' % (hashlib.md5(open(p, 'rb').read()).hexdigest(), rel))
    open(os.path.join(OUT, 'laws.md5'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


def run():
    write_cases()
    freeze()
    procs = []
    for arm in ARMS:
        of = os.path.join(OUT, '%s.%s.jsonl' % (SET, arm))
        if os.path.exists(of):
            os.remove(of)
        cmd = ['qrun', 'env', 'GB_ELEV=171', sys.executable, os.path.join(HERE, 'gustbench.py')] + gustv2.ARMS[arm] + ['--from', os.path.join(OUT, SET + '.cases'), '--out', of]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(of.replace('.jsonl', '.log'), 'w'), cwd=os.path.dirname(HERE)))
    for p in procs:
        p.wait()


def summary():
    import gustfactorial as GF
    t = {a: GF.rows(os.path.join(OUT, '%s.%s.jsonl' % (SET, a))) for a in ARMS}
    if not all(t.values()):
        raise SystemExit('the flights are not all there: ' + ', '.join('%s %d' % (a, len(v)) for a, v in t.items()))
    rng = np.random.default_rng(20261117)
    contrasts = (('both', 'neither'), ('boeing', 'neither'), ('airbus', 'neither'), ('both', 'boeing'), ('both', 'airbus'), ('both', 'boeingstab'), ('both', 'airbusstab'))      # the first prediction is in docs/PLAN.md
    out = []
    for label, sel in (('seven turbulence weathers pooled, both weights', lambda r: True), ('seven turbulence weathers, 12,450 lb', lambda r: 'w=12450 ' in r['name']),
                       ('seven turbulence weathers, 26,750 lb', lambda r: 'w=26750 ' in r['name'])):
        sub = {a: [r for r in v if sel(r)] for a, v in t.items()}
        n = len(sub['neither'])
        entry = dict(weather='%s (%d sequences)' % (label, n), set='rules_v3', arms={}, contrasts={})
        print('\n%s' % entry['weather'])
        print('  %-12s %4s %5s %6s %6s %6s %6s %7s %7s' % ('arm', 'n', 'hard', 'sink', 'sink95', 'events', 'line95', 'nose95', 'total'))
        for a in ARMS:
            m = GF.metrics(sub[a])
            entry['arms'][a] = m
            print('  %-12s %4d %5d %6.2f %6.2f %6d %7.1f %7.1f %7.0f' % (a, m['n'], m['hard'], m['sink_mean'], m['sink95'], m['events'], m['line95'], m['nose95'], m['total']))
        for a, b in contrasts:
            c = GF.contrast(sub[a], sub[b], rng)
            entry['contrasts']['%s-%s' % (a, b)] = c
            print('    %-20s hard %3d vs %3d (only %d / only %d, p %.3f)  d sink %+.2f [%+.2f, %+.2f]  d landing %+.0f [%+.0f, %+.0f] ft' % ('%s - %s' % (a, b), c['hard_a'], c['hard_b'], c['only_a'], c['only_b'], c['p_hard'],
                                                                                                                                   *c['d_sink'], *c['d_total']))
        margins = {a: np.array([r['below500']['alpha_margin'] for r in sub[a] if r['down']]) for a in ARMS}
        entry['margin_median'] = {a: float(np.median(m)) for a, m in margins.items()}
        entry['over_limit_2deg'] = {a: float(np.mean(m < -2.0)) for a, m in margins.items()}
        print('  median room under the alpha limit (deg):', {a: round(v, 2) for a, v in entry['margin_median'].items()})
        out.append(entry)
    json.dump(out, open(REPORT, 'w'))
    print('\nwrote', REPORT)


def main():
    a = sys.argv[1:]
    if not a or a[0] == 'cases':
        write_cases()
    elif a[0] == 'count':
        print(len(cases()) * len(ARMS), 'flights')
    elif a[0] == 'run':
        run()
    elif a[0] == 'summary':
        summary()
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
