"""A flight to 65,000 ft the way the aircraft really gets there: the whole fuel load, a cruise-climb of 20 to 30 hours, then down and a landing.

    python3 scenario65.py plan [LAT LON HEADING ELEV_FT] > plan.json     the plan, for the station or for fg_scenario.py (default: EFHK 22L)
    python3 scenario65.py headless                                      flies it through the laws and the mission manager, about 27 h of flight, and judges it

The aircraft takes off at 25,600 lb with 14,500 lb of fuel (NASA 2008: the weights fdm/mission.py assumes) and climbs at maximum thrust on the speed schedule (150 KCAS
to FL220, then a Mach number rising to 0.6 at FL550, Mach 0.6 above). Above about 55,000 ft its thrust only just matches the drag, and it rises as fuel burns away
(docs/PLAN.md "Performance": Pastor 2018 table 4): 57,500 ft after 4 h, 59,400 ft after 7 h, 62,000 ft after 12.5 h, 63,750 ft after 21 h, 65,000 ft after about 22 h in
the model (fdm/mission.py, which does the same sum in quasi-steady steps; this flies it). A climb to 65,000 ft in an hour is a light aircraft (the model's rate there is
309 ft/min at 11,500 lb, 62 at 15,000 and negative above): not this flight.

The route is a racetrack with its long sides along a meridian (a straight line in latitude and longitude is a straight line on the ground along a meridian, not along
a slanted course 400 nmi long), flown LOOPS times with the height command at 65,000 ft the whole time, then a long descent in steps to the final.
"""
import json
import math
import os
import sys

FT_PER_DEG = 364567.2
NM = 6076.1
TAKEOFF_LB, FUEL_LB = 25600.0, 14500.0
CEILING_FT = 65000.0
LOOPS = 10                         # about 2.5 h each at Mach 0.6: the ceiling is reached in the 9th (21.8 h), the rest is held
SIDE_NM, WIDTH_NM = 400.0, 60.0    # the long side along a meridian, the short side across
START_NM = 40.0                    # the racetrack's first corner: straight on from the runway
STEP_FT = 58000.0                  # the descent's first stretch is shallow (thin air: the angle-of-attack limit is 3.5 deg there and a pushover from level took the margin to nothing)
HERE = (60.330586, 24.978882)      # EFHK 22L threshold (default)
HEADING, ELEV = 227.5, 171.0


def along(p, brg, dist_ft):
    """The point a distance from p on a bearing (flat earth about p: js/geo.js along)."""
    c = math.radians(brg)
    return [p[0] + dist_ft * math.cos(c) / FT_PER_DEG, p[1] + dist_ft * math.sin(c) / (FT_PER_DEG * math.cos(math.radians(p[0])))]


def plan65(here=HERE, hdg=HEADING, elev=ELEV, ceiling=CEILING_FT, loops=LOOPS, fix_ft=None):
    r = lambda v: round(v, 6)
    pt = lambda p, alt=None: [r(p[0]), r(p[1])] + ([alt] if alt is not None else [])
    fix_ft = fix_ft or round((elev + 1730.0) / 100.0) * 100.0          # EFHK: 1,900 ft (js/geo.js localPlan: the same 10 nmi final)
    a0 = along(here, hdg, START_NM * NM)
    a1 = along(a0, 180, SIDE_NM * NM)
    a2 = along(a1, 90, WIDTH_NM * NM)
    a3 = along(a2, 0, SIDE_NM * NM)
    loop = [a1, a2, a3, a0]                                           # a loop, anticlockwise, from a0 back to a0
    d1 = along(a0, 90, 150 * NM)                                      # the descent: east, then back north-east of the field in steps
    d2 = along(here, 0, 100 * NM)
    onto = along(here, hdg + 180, 35 * NM)                            # on the final's line, 35 nmi out
    fix = along(here, hdg + 180, 10 * NM)
    aim = along(here, hdg, 800)
    points = [pt(a0, ceiling)] + [pt(p, ceiling) for _ in range(loops) for p in loop] + [pt(d1, STEP_FT), pt(d2, 25000.0), pt(onto, 5500.0), pt(fix, fix_ft)]
    land = {'kind': 'land', 'fix': pt(fix), 'aim': pt(aim)}
    return {
        'id': 'ceiling-65000',
        'note': 'The whole fuel load, %d racetracks of %d nmi at the height command of %s ft (the aircraft cruise-climbs to it over about 22 h), a long descent, the same runway.' % (
            loops, 2 * (SIDE_NM + WIDTH_NM), format(int(ceiling), ',')),
        'field': {'name': 'here', 'lat': r(here[0]), 'lon': r(here[1]), 'elev_ft': round(elev)},
        'items': [
            {'kind': 'takeoff', 'start': pt(here), 'end': pt(along(here, hdg, 9000))},
            {'kind': 'route', 'points': points},
            land,
        ],
        'lost_link': [{'kind': 'route', 'points': [pt(fix, fix_ft)]}, land],
        'sites': [{'name': 'home', 'aim': pt(aim), 'course': round(hdg % 360, 1), 'elev_ft': round(elev)}],
    }


def headless(weight=TAKEOFF_LB):
    """Flown as the station would: the plan and the start sent over the link, then hours of heartbeats. Prints the flight each hour and judges it."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import tempfile
    import numpy as np
    import harness as H
    import gcs_server as G
    import mission as MI
    plan = plan65()
    plan['field'].update(stand=plan['items'][0]['start'], stand_heading=HEADING)
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
        json.dump(plan, fh)
    sim = G.Sim(fh.name, weight=weight)
    f, ob = sim.f, sim.ob
    for n, (name, args) in enumerate((('plan', plan), ('start', {}))):
        sim.set('/gcs/up/cmd', json.dumps(dict(seq=n + 1, station='C', name=name, args=args)))
    for _ in range(int(2 * H.HZ)):
        sim.step()
    print('plan:', ob.down.get('/gcs/down/ack'), '|', str(ob.down.get('/gcs/down/status'))[:160], flush=True)
    names = ['simulation/sim-time-sec', 'position/h-sl-ft', 'velocities/vc-kts', 'velocities/mach', 'velocities/h-dot-fps', 'aero/alpha-deg', 'ap/alpha-limit-deg', 'ap/pitch-mode',
             'ap/thrust-mode', 'ctl/throttle-norm', 'fuel/total-lbs', 'attitude/phi-deg', 'accelerations/Nz', 'ap/leg-xt-ft', 'ap/on-mains', 'inertia/weight-lbs']
    rows, t0, done = [], f['simulation/sim-time-sec'], None
    for i in range(int(45 * 3600 * H.HZ)):
        if i % H.HZ == 0:
            sim.set('/gcs/up/heartbeat', i)
        sim.step()
        if not sim.ok:
            print('the model stopped')
            break
        if i % int(H.HZ) == 0:
            rows.append([f[n] for n in names])
            if len(rows) % 3600 == 1:
                print('%5.1f h  %6.0f ft  M %.3f  %6.0f lb  fuel %6.0f lb  mode %d/%d' % ((rows[-1][0] - t0) / 3600, rows[-1][1], rows[-1][3], rows[-1][15], rows[-1][10], rows[-1][7], rows[-1][8]), flush=True)
        if any('rollout over' in e[1] for e in ob.mgr.events) and done is None:
            done = i
        if done is not None and i > done + 5 * H.HZ:
            break
    a = np.array(rows)
    if os.environ.get('OUT'):
        np.savez(os.environ['OUT'], a=a, names=np.array(names))
    col = lambda n: a[:, names.index(n)]
    t = col('simulation/sim-time-sec') - t0
    alt, M = col('position/h-sl-ft'), col('velocities/mach')
    margin = col('ap/alpha-limit-deg') - col('aero/alpha-deg')
    air = col('ap/on-mains') == 0
    hi = air & (alt > 2500.0)
    nz = np.abs(col('accelerations/Nz') - 1)
    xt_nm = np.abs(col('ap/leg-xt-ft')) / NM
    bank = np.abs(col('attitude/phi-deg'))
    near_turn = np.convolve((bank > 3.0).astype(float), np.ones(900), mode='same') > 0        # 7.5 min either side of a turn: the leg's capture after the corner
    straight = air & (alt > 30000) & ~near_turn
    # Pastor's table 4 (the mean of his two flights), against the flight, at the minutes the model's own check uses
    checks = []
    for mins, hts in MI.PASTOR_CRUISE:
        tm, ht = float(np.mean(mins)), float(np.mean(hts))
        if 200.0 <= tm and tm * 60 < t[-1] - 3600:                 # the minutes of fdm/mission.py's P2 (from 4 h): the early climb is its P1 and not part of this
            k = int(np.argmin(np.abs(t - tm * 60)))
            checks.append(('height %4.0f min after takeoff against Pastor (within 1,000 ft)' % tm, abs(alt[k] - ht) <= 1000.0, '%.0f ft against %.0f ft (%+.0f)' % (alt[k], ht, alt[k] - ht)))
    top = np.nonzero(alt >= CEILING_FT - 150)[0]
    t_top = t[top[0]] / 3600 if len(top) else None
    held = alt[alt > CEILING_FT - 150]
    checks += [
        ('reaches the ceiling between 19 and 26 h (the model: 21.8 h)', t_top is not None and 19 <= t_top <= 26, '%s h after the start' % ('%.1f' % t_top if t_top is not None else 'never')),
        ('does not go above the ceiling', alt.max() <= CEILING_FT + 100, 'highest %.0f ft' % alt.max()),
        ('holds the ceiling once there (within 250 ft)', len(held) > 600 and np.ptp(held[len(held) // 20:]) <= 250, 'spread %.0f ft over %.1f h' % (np.ptp(held[len(held) // 20:]) if len(held) else 0, len(held) / 3600)),
        ('above 2,500 ft: under the angle-of-attack limit', margin[hi].min() >= 0.0, 'least margin %.2f deg, at %.1f h and %.0f ft' % (margin[hi].min(), t[hi][np.argmin(margin[hi])] / 3600, alt[hi][np.argmin(margin[hi])])),
        ('above 2,500 ft: Mach at most 0.65', M[hi].max() <= 0.65, 'highest %.3f' % M[hi].max()),
        ('above 2,500 ft: load factor within 0.35 g of 1', nz[hi].max() <= 0.35, 'largest %.2f g from 1' % nz[hi].max()),
        ('above 30,000 ft, wings nearly level: within 0.25 nmi of the track', np.mean(xt_nm[straight] <= 0.25) >= 0.98, '%.1f %% of the time, largest %.2f nmi (the corners excluded: a turn is off the line by its radius)' % (100 * np.mean(xt_nm[straight] <= 0.25), xt_nm[straight].max())),
        ('lands and stops on the runway', done is not None, 'rollout over at %s h' % ('%.1f' % (t[-1] / 3600) if done is not None else 'never')),
        ('fuel at the end at least the 765 lb reserve', col('fuel/total-lbs')[-1] >= 765.0, '%.0f lb left; the flight %.1f h' % (col('fuel/total-lbs')[-1], t[-1] / 3600)),
    ]
    on = col('ap/on-mains') > 0
    if on[1000:].any():                                              # the landing's touchdown: the last time the wheels came down
        td = int(np.nonzero(on[1:] & ~on[:-1])[0][-1]) + 1
        xt = col('ap/leg-xt-ft')[td:]
        checks.append(('the rollout stays within 15 ft of the line', np.abs(xt).max() <= 15.0, 'touchdown %.1f ft, rollout at most %.1f ft, sink %.2f m/s' % (col('ap/leg-xt-ft')[td], np.abs(xt).max(), -col('velocities/h-dot-fps')[td - 1] * 0.3048)))
    fixh = plan65()['items'][1]['points'][-1][2]
    land = air & (t > t[np.nonzero(alt < fixh + 200)[0][0]]) if (alt < fixh + 200).any() else air & False
    known = [
        ('the glide-path capture stays within 100 ft under the fix height', alt[land].min() >= fixh - 100, 'lowest %.0f ft against the fix at %.0f ft' % (alt[land].min(), fixh)),
        ('the glide-path capture stays under the angle-of-attack limit', margin[land].min() >= 0.0, 'least margin %.2f deg' % margin[land].min()),
    ] if land.any() else []
    print('the manager: ' + '; '.join('%.1f h %s' % ((e[0] - t0) / 3600, e[1]) for e in ob.mgr.events if not e[1].startswith('leg ')))
    ok = True
    for name, good, detail in checks:
        print('%-70s %s  %s' % (name, 'pass' if good else 'FAIL', detail))
        ok = ok and good
    for name, good, detail in known:
        print('%-70s %s  %s' % (name + ' (known, not counted)', 'pass' if good else 'FAIL', detail))
    print('the scenario flies to %.0f ft correctly' % CEILING_FT if ok else 'the scenario does not fly correctly yet')
    return ok


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'plan'
    if cmd == 'plan':
        a = [float(x) for x in sys.argv[2:6]]
        print(json.dumps(plan65(*(((a[0], a[1]), a[2], a[3]) if len(a) == 4 else ())), indent=1))
    elif cmd == 'headless':
        sys.exit(0 if headless() else 1)
    else:
        print(__doc__)
