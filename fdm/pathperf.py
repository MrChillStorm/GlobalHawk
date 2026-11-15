#!/usr/bin/env python3
"""The throttle the speed law needs for a flight path angle, measured: the thrust feed-forward of the level-off (docs/PLAN.md, "Level-off").

    python3 fdm/pathperf.py [--write]       --write: data/path_thrust.json, which fdm/laws.py reads

At the cells of the turn performance table (weight x pressure altitude x calibrated airspeed, fdm/turnperf.py) the aircraft is trimmed at flight path angles of -4 to +4 deg
(speed held, no acceleration, clean: the engine's throttle for it). Per cell: the throttle for level flight and its slope in the angle, deg^-1, from the angles at which a trim
exists and the throttle is inside its range. The laws add slope * (the angle now less the angle at engagement) to the throttle the speed law latched at engagement, so that the
thrust follows the path through a level-off (a climb flattened out at the climb's thrust is the speed running away: 38 kt at 12,000 lb, the baseline of docs/PLAN.md).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402
import turnperf as TP           # noqa: E402

GAMMAS = (-4.0, -2.0, 0.0, 2.0, 4.0)
TERRAIN = 0.0


def cell(f, w, h, k, gammas=GAMMAS, top=0.98):
    pts = []
    for g in gammas:
        try:
            t = H.trim(f, alt=h + 174.0, kcas=k, weight=w, lat=60.0, lon=25.0, psi=90.0, terrain=174.0, gamma=g)
        except Exception:
            continue
        if t['ok'] and 0.02 < t['throttle'] <= top:
            pts.append((g, t['throttle'], t['thrust'], t['thrust_max'], t['pitch_deg']))
    if len(pts) < 3 or not any(abs(p[0]) < 1e-9 for p in pts):
        return None
    g = np.array([p[0] for p in pts])
    th = np.array([p[1] for p in pts])
    slope, level = np.polyfit(g, th, 1)
    return dict(weight_lb=w, height_ft=h, kcas=k, throttle_level=round(float(next(p[1] for p in pts if abs(p[0]) < 1e-9)), 4), throttle_per_deg=round(float(slope), 5),
                fit_residual=round(float(np.abs(th - (slope * g + level)).max()), 4), angles=[round(float(x), 1) for x in g], throttles=[round(float(x), 4) for x in th])


def main():
    f = H.load_variant({})
    cells = {}
    holes = []
    print('%8s %8s %6s %10s %10s %9s  angles' % ('lb', 'ft', 'KCAS', 'level', 'per deg', 'residual'), flush=True)
    for w in TP.WEIGHTS:
        for h in TP.HEIGHTS:
            for k in TP.SPEEDS:
                m = TP.mach_of(k, h + 174.0)
                if m > TP.MAX_MACH:
                    holes.append(dict(weight_lb=w, height_ft=h, kcas=k, why='Mach %.2f over %g' % (m, TP.MAX_MACH)))
                    continue
                c = cell(f, w, h, k)
                if c is None:
                    holes.append(dict(weight_lb=w, height_ft=h, kcas=k, why='no trim within the throttle range'))
                    print('%8.0f %8.0f %6.1f  hole: no trim' % (w, h, k), flush=True)
                    continue
                cells[(w, h, k)] = c
                print('%8.0f %8.0f %6.1f %10.3f %10.4f %9.4f  %s' % (w, h, k, c['throttle_level'], c['throttle_per_deg'], c['fit_residual'], c['angles']), flush=True)
    grids = {'throttle_level': [], 'throttle_per_deg': []}
    for k in TP.SPEEDS:
        rows = {n: [] for n in grids}
        for w in TP.WEIGHTS:
            cols = {n: [] for n in grids}
            for h in TP.HEIGHTS:
                near = sorted([kk for (ww, hh, kk) in cells if ww == w and hh == h], key=lambda kk: abs(kk - k))
                if not near:                                  # no cell at this weight and height: the nearest weight at the same height and speed
                    alt = sorted([(abs(ww - w), ww, kk) for (ww, hh, kk) in cells if hh == h], key=lambda x: (x[0], abs(x[2] - k)))
                    c = cells[(alt[0][1], h, alt[0][2])]
                else:
                    c = cells[(w, h, near[0])]
                for n in grids:
                    cols[n].append(c[n])
            for n in grids:
                rows[n].append(cols[n])
        for n in grids:
            grids[n].append(rows[n])
    out = dict(note='pathperf.py: the throttle (norm) for level flight and its slope per degree of flight path angle, trimmed at -4 to +4 deg, clean, by weight, pressure altitude and calibrated airspeed',
               axes=dict(speed_kcas=list(TP.SPEEDS), weight_lb=list(TP.WEIGHTS), pressure_alt_ft=[h + 174.0 for h in TP.HEIGHTS]),
               grid_throttle_level=grids['throttle_level'], grid_throttle_per_deg=grids['throttle_per_deg'], holes=holes, cells=list(cells.values()))
    if '--write' in sys.argv:
        json.dump(out, open(os.path.join(HERE, 'data', 'path_thrust.json'), 'w'), indent=1)
        print('written')
    return out


# ---- the table to the ceiling (2026-11-15). The first table stopped at 45,174 ft, 110 KCAS and 26,000 lb and the laws clamp to it: at 64,000 ft it said the thrust holds a climb of 38 ft/s where the
# aircraft can climb 0.1, and the level-off began 800 ft out where the thrust could not fly it (docs/PLAN.md, the 65,000 ft scenario). Near the ceiling the throttle range is a narrow band of
# path angles (idle at -1.5 deg, the most thrust at level flight), so finer angles, and a level flight that takes the whole throttle is a cell (the throttle at most 1).
CEIL_HEIGHTS = (55000.0, 60000.0, 65000.0)
CEIL_WEIGHTS = (14000.0, 16000.0)
CEIL_SPEEDS = (90.0, 100.0)
CEIL_GAMMAS = (-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0)
CEIL_MAX_MACH = 0.70


def cell_limited(f, w, h, k):
    """A cell above the weight's ceiling: no level flight at full thrust. The flight path angle the throttle gives (0.4, 0.7 and the most) is found, the throttle for level flight
    is where that line crosses zero angle (over 1: the aircraft can only descend at full thrust) and its slope the line's."""
    pts = []
    for thr in (0.4, 0.7, 1.0):
        try:
            t = H.trim(f, alt=h + 174.0, kcas=k, weight=w, lat=60.0, lon=25.0, psi=90.0, terrain=174.0, throttle=thr)
        except Exception:
            return None
        if not t['ok']:
            return None
        pts.append((float(t['cond']['gamma']), thr))
    g = np.array([p[0] for p in pts])
    th = np.array([p[1] for p in pts])
    slope, level = np.polyfit(g, th, 1)
    return dict(weight_lb=w, height_ft=h, kcas=k, throttle_level=round(float(level), 4), throttle_per_deg=round(float(slope), 5),
                fit_residual=round(float(np.abs(th - (slope * g + level)).max()), 4), angles=[round(float(x), 2) for x in g], throttles=[round(float(x), 4) for x in th], limited=True)


def extend(old):
    """The old table with the heights, speeds and weights added: the old cells are kept as they were (a flight below 45,000 ft changes in nothing), the weights between the old rows are
    interpolated from them at the old heights (what the laws' table did between them), the new speeds copy the lowest old one (what it did below it), and the new heights are trimmed."""
    f = H.load_variant({})
    ax = old['axes']
    sp0, wt0, al0 = ax['speed_kcas'], ax['weight_lb'], ax['pressure_alt_ft']
    sp1 = sorted(set(sp0) | set(CEIL_SPEEDS))
    wt1 = sorted(set(wt0) | set(CEIL_WEIGHTS))
    al1 = list(al0) + [h + 174.0 for h in CEIL_HEIGHTS]
    cells = {(c['weight_lb'], c['height_ft'] + 174.0, c['kcas']): c for c in old['cells']}
    new_cells, holes = [], list(old['holes'])
    for w in wt1:
        for h in CEIL_HEIGHTS:
            for k in sp1:
                m = TP.mach_of(k, h + 174.0)
                if m > CEIL_MAX_MACH:                                          # (turnperf's Mach of a calibrated speed is 7 % over the model's up here: 100 KCAS at 65,000 ft is Mach 0.61 in it)
                    holes.append(dict(weight_lb=w, height_ft=h, kcas=k, why='Mach %.2f over %g' % (m, CEIL_MAX_MACH)))
                    continue
                c = cell(f, w, h, k, CEIL_GAMMAS, 1.0) or cell_limited(f, w, h, k)
                if c is None:
                    holes.append(dict(weight_lb=w, height_ft=h, kcas=k, why='no trim within the throttle range'))
                    print('%8.0f %8.0f %6.1f  hole: no trim' % (w, h, k), flush=True)
                    continue
                cells[(w, h + 174.0, k)] = c
                new_cells.append(c)
                print('%8.0f %8.0f %6.1f %10.3f %10.4f %9.4f  %s' % (w, h, k, c['throttle_level'], c['throttle_per_deg'], c['fit_residual'], c['angles']), flush=True)
    grids = {}
    for name, old_grid in (('throttle_level', old['grid_throttle_level']), ('throttle_per_deg', old['grid_throttle_per_deg'])):
        og = np.array(old_grid)                                              # speed x weight x altitude
        g = np.zeros((len(sp1), len(wt1), len(al1)))
        for i, k in enumerate(sp1):
            for j, w in enumerate(wt1):
                for a, h in enumerate(al1):
                    if a < len(al0):                                          # the old heights: from the old grid, the new speeds as the lowest old one, the new weights between the rows
                        ik = int(np.searchsorted(sp0, k, side='right') - 1) if k >= sp0[0] else 0
                        g[i, j, a] = np.interp(w, wt0, og[max(ik, 0), :, a])
                        if k not in sp0 and k > sp0[0]:                       # (none: the new speeds are below the old ones)
                            pass
                    else:                                                     # the new heights: the cell, else the nearest speed of this weight and height, else the nearest weight
                        c = cells.get((w, h, k))
                        if c is None:
                            near = sorted([kk for (ww, hh, kk) in cells if ww == w and hh == h], key=lambda kk: abs(kk - k))
                            if near:
                                c = cells[(w, h, near[0])]
                            else:
                                alt = sorted([(abs(ww - w), ww, kk) for (ww, hh, kk) in cells if hh == h], key=lambda x: (x[0], abs(x[2] - k)))
                                if not alt:                                   # nothing flown at this height: the height below
                                    below = max(hh for (ww, hh, kk) in cells if hh < h)
                                    alt = sorted([(abs(ww - w), ww, kk) for (ww, hh, kk) in cells if hh == below], key=lambda x: (x[0], abs(x[2] - k)))
                                    c = cells[(alt[0][1], below, alt[0][2])]
                                else:
                                    c = cells[(alt[0][1], h, alt[0][2])]
                        g[i, j, a] = c[name]
        grids[name] = g.round(5).tolist()
    out = dict(note=old['note'] + '; extended to 65,000 ft, 90 KCAS and 14,000 and 16,000 lb (pathperf.py --extend): finer path angles near the ceiling, the old cells kept',
               axes=dict(speed_kcas=sp1, weight_lb=wt1, pressure_alt_ft=al1), grid_throttle_level=grids['throttle_level'], grid_throttle_per_deg=grids['throttle_per_deg'],
               holes=holes, cells=old['cells'] + new_cells)
    return out


if __name__ == '__main__':
    if '--extend' in sys.argv:
        old = json.load(open(os.path.join(HERE, 'data', 'path_thrust.json')))
        out = extend(old)
        if '--write' in sys.argv:
            json.dump(out, open(os.path.join(HERE, 'data', 'path_thrust.json'), 'w'), indent=1)
            print('written')
    else:
        main()
