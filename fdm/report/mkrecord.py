#!/usr/bin/env python3
"""The record flight's time history for the report's figure: python3 mkrecord.py [record.npz]  ->  results/record.json

record.npz is the output of fdm/scenario_record.py (OUT=...): one row a second. The history is kept every 2 minutes (every 15 s in the last hour, the descent), and the angle-of-attack
margin as its median and its least value in each half hour: the racetrack's turns take some of it (the bank is held to 0.5 deg short of the limit), and what matters is how little is left."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'record_altitude.npz')
D = np.load(src, allow_pickle=True)
names = [str(n) for n in D['names']]
a = D['a']
col = lambda n: a[:, names.index(n)]
t = (col('simulation/sim-time-sec') - float(D['t0'])) / 3600.0
alt, w, fuel = col('position/h-sl-ft'), col('inertia/weight-lbs'), col('fuel/total-lbs')
margin = col('ap/alpha-limit-deg') - col('aero/alpha-deg')
failed = col('engine/failed')
out_h = float(t[int(np.argmax(failed > 0))]) if np.any(failed > 0) else None
k = int(np.argmax(alt))
keep = np.zeros(len(t), bool)
keep[::120] = True
keep[t > t[-1] - 1.0] = False
keep[np.nonzero(t > t[-1] - 1.0)[0][::15]] = True
keep[-1] = True
# the least margin in each half hour, above 2,500 ft and not in the descent (the margin is large and means nothing there)
win = np.floor(t * 2).astype(int)
mm_t, mm, md = [], [], []
for u in np.unique(win):
    s = (win == u) & (alt > 20000) & ((t < out_h) if out_h else True)
    if s.sum() > 60:
        mm_t.append(float(t[s].mean()))
        mm.append(float(margin[s].min()))
        md.append(float(np.median(margin[s])))
json.dump(dict(t_h=[round(float(x), 4) for x in t[keep]], alt_ft=[round(float(x)) for x in alt[keep]], weight_lb=[round(float(x)) for x in w[keep]],
               margin_t_h=[round(x, 3) for x in mm_t], margin_min_deg=[round(x, 3) for x in mm], margin_median_deg=[round(x, 3) for x in md],
               record=dict(alt_ft=round(float(alt[k])), t_h=round(float(t[k]), 2), weight_lb=round(float(w[k])), fuel_lb=round(float(fuel[k]), 1)), engine_out_h=out_h, flight_h=round(float(t[-1]), 2)),
          open(os.path.join(HERE, 'results', 'record.json'), 'w'))
print('record.json: %d points, %d margin points; record %.0f ft at %.2f h; engine out %.2f h' % (keep.sum(), len(mm), alt[k], t[k], out_h or -1))
