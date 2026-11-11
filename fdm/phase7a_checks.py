#!/usr/bin/env python3
"""Phase 7 part A checks: the basic flight laws and autopilot modes (docs/FLIGHT-LAWS.md, section 8).

    python3 fdm/phase7a_checks.py          about a minute and a half

Every check runs at cruise, at the climb point and in the approach configuration, with the wing-bending effect on
and off where it says so. The limits were written before the laws were run.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H         # noqa: E402

CONDS = dict(cruise=dict(alt=60000, mach=0.6, weight=15000), climb=dict(alt=10000, kcas=150, weight=26750),
             approach=dict(alt=3000, kcas=133, weight=20800, gear=1.0, spoiler=2 / 3))
PERIOD = dict(cruise=7.3, climb=5.4, approach=5.5)      # bare-airframe Dutch roll periods, s (Phase 6)
rows = []
QUASI_STEADY = float(open(os.path.join(HERE, 'out', 'mission.txt')).read().split('time from 10,000 to 55,000 ft, s')[1].split()[0])   # Phase 4's mission


def add(tag, name, ok, detail):
    rows.append((tag, name, bool(ok), detail))


def wrap(psi):
    return (np.asarray(psi) + 180.0) % 360.0 - 180.0


def growing(x, t):
    """True if an oscillation in x is larger in the last third of the record than in the middle third."""
    n = len(x)
    a, b = x[n // 3:2 * n // 3], x[2 * n // 3:]
    return np.ptp(b) > 1.5 * np.ptp(a) + 1e-6 and np.ptp(b) > 0.05


def step_metrics(t, y, y0, y1):
    """Overshoot (fraction of the step) and the time after which y stays within 10 % of the step."""
    d = y1 - y0
    over = max(0.0, (np.max((y - y0) / d) - 1.0))
    outside = np.abs(y - y1) > 0.1 * abs(d)
    settle = t[np.max(np.nonzero(outside)[0]) + 1] if outside.any() and not outside[-1] else (0.0 if not outside.any() else float('inf'))
    return over, settle


def main():
    f = H.load()
    trims = {k: H.trim(f, **dict(c)) for k, c in CONDS.items()}
    for k, t in trims.items():
        if not t['ok']:
            add('--', 'trim at %s' % k, False, 'no trim')
    for flex in (1, 0):
        tag = 'bent' if flex else 'rigid'
        for name, t in trims.items():
            f['flex/enable'] = flex
            # A1, A2: engage and hold height
            H.engage(f, t, pitch_mode=2, thrust_mode=3)
            f['flex/enable'] = flex
            log = H.run(f, 300)
            first = log['t'] <= 5
            moved = max(np.ptp(log[s][first]) for s in ('pitch', 'roll', 'yaw'))
            if flex:
                add('A1', 'engaging at the %s trim is bumpless' % name, moved < 0.2 and np.abs(log['alt'][first] - log['alt'][0]).max() < 5,
                    'surfaces moved %.3f deg, height %.2f ft in 5 s' % (moved, np.abs(log['alt'][first] - log['alt'][0]).max()))
            dh, dv = np.abs(log['alt'] - log['alt'][0]).max(), np.abs(log['kcas'] - log['kcas'][0]).max()
            add('A2', 'altitude hold 300 s, %s, %s' % (name, tag), dh < 30 and dv < 2, 'height within %.1f ft, speed within %.2f kt' % (dh, dv))
            # A3 pitch attitude step
            H.engage(f, t, pitch_mode=0, thrust_mode=0)
            th0 = f['attitude/theta-deg']
            step = -2.0 if name == 'approach' else 2.0          # nose up on the approach runs into the angle-of-attack limit, as it should
            f['ap/theta-cmd-deg'] = th0 + step
            log = H.run(f, 12)
            over, settle = step_metrics(log['t'], log['theta'], th0, th0 + step)
            add('A3', 'pitch step %+.0f deg, %s, %s' % (step, name, tag), over < 0.25 and settle <= 8, 'overshoot %.0f %%, within 10 %% after %.1f s' % (100 * over, settle))
            # A4 bank step
            H.engage(f, t, pitch_mode=2, thrust_mode=3)
            half = 0.5 * f['ap/bank-limit-deg']
            f['ap/bank-cmd-deg'] = half
            log = H.run(f, 14)
            over, settle = step_metrics(log['t'], log['phi'], 0.0, half)
            add('A4', 'bank step to %.1f deg, %s, %s' % (half, name, tag), over < 0.20 and settle <= 8 and np.abs(log['beta']).max() < 1.5,
                'overshoot %.0f %%, within 10 %% after %.1f s, sideslip up to %.2f deg' % (100 * over, settle, np.abs(log['beta']).max()))
            # A6 Dutch roll: a sideslip kick
            x = list(t['x'])
            V = np.hypot(x[0], x[2])
            x[1] = V * np.sin(np.radians(2.0))
            H.engage(f, t, x=x, pitch_mode=2, thrust_mode=3)
            log = H.run(f, 3 * PERIOD[name] + 10)
            late = np.abs(log['beta'][log['t'] >= 3 * PERIOD[name]]).max()
            add('A6', 'sideslip kick of 2 deg, %s, %s' % (name, tag), late < 0.2, 'sideslip %.3f deg after %.0f s (limit 0.2)' % (late, 3 * PERIOD[name]))
    f['flex/enable'] = 1
    for name, t in trims.items():
        # A5 heading change
        H.engage(f, t, pitch_mode=2, thrust_mode=3, roll_mode=1)
        f['ap/heading-cmd-deg'] = 90.0
        lim = f['ap/bank-limit-deg']
        log = H.run(f, 420 if name == 'cruise' else 200)
        err = abs(wrap(log['psi'][-1] - 90.0))
        add('A5', 'heading change of 90 deg, %s' % name, err < 1.0 and np.abs(log['phi']).max() <= lim + 1.0,
            'final heading error %.2f deg, bank up to %.1f deg (limit %.0f), height within %.0f ft, sideslip up to %.2f deg' % (
                err, np.abs(log['phi']).max(), lim, np.abs(log['alt'] - log['alt'][0]).max(), np.abs(log['beta']).max()))
        # A7 speed by elevator at maximum thrust
        H.engage(f, t, pitch_mode=1, thrust_mode=1)
        log = H.run(f, 300)
        late = log['t'] >= 60
        dv = np.abs(log['kcas'][late] - log['target'][late]).max()
        add('A7', 'speed by elevator at maximum thrust, %s' % name, dv < 3 and not growing(log['kcas'] - log['target'], log['t']),
            'speed within %.2f kt of the command after 60 s; climbed %.0f ft in 300 s' % (dv, log['alt'][-1] - log['alt'][0]))
        # A8 gain margin: all gains doubled, all halved
        for scale in (2.0, 0.5):
            H.engage(f, t, pitch_mode=2, thrust_mode=3, gain_scale=scale)
            f['ap/bank-cmd-deg'] = 0.5 * f['ap/bank-limit-deg']
            log = H.run(f, 60)
            bad = growing(log['phi'], log['t']) or growing(log['theta'], log['t']) or growing(log['beta'], log['t']) or not np.all(np.isfinite(log['alt']))
            add('A8', 'gains times %.1f, %s' % (scale, name), not bad, 'height within %.0f ft, bank %.1f..%.1f deg in the last 20 s' % (
                np.abs(log['alt'] - log['alt'][0]).max(), log['phi'][log['t'] > 40].min(), log['phi'][log['t'] > 40].max()))
    # A9 protections at cruise
    t = trims['cruise']
    H.engage(f, t, pitch_mode=0, thrust_mode=1)
    f['ap/theta-cmd-deg'] = 15.0
    log = H.run(f, 60)
    add('A9', 'pitch command 15 deg at cruise: angle of attack', log['alpha'].max() <= 3.5 + 1.0,
        'angle of attack up to %.2f deg (limit 3.5 + 1), lowest speed %.1f KCAS, pitch reached %.1f deg' % (log['alpha'].max(), log['kcas'].min(), log['theta'].max()))
    H.engage(f, t, pitch_mode=2, thrust_mode=3)
    f['ap/bank-cmd-deg'] = 60.0
    log = H.run(f, 40)
    add('A9', 'bank command 60 deg at cruise', np.abs(log['phi']).max() <= 16.0, 'bank up to %.1f deg (limit 15 + 1)' % np.abs(log['phi']).max())
    # A11 fuel extremes at cruise height: full and nearly empty
    for w in (26000.0, 11800.0):
        alt = 52000.0 if w > 20000 else 62000.0
        tw = H.trim(f, alt=alt, mach=0.6, weight=w)
        H.engage(f, tw, pitch_mode=2, thrust_mode=3)
        f['ap/bank-cmd-deg'] = 7.5
        log = H.run(f, 120)
        over, settle = step_metrics(log['t'], log['phi'], 0.0, 7.5)
        add('A11', 'bank step and altitude hold at %.0f lb, %.0f ft' % (w, alt), tw['ok'] and over < 0.2 and settle <= 8 and np.abs(log['alt'] - log['alt'][0]).max() < 30,
            'overshoot %.0f %%, settled %.1f s, height within %.1f ft' % (100 * over, settle, np.abs(log['alt'] - log['alt'][0]).max()))
    # A10 the climb, hands off
    t10 = H.trim(f, alt=10000, kcas=150, weight=25400, throttle=1.0)
    H.engage(f, t10, pitch_mode=1, thrust_mode=1, speed_schedule=1, roll_mode=1)
    log = H.run(f, 6000, every=120)
    if log['alt'].max() >= 55000:
        secs = float(np.interp(55000, log['alt'], log['t']))
        k = log['t'] <= secs
        add('A10', 'climb 10,000 to 55,000 ft hands off', abs(secs / QUASI_STEADY - 1) <= 0.05 and np.abs(log['kcas'][k][5:] - log['target'][k][5:]).max() < 3,
            '%.0f s against the quasi-steady %.0f s (%+.1f %%); speed within %.2f kt of the schedule, bank within %.2f deg; Pastor measured 4,596 s' % (
                secs, QUASI_STEADY, 100 * (secs / QUASI_STEADY - 1), np.abs(log['kcas'][k][5:] - log['target'][k][5:]).max(), np.abs(log['phi'][k]).max()))
    else:
        add('A10', 'climb 10,000 to 55,000 ft hands off', False, 'reached only %.0f ft in 6,000 s' % log['alt'].max())

    for tag, name, ok, detail in rows:
        print('%-4s %-52s %s  %s' % (tag, name, 'pass' if ok else 'MISS', detail))
    miss = sum(1 for r in rows if not r[2])
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))


if __name__ == '__main__':
    main()
