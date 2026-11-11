#!/usr/bin/env python3
"""Phase 7 part C, second half: manual mode. The protected and direct laws and the structural limit flags.

    python3 fdm/phase7d_checks.py        under a minute

Limits: docs/FLIGHT-LAWS.md section 8 (H, D, S), written before the laws were run. All PREDICTED: the real aircraft
has no stick. The "pilot" here is a few lines of proportional control, with its stick delayed as a link would.
"""
import collections
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H                 # noqa: E402
import missionmgr as MM             # noqa: E402

NM = 6076.1
CONDS = (('cruise', dict(alt=60000, mach=0.6, weight=15000)), ('climb', dict(alt=20000, kcas=150, weight=24000)),
         ('low', dict(alt=5000, kcas=135, weight=19000)))
STICKS = ('fcs/elevator-cmd-norm', 'fcs/aileron-cmd-norm', 'fcs/rudder-cmd-norm')
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))


def report(tag, name, detail):
    rows.append((tag, name, 'reported', detail))


def start(f, cond, manual=1):
    """Trimmed, the laws holding height and speed; then handed to the pilot with the throttle lever where it was."""
    t = H.trim(f, **cond)
    H.engage(f, t, pitch_mode=2, thrust_mode=3)
    f['fcs/throttle-cmd-norm'] = f['ctl/throttle-norm']
    f['ap/manual'] = manual
    return t


def hold(stick, value, until):
    return lambda f, t: f.__setitem__(stick, value if t < until else 0.0)


def past_dead(x, dead=0.05):
    """What a hand does about a dead band: moves the stick through it."""
    return 0.0 if x == 0 else math.copysign(dead + (1 - dead) * abs(x), x)


def protected(f):
    over_any = 0
    for name, cond in CONDS:
        # H1
        t = H.trim(f, **cond)
        H.engage(f, t, pitch_mode=2, thrust_mode=3)
        H.run(f, 20)
        f['fcs/throttle-cmd-norm'] = f['ctl/throttle-norm']
        f['ap/manual'] = 1
        log = H.run(f, 5, every=1)
        mv = max(np.ptp(log[k]) for k in ('pitch', 'roll', 'yaw'))
        add('H1', '%s: automatic to protected' % name, mv < 0.1 and np.ptp(log['alt']) < 5, 'surfaces move %.3f deg, height %.2f ft in 5 s' % (mv, np.ptp(log['alt'])))
        # H2
        log = H.run(f, 300)
        add('H2', '%s: hands off 300 s' % name, np.ptp(log['theta']) <= 1.0 and np.abs(log['theta'] - log['theta'][0]).max() <= 0.5 and np.abs(log['phi']).max() <= 1,
            'pitch attitude within %.2f deg, bank within %.2f deg; speed drifts %+.1f kt, height %+.0f ft' % (
                np.abs(log['theta'] - log['theta'][0]).max(), np.abs(log['phi']).max(), log['kcas'][-1] - log['kcas'][0], log['alt'][-1] - log['alt'][0]))
        # H3 back
        start(f, cond)
        over = []

        def back(f, t):
            f[STICKS[0]] = -1.0 if t < 30 else 0.0
            over.append(f['aero/alpha-deg'] - f['ap/alpha-limit-deg'])
        log = H.run(f, 60, hook=back)
        over_any += f['limits/overstress']
        add('H3', '%s: full back stick 30 s' % name, max(over) <= 0.5 and log['nz'].max() < 2.0 and f['limits/overstress'] == 0,
            'angle of attack %.2f deg over its limit at most; load factor %.2f to %.2f; nose up to %.1f deg, speed down to %.0f KCAS' % (
                max(over), log['nz'].min(), log['nz'].max(), log['theta'].max(), log['kcas'].min()))
        start(f, cond)
        log = H.run(f, 60, hook=hold(STICKS[0], 1.0, 30))
        over_any += f['limits/overstress']
        add('H3', '%s: full forward stick 30 s' % name, log['mach'].max() < 0.65 and log['kcas'].max() < 185 and log['nz'].min() > 0 and f['limits/overstress'] == 0,
            'Mach %.3f, %.0f KCAS at most; load factor %.2f to %.2f; nose down to %.1f deg' % (
                log['mach'].max(), log['kcas'].max(), log['nz'].min(), log['nz'].max(), log['theta'].min()))
        # H4
        start(f, cond)
        lim = f['ap/bank-limit-deg']
        log = H.run(f, 45, hook=hold(STICKS[1], 1.0, 30))
        over_any += f['limits/overstress']
        k = log['t'] >= 44
        add('H4', '%s: full side stick 30 s, then released' % name, log['phi'].max() <= lim + 1 and np.abs(log['phi'][k]).max() <= 1,
            'bank up to %.1f deg (limit %.0f); %.2f deg 15 s after release; sideslip up to %.2f deg' % (log['phi'].max(), lim, np.abs(log['phi'][k]).max(), np.abs(log['beta']).max()))
        # H7
        start(f, cond)
        H.run(f, 20)
        f['ap/manual'] = 2
        a = H.run(f, 3, every=1)
        f['ap/manual'] = 1
        b = H.run(f, 3, every=1)
        ma, mb = (max(np.ptp(l[k]) for k in ('pitch', 'roll', 'yaw')) for l in (a, b))
        add('H7', '%s: protected to direct and back' % name, ma < 0.1 and mb < 0.1, 'surfaces move %.3f deg going to direct, %.3f deg coming back' % (ma, mb))
    return over_any


def pilot_task(f, delay):
    """Climb 500 ft and turn 30 deg right by a proportional pilot whose stick arrives late."""
    start(f, CONDS[2][1])
    h0, psi0, v0, th0, thr0 = f['position/h-sl-ft'] + 500.0, f['attitude/psi-deg'] + 30.0, f['velocities/vc-kts'], f['attitude/theta-deg'], f['fcs/throttle-cmd-norm']
    line = collections.deque([(0.0, 0.0, thr0)] * max(1, int(round(delay * H.HZ))))

    def fly(f, t):
        theta_des = th0 + float(np.clip(0.02 * (h0 - f['position/h-sl-ft']) - 0.15 * f['velocities/h-dot-fps'], -4, 6))
        pitch = -float(np.clip(0.4 * (theta_des - f['attitude/theta-deg']), -1, 1))
        herr = (psi0 - f['attitude/psi-deg'] + 180.0) % 360.0 - 180.0
        roll = float(np.clip((1.0 * herr - f['attitude/phi-deg']) / 20.0 + f['attitude/phi-deg'] / f['ap/bank-command-limit-deg'], -1, 1))
        thr = float(np.clip(thr0 + 0.03 * (v0 - f['velocities/vc-kts']) + 0.004 * (h0 - f['position/h-sl-ft']), 0, 1))
        line.append((pitch, roll, thr))
        p, r, th = line.popleft()
        f[STICKS[0]], f[STICKS[1]], f['fcs/throttle-cmd-norm'] = p, r, th
    log = H.run(f, 120, hook=fly)
    herr = (psi0 - log['psi'][-1] + 180.0) % 360.0 - 180.0
    k = log['t'] > 90
    return log, abs(log['alt'][-1] - h0), abs(herr), np.ptp(log['alt'][k]), np.ptp(log['phi'][k]), f['limits/overstress']


def takeoff(f):
    elev, course = 2300.0, 40.0
    H.on_ground(f, 25600.0, elevation=elev, heading=course, lat=34.9, lon=-117.88)
    for _ in range(int(20 * H.HZ)):                                 # the gear was up for the flights before: let it come down
        f.run()
    H.on_ground(f, 25600.0, elevation=elev, heading=course, lat=34.9, lon=-117.88)
    H.brakes(f, 0)
    f['ap/theta-cmd-deg'] = f['attitude/theta-deg']
    f['ap/engaged'] = 1
    f['ap/manual'] = 1
    f['limits/reset'] = 1                 # being stood on its wheels by the harness is not a flight load
    f.run()
    f['limits/reset'] = 0
    f['fcs/throttle-cmd-norm'] = 1.0
    st = dict(rotated=False, lift=None)

    def fly(f, t):
        herr = (course - f['attitude/psi-deg'] + 180.0) % 360.0 - 180.0
        ped = float(np.clip(0.3 * herr - 2.0 * f['velocities/r-rad_sec'], -1, 1))
        f[STICKS[2]] = ped
        f['fcs/steer-cmd-norm'] = ped * min(1.0, 30.0 / max(f['velocities/vg-fps'], 1.0))
        v, th = f['velocities/vc-kts'], f['attitude/theta-deg']
        if v >= 130.0:
            st['rotated'] = True
        if f['aero/wheel-height-ft'] > 2 and st['lift'] is None:
            st['lift'] = (t, f['velocities/ve-kts'], th)
        if f['aero/wheel-height-ft'] > 100:
            f['gear/gear-cmd-norm'] = 0
        want = 0.0 if not st['rotated'] else float(np.clip(7.0 + 0.3 * (v - 150.0), 3, 12))
        f[STICKS[0]] = -float(np.clip(0.4 * (want - th), -1, 1)) if st['rotated'] else 0.0
        f[STICKS[1]] = float(np.clip(-f['attitude/phi-deg'] / 20.0, -1, 1))
    log = H.run(f, 150, hook=fly)
    lift = st['lift']
    add('H6', 'takeoff by hand through the protected law', lift is not None and log['alt'][-1] > elev + 2000 and f['limits/overstress'] == 0 and np.abs(log['phi']).max() < 5,
        '%s; %.0f ft above the field and %.0f KCAS after 150 s; bank within %.1f deg' % (
            'never left the ground' if lift is None else 'lifts off after %.1f s at %.0f KEAS and %.1f deg' % lift, log['alt'][-1] - elev, log['kcas'][-1], np.abs(log['phi']).max()))


def landing(f):
    elev, course, weight = 2300.0, 40.0, 20800.0
    fld = MM.Field(35.0, -117.0, elev)
    u = np.array([math.cos(math.radians(course)), math.sin(math.radians(course))])
    aim, far, begin = fld.ll(0, 0), fld.ll(*(-8 * NM * u)), fld.ll(*(-5 * NM * u))
    keas = math.sqrt(weight / (0.645 * 540 * 0.5 * 0.0023769)) / H.KT
    t = H.trim(f, alt=elev + 5.3 + 5 * NM * 0.07782, kcas=keas, weight=weight, gamma=-4.45, gear=1.0, spoiler=2 / 3, lat=begin[0], lon=begin[1],
               psi=course, terrain=elev)
    H.engage(f, t, pitch_mode=1, roll_mode=2, rwy_elev_ft=elev, leg_lat0_deg=far[0], leg_lon0_deg=far[1], leg_lat1_deg=aim[0], leg_lon1_deg=aim[1])
    f['fcs/throttle-cmd-norm'] = 0.0
    f['fcs/speedbrake-cmd-norm'] = 2 / 3
    f['ap/manual'] = 1
    th0 = f['attitude/theta-deg']
    st = dict(down=False)

    def fly(f, t):
        v, th, wh = f['velocities/ve-kts'], f['attitude/theta-deg'], f['aero/wheel-height-ft']
        if f['ap/on-mains'] > 0:
            st['down'] = True
        if st['down']:
            herr = (course - f['attitude/psi-deg'] + 180.0) % 360.0 - 180.0
            ped = float(np.clip(0.3 * herr - 0.002 * f['ap/leg-xt-ft'] - 2.0 * f['velocities/r-rad_sec'], -1, 1))
            f[STICKS[2]] = ped
            f['fcs/steer-cmd-norm'] = ped * min(1.0, 30.0 / max(f['velocities/vg-fps'], 1.0))
            f[STICKS[0]], f[STICKS[1]], f['fcs/speedbrake-cmd-norm'] = 0.3 if th > -0.5 else 0.0, 0.0, 1.0
            H.brakes(f, 0.5 if f['gear/unit[0]/WOW'] else 0.0)
            return
        flare = wh < 70.0
        want = 2.4 if flare else th0 + float(np.clip(0.3 * (v - keas), -4, 4))
        f[STICKS[0]] = -float(np.clip(0.4 * (want - th), -1, 1))
        f[STICKS[1]] = past_dead(float(np.clip(f['ap/bank-track-deg'] / f['ap/bank-command-limit-deg'], -1, 1)))      # the flight director's bank
        if not flare:
            st['spo'] = float(np.clip(2 / 3 + 0.004 * f['ap/glide-error-ft'] + 0.02 * f['ap/glide-sink-error-fps'], 0.1, 1))
        else:
            want_sink = max(2.3, 0.07782 * f['velocities/vg-fps'] * wh / 70.0)
            st['spo'] = float(np.clip(st['spo'] + 0.25 * (f['velocities/h-dot-fps'] + want_sink) / H.HZ, 0.1, 1))
        f['fcs/speedbrake-cmd-norm'] = st['spo']
    log = H.run(f, 260, every=6, hook=fly)
    H.brakes(f, 0)
    if not (log['mains'] > 0).any():
        add('H6', 'landing by hand through the protected law', False, 'never touched down')
        return
    i = int(np.argmax(log['mains'] > 0))
    past, sink, xt = -log['togo'][i], -log['hdot'][i - 1] * 0.3048, log['xt'][i]
    add('H6', 'landing by hand through the protected law', -500 <= past <= 5000 and abs(xt) <= 75 and sink < 2.0 and f['limits/overstress'] == 0,
        'touches down %.0f ft past the aiming point at %.2f m/s, %.1f KEAS and %.1f deg, %.1f ft off the centreline; down to %.0f kt, within %.0f ft of the centreline on the roll' % (
            past, sink, log['keas'][i], log['theta'][i], abs(xt), log['vg'][-1], np.abs(log['xt'][i:]).max()))


def dutch_roll(log):
    """Damping ratio from the decay of sideslip peaks after a pedal pulse."""
    k = log['t'] > 2.0
    b, t = log['beta'][k], log['t'][k]
    b = b - np.polyval(np.polyfit(t, b, 2), t)                      # take the slow drift out
    pk = [n for n in range(1, len(b) - 1) if abs(b[n]) > abs(b[n - 1]) and abs(b[n]) >= abs(b[n + 1]) and abs(b[n]) > 0.02]
    if len(pk) < 3:
        return 1.0, 0.0                                               # no oscillation left to measure
    d = np.mean([math.log(abs(b[pk[n]]) / abs(b[pk[n + 1]])) for n in range(min(3, len(pk) - 1))])
    return d / math.sqrt(math.pi ** 2 + d ** 2), 2 * (t[pk[1]] - t[pk[0]])


def direct(f):
    for name, cond in CONDS:
        start(f, cond, manual=2)
        log = H.run(f, 40, every=2, hook=hold(STICKS[2], 0.5, 1.0))
        z, period = dutch_roll(log)
        add('D1', '%s, direct: Dutch roll' % name, z >= 0.15, 'damping ratio %.2f%s' % (z, ', period %.1f s' % period if period else ' or more: no oscillation to measure'))
        start(f, cond, manual=2)
        log = H.run(f, 600, hook=lambda f, t: f.__setitem__(STICKS[0], -0.2 if 5 <= t < 6 else 0.0))       # a nudge, then hands off
        bad = (np.abs(log['phi']) > 10) | (np.abs(log['kcas'] - log['kcas'][0]) > 10)
        report('D2', '%s, direct: a nudge on the stick, then hands off' % name, ('%.0f s until 10 deg of bank or 10 kt off (bank %.1f deg, speed %+.1f kt then)' % (
            log['t'][np.argmax(bad)], log['phi'][np.argmax(bad)], log['kcas'][np.argmax(bad)] - log['kcas'][0])) if bad.any() else
            'still within 10 deg and 10 kt after 600 s (bank %.1f deg, speed %+.1f kt)' % (log['phi'][-1], log['kcas'][-1] - log['kcas'][0]))


def structure(f, clean):
    start(f, CONDS[2][1], manual=2)
    st = dict(passed=None, flagged=None, failed=None)

    def pull(f, t):
        f[STICKS[0]] = 0.25 if t < 6 else -1.0                       # a gentle dive for speed, then pull
        if f['accelerations/Nz'] > 2.5 and st['passed'] is None:
            st['passed'] = t
        if f['limits/overstress'] == 1 and st['flagged'] is None:
            st['flagged'] = t
        if f['limits/failed'] == 1 and st['failed'] is None:
            st['failed'] = t
    log = H.run(f, 20, every=1, hook=pull)
    ok = st['passed'] is not None and st['flagged'] is not None and st['flagged'] - st['passed'] <= 0.1 and clean == 0
    add('S1', 'direct, low: dive 6 s, then full back stick', ok, ('load factor passed 2.5 at %.2f s, flagged %.3f s later; reached %.2f; %s; never flagged in H3 or H4: %s' % (
        st['passed'], st['flagged'] - st['passed'], log['nz'].max(), 'failed (past 3.75) at %.2f s' % st['failed'] if st['failed'] else 'not past the ultimate',
        'true' if clean == 0 else 'FALSE')) if st['passed'] is not None else 'load factor reached only %.2f, at %.0f KEAS' % (log['nz'].max(), log['keas'].max()))
    f['limits/reset'] = 1
    f.run()
    cleared = f['limits/overstress'] == 0
    f['limits/reset'] = 0
    report('S1', 'limits/reset', 'clears the flags: %s' % cleared)


def main():
    f = H.load()
    clean = protected(f)
    for delay in (0.0, 0.3, 1.5):
        log, dh, dpsi, wob_h, wob_phi, over = pilot_task(f, delay)
        text = 'ends %.0f ft and %.1f deg from the targets; over the last 30 s height moves %.0f ft, bank %.1f deg; bank up to %.1f deg' % (
            dh, dpsi, wob_h, wob_phi, np.abs(log['phi']).max())
        if delay < 1.0:
            add('H5', 'pilot task, stick delayed %.1f s' % delay, dh <= 50 and dpsi <= 3 and not over, text)
        else:
            report('H5', 'pilot task, stick delayed %.1f s' % delay, text)
    takeoff(f)
    landing(f)
    direct(f)
    structure(f, clean)
    for tag, name, ok, detail in rows:
        print('%-3s %-46s %-8s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    judged = sum(1 for r in rows if r[2] != 'reported')
    print('\n%d checks, %d pass, %d miss; %d reported' % (judged, judged - miss, miss, len(rows) - judged))


if __name__ == '__main__':
    main()
