#!/usr/bin/env python3
"""The wing section's stall at Mach 0.6, fitted to the tunnel's height with the CFD's shape: python3 fdm/cfd/stall_fit.py [--write]

A named fit, not a prediction (limits: docs/PLAN.md, "Stall at Mach 0.6 fitted to the tunnel"). For the Mach 0.6 column of the wing table, at each Reynolds
number of the table, the lift above ALPHA_S is blended from the table's own to the target

    target(alpha, Re) = cl_CFD(alpha, Re) + offset(alpha, Re)

the CFD's curve from its runs at 1, 1.5 (if run) and 2 million by log Reynolds number, held beyond; the offset (not a scale, so the CFD's fall past the peak
is kept exactly) runs linearly in angle from the table's own value at ALPHA_S (target = table there: no jump) to the one that puts the CFD's peak at the
tunnel's maximum lift (from its 1 and 2 million by log Reynolds number, the nearer held beyond), and is held after the peak. The blend weight is 0 up to ALPHA_S, rises to 1 over RAMP degrees (a smooth step), stays 1 to the last angle the
CFD ran at, then falls back to 0 over TAIL degrees (the target held at its last value). Below ALPHA_S nothing changes, so the lift-curve slope and the lift at the
drag and moment limits' range stay as they are. --write puts the result in fdm/data/cfd_stall_m06.json, which strips.section_tables() applies to the wing's lift.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import strips as S  # noqa: E402

D = os.path.join(HERE, '..', 'data')
OUT = os.path.join(D, 'cfd_stall_m06.json')
MACH = 0.6
ALPHA_S = 3.5
RAMP = 1.0
TAIL = 2.0


def cfd_curves(cases):
    """{Reynolds number: (alpha, cl)} of Mach 0.6, every case with a finite result, in angle order."""
    out = {}
    for re in sorted(set(r['re'] for r in cases if abs(r['mach'] - MACH) < 1e-6)):
        c = sorted([r for r in cases if abs(r['mach'] - MACH) < 1e-6 and abs(r['re'] - re) < 1 and r['finite']], key=lambda r: r['alpha'])
        if len(c) >= 8:
            out[re] = (np.array([r['alpha'] for r in c]), np.array([r['cl'] for r in c]))
    return out


def cfd_at(curves, re, alpha):
    """The CFD's lift at the angles, at a Reynolds number: linear in log Reynolds number between its runs, the nearer held beyond."""
    res = sorted(curves)
    lr = np.log(res)
    x = float(np.clip(np.log(re), lr[0], lr[-1]))
    i = int(np.clip(np.searchsorted(lr, x) - 1, 0, max(len(res) - 2, 0)))
    if len(res) == 1:
        return np.interp(alpha, *curves[res[0]])
    w = (x - lr[i]) / (lr[i + 1] - lr[i])
    lo, hi = np.interp(alpha, *curves[res[i]]), np.interp(alpha, *curves[res[i + 1]])
    return (1 - w) * lo + w * hi


def tunnel_max(tunnel, re):
    pts = sorted((c['reynolds'], max(p[1] for p in c['alpha'])) for c in tunnel if abs(c['mach'] - MACH) < 1e-6)
    return float(np.interp(np.log(re), np.log([p[0] for p in pts]), [p[1] for p in pts]))


def weight(alpha, a_end):
    s = np.clip((alpha - ALPHA_S) / RAMP, 0, 1)
    s = s * s * (3 - 2 * s)
    t = np.clip((alpha - a_end) / TAIL, 0, 1)
    return s * (1 - t * t * (3 - 2 * t))


def build(cases, tunnel):
    curves = cfd_curves(cases)
    a_end = min(c[0][-1] for c in curves.values())
    S.CD_WAVE = False
    t = S.section_tables()
    wing = t['wing']
    mi = list(t['mach']).index(MACH)
    cl0 = np.array(wing['cl'][mi])                      # reynolds x alpha
    alpha = np.array(t['alpha'])
    w = weight(alpha, a_end)
    fine = np.arange(-2.0, a_end + 1e-9, 0.1)
    rows = []
    target = np.zeros_like(cl0)
    for k, re in enumerate(t['reynolds']):
        cf = cfd_at(curves, re, fine)
        top = int(np.argmax(cf))
        a_pk = float(fine[top])
        i_s = int(np.argmin(abs(alpha - ALPHA_S)))
        d_s = cl0[k][i_s] - float(cfd_at(curves, re, np.array([alpha[i_s]]))[0])
        d_p = tunnel_max(tunnel, re) - cf[top]
        off = d_s + (d_p - d_s) * np.clip((alpha - alpha[i_s]) / (a_pk - alpha[i_s]), 0, 1)
        target[k] = cfd_at(curves, re, np.clip(alpha, alpha[0], a_end)) + off
        rows.append(dict(re=re, offset_start=float(d_s), offset_peak=float(d_p), cfd_max=float(cf[top]), cfd_peak_deg=a_pk, tunnel_max=tunnel_max(tunnel, re)))
    new = (1 - w[None, :]) * cl0 + w[None, :] * target
    return t, mi, alpha, w, cl0, target, new, rows, a_end, sorted(curves)


def main():
    cases = json.load(open(os.path.join(D, 'cfd_lrn1015.json')))['cases']
    tunnel = json.load(open(os.path.join(D, 'lrn1015_tunnel.json')))['cases']
    t, mi, alpha, w, cl0, target, new, rows, a_end, res = build(cases, tunnel)
    print('CFD curves at Reynolds numbers %s, last common angle %.0f deg; blend from %.1f deg (ramp %.1f deg), back to the table over %.1f deg after the last angle' % (
        [r / 1e6 for r in res], a_end, ALPHA_S, RAMP, TAIL))
    for k, rw in enumerate(rows):
        i0 = int(np.argmin(abs(alpha - ALPHA_S)))
        top0, top1 = int(np.argmax(cl0[k])), int(np.argmax(new[k]))
        post = new[k][top1:][alpha[top1:] <= a_end]
        print('Re %4.1f M: tunnel max %.3f, CFD max %.3f at %.1f deg, offset %+.3f at the start and %+.3f at the peak; table max %.3f at %.1f deg -> new max %.3f at %.1f deg; '
              'steepest slope from %.1f deg to the peak %.3f /deg (table %.3f); lowest lift to %g deg %.3f' % (
                  rw['re'] / 1e6, rw['tunnel_max'], rw['cfd_max'], rw['cfd_peak_deg'], rw['offset_start'], rw['offset_peak'], cl0[k][top0], alpha[top0], new[k][top1],
                  alpha[top1], ALPHA_S, float(np.max(np.diff(new[k][i0:top1 + 1]) / 0.5)), float(np.max(np.diff(cl0[k][i0:top0 + 1]) / 0.5)) if top0 > i0 else 0.0, a_end, float(post.min())))
    if '--write' in sys.argv:
        json.dump(dict(mach=MACH, alpha_s=ALPHA_S, ramp=RAMP, tail=TAIL, alpha_end=a_end, alpha=alpha.tolist(), weight=[round(float(x), 5) for x in w],
                       target=[[round(float(x), 5) for x in row] for row in target], rows=rows,
                       notes='see fdm/cfd/stall_fit.py; applied by strips.section_tables() to the wing lift at the Mach number above'), open(OUT, 'w'))
        print('wrote', os.path.relpath(OUT))


if __name__ == '__main__':
    main()
