#!/usr/bin/env python3
"""The wing section's compressibility, against the tunnel and against XFOIL, and the exponent of strips.CM_MACH_K.

    python3 fdm/section_study.py [--xfoil] [--modes]

Always: the moment of the LRN 1015 in the tables (NeuralFoil, Prandtl-Glauert and its own transonic growth) at the
tunnel's three cases (TM 102840: Mach 0.2 and 0.6 at Re 1 million, Mach 0.6 at Re 2 million), for several K of
beta^-K; the K that makes the growth of the moment from Mach 0.2 to 0.6 equal the tunnel's mean; what each K does to
S1-S3 (the checks of phase4_checks.py).
--xfoil   also runs XFOIL 6.99 (the headless build in tools/xfoil-build, made as below) on the section at the same
          three cases and prints its moment at the tunnel's lift coefficients: an independent solver, Karman-Tsien
          compressibility, free transition with n_crit 9. XFOIL cannot be run past the first local sonic point, so at
          Mach 0.6 it gives a few points only; it is evidence for the trend, not a table.
          XFOIL 6.99 (web.mit.edu/drela/Public/web/xfoil/xfoil6.99.tgz, M. Drela, GPL), built here with gfortran, double
          precision, and its X11 plot library replaced by empty subroutines so it runs without a display:
              gfortran -O2 -fdefault-real-8 -std=legacy -w -c xfoil.f xpanel.f xoper.f xtcam.f xgdes.f xqdes.f xmdes.f xsolve.f
                  xbl.f xblsys.f xpol.f xplots.f pntops.f xgeom.f xutils.f modify.f blplot.f polplt.f aread.f naca.f spline.f
                  plutil.f iopol.f gui.f sort.f dplot.f profil.f userio.f frplot.f ntcalc.f   (from src/), osrc/osmap.f with
                  -ffixed-line-length-none and its OSFILE path set, osrc/getosfile.c, and one stubs.f holding an empty
                  SUBROUTINE for each plot call the linker reports missing (PLOT, NEWPEN, PLCHAR, ...); then link all.
--modes   also builds the model with the moment as NeuralFoil gave it (K = 1) and with a table held at its Mach 0.45
          values above that Mach, one table at a time, and prints the longitudinal modes of the bare airframe at the
          cruise: which table the unstable speed root comes from (the moment's: holding the lift's or the drag's leaves it).
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.optimize import brentq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import strips as S  # noqa: E402

D = os.path.join(HERE, 'data')
XFOIL = os.path.join(HERE, '..', 'tools', 'xfoil-build', 'xfoil')


def raw_wing():
    """The wing's table as NeuralFoil gave it: no exponent applied."""
    old = S.CM_MACH_K
    S.CM_MACH_K = 1.0
    try:
        return S.section_tables()['wing']
    finally:
        S.CM_MACH_K = old


def with_k(wing, k):
    t = copy.deepcopy(wing)
    beta = np.sqrt(1 - np.array(S.MACHS) ** 2)
    t['cm'] = (np.array(t['cm']) * (beta ** (1 - k))[:, None, None]).tolist()
    return t


def tunnel():
    return json.load(open(os.path.join(D, 'lrn1015_tunnel.json')))['cases']


def cm_means(wing):
    """Mean moment at the tunnel's own lift coefficients between 0.4 and 1.0, as phase 4's S2 reads it, per case."""
    out = {}
    for c in tunnel():
        cl, cd, cm = S.Section(wing, c['mach'])(S.ALPHAS, np.full(len(S.ALPHAS), c['reynolds']))
        top = int(np.argmax(cl))
        up = slice(int(np.argmin(np.abs(S.ALPHAS + 4))), top + 1)
        pts = [p for p in c['cm'] if 0.4 <= p[1] <= 1.0]
        out[(c['mach'], c['reynolds'])] = (float(np.mean([np.interp(p[1], cl[up], cm[up]) for p in pts])), float(np.mean([p[0] for p in pts])),
                                           float(cl[top]))
    return out


def fit(wing):
    def growth(k):
        o = cm_means(with_k(wing, k))
        return (np.mean([o[(0.6, 1e6)][0], o[(0.6, 2e6)][0]]) / o[(0.2, 1e6)][0]) - (np.mean([o[(0.6, 1e6)][1], o[(0.6, 2e6)][1]]) / o[(0.2, 1e6)][1])
    return brentq(growth, 0.0, 1.2)


def xfoil_cm():
    """XFOIL's moment at the tunnel's lift coefficients: {(mach, re): (mean cm, growth of its own points)}"""
    dat = os.path.join(D, 'lrn1015.dat')
    res = {}
    for c in tunnel():
        rows = []
        for a0, a1, da in ((0.0, 16.0, 0.5), (0.0, -6.0, -0.5)):
            with tempfile.TemporaryDirectory() as tmp:
                pol = 'polar.txt'          # XFOIL cuts longer file names
                cmds = ['LOAD %s' % dat, 'LRN1015', 'PANE', 'OPER', 'VISC %g' % c['reynolds'], 'MACH %g' % c['mach'], 'VPAR', 'N 9', '', 'ITER 400',
                        'PACC', pol, '', 'ALFA %g' % a0, 'ASEQ %g %g %g' % (a0, a1, da), 'PACC', '', 'QUIT']
                subprocess.run([XFOIL], input='\n'.join(cmds) + '\n', capture_output=True, text=True, timeout=600, cwd=tmp)
                if os.path.exists(os.path.join(tmp, pol)):
                    rows += [[float(x) for x in ln.split()[:7]] for ln in open(os.path.join(tmp, pol)).read().splitlines()[12:] if len(ln.split()) >= 7]
        rows.sort(key=lambda r: r[0])
        a, cl, cm = (np.array([r[i] for r in rows]) for i in (0, 1, 4))
        top = int(np.argmax(cl))
        pts = [p for p in c['cm'] if 0.4 <= p[1] <= 1.0 and p[1] <= cl[top]]
        res[(c['mach'], c['reynolds'])] = (float(np.mean([np.interp(p[1], cl[:top + 1], cm[:top + 1]) for p in pts])), len(pts), float(cl[top]), float(a[top]))
    return res


def modes_by_table():
    """The longitudinal modes at the cruise: the tables as NeuralFoil gave the moment (K = 1) with one table at a time held at
    its Mach 0.45 column above Mach 0.45, and the shipped model (K = strips.CM_MACH_K). Each is built from the strip model
    in this process (aerotables.sample) into a temporary data directory; the files in the repository are not touched."""
    import aerotables as A
    import harness as H
    shipped = S.CM_MACH_K
    for name, k, keys in (('K=1', 1.0, []), ('K=1, Cm held', 1.0, ['Cm']), ('K=1, CL held', 1.0, ['CL']), ('K=1, CD held', 1.0, ['CD']),
                          ('K=%g (shipped)' % shipped, shipped, [])):
        S.CM_MACH_K = k
        try:
            t = A.sample()
        finally:
            S.CM_MACH_K = shipped
        tmp = tempfile.mkdtemp(prefix='ghdata')
        for fn in os.listdir(D):
            if os.path.isfile(os.path.join(D, fn)):
                shutil.copy(os.path.join(D, fn), tmp)
        for key in keys:
            a = np.array(t[key])
            a[3:] = a[2]
            t[key] = a.tolist()
        json.dump(t, open(os.path.join(tmp, 'aero_tables.json'), 'w'))
        f = H.load_variant({'genghawk.D': tmp})
        tr = H.trim(f, alt=60000, mach=0.6, weight=15000)
        print('  %-18s %s' % (name, '; '.join(H.describe(e) for e in H.modes(f, tr)['longitudinal'])))
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    wing = raw_wing()
    print('moment at the tunnel\'s lift coefficients (0.4 to 1.0), tables with beta^-K and the tunnel:')
    print('  %-6s %s' % ('K', '   '.join('M%.1f Re%.0fM' % (m, r / 1e6) for m, r in [(0.2, 1e6), (0.6, 1e6), (0.6, 2e6)])))
    for k in (1.0, 0.8, 0.65, 0.5, 0.0):
        o = cm_means(with_k(wing, k))
        print('  %-6g %s' % (k, '   '.join('%.4f (%+.4f)' % (v[0], v[0] - v[1]) for v in o.values())))
    o = cm_means(wing)
    t = [v[1] for v in o.values()]
    print('  tunnel %s' % '   '.join('%.4f' % x for x in t))
    print('  growth from Mach 0.2 to 0.6 (mean of the two Re): tables %.3f, tunnel %.3f' % (
        np.mean([o[(0.6, 1e6)][0], o[(0.6, 2e6)][0]]) / o[(0.2, 1e6)][0], np.mean(t[1:]) / t[0]))
    k = fit(wing)
    print('K that gives the tunnel\'s growth: %.3f (strips.CM_MACH_K = %.2f)' % (k, S.CM_MACH_K))
    if '--xfoil' in sys.argv:
        if not os.path.exists(XFOIL):
            sys.exit('no XFOIL build at %s' % XFOIL)
        x = xfoil_cm()
        print('XFOIL 6.99 (Karman-Tsien, n_crit 9), moment at the tunnel\'s lift coefficients up to its own maximum:')
        for key, (cm, n, clmax, amax) in x.items():
            print('  Mach %.1f Re %.0fM: %.4f from %d points, XFOIL stops at CL %.2f, %.1f deg' % (key[0], key[1] / 1e6, cm, n, clmax, amax))
        print('  growth from Mach 0.2 to 0.6 at Re 1 million: %.3f' % (x[(0.6, 1e6)][0] / x[(0.2, 1e6)][0]))
    if '--modes' in sys.argv:
        print('longitudinal modes, controls fixed, 60,000 ft, Mach 0.6, 15,000 lb, with a table held at its Mach 0.45 column above:')
        modes_by_table()
