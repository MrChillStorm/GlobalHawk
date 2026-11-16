#!/usr/bin/env python3
"""The aircraft stops after a landing that ends the plan (docs/PLAN.md, "Runway picker, stage 3": E1 to E3, found in the first FlightGear flight on 04R).

    python3 fdm/stop_checks.py        about 10 minutes of the flight model: run it through the queue, `qrun python3 fdm/stop_checks.py`

A plan with a taxi item at the start and none after the landing (the lost-link route of any plan with a taxi out is that): at "rollout over" the laws' taxi target was still
the taxi item's 15 kt and the aircraft rolled on at 15 kt, off the runway's end. Here the made-up field XDM1, the plan the station lays from its first stand, flown to its end in
the Python flight model: it must come to a stop on the runway and stay there. (FlightGear's Nasal manager has the same two lines; the flight in FlightGear is by hand and
written up in docs/PLAN.md.)
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
import harness as H                 # noqa: E402

FT = 364567.2
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))
    print('%-5s %-70s %-5s %s' % rows[-1], flush=True)


def case(tag, plan):
    land = plan['items'][-1]
    sim, say, run, st = HC.flight(plan)
    f = sim.f
    a = say('plan', plan)
    b = say('start', {})
    add(tag + '.0', 'the plan (%s) is accepted and started' % ', '.join(i['kind'] for i in plan['items']), a['status'] == 'accepted' and b['status'] == 'accepted', '%s / %s' % (a['status'], b['status']))
    t_end = f['simulation/sim-time-sec'] + 4 * 3600
    over = None
    while f['simulation/sim-time-sec'] < t_end:
        run(10)
        s = st()
        if over is None and any('rollout over' in e[1] for e in s['events']):
            over = f['simulation/sim-time-sec']
            at_over = (f['position/lat-geod-deg'], f['position/long-gc-deg'], f['ap/ground-speed-kt'])
        if s['doing'] == 'plan complete':
            break
    add(tag + '.1', 'the plan flies its box and lands: "rollout over", then "plan complete"', over is not None and st()['doing'] == 'plan complete', 'rollout over at %s s of the flight' % ('%.0f' % over if over else 'never'))
    if over is None:
        return
    # the runway's line, from the landing's fix to its aiming point (the plan's own)
    la0, lo0 = land['fix']
    la1, lo1 = land['aim']
    c = math.cos(math.radians(la0))
    ax, ay = (la1 - la0) * FT, (lo1 - lo0) * FT * c
    ln = math.hypot(ax, ay)
    ux, uy = ax / ln, ay / ln
    rwy_hdg = math.degrees(math.atan2(uy, ux)) % 360

    def along_lat(lat, lon):
        x, y = (lat - la0) * FT, (lon - lo0) * FT * c
        return x * ux + y * uy, x * uy - y * ux
    pos = lambda: (f['position/lat-geod-deg'], f['position/long-gc-deg'])
    t0 = f['simulation/sim-time-sec']
    track = []
    for _ in range(36):                                                    # 6 minutes: sampled every 10 s
        run(10)
        track.append((f['simulation/sim-time-sec'] - over, f['ap/ground-speed-kt'], *along_lat(*pos())))
    stopped = [t for t in track if t[1] < 0.5]
    first = stopped[0][0] if stopped else None
    add(tag + '.2', 'it brakes to under 0.5 kt within 60 s of "rollout over"', first is not None and first <= 60.0, 'under 0.5 kt %s s after it; speeds %s' % ('%.0f' % first if first is not None else 'never', ' '.join('%.1f' % t[1] for t in track[:8])))
    last = [t for t in track if t[0] >= track[-1][0] - 120.0]
    drift = max(math.hypot(t[2] - last[0][2], t[3] - last[0][3]) for t in last)
    add(tag + '.3', 'it stays where it stopped: within 5 ft for the last 120 s', drift <= 5.0 and last[-1][1] < 0.5, '%.2f ft, %.2f kt' % (drift, last[-1][1]))
    al, lat = along_lat(*pos())
    hd = f['attitude/psi-deg']
    dh = abs((hd - rwy_hdg + 180) % 360 - 180)
    add(tag + '.4', 'on the runway: within 20 ft of the centreline, heading within 3 deg of its', abs(lat) <= 20.0 and dh <= 3.0, '%.1f ft off the centreline, heading %.1f (runway %.1f)' % (lat, hd, rwy_hdg))
    ro = math.hypot(al - along_lat(at_over[0], at_over[1])[0], 0)
    add(tag + '.5', 'it stopped on the pavement: no further than 2,000 ft past where the rollout was over', 0.0 <= ro <= 2000.0, '%.0f ft past the 15 kt point' % ro)


def main():
    xdm = AD.load('XDM1', [os.path.join(GC.GCS, 'tests', 'fixtures', 'scenery')])
    demo = json.load(open(os.path.join(HC.MISSIONS, 'demo-local.json')))
    s1 = xdm['parking'][0]
    r = GC.lay(xdm, demo, (s1['lat'], s1['lon']), s1['h'], False)       # no holds: nothing to clear on the way
    plan = r['plan']
    assert [i['kind'] for i in plan['items']] == ['taxi', 'takeoff', 'route', 'land', 'taxi'], plan['items']
    plan['items'] = plan['items'][:-1]                                    # ... and no taxi in: the plan ends with the landing
    case('E1', plan)                                                       # a taxi out, then the landing: the 15 kt of the taxi item was held
    bare = json.loads(json.dumps(demo))
    bare['items'] = [i for i in bare['items'] if i['kind'] != 'taxi']
    assert [i['kind'] for i in bare['items']] == ['takeoff', 'route', 'land'], bare['items']
    case('E3', bare)                                                       # no taxi item at all
    print('%d checks, %d pass, %d miss' % (len(rows), sum(r[2] == 'pass' for r in rows), sum(r[2] != 'pass' for r in rows)))


if __name__ == '__main__':
    main()
