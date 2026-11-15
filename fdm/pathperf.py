#!/usr/bin/env python3
"""The throttle the speed law needs for a flight path angle, measured: the thrust feed-forward of the level-off (docs/PLAN.md, "Level-off").

    python3 fdm/pathperf.py [--write]       --write: data/path_thrust.json, which fdm/laws.py reads

On the grid of the turn performance table (fdm/turnperf.py: weight x pressure altitude x calibrated airspeed, the whole envelope, 0 to 65,000 ft) the aircraft is trimmed at
fixed throttles (0.2 to 1) with the speed held, no acceleration, clean: the flight path angle each throttle gives. Per cell, the line through those points: the throttle for level
flight (its value at path angle 0, over 1 where the aircraft cannot hold the height at full thrust: it can only descend) and its slope in the angle, deg^-1. The laws add
slope * (the angle now less the angle at engagement) to the throttle the speed law latched at engagement, so that the thrust follows the path through a level-off (a climb
flattened out at the climb's thrust is the speed running away: 38 kt at 12,000 lb, the baseline of docs/PLAN.md); the climb the thrust holds is (1 - level) / slope, and the
descent at idle level / slope.

One method for every cell, at every height (the first table trimmed at path angles of -4 to +4 deg, which at the ceiling is a band of a degree or two and left the cells over
45,000 ft and over a weight's ceiling empty: the laws clamped to the table's edge, and at 64,000 ft it said the thrust holds a climb of 38 ft/s where the aircraft can climb 0.1).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402
import turnperf as TP           # noqa: E402

THROTTLES = (0.2, 0.4, 0.6, 0.8, 1.0)
ANGLES = (-4.0, -2.0, -1.0, 0.0, 1.0, 2.0, 4.0)       # deg about level flight


def trims(f, w, h, k, throttles):
    pts = []
    for thr in throttles:
        try:
            t = H.trim(f, alt=h, kcas=k, weight=w, lat=60.0, lon=25.0, psi=90.0, terrain=TP.TERRAIN, throttle=thr)
        except Exception:
            continue
        if t['ok']:
            pts.append((float(t['cond']['gamma']), float(thr)))
    return pts


def cell(f, w, h, k):
    """A first line through trims at five throttles from idle to full; the cell's line through trims at the throttles that make path angles of -4 to +4 deg about level flight
    by that first line (the throttle for level flight is where the laws work: the first line, over the whole range, is out by 0.008 of throttle at low heights, where the
    thrust is plentiful and the angles at the first throttles are 20 deg)."""
    pts = trims(f, w, h, k, THROTTLES)
    if len(pts) < 3:
        return None
    g = np.array([p[0] for p in pts])
    th = np.array([p[1] for p in pts])
    slope, level = np.polyfit(g, th, 1)
    want = sorted(set(round(float(min(1.0, max(0.03, level + slope * a))), 3) for a in ANGLES))
    pts2 = trims(f, w, h, k, want)
    if len(pts2) >= 3:
        pts = pts2
        g = np.array([p[0] for p in pts])
        th = np.array([p[1] for p in pts])
        slope, level = np.polyfit(g, th, 1)
    return dict(weight_lb=w, height_ft=h, kcas=k, throttle_level=round(float(level), 4), throttle_per_deg=round(float(slope), 5),
                fit_residual=round(float(np.abs(th - (slope * g + level)).max()), 4), angles=[round(float(x), 2) for x in g], throttles=[round(float(x), 3) for x in th])


def main():
    f = H.load_variant({})
    cells = {}
    holes = []
    print('%8s %8s %6s %6s %10s %10s %9s  angles' % ('lb', 'ft', 'KCAS', 'Mach', 'level', 'per deg', 'residual'), flush=True)
    for w in TP.WEIGHTS:
        for h in TP.HEIGHTS:
            for k in TP.SPEEDS:
                m = TP.mach_of(k, h)
                if m > TP.MAX_MACH:
                    holes.append(dict(weight_lb=w, height_ft=h, kcas=k, why='Mach %.2f over %g' % (m, TP.MAX_MACH)))
                    continue
                c = cell(f, w, h, k)
                if c is None:
                    holes.append(dict(weight_lb=w, height_ft=h, kcas=k, why='no trim at three throttles'))
                    print('%8.0f %8.0f %6.1f %6.2f  hole: no trim' % (w, h, k, m), flush=True)
                    continue
                c['mach'] = round(m, 3)
                cells[(w, h, k)] = c
                print('%8.0f %8.0f %6.1f %6.2f %10.3f %10.4f %9.4f  %s' % (w, h, k, m, c['throttle_level'], c['throttle_per_deg'], c['fit_residual'], c['angles']), flush=True)
    # the grid the laws' 3D table reads: [speed][weight][height]. A hole takes the nearest speed measured at that weight and height; at a weight and height where nothing is
    # flown (the Mach over the limit at every speed there) the nearest weight's cell there. Listed in "holes", never invented.
    grids = {'throttle_level': [], 'throttle_per_deg': []}
    for k in TP.SPEEDS:
        rows = {n: [] for n in grids}
        for w in TP.WEIGHTS:
            cols = {n: [] for n in grids}
            for h in TP.HEIGHTS:
                near = sorted([kk for (ww, hh, kk) in cells if ww == w and hh == h], key=lambda kk: abs(kk - k))
                if near:
                    c = cells[(w, h, near[0])]
                else:
                    other = sorted([(abs(ww - w), abs(kk - k), ww, kk) for (ww, hh, kk) in cells if hh == h])
                    c = cells[(other[0][2], h, other[0][3])]
                for n in grids:
                    cols[n].append(c[n])
            for n in grids:
                rows[n].append(cols[n])
        for n in grids:
            grids[n].append(rows[n])
    out = dict(note='pathperf.py: the throttle (norm) for level flight (over 1: the height cannot be held at full thrust) and its slope per degree of flight path angle, from trims at fixed throttles, '
                    'clean, by weight, pressure altitude and calibrated airspeed over the whole envelope',
               axes=dict(speed_kcas=list(TP.SPEEDS), weight_lb=list(TP.WEIGHTS), pressure_alt_ft=list(TP.HEIGHTS)),
               grid_throttle_level=grids['throttle_level'], grid_throttle_per_deg=grids['throttle_per_deg'], holes=holes, cells=list(cells.values()))
    print('%d cells, %d holes; the worst fit residual %.4f' % (len(cells), len(holes), max(c['fit_residual'] for c in cells.values())), flush=True)
    if '--write' in sys.argv:
        json.dump(out, open(os.path.join(HERE, 'data', 'path_thrust.json'), 'w'), indent=1)
        print('written')
    return out


if __name__ == '__main__':
    main()
