#!/usr/bin/env python3
"""A matrix of FlightGear flights, one after the other, each recorded (fdm/fg_scenario.py's CSV): the box at EFHK, runway 22L, in a steady crosswind, at three fuel loads.

    python3 fdm/fg_matrix.py [--aim] [NAME ...]        fly the conditions (all, or the named ones: full_x36, light_x9, ...); a recording that exists is skipped
                                                       --aim: with the aim offset on, to fdm/out/fg_matrix_aim (fdm/flare_drift.py takes that folder's files too)

Weights: full = the aircraft's own tanks (15,300 lb of fuel, 26,750 lb), half = 7,650 lb of fuel, light = 1,000 lb of fuel (the tanks share it equally: FUEL_LB).
Crosswinds: the wind from 310 at the surface, the runway's course 227.5, so 99 % of the wind is across the runway: 9, 18, 27 and 36 kt (METARWIND 31009KT ... 31036KT). Steady wind and nothing else: no
gusts, no shear (the 36 kt flights of docs/PLAN.md had the shear, which lifted the wind at the wheels to 55 kt): the point is the drift the landing's flare gives for a known crosswind and weight, which
a tuning formula can take out. Recordings go to fdm/out/fg_matrix/NAME.csv, a log of each beside it.

One FlightGear at a time, started only on an unlocked screen (a locked one is waited out, not retried: FlightGear does not come up) and with nothing else answering on port 5477; each flight's FlightGear
is stopped when the flight ends. The recordings are the data for docs/PLAN.md, "The flare drift as a table".
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AIM = '--aim' in sys.argv          # --aim: the aim offset on (ap/final-aim 1: the weight-and-crosswind formula, laws.py FINAL_AIM_FT_PER_KT_KLB), recorded to fdm/out/fg_matrix_aim
OUT = os.path.join(HERE, 'out', 'fg_matrix_aim' if AIM else 'fg_matrix')
if '--out' in sys.argv:            # --out NAME: record to fdm/out/NAME (a variant of the laws: the earlier recordings stay)
    OUT = os.path.join(HERE, 'out', sys.argv[sys.argv.index('--out') + 1])
WEIGHTS = (('full', None), ('light', '1000'), ('half', '7650'))
CROSS = (36, 9, 27, 18)
ORDER = [('full', 36), ('light', 36), ('light', 9), ('full', 9), ('half', 36), ('half', 9), ('full', 27), ('light', 27), ('half', 27), ('full', 18), ('light', 18), ('half', 18)]


def locked():
    r = subprocess.run('ioreg -n Root -d1 -a', shell=True, capture_output=True, text=True).stdout
    return 'CGSSessionScreenIsLocked' in r and '<true/>' in r.split('CGSSessionScreenIsLocked')[1][:40]


def flightgear_pids():
    r = subprocess.run("ps -eo pid,command | grep '[M]acOS/FlightGear '", shell=True, capture_output=True, text=True).stdout
    return [int(l.split()[0]) for l in r.splitlines() if l.strip()]


def port_busy():
    return bool(subprocess.run('lsof -nP -iTCP:5477 -sTCP:LISTEN', shell=True, capture_output=True, text=True).stdout.strip())


def fly(name, weight, kt):
    fuel = dict(WEIGHTS)[weight]
    csv_path = os.path.join(OUT, name + '.csv')
    log_path = os.path.join(OUT, name + '.log')
    env = dict(os.environ, METARWIND='310%02dKT' % kt, SPEEDUP='4')
    for k in ('GUSTS', 'SHEAR_KT', 'SHEAR_AT', 'FUEL_LB', 'SETPROPS'):
        env.pop(k, None)
    if AIM:
        env['SETPROPS'] = 'ap/final-aim=1'
    if fuel:
        env['FUEL_LB'] = fuel
    while locked():
        print('%s: the screen is locked, waiting' % name, flush=True)
        time.sleep(60)
    for p in flightgear_pids():
        print('%s: a FlightGear (pid %d) is running: stopping it' % (name, p), flush=True)
        subprocess.run(['kill', str(p)])
    time.sleep(3)
    if port_busy():
        raise SystemExit('port 5477 answers and no FlightGear of ours is up: not starting %s' % name)
    t0 = time.time()
    with open(log_path, 'w') as lg:
        pr = subprocess.Popen([sys.executable, os.path.join(HERE, 'fg_scenario.py'), 'EFHK', '22L', csv_path], env=env, stdout=lg, stderr=subprocess.STDOUT, cwd=HERE)
        time.sleep(12)
        subprocess.run(['open', '-a', '/Applications/FlightGear.app'], capture_output=True)       # a FlightGear started from a script waits to be brought forward
        pr.wait()
    for p in flightgear_pids():
        subprocess.run(['kill', str(p)])
    time.sleep(3)
    ok = os.path.exists(csv_path) and os.path.getsize(csv_path) > 100000
    print('%s: %s in %.0f s of real time' % (name, 'recorded' if ok else 'NO RECORDING (see %s)' % log_path, time.time() - t0), flush=True)
    return ok


def main():
    os.makedirs(OUT, exist_ok=True)
    args = sys.argv[1:]
    if '--out' in args:
        del args[args.index('--out'):args.index('--out') + 2]
    want = [a for a in args if not a.startswith('--')]
    todo = [(w, k) for w, k in ORDER if not want or '%s_x%d' % (w, k) in want]
    for w, k in todo:
        name = '%s_x%d' % (w, k)
        if os.path.exists(os.path.join(OUT, name + '.csv')):
            print('%s: exists, skipped' % name, flush=True)
            continue
        # a flight that dies in its first seconds (2026-11-17, half_x27: "plan: None None", the aircraft's Nasal not yet answering) gets one more try
        if not fly(name, w, k) and not fly(name, w, k):
            print('%s failed twice: stopping the matrix' % name, flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()
