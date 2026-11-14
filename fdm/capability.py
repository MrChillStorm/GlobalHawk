#!/usr/bin/env python3
"""The aircraft's capability, as the ground station's planner takes it (docs/PLAN.md, "The planner uses the aircraft's capability tables").

    python3 fdm/capability.py measure    flies the laws (about 5 minutes): the descent as the mission manager flies it, and the slowing
                                         down in the landing configuration; writes fdm/data/capability_flown.json
    python3 fdm/capability.py            writes GlobalHawk/gcs/js/capability.js from fdm/laws.py's constants, the data files and
                                         capability_flown.json (a second)
    python3 fdm/capability.py --check    fails if the committed js/capability.js is not what the laws and the data say today

One source: the station reads no capability number from anywhere else. Constants come from `laws` and `missionmgr` themselves
(the bank limit, the angle-of-attack limit, the roll delay table fdm/rolltest.py measured, the approach lift coefficient, the glide
path), what the aircraft does comes from flying it. The forecast's descent (js/perfdata.js, fdm/gcs_perf.py) is the flown one: the
trim it had taken at idle thrust was 15 to 50 % steeper than the manager's descent.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402
import laws                     # noqa: E402
import mission as M             # noqa: E402
import missionmgr as MM         # noqa: E402

DATA = os.path.join(HERE, 'data', 'capability_flown.json')
OUT = os.path.join(HERE, '..', 'GlobalHawk', 'gcs', 'js', 'capability.js')
NM = 6076.1
ALT = [2500.0, 5000.0, 10000.0, 15000.0, 20000.0, 25000.0, 30000.0, 35000.0, 40000.0, 45000.0, 50000.0, 55000.0, 60000.0, 65000.0]
WEIGHT = [11500.0, 15000.0, 19000.0, 23000.0, 26700.0]
WEIGHT_LAND = [12000.0, 15000.0, 19000.0, 23000.0, 26700.0]      # the landing weights: the trim at 150 KCAS in the landing configuration does not exist at 11,500 lb
FAR = -20000.0                  # ft: the ground a long way down, so that a descent from 2,500 ft is not a landing
ELEV = 174.0
MAX_JOIN_DEG = 120.0            # the planner's: the most a corner may turn (the laws fly one to 150 deg as a fly-by and past that as a fly-over); mine


def approach_kcas(weight):
    return math.sqrt(weight / (laws.APPROACH_CL * laws.WING_AREA * 0.5 * 0.0023769)) / H.KT


def flown_descent(f, alt, weight, seconds=170.0, after=70.0):
    """The descent the mission manager flies from a height: the rate (ft/min, negative) and the fuel flow (lb/h) after the first
    `after` seconds, on the speed schedule, idle thrust and half spoilers, standard atmosphere, no wind. It starts from the descent's own
    trim (the level trim does not exist above the weight's ceiling), so what is measured is the manager's descent with its laws and not
    the settling of the start. None where the aircraft does not settle (the engine at idle high up with a light weight)."""
    try:
        t = H.trim(f, alt=alt, weight=weight, lat=34.9, lon=-117.9, psi=90.0, terrain=FAR, throttle=0.0, spoiler=0.5, **M.schedule(alt))
    except ValueError:
        return None, None
    H.engage(f, t, pitch_mode=1, thrust_mode=2, speed_schedule=1, spoiler_mode=1, spoiler_cmd=0.5)
    fld = MM.Field(34.9, -117.9, FAR)
    mgr = MM.Manager(f, [dict(kind='route', points=[fld.ll(0, 400 * NM) + (alt - 8000.0,)])])
    f['ap/engaged'] = 1
    rows = []
    t0 = f['simulation/sim-time-sec']
    for i in range(int(seconds * H.HZ)):
        mgr.step()
        f.run()
        if i % H.HZ == 0 and f['simulation/sim-time-sec'] - t0 > after:
            rows.append((f['velocities/h-dot-fps'], f['engine/fuel-flow-pph']))
    a = np.array(rows)
    rate, flow = float(np.mean(a[:, 0]) * 60.0), float(np.mean(a[:, 1]))
    if not (math.isfinite(rate) and -6000.0 < rate < -100.0) or float(np.std(a[:, 0]) * 60.0) > 300.0:
        return None, None                    # not a steady descent
    return rate, flow


def flown_slowing(f, weight):
    """Level on the schedule's 150 KCAS at the landing fix, the landing configuration put on, the speed commanded to the approach speed, well
    under the glide path so that it is not taken over meanwhile: how long and how far the aircraft takes to come to within CAPTURE_SPEED_KT
    of the approach speed, how far under it the speed goes, how long until it holds the height again (the configuration makes it dive and the
    altitude hold climbs it back: the last time it moved more than 3 ft/s up or down), and the angle of attack when it has settled in the configuration."""
    u = np.array([0.0, 1.0])
    fld = MM.Field(60.3, 24.96, ELEV)
    aim, fix = fld.ll(0, 0), fld.ll(*(-12 * NM * u))
    app = approach_kcas(weight)
    t = H.trim(f, alt=ELEV + 3000.0, kcas=M.schedule(0)['kcas'], weight=weight, lat=fix[0], lon=fix[1], psi=90.0, terrain=ELEV)
    H.engage(f, t, pitch_mode=2, thrust_mode=3)
    mgr = MM.Manager(f, [dict(kind='land', fix=fix, aim=aim, elev=ELEV)])
    f['ap/engaged'] = 1
    t0, s0 = f['simulation/sim-time-sec'], None
    slow_s = slow_ft = None
    vmin, alpha, busy = 1e9, [], 0.0
    for i in range(int(260 * H.HZ)):
        mgr.step()
        f.run()
        now = f['simulation/sim-time-sec'] - t0
        v = f['velocities/vc-kts']
        if s0 is None:
            s0 = f['ap/leg-togo-ft']
        if f['ap/land-mode'] == 1:
            break
        if slow_s is None and v <= app + MM.CAPTURE_SPEED_KT:
            slow_s, slow_ft = now, s0 - f['ap/leg-togo-ft']
        vmin = min(vmin, v)
        if abs(f['velocities/h-dot-fps']) > 3.0:
            busy = now                          # the last time the aircraft was climbing or sinking more than 3 ft/s, level as it is held
        if slow_s is not None and now > slow_s + 25.0:
            alpha.append(f['aero/alpha-deg'])          # settled in the configuration at the approach speed, before the path is taken over
    return dict(approach_kcas=round(app, 1), slow_s=None if slow_s is None else round(slow_s, 1), slow_ft=None if slow_ft is None else round(slow_ft),
                vmin_kcas=round(vmin, 1), settle_s=round(busy, 1), alpha_level=round(float(np.mean(alpha)), 2) if alpha else None)


def measure():
    f = H.load()
    if 'slowing' in sys.argv:                  # only the slowing down again: the descents stay as they are in the file
        out = json.load(open(DATA))
        out['slowing'] = []
        return slowing_part(out)
    out = dict(alt_ft=ALT, weight_lb=WEIGHT, descent_fpm=[], descent_pph=[], slowing=[])
    trim = {k: [] for k in ('fpm', 'pph')}
    for a in ALT:
        rows = [flown_descent(f, a, w) for w in WEIGHT]
        out['descent_fpm'].append([None if r[0] is None else round(r[0], 1) for r in rows])
        out['descent_pph'].append([None if r[1] is None else round(r[1], 1) for r in rows])
        print('%6.0f ft: descent %s ft/min' % (a, out['descent_fpm'][-1]), flush=True)
    # where the descent does not settle (60,000 ft and up, light weights) the table's old idle trim is scaled by the ratio flown / trim at the
    # highest height of that weight that did settle: noted in the file
    filled = []
    for j, w in enumerate(WEIGHT):
        last = max(i for i in range(len(ALT)) if out['descent_fpm'][i][j] is not None)
        t_last = H.trim(f, alt=ALT[last], weight=w, throttle=0.0, spoiler=0.5, **M.schedule(ALT[last]))
        trim_fpm = lambda tt: tt['ktas'] * H.KT * math.sin(math.radians(tt['cond']['gamma'])) * 60.0
        ratio, ratio_pph = out['descent_fpm'][last][j] / trim_fpm(t_last), out['descent_pph'][last][j] / t_last['fuel_flow']
        for i in range(last + 1, len(ALT)):
            tt = H.trim(f, alt=ALT[i], weight=w, throttle=0.0, spoiler=0.5, **M.schedule(ALT[i]))
            out['descent_fpm'][i][j] = round(trim_fpm(tt) * ratio, 1)
            out['descent_pph'][i][j] = round(tt['fuel_flow'] * ratio_pph, 1)
            filled.append([ALT[i], w])
    out['filled_from_trim'] = filled
    return slowing_part(out)


def flown_capture(f, weight, agl):
    """The landing item begun at the fix 10 nmi out, level on the schedule's 150 KCAS at a height over the ground, as the manager flies it:
    how long until it takes the glide path over (s), and the highest above the path it goes, the lowest below it once within 10 ft of it,
    the crossings of it beyond 5 ft (the M5b limits: 8 ft, -12 ft, none)."""
    u = np.array([0.0, 1.0])
    fld = MM.Field(60.3, 24.96, ELEV)
    aim, fix = fld.ll(0, 0), fld.ll(*(-10 * NM * u))
    t = H.trim(f, alt=ELEV + agl, kcas=M.schedule(0)['kcas'], weight=weight, lat=fix[0], lon=fix[1], psi=90.0, terrain=ELEV)
    H.engage(f, t, pitch_mode=2, thrust_mode=3)
    plan = [dict(kind='land', fix=fix, aim=aim, elev=ELEV)]
    mgr = MM.Manager(f, plan)
    f['ap/engaged'] = 1
    t0, cap_t, err = f['simulation/sim-time-sec'], None, []
    for i in range(int(400 * H.HZ)):
        mgr.step()
        f.run()
        if plan[0]['_on_path']:
            if cap_t is None:
                cap_t = f['simulation/sim-time-sec'] - t0
            if f['ap/flare'] > 0 or f['ap/leg-togo-ft'] < 1500 or f['ap/on-mains'] > 0:
                break
            err.append(f['ap/glide-error-ft'])
    if cap_t is None or not err:
        return None
    e = np.array(err)
    reached = int(np.argmax(e >= -10.0)) if (e >= -10).any() else len(e)
    under = float(e[reached:].min()) if reached < len(e) else float(e.min())
    big = e[reached:][np.abs(e[reached:]) > 5]
    cross = int(np.sum(np.diff(np.sign(big)) != 0)) if len(big) > 1 else 0
    return dict(gap_s=round(cap_t, 1), over=round(float(e.max()), 1), under=round(under, 1), crossings=cross)


def capture_gap(f, weight):
    """How far under the glide path the aircraft may be at the fix, 10 nmi out, level on 150 KCAS, for the manager to take the path over cleanly
    (over at most 8 ft, no dip under -12 ft, no crossing beyond 5 ft): the path's height at the fix less the highest height over the ground at which the
    capture is clean and is clean at every lower one tried (down to 2,000 ft), ft. It is the way the aircraft needs to settle in the landing
    configuration (it dives when the gear and spoilers go on and the altitude hold climbs it back) before the path comes down to it."""
    path = laws.GLIDE_TAN * 10 * NM + 5.3
    runs = []
    for agl in np.arange(4600.0, 1999.0, -200.0):
        r = flown_capture(f, weight, float(agl))
        if r is not None:
            r['agl'] = float(agl)
            runs.append(r)
    clean = [r['over'] <= 8.0 and r['under'] >= -12.0 and r['crossings'] == 0 for r in runs]
    first = next((i for i in range(len(runs)) if all(clean[i:])), None)
    return (None if first is None else round(path - runs[first]['agl'])), runs


def slowing_part(out):
    f = H.load(rebuild=False)               # a fresh model: the trims above the weights' ceilings leave it in a state the next trim does not start from
    for w in WEIGHT_LAND:
        s = flown_slowing(f, w)
        s['weight_lb'] = w
        s['capture_gap_ft'], runs = capture_gap(f, w)
        s['capture_runs'] = runs
        out['slowing'].append(s)
        print('        the path may be %s ft above it at the fix: %s' % (s['capture_gap_ft'], ' '.join('%.0f:%.0fs %.1f/%.1f/%d' % (r['agl'], r['gap_s'], r['over'], r['under'], r['crossings']) for r in runs)), flush=True)
        print('%6.0f lb: approach %.1f KCAS, within %d kt of it after %s s and %s ft, lowest speed %.1f, level again after %.0f s, angle of attack %.2f deg' % (
            w, s['approach_kcas'], MM.CAPTURE_SPEED_KT, s['slow_s'], s['slow_ft'], s['vmin_kcas'], s['settle_s'], s['alpha_level'] or float('nan')), flush=True)
    out['note'] = 'fdm/capability.py measure: the descent as the mission manager flies it (idle thrust, half spoilers, the speed schedule; where it does not settle, filled_from_trim: the old idle trim times the ratio flown / trim at the highest height of that weight that did settle), and the slowing down in the landing configuration from 150 KCAS'
    json.dump(out, open(DATA, 'w'), indent=1)
    print('wrote', os.path.relpath(DATA))


def build():
    flown = json.load(open(DATA))
    kcas, delay = laws.roll_delay()
    cap = dict(
        turn=dict(bank_limit=[list(p) for p in laws.BANK_LIMIT], bank_command=laws.BANK_COMMAND, bank_rate_dps=laws.BANK_RATE,
                  roll_delay=dict(kcas=kcas, delay_s=delay), alpha_limit=[list(p) for p in laws.ALPHA_LIMIT], alpha_zero_lift_deg=laws.ALPHA_ZERO_LIFT,
                  alpha_margin_deg=laws.TURN_ALPHA_MARGIN, min_bank_deg=laws.TURN_MIN_BANK, fly_by_max_deg=laws.TURN_FLY_BY_MAX, max_join_deg=MAX_JOIN_DEG, g_fps2=32.174),
        approach=dict(cl=laws.APPROACH_CL, wing_area_ft2=laws.WING_AREA, glide_tan=laws.GLIDE_TAN, capture_speed_kt=MM.CAPTURE_SPEED_KT,
                      schedule_kcas=laws.SCHEDULE_KCAS, aim_height_ft=5.3, min_final_nm=8.0),
        flown=dict(alt_ft=flown['alt_ft'], weight_lb=flown['weight_lb'], descent_fpm=flown['descent_fpm'], descent_pph=flown['descent_pph'],
                   slowing=flown['slowing']),
    )
    return cap


def js(cap):
    return ('/** Generated by fdm/capability.py from fdm/laws.py, the data files and fdm/data/capability_flown.json: do not edit. The aircraft\'s capability, as the planner takes it. */\n'
            "(function (root) {\n  'use strict';\n  const data = %s;\n"
            "  if (typeof module !== 'undefined' && module.exports) module.exports = data;\n  else (root.GCS = root.GCS || {}).capability = data;\n"
            "})(typeof window !== 'undefined' ? window : globalThis);\n" % json.dumps(cap))


def main():
    if 'measure' in sys.argv:
        measure()
        return
    text = js(build())
    if '--check' in sys.argv:
        have = open(OUT).read() if os.path.exists(OUT) else ''
        if have != text:
            print('js/capability.js is not what the laws and the data say today: run python3 fdm/capability.py')
            sys.exit(1)
        print('js/capability.js is current')
        return
    open(OUT, 'w').write(text)
    print('wrote', os.path.relpath(OUT))


if __name__ == '__main__':
    main()
