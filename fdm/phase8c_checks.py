#!/usr/bin/env python3
"""Phase 8 part C checks: the station's forecast against the flight model, and the two ports against their originals.

    python3 fdm/phase8c_checks.py        about 15 s; needs node

C1 the forecast (GlobalHawk/gcs/js/predict.js, run by node) against a flight of the model.
C2 the ported plan check (js/plancheck.js) against the aircraft's (fdm/onboard.py) on damaged plans.
C3 the ported glide reach (js/reach.js) against the aircraft's planner (fdm/missionmgr.py).
Limits: docs/GCS.md, written first.
"""
import copy
import json
import math
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcs_server as G              # noqa: E402
import harness as H                 # noqa: E402
import missionmgr as MM             # noqa: E402
import onboard as OB                # noqa: E402

GCS = os.path.join(HERE, '..', 'GlobalHawk', 'gcs')
PLAN = os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json')
NM = 6076.1
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))


def node(script, data):
    """Run a few lines of JavaScript in the station's folder with `data` as input; returns what it prints as JSON."""
    r = subprocess.run(['node', '-e', "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n" + script], input=json.dumps(data),
                       capture_output=True, text=True, cwd=GCS, check=True)
    return json.loads(r.stdout)


FORECAST = """
const pr = require('./js/predict.js').make(require('./js/perfdata.js'));
const pc = require('./js/plancheck.js');
const legs = pc.legs(input.items, input.from_, input.elev);
const r = pr.predict(legs, input.state);
console.log(JSON.stringify({ total: r.total, profile: r.profile, points: r.points, warnings: r.warnings }));
"""


def fly(plan, stop, limit=3600.0):
    """Fly a plan in the model from the stand. Returns the state at the start of the takeoff and when stop(f, mgr) holds."""
    sim = G.Sim(PLAN)
    f, ob = sim.f, sim.ob
    for n, (name, args) in enumerate((('plan', plan), ('start', {}))):
        sim.set('/gcs/up/cmd', json.dumps(dict(seq=n + 1, station='C', name=name, args=args)))
    t0 = None
    for i in range(int(limit * H.HZ)):
        if i % H.HZ == 0:
            sim.set('/gcs/up/heartbeat', i)
        sim.step()
        kind = ob.mgr.plan[min(ob.mgr.i, len(ob.mgr.plan) - 1)]['kind']
        if t0 is None and kind == 'takeoff':
            t0 = dict(t=f['simulation/sim-time-sec'], fuel=f['fuel/total-lbs'], weight=f['inertia/weight-lbs'], alt=f['position/h-sl-ft'])
        if t0 is not None and stop(f, ob.mgr):
            return t0, dict(t=f['simulation/sim-time-sec'], fuel=f['fuel/total-lbs'], alt=f['position/h-sl-ft'])
    return t0, None


def forecast():
    plan = json.load(open(PLAN))
    items = plan['items'][1:]                                     # from the takeoff on
    t0, end = fly(plan, lambda f, m: f['ap/rollout'] == 1)
    fc = node(FORECAST, dict(items=items, from_=None, elev=plan['field']['elev_ft'], state=dict(alt_ft=t0['alt'], weight_lb=t0['weight'], fuel_lb=t0['fuel'])))
    tm, fm = end['t'] - t0['t'], t0['fuel'] - end['fuel']
    tf, ff = fc['total']['t_s'], fc['total']['fuel_used_lb']
    add('C1', 'the demo plan, takeoff to touchdown', abs(tf / tm - 1) <= 0.10 and abs(ff / fm - 1) <= 0.15,
        'time: forecast %.1f min, flown %.1f (%+.1f %%); fuel: forecast %.0f lb, flown %.0f (%+.1f %%); forecast warnings: %s' % (
            tf / 60, tm / 60, 100 * (tf / tm - 1), ff, fm, 100 * (ff / fm - 1), fc['warnings'] or 'none'))
    # a climb to 45,000 ft along 150 nmi
    fld = MM.Field(34.9, -117.88, 2300.0)
    u = (math.cos(math.radians(40.0)), math.sin(math.radians(40.0)))
    P = lambda nm: list(fld.ll(nm * NM * u[0], nm * NM * u[1]))
    high = copy.deepcopy(plan)
    high['items'][2]['points'] = [P(50) + [45000.0], P(100) + [45000.0], P(150) + [45000.0]]
    t0, end = fly(high, lambda f, m: f['position/h-sl-ft'] >= 44850.0)
    fc = node(FORECAST, dict(items=high['items'][1:3], from_=None, elev=2300.0, state=dict(alt_ft=t0['alt'], weight_lb=t0['weight'], fuel_lb=t0['fuel'])))
    top = next((p for p in fc['profile'] if p[1] >= 44850.0), None)
    if end is None or top is None:
        add('C1', 'a climb to 45,000 ft along 150 nmi', False, 'the model %s 45,000 ft; the forecast %s' % ('reached' if end else 'never reached', 'reached it' if top else 'never did'))
    else:
        tm, fm = end['t'] - t0['t'], t0['fuel'] - end['fuel']
        tf, ff = top[2], t0['fuel'] - top[3]
        add('C1', 'a climb to 45,000 ft along 150 nmi', abs(tf / tm - 1) <= 0.10 and abs(ff / fm - 1) <= 0.15,
            'time to 44,850 ft: forecast %.1f min, flown %.1f (%+.1f %%); fuel: forecast %.0f lb, flown %.0f (%+.1f %%)' % (
                tf / 60, tm / 60, 100 * (tf / tm - 1), ff, fm, 100 * (ff / fm - 1)))


def damage(plan, rng):
    """One random fault, or none, put into a copy of the plan."""
    p = copy.deepcopy(plan)
    route, land = p['items'][2], p['items'][3]
    pt = rng.choice(route['points'])
    what = rng.randrange(16)
    if what == 0:
        rng.choice(p['items'])['kind'] = rng.choice(['loiter', 'orbit', '', None])
    elif what == 1:
        pt[2] = rng.choice([70000.0, -5.0, 65000.0, 0.0, 65000.5])
    elif what == 2:
        pt[0] = rng.choice([95.0, -91.0, 90.0, 'x'])
    elif what == 3:
        pt[1] = rng.choice([181.0, -180.0, None])
    elif what == 4:
        land['fix'] = list(MM.Field(*land['aim'], 0).ll(*[-rng.uniform(2, 14) * NM * c for c in (math.cos(math.radians(40)), math.sin(math.radians(40)))]))
    elif what == 5:
        p['lost_link'].pop(rng.randrange(len(p['lost_link'])))
    elif what == 6:
        p['items'].pop(rng.randrange(len(p['items'])))
    elif what == 7:
        del p['field'][rng.choice(['lat', 'lon', 'elev_ft'])]
    elif what == 8:
        route['points'] = []
    elif what == 9:
        pt.pop()
    elif what == 10:
        p['sites'][0][rng.choice(['course', 'elev_ft'])] = rng.choice(['north', None, True])
    elif what == 11:
        p['lost_link'] = rng.choice([None, [], [p['items'][3]]])
    elif what == 12:
        route['points'][0][1] += rng.choice([40.0, 80.0])          # a very long leg, or just under
    elif what == 13:
        p['items'][rng.randrange(len(p['items']))] = rng.choice(['route', 7, None, []])
    elif what == 14:
        p['items'][1][rng.choice(['start', 'end'])] = rng.choice([[1.0], None, [0.0, 0.0, 0.0]])
    return p


def ports():
    plan = json.load(open(PLAN))
    rng = random.Random(8)
    plans = [damage(plan, rng) for _ in range(200)]
    ours = [OB.check_plan(p) for p in plans]
    theirs = node("const pc = require('./js/plancheck.js'); console.log(JSON.stringify(input.map((p) => pc.checkPlan(p))));", plans)
    verdict = sum((a is None) == (b is None) for a, b in zip(ours, theirs))
    same = sum(a == b for a, b in zip(ours, theirs))
    diff = [(a, b) for a, b in zip(ours, theirs) if a != b]
    add('C2', 'the plan check, ported: 200 damaged plans', verdict == 200, 'the same verdict on %d of 200 (%d refused); the same words on %d%s' % (
        verdict, sum(a is not None for a in ours), same, '' if not diff else '; e.g. aircraft "%s", station "%s"' % diff[0]))
    # reach: the aircraft's planner with a stand-in for the flight model
    cases = []
    m = MM.Manager.__new__(MM.Manager)
    for _ in range(50):
        site = dict(aim=(rng.uniform(-60, 60), rng.uniform(-170, 170)), course=rng.uniform(0, 360), elev=rng.uniform(0, 6000))
        brg, d, trk, alt = rng.uniform(0, 360), rng.uniform(1, 300) * NM, rng.uniform(0, 360), rng.uniform(3000, 65000)
        here = MM.Field(*site['aim'], 0).ll(d * math.cos(math.radians(brg)), d * math.sin(math.radians(brg)))
        m.f = {'position/lat-geod-deg': here[0], 'position/long-gc-deg': here[1], 'position/h-sl-ft': alt,
               'velocities/v-east-fps': 300 * math.sin(math.radians(trk)), 'velocities/v-north-fps': 300 * math.cos(math.radians(trk))}
        cases.append(dict(site=dict(aim=list(site['aim']), course=site['course'], elev_ft=site['elev']), here=list(here), alt=alt, track=trk,
                          aircraft=m.reach(site)))
    got = node("const r = require('./js/reach.js'); console.log(JSON.stringify(input.map((c) => r.margin(c.site, c.here, c.alt, c.track))));", cases)
    worst = max(abs(a['aircraft'] - b) for a, b in zip(cases, got))
    add('C3', 'glide reach, ported: 50 cases', worst <= 1.0, 'the largest difference %.3f ft' % worst)


def main():
    forecast()
    ports()
    for tag, name, ok, detail in rows:
        print('%-3s %-44s %-5s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))


if __name__ == '__main__':
    main()
