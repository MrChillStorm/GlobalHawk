#!/usr/bin/env python3
"""The CFD runs of the LRN 1015 against the tunnel, NeuralFoil's table (with the moment's exponent) and XFOIL: python3 fdm/cfd/compare.py

Reads fdm/data/cfd_lrn1015.json (fdm/cfd/sweep.py --collect). Limits, written before the first run (docs/PLAN.md, Q5): SU2 is trusted for the
stall only if at Mach 0.6 its moment at equal lift between 0.4 and 1.0 is within 0.02 of the tunnel's at both Reynolds numbers and its maximum lift is
within 10 % of the tunnel's 1.31 (Re 1 million). Fully turbulent flow has more drag than the tunnel's free transition, so drag is reported only.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import strips as S  # noqa: E402

D = os.path.join(HERE, '..', 'data')


def curve(cases, mach, re):
    c = sorted([r for r in cases if abs(r['mach'] - mach) < 1e-6 and abs(r['re'] - re) < 1], key=lambda r: r['alpha'])
    return tuple(np.array([r[k] for r in c]) for k in ('alpha', 'cl', 'cd', 'cm'))


def main():
    cfd = json.load(open(os.path.join(D, 'cfd_lrn1015.json')))['cases']
    tunnel = json.load(open(os.path.join(D, 'lrn1015_tunnel.json')))['cases']
    wing = S.section_tables()['wing']
    out = {}
    for c in tunnel:
        m, re = c['mach'], c['reynolds']
        a, cl, cd, cm = curve(cfd, m, re)
        if len(a) < 4:
            continue
        top = int(np.argmax(cl))
        pts = [p for p in c['cm'] if 0.4 <= p[1] <= 1.0 and p[1] <= cl[top]]
        t_cm = float(np.mean([p[0] for p in pts]))
        o = np.argsort(cl[:top + 1])
        c_cm = float(np.mean([np.interp(p[1], cl[:top + 1][o], cm[:top + 1][o]) for p in pts]))
        t_max = max(p[1] for p in c['alpha'])
        mcl, mcd, mcm = S.Section(wing, m)(S.ALPHAS, np.full(len(S.ALPHAS), re))
        mt = int(np.argmax(mcl))
        out[(m, re)] = dict(cfd_cm=c_cm, tunnel_cm=t_cm, d_cm=c_cm - t_cm, cfd_clmax=float(cl[top]), alpha_clmax=float(a[top]), tunnel_clmax=t_max,
                            d_clmax=100 * (cl[top] / t_max - 1), model_clmax=float(mcl[mt]), n=len(a), cd_cl07=float(np.interp(0.7, cl[:top + 1][o], cd[:top + 1][o])))
        r = out[(m, re)]
        print('Mach %.1f Re %.0f million: moment at the tunnel\'s lifts: CFD %.4f, tunnel %.4f (%+.4f); maximum lift: CFD %.3f at %.0f deg (last case %.0f deg), tunnel %.3f (%+.1f %%), '
              'model %.3f; drag at cl 0.7 CFD %.5f' % (m, re / 1e6, r['cfd_cm'], r['tunnel_cm'], r['d_cm'], r['cfd_clmax'], r['alpha_clmax'], a[-1], r['tunnel_clmax'], r['d_clmax'], r['model_clmax'], r['cd_cl07']))
    # the trust rule
    k6a, k6b = out.get((0.6, 1e6)), out.get((0.6, 2e6))
    if k6a and k6b:
        trusted = abs(k6a['d_cm']) <= 0.02 and abs(k6b['d_cm']) <= 0.02 and abs(k6a['d_clmax']) <= 10.0
        print('\ntrust rule (moment within 0.02 at both Reynolds numbers, maximum lift within 10 %% at Re 1 million): %s' % ('TRUSTED' if trusted else 'NOT trusted'))
    # the step of the maximum lift from Mach 0.6 to 0.65, at the flight's Reynolds number
    c6 = [curve(cfd, 0.6, re) for re in (1e6, 2e6)]
    a65, cl65, _, _ = curve(cfd, 0.65, 1.5e6)
    if len(a65) >= 4 and all(len(x[0]) >= 4 for x in c6):
        m6 = 0.5 * (np.max(c6[0][1]) + np.max(c6[1][1]))
        print('maximum lift at Mach 0.65 (Re 1.5 million) %.3f against %.3f at Mach 0.6 (mean of Re 1 and 2 million): %+.1f %%; model: %.3f at 0.65 against %.3f at 0.6' % (
            np.max(cl65), m6, 100 * (np.max(cl65) / m6 - 1), float(np.max(S.Section(wing, 0.65)(S.ALPHAS, np.full(len(S.ALPHAS), 1.5e6))[0])),
            float(np.max(S.Section(wing, 0.6)(S.ALPHAS, np.full(len(S.ALPHAS), 1.5e6))[0]))))
    # the growth of the moment from Mach 0.2 to 0.6 at the same lifts
    a2, cl2, _, cm2 = curve(cfd, 0.2, 1e6)
    if (0.2, 1e6) in out and (0.6, 1e6) in out:
        print('growth of the moment from Mach 0.2 to 0.6, Re 1 million, at the tunnel\'s lifts: CFD %.3f, tunnel %.3f (the tables 1.237, XFOIL 1.187)' % (
            out[(0.6, 1e6)]['cfd_cm'] / out[(0.2, 1e6)]['cfd_cm'], out[(0.6, 1e6)]['tunnel_cm'] / out[(0.2, 1e6)]['tunnel_cm']))
    json.dump({'%g_%g' % k: v for k, v in out.items()}, open(os.path.join(D, 'cfd_compare.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
