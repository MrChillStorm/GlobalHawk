#!/usr/bin/env python3
"""Cuts the wind an aircraft met on a final out of a FlightGear recording (fdm/fg_scenario.py's CSV), as a profile against the height over the runway, for the bench's replay (fdm/gustbench.py `replay=NAME`).

    python3 fdm/gustreplay.py RECORDING.csv NAME [--first]       writes fdm/out/gust/replay_NAME.json

The last landing of the flight (the second approach after a missed approach; --first: the first touchdown): the rows in landing mode under 990 ft of wheel height down to the touchdown. The total wind at the
aircraft (the flight model's, north, east and down, ft/s) is turned into the runway's axes by the course the flight was landing on: headwind (kt), the wind blowing to the left of the course (kt; the bench's
`xw`: from the right) and the updraught (kt); the profile is binned at 2 ft (the turbulence as the aircraft met it: a frozen wind against height).
"""
import csv
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def num(r, k):
    try:
        return float(r[k])
    except (KeyError, ValueError, TypeError):
        return float('nan')


def main():
    path, name = sys.argv[1], sys.argv[2]
    rows = list(csv.DictReader(open(path)))
    tds = [i for i, r in enumerate(rows) if num(r, 'mains') > 0 and num(r, 'lm') == 1]
    td = tds[0] if '--first' in sys.argv else next(i for i in reversed(tds) if num(rows[i], 'mains') > 0) if False else None
    # the last landing: the first touchdown after the last time the aircraft was above 990 ft in landing mode
    if '--first' in sys.argv:
        td = tds[0]
    else:
        above = [i for i, r in enumerate(rows) if num(r, 'lm') == 1 and num(r, 'wh') >= 999.0]
        td = next(i for i in tds if i > above[-1])
    whole = '--whole' in sys.argv
    if whole:
        # the whole glide: above 990 ft the wheel height reads 1,000, so the height is the MSL altitude less the offset measured between 900 and 985 ft of wheel height
        s0 = [r for r in rows[max(0, td - 4000):td + 1] if num(r, 'lm') == 1]
        off = float(np.nanmedian([num(r, 'alt') - num(r, 'wh') for r in s0 if 900.0 < num(r, 'wh') < 985.0]))
        seg = []
        for r in s0:
            h = num(r, 'wh') if num(r, 'wh') < 990.0 else num(r, 'alt') - off
            if h > 0:
                r = dict(r); r['wh'] = repr(h); seg.append(r)
    else:
        seg = [r for r in rows[max(0, td - 4000):td + 1] if num(r, 'lm') == 1 and 0 < num(r, 'wh') < 990.0]
    course = math.radians(np.nanmedian([num(r, 'legc') for r in seg]))
    a, x, v, h = [], [], [], []
    for r in seg:
        wn, we, wd = num(r, 'wnorth'), num(r, 'weast'), num(r, 'wdown')
        a.append(-(wn * math.cos(course) + we * math.sin(course)) / 1.68781)
        x.append((wn * math.sin(course) - we * math.cos(course)) / 1.68781)
        v.append(-wd / 1.68781)
        h.append(num(r, 'wh'))
    h, a, x, v = map(np.array, (h, a, x, v))
    edges = np.arange(0.0, (3000.0 if whole else 992.0), 2.0)
    centres, A, X, V = [], [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (h >= lo) & (h < hi)
        if m.any():
            centres.append(0.5 * (lo + hi)); A.append(float(a[m].mean())); X.append(float(x[m].mean())); V.append(float(v[m].mean()))
    # the last HT ft in time: a profile against height keeps one value for the last foot or two, where the aircraft spends its last seconds and where the wind's changes in time push it (docs/PLAN.md, "The bank at touchdown":
    # the flare drift of FlightGear's 36 kt flight, 13 ft in 3 s, was 3 ft offline); the bench's `rt=1` takes the wind from this series, in the time since the aircraft was HT ft over the runway
    HT = 15.0
    ix = [k for k, r in enumerate(rows[:td + 1]) if k >= td - 400 and num(r, 'lm') == 1 and 0 < num(r, 'wh') <= HT]
    if ix:
        i0 = ix[0]
        tl, ta, tx, tv = [], [], [], []
        for r in rows[i0:min(len(rows), td + 12)]:
            wn, we, wd = num(r, 'wnorth'), num(r, 'weast'), num(r, 'wdown')
            tl.append(num(r, 't') - num(rows[i0], 't'))
            ta.append(-(wn * math.cos(course) + we * math.sin(course)) / 1.68781)
            tx.append((wn * math.sin(course) - we * math.cos(course)) / 1.68781)
            tv.append(-wd / 1.68781)
    out = dict(source=os.path.basename(path), course_deg=math.degrees(course), agl=centres, a=A, x=X, v=V, **(dict(ht=HT, tl=tl, ta=ta, tx=tx, tv=tv) if ix else {}))
    dest = os.path.join(HERE, 'out', 'gust', 'replay_%s.json' % name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    json.dump(out, open(dest, 'w'))
    print('%s: %d rows of the landing, course %.1f deg; crosswind (to the left) %.1f kt at 900 ft, %.1f at 100 ft, %.1f at 5 ft; headwind %.1f, %.1f, %.1f; wrote %s' % (
        name, len(seg), math.degrees(course), np.interp(900, centres, X), np.interp(100, centres, X), np.interp(5, centres, X), np.interp(900, centres, A), np.interp(100, centres, A), np.interp(5, centres, A), dest))


if __name__ == '__main__':
    main()
