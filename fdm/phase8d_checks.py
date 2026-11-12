#!/usr/bin/env python3
"""Phase 8 part D checks: stations, who has control, handover, and flying by hand through the link.

    python3 fdm/phase8d_checks.py        about 20 s

The aircraft's end, in the model, driven by the messages stations send (docs/GCS.md, limits S1-S4).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcs_server as G              # noqa: E402
import harness as H                 # noqa: E402

PLAN = os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json')
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))


class World:
    """The aircraft and any number of stations, each beating once a second unless silenced."""

    def __init__(self):
        self.sim = G.Sim(PLAN)
        self.f, self.ob = self.sim.f, self.sim.ob
        self.seq, self.beat = {}, 0
        self.silent = set()
        self.stick = {}                          # station -> (p, r, y, t, s), sent 20 times a second

    def cmd(self, station, name, args=None):
        self.seq[station] = self.seq.get(station, 0) + 1
        self.sim.set('/gcs/up/cmd', json.dumps(dict(seq=self.seq[station], station=station, name=name, args=args or {})))
        a = json.loads(self.ob.down['/gcs/down/ack'])
        return a['status'] == 'accepted', a['reason']

    def status(self):
        self.ob.status()
        return json.loads(self.ob.down['/gcs/down/status'])

    def run(self, seconds, stations=('LRE', 'MCE'), log=None):
        for i in range(int(seconds * H.HZ)):
            if i % H.HZ == 0:
                self.beat += 1
                for n, s in enumerate(stations):
                    if s not in self.silent:
                        self.sim.set('/gcs/up/heartbeat', '%s:%d' % (s, self.beat))
            if i % 6 == 0:
                for s, v in self.stick.items():
                    if s not in self.silent:
                        self.sim.set('/gcs/up/stick', json.dumps(dict(station=s, p=v[0], r=v[1], y=v[2], t=v[3], s=v[4])))
            self.sim.step()
            if log is not None:
                log.append([self.f[k] for k in ('attitude/theta-deg', 'attitude/phi-deg', 'aero/alpha-deg', 'ap/alpha-limit-deg', 'position/h-sl-ft')])


def main():
    w = World()
    f = w.f
    w.run(1.0, stations=('LRE',))
    w.run(1.0)
    ok1, _ = w.cmd('LRE', 'plan', json.load(open(PLAN)))
    ok2, why = w.cmd('MCE', 'start')
    c = w.status()['control']
    add('S1', 'the first station heard holds control', ok1 and not ok2 and 'LRE has control' in why and c['holder'] == 'LRE' and [s['name'] for s in c['stations']] == ['LRE', 'MCE'],
        'holder %s; stations heard %s; MCE\'s start refused: "%s"' % (c['holder'], [s['name'] for s in c['stations']], why))
    w.cmd('LRE', 'start')
    w.run(420)
    # ---- S2 handover
    r = []
    r.append(('offer to a station never heard', *w.cmd('LRE', 'control.offer', dict(to='XYZ'))))
    r.append(('accept with nothing offered', *w.cmd('MCE', 'control.accept')))
    o1 = w.cmd('LRE', 'control.offer', dict(to='MCE'))
    offered = w.status()['control']['offer_to']
    c1 = w.cmd('LRE', 'control.cancel')
    r.append(('accept after a cancel', *w.cmd('MCE', 'control.accept')))
    o2 = w.cmd('LRE', 'control.offer', dict(to='MCE'))
    r.append(('accept by a third station', *w.cmd('OPS', 'control.accept')))
    acc = w.cmd('MCE', 'control.accept')
    holder = w.status()['control']['holder']
    old = w.cmd('LRE', 'hold')
    new = w.cmd('MCE', 'hold')
    add('S2', 'handover: offer, cancel, offer, accept', o1[0] and offered == 'MCE' and c1[0] and o2[0] and acc[0] and holder == 'MCE' and all(not ok for _, ok, _ in r),
        'offered to %s, cancelled, offered again, accepted: holder %s; refused: %s' % (offered, holder, '; '.join('%s ("%s")' % (n, why) for n, _, why in r)))
    add('S2', 'after the handover', not old[0] and 'MCE has control' in old[1] and new[0], 'LRE\'s hold refused ("%s"); MCE\'s hold accepted' % old[1])
    w.cmd('MCE', 'resume')
    w.silent = {'LRE'}
    w.run(60)
    quiet = f['ap/link-lost'] == 0
    w.silent = {'MCE'}
    t0 = f['simulation/sim-time-sec']
    t = 0.0
    while f['ap/link-lost'] == 0 and t < 40:
        w.run(0.1)
        t += 0.1
    add('S2', 'the lost-link watch follows the holder', quiet and abs(t - 30) <= 1.5, 'the old holder silent for 60 s: %s; the new holder silent: lost link after %.1f s' % (
        'no lost link' if quiet else 'LOST LINK', t))
    # ---- S3 taking control
    w.run(5)
    s = w.status()
    took = w.cmd('LRE', 'control.take')
    res = w.cmd('LRE', 'resume')
    w.silent = set()
    w.run(3)
    again = w.cmd('MCE', 'control.take')
    add('S3', 'taking control', s['contingency'] == 'link' and took[0] and res[0] and w.status()['control']['holder'] == 'LRE' and not again[0] and 'being heard' in again[1],
        'with the link lost (contingency "%s") LRE takes control and its resume is done; MCE\'s take while LRE is heard is refused: "%s"' % (s['contingency'], again[1]))
    # ---- S4 by hand
    w.run(60)
    alt0 = f['position/h-sl-ft']
    wrong = w.cmd('MCE', 'manual', dict(mode=1))
    on = w.cmd('LRE', 'manual', dict(mode=1))
    thr = f['fcs/throttle-cmd-norm']
    w.run(2)
    th0 = f['attitude/theta-deg']
    w.stick = {'MCE': (-1.0, 1.0, 0.0, thr, 0.0)}
    w.run(3)
    watcher = f['fcs/elevator-cmd-norm'] == 0.0 and f['fcs/aileron-cmd-norm'] == 0.0      # the aircraft's stick inputs never moved
    th0 = f['attitude/theta-deg']
    w.stick = {'LRE': (-1.0, 0.0, 0.0, thr, 0.0)}
    w.run(3)
    dth = f['attitude/theta-deg'] - th0
    w.stick = {'LRE': (0.0, 0.5, 0.0, thr, 0.0)}
    w.run(15)
    bank, want = f['attitude/phi-deg'], 0.5 * f['ap/bank-command-limit-deg']
    w.stick = {'LRE': (-1.0, 0.0, 0.0, thr, 0.0)}
    log = []
    w.run(30, log=log)
    log = np.array(log)
    over = float((log[:, 2] - log[:, 3]).max())
    add('S4', 'by hand through the link', (not wrong[0]) and on[0] and watcher and dth >= 3.0 and abs(bank - want) <= 2.0 and over <= 0.5,
        'a watcher\'s manual refused ("%s") and its stick ignored: %s; full back stick 3 s: pitch %+.1f deg; half right stick: bank %.1f deg (half the limit is %.1f); '
        'full back stick 30 s: angle of attack %.2f deg over its limit at most' % (wrong[1], watcher, dth, bank, want, over))
    w.stick = {'LRE': (0.0, 0.0, 0.0, thr, 0.0)}
    w.run(20)
    h1 = f['position/h-sl-ft']
    off = w.cmd('LRE', 'manual', dict(mode=0))
    w.run(120)
    s = w.status()
    add('S4', 'back to automatic', off[0] and s['kind'] == 'hold' and abs(f['position/h-sl-ft'] - h1) <= 300 and f['ap/manual'] == 0,
        'the aircraft holds: "%s", %.0f ft from the height it had when handed back' % (s['doing'], f['position/h-sl-ft'] - h1))
    w.cmd('LRE', 'manual', dict(mode=1))
    w.stick = {'LRE': (0.0, 0.3, 0.0, thr, 0.0)}
    w.run(5)
    w.silent = {'LRE'}
    t = 0.0
    while not (f['ap/manual'] == 0 and w.status()['contingency'] == 'link') and t < 40:
        w.run(0.1)
        t += 0.1
    s = w.status()
    add('S4', 'the link lost while flown by hand', t <= 31.5 and f['ap/manual'] == 0 and s['contingency'] == 'link',
        'automatic again and on the lost-link route %.1f s after the last uplink: "%s"' % (t, s['doing']))
    for tag, name, ok, detail in rows:
        print('%-3s %-40s %-5s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))


if __name__ == '__main__':
    main()
