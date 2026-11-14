#!/usr/bin/env python3
"""The turn onto the first leg after takeoff, measured: what the aircraft does when the first point is not straight ahead of the runway.

    python3 fdm/departure.py [--write]       --write: into fdm/data/capability_flown.json ("departure"), which fdm/capability.py reads

The mission manager starts the first leg where the aircraft lifts off and has no leg before it, so the corner between the runway's heading and
that leg is not flown with the lead and the arc it uses between legs (the laws' ap/turn-*): the aircraft turns by the intercept law and sweeps
past the line first. Measured here, headless, in calm air, on the demo field's runway, the manager's own takeoff at its own weight: for a first
point `delta` degrees off the runway's heading (40 nmi out, then straight on), the largest distance off the first leg's line in the first 200 s
after lift-off (off_ft), how far from the takeoff's end the aircraft is when it is within 150 ft of the line and stays there for 20 s (back_nm),
and how much heading it turned through up to then (turned_deg). The planner (js/flightmath.js, plancheck.assess, router.joinDeparture) takes the
corner at the takeoff's end from this table. Limits and results: docs/PLAN.md, "The turn after takeoff".
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capability as CAP            # noqa: E402
import missionmgr as MM             # noqa: E402
import onboard as OB                # noqa: E402
import phase8f_checks as C          # noqa: E402

NM = 6076.1
DELTAS = (0.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0, 120.0)


def along(p, brg, ft):
    c = math.radians(brg)
    return [p[0] + ft * math.cos(c) / MM.FT_PER_DEG, p[1] + ft * math.sin(c) / (MM.FT_PER_DEG * math.cos(math.radians(p[0])))]


def case(demo, fld, hdg, delta):
    start, end = demo['items'][1]['start'], demo['items'][1]['end']
    p1 = along(end, hdg + delta, 40 * NM)
    p2 = along(p1, hdg + delta, 40 * NM)
    fix = along(start, hdg + 180, 10 * NM)
    plan = json.loads(json.dumps(demo))
    plan['id'] = 'departure'
    plan['items'] = [demo['items'][0], demo['items'][1], dict(kind='route', points=[[p1[0], p1[1], 15000], [p2[0], p2[1], 15000], [fix[0], fix[1], 5200]]),
                     dict(kind='land', fix=fix, aim=along(start, hdg, 800), elev_ft=demo['field']['elev_ft'])]
    plan['sites'] = []
    bad = OB.check_plan(plan)
    if bad:
        raise SystemExit('the aircraft refuses the plan: %s' % bad)
    a, t0, _ = C.fly(plan, limit=420.0)
    air = int(np.argmax(a[:, 11] > demo['field']['elev_ft'] + 300.0))
    ne = np.array([fld.ne(lat, lon) for lat, lon in zip(a[:, 1], a[:, 2])])
    d0 = np.array(fld.ne(*end))
    dist = np.hypot(ne[:, 0] - d0[0], ne[:, 1] - d0[1])
    xt = a[air:, 6]
    back = next((i for i in range(10, len(xt) - 20) if np.all(np.abs(xt[i:i + 20]) < 150.0)), None)
    psi = np.degrees(np.unwrap(np.radians(a[air:, 19])))
    k = min(len(psi) - 1, (back if back is not None else len(psi) - 1) + 20)
    return dict(delta_deg=delta, off_ft=round(float(np.max(np.abs(xt[:200]))), -1), back_nm=None if back is None else round(float(dist[air + back]) / NM, 1),
                turned_deg=round(float(np.abs(np.diff(psi[:k + 1])).sum()), 0)), t0


def main():
    demo, cs = C.cases()
    fld = MM.Field(demo['field']['lat'], demo['field']['lon'], demo['field']['elev_ft'])
    hdg = cs[0]['hdg']
    rows, t0 = [], None
    print('%10s %10s %10s %10s' % ('delta, deg', 'off, ft', 'back, nmi', 'turned, deg'), flush=True)
    for d in DELTAS:
        r, t0 = case(demo, fld, hdg, d)
        rows.append(r)
        print('%10.0f %10.0f %10s %10.0f' % (r['delta_deg'], r['off_ft'], r['back_nm'], r['turned_deg']), flush=True)
    out = dict(rows=rows, weight_lb=round(t0['weight'], -2), field_elev_ft=demo['field']['elev_ft'], takeoff_heading_deg=round(hdg, 1),
               note='fdm/departure.py: a first point delta deg off the runway\'s heading, 40 nmi out; off_ft: the most off the first leg in 200 s after lift-off, back_nm: from the takeoff\'s end '
                    'to within 150 ft of the line for 20 s, turned_deg: heading turned through up to then; headless, calm air')
    if '--write' in sys.argv:
        flown = json.load(open(CAP.DATA))
        flown['departure'] = out
        json.dump(flown, open(CAP.DATA, 'w'), indent=1)
        print('written to', os.path.relpath(CAP.DATA))


if __name__ == '__main__':
    main()
