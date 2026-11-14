#!/usr/bin/env python3
"""Phase 7 part C checks: navigators and their voting, the lost link, the landing without the engine.

    python3 fdm/phase7c_checks.py        about a minute

Limits: docs/FLIGHT-LAWS.md section 8, written before the laws were run. Everything here is PREDICTED: there is no
measurement of the real aircraft's contingency behaviour to compare with, except that the 2017 loss happened.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H                 # noqa: E402
import mission                      # noqa: E402
import missionmgr as MM             # noqa: E402
import phase7b_checks as B          # noqa: E402

NM = 6076.1
COURSE = 40.0
ELEV = 2300.0
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))


def report(tag, name, detail):
    rows.append((tag, name, 'reported', detail))


def healthy(f):
    """All four navigators on and right, the miscompare flag cleared."""
    for k in NAV_RESET:
        f[k] = NAV_RESET[k]
    f['nav/miscompare'] = 0


def cruise(f, **nav):
    healthy(f)
    t = H.trim(f, alt=60000, mach=0.6, weight=15000)
    H.engage(f, t, pitch_mode=2, thrust_mode=3, roll_mode=1)
    for k, v in nav.items():
        f['nav/' + k.replace('_', '-')] = v
    return t


NAV_RESET = {'nav/%s-on' % n: 1 for n in ('kna', 'knb', 'lna', 'lnb')}
NAV_RESET.update({'nav/%s-%s-error-deg' % (n, a): 0 for n in ('kna', 'knb', 'lna', 'lnb') for a in ('roll', 'pitch')})


def fly_nav(f, seconds, hook=None):
    log = {k: [] for k in ('t', 'phi', 'theta', 'vroll', 'vpitch', 'alt', 'mis')}
    for i in range(int(seconds * H.HZ)):
        if hook:
            hook(i / H.HZ)
        f.run()
        for k, p in zip(log, ('simulation/sim-time-sec', 'attitude/phi-deg', 'attitude/theta-deg', 'nav/roll-deg', 'nav/pitch-deg',
                              'position/h-sl-ft', 'nav/miscompare')):
            log[k].append(f[p])
    log = {k: np.array(v) for k, v in log.items()}
    log['t'] = np.arange(len(log['t'])) / H.HZ
    return log


def navigators(f):
    # N1: healthy, through a 40 deg heading change
    for label, off in (('four on', {}), ('two on (Kearfotts off)', dict(kna_on=0, knb_on=0))):
        cruise(f, **off)
        f['ap/heading-cmd-deg'] = f['attitude/psi-deg'] + 40.0
        log = fly_nav(f, 90)
        e = max(np.abs(log['vroll'] - log['phi']).max(), np.abs(log['vpitch'] - log['theta']).max())
        add('N1', 'healthy, %s' % label, e <= 0.01 and f['nav/miscompare'] == 0,
            'voted roll and pitch within %.4f deg of the truth through a turn to %.1f deg of bank' % (e, np.abs(log['phi']).max()))
    # N2: the 2017 case
    cruise(f, kna_on=0, knb_on=0)

    def ramp(t):
        f['nav/lna-roll-error-deg'] = min(30.0, max(0.0, (t - 5.0) * 10.0))
    log = fly_nav(f, 120, ramp)
    flagged = log['t'][np.argmax(log['mis'] > 0)] if (log['mis'] > 0).any() else float('inf')
    after = log['t'] >= 5.0                     # from the failure on: the first seconds are the engagement settling
    add('N2', 'the 2017 case: one of two ramps to 30 deg', np.abs(log['phi'][after]).max() < 5 and flagged - 5.3 <= 1.0 and np.abs(log['alt'] - log['alt'][0]).max() <= 100,
        'bank stays within %.2f deg after the failure (the vote is up to %.1f deg out until the two disagree by 3); miscompare %.2f s after the error passed 3 deg; '
        'height within %.1f ft over two minutes (the real aircraft reached 152 deg)' % (
            np.abs(log['phi'][after]).max(), np.abs(log['vroll'] - log['phi']).max(), flagged - 5.3, np.abs(log['alt'] - log['alt'][0]).max()))
    # the same in a turn: the reference is the turn rate, so it must pick the right one while banked too
    cruise(f, kna_on=0, knb_on=0)
    f['ap/heading-cmd-deg'] = f['attitude/psi-deg'] + 90.0
    log = fly_nav(f, 150, lambda t: f.__setitem__('nav/lnb-roll-error-deg', -min(30.0, max(0.0, (t - 40.0) * 10.0))))
    k = log['t'] > 38
    report('N2', 'the same failure during a turn', 'bank between %.1f and %.1f deg after the failure (limit 12.9 at this height); voted roll within %.2f deg of the truth; height within %.0f ft' % (
        log['phi'][k].min(), log['phi'][k].max(), np.abs(log['vroll'] - log['phi'])[k].max(), np.abs(log['alt'] - log['alt'][0]).max()))
    # N3: one of four steps to 60 deg
    cruise(f)
    log = fly_nav(f, 60, lambda t: f.__setitem__('nav/knb-roll-error-deg', 60.0 if t > 5 else 0.0))
    after = log['t'] >= 5.0
    add('N3', 'one of four steps to 60 deg', np.abs(log['phi'][after]).max() < 2, 'bank within %.3f deg after the step; the vote stays within %.4f deg of the truth' % (
        np.abs(log['phi'][after]).max(), np.abs(log['vroll'] - log['phi']).max()))
    # N4: a common error
    cruise(f, kna_on=0, knb_on=0)

    def both(t):
        f['nav/lna-roll-error-deg'] = f['nav/lnb-roll-error-deg'] = min(30.0, max(0.0, (t - 5.0) * 10.0))
    log = fly_nav(f, 120, both)
    report('N4', 'both of two wrong the same way (expected to fail)', 'bank goes to %.1f deg and stays (the error is 30 deg); no miscompare: %s; height changes by %.0f ft. '
           'No voting survives a common error' % (log['phi'][np.argmax(np.abs(log['phi']))], 'none raised' if not (log['mis'] > 0).any() else 'raised',
                                                 np.abs(log['alt'] - log['alt'][0]).max()))


def unit(deg):
    return np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg))])


def fly_plan(f, mgr, hours, hook=None, tail=0.0):
    keys = H.AP_LOG + (('item', None),)
    log = {k: [] for k, _ in keys}
    t0 = f['simulation/sim-time-sec']
    extra = None
    for i in range(int(hours * 3600 * H.HZ)):
        if hook:
            hook(i / H.HZ)
        mgr.step()
        if mgr.done:
            extra = i if extra is None else extra
            if i - extra > tail * H.HZ:
                break
        if not f.run():
            break
        if i % 12 == 0:
            for k, p in keys:
                log[k].append(mgr.i if p is None else f[p])
    log = {k: np.array(v) for k, v in log.items()}
    log['t'] = log['t'] - t0
    return log, t0


def lost_link(f):
    fld = MM.Field(34.9, -117.88, ELEV)
    u, r = unit(COURSE), unit(COURSE + 90.0)
    P = lambda a, b=0.0: fld.ll(*(a * u + b * r))
    start = P(10 * NM)
    t = H.trim(f, alt=20000.0, weight=22000.0, lat=start[0], lon=start[1], psi=COURSE, terrain=ELEV, **mission.schedule(20000.0))
    H.engage(f, t, pitch_mode=2, thrust_mode=3, speed_schedule=1)
    plan = [dict(kind='route', points=[P(25 * NM) + (20000.0,), P(25 * NM, 25 * NM) + (20000.0,), P(60 * NM, 60 * NM) + (20000.0,)])]
    home = [dict(kind='route', points=[P(-16 * NM) + (6500.0,)]), dict(kind='land', fix=P(-16 * NM), aim=P(0), elev=ELEV)]
    mgr = MM.Manager(f, plan, lost_link=home)
    f['ap/link-monitor'] = 1
    st = dict(cut=None)

    def uplink(t):
        if st['cut'] is None and mgr.k >= 1 and f['ap/leg-togo-ft'] < 15 * NM:
            st['cut'] = f['simulation/sim-time-sec']
        if st['cut'] is None:
            f['ap/link-last-sec'] = f['simulation/sim-time-sec']
    log, t0 = fly_plan(f, mgr, 2.0, uplink)
    f['ap/link-monitor'] = 0
    left = [tt for tt, e in mgr.events if e.startswith('LINK LOST')]
    delay = left[0] - st['cut'] if left and st['cut'] else float('inf')
    add('L1', 'link lost on the second leg', abs(delay - 30.0) <= 1.0 and mgr.done,
        'the last uplink %.1f min into the flight; the aircraft left the plan %.1f s later and %s' % (
            (st['cut'] - t0) / 60 if st['cut'] else -1, delay, 'landed, %.0f min after that' % ((log['t'][-1] + t0 - left[0]) / 60) if mgr.done else 'did not finish'))
    k = log['item'] == 2
    n0 = len(B.rows)
    if k.any():
        B.judge_landing({key: val[k] for key, val in log.items()}, 'landing')
    for tag, name, ok, detail in B.rows[n0:]:
        add('L1', 'after the lost link, %s (part B\'s %s)' % (name.split(': ')[-1], tag), ok, detail)
    return mgr


def engine_out(f, tag, alt, dist_nm, weight=21000.0):
    fld = MM.Field(34.9, -117.88, ELEV)
    away = COURSE + 70.0
    ua = unit(away)
    start, far = fld.ll(*(dist_nm * NM * ua)), fld.ll(*((dist_nm + 400) * NM * ua))
    other = fld.ll(*((dist_nm + 150) * NM * ua))
    t = H.trim(f, alt=alt, weight=weight, lat=start[0], lon=start[1], psi=away, terrain=ELEV, **mission.schedule(alt))
    H.engage(f, t, pitch_mode=2, thrust_mode=3, speed_schedule=1)
    f['engine/failed'] = 0
    sites = [dict(aim=other, course=90.0, elev=ELEV, name='the far runway'), dict(aim=fld.ll(0, 0), course=COURSE, elev=ELEV, name='home')]
    mgr = MM.Manager(f, [dict(kind='route', points=[far + (alt,)])], sites=sites)
    log, t0 = fly_plan(f, mgr, 3.0, lambda t: f.__setitem__('engine/failed', 1.0 if t > 10 else 0.0), tail=120.0)
    f['engine/failed'] = 0
    it = mgr.plan[-1]
    name = 'engine stopped at %.0f ft, %d nmi out, flying away' % (alt, dist_nm)
    if not (log['mains'] > 0).any() or it.get('site', {}).get('name') != 'home':
        add(tag, name, False, 'no landing at home: ' + '; '.join(e for _, e in mgr.events[-4:]))
        return mgr
    i = int(np.argmax(log['mains'] > 0))
    past, sink, xt = -log['togo'][i], -log['hdot'][i - 1] * 0.3048, log['xt'][i]
    roll = np.abs(log['xt'][i:]).max()
    add(tag, name, -500 <= past <= 5000 and sink < 2.0 and abs(xt) <= 30 and mgr.done and log['vg'][-1] < 1.0 and roll <= 50,
        'touches down %.0f ft past the aiming point, sinking %.2f m/s at %.1f KEAS and %.1f deg of pitch, %.1f ft off the centreline; stops (%.1f kt) within %.1f ft of it, '
        '%.1f min after the failure; thrust all the way %.0f lbf' % (past, sink, log['keas'][i], log['theta'][i], abs(xt), log['vg'][-1], roll, (log['t'][i] - 10) / 60,
                                                                      f['external_reactions/thrust/magnitude']))
    g = (log['t'] > 60) & (log['item'] == 1) & (log['spoiler'] < 0.01) & (np.abs(log['phi']) < 2)
    ratio = float(np.mean(log['vg'][g] * H.KT / -log['hdot'][g])) if g.any() else float('nan')
    report('E3', '%s: the planner\'s book' % tag, 'expected %.0f ft in hand at the entry point, had %.0f ft; glide ratio flown %.1f (the planner counts on %.0f); started final %.0f ft above the path' % (
        it['expected'], it['arrived'], ratio, MM.GLIDE_RATIO, it['final']))
    return mgr


def main():
    f = H.load()
    navigators(f)
    healthy(f)
    m1 = lost_link(f)
    m2 = engine_out(f, 'E1', 20000.0, 30)
    m3 = engine_out(f, 'E2', 50000.0, 100)
    # nothing in reach: the alert
    fld = MM.Field(34.9, -117.88, ELEV)
    t = H.trim(f, alt=20000.0, weight=21000.0, lat=36.5, lon=-117.88, psi=0.0, terrain=ELEV, **mission.schedule(20000.0))
    H.engage(f, t, pitch_mode=2, thrust_mode=3, speed_schedule=1)
    f['engine/failed'] = 1
    m4 = MM.Manager(f, [dict(kind='route', points=[(38.0, -117.88, 20000.0)])], sites=[dict(aim=fld.ll(0, 0), course=COURSE, elev=ELEV, name='home')])
    for _ in range(60):
        m4.step()
        f.run()
    f['engine/failed'] = 0
    add('E4', 'no runway in reach (96 nmi from 20,000 ft)', m4.alert == 'no runway in reach', 'alert: %s; glides towards the nearest' % m4.alert)
    add('G0', 'no go-around in the flights above (a go-around hides nothing)', MM.Manager.go_arounds == 0, '%d go-arounds' % MM.Manager.go_arounds)
    for tag, name, ok, detail in rows:
        print('%-3s %-52s %-8s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    judged = sum(1 for r in rows if r[2] != 'reported')
    print('\n%d checks, %d pass, %d miss; %d reported' % (judged, judged - miss, miss, len(rows) - judged))
    for label, m in (('lost link', m1), ('E1', m2), ('E2', m3)):
        print('\n%s, as the manager saw it:' % label)
        t0 = m.events[0][0]
        for t, text in m.events:
            print('  %7.1f min  %s' % ((t - t0) / 60, text))


if __name__ == '__main__':
    main()
