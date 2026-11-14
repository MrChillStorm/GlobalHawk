#!/usr/bin/env python3
"""The CFD's rise of section drag with Mach number, as a correction to the wing's drag table: python3 fdm/cfd/wave_drag.py

For each Mach number above the reference (0.45) and each lift coefficient up to that Mach number's attached maximum:

    d(M, cl) = [CFD cd(M, cl) - CFD cd(0.45, cl)] - [table cd(M, cl) - table cd(0.45, cl)]       at Reynolds 1.5 million

the table being NeuralFoil's as it came (strips.CD_WAVE off). Only differences between Mach numbers in the same solver are used: its absolute drag is fully turbulent
and about twice the tunnel's. The correction goes into fdm/data/cfd_wave_drag.json, which strips.section_tables() adds to the wing's drag at Mach above 0.45. Limits:
docs/PLAN.md, "Wave drag from the CFD". Cases count when their density residual is under -4 and their lift spread under 0.01.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import strips as S  # noqa: E402

D = os.path.join(HERE, '..', 'data')
OUT = os.path.join(D, 'cfd_wave_drag.json')
REF = 0.45
RE = 1.5e6
MACHS = (0.55, 0.60, 0.65, 0.70)
CL = np.arange(0.20, 1.5001, 0.05)
# Rule A: a case counts when its density residual is under -4 and its lift spread under 0.01 (the first rule, docs/PLAN.md "Wave drag from the CFD", limit (a)).
# Rule B (the default, docs/PLAN.md: "a second deviation"): the lift spread under 0.01 alone, the residual listed and not used, and a lift is supported only where the
# used cases at both Mach numbers bracket it with neighbours at most MAXGAP apart in lift. `--rule A` reproduces the first; `--out PATH` writes elsewhere.
RULE = 'A' if '--rule' in sys.argv and sys.argv[sys.argv.index('--rule') + 1] == 'A' else 'B'
MAXGAP = 0.30
if '--out' in sys.argv:
    OUT = sys.argv[sys.argv.index('--out') + 1]


def usable(r):
    return (r['res_rho'] < -4.0 and r['cl_spread'] < 0.01) if RULE == 'A' else r['cl_spread'] < 0.01


def bracketed(cl, x):
    """Where the sorted lifts of the used cases bracket x with neighbours at most MAXGAP apart (or x is at a case)."""
    ok = np.zeros(len(x), bool)
    for n, xi in enumerate(x):
        i = int(np.searchsorted(cl, xi - 1e-9))
        if i < len(cl) and abs(cl[i] - xi) < 1e-9:
            ok[n] = True
        elif 0 < i < len(cl):
            ok[n] = cl[i] - cl[i - 1] <= MAXGAP + 1e-9
    return ok


def curve(cases, mach, re=RE):
    c = sorted([r for r in cases if abs(r['mach'] - mach) < 1e-6 and abs(r['re'] - re) < 1], key=lambda r: r['alpha'])
    used, dropped = [], []
    for r in c:
        (used if usable(r) else dropped).append(r)
    return used, dropped


def attached(rows):
    """cl and cd of the cases up to the attached maximum of lift, with the lift rising."""
    cl = np.array([r['cl'] for r in rows])
    cd = np.array([r['cd'] for r in rows])
    top = int(np.argmax(cl))
    o = np.argsort(cl[:top + 1])
    return cl[:top + 1][o], cd[:top + 1][o], float(cl[top])


def table_cd(mach, cl):
    S.CD_WAVE = False
    try:
        t = S.section_tables()['wing']
    finally:
        S.CD_WAVE = True
    clt, cdt, _ = S.Section(t, mach)(S.ALPHAS, np.full(len(S.ALPHAS), RE))
    top = int(np.argmax(clt))
    o = np.argsort(clt[:top + 1])
    return np.interp(cl, clt[:top + 1][o], cdt[:top + 1][o])


def main():
    cases = json.load(open(os.path.join(D, 'cfd_lrn1015.json')))['cases']
    base_rows, dropped = curve(cases, REF)
    if len(base_rows) < 4:
        sys.exit('no usable cases at Mach %.2f' % REF)
    bcl, bcd, bmax = attached(base_rows)
    print('Mach %.2f (reference): %d cases used, %d dropped, attached maximum lift %.3f' % (REF, len(base_rows), len(dropped), bmax))
    out = dict(reference_mach=REF, reynolds=RE, cl=[round(float(x), 3) for x in CL], mach=[], d=[], attached_max=[], notes='see fdm/cfd/wave_drag.py')
    for m in MACHS:
        rows, drop = curve(cases, m)
        if len(rows) < 4:
            print('Mach %.2f: %d cases used, %d dropped: not enough, skipped' % (m, len(rows), len(drop)))
            continue
        cl, cd, top = attached(rows)
        k = (CL <= min(top, bmax) + 1e-9)
        d = np.zeros(len(CL))
        cfd_inc = np.interp(CL[k], cl, cd) - np.interp(CL[k], bcl, bcd)
        tab_inc = table_cd(m, CL[k]) - table_cd(REF, CL[k])
        d[k] = cfd_inc - tab_inc
        d[~k] = d[k][-1]                                  # past the attached range of either: the last value held
        # where the CFD has cases at this Mach number and at the reference: between the lowest lift of either and the attached maximum.
        # Below the lowest case the correction is the value at it, held (np.interp's clamp): not a CFD result, and listed as such.
        lo = max(cl.min(), bcl.min())
        sup = (CL >= lo - 1e-9) & k
        if RULE == 'B':
            sup &= bracketed(cl, CL) & bracketed(bcl, CL)
            if not sup.any():
                print('Mach %.2f: no lift is bracketed by used cases at both Mach numbers, skipped' % m)
                continue
            d = np.interp(CL, CL[sup], (cfd_inc - tab_inc)[sup[k]])        # held at the nearest supported lift beyond it
            lo = float(CL[sup].min())
            print('Mach %.2f: used cases at alpha %s (lift %s); supported lifts %.2f to %.2f%s' % (
                m, [r['alpha'] for r in rows], [round(r['cl'], 2) for r in rows], CL[sup].min(), CL[sup].max(),
                '' if sup[(CL >= CL[sup].min() - 1e-9) & (CL <= CL[sup].max() + 1e-9)].all() else ', with a gap: ' + str([round(float(x), 2) for x in CL[(CL >= CL[sup].min()) & (CL <= CL[sup].max()) & ~sup]])))
        rise = np.full(len(CL), np.nan)
        rise[sup] = cfd_inc[sup[k]]
        out.setdefault('cfd_rise', []).append([None if not np.isfinite(x) else round(float(x), 6) for x in rise])
        out.setdefault('lowest_supported_cl', []).append(round(float(lo), 3))
        out['mach'].append(m)
        out['d'].append([round(float(x), 6) for x in d])
        out['attached_max'].append(round(top, 3))
        print('Mach %.2f: %d cases used, %d dropped, attached maximum %.3f; correction at cl 0.4 / 0.6 / 0.8 / 0.95: %s counts (CFD rise %s, table rise %s)' % (
            m, len(rows), len(drop), top, ' / '.join('%+.0f' % (1e4 * np.interp(c, CL, d)) for c in (0.4, 0.6, 0.8, 0.95)),
            ' / '.join('%+.0f' % (1e4 * (np.interp(c, cl, cd) - np.interp(c, bcl, bcd))) for c in (0.4, 0.6, 0.8, 0.95)),
            ' / '.join('%+.0f' % (1e4 * float(np.ravel(table_cd(m, np.array([c])) - table_cd(REF, np.array([c])))[0])) for c in (0.4, 0.6, 0.8, 0.95))))
    # smooth in Mach: the correction must not fall as Mach rises at the same lift
    dd = np.array(out['d'])
    bad = [(out['mach'][i + 1], float(CL[j])) for i in range(len(dd) - 1) for j in range(len(CL)) if dd[i + 1, j] < dd[i, j] - 5e-4]
    print('non-monotonic in Mach (a fall of more than 5 counts) at %d of %d points%s' % (len(bad), dd.size - dd.shape[1], (': %s' % bad[:6]) if bad else ''))
    out['non_monotonic_points'] = len(bad)
    # the same question asked of the CFD's own rise (what the rule was meant to catch: a solver or mesh artefact shows as the drag at fixed lift falling as Mach rises);
    # the correction above also carries the table's own rise, which is irregular at Mach 0.7 where the table's wave drag is extreme
    rise = np.array([[np.nan if x is None else x for x in r] for r in out['cfd_rise']])
    falls = [(out['mach'][i + 1], float(CL[j])) for i in range(len(rise) - 1) for j in range(len(CL))
             if np.isfinite(rise[i, j]) and np.isfinite(rise[i + 1, j]) and rise[i + 1, j] < rise[i, j] - 2e-4]
    steps = int(sum(np.isfinite(rise[i, j]) and np.isfinite(rise[i + 1, j]) for i in range(len(rise) - 1) for j in range(len(CL))))
    print('the CFD\'s own rise falls with Mach (more than 2 counts) at %d of %d supported points%s; lowest supported lift by Mach: %s' % (
        len(falls), steps, (': %s' % falls[:6]) if falls else '', dict(zip(out['mach'], out['lowest_supported_cl']))))
    out['cfd_rise_falls'] = len(falls)
    out['cfd_rise_points'] = steps
    out['rule'] = RULE
    if RULE == 'B' and falls:
        print('rule B (c\'): the CFD\'s own rise falls with Mach; NOT written')
        return
    json.dump(out, open(OUT, 'w'), indent=1)
    print('rule %s: wrote %s' % (RULE, os.path.relpath(OUT)))


if __name__ == '__main__':
    main()
