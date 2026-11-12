#!/usr/bin/env python3
"""Phase 8 part B checks: the alerts the aircraft raises (docs/GCS.md, limits B2).

    python3 fdm/phase8b_checks.py        about 20 s

Each alert is raised by its own condition in the flight model and must appear in /gcs/down/status within a second
(the angle-of-attack one within 4: it waits 3 s by design), and go when the condition ends. The station's side
(order, tones, acknowledging) is tested in GlobalHawk/gcs/tests/alerts.test.js.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcs_server as G              # noqa: E402
import harness as H                 # noqa: E402

PLAN = os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json')
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))


class Flight:
    def __init__(self, plan):
        self.sim = G.Sim(PLAN)
        self.f, self.ob = self.sim.f, self.sim.ob
        self.seq, self.beat, self.seen = 0, 0, set()
        self.cmd('plan', plan)
        self.cmd('start')

    def cmd(self, name, args=None):
        self.seq += 1
        self.sim.set('/gcs/up/cmd', json.dumps(dict(seq=self.seq, station='CHECK', name=name, args=args or {})))
        return json.loads(self.ob.down['/gcs/down/ack'])

    def alerts(self):
        return {a['id']: a for a in json.loads(self.ob.down['/gcs/down/status'])['alerts']}

    def run(self, seconds, beat=True, hook=None):
        for i in range(int(seconds * H.HZ)):
            if beat and i % H.HZ == 0:
                self.beat += 1
                self.sim.set('/gcs/up/heartbeat', self.beat)
            if hook:
                hook()
            self.sim.step()
            if i % 60 == 0:
                self.seen |= set(self.alerts())

    def until(self, cond, seconds, **kw):
        """Seconds until cond() holds, stepping a tenth of a second at a time; None if it never does."""
        t = 0.0
        while t < seconds:
            if cond():
                return t
            self.run(0.1, **kw)
            t += 0.1
        return t if cond() else None


def case(fl, i, raise_, clear=None, limit=1.0, wait=40.0, **kw):
    """Raise a condition, time the alert; end it, time the clearing."""
    raise_()
    up = fl.until(lambda: i in fl.alerts(), wait, **kw)
    a = fl.alerts().get(i, {})
    down = None
    if clear:
        clear()
        down = fl.until(lambda: i not in fl.alerts(), wait)
    ok = up is not None and up <= limit and (clear is None or (down is not None and down <= limit))
    add('B2', i, ok, '%s: "%s" (%s)%s' % ('raised after %.1f s' % up if up is not None else 'NOT RAISED', a.get('text', ''), a.get('action', ''),
                                          '' if clear is None else '; cleared after %.1f s' % down if down is not None else '; NOT CLEARED'))
    return a


def main():
    plan = json.load(open(PLAN))
    fl = Flight(plan)
    f = fl.f
    fl.run(480)
    add('B2', 'a normal flight, stand to 15,000 ft', not fl.seen and f['position/h-sl-ft'] > 15000, 'alerts seen in 8 minutes: %s; at %.0f ft' % (
        sorted(fl.seen) or 'none', f['position/h-sl-ft']))
    case(fl, 'off-plan', lambda: fl.cmd('hold'), lambda: fl.cmd('resume'))
    case(fl, 'nav-one', lambda: [fl.cmd('nav', dict(name=n, on=False)) for n in ('kna', 'knb', 'lna')],
         lambda: [fl.cmd('nav', dict(name=n, on=True)) for n in ('kna', 'knb', 'lna')])

    def disagree():
        fl.cmd('nav', dict(name='kna', on=False))
        fl.cmd('nav', dict(name='knb', on=False))
        f['nav/lna-roll-error-deg'] = 10.0

    def agree():
        f['nav/lna-roll-error-deg'] = 0.0
        fl.cmd('nav', dict(name='kna', on=True))
        fl.cmd('nav', dict(name='knb', on=True))
        f['nav/miscompare-reset'] = 1
        fl.run(0.05)
        f['nav/miscompare-reset'] = 0
    case(fl, 'nav-disagree', disagree, agree)
    tanks = [f['propulsion/tank[%d]/contents-lbs' % i] for i in range(6)]
    case(fl, 'fuel-low', lambda: [f.__setitem__('propulsion/tank[%d]/contents-lbs' % i, 200.0) for i in range(6)],
         lambda: [f.__setitem__('propulsion/tank[%d]/contents-lbs' % i, v) for i, v in enumerate(tanks)])

    def stress():
        f['limits/overstress'] = 1

    def unstress():
        f['limits/reset'] = 1
        fl.run(0.05)
        f['limits/reset'] = 0
    case(fl, 'structure', stress, unstress)
    # the angle-of-attack limit: by hand, stick held back
    stick = dict(v=0.0)

    def pull():
        f['fcs/throttle-cmd-norm'] = 0.3
        f['ap/manual'] = 1
        stick['v'] = -1.0

    def release():
        stick['v'] = 0.0
        f['ap/manual'] = 0
    hold = lambda: f.__setitem__('fcs/elevator-cmd-norm', stick['v'])
    at = dict(t=None)

    def reached():
        if at['t'] is None and f['ap/alpha-limit-deg'] - f['aero/alpha-deg'] < 0.3:
            at['t'] = f['simulation/sim-time-sec']
        return 'aoa' in fl.alerts()
    pull()
    up = fl.until(reached, 90, hook=hold)
    lag = f['simulation/sim-time-sec'] - at['t'] if at['t'] and up is not None else None
    a = fl.alerts().get('aoa', {})
    release()
    down = fl.until(lambda: 'aoa' not in fl.alerts(), 60, hook=hold)
    add('B2', 'aoa', lag is not None and 3.0 <= lag <= 4.0 + 0.6 and down is not None and down <= 30,
        '%s: "%s" (%s); cleared %s after the stick was released' % (
            'raised %.1f s after the angle of attack came within 0.3 deg of its limit' % lag if lag is not None else 'NOT RAISED', a.get('text', ''), a.get('action', ''),
            '%.1f s' % down if down is not None else 'NEVER'))
    fl.run(60)
    # the link: silence, then a resume
    t0 = f['simulation/sim-time-sec']
    up = fl.until(lambda: 'link' in fl.alerts(), 40, beat=False)
    a = fl.alerts().get('link', {})
    fl.cmd('resume')
    down = fl.until(lambda: 'link' not in fl.alerts(), 5)
    add('B2', 'link', up is not None and abs(up - 30) <= 1.6 and down is not None and down <= 1.0,
        'raised %.1f s into the silence: "%s" (%s); cleared %.1f s after a resume' % (up or -1, a.get('text', ''), a.get('action', ''), down if down is not None else -1))
    # the engine, with the runway in reach: the alert names the site
    a = case(fl, 'engine', lambda: f.__setitem__('engine/failed', 1))
    add('B2', 'engine: names the site', 'Demo field 04' in a.get('action', '') and 'no-site' not in fl.alerts(), a.get('action', ''))
    # and with nothing in reach
    far = copy.deepcopy(plan)
    far['sites'] = [dict(name='Far away', aim=[41.0, -110.0], course=90.0, elev_ft=4000.0)]
    fl2 = Flight(far)
    fl2.run(300)
    case(fl2, 'no-site', lambda: fl2.f.__setitem__('engine/failed', 1))
    for tag, name, ok, detail in rows:
        print('%-3s %-36s %-5s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))


if __name__ == '__main__':
    main()
