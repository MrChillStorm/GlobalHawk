#!/usr/bin/env python3
"""Phase 7 part B checks: the two recorded landings flown by the laws, and one whole mission hands off
(docs/FLIGHT-LAWS.md, sections 5 and 8). About half a minute.

The mission manager is fdm/missionmgr.py, a stand-in in Python for the one that will run in FlightGear: it gives
the laws their next leg, target and mode ten times a second. Everything else is the laws in the JSBSim model.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H         # noqa: E402
import missionmgr as MM     # noqa: E402

NM = 6076.1
COURSE = 40.0
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, bool(ok), detail))


def unit(deg):
    return np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg))])


def landing_case(f, name, weight, elev, meas):
    fld = MM.Field(35.0, -117.0, elev)
    u = unit(COURSE)
    aim, far = fld.ll(0, 0), fld.ll(*(-8 * NM * u))
    d0 = 5 * NM
    start = fld.ll(*(-d0 * u))
    keas = math.sqrt(weight / (0.645 * 540 * 0.5 * 0.0023769)) / H.KT
    t = H.trim(f, alt=elev + 5.3 + d0 * 0.07782, kcas=keas, weight=weight, gamma=-4.45, gear=1.0, spoiler=2 / 3, lat=start[0], lon=start[1],
               psi=COURSE, terrain=elev)
    H.engage(f, t, pitch_mode=1, roll_mode=2, ground_steer=1, land_mode=1, rwy_elev_ft=elev, leg_lat0_deg=far[0], leg_lon0_deg=far[1],
             leg_lat1_deg=aim[0], leg_lon1_deg=aim[1])
    log = H.run(f, 260, every=6)
    add('M6', '%s landing: approach speed chosen by the law' % name, abs(log['target'][5] - meas['app']) <= 2, '%.1f KEAS (measured %d)' % (log['target'][5], meas['app']))
    judge_landing(log, name + ' landing', meas)


def judge_landing(log, name, meas=None):
    air = log['mains'] == 0
    if not (log['mains'] > 0).any():
        add('M7', '%s: touchdown' % name, False, 'never touched down')
        return
    i = int(np.argmax(log['mains'] > 0))
    app = (log['togo'] < 3 * NM) & (log['flare'] == 0) & air & (log['rollout'] == 0) & (log['t'] < log['t'][i])
    sp = log['spoiler'][app]
    inside = np.mean((sp >= 0.15) & (sp <= 0.95))
    verr = (log['keas'] - log['target'])[app]
    add('M5', '%s: approach from 3 nmi' % name, np.abs(log['glide'][app]).max() <= 30 and np.abs(verr).max() <= 3 and inside >= 0.9 and abs(log['xt'][app][-1]) <= 20,
        'glide path within %.1f ft, speed within %.2f kt, spoilers %.2f to %.2f (inside 0.15-0.95 for %.0f %% of it), %.1f ft off the centreline at the flare' % (
            np.abs(log['glide'][app]).max(), np.abs(verr).max(), sp.min(), sp.max(), 100 * inside, abs(log['xt'][app][-1])))
    sink, pitch, spd, spo = -log['hdot'][i - 1] * 0.3048, log['theta'][i], log['keas'][i], log['spoiler'][i - 1]
    ok = 0.3 <= sink <= 1.2 and 1.5 <= pitch <= 3.5 and 0.10 < spo < 1.0 and (meas is None or abs(spd - meas['td']) <= 5)
    add('M7', '%s: touchdown' % name, ok, 'sink %.2f m/s, pitch %.2f deg, %.1f KEAS, spoilers %.2f, %.0f ft past the aiming point%s' % (
        sink, pitch, spd, spo, -log['togo'][i], '' if meas is None else ' (measured %.2f m/s, %.1f deg, %d KEAS)' % (meas['sink'], meas['pitch'], meas['td'])))
    g, ud = log['vg'][i:], log['udot'][i:]
    k = (g < 100) & (g > 50)
    dec = -ud[k].mean() / 32.174
    add('M8', '%s: rollout' % name, abs(dec - 0.235) <= 0.03 and np.abs(log['xt'][i:]).max() <= 15 and g[-1] <= 16,
        'deceleration %.3f g between 100 and 50 kt, within %.1f ft of the centreline, down to %.0f kt' % (dec, np.abs(log['xt'][i:]).max(), g[-1]))


def mission(f):
    elev = 2300.0
    fld = MM.Field(34.9, -117.88, elev)
    u, r = unit(COURSE), unit(COURSE + 90.0)
    P = lambda a, b=0.0: fld.ll(*(a * u + b * r))
    stand = P(-400, 400)
    plan = [
        dict(kind='taxi', points=[P(-400), P(0)], speed=15, turn_speed=8, stop=True),
        dict(kind='takeoff', start=P(0), end=P(10000), elev=elev),
        dict(kind='route', points=[P(25 * NM) + (20000.0,), P(25 * NM, 25 * NM) + (20000.0,),
                                   fld.ll(*(25 * NM * u + 25 * NM * r + 25 * NM * unit(COURSE + 210.0))) + (20000.0,),
                                   P(-16 * NM) + (6500.0,)]),
        dict(kind='land', fix=P(-16 * NM), aim=P(0), elev=elev),
        dict(kind='taxi', points=lambda m: [fld.ll(*(np.array(fld.ne(*m.here())) + 400 * u)), fld.ll(*(np.array(fld.ne(*m.here())) + 400 * u + 300 * r))],
             speed=12, turn_speed=8, stop=True),
    ]
    H.on_ground(f, 25600.0, elevation=elev, heading=COURSE - 90.0, lat=stand[0], lon=stand[1])
    H.brakes(f, 0)
    f['ap/speed-schedule'] = 1
    f['ap/theta-cmd-deg'] = f['attitude/theta-deg']
    mgr = MM.Manager(f, plan)
    f['ap/engaged'] = 1
    keys = H.AP_LOG + (('item', None), ('steer', 'fcs/steer-pos-deg'), ('taxi', 'ap/taxi-speed-kt'), ('altcmd', 'ap/alt-cmd-ft'), ('pm', 'ap/pitch-mode'), ('len', 'ap/leg-length-ft'))
    log = {k: [] for k, _ in keys}
    t0 = f['simulation/sim-time-sec']
    for i in range(int(3.0 * 3600 * H.HZ)):
        mgr.step()
        if mgr.done or not f.run():
            break
        if i % 12 == 0:
            for k, p in keys:
                log[k].append(mgr.i if p is None else f[p])
    log = {k: np.array(v) for k, v in log.items()}
    log['t'] = log['t'] - t0
    finite = bool(np.all(np.isfinite(log['alt'])) and np.all(np.isfinite(log['phi'])))
    last = plan[-1].get('_pts', [None])[-1]
    off = math.hypot(*(np.array(fld.ne(log['lat'][-1], log['lon'][-1])) - np.array(fld.ne(*last)))) if last else float('inf')
    add('M1', 'the whole mission, hands off', mgr.done and finite and off <= 50 and log['vg'][-1] < 0.5,
        '%s in %.0f min; ends %.0f ft from the last point at %.1f kt; highest %.0f ft; fuel used %.0f lb' % (
            'completed' if mgr.done else 'stopped at item %d (%s)' % (mgr.i, plan[min(mgr.i, len(plan) - 1)]['kind']), log['t'][-1] / 60, off, log['vg'][-1],
            log['alt'].max(), log['weight'][0] - log['weight'][-1]))
    # M2 taxi (first and last items): distance from the path, which is the legs with the corners cut where the
    # manager changes leg 40 ft early
    def off_path(lat, lon, pts):
        p = np.array(fld.ne(lat, lon))
        best = float('inf')
        for a, b in zip(pts[:-1], pts[1:]):
            a, b = np.array(fld.ne(*a)), np.array(fld.ne(*b))
            w = np.clip(np.dot(p - a, b - a) / np.dot(b - a, b - a), 0, 1)
            best = min(best, float(np.linalg.norm(p - (a + w * (b - a)))))
        return best
    for item, label in ((0, 'taxi out'), (4, 'taxi in')):
        k = np.nonzero(log['item'] == item)[0]
        if not len(k):
            add('M2', label, False, 'not reached')
            continue
        pts = plan[item]['_pts']
        d = np.array([off_path(log['lat'][n], log['lon'][n], pts) for n in k])
        moving = (log['t'][k] > log['t'][k][0] + 2) & (log['taxi'][k] > 0.5)      # not the stop itself: there the command is zero by design
        over = (log['vg'][k] - log['taxi'][k])[moving].max()
        add('M2', label, d.max() <= 30 and np.percentile(d, 70) <= 10 and over <= 3,
            'within %.1f ft of the path (the corners), within %.1f ft for 70 %% of the way; %.1f kt over the commanded speed at most; bank up to %.2f deg' % (
                d.max(), np.percentile(d, 70), over, np.abs(log['phi'][k]).max()))
    # M3 takeoff
    k = log['item'] == 1
    if k.any():
        t, v = log['t'][k], log['kcas'][k]
        t130 = float(np.interp(130, v, t)) - t[0]
        lift = int(np.argmax(log['wh'][k] > 2.0))
        first_cmd = t[np.argmax(log['theta'][k] > 1.0)] - t[0]
        add('M3', 'takeoff', np.abs(log['xt'][k]).max() <= 15 and log['theta'][k][lift] < 8 and abs(t130 / 37.5 - 1) <= 0.15 and 120 <= log['keas'][k][lift] <= 145,
            '130 KIAS %.1f s after the start (Pastor 37.5); nose through 1 deg at %.1f s; liftoff at %.0f KEAS and %.1f deg; within %.1f ft of the centreline' % (
                t130, first_cmd, log['keas'][k][lift], log['theta'][k][lift], np.abs(log['xt'][k]).max()))
    # M4 enroute
    k = log['item'] == 2
    if k.any():
        t = log['t'][k]
        level = k & (log['pm'] == 2)
        tl = log['t'][level]
        held = np.abs(log['alt'][level] - log['altcmd'][level])
        settled = level & np.concatenate([[False], np.diff(log['pm']) == 0]) & (np.abs(log['alt'] - log['altcmd']) < 150)
        over = float(held.max()) if len(held) else float('nan')
        late = held[tl > tl[0] + 120] if len(tl) else np.array([0.0])
        verr = np.abs(log['kcas'][level] - log['target'][level])[tl > tl[0] + 120] if len(tl) else np.array([0.0])
        xt_nm = np.abs(log['xt'][k]) / NM
        # after each leg change, the time for the cross-track error to come inside 0.25 nmi
        add('M4', 'enroute: height', over <= 150 and late.max() <= 50 and verr.max() <= 3,
            'capture within %.0f ft of the commanded height, held within %.1f ft and %.2f kt after two minutes level' % (over, late.max(), verr.max()))
        add('M4', 'enroute: track', np.percentile(xt_nm, 80) <= 0.25, 'cross-track error under 0.25 nmi for %.0f %% of the route; largest %.2f nmi (in the turns); bank up to %.1f deg' % (
            100 * np.mean(xt_nm <= 0.25), xt_nm.max(), np.abs(log['phi'][k]).max()))
        add('M4', 'enroute: bank inside the limit', np.abs(log['phi'][k]).max() <= 26.0, 'bank up to %.1f deg (limit 25 below 30,000 ft, 1 deg allowed over)' % np.abs(log['phi'][k]).max())
    k = log['item'] == 3
    if k.any():
        sub = {key: val[k] for key, val in log.items()}
        judge_landing(sub, 'mission landing')
    return log, mgr


def main():
    f = H.load()
    landing_case(f, '2013', 20800.0, 2357.0, dict(app=133, td=130, pitch=2.4, sink=0.66))
    landing_case(f, '2014', 17100.0, 574.0, dict(app=120, td=122, pitch=2.3, sink=0.75))
    log, mgr = mission(f)
    for tag, name, ok, detail in rows:
        print('%-3s %-44s %s  %s' % (tag, name, 'pass' if ok else 'MISS', detail))
    miss = sum(1 for r in rows if not r[2])
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))
    print('\nthe mission, as the manager saw it:')
    for t, text in mgr.events:
        print('  %7.1f min  %s' % (t / 60, text))
    np.savez_compressed(os.path.join(HERE, 'out', 'mission7b.npz'), **log)


if __name__ == '__main__':
    main()
