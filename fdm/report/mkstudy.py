#!/usr/bin/env python3
"""The data of the wing-tip and flare-drift studies for the report: python3 mkstudy.py  ->  results/lat_roll_loop.json, results/flare_drift.json

lat_roll_loop.json: the landing's roll loop, the old landing law (`law2`: no stiffer roll loop, no bank washout) against the present one (`law3`), flown on the same cases (fdm/latsweep.py,
LAT_FLAGS="--gs --auto": fdm/out/lat_on/SET.law2.jsonl and SET.law3.jsonl; the sets train, test and final differ in seeds and weights and nothing was chosen on `final`). Per set and law: the line at
the first wheel, the bank there, the hard landings, and the wing tips' lowest height from 15 ft of wheel height to 3 s after the first wheel, for the rigid structure and with the wing's bending.

flare_drift.json: the twelve FlightGear flights in a steady crosswind (fdm/fg_matrix.py, fdm/out/fg_matrix) and the six with the aim offset on (fdm/out/fg_matrix_aim), measured by fdm/flare_drift.py,
and the one-coefficient fit of the drift (drift = k x weight in 1,000 lb x crosswind).

The sources are in fdm/out (not committed): without them the JSON files already in results/ are kept.
"""
import glob
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FDM = os.path.join(HERE, '..')
R = os.path.join(HERE, 'results')
sys.path.insert(0, FDM)
SETS = (('train', 'design set'), ('test', 'fresh seeds'), ('final', 'confirmation set'))
LAWS = (('law2', 'old landing law'), ('law3', 'present law'))


def load(path):
    rows = {}
    for line in open(path):
        r = json.loads(line)
        rows[r['name']] = r
    return rows


def val(r, k, default=99.0):
    v = r.get(k)
    return default if v is None else float(v)


def stats(rows):
    keys = sorted(rows)
    x = np.array([abs(rows[k]['xt_td_ft']) for k in keys])
    sink = np.array([rows[k]['sink_ms'] for k in keys])
    phi = np.array([abs(val(rows[k], 'phi_td_deg', 0.0)) for k in keys])
    rig = np.array([val(rows[k], 'tip_min_ft') for k in keys])
    fl = np.array([val(rows[k], 'tip_min_flex3_ft') for k in keys])
    ftd = np.array([val(rows[k], 'flex_td_ft', np.nan) for k in keys])
    fmin = np.array([val(rows[k], 'flex_min_ft', np.nan) for k in keys])
    return dict(n=len(keys), line_mean=float(x.mean()), line_p95=float(np.percentile(x, 95)), line_over30=int((x > 30).sum()), hard=int((sink > 2).sum()), sink_mean=float(sink.mean()),
                bank_td_mean=float(phi.mean()), bank_td_max=float(phi.max()), rigid_le0=int((rig <= 0).sum()), rigid_lt05=int((rig < 0.5).sum()), rigid_min=float(rig.min()),
                flex_le0=int((fl <= 0).sum()), flex_lt05=int((fl < 0.5).sum()), flex_min=float(fl.min()), flex_median=float(np.median(fl)),
                flex_td_mean=float(np.nanmean(ftd)), flex_lowest=float(np.nanmin(fmin)),
                lists=dict(rigid=[round(float(v), 2) for v in rig], flex=[round(float(v), 2) for v in fl], bank=[round(float(v), 2) for v in phi]))


def lat_roll_loop():
    src = os.path.join(FDM, 'out', 'lat_on')
    need = [os.path.join(src, '%s.%s.jsonl' % (s, l)) for s, _ in SETS for l, _ in LAWS]
    if not all(os.path.exists(p) for p in need):
        print('lat_roll_loop: the flights are not in fdm/out/lat_on, results/lat_roll_loop.json kept')
        return
    out = {}
    for s, label in SETS:
        d = {l: load(os.path.join(src, '%s.%s.jsonl' % (s, l))) for l, _ in LAWS}
        keys = [k for k in d['law2'] if k in d['law3'] and 'tip_min_flex3_ft' in d['law2'][k] and 'tip_min_flex3_ft' in d['law3'][k]]
        if len(keys) != len(d['law2']):
            print('lat_roll_loop: %s has %d of %d flights with the bending tracked' % (s, len(keys), len(d['law2'])))
        out[s] = dict(label=label, **{l: stats({k: d[l][k] for k in keys}) for l, _ in LAWS})
        a = np.array([abs(d['law2'][k]['xt_td_ft']) - abs(d['law3'][k]['xt_td_ft']) for k in keys])
        out[s]['line_better'] = int((a > 0).sum())
        rng = np.random.default_rng(1)
        b = [rng.choice(a, len(a)).mean() for _ in range(10000)]
        out[s]['line_gain'] = [float(a.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]
    json.dump(out, open(os.path.join(R, 'lat_roll_loop.json'), 'w'))
    print('wrote results/lat_roll_loop.json', {s: (out[s]['law2']['n'], out[s]['law2']['flex_le0'], out[s]['law3']['flex_le0']) for s, _ in SETS})


def aim_coefficient():
    m = re.search(r'^FINAL_AIM_FT_PER_KT_KLB\s*=\s*([0-9.eE+-]+)', open(os.path.join(FDM, 'laws.py')).read(), re.M)
    return float(m.group(1)) if m else float('nan')


def flare_drift():
    import flare_drift as F
    plain = sorted(glob.glob(os.path.join(FDM, 'out', 'fg_matrix', '*.csv')))
    aimed = sorted(glob.glob(os.path.join(FDM, 'out', 'fg_matrix_aim', '*.csv')))
    if len(plain) < 12:
        print('flare_drift: the FlightGear recordings are not in fdm/out, results/flare_drift.json kept')
        return
    keep = ('name', 'weight', 'xw', 'hw', 'crab15', 'crab_td', 'beta15', 'beta_td', 'x40', 'x15', 'x_td', 'drift15', 'drift40', 'phi_td', 'keas', 'sink', 'ay2')
    rows = []
    for aim, paths in ((False, plain), (True, aimed)):
        for p in paths:
            r = F.analyse(p)
            if r:
                rows.append(dict({k: r[k] for k in keep}, aim=aim))
    base = [r for r in rows if not r['aim']]
    x = np.array([r['weight'] / 1000.0 * r['xw'] for r in base])
    d = np.array([r['drift15'] for r in base])
    k = float((x * d).sum() / (x * x).sum())
    loo = []
    for i in range(len(d)):
        m = np.arange(len(d)) != i
        ki = float((x[m] * d[m]).sum() / (x[m] * x[m]).sum())
        loo.append(d[i] - ki * x[i])
    fit = dict(k=k, n=len(d), rms=float(np.sqrt(np.mean((d - k * x) ** 2))), loo_rms=float(np.sqrt(np.mean(np.square(loo)))), loo_max=float(np.abs(loo).max()), aim_k=aim_coefficient())
    json.dump(dict(rows=rows, fit=fit), open(os.path.join(R, 'flare_drift.json'), 'w'))
    print('wrote results/flare_drift.json: %d flights, k %.4f, rms %.2f, leave-one-out %.2f ft' % (len(rows), k, fit['rms'], fit['loo_rms']))


if __name__ == '__main__':
    lat_roll_loop()
    flare_drift()
