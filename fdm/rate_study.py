#!/usr/bin/env python3
"""Does the model's frame rate matter? The take-off, landings and the mission's checks run at 120, 240, 480 and 960 Hz.

    python3 fdm/rate_study.py            about two minutes (a queue job: qrun python3 fdm/rate_study.py)

FlightGear runs the flight model at 120 Hz. Every check script reads fdm/harness.HZ, which GH_HZ in the environment
changes, so phase 7b (take-off, landings, rollouts, the mission, all flown by the laws) is run at each rate and the
figures it prints are set side by side. What differs between rates is the step's error, not the model's: a result that
moves with the rate is not settled by the model's data. The cost of a frame is printed too (the model alone: the
properties FlightGear copies in and out each frame are not in it).

Limits (written before the first run): every figure the checks hold to a record stays inside its limit at all four
rates, and the figures at 120 Hz differ from those at 960 Hz by less than the records' own scatter: lift-off speed
under 5 kt and pitch under 1 deg, touchdown sink under 0.1 m/s, pitch under 0.3 deg, speed under 2 kt.
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RATES = (120, 240, 480, 960)


def run(hz):
    env = dict(os.environ, GH_HZ=str(hz))
    out = subprocess.run([sys.executable, os.path.join(HERE, 'phase7b_checks.py')], env=env, capture_output=True, text=True).stdout
    keep = {}
    for line in out.splitlines():
        m = re.match(r'(M3|M7|M8)\s+(.*?)\s{2,}(pass|MISS)\s+(.*)', line)
        if m:
            keep[(m.group(1), m.group(2))] = (m.group(3), m.group(4))
    return keep, re.findall(r'(\d+) checks, (\d+) pass', out)


def number(text, pattern):
    m = re.search(pattern, text)
    return float(m.group(1)) if m else float('nan')


if __name__ == '__main__':
    runs = {}
    for hz in RATES:
        t0 = time.time()
        runs[hz] = run(hz)
        print('%4d Hz: %s checks, %s pass (%.0f s of wall time)' % (hz, *runs[hz][1][0], time.time() - t0) if runs[hz][1] else '%4d Hz: no result' % hz, flush=True)
    print('\n%-34s' % '' + ''.join('%12d Hz' % hz for hz in RATES))
    rows = [('take-off lift-off speed, KEAS', 'M3', 'take', r'liftoff at (\d+) KEAS'), ('take-off lift-off pitch, deg', 'M3', 'take', r'KEAS and ([\d.]+) deg'),
            ('take-off 130 KIAS at, s', 'M3', 'take', r'130 KIAS ([\d.]+) s')]
    for label, tag, key, pat in rows:
        print('%-34s' % label + ''.join('%15.1f' % number(next(v[1] for k, v in runs[hz][0].items() if k[0] == tag and key in k[1]), pat) for hz in RATES))
    for n, name in enumerate(('2013', '2014', 'mission')):
        for label, pat in (('sink, m/s', r'sink ([\d.]+) m/s'), ('pitch, deg', r'pitch ([\d.]+) deg'), ('KEAS', r'([\d.]+) KEAS'),
                           ('ft past the aiming point', r'(\d+) ft past')):
            vals = []
            for hz in RATES:
                text = next((v[1] for k, v in runs[hz][0].items() if k[0] == 'M7' and name in k[1]), '')
                vals.append(number(text, pat))
            print('%-34s' % ('%s touchdown %s' % (name, label)) + ''.join('%15.2f' % v for v in vals))
    for name in ('2013', '2014', 'mission'):
        vals = [number(next((v[1] for k, v in runs[hz][0].items() if k[0] == 'M8' and name in k[1]), ''), r'deceleration ([\d.]+) g') for hz in RATES]
        print('%-34s' % ('%s rollout deceleration, g' % name) + ''.join('%15.3f' % v for v in vals))
    ok = all(c and c[0][0] == c[0][1] for _, c in runs.values())
    print('\nevery check passes at every rate: %s' % ok)
