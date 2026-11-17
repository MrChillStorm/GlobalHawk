#!/usr/bin/env python3
"""Phase 8 part F checks: the station's planner against the aircraft's capability (docs/PLAN.md, "The planner uses the aircraft's capability
tables", limits P1 to P6).

    python3 fdm/phase8f_checks.py        about 4 minutes; needs node

P1 the station's capability file is what the laws and the data say today (fdm/capability.py), and the forecast's table takes its descent from the
   same flown measurement.
P2 the forecast's descent against a fresh flight of the manager's descent at six points: within 10 %.
P5 plans the router makes, flown in the model by the aircraft's own manager after the aircraft's plan check accepts them: no turn more than 150 ft
   past its new line (calm air), the glide taken over within the M5b limits, the landing within M7 and M8's, the forecast's time within 10 %.
(P3 and P4, the assessment and the router's own plans, are tests of the station: GlobalHawk/gcs/tests.)
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capability as CAP            # noqa: E402
import gcs_server as G              # noqa: E402
import harness as H                 # noqa: E402
import missionmgr as MM             # noqa: E402
import onboard as OB                # noqa: E402

GCS = os.path.join(HERE, '..', 'GlobalHawk', 'gcs')
DEMO = os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json')
NM = 6076.1
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))
    print('%-3s %-62s %-5s %s' % rows[-1], flush=True)


def node(script, data):
    r = subprocess.run(['node', '-e', "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n" + script], input=json.dumps(data),
                       capture_output=True, text=True, cwd=GCS, check=True)
    return json.loads(r.stdout)


ROUTER = """
const R = require('./js/router.js'), P = require('./js/predict.js'), perf = require('./js/perfdata.js'), pc = require('./js/plancheck.js');
const FM = require('./js/flightmath.js'), geo = require('./js/geo.js');
const fc = P.make(perf);
console.log(JSON.stringify(input.cases.map((c) => {
  const legsFor = (pts) => pc.legs([{ kind: 'route', points: pts }, { kind: 'land', fix: c.fix, aim: c.aim }], c.start, c.elev);
  // the height over the fix the aircraft's capability asks for (the station's own default for a plan that does not give one)
  const fixAlt = Math.round((c.elev + FM.finalFixHeightAgl(geo.course(c.fix, c.aim).ft, c.weight)) / 100) * 100;
  const r = R.plan({ start: c.start, start_alt_ft: c.elev + 100, start_hdg_deg: c.rhdg, goal: c.fix, aim: c.aim, fix_alt_ft: fixAlt, weight_lb: c.weight, fuel_lb: c.fuel, fc, perf, wind: null,
    hours: 0, zones: [], hazards: [], now: 0, legsFor, altitudes: [10000, 15000, 20000] });
  return r.ok ? { points: r.best.points, join: r.best.join || null, departure: r.best.departure_points || 0, time_s: r.best.time_s, fuel_lb: r.best.fuel_lb } : { error: r.error };
})));
"""

FORECAST = """
const P = require('./js/predict.js').make(require('./js/perfdata.js')), pc = require('./js/plancheck.js');
const legs = pc.legs(input.items, input.from_, input.elev);
const r = P.predict(legs, input.state);
console.log(JSON.stringify({ total: r.total, warnings: r.warnings }));
"""


def p1_p2():
    here = open(CAP.OUT).read() if os.path.exists(CAP.OUT) else ''
    ok = here == CAP.js(CAP.build())
    # the forecast's table: the descent arrays are the flown measurement's
    perf = json.loads(re.search(r'const data = (\{.*?\});\n', open(os.path.join(GCS, 'js', 'perfdata.js')).read(), re.S).group(1))
    flown = json.load(open(CAP.DATA))
    same = perf['descent_fpm'] == flown['descent_fpm'] and perf['descent_pph'] == flown['descent_pph']
    add('P1', 'the capability file is what the laws and the data say today', ok and same,
        'js/capability.js %s; the forecast table\'s descent %s the flown measurement' % ('current' if ok else 'DIFFERS (run python3 fdm/capability.py)', 'is' if same else 'DIFFERS from (run fdm/gcs_perf.py after fdm/capability.py measure)'))
    f = H.load()
    out = node("const P = require('./js/predict.js').make(require('./js/perfdata.js'));\nconsole.log(JSON.stringify(input.map((p) => P.look(require('./js/perfdata.js').descent_fpm, p[0], p[1]))));",
               [[a, w] for a in (10000.0, 20000.0, 30000.0) for w in (14000.0, 22000.0)])
    worst, lines = 0.0, []
    for (a, w), table in zip([(a, w) for a in (10000.0, 20000.0, 30000.0) for w in (14000.0, 22000.0)], out):
        rate, _ = CAP.flown_descent(f, a, w)
        worst = max(worst, abs(table / rate - 1))
        lines.append('%d ft %d lb: table %.0f, flown %.0f' % (a, w, table, rate))
    add('P2', 'the forecast\'s descent against the manager\'s', worst <= 0.10, 'worst %.1f %% (limit 10 %%): %s' % (100 * worst, '; '.join(lines)))


def cases():
    """Six plans: the demo field's takeoff, then a landing at a place 80 to 300 nmi away from every side, its final from a different direction."""
    demo = json.load(open(DEMO))
    fld = MM.Field(demo['field']['lat'], demo['field']['lon'], demo['field']['elev_ft'])
    start = demo['items'][1]['end']
    n0, e0 = fld.ne(*demo['items'][1]['end'])
    hdg = math.degrees(math.atan2(e0, n0)) % 360          # the takeoff's heading (the takeoff starts at the field's origin)
    out = []
    for k, (bearing, dist, final) in enumerate([(30, 80, 40), (120, 140, 250), (210, 200, 100), (300, 120, 340), (75, 260, 215), (255, 300, 20)]):
        n, e = np.array([math.cos(math.radians(bearing)), math.sin(math.radians(bearing))]) * dist * NM
        aim = list(fld.ll(n, e))
        fix = list(MM.along(aim, final + 180.0, 10 * NM))
        out.append(dict(start=start, hdg=hdg, fix=fix, aim=aim, elev=demo['field']['elev_ft'], weight=25600.0, fuel=14150.0, name='%d nmi at %d, final %d' % (dist, bearing, final)))
    return demo, out


def fly(plan, limit=7200.0):
    """The plan flown from the stand by the aircraft's own manager, sampled every second: [t, lat, lon, glide error, land mode, togo, xt, mains, hdot, vg, rollout]."""
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
        json.dump(plan, fh)
    sim = G.Sim(fh.name)
    f, ob = sim.f, sim.ob
    for n, (name, args) in enumerate((('plan', plan), ('start', {}))):
        sim.set('/gcs/up/cmd', json.dumps(dict(seq=n + 1, station='C', name=name, args=args)))
    keys = ['simulation/sim-time-sec', 'position/lat-geod-deg', 'position/long-gc-deg', 'ap/glide-error-ft', 'ap/land-mode', 'ap/leg-togo-ft', 'ap/leg-xt-ft', 'ap/on-mains',
            'velocities/h-dot-fps', 'ap/ground-speed-kt', 'ap/rollout', 'position/h-sl-ft', 'ap/flare', 'ap/turn-phase', 'ap/turn-lead-ft', 'attitude/phi-deg',
            'ap/turn-bank-deg', 'aero/alpha-deg', 'ap/alpha-limit-deg', 'attitude/psi-deg']
    rows_, t0 = [], None
    for i in range(int(limit * H.HZ)):
        if i % H.HZ == 0:
            sim.set('/gcs/up/heartbeat', i)
        sim.step()
        kind = ob.mgr.plan[min(ob.mgr.i, len(ob.mgr.plan) - 1)]['kind']
        if t0 is None and kind == 'takeoff':
            t0 = dict(t=f['simulation/sim-time-sec'], fuel=f['fuel/total-lbs'], weight=f['inertia/weight-lbs'], alt=f['position/h-sl-ft'])
        if i % H.HZ == 0:
            rows_.append([f[k] for k in keys])
            if t0 is not None and f['ap/rollout'] == 1 and f['ap/ground-speed-kt'] < 15.0:
                break
    os.unlink(fh.name)
    return np.array(rows_), t0, ob.mgr


def turns(plan, a, fld):
    """For each corner of the route (and the join onto the final): how far the aircraft went past the new line, ft (calm air)."""
    route = plan['items'][2]['points']
    land = plan['items'][3]
    chain = [plan['items'][1]['end']] + [[p[0], p[1]] for p in route] + [land['aim']]
    ne = np.array([fld.ne(lat, lon) for lat, lon in zip(a[:, 1], a[:, 2])])
    out = []
    for i in range(1, len(chain) - 1):
        p0, p1, p2 = [np.array(fld.ne(*c)) for c in chain[i - 1:i + 2]]
        c0, c1 = math.atan2(p1[1] - p0[1], p1[0] - p0[0]), math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        delta = (math.degrees(c1 - c0) + 180) % 360 - 180
        if abs(delta) < 10:
            continue
        d = np.array([math.cos(c1), math.sin(c1)])
        rel = ne - p1
        along = rel @ d
        right = rel @ np.array([-d[1], d[0]])
        near = (np.hypot(rel[:, 0], rel[:, 1]) < 12 * NM) & (along > -9 * NM) & (along < 12 * NM)
        past = np.maximum(0.0, -np.sign(delta) * right)
        # the approach from the far side of the line is not an overshoot: only after the aircraft has come within 300 ft of it
        came = np.cumsum(near & (np.abs(right) < 300.0)) > 0
        out.append((i, delta, float(np.max(past[near & came])) if (near & came).any() else float('nan')))
    return out


def turning_after_takeoff(plan, dep, hdg, a, fld, field_elev):
    """The heading the aircraft turned through from lift-off until it was 2.5 nmi past the first point of the route proper (the plan's points after the
    departure's), against the corners the plan has up to there (the one at the takeoff's end from the takeoff's heading, those at the departure's points, and that
    at the first point itself): [extra deg, flown deg, planned deg]. The loop the aircraft flew in FlightGear (205 deg for a corner of 171) is the extra."""
    route = plan['items'][2]['points']
    end = plan['items'][1]['end']
    chain = [end] + [[p[0], p[1]] for p in route] + [plan['items'][3]['aim']]
    ne = [np.array(fld.ne(*c)) for c in chain]
    course = lambda u, v: math.degrees(math.atan2(v[1] - u[1], v[0] - u[0])) % 360
    turn = lambda c0, c1: (c1 - c0 + 180) % 360 - 180
    planned = abs(turn(hdg, course(ne[0], ne[1])))
    for i in range(1, dep + 2):
        if i + 1 < len(chain):
            planned += abs(turn(course(ne[i - 1], ne[i]), course(ne[i], ne[i + 1])))
    air = int(np.argmax(a[:, 11] > field_elev + 300.0))
    pos = np.array([fld.ne(lat, lon) for lat, lon in zip(a[:, 1], a[:, 2])])
    target = ne[dep + 1]
    d = np.hypot(pos[:, 0] - target[0], pos[:, 1] - target[1])
    near = air + int(np.argmin(d[air:air + 1500]))
    past = np.nonzero(d[near:] > 2.5 * NM)[0]
    k1 = near + int(past[0]) if len(past) else len(d) - 1
    psi = np.degrees(np.unwrap(np.radians(a[air:k1 + 1, 19])))
    flown = float(np.abs(np.diff(psi)).sum())
    return flown - planned, flown, planned


def p5():
    demo, cs = cases()
    for c in cs:                                          # P5_NO_HDG: the baseline, the router as it was, with no takeoff heading
        c['rhdg'] = None if os.environ.get('P5_NO_HDG') else c['hdg']
    routed = node(ROUTER, dict(cases=cs))
    worst_turn, lines, fails = 0.0, [], []
    for c, r in zip(cs, routed):
        if 'error' in r:
            fails.append('%s: no route (%s)' % (c['name'], r['error']))
            continue
        plan = json.loads(json.dumps(demo))
        plan['id'] = 'p5'
        plan['items'] = [demo['items'][0], demo['items'][1], dict(kind='route', points=r['points']),
                         dict(kind='land', fix=c['fix'], aim=c['aim'], elev_ft=c['elev'])]
        plan['sites'] = []
        bad = OB.check_plan(plan)
        if bad:
            fails.append('%s: the aircraft refuses it (%s)' % (c['name'], bad))
            continue
        a, t0, mgr = fly(plan)
        fld = MM.Field(demo['field']['lat'], demo['field']['lon'], demo['field']['elev_ft'])
        tn = turns(plan, a, fld)
        over = max([x[2] for x in tn if not math.isnan(x[2])] or [0.0])
        # the glide: from when the manager took it over until the flare
        k = np.nonzero((a[:, 4] == 1) & (a[:, 12] == 0) & (a[:, 10] == 0) & (a[:, 7] == 0) & (a[:, 5] > 1500))[0]
        e = a[k, 3]
        reached = int(np.argmax(e >= -10.0)) if (e >= -10).any() else len(e)
        up, under = float(e.max()), float(e[reached:].min()) if reached < len(e) else float(e.min())
        big = e[reached:][np.abs(e[reached:]) > 5]
        cross = int(np.sum(np.diff(np.sign(big)) != 0)) if len(big) > 1 else 0
        air = int(np.argmax(a[:, 11] > demo['field']['elev_ft'] + 300.0))                      # the first row in the air: the stand has weight on its wheels too
        td = air + int(np.argmax(a[air:, 7] > 0)) if (a[air:, 7] > 0).any() else None
        sink = -a[td - 1, 8] * 0.3048 if td else float('nan')
        roll = float(np.abs(a[td:, 6]).max()) if td else float('nan')
        extra, flown_turn, planned_turn = turning_after_takeoff(plan, r.get('departure', 0), c['hdg'], a, fld, demo['field']['elev_ft'])
        fc = node(FORECAST, dict(items=plan['items'][1:], from_=None, elev=demo['field']['elev_ft'], state=dict(alt_ft=t0['alt'], weight_lb=t0['weight'], fuel_lb=t0['fuel'])))
        tf, tm = fc['total']['t_s'], (a[td, 0] if td else a[-1, 0]) - t0['t']
        ok = over <= 150.0 and up <= 8.0 and under >= -12.0 and cross == 0 and 0.2 <= sink <= 1.2 and roll <= 15.0 and abs(tf / tm - 1) <= 0.10 and extra <= 40.0
        lines.append('%s: %d points%s; turns %s; past the line %.0f ft, turned %.0f deg to the first point against %.0f planned (%+.0f), glide +%.1f/%.1f ft %d crossings, sink %.2f m/s, rollout %.1f ft off, forecast %.1f min flown %.1f%s' % (
            c['name'], len(r['points']), ' (%s)' % r['join'][:40] if r['join'] else '', ','.join('%.0f deg %.0f ft' % (abs(x[1]), x[2]) for x in tn), over, flown_turn, planned_turn, extra, up, under, cross, sink, roll,
            tf / 60, tm / 60, '' if ok else '  <-- MISS'))
        if not ok:
            fails.append(c['name'])
    for line in lines:
        print('    ' + line, flush=True)
    add('P5', 'router plans flown by the aircraft', not fails, '%d plans; %s' % (len(cs), 'all within the limits' if not fails else 'misses: ' + '; '.join(fails)))
    add('G0', 'no go-around in the router plans flown (a go-around hides nothing)', MM.Manager.go_arounds == 0, '%d go-arounds' % MM.Manager.go_arounds)


def main():
    p1_p2()
    p5()
    miss = sum(1 for r in rows if r[2] != 'pass')
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))


if __name__ == '__main__':
    main()
