#!/usr/bin/env python3
"""Phase 8 part C checks: the station's forecast against the flight model, and the two ports against their originals.

    python3 fdm/phase8c_checks.py        about 15 s; needs node

C1 the forecast (GlobalHawk/gcs/js/predict.js, run by node) against a flight of the model.
C2 the ported plan check (js/plancheck.js) against the aircraft's (fdm/onboard.py) on damaged plans.
C3 the ported glide reach (js/reach.js) against the aircraft's planner (fdm/missionmgr.py).
C4 the planner's turn (js/flightmath.js: the turn performance table's flown bank, the radius, the lead) against the aircraft's lead (ap/turn-lead-ft) in calm air,
   a 90 deg corner, cruise speeds over weights and heights on the table's grid and between its points (docs/PLAN.md TT3: within 50 ft).
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


def descent_cases(plan):
    """Plans whose route has a leg that goes down at a set slope (docs/PLAN.md, "The aircraft refuses what it cannot fly"): the verdict each should have, and the plan."""
    out = []
    for name, deg, refused, short in (('5.9 deg', 5.9, False, False), ('6.1 deg', 6.1, True, False), ('7 deg', 7.0, True, False), ('8.3 deg', 8.3, True, False),
                                      ('a climb', None, False, False), ('7 deg in 1.5 nmi: too short to judge', 7.0, False, True)):
        p = copy.deepcopy(plan)
        pts = p['items'][2]['points']
        a, b = pts[-2], pts[-1]
        if short:                                           # the last leg cut to 1.5 nmi
            ft = MM.course(a, b)[1]
            pts[-2] = [a[0] + (b[0] - a[0]) * (1 - 1.5 * NM / ft), a[1] + (b[1] - a[1]) * (1 - 1.5 * NM / ft), a[2]]
            a = pts[-2]
        a[2] = b[2] - 3000.0 if deg is None else b[2] + math.tan(math.radians(deg)) * MM.course(a, b)[1]      # None: a climb of 3,000 ft
        out.append((name, refused, p))
    p = copy.deepcopy(plan)                                 # the lost-link route is checked too
    lp = p['lost_link'][0]['points']
    lp.insert(0, [lp[0][0] + 0.3, lp[0][1] + 0.3, lp[0][2] + 26000.0])
    out.append(('a steep leg in the lost-link route', True, p))
    return out


def hold_cases(plan):
    """Plans whose taxi item has holds (docs/PLAN.md, "Hold points and clearances"): good ones and each fault the check names."""
    H = lambda i, id_='H1', name='hold short of runway 04', kind='runway': dict(i=i, id=id_, name=name, kind=kind)
    cases = [None, [], [H(0)], [H(1, kind='takeoff')], [H(0), H(1, 'H2', kind='takeoff')], [H(0, kind='junction'), H(1, 'H2', kind='point')],
             'runway', {'i': 0}, [H(0), H(0, 'H2')], [H(2)], [H(-1)], [H(0.5)], [H(None)], [dict(H(0), i='0')], [H(0, '')], [H(0, 'x' * 25)], [H(0, 'x' * 24)], [H(0, 7)], [H(0), H(1, 'H1')],
             [H(0, name='')], [H(0, name='n' * 81)], [H(0, name='n' * 80)], [H(0, kind='gate')], [H(0, kind=None)], [H(0, kind='takeoff')], [H(0), 5], [[H(i, 'H%d' % i, kind='point') for i in range(2)]],
             [dict(i=0, id='H1', name='x')], [dict(id='H1', name='x', kind='point')], [H(i % 2, 'H%d' % i) for i in range(17)]]
    out = []
    for h in cases:
        p = copy.deepcopy(plan)
        if h is not None:
            p['items'][0]['holds'] = h
        out.append(p)
    p = copy.deepcopy(plan)                                 # the same id in the lost-link route's taxi item: checked per list of items
    p['lost_link'].insert(0, dict(kind='taxi', points=[[34.9, -117.88], [34.91, -117.88]], holds=[H(0)]))
    p['items'][0]['holds'] = [H(0)]
    out.append(p)
    return out


def ports():
    plan = json.load(open(PLAN))
    rng = random.Random(8)
    plans = [damage(plan, rng) for _ in range(200)]
    extra = descent_cases(plan)
    plans += [p for _, _, p in extra]
    ours = [OB.check_plan(p) for p in plans]
    theirs = node("const pc = require('./js/plancheck.js'); console.log(JSON.stringify(input.map((p) => pc.checkPlan(p))));", plans)
    verdict = sum((a is None) == (b is None) for a, b in zip(ours, theirs))
    same = sum(a == b for a, b in zip(ours, theirs))
    diff = [(a, b) for a, b in zip(ours, theirs) if a != b]
    add('C2', 'the plan check, ported: 200 damaged plans and the descent slopes', verdict == len(plans) and same == len(plans), 'the same verdict on %d of %d (%d refused); the same words on %d%s' % (
        verdict, len(plans), sum(a is not None for a in ours), same, '' if not diff else '; e.g. aircraft "%s", station "%s"' % diff[0]))
    got = [OB.check_plan(p) for _, _, p in extra]
    wrong = ['%s: %s' % (name, g) for (name, refused, _), g in zip(extra, got) if (g is not None) != refused or (refused and 'does not come down more steeply than 6 deg' not in (g or ''))]
    add('C2b', 'the plan check refuses a leg that goes down over 6 deg and nothing else', not wrong, '5.9 deg, a climb and a leg under 2 nmi accepted; 6.1, 7 and 8.3 deg and the lost-link route\'s steep leg refused with the leg named%s' % ('' if not wrong else '; WRONG: ' + ' | '.join(wrong)))
    hp = hold_cases(plan)
    ho = [OB.check_plan(p) for p in hp]
    ht = node("const pc = require('./js/plancheck.js'); console.log(JSON.stringify(input.map((p) => pc.checkPlan(p))));", hp)
    hd = [(a, b) for a, b in zip(ho, ht) if a != b]
    add('C2c', 'the plan check, ported: the holds of a taxi item, good and damaged', not hd and sum(a is not None for a in ho) >= 20 and ho[2] is None and ho[4] is None,
        '%d plans, %d refused, the same words on %d%s' % (len(hp), sum(a is not None for a in ho), sum(a == b for a, b in zip(ho, ht)), '' if not hd else '; e.g. aircraft "%s", station "%s"' % hd[0]))
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


TURN_LEAD_CELLS = ((12000.0, 4000.0), (20000.0, 4000.0), (26000.0, 4000.0), (20000.0, 20000.0), (26000.0, 30000.0), (20000.0, 45000.0), (15000.0, 12000.0), (23000.0, 38000.0))
TURN_LEAD_LIMIT_FT = 50.0


def turn_lead():
    """C4: for each cell (weight, height over the ground) the aircraft is trimmed at the speed the laws hold there, level, a 90 deg corner 12 nmi ahead, calm; its lead
    (ap/turn-lead-ft, the distance before the corner the turn starts at) against the planner's for the same weight, pressure altitude, speed and ground speed."""
    import numpy as np
    kc = node("const FM = require('./js/flightmath.js'); console.log(JSON.stringify(input.map((c) => FM.scheduleKcas(c[1] + 174))));", [list(c) for c in TURN_LEAD_CELLS])
    got = []
    for (w, h), k in zip(TURN_LEAD_CELLS, kc):
        f = H.load(rebuild=not got)          # the first load builds the laws as they are today, the rest use that build
        fld = MM.Field(60.3, 24.96, 174.0)
        u = lambda deg: np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg))])        # (north, east)
        start = fld.ll(*(-12 * NM * u(90.0)))
        B, C = fld.ll(0.0, 0.0), fld.ll(*(40000.0 * u(180.0)))
        t = H.trim(f, alt=174.0 + h, kcas=k, weight=w, lat=start[0], lon=start[1], psi=90.0, terrain=174.0)
        H.engage(f, t, pitch_mode=2, thrust_mode=3, speed_schedule=0)
        mgr = MM.Manager(f, [dict(kind='route', points=[B + (174.0 + h,), C + (174.0 + h,)])])
        f['ap/engaged'] = 1
        f['ap/speed-cmd-kcas'] = f['velocities/vc-kts']
        for _ in range(int(40 * H.HZ)):          # long enough for the leg law's start to settle: the lead is worked from the heading now, and a degree off the leg's course moves it 1 %
            mgr.step()
            f.run()
        got.append(dict(weight=f['inertia/weight-lbs'], alt=f['engine/pressure-altitude-ft'], kcas=f['velocities/vc-kts'], vg=f['velocities/vg-fps'], delta=f['ap/turn-delta-deg'],
                        lead=f['ap/turn-lead-ft'], bank=f['ap/turn-bank-deg'], flown=f['ap/turn-bank-flown-deg']))
    theirs = node("const FM = require('./js/flightmath.js'); console.log(JSON.stringify(input.map((g) => FM.turn({ delta_deg: g.delta, alt_ft: g.alt, vg_fps: g.vg, kcas: g.kcas, weight_lb: g.weight, bank_deg: g.bank }).lead_ft)));", got)
    worst = 0.0
    for (w, h), g, lead in zip(TURN_LEAD_CELLS, got, theirs):
        d = lead - g['lead']
        worst = max(worst, abs(d))
        add('C4', 'turn lead %5.0f lb %5.0f ft' % (w, h), abs(d) <= TURN_LEAD_LIMIT_FT,
            'aircraft %6.0f ft, planner %6.0f ft (%+.0f); bank commanded %.1f, flown %.1f deg, %.0f KCAS, vg %.0f ft/s' % (g['lead'], lead, d, g['bank'], g['flown'], g['kcas'], g['vg']))
    add('C4', 'turn lead, worst of %d cells' % len(got), worst <= TURN_LEAD_LIMIT_FT, '%.0f ft (limit %.0f)' % (worst, TURN_LEAD_LIMIT_FT))


def main():
    forecast()
    ports()
    turn_lead()
    for tag, name, ok, detail in rows:
        print('%-3s %-44s %-5s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))


if __name__ == '__main__':
    main()
