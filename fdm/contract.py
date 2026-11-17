#!/usr/bin/env python3
"""Each task's contract with the next, checked on a recorded flight: which task broke what it had to hand over, first.

    python3 fdm/contract.py FLIGHT.csv PLAN.json

The idea is the MV-22B's (~/git/V-22/docs/FLIGHT-LAWS.md, "Contracts"): a task states what it must hand over to the next, so a bad landing points at the
first task to break its own, and that is the task that needs fixing; a go-around or a later task's recovery never hides it. The flight is a recording from
the FlightGear recorders (the scratchpad's approachrec.py family: columns t, lat, lon, alt, wh, xt, psi, phi, beta, kcas, target, hdot, theta, togo, mains,
lm, flare, gerrft, tphase) and the plan that was flown (JSON: field, items). The limits are the ones written in docs/PLAN.md (M5b, M7, M8, P5, the
entry contract) and, where none was written, mine; they are in CONTRACTS below, one line each. Every contract is reported, pass or MISS, in the order the
tasks hand over; "first broken" is the earliest MISS in time.
"""
import csv
import json
import math
import wgs84 as WG                 # the one earth model: WGS84's tangent plane (fdm/wgs84.py)
import sys

import numpy as np

NM = 6076.1

# (task handing over, to whom, what is measured, limit, where the limit comes from)
CONTRACTS = {
    'takeoff.line': ('Takeoff', 'Climb', 'distance off the centreline on the roll and at lift-off', 15.0, 'ft; M3 (within 15 ft; the flights of 2026-11-14 were within 3.5 ft in calm air)'),
    'takeoff.climbout': ('Takeoff', 'Climb', 'distance off the line 10 s after lift-off', 40.0, 'ft; mine: the crab has to be on by then'),
    'turn.line': ('Turn', 'Leg', 'how far past the new line the arc ends', 150.0, 'ft; P5'),
    'route.entry': ('Route', 'Landing', 'height above the glide path at the landing fix (the entry contract)', None, 'ft; fdm/missionmgr.py entry_limit: 0.8 of what the capture takes at the weight'),
    'route.line': ('Route', 'Landing', 'distance off the final\'s line where the landing begins', 150.0, 'ft; mine'),
    'final.gate': ('Final', 'Flare', 'off the line, off the path, off the speed at the flare gate', None, 'ft, ft, kt: 10, 12 and 3; M5b and M5, mine for the line; and the stabilised-approach gate above it (a missed approach is this contract broken)'),
    'flare.touchdown': ('Flare', 'Touchdown', 'sink, pitch, line and heading at the first wheel', None, 'M7 (0.3 to 1.2 m/s, 1.5 to 3.5 deg), 15 ft, 5 deg'),
    'rollout.line': ('Rollout', 'Stop', 'largest distance off the line from touchdown to 15 kt', 15.0, 'ft; M8'),
}


def load(path):
    rows = list(csv.DictReader(open(path)))

    def col(k):
        return np.array([float(r[k]) if r.get(k) not in ('', None) else float('nan') for r in rows])
    return rows, col


def main():
    path, plan_path = sys.argv[1], sys.argv[2]
    rows, col = load(path)
    plan = json.load(open(plan_path))
    t = col('t')
    t0 = t[0]
    wh, xt, psi, phi, kcas, tgt = col('wh'), col('xt'), col('psi'), col('phi'), col('kcas'), col('target')
    mains, lm, flare, gerr, tph, hdot, theta, togo = col('mains'), col('lm'), col('flare'), col('gerrft'), col('tphase'), col('hdot'), col('theta'), col('togo')
    home = [plan['field']['lat'], plan['field']['lon']]

    def ne(la, lo):
        return np.array(WG.enu(home, (la, lo)))
    pos = np.array([ne(a, b) for a, b in zip(col('lat'), col('lon'))])
    items = plan['items']
    takeoff = next((i for i in items if i['kind'] == 'takeoff'), None)
    land = next(i for i in items if i['kind'] == 'land')
    route = [p for i in items if i['kind'] == 'route' for p in i['points']]
    course = lambda a, b: math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360
    turn = lambda a, b: (b - a + 180) % 360 - 180
    res = []                                         # (time s, key, ok, text)

    # ---- takeoff
    if takeoff is not None:
        hdg = course(ne(*takeoff['start']), ne(*takeoff['end']))
        lift = int(np.nonzero(wh > 1)[0][0])
        roll = np.abs(xt[10:lift])
        at_lift = abs(xt[lift])
        lim = CONTRACTS['takeoff.line'][3]
        res.append((t[lift] - t0, 'takeoff.line', max(roll.max() if len(roll) else 0.0, at_lift) <= lim,
                    'on the roll up to %.1f ft, at lift-off %.1f ft off the line (limit %.0f); heading %.1f at lift-off for a runway at %.1f' % (roll.max() if len(roll) else 0.0, at_lift, lim, psi[lift], hdg)))
        k10 = min(lift + int(10 / max(np.median(np.diff(t)), 1e-3)), len(t) - 1)
        lim = CONTRACTS['takeoff.climbout'][3]
        res.append((t[k10] - t0, 'takeoff.climbout', abs(xt[k10]) <= lim, '10 s after lift-off %.1f ft off the line (limit %.0f), at %.0f ft' % (abs(xt[k10]), lim, col('alt')[k10])))

    # ---- each turn between route legs: how far past the new line (P5's measure)
    chain = ([ne(*takeoff['end'])] if takeoff else []) + [ne(p[0], p[1]) for p in route] + [ne(*land['aim'])]
    air = int(np.nonzero(wh > 5)[0][0]) if (wh > 5).any() else 0
    for i in range(1, len(chain) - 1):
        c0, c1 = course(chain[i - 1], chain[i]), course(chain[i], chain[i + 1])
        d = turn(c0, c1)
        if abs(d) < 10:
            continue
        dn = np.array([math.cos(math.radians(c1)), math.sin(math.radians(c1))])
        rel = pos - chain[i]
        along, right = rel @ dn, rel @ np.array([-dn[1], dn[0]])
        legft = float(np.hypot(*(chain[i + 1] - chain[i])))
        near = (np.hypot(rel[:, 0], rel[:, 1]) < 12 * NM) & (along > -9 * NM) & (along < min(12 * NM, 0.5 * legft)) & (wh > 5) & (np.arange(len(t)) > air)
        came = np.cumsum(near & (np.abs(right) < 300.0)) > 0
        past = np.maximum(0.0, -np.sign(d) * right)
        sel = near & came
        if not sel.any():
            res.append((float('nan'), 'turn.line', False, 'corner %d (%+.0f deg): the aircraft never came within 300 ft of the new line' % (i, d)))
            continue
        k = int(np.nonzero(sel)[0][int(np.argmax(past[sel]))])
        lim = CONTRACTS['turn.line'][3]
        res.append((t[k] - t0, 'turn.line', past[sel].max() <= lim, 'corner %d (%+.0f deg): %.0f ft past the new line (limit %.0f)' % (i, d, past[sel].max(), lim)))

    # ---- a go-around in the recording is the route's contract broken: the status text says GO-AROUND while the aircraft circles, and the break is reported, not forgiven
    status = [r.get('status') or '' for r in rows]
    ga = [i for i, text in enumerate(status) if 'GO-AROUND' in text.upper()]
    if ga:
        res.append((t[ga[0]] - t0, 'route.entry', False, 'the go-around task took the aircraft at %.0f s and held it %.0f s (%s): the landing was not committed because the route did not hand over at the glide path' % (
            t[ga[0]] - t0, t[ga[-1]] - t[ga[0]], status[ga[0]][:90])))
    # ---- a missed approach is the final's contract with the flare broken (the stabilised-approach gate): the status text says MISSED APPROACH (or LANDING ABANDONED) while the aircraft climbs out and circles
    ma = [i for i, text in enumerate(status) if 'MISSED APPROACH' in text.upper() or 'LANDING ABANDONED' in text.upper()]
    if ma:
        res.append((t[ma[0]] - t0, 'final.gate', False, 'the missed approach took the aircraft at %.0f s and held it %.0f s (%s): the final did not hand over to the flare inside the gate (docs/FLIGHT-LAWS.md 5.6c)' % (
            t[ma[0]] - t0, t[ma[-1]] - t[ma[0]], status[ma[0]][:90])))
    # ---- route to landing: where the landing begins (landing mode on), judged on the entry contract
    on = np.nonzero(lm == 1)[0]
    if len(on):
        k = int(on[0])
        above = gerr[k]
        # the entry limit by the weight is the aircraft's own (missionmgr.entry_limit); a recording has no weight, so the contract is judged at its lightest: 400 ft at 10 nmi
        togo_nm = togo[k] / NM
        lim = 0.8 * 500.0 * max(0.0, min(togo_nm, 12.0) - 1.5) / 8.5
        clipped = above >= 2999.0
        res.append((t[k] - t0, 'route.entry', above <= lim, 'the landing began %s%.0f ft %s the glide path with %.1f nmi to go (the aircraft would take %.0f ft at the lightest weight)' % (
            '(clipped: at least) ' if clipped else '', abs(above), 'above' if above > 0 else 'under', togo_nm, lim)))
        fx = ne(*land['fix'])
        ax = ne(*land['aim'])
        fc = course(fx, ax)
        dn = np.array([math.cos(math.radians(fc)), math.sin(math.radians(fc))])
        off = abs((pos[k] - fx) @ np.array([-dn[1], dn[0]]))
        res.append((t[k] - t0, 'route.line', off <= CONTRACTS['route.line'][3], 'the landing began %.0f ft off the final\'s line (limit %.0f)' % (off, CONTRACTS['route.line'][3])))
    else:
        res.append((float('nan'), 'route.entry', False, 'the landing never began'))

    # ---- final to flare, at the flare's first sample
    fl = np.nonzero(flare == 1)[0]
    if len(fl):
        k = int(fl[0])
        bad = []
        if abs(xt[k]) > 10.0:
            bad.append('%.1f ft off the line' % abs(xt[k]))
        if abs(gerr[k]) > 12.0:
            bad.append('%.0f ft off the path' % abs(gerr[k]))
        if abs(kcas[k] - tgt[k]) > 3.0:
            bad.append('%.1f kt off the speed' % abs(kcas[k] - tgt[k]))
        if abs(phi[k]) > 2.0:
            bad.append('bank %.1f deg' % abs(phi[k]))
        res.append((t[k] - t0, 'final.gate', not bad, 'at the flare gate (%.0f ft): %s (limits 10 ft, 12 ft, 3 kt, 2 deg)' % (wh[k], ', '.join(bad) if bad else 'on the line %.1f ft, on the path %.1f ft, speed %.1f kt off, bank %.1f deg' % (abs(xt[k]), abs(gerr[k]), abs(kcas[k] - tgt[k]), abs(phi[k])))))
    else:
        res.append((float('nan'), 'final.gate', False, 'the flare never began'))

    # ---- touchdown
    td = np.nonzero((mains > 0) & (lm == 1))[0]
    if len(td):
        k = int(td[0])
        sink = -hdot[max(k - 1, 0)] * 0.3048
        hdg_rw = course(ne(*land['fix']), ne(*land['aim']))
        bad = []
        if not 0.3 <= sink <= 1.2:
            bad.append('sink %.2f m/s' % sink)
        if not 1.5 <= theta[k] <= 3.5:
            bad.append('pitch %.1f deg' % theta[k])
        if abs(xt[k]) > 15.0:
            bad.append('%.1f ft off the line' % abs(xt[k]))
        if abs(turn(hdg_rw, psi[k])) > 5.0:
            bad.append('heading %.1f deg off the runway' % abs(turn(hdg_rw, psi[k])))
        past = -togo[k]
        res.append((t[k] - t0, 'flare.touchdown', not bad, 'touchdown %.0f ft past the aiming point: %s' % (past, ', '.join(bad) if bad else 'sink %.2f m/s, pitch %.1f deg, %.1f ft off the line, heading %.1f deg off the runway' % (sink, theta[k], abs(xt[k]), abs(turn(hdg_rw, psi[k]))))))
        ro = np.abs(xt[k:])
        lim = CONTRACTS['rollout.line'][3]
        res.append((t[k] - t0, 'rollout.line', ro.max() <= lim, 'rollout up to %.1f ft off the line (limit %.0f)' % (ro.max(), lim)))
    else:
        res.append((float('nan'), 'flare.touchdown', False, 'no touchdown with the landing on'))

    # ---- the report
    res.sort(key=lambda r: (math.isnan(r[0]), r[0]))
    print('%-9s %-18s %-4s %s' % ('t, s', 'contract', '', 'measured'))
    for ts, key, ok, text in res:
        who, to, _, _, _ = CONTRACTS[key]
        print('%-9s %-18s %-4s %s -> %s: %s' % ('-' if math.isnan(ts) else '%.0f' % ts, key, 'ok' if ok else 'MISS', who, to, text))
    broken = [r for r in res if not r[2]]
    print()
    if not broken:
        print('every contract held')
        return
    ts, key, _, text = broken[0]
    who, to, what, _, _ = CONTRACTS[key]
    print('FIRST BROKEN: %s (handing over to %s), %s: %s' % (who, to, 'at %.0f s' % ts if not math.isnan(ts) else 'never reached', text))
    print('   the first in time is the first task to look at; the %d later break%s %s listed, each a task of its own (a later one is not hidden by an earlier one, and none by a go-around)' % (len(broken) - 1, '' if len(broken) == 2 else 's', 'is' if len(broken) == 2 else 'are'))
    for ts, key, _, text in broken[1:]:
        who, to, _, _, _ = CONTRACTS[key]
        print('   also: %s -> %s %s: %s' % (who, to, 'at %.0f s' % ts if not math.isnan(ts) else '', text))


if __name__ == '__main__':
    main()
