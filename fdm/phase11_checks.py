#!/usr/bin/env python3
"""Phase 11 checks: the model off its design conditions: days that are not standard, and wind and turbulence.

    python3 fdm/phase11_checks.py [days|wind]

O  non-standard days (the property atmosphere/delta-T, the engine tables' temperature axis -40 to +40 K). Limits: docs/PLAN.md,
   "Five more ideas", Q3, written before the first run. Physical sanity, nothing to hold them to in the sources: the laws hold
   height and speed as in phase 7a's A2 (30 ft and 2 kt in 300 s) at three conditions on days of -20, +15 and +30 K from
   standard; the time from 10,000 to 55,000 ft grows, and the maximum thrust at 20,000 ft falls, with the temperature; the
   fall is between 0.1 and 1.5 % a kelvin; the 2013 landing stays inside phase 7b's touchdown limits at -20 and +30 K.
W  wind and turbulence (added below, with its limits from the same section, Q2).
"""
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402
import mission as MI            # noqa: E402
import phase7b_checks as B      # noqa: E402

rows = []
RANKINE = 1.8
DAYS = (-20.0, 15.0, 30.0)
CONDS = (('high', dict(alt=55000, mach=0.6, weight=15000)), ('climb', dict(alt=20000, kcas=150, weight=24000)),
         ('low', dict(alt=5000, kcas=135, weight=19000)))


def add(tag, name, ok, detail, kind='pass'):
    rows.append((tag, name, 'reported' if kind == 'reported' else ('pass' if ok else 'MISS'), detail))


def day(f, dT):
    f['atmosphere/delta-T'] = dT * RANKINE


def geo(f, palt):
    """The geometric height at which the pressure altitude is palt, on the day set."""
    g = float(palt)
    for _ in range(8):
        H.state(f, dict(alt=g, mach=0.5, weight=20000), 2.0, 0.0, 1.0)
        g += palt - f['engine/pressure-altitude-ft']
    return g


def days(f):
    # O1 the laws hold height and speed on each day
    for dT in (0.0,) + DAYS:
        for name, cond in CONDS:
            day(f, dT)
            t = H.trim(f, **dict(cond))
            if not t['ok'] or not 0.02 <= t['throttle'] <= 1.0:
                add('O1', '%+.0f K, %s: hands off 300 s' % (dT, name), dT > 0 and not t['ok'] or False,
                    'no level trim here (throttle %.0f %%, residual %.2f): the thrust is not there on this day' % (100 * t['throttle'], t['residual']), 'pass' if dT <= 0 else 'reported')
                continue
            H.engage(f, t, pitch_mode=2, thrust_mode=3)
            log = H.run(f, 300, every=12)
            dh, dv = float(np.ptp(log['alt'])), float(np.ptp(log['kcas']))
            add('O1', '%+.0f K, %s: hands off 300 s' % (dT, name), dh < 30 and dv < 2 and np.all(np.isfinite(log['alt'])),
                'height within %.1f ft, speed within %.2f kt; throttle %.0f %% (limits 30 ft, 2 kt)' % (dh, dv, 100 * t['throttle']))
    day(f, 0.0)
    # O2 the climb at maximum thrust on the schedule, against pressure altitude (the schedule, the thrust and the ceiling are pressure
    # altitude's: at 55,000 ft geometric a day 20 K colder is at 59,500 ft of pressure, 4,500 ft higher, which a first version of this
    # check, flown against geometric height, took for a slow climb). The rate is the steady one at 23,000 lb, without the correction for
    # the speed gained on the schedule; the time is the integral from 10,000 to 55,000 ft on a 2,500 ft grid.
    pts = list(range(10000, 55001, 2500))
    res = {}
    for dT in (-20.0, 0.0, 15.0, 30.0):
        day(f, dT)
        rocs = []
        for pa in pts:
            t = H.trim(f, alt=geo(f, pa), weight=23000.0, throttle=1.0, **MI.schedule(pa))
            rocs.append(t['ktas'] * H.KT * math.sin(math.radians(t['cond']['gamma'])) * 60.0 if t['ok'] else 0.0)
        rocs = np.array(rocs)
        ceiling = next((pa for pa, r in zip(pts, rocs) if r < 100.0), None)
        if (rocs > 20.0).all():
            tm = float(np.trapezoid(1.0 / rocs, pts)) * 60.0
        else:
            tm = float('inf')
        res[dT] = dict(time=tm, rocs=rocs, ceiling=ceiling)
    day(f, 0.0)
    order = sorted(res)
    mono = all(res[b2]['time'] > res[a2]['time'] for a2, b2 in zip(order[:-1], order[1:]))
    add('O2', 'time from 10,000 to 55,000 ft (pressure) grows with the temperature', mono,
        '; '.join('%+.0f K: %s' % (dT, ('%.0f s' % res[dT]['time']) if np.isfinite(res[dT]['time']) else 'not reached (rate under 100 ft/min above %d ft)' % res[dT]['ceiling']) for dT in order))
    add('O2', 'climb rate at 20,000, 40,000 and 50,000 ft (pressure), ft/min', True,
        '; '.join('%+.0f K: %s' % (dT, ', '.join('%.0f' % res[dT]['rocs'][pts.index(h)] for h in (20000, 40000, 50000))) for dT in order), 'reported')
    # the whole quasi-steady flight on each day (in geometric height and the schedule of geometric height: reported, a trend only)
    flights = []
    for dT in (-20.0, 0.0, 15.0, 30.0):
        day(f, dT)
        log = MI.fly(f, ceiling=MI.CEILING)
        flights.append('%+.0f K: %.1f h, highest %.0f ft' % (dT, MI.compare(log)[1], log['alt'].max()))
    day(f, 0.0)
    add('O2', 'the quasi-steady flight on each day: endurance (geometric heights: a trend only)', True, '; '.join(flights), 'reported')
    # O3 maximum thrust at 20,000 ft against the temperature, per kelvin
    th = {}
    for dT in (-20.0, 0.0, 15.0):
        day(f, dT)
        H.state(f, dict(alt=20000, mach=0.4, weight=20000), 2.0, 0.0, 1.0)
        th[dT] = (f['engine/max-thrust-lbf'], f['engine/delta-T-K'])
    day(f, 0.0)
    per = []
    for a, b in ((-20.0, 0.0), (0.0, 15.0)):
        per.append(100 * (th[b][0] / th[a][0] - 1) / (th[b][1] - th[a][1]))
    add('O3', 'maximum thrust at 20,000 ft, Mach 0.4: change per K (-20 to 0 K, 0 to +15 K), %', all(-1.5 <= p <= -0.1 for p in per),
        '%+.2f and %+.2f %%/K (limits -1.5 to -0.1)' % tuple(per))
    # O4 the 2013 landing on a cold and a hot day
    for dT in (-20.0, 30.0):
        day(f, dT)
        n = len(B.rows)
        B.landing_case(f, '2013 at %+.0f K' % dT, 20800.0, 2357.0, dict(app=133, td=130, pitch=2.4, sink=0.66))
        for tag, name, ok, detail in B.rows[n:]:
            if tag in ('M5', 'M7'):
                add('O4', name, ok, detail)
    day(f, 0.0)


FPS = 1.6878


def wind(f, from_deg, kt):
    """A steady wind of kt knots from the compass direction from_deg (JSBSim's components blow towards north and east)."""
    r = math.radians(from_deg)
    f['atmosphere/wind-north-fps'] = -kt * FPS * math.cos(r)
    f['atmosphere/wind-east-fps'] = -kt * FPS * math.sin(r)


def turbulence(f, on=True, kt20=15.0, severity=1):
    """MIL-F-8785C turbulence as JSBSim has it: the wind at 20 ft above the ground (15 kt is light, 30 moderate) and a severity."""
    f['atmosphere/turb-type'] = 3 if on else 0
    f['atmosphere/turbulence/milspec/windspeed_at_20ft_AGL-fps'] = kt20 * FPS
    f['atmosphere/turbulence/milspec/severity'] = severity


def calm(f):
    wind(f, 0.0, 0.0)
    turbulence(f, False)


class Gale:
    """A steady wind brought up over `ramp` seconds. JSBSim's initial conditions (every H.state, H.engage, H.on_ground) set the wind
    back to nothing, and an instant 25 kt would be a step in airspeed, so the wind is put on in the run loops: hook(f, t) in H.run,
    or by wrapping an instance's run() for a flight that has its own loop (the mission)."""

    def __init__(self, from_deg, kt, ramp=30.0):
        self.from_deg, self.kt, self.ramp, self.t0 = from_deg, kt, ramp, None

    def apply(self, f, t):
        k = min(1.0, max(0.0, t / self.ramp))
        wind(f, self.from_deg, k * self.kt)

    def hook(self, f, t):
        self.apply(f, t)

    def install(self, f):
        orig = f.run

        def run():
            now = f['simulation/sim-time-sec']
            if self.t0 is None:
                self.t0 = now
            self.apply(f, now - self.t0)
            return orig()
        f.run = run
        return f


def cruise_turbulence(f, severity=5, seconds=600, alt=60000, **cond):
    """W1 the cruise in turbulence, the laws holding height and speed. Also logged, as evidence for what the airspeed does: the ground
    speed and the gust along the aircraft's heading."""
    calm(f)
    t = H.trim(f, alt=alt, **(cond or dict(mach=0.6, weight=15000)))       # trimmed in calm air: the gusts are forces the trim would fight
    H.engage(f, t, pitch_mode=2, thrust_mode=3)
    turbulence(f, True, 15.0, severity)
    keys = ('t', 'alt', 'kcas', 'phi', 'nz', 'throttle')
    cols = {k: [] for k in keys + ('vg', 'ug', 'wg')}
    props = dict(H.AP_LOG)
    for i in range(int(seconds * H.HZ)):
        if not f.run():
            break
        if i % 6 == 0:
            for k in keys:
                cols[k].append(f[props[k]])
            psi = math.radians(f['attitude/psi-deg'])
            cols['vg'].append(f['velocities/vg-fps'] / FPS)
            cols['ug'].append((f['atmosphere/turb-north-fps'] * math.cos(psi) + f['atmosphere/turb-east-fps'] * math.sin(psi)) / FPS)
            cols['wg'].append(f['atmosphere/turb-down-fps'] / FPS)
    c = {k: np.array(v) for k, v in cols.items()}
    return dict(dh=float(np.abs(c['alt'] - c['alt'][0]).max()), dv=float(np.ptp(c['kcas'])), dvg=float(np.ptp(c['vg'])), dug=float(np.ptp(c['ug'])),
                dwg=float(np.std(c['wg']) * 1.0), bank=float(np.abs(c['phi']).max()), nz=(float(c['nz'].min()), float(c['nz'].max())), over=f['limits/overstress'],
                finite=bool(np.all(np.isfinite(c['alt']))), thr=(float(c['throttle'].min()), float(c['throttle'].max())), sigma_w=float(np.std(c['wg']) * 0.3048 * FPS))


def crosswind_landing(f, kt, name, weight=20800.0, elev=2357.0, turb=True, severity=3):
    """W3 the 2013 landing in a crosswind from the right (brought up over 30 s as the approach begins), light turbulence: returns the
    log judged on the lateral figures."""
    calm(f)
    gale = Gale(B.COURSE + 90.0, kt)
    fld = B.MM.Field(35.0, -117.0, elev)
    u = B.unit(B.COURSE)
    aim, far = fld.ll(0, 0), fld.ll(*(-8 * B.NM * u))
    d0 = 5 * B.NM
    start = fld.ll(*(-d0 * u))
    keas = math.sqrt(weight / (0.645 * 540 * 0.5 * 0.0023769)) / H.KT
    t = H.trim(f, alt=elev + 5.3 + d0 * 0.07782, kcas=keas, weight=weight, gamma=-4.45, gear=1.0, spoiler=2 / 3, lat=start[0], lon=start[1], psi=B.COURSE, terrain=elev)
    H.engage(f, t, pitch_mode=1, roll_mode=3, ground_steer=1, land_mode=1, rwy_elev_ft=elev, leg_lat0_deg=far[0], leg_lon0_deg=far[1],
             leg_lat1_deg=aim[0], leg_lon1_deg=aim[1])
    turbulence(f, turb, 15.0, severity)
    log = H.run(f, 260, every=6, hook=gale.hook)
    calm(f)
    if not (log['mains'] > 0).any():
        return dict(down=False)
    i = int(np.argmax(log['mains'] > 0))
    sink = -log['hdot'][i - 1] * 0.3048
    after = slice(i, None)
    return dict(down=True, xt=float(log['xt'][i]), xt_max=float(np.abs(log['xt'][after]).max()), sink=float(sink), bank=float(np.abs(log['phi'][after]).max()),
                end=float(log['vg'][-1]), pitch=float(log['theta'][i]), keas=float(log['keas'][i]), beta=float(np.abs(log['beta'][max(0, i - 40):i]).max()),
                past=float(-log['togo'][i]), finite=bool(np.all(np.isfinite(log['alt']))))


def gate_weather():
    """W4: the stabilised-approach gate (docs/PLAN.md, "The approach that cannot hold its line") in the weather the landings are claimed for: the manager flies the landing from 5 nmi out
    (as M11) and no missed approach is begun and the aircraft lands, at three weights in calm air and at 20,800 lb in a 20 kt crosswind and light turbulence (six turbulence sequences); and
    in severe turbulence (sigma_w 4 m/s, beyond the claim: reported) every missed approach the gate begins ends with the wheels not touching in the minute after it."""
    n0 = B.MM.Manager.go_arounds
    rows, bad = [], []
    for w, kt, sev, seed in [(12450.0, 0, 0, None), (20800.0, 0, 0, None), (26749.0, 0, 0, None)] + [(20800.0, 20, 3, s) for s in range(1, 7)]:
        def weather(f, kt=kt, sev=sev):
            turbulence(f, sev > 0, 15.0, max(sev, 1))
            if kt:
                Gale(B.COURSE + 90.0, float(kt)).install(f)
        r = B.gate_case(w, 0.0, False, seconds=400.0, setup=weather, seed=seed)
        rows.append('%d lb%s: %s' % (w, (', %d kt, sequence %d' % (kt, seed)) if kt else ', calm', 'no missed approach, down %.0f ft past the aiming point, %.2f m/s' % (r['td']['past'], r['td']['sink']) if r['td'] and not r['misses'] else 'MISSED APPROACH or not down: %s' % [m['why'].split(';')[0] for m in r['misses']]))
        if r['misses'] or r['td'] is None:
            bad.append(rows[-1])
    add('W4', 'the gate lets the landings in calm air and in light turbulence with a 20 kt crosswind through (9 landings)', not bad, '; '.join(rows[:3]) + '; ... six of 20,800 lb at 20 kt in light turbulence: ' + ('all landed with no missed approach' if not bad else '%d of 9 did not: %s' % (len(bad), ' / '.join(bad))))
    out, started, down = [], 0, 0
    for w in (12450.0, 20800.0):
        for s in range(1, 7):
            def weather(f):
                turbulence(f, True, 15.0, 5)
                Gale(B.COURSE + 90.0, 10.0).install(f)
            r = B.gate_case(w, 0.0, False, seconds=220.0, setup=weather, seed=s)
            if r['misses']:
                started += 1
                down += 1 if r['misses'][0]['down'] else 0
                out.append('%d lb sequence %d: %s, lowest %.0f ft over the runway after it%s' % (w, s, r['misses'][0]['why'].split(';')[0].replace('MISSED APPROACH: ', ''), r['misses'][0]['low'], ', WHEELS DOWN' if r['misses'][0]['down'] else ''))
    add('W4', 'severe turbulence (sigma_w 4 m/s, beyond the claim): the missed approaches the gate begins do not end on the ground', down == 0,
        '%d of 12 landings made one, %d touched the ground in the minute after it; %s' % (started, down, '; '.join(out)), 'reported')
    return B.MM.Manager.go_arounds - n0


def wind_checks(f):
    # W1
    for sev, alt, cond, name in ((5, 60000, {}, 'at 60,000 ft, severity 5'), (3, 20000, dict(kcas=150, weight=24000), 'at 20,000 ft, severity 3')):
        r = cruise_turbulence(f, sev, alt=alt, **cond)
        base = 'cruise in turbulence %s (sigma_w %.2f m/s): ' % (name, r['sigma_w'])
        add('W1', base + 'height within 150 ft, bank within 8 deg, no alert', r['finite'] and r['dh'] <= 150 and r['bank'] <= 8 and r['over'] == 0,
            'height within %.0f ft, bank within %.1f deg, limit flag %g' % (r['dh'], r['bank'], r['over']))
        add('W1', base + 'airspeed within 5 kt', r['dv'] <= 5.0,
            'airspeed over %.1f kt, ground speed over %.1f kt, the gust along the heading over %.1f kt; throttle %.2f to %.2f' % (r['dv'], r['dvg'], r['dug'], *r['thr']))
        add('W1', base + 'load factor 0.7 to 1.3', 0.7 <= r['nz'][0] and r['nz'][1] <= 1.3, 'load factor %.2f to %.2f' % r['nz'])
    # W2 the whole mission in a 25 kt headwind at the runway (the same wind, uniform in height, across the legs) and light turbulence.
    # A fresh model for each case: the flight before leaves the manager's and the landing's latches set (a first version flew the
    # crosswind landings after the mission and they never touched down)
    f = H.load()
    calm(f)
    turbulence(f, True, 15.0, 3)
    Gale(B.COURSE, 25.0).install(f)
    n = len(B.rows)
    log, mgr = B.mission(f)
    calm(f)
    for tag, name, ok, detail in B.rows[n:]:
        if tag == 'M1':                                                 # the limits written: it completes ...
            add('W2', 'mission, 25 kt wind from the runway heading, light turbulence: ' + name, ok, detail)
        elif tag == 'M4' and 'track' in name:                           # ... and the legs are held: 0.25 nmi for 95 % of the route (7b's own rule is 80 %)
            share = float(re.search(r'for (\d+) %', detail).group(1))
            add('W2', 'mission, 25 kt wind, light turbulence: enroute: track within 0.25 nmi for 95 % of the route', share >= 95.0,
                '%s (phase 7b\'s own rule, 80 %%: %s)' % (detail, 'pass' if ok else 'MISS'))
        else:                                                           # the rest as phase 7b's own checks judge them, reported
            add('W2', 'mission, 25 kt wind, light turbulence: ' + name, ok, '%s (as phase 7b would judge it: %s)' % (detail, 'pass' if ok else 'MISS'), 'reported')
    # W3 crosswind landings
    for kt, turb, sev, kind in ((10.0, True, 3, 'pass'), (20.0, True, 3, 'reported'), (10.0, False, 3, 'reported'), (0.0, True, 3, 'reported'), (10.0, True, 5, 'reported'), (0.0, True, 5, 'reported')):
        r = crosswind_landing(H.load(), kt, '%d kt' % kt, turb=turb, severity=sev)
        name = '2013 landing, %d kt crosswind from the right, %s' % (kt, ('light turbulence' if sev == 3 else 'severe turbulence (severity 5, sigma_w 4 m/s at the field)') if turb else 'no turbulence')
        if not r['down']:
            add('W3', name, False, 'never touched down', kind)
            continue
        ok = r['finite'] and abs(r['xt']) <= 30 and r['sink'] < 1.5 and r['bank'] < 5 and r['end'] <= 16
        add('W3', name, ok, 'down %.0f ft from the centreline (%.0f ft at most on the rollout), sink %.2f m/s, pitch %.1f deg, %.0f KEAS, sideslip up to %.1f deg before it, bank on the ground up to %.1f deg, down to %.0f kt; %.0f ft past the aiming point' % (
            r['xt'], r['xt_max'], r['sink'], r['pitch'], r['keas'], r['beta'], r['bank'], r['end'], r['past']), kind)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    f = H.load()
    if which in ('all', 'days'):
        days(f)
    if which in ('all', 'wind'):
        wind_checks(f)
    if which in ('all', 'wind'):
        add('G0', 'no go-around in the wind flights (a go-around hides nothing)', B.MM.Manager.go_arounds == 0, '%d go-arounds' % B.MM.Manager.go_arounds)
        gate_weather()
    for tag, name, status, detail in rows:
        print('%-3s %-62s %s  %s' % (tag, name, status, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    n = sum(1 for r in rows if r[2] != 'reported')
    print('\n%d checks, %d pass, %d miss' % (n, n - miss, miss))


if __name__ == '__main__':
    main()
