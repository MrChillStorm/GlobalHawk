#!/usr/bin/env python3
"""A flight from one airport to another, in the flight model (docs/PLAN.md, "Destination picker, stage 4": D8 and D11).

    python3 fdm/dest_checks.py        about 10 minutes of the flight model: run it through the queue, `qrun python3 fdm/dest_checks.py`

The plans are what the station's module (js/ground.js planBetween) makes for the made-up fields XDM1 and XDM2 (about 48 nmi apart, 2,300 and 3,100 ft), flown to their end by the
aircraft's own manager, the holds cleared as they come: from XDM1's stand S1 to XDM2's stand S2 (runway 04 to 09), and, at one airport, the circuit from XDM1's runway 04 to its 22
with the way in to the other stand. The flight model's ground is flat at the height of the field it starts on: the terrain is raised to the destination's when the landing begins,
as the scenery would have it.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import airportdata as AD            # noqa: E402
import ground_checks as GC          # noqa: E402
import hold_checks as HC            # noqa: E402

FT = 364567.2
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))
    print('%-5s %-72s %-5s %s' % rows[-1], flush=True)


def fly(tag, name, plan, stand_end, elev_end):
    sim, say, run, st = HC.flight(plan)
    f = sim.f
    a = say('plan', plan)
    b = say('start', {})
    add(tag + '.0', name + ': the plan is accepted and started', a['status'] == 'accepted' and b['status'] == 'accepted', '%s / %s' % (a['status'], b['status']))
    if a['status'] != 'accepted' or b['status'] != 'accepted':
        return
    land = next(i for i in plan['items'] if i['kind'] == 'land')
    la0, lo0 = land['fix']
    c = math.cos(math.radians(la0))
    ax, ay = (land['aim'][0] - la0) * FT, (land['aim'][1] - lo0) * FT * c
    ln = math.hypot(ax, ay)
    ux, uy = ax / ln, ay / ln
    lat_of = lambda lat, lon: ((lat - la0) * FT) * uy * -1 + ((lon - lo0) * FT * c) * ux          # feet to the right of the line from the fix to the aiming point
    along_of = lambda lat, lon: ((lat - la0) * FT) * ux + ((lon - lo0) * FT * c) * uy
    t_end = f['simulation/sim-time-sec'] + 4 * 3600
    cleared, terrain, touch = [], False, None
    while f['simulation/sim-time-sec'] < t_end:
        run(5)
        s = st()
        w = s.get('wait')
        if w and w['id'] not in cleared:
            say('clear', {'id': w['id']})
            cleared.append(w['id'])
        mgr = sim.ob.mgr
        kind = mgr.plan[min(mgr.i, len(mgr.plan) - 1)]['kind']
        if not terrain and kind == 'land':
            f['position/terrain-elevation-asl-ft'] = elev_end          # the scenery's: the destination field is higher
            terrain = True
        if touch is None and f['ap/rollout'] == 1:
            touch = (f['position/lat-geod-deg'], f['position/long-gc-deg'], f['ap/ground-speed-kt'], f['simulation/sim-time-sec'])
        if s['doing'] == 'plan complete':
            break
    run(20)
    s = st()
    done = s['doing'] == 'plan complete'
    events = [e[1] for e in s['events']]
    add(tag + '.1', name + ': it takes off, flies the route, lands, takes the exit, taxis in: "plan complete"', done, 'doing %s; holds cleared %s; last events %s' % (s['doing'][:40], ','.join(cleared) or 'none', ' | '.join(events[-4:])))
    if not done or touch is None:
        return
    off = lat_of(touch[0], touch[1])
    add(tag + '.2', name + ': the landing is on the runway: within 20 ft of the centreline at touchdown', abs(off) <= 20.0, '%.1f ft off at %.0f kt, %.0f ft past the aiming point' % (off, touch[2], along_of(touch[0], touch[1]) - ln))
    pos = (f['position/lat-geod-deg'], f['position/long-gc-deg'])
    d = math.hypot((pos[0] - stand_end[0]) * FT, (pos[1] - stand_end[1]) * FT * math.cos(math.radians(stand_end[0])))
    add(tag + '.3', name + ': it is parked at the stand there: within 15 ft, under 0.5 kt', d <= 15.0 and f['ap/ground-speed-kt'] < 0.5, '%.1f ft from the stand point (the centre of gravity), %.2f kt' % (d, f['ap/ground-speed-kt']))


def main():
    scen = [os.path.join(GC.GCS, 'tests', 'fixtures', 'scenery')]
    xdm = AD.load('XDM1', scen)
    xdm2 = AD.load('XDM2', scen)
    s1 = xdm['parking'][0]
    s2b = next(p for p in xdm2['parking'] if p['n'] == 'S2')
    s2a = next(p for p in xdm['parking'] if p['n'] == 'S2')
    # D8: XDM1 S1 to XDM2 S2, runway 04 to 09
    res = GC.between_plans(xdm, xdm2, 2300, 3100, (s1['lat'], s1['lon'], s1['h']), (s2b['lat'], s2b['lon'], s2b['h']))
    r = next(x for x in res if x['a'] == '04' and x['b'] == '09')
    assert 'plan' in r, r
    fly('D8', 'XDM1 S1 to XDM2 S2 (04 to 09)', r['plan'], (s2b['lat'], s2b['lon']), 3100.0)
    # D11: one airport, the circuit from 04 to 22, the way in to the other stand
    res = GC.between_plans(xdm, xdm, 2300, 2300, (s1['lat'], s1['lon'], s1['h']), (s2a['lat'], s2a['lon'], s2a['h']))
    r = next(x for x in res if x['a'] == '04' and x['b'] == '22')
    assert 'plan' in r, r
    fly('D11', 'XDM1 04 to its 22, circuit, stand S1 to S2', r['plan'], (s2a['lat'], s2a['lon']), 2300.0)
    print('%d checks, %d pass, %d miss' % (len(rows), sum(r[2] == 'pass' for r in rows), sum(r[2] != 'pass' for r in rows)))


if __name__ == '__main__':
    main()
