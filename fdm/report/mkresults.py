#!/usr/bin/env python3
"""Time histories and curves for the report's figures, from the flight model itself, into results/histories.json.
The report's numbers are the check logs'; these are the same runs the checks make, kept as curves.

    qrun /opt/homebrew/bin/python3 fdm/report/mkresults.py        a few minutes
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness as H                     # noqa: E402
import mission as M                     # noqa: E402
import missionmgr as MM                 # noqa: E402
import phase7a_checks as A              # noqa: E402
import phase7b_checks as B              # noqa: E402
import phase7c_checks as C              # noqa: E402

out = {}
r = lambda x, n=3: [round(float(v), n) for v in x]


def keep(log, keys, step=1, digits=3):
    return {k: r(log[k][::step], 5 if k in ('lat', 'lon') else digits) for k in keys}


f = H.load()

# ---- the quasi-steady mission against Pastor: the climb and the cruise-climb
log = M.fly(f)
rows, hours = M.compare(log)
top = int(np.argmax(log['alt'] >= 55000))
out['mission'] = dict(t=r(log['t'][::4], 0), alt=r(log['alt'][::4], 0), weight=r(log['weight'][::4], 0), hours=hours,
                      pastor_climb={str(k): list(v) for k, v in M.PASTOR_CLIMB.items()}, pastor_cruise=[[list(a), list(b)] for a, b in M.PASTOR_CRUISE],
                      climb=dict(t=r(log['t'][:top + 2], 0), alt=r(log['alt'][:top + 2], 0)),
                      rows=[[tag, name, float(v), float(ref), float(lim), kind] for tag, name, v, ref, lim, kind in rows])
print('mission: %.1f h' % hours, flush=True)

# ---- the laws: steps at the three conditions, and the climb hands off
out['steps'] = {}
trims = {k: H.trim(f, **dict(c)) for k, c in A.CONDS.items()}
for name, t in trims.items():
    s = {}
    H.engage(f, t, pitch_mode=0, thrust_mode=0)
    th0 = f['attitude/theta-deg']
    step = -2.0 if name == 'approach' else 2.0
    f['ap/theta-cmd-deg'] = th0 + step
    lg = H.run(f, 12, every=6)
    s['pitch'] = dict(t=r(lg['t']), y=r((lg['theta'] - th0) / step))
    H.engage(f, t, pitch_mode=2, thrust_mode=3)
    half = 0.5 * f['ap/bank-limit-deg']
    f['ap/bank-cmd-deg'] = half
    lg = H.run(f, 14, every=6)
    s['bank'] = dict(t=r(lg['t']), y=r(lg['phi'] / half), beta=r(lg['beta']), to=half)
    H.engage(f, t, pitch_mode=2, thrust_mode=3, roll_mode=1)
    f['ap/heading-cmd-deg'] = 90.0
    lg = H.run(f, 420 if name == 'cruise' else 200, every=24)
    psi = (lg['psi'] - lg['psi'][0] + 180) % 360 - 180
    s['heading'] = dict(t=r(lg['t']), psi=r(psi), phi=r(lg['phi']), turn=float((90.0 - lg['psi'][0] + 180) % 360 - 180))
    out['steps'][name] = s
    print('steps:', name, flush=True)
t10 = H.trim(f, alt=10000, kcas=150, weight=25400, throttle=1.0)
H.engage(f, t10, pitch_mode=1, thrust_mode=1, speed_schedule=1, roll_mode=1)
lg = H.run(f, 6000, every=240)
out['climb_laws'] = keep(lg, ('t', 'alt', 'kcas', 'target', 'mach'), digits=2)
print('climb under the laws', flush=True)

# ---- the 2013 landing under the laws
weight, elev = 20800.0, 2300.0
fld = MM.Field(35.0, -117.0, elev)
u = B.unit(B.COURSE)
aim, far, d0 = fld.ll(0, 0), fld.ll(*(-8 * B.NM * u)), 5 * B.NM
first = fld.ll(*(-d0 * u))
keas = math.sqrt(weight / (0.645 * 540 * 0.5 * 0.0023769)) / H.KT
t = H.trim(f, alt=elev + 5.3 + d0 * 0.07782, kcas=keas, weight=weight, gamma=-4.45, gear=1.0, spoiler=2 / 3, lat=first[0], lon=first[1], psi=B.COURSE, terrain=elev)
H.engage(f, t, pitch_mode=1, roll_mode=2, ground_steer=1, land_mode=1, rwy_elev_ft=elev, leg_lat0_deg=far[0], leg_lon0_deg=far[1], leg_lat1_deg=aim[0], leg_lon1_deg=aim[1])
lg = H.run(f, 260, every=12)
out['landing'] = keep(lg, ('t', 'togo', 'wh', 'keas', 'hdot', 'theta', 'spoiler', 'vg', 'udot', 'mains', 'glide'))
out['landing']['weight'] = weight
print('landing', flush=True)

# ---- the whole mission
lg, mgr = B.mission(f)
out['flight'] = keep(lg, ('t', 'alt', 'kcas', 'lat', 'lon', 'item', 'phi', 'weight'), step=20, digits=1)
print('whole mission: %.0f min' % (lg['t'][-1] / 60), flush=True)

# ---- the 2017 case: one of two navigators ramps to 30 deg in roll
C.cruise(f, kna_on=0, knb_on=0)
lg = C.fly_nav(f, 40, lambda t: f.__setitem__('nav/lna-roll-error-deg', min(30.0, max(0.0, (t - 5.0) * 10.0))))
out['navigator'] = dict(t=r(lg['t'][::6]), phi=r(lg['phi'][::6]), voted=r(lg['vroll'][::6]), wrong=r(lg['phi'][::6] + np.clip((lg['t'][::6] - 5.0) * 10.0, 0, 30)),
                        flagged=float(lg['t'][np.argmax(lg['mis'] > 0)]) if (lg['mis'] > 0).any() else None)
C.healthy(f)
print('navigator', flush=True)

# ---- the engine stopped at 20,000 ft, 30 nmi out, flying away: the check's own run, its log caught
caught = {}
fly_plan = C.fly_plan


def catching(*a, **k):
    caught['log'], t0 = fly_plan(*a, **k)
    return caught['log'], t0


C.fly_plan = catching
C.engine_out(f, 'E1', 20000.0, 30)
C.fly_plan = fly_plan
lg = caught['log']
fld = MM.Field(34.9, -117.88, C.ELEV)
ne = np.array([fld.ne(a, b) for a, b in zip(lg['lat'][::20], lg['lon'][::20])])
out['engine_out'] = dict(t=r(lg['t'][::20], 1), alt=r(lg['alt'][::20], 0), north=r(ne[:, 0] / B.NM, 3), east=r(ne[:, 1] / B.NM, 3), spoiler=r(lg['spoiler'][::20]),
                         keas=r(lg['keas'][::20], 1), course=C.COURSE, elev=C.ELEV)
print('engine out', flush=True)

# ---- the engine as modelled, and the landing's roll by weight
e = json.load(open(os.path.join(HERE, '..', 'data', 'engine.json')))
out['engine'] = dict(altitude_ft=e['tables']['altitude_ft'], mach=e['tables']['mach'], max_thrust_lbf=e['tables']['max_thrust_lbf'][1], limit=e['tables']['limit'],
                     delta_T_K=e['tables']['delta_T_K'])
json.dump(out, open(os.path.join(HERE, 'results', 'histories.json'), 'w'))
print('wrote results/histories.json: %d kB' % (os.path.getsize(os.path.join(HERE, 'results', 'histories.json')) // 1024))
