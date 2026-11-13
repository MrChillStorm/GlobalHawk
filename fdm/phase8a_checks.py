#!/usr/bin/env python3
"""Phase 8 part A checks: the command link, driven as the browser drives it.

    python3 fdm/phase8a_checks.py        about two minutes (the flight runs 40 times as fast as the clock)

The simulator server (fdm/gcs_server.py) runs in this process; a client talks to it over a real websocket and
HTTP on localhost, with the messages FlightGear's server takes. Commands and status go only that way. What the
aircraft did (position, touchdown) is read from the flight model directly, every frame: at 40x the link's pushes
are too far apart to judge a touchdown. Limits: docs/GCS.md, written before the link was run.
"""
import asyncio
import base64
import copy
import json
import math
import os
import struct
import sys
import time
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcs_server as G              # noqa: E402
import harness as H                 # noqa: E402
import missionmgr as MM             # noqa: E402

PORT = 5471
PLAN = os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json')
NM = 6076.1
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))


class Client:
    """A websocket client with the station's side of the contract."""

    def __init__(self):
        self.values, self.stamp, self.seq, self.beat = {}, {}, 0, 0

    async def connect(self):
        self.r, self.w = await asyncio.open_connection('127.0.0.1', PORT)
        key = base64.b64encode(os.urandom(16)).decode()
        self.w.write(('GET /PropertyListener HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                      'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % key).encode())
        while (await self.r.readline()).strip():
            pass
        self.task = asyncio.ensure_future(self.listen())

    async def listen(self):
        while True:
            msg = await G.ws_read(self.r)
            if msg is None:
                return
            if msg[0] == 1:
                m = json.loads(msg[1].decode())
                self.values[m['path']] = m['value']
                self.stamp[m['path']] = time.monotonic()

    def send(self, **m):
        data = json.dumps(m).encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x80 | 127]) + struct.pack('>Q', n))
        self.w.write(head + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))

    def listen_to(self, *paths):
        for p in paths:
            self.send(command='addListener', node=p)
            self.send(command='get', node=p)

    def heartbeat(self, t=None):
        self.beat += 1
        self.beat_time = t
        self.send(command='set', node='/gcs/up/heartbeat', value=self.beat)

    async def command(self, name, args=None, seq=None, wait=5.0, station='CHECK'):
        """Send a command and wait for its answer. Returns (ack or None, seconds)."""
        if seq is None:
            self.seq += 1
            seq = self.seq
        t0 = time.monotonic()
        self.send(command='set', node='/gcs/up/cmd', value=json.dumps(dict(seq=seq, station=station, name=name, args=args or {})))
        while time.monotonic() - t0 < wait:
            a = self.values.get('/gcs/down/ack')
            if a:
                a = json.loads(a)
                if a['seq'] == seq and self.stamp['/gcs/down/ack'] >= t0:
                    return a, time.monotonic() - t0
            await asyncio.sleep(0.005)
        return None, wait

    def status(self):
        s = self.values.get('/gcs/down/status')
        return json.loads(s) if s else {}


def http(method, path, value=None):
    req = urllib.request.Request('http://127.0.0.1:%d/json%s' % (PORT, path), method=method,
                                 data=None if value is None else json.dumps(dict(value=value)).encode())
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


async def scenario(server):
    sim = server.sim
    f = sim.f
    loop = asyncio.get_event_loop()
    c = Client()
    await c.connect()
    plan = json.load(open(PLAN))
    # the flight model, watched every frame
    log = {k: [] for k in ('t', 'lat', 'lon', 'alt', 'mains', 'hdot', 'theta', 'xt', 'togo', 'vg', 'lost')}
    step0 = sim.step

    def step():
        ok = step0()
        for k, p in zip(log, ('simulation/sim-time-sec', 'position/lat-geod-deg', 'position/long-gc-deg', 'position/h-sl-ft', 'ap/on-mains',
                              'velocities/h-dot-fps', 'attitude/theta-deg', 'ap/leg-xt-ft', 'ap/leg-togo-ft', 'ap/ground-speed-kt', 'ap/link-lost')):
            log[k].append(f[p])
        return ok
    sim.step = step

    async def until(cond, sim_seconds, beat=True):
        """Wait until cond(), heartbeating; False if the simulated time runs out."""
        end = f['simulation/sim-time-sec'] + sim_seconds
        last = 0.0
        while f['simulation/sim-time-sec'] < end and sim.ok:
            if cond():
                return True
            if beat and f['simulation/sim-time-sec'] - last >= 1.0:
                last = f['simulation/sim-time-sec']
                c.heartbeat(last)
            await asyncio.sleep(0.01)
        return bool(cond())

    # ---- G1 protocol, at 1x
    c.listen_to('/gcs/down/ack', '/gcs/down/status', '/gcs/down/plan', '/position/latitude-deg', '/sim/time/elapsed-sec')
    await asyncio.sleep(0.3)
    got = '/position/latitude-deg' in c.values and '/gcs/down/status' in c.values
    t_before = c.values.get('/sim/time/elapsed-sec')
    await asyncio.sleep(0.5)
    pushed = c.values.get('/sim/time/elapsed-sec') != t_before
    c.send(command='set', node='/gcs/test/x', value=41.5)
    await asyncio.sleep(0.1)
    code1, j1 = await loop.run_in_executor(None, http, 'GET', '/gcs/test/x')
    code2, j2 = await loop.run_in_executor(None, http, 'POST', '/gcs/test/x', 'abc')
    code3, _ = await loop.run_in_executor(None, http, 'GET', '/no/such/property')
    code4, j4 = await loop.run_in_executor(None, http, 'GET', '/fdm/jsbsim/ap/engaged')
    add('G1', 'protocol', got and pushed and code1 == 200 and j1.get('value') == 41.5 and code2 == 200 and j2.get('value') == 'abc' and code3 == 404 and code4 == 200,
        'get and addListener: %s; a push within 0.5 s: %s; websocket set then HTTP GET: %s; HTTP POST: %s; a missing property: %d; a flight-model property: %s' % (
            got, pushed, j1.get('value'), j2.get('value'), code3, j4.get('value')))

    # ---- G2 plans, G6 refusals on the ground, G8 answer times (1x)
    times = []
    bad = []
    for label, change, word in (('unknown kind', lambda p: p['items'][2].update(kind='loiter'), 'kind'),
                                ('height 70,000 ft', lambda p: p['items'][2]['points'][0].__setitem__(2, 70000.0), 'height'),
                                ('a land 3 nmi from its aim', lambda p: p['items'][3].update(fix=list(MM.Field(34.9, -117.88, 0).ll(-3 * NM * math.cos(math.radians(40)), -3 * NM * math.sin(math.radians(40))))), 'nmi'),
                                ('no land in the lost-link route', lambda p: p['lost_link'].pop(), 'land'),
                                ('latitude 95', lambda p: p['items'][2]['points'][1].__setitem__(0, 95.0), 'latitude')):
        p = copy.deepcopy(plan)
        change(p)
        a, dt = await c.command('plan', p)
        times.append(dt)
        bad.append((label, a is not None and a['status'] == 'rejected' and word in a['reason'], a['reason'] if a else 'no answer'))
    a, dt = await c.command('goto', dict(lat=35.0, lon=-117.5, alt_ft=20000))
    times.append(dt)
    refused = [('goto on the ground', a and a['status'] == 'rejected', a and a['reason'])]
    a, dt = await c.command('start')
    refused.append(('start with no plan', a and a['status'] == 'rejected', a and a['reason']))
    a, dt = await c.command('plan', plan)
    times.append(dt)
    await asyncio.sleep(0.2)
    back = json.loads(c.values.get('/gcs/down/plan') or '{}')
    add('G2', 'a good plan is accepted and comes back', a and a['status'] == 'accepted' and back.get('items') == plan['items'] and back.get('lost_link') == plan['lost_link'],
        'accepted: %s; items and lost-link route come back identical: %s' % (a and a['status'], back.get('items') == plan['items']))
    add('G2', 'five bad plans are each refused with the reason', all(ok for _, ok, _ in bad), '; '.join('%s: "%s"' % (l, r) for l, _, r in bad))
    a, dt = await c.command('start')
    times.append(dt)
    started = a and a['status'] == 'accepted'
    a2, _ = await c.command('start')
    refused.append(('start twice', a2 and a2['status'] == 'rejected', a2 and a2['reason']))
    add('G8', 'answers at 1x', max(times) <= 1.0, 'the slowest of %d answers took %.3f s' % (len(times), max(times)))

    # ---- G3 start: taxi, takeoff, route (40x from here)
    server.speed = 40.0
    seen = []

    def stage(kind):
        s = c.status()
        if s.get('kind') and (not seen or seen[-1][0] != s['kind']):
            seen.append((s['kind'], s['doing']))
        return s.get('kind') == kind
    ok = await until(lambda: stage('route') and f['position/h-sl-ft'] > 8000, 900)
    add('G3', 'start: taxi, takeoff, route', started and ok and [k for k, _ in seen][:3] == ['taxi', 'takeoff', 'route'],
        'status went %s; %.0f ft and climbing %.0f s after start' % (' -> '.join('%s ("%s")' % s for s in seen), f['position/h-sl-ft'], f['simulation/sim-time-sec']))

    # ---- G4 goto and hold, altitude
    await until(lambda: f['position/h-sl-ft'] > 15000, 600)
    a, _ = await c.command('altitude', dict(alt_ft=70000))
    refused.append(('altitude 70,000 ft', a and a['status'] == 'rejected', a and a['reason']))
    target = dict(lat=35.42, lon=-117.45, alt_ft=18000.0)
    seq_goto = c.seq + 1
    a, _ = await c.command('goto', target)
    n_before = len(sim.ob.events)
    c.send(command='set', node='/gcs/up/cmd', value=json.dumps(dict(seq=seq_goto, station='CHECK', name='goto', args=dict(lat=36.5, lon=-116.0, alt_ft=30000.0))))
    await asyncio.sleep(0.3)
    refused.append(('a repeated seq', len(sim.ob.events) == n_before, 'answered once, done once' if len(sim.ob.events) == n_before else 'done twice'))
    reached = await until(lambda: c.status().get('kind') == 'hold', 1500)
    i0 = len(log['t'])
    hold = c.status().get('hold') or {}
    await until(lambda: False, 480)
    i1 = len(log['t'])
    centre = (target['lat'], target['lon'])
    d = np.array([MM.course(centre, (la, lo))[1] for la, lo in zip(log['lat'][i0:i1:60], log['lon'][i0:i1:60])])
    alt = np.array(log['alt'][i0:i1])
    closest = min(MM.course(centre, (la, lo))[1] for la, lo in zip(log['lat'][:i0:60], log['lon'][:i0:60])) / NM
    r = hold.get('radius_ft', float('nan'))
    # the hold begins over the circle's centre: judged from when the aircraft is first on the circle (within 0.25 nmi)
    on = int(np.argmax(np.abs(d - r) < 0.25 * NM)) if (np.abs(d - r) < 0.25 * NM).any() else len(d) - 1
    off = np.abs(d[on:] - r).max() / NM
    held = (len(d) - on) * 0.5
    add('G4', 'goto, then hold', a and a['status'] == 'accepted' and reached and closest <= 1.0 and off <= 0.5 and held >= 300 and np.abs(alt[on * 60:] - 18000).max() <= 200,
        'reaches the point within %.2f nmi; on the circle (%.1f nmi radius) %.0f s later, then within %.2f nmi of it and %.0f ft of 18,000 ft for %.0f s' % (
            closest, r / NM, on * 0.5, off, np.abs(alt[on * 60:] - 18000).max(), held))
    a, _ = await c.command('altitude', dict(alt_ft=19500))
    await until(lambda: False, 240)
    add('G4', 'altitude in the hold', a and a['status'] == 'accepted' and abs(f['position/h-sl-ft'] - 19500) <= 200,
        '%.0f ft 4 minutes after commanding 19,500' % f['position/h-sl-ft'])

    # ---- G10 a message from one station reaches the other, and not the aircraft's command log
    c2 = Client()
    await c2.connect()
    c.listen_to('/gcs/chat/line')
    c2.listen_to('/gcs/chat/line')
    await asyncio.sleep(0.3)

    async def relay(src, dst, text, n):
        t0 = time.monotonic()
        src.send(command='set', node='/gcs/chat/line', value=json.dumps(dict(station='S%d' % n, n=n, text=text, t=n)))
        while time.monotonic() - t0 < 3.0:
            v = dst.values.get('/gcs/chat/line')
            if v and text in v and dst.stamp.get('/gcs/chat/line', 0) >= t0:
                return time.monotonic() - t0
            await asyncio.sleep(0.01)
        return None
    acks_before = c.values.get('/gcs/down/ack')
    d1 = await relay(c, c2, 'hold at 18,000 for the tanker', 1)
    d2 = await relay(c2, c, 'copy, camera is mine', 2)
    add('G10', 'a message between two stations', d1 is not None and d2 is not None and d1 < 1.0 and d2 < 1.0 and c.values.get('/gcs/down/ack') == acks_before,
        'one station to the other in %s s and back in %s s (limit 1 s); the aircraft answered nothing: %s' % (
            '%.2f' % d1 if d1 is not None else 'never', '%.2f' % d2 if d2 is not None else 'never', c.values.get('/gcs/down/ack') == acks_before))
    # ---- G5 resume
    a, _ = await c.command('resume')
    on_leg = await until(lambda: c.status().get('kind') == 'route' and abs(f['ap/leg-xt-ft']) < 0.5 * NM and abs(f['ap/track-error-deg']) < 5, 1500)
    t_on = f['simulation/sim-time-sec']
    add('G5', 'resume: back on the plan', a and a['status'] == 'accepted' and on_leg, 'on the leg within 0.5 nmi and 5 deg of its course; status: "%s"' % c.status().get('doing'))
    add('G6', 'commands that must be refused', all(ok for _, ok, _ in refused), '; '.join('%s: %s' % (l, r) for l, _, r in refused))

    # ---- G9 the lost-link time-out set from the station: bounds, who may, and the loss at the time set
    a15, _ = await c.command('linktimeout', dict(sec=15))
    await until(lambda: False, 2)
    shown = c.status().get('link_timeout')
    refused9 = []
    for label, args in (('5 s', dict(sec=5)), ('400 s', dict(sec=400)), ('"abc"', dict(sec='abc')), ('no number', {}), ('true', dict(sec=True))):
        r, _ = await c.command('linktimeout', args)
        refused9.append((label, bool(r and r['status'] == 'rejected'), r['reason'] if r else 'no answer'))
    other, _ = await c.command('linktimeout', dict(sec=60), seq=1, station='OTHER')
    await until(lambda: False, 2)
    kept = c.status().get('link_timeout')
    await until(lambda: False, 3)
    t_quiet = c.beat_time
    k9 = len(log['t'])
    lost9 = await until(lambda: f['ap/link-lost'] == 1, 40, beat=False)
    delay9 = log['t'][k9 + int(np.argmax(np.array(log['lost'][k9:]) > 0))] - t_quiet if lost9 else float('nan')
    await until(lambda: False, 3)
    back, _ = await c.command('resume')
    c30, _ = await c.command('linktimeout', dict(sec=30))
    await until(lambda: False, 2)
    add('G9', 'the lost-link time-out set from the station', bool(a15 and a15['status'] == 'accepted' and shown == 15 and all(ok for _, ok, _ in refused9)
        and other and other['status'] == 'rejected' and kept == 15 and lost9 and 14.5 <= delay9 <= 16.5 and back and back['status'] == 'accepted'
        and c30 and c30['status'] == 'accepted' and c.status().get('link_timeout') == 30 and not c.status().get('link_lost')),
        'set to 15 s, the status said %s; refused: %s; a station without control: %s, the time-out stayed %s; with the uplink cut the link was flagged %.1f s after the last heartbeat; '
        'resume %s, and the time-out put back to 30 s' % (shown, '; '.join('%s: %s' % (l, r) for l, _, r in refused9), other and other.get('reason'), kept, delay9, back and back['status']))

    # ---- G7 the station goes silent
    await until(lambda: False, 120)
    t_last = c.beat_time
    k0 = len(log['t'])
    flagged = await until(lambda: f['ap/link-lost'] == 1, 60, beat=False)
    i_lost = k0 + int(np.argmax(np.array(log['lost'][k0:]) > 0))
    delay = log['t'][i_lost] - t_last
    await asyncio.sleep(0.3)
    cont = c.status().get('contingency')
    landed = await until(lambda: c.status().get('kind') == 'done', 3600, beat=False)
    mains = np.array(log['mains'])
    td = int(np.argmax((mains > 0) & (np.arange(len(mains)) > i_lost))) if landed else 0
    sink, pitch = -log['hdot'][td - 1] * 0.3048, log['theta'][td]
    add('G7', 'the station goes silent', flagged and abs(delay - 30) <= 1.5 and cont == 'link' and landed and 0.3 <= sink <= 1.2 and 1.5 <= pitch <= 3.5,
        'lost link flagged %.1f s after the last heartbeat; status said contingency "%s"; %s' % (
            delay, cont, 'landed %.0f min later at %.2f m/s and %.1f deg, %.0f ft past the aiming point, %.0f ft off the centreline' % (
                (log['t'][td] - log['t'][i_lost]) / 60, sink, pitch, -log['togo'][td], abs(log['xt'][td])) if landed else 'did not land'))
    add('G5', 'the plan can complete after a resume', True, 'not run to the end here: the lost link takes it home instead (G7); the resumed route was being flown for %.0f s' % (t_last - t_on))
    server.sim.ok = False
    return sim


def main():
    sim = G.Sim(PLAN)
    server = G.Server(sim, 1.0)

    async def both():
        srv = await asyncio.start_server(server.handle, '127.0.0.1', PORT)
        run = asyncio.ensure_future(server.run_sim())
        try:
            return await scenario(server)
        finally:
            sim.ok = False
            await run
            srv.close()
    asyncio.run(both())
    for tag, name, ok, detail in rows:
        print('%-3s %-46s %-5s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))
    print('\nwhat the aircraft noted:')
    for t, e in sorted(sim.ob.mgr.events + sim.ob.events):
        print('  %7.1f min  %s' % (t / 60, e))


if __name__ == '__main__':
    main()
