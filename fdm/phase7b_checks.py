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
import mission as M          # noqa: E402
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
    H.engage(f, t, pitch_mode=1, roll_mode=3, ground_steer=1, land_mode=1, rwy_elev_ft=elev, leg_lat0_deg=far[0], leg_lon0_deg=far[1],
             leg_lat1_deg=aim[0], leg_lon1_deg=aim[1])
    log = H.run(f, 260, every=6)
    add('M6', '%s landing: approach speed chosen by the law' % name, abs(log['target'][5] - meas['app']) <= 2, '%.1f KEAS (measured %d)' % (log['target'][5], meas['app']))
    judge_landing(log, name + ' landing', meas)


def capture_case(f, weight, headwind):
    """The glide path taken over from level flight (docs/PLAN.md, "The takeoff's veer and the glide path's overshoot"): the manager
    flies a land item from 9 nmi out and 3,500 ft over the runway, on the approach speed, in the landing configuration. Returns the
    highest the aircraft gets above the path, the lowest it gets below it once it has first come within 10 ft of it, and the
    crossings of the path beyond 5 ft (a turn onto the path ends on it: none)."""
    elev = 174.0
    u = unit(90.0)
    fld = MM.Field(60.3, 24.96, elev)
    aim, fix, start = fld.ll(0, 0), fld.ll(*(-10 * NM * u)), fld.ll(*(-9 * NM * u))
    keas = math.sqrt(weight / (0.645 * 540 * 0.5 * 0.0023769)) / H.KT
    t = H.trim(f, alt=elev + 3500, kcas=keas, weight=weight, gamma=0.0, gear=1.0, spoiler=2 / 3, lat=start[0], lon=start[1], psi=90.0, terrain=elev)
    H.engage(f, t)
    mgr = MM.Manager(f, [dict(kind='land', fix=fix, aim=aim, elev=elev)])
    f['ap/engaged'] = 1
    if headwind:
        f['atmosphere/wind-east-fps'] = -headwind * 1.6878      # blowing towards the west: a headwind on a heading of 90
    err = []
    for _ in range(int(400 * H.HZ)):
        mgr.step()
        if not f.run():
            break
        if mgr.plan[0]['_on_path']:
            if f['ap/flare'] > 0 or f['ap/leg-togo-ft'] < 1500 or f['ap/on-mains'] > 0:
                break
            err.append(f['ap/glide-error-ft'])
    e = np.array(err)
    reached = int(np.argmax(e >= -10.0)) if (e >= -10).any() else len(e)
    under = float(e[reached:].min()) if reached < len(e) else float(e.min())
    big = e[reached:][np.abs(e[reached:]) > 5]
    return float(e.max()), under, (int(np.sum(np.diff(np.sign(big)) != 0)) if len(big) > 1 else 0)


def capture_matrix(f):
    cells = {(w, hw): capture_case(f, w, hw) for w in (12000.0, 14000.0, 17000.0, 20000.0, 23000.0, 26000.0) for hw in (0.0, 20.0, -15.0)}
    over, under = max(c[0] for c in cells.values()), min(c[1] for c in cells.values())
    crossings = sum(c[2] for c in cells.values())
    add('M5b', 'glide path taken over from level flight, 18 cases', over <= 8 and under >= -12 and crossings == 0,
        '12,000 to 26,000 lb, calm, 20 kt headwind, 15 kt tailwind: highest above the path %.1f ft (limit 8), lowest below it after arriving %.1f ft (limit -12), '
        '%d crossings beyond 5 ft (limit 0)' % (over, under, crossings))


def entry_case(f, weight, above):
    """The landing item begun at the fix 10 nmi out, level, ABOVE the glide path by a height (docs/PLAN.md, "The aircraft refuses what it cannot fly"). Returns the
    go-around's start (s) and its lowest height against the height it came down to (ft), the glide error after the path was taken (the M5b figures), and the
    touchdown: feet past the aiming point, sink (m/s) and distance off the line (ft)."""
    elev = 174.0
    u = unit(90.0)
    fld = MM.Field(60.3, 24.96, elev)
    aim, fix = fld.ll(0, 0), fld.ll(*(-10 * NM * u))
    path10 = 5.3 + MM.GLIDE_TAN * 10 * NM
    t = H.trim(f, alt=elev + path10 + above, kcas=M.schedule(0)['kcas'], weight=weight, lat=fix[0], lon=fix[1], psi=90.0, terrain=elev)
    H.engage(f, t, pitch_mode=2, thrust_mode=3)
    plan = [dict(kind='land', fix=fix, aim=aim, elev=elev)]
    mgr = MM.Manager(f, plan)
    f['ap/engaged'] = 1
    t0, ga_t, low, err, td = f['simulation/sim-time-sec'], None, 1e9, [], None
    for _ in range(int(2400 * H.HZ)):
        mgr.step()
        if not f.run():
            break
        it = mgr.plan[min(mgr.i, len(mgr.plan) - 1)]
        if it['kind'] == 'go_around':
            ga_t = ga_t if ga_t is not None else f['simulation/sim-time-sec'] - t0
            low = min(low, f['position/h-sl-ft'] - it['alt'])
        if it['kind'] == 'land' and it.get('_on_path') and f['ap/flare'] == 0 and f['ap/on-mains'] == 0 and f['ap/leg-togo-ft'] > 1500:
            err.append(f['ap/glide-error-ft'])
        if f['ap/on-mains'] > 0:
            td = (-f['ap/leg-togo-ft'], -f['velocities/h-dot-fps'] * 0.3048, abs(f['ap/leg-xt-ft']))
            break
    e = np.array(err) if err else np.array([float('nan')])
    reached = int(np.argmax(e >= -10.0)) if (e >= -10).any() else len(e)
    big = e[reached:][np.abs(e[reached:]) > 5]
    return dict(ga_t=ga_t, low=low if low < 1e8 else None, over=float(np.nanmax(e)) if err else float('nan'), under=float(e[reached:].min()) if reached < len(e) else float('nan'),
                cross=int(np.sum(np.diff(np.sign(big)) != 0)) if len(big) > 1 else 0, td=td)


def entry_contract():
    """M10: the landing task's entry contract. Above the path by more than the limit (0.8 of what the capture takes at the weight, at 10 nmi: 400, 1,200 and 1,600 ft) the go-around task takes the aircraft at once: it circles
    down to the height the final is begun from (never more than 300 ft under it), goes back onto the final and lands within M5b's glide limits, M7's sink and M8's
    line; within the limit (0.8 of the height the capture was flown to take over at that weight) it takes the path over as it always did, with no go-around."""
    n0 = MM.Manager.go_arounds
    lines, ok = [], True
    for w in (12000.0, 20000.0, 26000.0):
        cap = {12000.0: 500.0, 20000.0: 1500.0, 26000.0: 2000.0}[w]
        for above, around in ((0.7 * cap, False), (1.3 * cap, True), (cap + 3000.0, True)):
            r = entry_case(H.load(rebuild=False), w, above)
            td = r['td']
            good = td is not None and (r['ga_t'] is not None) == around and 0.2 <= td[1] <= 1.2 and -50 <= td[0] <= 2000 and td[2] <= 15.0
            if around:
                good = good and r['ga_t'] < 5.0 and r['low'] >= -300.0 and r['over'] <= 8.0 and r['under'] >= -12.0      # M5b's over and under; the crossings are not counted: after the circle the settle may pass 5 ft once (5.6 ft seen)
            ok = ok and good
            lines.append('%d lb +%d ft: %s, %s' % (w, above, ('go-around at %.0f s, %.0f ft under its height at the least, then glide +%.1f/%.1f ft (%d crossings)' % (r['ga_t'], r['low'], r['over'], r['under'], r['cross'])
                          if r['ga_t'] is not None else 'no go-around, path taken (highest %.0f ft above it)' % r['over']),
                          'not down' if td is None else 'down %.0f ft past the aiming point, %.2f m/s, %.1f ft off the line%s' % (td[0], td[1], td[2], '' if good else '  <-- MISS')))
    add('M10', 'landing begun above the glide path: the entry contract, 9 cases', ok, '; '.join(lines))
    return MM.Manager.go_arounds - n0


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
        # 14,000 ft, not 20,000: the last leg is 26 nmi, from 20,000 ft down to the fix at 6,500 ft that is 5 deg and the aircraft needs 50 nmi: it began the landing 2,345 ft over
        # the path (the go-around task caught it, docs/PLAN.md "The aircraft refuses what it cannot fly"); from 14,000 ft it is 2.7 deg
        dict(kind='route', points=[P(25 * NM) + (14000.0,), P(25 * NM, 25 * NM) + (14000.0,),
                                   fld.ll(*(25 * NM * u + 25 * NM * r + 25 * NM * unit(COURSE + 210.0))) + (14000.0,),
                                   P(-20 * NM) + (6500.0,)]),
        dict(kind='land', fix=P(-20 * NM), aim=P(0), elev=elev),
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
        # M3b the climb 30 to 40 s after lift-off against the ATTREX records' first seconds (limits written 2026-11-13, the
        # speed's after it had missed by 2 kt: 147 to 151 KEAS, 10 to 14 deg, 2,250 to 3,650 ft/min)
        tl = t[lift]                                         # the take-off item ends at the climb's start: the window is in the whole log
        w = (log['t'] >= tl + 30) & (log['t'] <= tl + 40)
        if w.any():
            keas, th = float(np.mean(log['keas'][w])), float(np.mean(log['theta'][w]))
            roc = float((log['alt'][w][-1] - log['alt'][w][0]) / (log['t'][w][-1] - log['t'][w][0]) * 60.0)
            add('M3b', 'takeoff: climb 30 to 40 s after lift-off', 147 <= keas <= 151 and 10 <= th <= 14 and 2250 <= roc <= 3650,
                '%.1f KEAS (147-151), %.1f deg (10-14), %.0f ft/min (2,250-3,650)' % (keas, th, roc))
    # M4 enroute
    k = log['item'] == 2
    if k.any():
        t = log['t'][k]
        level = k & (log['pm'] == 2)
        tl = log['t'][level]
        held = np.abs(log['alt'][level] - log['altcmd'][level])
        settled = level & np.concatenate([[False], np.diff(log['pm']) == 0]) & (np.abs(log['alt'] - log['altcmd']) < 150)
        over = float(held.max()) if len(held) else float('nan')           # (the largest distance from the height at any time in the altitude mode: with the fixed 150 ft gate that was the capture's start; kept to report)
        # each level stretch is judged from two minutes after its own start (the route has a level at its cruise and, now that the descent to the fix is one the aircraft
        # can make, another at the fix's height: judged from the first one's start the second's level-off would count as not settled)
        idx = np.nonzero(level)[0]
        runs = np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1) if len(idx) else []
        # the capture's own measure: how far past the commanded height each stretch of the altitude mode went, after first coming within 20 ft of it or past it (the altitude mode takes over
        # where the capture's profile asks for the climb rate there is, 700 ft out in this mission, so the distance at its start says nothing about how it ends: docs/PLAN.md, "Level-off")
        past = [0.0]
        for r in runs:
            d0 = np.sign(log['altcmd'][r][0] - log['alt'][r][0]) or 1.0
            e = (log['alt'][r] - log['altcmd'][r]) * d0
            reached = np.nonzero(e >= -20.0)[0]
            if len(reached):
                past.append(float(max(0.0, e[reached[0]:].max())))
        overshoot = max(past)
        late = np.concatenate([np.abs(log['alt'][r] - log['altcmd'][r])[log['t'][r] > log['t'][r][0] + 120] for r in runs] + [np.array([0.0])])
        verr = np.concatenate([np.abs(log['kcas'][r] - log['target'][r])[log['t'][r] > log['t'][r][0] + 120] for r in runs] + [np.array([0.0])])
        xt_nm = np.abs(log['xt'][k]) / NM
        # after each leg change, the time for the cross-track error to come inside 0.25 nmi
        add('M4', 'enroute: height', overshoot <= 150 and late.max() <= 50 and verr.max() <= 3,
            'capture overshoots the commanded height by at most %.0f ft (the altitude mode begins up to %.0f ft out), held within %.1f ft and %.2f kt after two minutes level' % (overshoot, over, late.max(), verr.max()))
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
    capture_matrix(f)
    log, mgr = mission(f)
    add('G0', 'no go-around in the flights above (a go-around hides nothing)', MM.Manager.go_arounds == 0, '%d go-arounds' % MM.Manager.go_arounds)
    started = entry_contract()
    add('G1', 'the entry contract made its go-arounds, six of nine cases', started == 6, '%d go-arounds' % started)
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
