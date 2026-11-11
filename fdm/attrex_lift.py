#!/usr/bin/env python3
"""The lift curve and the turns of NASA 872 from the ATTREX flight data, against the model.

    python3 fdm/attrex_lift.py          about a minute; writes fdm/data/attrex_lift.json

Lift: in steady flight the lift equals the weight, so CL = W / (q S) with q = 0.7 p M2 from the measured static
pressure and Mach number. The data has no weight or fuel channel. The weight is the takeoff weight less the fuel
burned, and the fuel burned comes from our engine model flown along the measured height and Mach number: maximum
thrust while level or climbing, idle while descending. **So the lift coefficients here lean on the engine model
and on an assumed takeoff weight (full: 26,750 lb)**; the slope of CL against angle of attack scales with both.
The data's angle of attack turns out to be pitch attitude less flight-path angle (the two agree within 0.2 deg
all flight): a true angle of attack of the axes the inertial unit calls level. What is fitted is where the wing
sits in those axes: its incidence, one number.

Turns: in a steady level turn tan(bank) = V x (turn rate) / g. This checks the reading of the data more than the model.
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import attrex               # noqa: E402
import engine as E          # noqa: E402

ENG = json.load(open(os.path.join(HERE, 'data', 'engine.json')))['tables']
CAL = os.path.join(HERE, 'data', 'calibration.json')
S_REF = 540.0
TAKEOFF_WEIGHT = 26750.0
PSF = 2.0885434             # per hPa
FT = 0.3048


def fuel_flow(alt_ft, mach, T_K, descending):
    """lb/h from the engine tables: maximum thrust, or idle in a descent; scaled with the square root of temperature."""
    from scipy.interpolate import RegularGridInterpolator
    global _FF
    try:
        _FF
    except NameError:
        a, m = np.array(ENG['altitude_ft']), np.array(ENG['mach'])
        f = np.array(ENG['fuel_lbh'])
        fr = ENG['thrust_fraction']
        _FF = (RegularGridInterpolator((a, m), f[:, :, fr.index(1.0)], bounds_error=False, fill_value=None),
               RegularGridInterpolator((a, m), f[:, :, fr.index(0.07)], bounds_error=False, fill_value=None))
    pts = np.stack([np.clip(alt_ft, 0, 70000), np.clip(mach, 0, 0.7)], -1)
    t_isa = np.array([E.isa(h)[0] for h in np.clip(alt_ft, 0, 70000)])
    cal = json.load(open(CAL)).get('fuel_factor', 1.0) if os.path.exists(CAL) else 1.0
    return np.where(descending, _FF[1](pts), _FF[0](pts)) * np.sqrt(T_K / t_isa) * cal


def flight(path):
    d = attrex.derived(attrex.load(path, every=20))             # one record a second
    t = d['t']
    ok = ~np.isnan(d['P']) & ~np.isnan(d['M']) & ~np.isnan(d['T'])
    alt = np.interp(t, t[ok], d['HP'][ok]) / FT
    mach = np.interp(t, t[ok], d['M'][ok])
    T = np.interp(t, t[ok], d['T'][ok])
    vs = np.gradient(alt, t)                                     # ft/s
    vs = np.convolve(vs, np.ones(60) / 60, mode='same')
    flow = fuel_flow(alt, mach, T, vs < -8.0)                    # lb/h
    burned = np.concatenate([[0.0], np.cumsum(0.5 * (flow[1:] + flow[:-1]) * np.diff(t) / 3600.0)])
    d['W'] = TAKEOFF_WEIGHT - burned - 150.0                     # 150 lb: taxi, takeoff and the first climb before the record starts
    d['vs'] = vs
    return d


def lift_points(d):
    """One point per steady segment: Mach, angle of attack, CL, weight, height."""
    out = []
    for s in attrex.steady_segments(d):
        k = (d['t'] >= s['start']) & (d['t'] <= s['end'])
        q = 0.7 * np.nanmean(d['P'][k]) * PSF * np.nanmean(d['M'][k]) ** 2
        w = float(np.nanmean(d['W'][k]))
        out.append(dict(t=float(s['start']), minutes=s['dur'] / 60, mach=float(np.nanmean(d['M'][k])), aoa=float(np.nanmean(d['AOA'][k])),
                        cl=w / (q * S_REF), weight=w, alt_ft=float(s['hp'] / FT), pitch=float(np.nanmean(d['PITCH'][k])),
                        climb_fpm=float(s['dh'] / FT / (s['dur'] / 60))))
    return out


def turns(d):
    """Long steady turns: mean bank, and the bank the turn rate and speed call for."""
    roll, t = d['ROLL'], d['t']
    hdg = np.degrees(np.unwrap(np.radians(np.where(np.isnan(d['HDG']), 0.0, d['HDG']))))
    out, i, n = [], 0, len(t)
    banked = np.abs(roll) > 8.0
    while i < n:
        if not banked[i]:
            i += 1
            continue
        j = i
        while j < n and banked[j] and np.sign(roll[j]) == np.sign(roll[i]):
            j += 1
        if t[j - 1] - t[i] > 90.0 and not np.isnan(d['HDG'][i:j]).any():
            a, b = i + 15, j - 15                               # drop the roll-in and roll-out
            rate = np.radians(hdg[b] - hdg[a]) / (t[b] - t[a])
            v = np.nanmean(np.hypot(d['XDOT'][a:b], d['YDOT'][a:b]))   # ground speed: the turn is over the ground
            out.append(dict(bank=float(np.nanmean(roll[a:b])), predicted=float(np.degrees(np.arctan(v * rate / 9.80665))),
                            seconds=float(t[b] - t[a]), alt_ft=float(np.nanmean(d['HP'][a:b]) / FT), tas=float(np.nanmean(d['TAS'][a:b]))))
        i = j
    return out


def main():
    files = sorted(glob.glob(os.path.join(attrex.DATA, 'MMS-20Hz', '*.ict.gz')))
    pts, trn = [], []
    for p in files:
        d = flight(p)
        date = os.path.basename(p).split('_')[2]
        lp, tr = lift_points(d), turns(d)
        for x in lp + tr:
            x['flight'] = date
        pts += lp
        trn += tr
        print('%s: %2d steady segments, %2d long turns, fuel burned by the model %.0f lb in %.1f h' % (
            date, len(lp), len(tr), TAKEOFF_WEIGHT - 150 - d['W'][-1], (d['t'][-1] - d['t'][0]) / 3600), flush=True)
    out = dict(assumptions=dict(takeoff_weight_lb=TAKEOFF_WEIGHT, weight='takeoff weight less the fuel flow of our engine model along '
                                'the measured height and Mach number', q='0.7 p M2 from measured pressure and Mach'),
               points=pts, turns=trn)
    # The flights' takeoff weights aren't known and differ, which shifts each flight's lift coefficients as a
    # whole. So the slope is fitted within flights: every flight gets its own intercept, all share one slope.
    # Flights whose steady segments span less than 1 deg of angle of attack carry no slope and are left out.
    res = []
    for lo, hi in ((0.50, 0.54), (0.59, 0.62)):
        k = [x for x in pts if lo <= x['mach'] <= hi and abs(x['climb_fpm']) < 30]
        a_all, c_all, used, inter = [], [], [], []
        for fl in sorted(set(x['flight'] for x in k)):
            a = np.array([x['aoa'] for x in k if x['flight'] == fl])
            c = np.array([x['cl'] for x in k if x['flight'] == fl])
            if len(a) >= 5 and np.ptp(a) >= 1.0:
                a_all.append(a - a.mean())
                c_all.append(c - c.mean())
                used.append(fl)
                inter.append((a.mean(), c.mean()))
        if not used:
            print('Mach %.2f-%.2f: no flight spans 1 deg of angle of attack in its steady segments' % (lo, hi))
            continue
        a, c = np.concatenate(a_all), np.concatenate(c_all)
        sl = float(np.sum(a * c) / np.sum(a * a))
        cl0 = [cm - sl * am for am, cm in inter]                   # each flight's lift coefficient at zero angle of attack
        res.append(dict(mach_lo=lo, mach_hi=hi, flights=used, segments=int(len(a)), slope_per_deg=sl,
                        rms=float(np.std(c - sl * a)), cl_at_zero_alpha_mean=float(np.mean(cl0)), cl_at_zero_alpha_range=[float(min(cl0)), float(max(cl0))]))
        print('Mach %.2f-%.2f: %d flights, %d segments: slope %.4f per deg (scatter %.3f); CL at zero angle of attack %.3f '
              '(flights %.3f to %.3f)' % (lo, hi, len(used), len(a), sl, res[-1]['rms'], np.mean(cl0), min(cl0), max(cl0)))
    out['lift_fits'] = res
    if trn:
        e = np.array([abs(x['bank']) - abs(x['predicted']) for x in trn])
        print('turns: %d of 90 s or more; bank %.1f deg on average; measured less predicted %+.2f deg mean, %.2f deg scatter' % (
            len(trn), np.mean([abs(x['bank']) for x in trn]), e.mean(), e.std()))
        out['turn_fit'] = dict(n=len(trn), mean_bank=float(np.mean([abs(x['bank']) for x in trn])), mean_error_deg=float(e.mean()),
                               scatter_deg=float(e.std()))
    json.dump(out, open(os.path.join(HERE, 'data', 'attrex_lift.json'), 'w'), indent=1)
    return out


if __name__ == '__main__':
    main()
