#!/usr/bin/env python3
"""The short period of NASA 872 from the ATTREX flights at 20 Hz, and what it can say of the static margin.

    python3 fdm/attrex_shortperiod.py [--model]       a few minutes; writes fdm/data/attrex_shortperiod.json

The 20 Hz records carry pitch attitude (PITCH, 0.01 deg), angle of attack (AOA), vertical acceleration (ZDOTDOT), dynamic pressure (Q,
hPa: not pitch rate) and Mach number. No control surface is recorded, so no transfer function can be taken; but in the turbulence of
any steady, level stretch an aircraft that is not held tightly shows its short period as a peak in the spectra of its pitch rate and
angle of attack. The pitch rate here is the derivative of PITCH.

Limits: docs/PLAN.md, "Five more ideas", Q1, written before this was run. A peak counts when it stands 3 times over the median of the
0.05 to 1 Hz band in a segment (steady, level, above 50,000 ft, at least 600 s: attrex.steady_segments); the test is meaningful if it is
seen in at least half of at least 20 segments. Reading: the measured peak within 30 % of the model's closed-loop peak: the margin is
supported; lower by 1.5 times or more: less margin than the model's, reported with what the frequency implies (margin goes with the
frequency squared); no peak: the idea fails. The centre of gravity and the laws are not changed under this.

What the peak depends on is also read: a bare airframe's short-period frequency goes with the square root of the dynamic pressure; a
flight control that schedules its gains with dynamic pressure, as ours does, holds the closed-loop frequency near constant. So the
exponent n in f ~ q^n, over the segments, says which the real aircraft is nearer. Reported, with no limit.

--model   also flies the model (the laws on, altitude and speed held) in MIL-F-8785C turbulence at the segments' conditions and reads
          the same spectra, and the bare airframe's short period (controls fixed) from the model's modes at the same trims.
"""
import glob
import json
import os
import sys

import numpy as np
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import attrex  # noqa: E402

OUT = os.path.join(HERE, 'data', 'attrex_shortperiod.json')
FS = 20.0
BAND = (0.05, 1.0)
M_FT = 3.28084


def peak(x, fs=FS, nperseg=2048):
    """The highest peak of the spectrum in the band: frequency, its height over the band's median, the half-power width over its frequency."""
    f, P = signal.welch(signal.detrend(x), fs=fs, nperseg=nperseg, noverlap=nperseg // 2)
    band = (f >= BAND[0]) & (f <= BAND[1])
    fb, Pb = f[band], P[band]
    i = int(np.argmax(Pb))
    half = Pb[i] / 2.0
    lo, hi = i, i
    while lo > 0 and Pb[lo] > half:
        lo -= 1
    while hi < len(Pb) - 1 and Pb[hi] > half:
        hi += 1
    width = (fb[hi] - fb[lo]) / fb[i]
    return float(fb[i]), float(Pb[i] / np.median(Pb)), float(width)


def segments():
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, '..', 'refs', 'tracks', 'ATTREX-2011-2014', 'MMS-20Hz', '*.gz'))):
        d = attrex.load(path)
        attrex.derived(d)
        dec = {k: (v[::20] if isinstance(v, np.ndarray) else v) for k, v in d.items()}
        segs = [s for s in attrex.steady_segments(dec) if s['hp'] > 15240.0]
        t = d['t']
        for s in segs:
            k = (t >= s['start']) & (t <= s['end'])
            th, al, az, qd = d['PITCH'][k], d['AOA'][k], d['ZDOTDOT'][k], d['Q'][k]
            ok = np.isfinite(th) & np.isfinite(al)
            if ok.sum() < 4096 or ok.mean() < 0.95:
                continue
            th, al = th[ok], al[ok]
            q = np.gradient(th, 1 / FS)
            r = dict(file=os.path.basename(path)[15:23], start=float(s['start']), dur=float(s['dur']), hp_ft=float(s['hp'] * M_FT), mach=float(s['M']),
                     tas=float(s['tas']), qbar_hpa=float(np.nanmean(qd)), pitch=float(np.mean(th)), aoa=float(np.mean(al)))
            for name, x in (('q', q), ('alpha', al), ('pitch', th)):
                r[name] = dict(zip(('f', 'ratio', 'width'), peak(x)))
            azk = az[np.isfinite(az)]
            if len(azk) >= 4096:
                r['az'] = dict(zip(('f', 'ratio', 'width'), peak(azk)))
            rows.append(r)
        print('%s: %d segments above 50,000 ft' % (os.path.basename(path)[15:23], len(segs)), flush=True)
    return rows


def model_peaks():
    """The model's closed-loop peak in turbulence at conditions on the measured ones, and its bare short period."""
    import harness as H
    import phase11_checks as P
    out = []
    f = H.load()
    for alt, mach, weight in ((50000, 0.58, 20000.0), (55000, 0.61, 17000.0), (60000, 0.60, 15000.0)):
        P.calm(f)
        t = H.trim(f, alt=alt, mach=mach, weight=weight)
        if not t['ok']:
            print('no trim at %d ft M%.2f %.0f lb' % (alt, mach, weight))
            continue
        modes = H.modes(f, t)['longitudinal']
        sp = max(modes, key=lambda e: abs(e))
        bare = dict(period=2 * np.pi / sp.imag if sp.imag else None, damping=-sp.real / abs(sp), f=sp.imag / (2 * np.pi))
        H.engage(f, t, pitch_mode=2, thrust_mode=3)
        P.turbulence(f, True, 15.0, 5)
        cols = {'theta': [], 'alpha': [], 'q': []}
        for i in range(int(1800 * H.HZ)):
            f.run()
            if i % int(H.HZ / FS) == 0:
                cols['theta'].append(f['attitude/theta-deg'])
                cols['alpha'].append(f['aero/alpha-deg'])
                cols['q'].append(np.degrees(f['velocities/q-rad_sec']))
        r = dict(alt=alt, mach=mach, weight=weight, qbar_hpa=float(f['aero/qbar-psf'] * 0.4788), bare=bare)
        for name in ('q', 'alpha', 'theta'):
            r[name] = dict(zip(('f', 'ratio', 'width'), peak(np.array(cols[name]))))
        out.append(r)
        print('model %d ft M%.2f %.0f lb: bare %.3f Hz (damping %.2f); closed loop in turbulence: q %.3f Hz (%.1fx), alpha %.3f Hz (%.1fx)' % (
            alt, mach, weight, bare['f'], bare['damping'], r['q']['f'], r['q']['ratio'], r['alpha']['f'], r['alpha']['ratio']), flush=True)
        P.calm(f)
    return out


def main():
    rows = segments()
    res = dict(segments=rows)
    n = len(rows)
    seen = [r for r in rows if r['q']['ratio'] >= 3.0 or r['alpha']['ratio'] >= 3.0]
    fq = np.array([r['q']['f'] for r in seen])
    print('\n%d segments above 50,000 ft; a peak 3 times over the median in %d (%.0f %%)' % (n, len(seen), 100 * len(seen) / max(n, 1)))
    if seen:
        print('pitch-rate peak frequency: median %.3f Hz, middle half %.3f to %.3f Hz, range %.3f to %.3f; half-power width / frequency %.2f (damping about %.2f)' % (
            np.median(fq), *np.percentile(fq, [25, 75]), fq.min(), fq.max(), np.median([r['q']['width'] for r in seen]), np.median([r['q']['width'] for r in seen]) / 2))
        qb = np.array([r['qbar_hpa'] for r in seen])
        lf, lq = np.log(fq), np.log(qb)
        n_exp = float(np.polyfit(lq, lf, 1)[0])
        m = np.array([r['mach'] for r in seen])
        print('dynamic pressure %.0f to %.0f hPa, Mach %.2f to %.2f; the exponent of f against q: %.2f (0.5 for a bare airframe, 0 for gains scheduled with q); correlation %.2f' % (
            qb.min(), qb.max(), m.min(), m.max(), n_exp, float(np.corrcoef(lq, lf)[0, 1])))
        res.update(n_segments=n, n_seen=len(seen), f_median=float(np.median(fq)), f_quartiles=[float(x) for x in np.percentile(fq, [25, 75])], exponent=n_exp)
    if '--model' in sys.argv:
        res['model'] = model_peaks()
    json.dump(res, open(OUT, 'w'), indent=1)
    print('wrote', os.path.relpath(OUT))


if __name__ == '__main__':
    main()
