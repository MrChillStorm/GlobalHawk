#!/usr/bin/env python3
"""The throttle the speed law needs for a flight path angle, measured: the thrust feed-forward of the level-off (docs/PLAN.md, "Level-off").

    python3 fdm/pathperf.py [--write]       --write: data/path_thrust.json, which fdm/laws.py reads (the measured cells: CELLS=file.json)

The throttle for level flight and its slope in the flight path angle (the laws add slope * (the angle now less the angle at engagement) to the throttle the speed law latched at engagement, so that the thrust
follows the path through a level-off; the climb the thrust holds is (1 - level) / slope, the descent at idle level / slope) as a function of

    Mach number x lift coefficient (weight over dynamic pressure and wing area) x pressure altitude

and not of calibrated airspeed x weight x altitude, as the first tables were. The drag the aircraft has to overcome is a function of the lift coefficient and Mach number (CD(CL, M) q S), the thrust of the engine a
function of Mach number and the air's pressure and temperature: above the tropopause the throttle for level flight depends on the lift coefficient and Mach number alone (flown: the same CL and Mach at every
height from 32,500 to 65,000 ft, 11,500 to 26,700 lb, within 0.002 of throttle, docs/PLAN.md "the throttle table in lift coefficient and Mach"), and below it on the temperature too, which is a function of height
(0 to 30,000 ft every 2,500 ft, flown; above, three slices at 36,089, 50,000 and 62,500 ft: the throttle at the same CL and Mach changes by 0.0005 from 30,000 to 35,000 ft and by 0.001 to 0.01 in 10,000 ft above). Third grid: the angle of attack at level flight (the body-axes angle at flight path angle 0, from the same trims: grid_alpha_level_deg), the laws' altitude mode adds it to its pitch command (docs/PLAN.md, "the level-flight angle of attack"). The first table (calibrated airspeed x weight x height, 7 x 10 x 14
cells) was off by up to 0.14 of throttle (6 ft/s of climb rate) at 50,000 to 60,000 ft between its points and 0.56 above 60,000 ft, where the level throttle goes over 1 (docs/PLAN.md).

Method: at a (height, Mach, CL) the weight is CL q S (q = 1481.35 delta M^2); where that is inside the aircraft's weight range (11,500 to 26,700 lb) the aircraft is trimmed at fixed throttles (0.2 to 1) with the
speed held, no acceleration, clean, and then at the throttles that make path angles of -4 to +4 deg about level; the line through the points gives the throttle for level flight (its value at path angle 0, over 1
where the aircraft cannot hold the height at full thrust: it can only descend) and its slope in the angle, deg^-1. Above 32,500 ft the cells of every height there that the weights allow are flown and averaged
into the slice of their band (a state that only another band's heights reach takes that band's value). Where the weight range does not reach (the lift coefficient and Mach number of a state no weight makes at that height) the value is extended along the lift coefficient by the line through the
nearest two measured, the way a table needs it; the laws only ever look up states that are flown.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402

TERRAIN = -5000.0                                   # the pressure altitude is the axis itself: the ground is 5,000 ft below at every height
MAX_MACH = 0.62                                     # the governor's Mach 0.63 less a margin
MACHS = tuple(round(0.10 + 0.02 * i, 2) for i in range(27))          # 0.10 to 0.62
CLS = tuple(round(0.10 + 0.05 * i, 2) for i in range(25))            # 0.10 to 1.30
TROPO = tuple(2500.0 * i for i in range(13))                         # 0 to 30,000 ft: slices of their own
BANDS = ((36089.0, (32500.0, 35000.0, 37500.0, 40000.0)),            # above the troposphere: slices at 36,089, 50,000 and 62,500 ft, each the average of the cells flown at the heights beside it (the throttle
         (50000.0, tuple(42500.0 + 2500.0 * i for i in range(7))),   # for the same CL and Mach number changes by -0.001 to -0.01 of throttle in 10,000 ft there, a little more near full thrust)
         (62500.0, (60000.0, 62500.0, 65000.0)))
STRAT = BANDS[0][0]
W_MIN, W_MAX = 11500.0, 26700.0                                      # lb: the aircraft's weight range (11,450 empty, 26,750 full) less a margin
SP_US = (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)                              # the spoilers' effect on the level angle of attack, deg, by spoiler position, lift coefficient and Mach number (a table of its own: it is not a constant per unit of spoiler:
SP_HEIGHT = 5000.0                                                    # 3.1 deg at CL 0.3 and 5.5 at CL 1.0 for 2/3: they dump a share of the lift), measured at this height (the landing configuration is flown under 10,000 ft)
SP_MACHS = tuple(round(0.10 + 0.02 * i, 2) for i in range(16))       # 0.10 to 0.40
THROTTLES = (0.2, 0.4, 0.6, 0.8, 1.0)
ANGLES = (-4.0, -2.0, -1.0, 0.0, 1.0, 2.0, 4.0)       # deg about level flight


def delta(h):
    """The pressure ratio of the standard atmosphere."""
    return (1 - 6.8756e-6 * h) ** 5.2559 if h < 36089.24 else 0.22336 * math.exp(-(h - 36089.24) / 20805.7)


def weight_for(cl, mach, h, s_w):
    return cl * s_w * 1481.35 * delta(h) * mach * mach


def trims(f, w, h, mach, throttles, **extra):
    pts = []
    for thr in throttles:
        try:
            t = H.trim(f, alt=h, mach=mach, weight=w, lat=60.0, lon=25.0, psi=90.0, terrain=TERRAIN, throttle=thr, **extra)
        except Exception:
            continue
        if t['ok']:
            pts.append((float(t['cond']['gamma']), float(thr), float(t['alpha'])))
    return pts


def cell(f, w, h, mach, **extra):
    """A first line through trims at five throttles from idle to full; the cell's line through trims at the throttles that make path angles of -4 to +4 deg about level flight by that first line (the first
    line over the whole range is out by 0.008 of throttle where the thrust is plentiful and the angles at the first throttles are 20 deg). (level throttle, per degree, fit residual, level-flight angle of attack) or None."""
    pts = trims(f, w, h, mach, THROTTLES, **extra)
    if len(pts) < 3:
        return None
    g = np.array([p[0] for p in pts])
    th = np.array([p[1] for p in pts])
    al = np.array([p[2] for p in pts])
    slope, level = np.polyfit(g, th, 1)
    want = sorted(set(round(float(min(1.0, max(0.03, level + slope * a))), 3) for a in ANGLES))
    pts2 = trims(f, w, h, mach, want, **extra)
    if len(pts2) >= 3:
        g = np.array([p[0] for p in pts2])
        th = np.array([p[1] for p in pts2])
        al = np.array([p[2] for p in pts2])
        slope, level = np.polyfit(g, th, 1)
    a_slope, a_level = np.polyfit(g, al, 1)               # the angle of attack at path angle 0: the level-flight angle (the body-axes angle the laws' pitch command needs: pitch = path angle + angle of attack)
    return float(level), float(slope), float(np.abs(th - (slope * g + level)).max()), float(a_level)


def extend(a):
    """Fill the NaNs of a[mach][cl]: along the lift coefficient by the line through the nearest two measured (the nearest one if only one), else from the nearest Mach number's row."""
    a = a.copy()
    for i in range(a.shape[0]):
        ok = ~np.isnan(a[i])
        if ok.sum() >= 2:
            x = np.nonzero(ok)[0]
            for j in np.nonzero(~ok)[0]:
                lo, hi = x[x < j], x[x > j]
                if len(lo) and len(hi):
                    a[i, j] = np.interp(j, [lo[-1], hi[0]], [a[i, lo[-1]], a[i, hi[0]]])
                elif len(hi):
                    p, q = hi[0], hi[1]
                    a[i, j] = a[i, p] + (a[i, q] - a[i, p]) * (j - p) / (q - p)
                else:
                    p, q = lo[-1], lo[-2]
                    a[i, j] = a[i, p] + (a[i, p] - a[i, q]) * (j - p) / (p - q)
        elif ok.sum() == 1:
            a[i, ~ok] = a[i, ok][0]
    for i in range(a.shape[0]):                          # rows with nothing measured: the nearest row that has
        if np.isnan(a[i]).all():
            near = sorted([k for k in range(a.shape[0]) if not np.isnan(a[k]).any()], key=lambda k: abs(k - i))
            a[i] = a[near[0]]
    return a


def main():
    f = H.load_variant({})
    s_w = float(f['metrics/Sw-sqft'])
    print('wing area %.1f ft^2; weights %g to %g lb; %d Mach x %d CL x %d heights (%d troposphere slices and %d above)' % (s_w, W_MIN, W_MAX, len(MACHS), len(CLS), len(TROPO) + len(BANDS), len(TROPO), len(BANDS)), flush=True)
    slices = {}                                           # height -> {'level': [mach][cl], 'per_deg': ..., 'count': ...}
    cells = []
    holes = []

    def new():
        return dict(level=np.full((len(MACHS), len(CLS)), np.nan), per_deg=np.full((len(MACHS), len(CLS)), np.nan), alpha=np.full((len(MACHS), len(CLS)), np.nan), n=np.zeros((len(MACHS), len(CLS)), int),
                    level_spread=np.zeros((len(MACHS), len(CLS))), pd_spread=np.zeros((len(MACHS), len(CLS))))
    bands = dict(BANDS)
    for h in TROPO + tuple(b[0] for b in BANDS):
        s = new()
        heights = bands.get(h, (h,))
        flown = failed = 0
        for i, m in enumerate(MACHS):
            for j, cl in enumerate(CLS):
                vals = []
                for hh in heights:
                    w = weight_for(cl, m, hh, s_w)
                    if not (W_MIN <= w <= W_MAX):
                        continue
                    c = cell(f, w, hh, m)
                    if c is None:
                        failed += 1
                        holes.append(dict(height_ft=hh, mach=m, cl=cl, weight_lb=round(w), why='no trim at three throttles'))
                        continue
                    flown += 1
                    vals.append(c)
                    cells.append(dict(height_ft=hh, mach=m, cl=cl, weight_lb=round(w, 1), level=round(c[0], 5), per_deg=round(c[1], 5), residual=round(c[2], 5), alpha_level=round(c[3], 4)))
                if vals:
                    lv = np.array([v[0] for v in vals])
                    pd = np.array([v[1] for v in vals])
                    s['level'][i, j] = lv.mean()
                    s['per_deg'][i, j] = pd.mean()
                    s['alpha'][i, j] = np.mean([v[3] for v in vals])
                    s['n'][i, j] = len(vals)
                    s['level_spread'][i, j] = lv.max() - lv.min()
                    s['pd_spread'][i, j] = pd.max() - pd.min()
        slices[h] = s
        print('%7.0f ft: %4d cells flown, %3d with no trim, %4d of %d points measured; level %.3f to %.3f; the spread of the heights averaged: %.4f at most' % (
            h, flown, failed, int((~np.isnan(s['level'])).sum()), len(MACHS) * len(CLS), np.nanmin(s['level']), np.nanmax(s['level']), s['level_spread'].max()), flush=True)
    heights = list(TROPO) + [b[0] for b in BANDS]
    for n, (h, _) in enumerate(BANDS):                   # a state only another band's heights reach: that band's value (the nearest first)
        for key in ('level', 'per_deg', 'alpha'):
            a = slices[h][key]
            for other, _ in sorted(BANDS, key=lambda b: abs(b[0] - h)):
                if other != h:
                    b = slices[other][key]
                    miss = np.isnan(a) & ~np.isnan(b)
                    a[miss] = b[miss]
    dsp = np.full((len(SP_US), len(SP_MACHS), len(CLS)), np.nan)        # [spoiler][mach][cl]: the angle of attack at level flight less the clean aircraft's, deg
    dsp[0] = 0.0
    nsp = 0
    for iu, u in enumerate(SP_US):
        if iu == 0:
            continue
        for im, m in enumerate(SP_MACHS):
            for ic, cl in enumerate(CLS):
                w = weight_for(cl, m, SP_HEIGHT, s_w)
                if not (W_MIN <= w <= W_MAX):
                    continue
                c0 = cell(f, w, SP_HEIGHT, m)
                cu = cell(f, w, SP_HEIGHT, m, spoiler=u)
                if c0 is not None and cu is not None:
                    dsp[iu, im, ic] = cu[3] - c0[3]
                    nsp += 1
    print('spoiler table: %d cells flown at %g ft; the effect at 2/3 from %.2f to %.2f deg' % (nsp, SP_HEIGHT, np.nanmin(dsp[2]), np.nanmax(dsp[2])), flush=True)
    sp_grid = []
    for iu in range(len(SP_US)):
        a = np.clip(extend(dsp[iu]), 0.0, 14.0)
        sp_grid.append([[round(float(a[im, ic]), 4) for im in range(len(SP_MACHS))] for ic in range(len(CLS))])           # [spoiler][cl][mach]
    grids = {}
    for key in ('level', 'per_deg', 'alpha'):
        out = []
        for h in heights:
            a = extend(slices[h][key])                    # [mach][cl]
            a = np.clip(a, 0.0, 2.5) if key == 'level' else (np.clip(a, 0.0, 1.0) if key == 'per_deg' else np.clip(a, -8.0, 14.0))
            out.append([[round(float(a[i, j]), 5) for i in range(len(MACHS))] for j in range(len(CLS))])      # [height][cl][mach]
        grids[key] = out
    res = max(c['residual'] for c in cells)
    print('%d cells, %d with no trim; the worst fit residual %.4f' % (len(cells), len(holes), res), flush=True)
    doc = dict(note='pathperf.py: the throttle (norm) for level flight (over 1: the height cannot be held at full thrust) and its slope per degree of flight path angle, from trims at fixed throttles, clean, by Mach number, '
                    'lift coefficient (weight over dynamic pressure and wing area) and pressure altitude: 0 to 30,000 ft every 2,500 ft, and one slice for 36,089 ft and above (measured at 32,500 to 65,000 ft); '
                    'values at states no weight in 11,500 to 26,700 lb makes are extended along the lift coefficient (listed in the docstring of pathperf.py), the laws never look them up',
               axes=dict(pressure_alt_ft=heights, cl=list(CLS), mach=list(MACHS)), wing_area_sqft=s_w,
               grid_throttle_level=grids['level'], grid_throttle_per_deg=grids['per_deg'], grid_alpha_level_deg=grids['alpha'], spoiler_axes=dict(spoiler=list(SP_US), cl=list(CLS), mach=list(SP_MACHS), height_ft=SP_HEIGHT), grid_alpha_spoiler_deg=sp_grid,
               measured=dict(cells=len(cells), no_trim=len(holes), worst_fit_residual=round(res, 5), worst_spread_of_heights_in_a_band=round(max(float(slices[b[0]]['level_spread'].max()) for b in BANDS), 5)))
    if '--write' in sys.argv:
        json.dump(doc, open(os.path.join(HERE, 'data', 'path_thrust.json'), 'w'), separators=(',', ':'))
        print('written')
        if os.environ.get('CELLS'):
            json.dump(dict(cells=cells, holes=holes), open(os.environ['CELLS'], 'w'))
    return doc


if __name__ == '__main__':
    main()
