#!/usr/bin/env python3
"""Phase 9 part A checks: the aircraft in FlightGear itself. Starts FlightGear twice (on a runway, in the air),
reads it through its web server, and stops it.

    python3 fdm/phase9a_checks.py [ground|air]        several minutes: FlightGear is slow to start

Limits: docs/PLAN.md, written before FlightGear was started with the aircraft. FlightGear opens a window while this
runs. If it stalls in its start (it sometimes does: no answer for 4 minutes), the case is reported as not started.
"""
import json
import math
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FGFS = '/Applications/FlightGear.app/Contents/MacOS/FlightGear'
AIRCRAFT_DIR = os.path.realpath(os.path.join(HERE, '..', 'GlobalHawk'))
PORT = 5477
FG_ROOT = os.path.expanduser('~/git/fgdata')     # where this machine keeps FlightGear's data; left to FlightGear if absent
J = '/fdm/jsbsim/'
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))


def get(path):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/json%s' % (PORT, path), timeout=3) as r:
            return json.loads(r.read().decode()).get('value')
    except Exception:
        return None


def start(extra, log, tries=2):
    """FlightGear sometimes stalls in its start and never comes up: it is then stopped and started once more."""
    for n in range(tries):
        proc, took = start_once(extra, log)
        if took is not None or n == tries - 1:
            return proc, took
        stop(proc)
        time.sleep(5)


def start_once(extra, log):
    args = [FGFS, '--aircraft-dir=' + AIRCRAFT_DIR, '--aircraft=GlobalHawk', '--httpd=%d' % PORT, '--disable-ai-traffic', '--disable-real-weather-fetch',
            '--timeofday=noon', '--geometry=1024x640', '--disable-sound', '--disable-terrasync', '--prop:/sim/rendering/multi-sample-buffers=0',
            '--prop:/sim/startup/save-on-exit=false', '--model-hz=120'] + extra
    if os.path.isdir(FG_ROOT):
        args.insert(1, '--fg-root=' + FG_ROOT)
    proc = subprocess.Popen(args, stdout=open(log, 'w'), stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < 240:
        if proc.poll() is not None:
            return proc, None
        if get('/sim/globalhawk/started'):
            return proc, time.time() - t0
        time.sleep(2)
    return proc, None


def stop(proc):
    proc.terminate()
    try:
        proc.wait(20)
    except subprocess.TimeoutExpired:
        proc.kill()


def watch(seconds, keys):
    """Sample properties about twice a second of real time. Returns {key: [values]} and the sim time covered."""
    out = {k: [] for k in keys}
    t0 = get('/sim/time/elapsed-sec') or 0.0
    end = time.time() + seconds
    while time.time() < end:
        for k, p in keys.items():
            v = get(p)
            out[k].append(float(v) if isinstance(v, (int, float)) else float('nan'))
        time.sleep(0.4)
    return out, (get('/sim/time/elapsed-sec') or 0.0) - t0


def errors(log):
    bad = []
    for line in open(log, errors='replace'):
        low = line.lower()
        if 'jsonurihandler' in low or 'tied property' in low:
            continue        # this script asking before the aircraft is up, and a message FlightGear's own Nasal gives with any aircraft
        if ('globalhawk' in low or 'jsbsim' in low or 'nasal' in low) and any(w in low for w in ('error', 'failed', 'could not', 'cannot', 'unable', 'not found', 'exception')):
            bad.append(line.strip()[:160])
    return bad


def ground():
    log = os.path.join(HERE, 'out', 'fg-ground.log')
    proc, took = start(['--airport=EFHK'], log)      # an airport whose scenery is on this machine; no runway named: FlightGear picks one
    if took is None:
        stop(proc)
        add('F1', 'starts on the runway', False, 'FlightGear did not come up with the aircraft in 4 minutes (see fdm/out/fg-ground.log)')
        return
    hz = get('/sim/model-hz')
    have = [get(J + p) is not None for p in ('ap/engaged', 'nav/roll-deg', 'limits/overstress', 'engine/thrust-lbf', 'fuel/total-lbs', 'flex/tip-deflection-ft')]
    bad = errors(log)
    add('F1', 'starts on the runway', all(have) and hz == 120 and not bad, 'up in %.0f s; flight model at %s Hz; the laws\' properties there: %s; error lines naming the aircraft: %s' % (
        took, hz, all(have), bad[:3] or 'none'))
    time.sleep(5)
    d, sim = watch(60, dict(lat='/position/latitude-deg', lon='/position/longitude-deg', pitch='/orientation/pitch-deg', roll='/orientation/roll-deg',
                            agl='/position/altitude-agl-ft', manual=J + 'ap/manual', engaged=J + 'ap/engaged', fps='/sim/frame-rate'))
    moved = math.hypot((max(d['lat']) - min(d['lat'])) * 364567, (max(d['lon']) - min(d['lon'])) * 364567 * math.cos(math.radians(d['lat'][0])))
    nan = any(math.isnan(v) for k in d for v in d[k])
    add('F2', 'on the runway for a minute', not nan and moved < 3 and max(abs(v) for v in d['pitch']) < 2 and max(abs(v) for v in d['roll']) < 2 and d['manual'][-1] == 1 and d['engaged'][-1] == 1,
        'no NaN: %s; moved %.2f ft; pitch %.2f to %.2f deg, bank within %.2f deg; wheels %.1f ft above the ground point; laws engaged %g in manual mode %g; %.0f s of flight time' % (
            not nan, moved, min(d['pitch']), max(d['pitch']), max(abs(v) for v in d['roll']), d['agl'][-1], d['engaged'][-1], d['manual'][-1], sim))
    add('F5', 'frames a second on the ground (reported)', True, '%.0f to %.0f' % (min(d['fps']), max(d['fps'])))
    stop(proc)


def air():
    log = os.path.join(HERE, 'out', 'fg-air.log')
    proc, took = start(['--lat=35.2', '--lon=-117.4', '--altitude=20000', '--vc=150', '--heading=40'], log)
    if took is None:
        stop(proc)
        add('F3', 'starts in the air', False, 'FlightGear did not come up with the aircraft in 4 minutes (see fdm/out/fg-air.log)')
        return
    time.sleep(150)                                                 # let it settle: FlightGear starts it untrimmed, and the speed loop takes two or three swings of about 100 s to come to rest
    keys = dict(alt='/position/altitude-ft', kcas='/velocities/airspeed-kt', roll='/orientation/roll-deg', pitch='/orientation/pitch-deg',
                hdg='/orientation/heading-deg', thr=J + 'ctl/throttle-norm', gear=J + 'gear/gear-pos-norm', fps='/sim/frame-rate', engaged=J + 'ap/engaged')
    d, sim = watch(120, keys)
    nan = any(math.isnan(v) for k in d for v in d[k])
    dalt, dv = max(d['alt']) - min(d['alt']), max(d['kcas']) - min(d['kcas'])
    add('F3', 'in the air: the laws hold it', not nan and dalt <= 100 and dv <= 3 and max(abs(v) for v in d['roll']) < 2 and d['engaged'][-1] == 1 and min(d['alt']) > 15000,
        'no NaN: %s; over %.0f s of flight: height %.0f to %.0f ft, %.1f to %.1f KCAS, bank within %.2f deg, heading %.1f to %.1f; throttle %.2f; gear %.2f; errors: %s' % (
            not nan, sim, min(d['alt']), max(d['alt']), min(d['kcas']), max(d['kcas']), max(abs(v) for v in d['roll']), min(d['hdg']), max(d['hdg']),
            d['thr'][-1], d['gear'][-1], errors(log)[:2] or 'none'))
    add('F5', 'frames a second in the air (reported)', True, '%.0f to %.0f' % (min(d['fps']), max(d['fps'])))
    stop(proc)


if __name__ == '__main__':
    which = sys.argv[1:] or ['ground', 'air']
    if 'ground' in which:
        ground()
    if 'air' in which:
        air()
    for tag, name, ok, detail in rows:
        print('%-3s %-40s %-5s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))
