#!/usr/bin/env python3
"""The drift of the flare, from FlightGear recordings (fdm/fg_scenario.py's CSV; fdm/fg_matrix.py flies the weights and crosswinds):

    python3 fdm/flare_drift.py [RECORDING.csv ...]      default: fdm/out/fg_matrix/*.csv

Per recording (the weight from its log beside it, `weight N lb`): the crosswind at the wheels (the total wind the flight model had, in the runway's axes, mean of the last 10 s before touchdown; positive from the
right), the nose's crab angle and the sideslip at 15 ft and at the first wheel, the line (cross-track, right positive) at 40 ft, 15 ft and the first wheel, the drift from 15 ft and from 40 ft to the first wheel
(left positive: with the wind from the right a drift to the left is downwind), the lateral acceleration over the last 2 s, the bank at the first wheel. Then the drift against the crosswind and the weight:
a line through the origin per weight (feet per knot) and a fit over all of them, so that an aim offset or a feed-forward can be worked out from the data (docs/PLAN.md, "The flare drift as a table").
"""
import csv
import glob
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def col(rows, k):
    return np.array([float(r[k]) if r.get(k) not in ('', None) else np.nan for r in rows])


def weight_of(path):
    log = os.path.splitext(path)[0] + '.log'
    if os.path.exists(log):
        m = re.search(r'weight (\d+) lb', open(log).read())
        if m:
            return float(m.group(1))
    return float('nan')


def analyse(path):
    rows = list(csv.DictReader(open(path)))
    t, wh, lm, mains, xt = (col(rows, k) for k in ('t', 'wh', 'lm', 'mains', 'xt'))
    above = [i for i in range(len(rows)) if lm[i] == 1 and wh[i] >= 999.0]
    start = above[-1] if above else 0
    td = next((i for i in range(start, len(rows)) if mains[i] > 0), None)
    if td is None:
        return None
    psi, legc, beta, phi, ay, keas, thet = (col(rows, k) for k in ('psi', 'legc', 'beta', 'phi', 'ay', 'keas', 'theta'))
    wn, we = col(rows, 'wnorth'), col(rows, 'weast')
    c = np.radians(np.nanmedian(legc[start:td + 1]))
    xw = (wn * np.sin(c) - we * np.cos(c)) / 1.68781            # kt, positive: blowing to the left of the course (from the right)
    hw = -(wn * np.cos(c) + we * np.sin(c)) / 1.68781

    def at(h):
        j = next((i for i in range(start, td + 1) if wh[i] <= h), td)
        return j
    i15, i40 = at(15.0), at(40.0)
    last10 = [i for i in range(start, td + 1) if t[i] >= t[td] - 10.0]
    last2 = [i for i in range(start, td + 1) if t[i] >= t[td] - 2.0]
    crab = lambda i: float((psi[i] - np.degrees(c) + 540.0) % 360.0 - 180.0)
    return dict(path=path, name=os.path.splitext(os.path.basename(path))[0], weight=weight_of(path), xw=float(np.nanmean(xw[last10])), hw=float(np.nanmean(hw[last10])),
                crab15=crab(i15), crab_td=crab(td), beta15=float(beta[i15]), beta_td=float(beta[td]), x40=float(xt[i40]), x15=float(xt[i15]), x_td=float(xt[td]),
                drift15=float(-(xt[td] - xt[i15])), drift40=float(-(xt[td] - xt[i40])), ay2=float(np.nanmean(ay[last2])), phi_td=float(phi[td]), keas=float(keas[td]),
                sink=float(-col(rows, 'hdot')[max(0, td - 1)] * 0.3048), t_td=float(t[td]), dt15=float(t[td] - t[i15]))


def aim_coefficient():
    """FINAL_AIM_FT_PER_KT_KLB as laws.py has it now (the aim the flights in fdm/out/fg_matrix_aim were flown with)."""
    m = re.search(r'^FINAL_AIM_FT_PER_KT_KLB\s*=\s*([0-9.eE+-]+)', open(os.path.join(HERE, 'laws.py')).read(), re.M)
    return float(m.group(1)) if m else float('nan')


def main():
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(HERE, 'out', 'fg_matrix', '*.csv')))
    R = [r for r in (analyse(p) for p in paths) if r]
    if not R:
        raise SystemExit('no recordings with a touchdown')
    print('%-12s %7s %6s %6s | %6s %6s %6s %6s | %7s %7s %7s | %8s %8s %6s | %7s %6s %5s' % (
        'flight', 'lb', 'xw kt', 'hw kt', 'crab15', 'crabTD', 'beta15', 'betaTD', 'x40 ft', 'x15 ft', 'xTD ft', 'drift15', 'drift40', 'ay g', 'phiTD', 'KEAS', 'sink'))
    for r in R:
        print('%-12s %7.0f %6.1f %6.1f | %6.1f %6.1f %6.1f %6.1f | %7.1f %7.1f %7.1f | %8.1f %8.1f %6.3f | %7.2f %6.0f %5.2f' % (
            r['name'], r['weight'], r['xw'], r['hw'], r['crab15'], r['crab_td'], r['beta15'], r['beta_td'], r['x40'], r['x15'], r['x_td'], r['drift15'], r['drift40'], r['ay2'], r['phi_td'], r['keas'], r['sink']))
    aimed = [r for r in R if 'fg_matrix_aim' in r['path']]
    if aimed:
        k = aim_coefficient()
        print('\nWith the aim offset on (laws.py FINAL_AIM_FT_PER_KT_KLB = %g): the aim is that x weight in 1,000 lb x crosswind; the line should be at the aim down to 15 ft and at 0 at the first wheel' % k)
        print('%-12s %7s %6s | %8s %7s %7s | %8s %8s' % ('flight', 'lb', 'xw kt', 'aim ft', 'x40 ft', 'x15 ft', 'xTD ft', 'drift15'))
        for r in aimed:
            print('%-12s %7.0f %6.1f | %8.1f %7.1f %7.1f | %8.1f %8.1f' % (r['name'], r['weight'], r['xw'], k * r['weight'] / 1000.0 * r['xw'], r['x40'], r['x15'], r['x_td'], r['drift15']))
        x = np.array([r['weight'] / 1000.0 * r['xw'] for r in aimed]); e = np.array([r['x_td'] for r in aimed])
        c = float(-(x * e).sum() / (x * x).sum())
        print('touchdown error (right positive): mean %.1f ft, rms %.1f ft, worst %.1f ft; fitted through the origin it is %.4f ft per (kt x 1,000 lb): the coefficient that would take it out is %.4f (now %g)' % (
            float(e.mean()), float(np.sqrt(np.mean(e ** 2))), float(np.abs(e).max()), -c, k + c, k))
    if len(R) >= 3:
        xw = np.array([r['xw'] for r in R]); w = np.array([r['weight'] for r in R])
        for key in ('drift15', 'drift40'):
            d = np.array([r[key] for r in R])
            k0 = float((xw * d).sum() / (xw * xw).sum())
            print('\n%s (left positive) = %.3f ft/kt x crosswind (a line through the origin), rms residual %.1f ft over %d flights' % (key, k0, float(np.sqrt(np.mean((d - k0 * xw) ** 2))), len(R)))
            for wt in sorted(set(round(x, -2) for x in w if not math.isnan(x))):
                m = np.abs(w - wt) < 1500
                if m.sum() >= 2:
                    k = float((xw[m] * d[m]).sum() / (xw[m] ** 2).sum())
                    print('    about %6.0f lb: %.3f ft/kt (%d flights)' % (wt, k, m.sum()))
            ok = ~np.isnan(w)
            if ok.sum() >= 4:
                A = np.column_stack([xw[ok], xw[ok] * w[ok] / 1000.0])
                coef, *_ = np.linalg.lstsq(A, d[ok], rcond=None)
                print('    over weight too: drift = xw x (%.3f + %.4f x weight in 1000 lb) ft, rms residual %.1f ft' % (coef[0], coef[1], float(np.sqrt(np.mean((d[ok] - A @ coef) ** 2)))))


if __name__ == '__main__':
    main()
