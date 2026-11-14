#!/usr/bin/env python3
"""What the aircraft really does in a steady turn, measured: the turn performance table (docs/PLAN.md, "a turn performance table instead of a fixed
fraction of the bank limit").

    python3 fdm/turnperf.py [--write]       --write: data/turn_performance.json, which fdm/laws.py and fdm/capability.py read

Level turns of 200 deg in calm air through the bank law (roll mode 0, ap/bank-cmd-deg) with the speed and altitude held, at three weights, four heights and three speeds
at each, banks commanded of 10 to 45 deg (the model built with the bank command limit lifted, so the command reaches them). Per cell:
  flown_per_cmd  the bank flown over the bank commanded, less 1 (the steady part from 60 deg of turn on): the laws' bank law settles above its command, more so heavy
                 and low (the 0.86 of the bank limit stood in for it, one number for every cell)
  cap_deg        the largest bank flown that holds the height within CAP_ALT_FT, the speed within CAP_KCAS and stays CAP_ALPHA_MARGIN under the angle-of-attack
                 limit (the aircraft's own limit, not the sourced bank): the ceiling for a correction in a wind
  what limits it ('alt', 'speed' or 'alpha'; 'none' when the largest bank tried held)
  lag_in_s       the turn's effective delay rolling in: the time from the command until the heading has changed as much as a turn at the steady rate would have by then
                 (the area between the steady turn rate and the turn rate's response), less the command's own ramp (half the bank over the 5 deg/s rate): the time the
                 turn starts late by, in the lead. From the heading, not the bank: the bank settles with a long tail and the lift follows it later still, so the heading's
                 delay is 0.4 s more than the bank's (the calm turn's trace, docs/PLAN.md), which the delay table of rolltest.py (time to 10 deg) does not see either
  moment_in_s2, moment_out_s2   the sideways drift of the response's tail, in s^2: the area between the real heading and the heading of the instant-turn equivalent
                 (the one the delays make) over the roll in (from the command to the turn being 60 deg on) and over the roll out, over the steady turn rate. The aircraft
                 is that area times its speed and its turn rate, g tan(bank) times it, to the inside at the roll in (a shift of the whole arc, seen at the exit only by its
                 component across the new line: cos of the corner) and to the outside at the roll out (seen in full). A first-order tail of time constant T has T^2 / 2
                 (the ramp of a bank rate limit alone, T_ramp^2 / 24: 0.8 s^2 at 22,000 lb, much less than what is measured)
  lag_out_s      the same rolling out: the heading gained after the roll out is commanded, over the steady turn rate, less the ramp: the time the turn goes on for after
                 the command, in the trigger of the roll out
The cells are on a common grid (WEIGHTS x HEIGHTS x SPEEDS, the three axes the laws' 3D table needs); a combination the aircraft does not fly (over MAX_MACH, or
a trim that does not exist) is a hole: listed in "holes" and filled in "grid" from the nearest speed at the same weight and height, never invented.
Limits and results: docs/PLAN.md, "Turns in a wind: a turn performance table".
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

WEIGHTS = (12000.0, 20000.0, 26000.0)
# height over the ground (terrain 174 ft) and the calibrated airspeeds flown there (the schedule's speed in the middle)
HEIGHTS = (4000.0, 20000.0, 30000.0, 45000.0)          # over the ground (terrain 174 ft): the pressure altitude is 174 ft more
SPEEDS = (110.0, 130.0, 150.0, 170.0)                  # KCAS; FAST_KCAS (175): above it the pitch governor takes the nose up and the height is not held
MAX_MACH = 0.62                                         # the governor's Mach 0.63 less a margin
TERRAIN = 174.0
BANKS = (10.0, 20.0, 30.0, 35.0, 40.0, 45.0)
CAP_ALT_FT, CAP_KCAS, CAP_ALPHA_MARGIN = 100.0, 5.0, 0.5
STEADY_FROM_DEG = 60.0
TURN_DEG = 200.0
LAG_BANKS = (10.0, 20.0)         # the banks the lags are measured at (they should not depend on the size of the step: compared)
ROLLOUT_S = 45.0


def fly(f, w, h, k, b):
    t = H.trim(f, alt=h + TERRAIN, kcas=k, weight=w, lat=60.0, lon=25.0, psi=90.0, terrain=TERRAIN)
    H.engage(f, t, pitch_mode=2, thrust_mode=3, speed_schedule=0)
    f['ap/speed-cmd-kcas'] = f['velocities/vc-kts']
    f['ap/roll-mode'] = 0
    t0 = f['simulation/sim-time-sec']
    alt0, vc0, psi0 = f['position/h-sl-ft'], f['velocities/vc-kts'], f['attitude/psi-deg']
    f['ap/bank-cmd-deg'] = b
    rows, turned, last = [], 0.0, psi0
    for i in range(int(150 * H.HZ)):
        f.run()
        psi = f['attitude/psi-deg']
        turned += (psi - last + 540) % 360 - 180
        last = psi
        if i % int(H.HZ / 4) == 0:
            rows.append((turned, f['attitude/phi-deg'], f['aero/alpha-deg'], f['position/h-sl-ft'] - alt0, f['velocities/vc-kts'] - vc0, f['ap/alpha-limit-deg'],
                         f['simulation/sim-time-sec'] - t0))
        if turned > TURN_DEG:
            break
    a = np.array(rows)
    steady = a[a[:, 0] > STEADY_FROM_DEG]
    phi_ss = float(steady[:, 1].mean()) if len(steady) else float('nan')
    out = dict(cmd=b, flown=phi_ss, alpha=float(a[:, 2].max()), alpha_limit=float(a[0, 5]), dalt=float(abs(a[:, 3]).max()), dkcas=float(abs(a[:, 4]).max()), turned=float(turned))
    if b in LAG_BANKS and phi_ss == phi_ss:
        # the steady turn rate: the slope of the heading over the turn from 60 to 180 deg
        m = (a[:, 0] > STEADY_FROM_DEG) & (a[:, 0] < 180.0)
        w_ss = float(np.polyfit(a[m, 6], a[m, 0], 1)[0])
        # in: the time the heading is 60 deg on, less what 60 deg takes at the steady rate
        j = int(np.argmax(a[:, 0] > STEADY_FROM_DEG))
        d_in = float(a[j, 6] - a[j, 0] / w_ss)                      # the heading's delay, from the command, in all
        out['lag_in'] = d_in - 0.5 * b / laws.BANK_RATE
        ideal_in = w_ss * np.maximum(0.0, a[:j + 1, 6] - d_in)
        out['moment_in'] = float(np.trapezoid(a[:j + 1, 0] - ideal_in, a[:j + 1, 6]) / w_ss)
        # out: the heading gained from the command to 0 on, over the steady rate
        f['ap/bank-cmd-deg'] = 0.0
        turned0 = turned
        r = []
        for i in range(int(ROLLOUT_S * H.HZ)):
            f.run()
            psi = f['attitude/psi-deg']
            turned += (psi - last + 540) % 360 - 180
            last = psi
            if i % int(H.HZ / 4) == 0:
                r.append((f['attitude/phi-deg'], turned, i / H.HZ))
        r = np.array(r)
        gain = r[:, 1] - turned0
        out['lag_out'] = float(gain[-1] / w_ss) - 0.5 * phi_ss / laws.BANK_RATE
        rem_a = gain[-1] - gain
        rem_i = np.maximum(0.0, gain[-1] - w_ss * r[:, 2])
        out['moment_out'] = float(np.trapezoid(rem_a - rem_i, r[:, 2]) / w_ss)
        out['bank_end'] = float(abs(r[-1, 0]))
        out['turn_rate_dps'] = w_ss
    return out


def crossing(xs, ys, limit):
    """x at which ys first goes over the limit, interpolated; None if it never does"""
    for i in range(1, len(xs)):
        if ys[i] > limit >= ys[i - 1]:
            return xs[i - 1] + (xs[i] - xs[i - 1]) * (limit - ys[i - 1]) / (ys[i] - ys[i - 1])
    return None if ys[0] <= limit else xs[0]


def cell(f, w, h, k):
    runs = [fly(f, w, h, k, b) for b in BANKS]
    cmd = np.array([r['cmd'] for r in runs])
    flown = np.array([r['flown'] for r in runs])
    low = cmd <= 30.0
    e = float(np.sum((flown[low] - cmd[low]) * cmd[low]) / np.sum(cmd[low] ** 2))       # flown - cmd = e * cmd
    lims = {'alt': crossing(list(flown), [r['dalt'] for r in runs], CAP_ALT_FT),
            'speed': crossing(list(flown), [r['dkcas'] for r in runs], CAP_KCAS),
            'alpha': crossing(list(flown), [r['alpha'] - r['alpha_limit'] for r in runs], -CAP_ALPHA_MARGIN)}
    found = {n: v for n, v in lims.items() if v is not None}
    if found:
        why = min(found, key=found.get)
        cap = found[why]
    else:
        why, cap = 'none', float(flown[-1])
    lin = [r['lag_in'] for r in runs if 'lag_in' in r]
    lout = [r['lag_out'] for r in runs if 'lag_out' in r]
    min_ = [r['moment_in'] for r in runs if 'moment_in' in r]
    mout = [r['moment_out'] for r in runs if 'moment_out' in r]
    return dict(weight_lb=w, height_ft=h, kcas=k, flown_per_cmd=round(e, 4), cap_deg=round(cap, 1), limited_by=why,
                lag_in_s=round(float(np.mean(lin)), 2), lag_out_s=round(float(np.mean(lout)), 2),
                lag_in_spread=round(float(max(lin) - min(lin)), 2), lag_out_spread=round(float(max(lout) - min(lout)), 2),
                moment_in_s2=round(float(np.mean(min_)), 2), moment_out_s2=round(float([r['moment_out'] for r in runs if r['cmd'] == 20.0][0]), 2),    # the roll out's from the 20 deg run: the response is not as linear in the step as the delays, and 20 is the nearer to the bank the turns use
                moment_in_spread=round(float(max(min_) - min(min_)), 2), moment_out_spread=round(float(max(mout) - min(mout)), 2),
                alpha_limit=round(runs[0]['alpha_limit'], 2), runs=[{kk: round(vv, 2) for kk, vv in r.items()} for r in runs])


def mach_of(kcas, h_ft):
    """Mach number at a calibrated airspeed and a pressure altitude (ISA)"""
    p = (1 - 6.87559e-6 * h_ft) ** 5.25588
    qc = (1 + 0.2 * (kcas / 661.47) ** 2) ** 3.5 - 1
    return math.sqrt(5 * ((qc / p + 1) ** (1 / 3.5) - 1))


def main():
    f = H.load_variant({'laws.BANK_COMMAND': 2.0, 'laws.BANK_LIMIT': [(0.0, 25.0), (80000.0, 25.0)]})
    cells, holes = {}, []
    print('%8s %8s %6s %6s %10s %8s %7s %7s %7s %7s  %s' % ('lb', 'ft', 'KCAS', 'Mach', 'flown/cmd', 'cap deg', 'lag in', 'lag out', 'm in', 'm out', 'limited by'), flush=True)
    for w in WEIGHTS:
        for h in HEIGHTS:
            for k in SPEEDS:
                m = mach_of(k, h + TERRAIN)
                if m > MAX_MACH:
                    holes.append(dict(weight_lb=w, height_ft=h, kcas=k, why='Mach %.2f over %g' % (m, MAX_MACH)))
                    print('%8.0f %8.0f %6.1f %6.2f  hole: over Mach %g' % (w, h, k, m, MAX_MACH), flush=True)
                    continue
                try:
                    c = cell(f, w, h, k)
                except Exception as ex:                      # a trim that does not exist is a hole, not a guess
                    holes.append(dict(weight_lb=w, height_ft=h, kcas=k, why='no trim: %s' % str(ex)[:60]))
                    print('%8.0f %8.0f %6.1f %6.2f  hole: %s' % (w, h, k, m, str(ex)[:60]), flush=True)
                    continue
                c['mach'] = round(m, 3)
                cells[(w, h, k)] = c
                print('%8.0f %8.0f %6.1f %6.2f %+9.2f%% %8.1f %7.2f %7.2f %7.2f %7.2f  %s (spread in %.2f out %.2f; m in %.2f out %.2f)' % (w, h, k, m, 100 * c['flown_per_cmd'], c['cap_deg'], c['lag_in_s'], c['lag_out_s'], c['moment_in_s2'], c['moment_out_s2'], c['limited_by'], c['lag_in_spread'], c['lag_out_spread'], c['moment_in_spread'], c['moment_out_spread']), flush=True)
    # the grid the laws' 3D table reads: [speed][weight][height]; a hole takes the nearest measured speed at that weight and height (the speeds are ascending)
    grids = {k_: [] for k_ in ('flown_per_cmd', 'cap_deg', 'lag_in_s', 'lag_out_s', 'moment_in_s2', 'moment_out_s2')}
    for k in SPEEDS:
        rows_ = {k_: [] for k_ in grids}
        for w in WEIGHTS:
            cols = {k_: [] for k_ in grids}
            for h in HEIGHTS:
                near = sorted([kk for (ww, hh, kk) in cells if ww == w and hh == h], key=lambda kk: abs(kk - k))
                c = cells[(w, h, near[0])]
                for k_ in grids:
                    cols[k_].append(c[k_])
            for k_ in grids:
                rows_[k_].append(cols[k_])
        for k_ in grids:
            grids[k_].append(rows_[k_])
    out = {'note': 'turnperf.py: level 200 deg turns in calm air, the bank law, the speed and height held; flown_per_cmd = bank flown over bank commanded less 1; cap_deg = the largest bank flown that '
                   'holds %g ft, %g kt and is %g deg under the angle-of-attack limit' % (CAP_ALT_FT, CAP_KCAS, CAP_ALPHA_MARGIN),
           'axes': dict(speed_kcas=list(SPEEDS), weight_lb=list(WEIGHTS), pressure_alt_ft=[h + TERRAIN for h in HEIGHTS]),
           'grid_flown_per_cmd': grids['flown_per_cmd'], 'grid_cap_deg': grids['cap_deg'], 'grid_lag_in_s': grids['lag_in_s'], 'grid_lag_out_s': grids['lag_out_s'], 'grid_moment_in_s2': grids['moment_in_s2'], 'grid_moment_out_s2': grids['moment_out_s2'], 'holes': holes, 'cells': list(cells.values())}
    if '--write' in sys.argv:
        json.dump(out, open(os.path.join(HERE, 'data', 'turn_performance.json'), 'w'), indent=1)
        print('written')
    return out


if __name__ == '__main__':
    main()
