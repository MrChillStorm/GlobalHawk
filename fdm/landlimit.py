#!/usr/bin/env python3
"""The crosswind the landing holds its contracts in, by weight, found by flying it (docs/PLAN.md, "Wind limits": WL2).

    python3 fdm/landlimit.py [--write]       --write: data/landing_limits.json, which fdm/capability.py puts in the capability file (the station's plan check reads it)

The final from 5 nmi out in the landing configuration with the landing task's laws (the setup of phase11's W3), calm air but for a steady wind across the runway from the right,
put on over 30 s, raised from START_KT in STEP_KT steps until a contract breaks. The limit of a weight is the highest wind at which every contract held; the first break
(which task's contract, by what) is kept beside it, as is what the controls did. The contracts are the tasks' handovers (fdm/contract.py; the limits are the ones in docs/PLAN.md,
M5b, M7, M8, and mine where none was written):
  final.gate        at the flare's start: off the line <= 10 ft, off the glide path <= 12 ft, off the speed <= 3 kt
  flare.touchdown   at the first wheel: sink 0.3 to 1.2 m/s, pitch 1.5 to 3.5 deg, bank <= 5 deg, off the line <= 15 ft, the nose within 5 deg of the runway's course
  rollout.line      from the first wheel to the end: the largest distance off the line <= 15 ft
  control.margin    the ruddervators and the ailerons within 2/3 of their travel throughout (Boeing's crosswind guidance keeps a third for gusts)
The limit is a limit of these contracts and of this model, in steady wind: it is lower in turbulence (docs/PLAN.md) and it is the aircraft's own, not a certified figure.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402
import phase11_checks as P      # noqa: E402
import phase7b_checks as B      # noqa: E402

WEIGHTS = (12000.0, 16000.0, 20800.0, 24000.0, 26000.0)
START_KT, STEP_KT, MAX_KT = 10.0, 5.0, 60.0
SIDE = 90.0                       # the wind from the right of the runway's course (from the left it is the same to a few feet: the sweeps of 2026-11-14)
ELEV = 2357.0
TRAVEL_DEG = 20.0                 # the surface commands' travel (fdm/laws.py clips them at 20)
CONTROL_MARGIN = 2.0 / 3.0


def land(kt, weight):
    f = H.load_variant({})
    P.calm(f)
    gale = P.Gale(B.COURSE + SIDE, kt)
    fld = B.MM.Field(35.0, -117.0, ELEV)
    u = B.unit(B.COURSE)
    aim, far = fld.ll(0, 0), fld.ll(*(-8 * B.NM * u))
    d0 = 5 * B.NM
    start = fld.ll(*(-d0 * u))
    keas = math.sqrt(weight / (0.645 * 540 * 0.5 * 0.0023769)) / H.KT
    t = H.trim(f, alt=ELEV + 5.3 + d0 * 0.07782, kcas=keas, weight=weight, gamma=-4.45, gear=1.0, spoiler=2 / 3, lat=start[0], lon=start[1], psi=B.COURSE, terrain=ELEV)
    H.engage(f, t, pitch_mode=1, roll_mode=3, ground_steer=1, land_mode=1, rwy_elev_ft=ELEV, leg_lat0_deg=far[0], leg_lon0_deg=far[1], leg_lat1_deg=aim[0], leg_lon1_deg=aim[1])
    ext = dict(ail=0.0, rud=0.0)

    def hook(f_, t_):
        gale.hook(f_, t_)
        ext['ail'] = max(ext['ail'], abs(f_['ctl/roll-cmd-deg']) / TRAVEL_DEG)
        ext['rud'] = max(ext['rud'], abs(f_['ctl/yaw-deg']) / TRAVEL_DEG)
    log = H.run(f, 260, every=6, hook=hook)
    P.calm(f)
    log['_ext'] = ext
    return log


def judge(log):
    """the contracts against a recorded landing: {broke: [contract names], first: name or None, details}"""
    down = np.nonzero(log['mains'] > 0)[0]
    if not len(down):
        return dict(broke=['never down'], first='never down', detail='no touchdown')
    i = int(down[0])
    fl = np.nonzero(log['flare'] > 0)[0]
    k = int(fl[0]) if len(fl) else i
    gate = (abs(log['xt'][k]), abs(log['glide'][k]), abs(log['kcas'][k] - log['target'][k]))
    sink = -log['hdot'][max(0, i - 1)] * 0.3048
    hdg = abs((log['psi'][i] - B.COURSE + 540) % 360 - 180)
    pitch = float(log['theta'][i])
    bank = abs(float(log['phi'][i]))
    xt_td = abs(float(log['xt'][i]))
    roll = float(np.abs(log['xt'][i:]).max())
    ext = log['_ext']
    broke, detail = [], {}
    if gate[0] > 10 or gate[1] > 12 or gate[2] > 3:
        broke.append('final.gate')
        detail['final.gate'] = 'off the line %.0f ft, off the path %.0f ft, off the speed %.1f kt' % gate
    if not (0.3 <= sink <= 1.2) or bank > 5 or xt_td > 15 or hdg > 5 or not (1.5 <= pitch <= 3.5):
        broke.append('flare.touchdown')
        detail['flare.touchdown'] = 'sink %.2f m/s, pitch %.1f, bank %.1f, off the line %.0f ft, nose %.1f deg off the runway' % (sink, pitch, bank, xt_td, hdg)
    if roll > 15:
        broke.append('rollout.line')
        detail['rollout.line'] = 'largest distance off the line %.0f ft' % roll
    if max(ext['ail'], ext['rud']) > CONTROL_MARGIN:
        broke.append('control.margin')
        detail['control.margin'] = 'aileron %.2f, ruddervators %.2f of travel' % (ext['ail'], ext['rud'])
    return dict(broke=broke, first=broke[0] if broke else None, detail=detail, heading_deg=round(hdg, 1), rollout_ft=round(roll, 1), touchdown_ft=round(xt_td, 1),
                aileron=round(ext['ail'], 2), rudder=round(ext['rud'], 2), sink=round(sink, 2))


def search(weight):
    runs, limit, first = [], None, None
    kt = START_KT
    while kt <= MAX_KT:
        r = judge(land(kt, weight))
        r['kt'] = kt
        runs.append(r)
        print('%6.0f lb %3.0f kt: %-16s heading %4.1f deg, rollout %5.1f ft, rudder %.2f, aileron %.2f  %s' % (
            weight, kt, r['first'] or 'holds', r.get('heading_deg', float('nan')), r.get('rollout_ft', float('nan')), r.get('rudder', float('nan')), r.get('aileron', float('nan')),
            '; '.join('%s: %s' % kv for kv in r['detail'].items()) if r['detail'] else ''), flush=True)
        if r['broke']:
            first = dict(kt=kt, contract=r['first'], detail=r['detail'].get(r['first'], ''))
            break
        limit = kt
        kt += STEP_KT
    return dict(weight_lb=weight, limit_kt=limit, first_break=first, runs=runs)


def main():
    rows = [search(w) for w in WEIGHTS]
    out = dict(note='landlimit.py: the highest steady crosswind (kt, from the right, calm air otherwise, %g kt steps) at which every contract of the landing held, by weight, flown from 5 nmi out '
                    'in the landing configuration; contracts and their limits in the file\'s source (final.gate, flare.touchdown, rollout.line, control.margin)' % STEP_KT,
               weight_lb=[r['weight_lb'] for r in rows], crosswind_kt=[r['limit_kt'] for r in rows], rows=rows)
    if '--write' in sys.argv:
        json.dump(out, open(os.path.join(HERE, 'data', 'landing_limits.json'), 'w'), indent=1)
        print('written')
    return out


if __name__ == '__main__':
    main()
