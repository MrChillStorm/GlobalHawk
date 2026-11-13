#!/usr/bin/env python3
"""Phase 9 part B checks: the aircraft's end of the link in Nasal, in FlightGear itself, driven as the ground
station drives it (Phase 8's websocket client).

    python3 fdm/phase9b_checks.py [smoke]        about 15 minutes; FlightGear opens a window. smoke: start, N1, N2 only

Limits: docs/PLAN.md, written before any of the Nasal was run. The flight runs SPEED times as fast as the clock.
"""
import asyncio
import json
import math
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcs_server as G              # noqa: E402
import missionmgr as MM             # noqa: E402
import phase8a_checks as P8         # noqa: E402
import phase9a_checks as P9         # noqa: E402

PORT = P9.PORT
P8.PORT = PORT
J = '/fdm/jsbsim/'
NM = 6076.1
SPEED = 4
LOG = os.path.join(HERE, 'out', 'fg-link.log')
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))
    print('%-3s %-46s %-5s %s' % rows[-1], flush=True)


def get(path):
    return P9.get(path)


def post(path, value):
    req = urllib.request.Request('http://127.0.0.1:%d/json%s' % (PORT, path), method='POST', data=json.dumps(dict(value=value)).encode())
    try:
        urllib.request.urlopen(req, timeout=3).read()
        return True
    except Exception:
        return False


def simt():
    return get(J + 'simulation/sim-time-sec') or 0.0


def offset(p, brg, dist):
    c = math.radians(brg)
    return [p[0] + dist * math.cos(c) / MM.FT_PER_DEG, p[1] + dist * math.sin(c) / (MM.FT_PER_DEG * math.cos(math.radians(p[0])))]



def model_landing(weight, elev):
    """The flight model alone, landing at a weight and a field height (the station's own table is made from the
    same: fdm/gcs_perf.py): how far past the aiming point it is down to 15 kt, ft."""
    import gcs_perf
    import harness as H
    return gcs_perf.landing_roll(H.load(rebuild=False), weight, elev)[1]

def nasal_errors():
    bad = []
    for line in open(LOG, errors='replace'):
        low = line.lower()
        if 'tied property' in low:
            continue                # FlightGear's own Nasal says this with any aircraft
        if ('nasal' in low and ('error' in low or 'parse' in low)) or 'global hawk link' in low or ('globalhawk/nasal' in low and 'error' in low):
            bad.append(line.strip()[:200])
    return bad


class Station(P8.Client):
    async def say(self, name, args=None, station='CHECK', seq=None, wait=4.0):
        """Send a command as a station; the answer or None."""
        if seq is None:
            self.seq += 1
            seq = self.seq
        t0 = time.monotonic()
        self.send(command='set', node='/gcs/up/cmd', value=json.dumps(dict(seq=seq, station=station, name=name, args=args if args is not None else {})))
        while time.monotonic() - t0 < wait:
            a = self.values.get('/gcs/down/ack')
            if a:
                try:
                    a = json.loads(a)
                except ValueError:
                    a = {}
                if a.get('seq') == seq and a.get('station') == station and self.stamp['/gcs/down/ack'] >= t0:
                    return a
            await asyncio.sleep(0.01)
        return None


def cases(plan):
    """Commands for N2: (station, name, args). The same list goes to the Python end and to the Nasal end."""
    def changed(**kw):
        p = json.loads(json.dumps(plan))
        p.update(kw)
        return p
    route = plan['items'][1]
    far = [[10.0, 20.0, 5000.0], [10.0, 120.0, 5000.0]]
    return [
        ('CHECK', 'start', {}), ('CHECK', 'fly.upside.down', {}), ('CHECK', 'goto', dict(lat=60.0, lon=25.0, alt_ft=5000.0)),
        ('CHECK', 'plan', {}), ('CHECK', 'plan', changed(items=[])), ('CHECK', 'plan', changed(items=[dict(kind='loop')])),
        ('CHECK', 'plan', changed(items=[dict(kind='route', points=[[95.0, 25.0, 5000.0]])])),
        ('CHECK', 'plan', changed(items=[dict(kind='route', points=[[60.0, 25.0, 90000.0]])])),
        ('CHECK', 'plan', changed(items=[dict(kind='route', points=[[60.0, 25.0]])])),
        ('CHECK', 'plan', changed(items=[dict(kind='route', points=far)])),
        ('CHECK', 'plan', changed(items=[plan['items'][0]])),
        ('CHECK', 'plan', changed(items=[route, dict(kind='land', fix=[60.0, 25.0], aim=[60.05, 25.0])])),
        ('CHECK', 'plan', changed(items=[dict(kind='hold', centre=[60.0, 25.0])])),
        ('CHECK', 'plan', changed(lost_link=[route])),
        ('CHECK', 'plan', changed(sites=[dict(name='x', aim=[60.0, 25.0])])),
        ('CHECK', 'plan', changed(field=dict(lat=60.0))),
        ('CHECK', 'altitude', dict(alt_ft=9000.0)), ('CHECK', 'hold', {}), ('CHECK', 'home', {}), ('CHECK', 'resume', {}),
        ('CHECK', 'manual', dict(mode=5)), ('CHECK', 'manual', dict(mode=2)), ('CHECK', 'nav', dict(name='gps', on=True)),
        ('CHECK', 'linktimeout', dict(sec=15)), ('CHECK', 'linktimeout', dict(sec=5)), ('CHECK', 'linktimeout', dict(sec=400)),
        ('CHECK', 'linktimeout', dict(sec='abc')), ('CHECK', 'linktimeout', {}),      # not sec=True: Nasal's JSON reader reads true as 1 (json.nas), so it refuses it by the bounds, Python as not a number
        ('OTHER', 'linktimeout', dict(sec=60)), ('CHECK', 'linktimeout', dict(sec=30)),
        ('CHECK', 'control.offer', dict(to='NOBODY')), ('CHECK', 'control.offer', dict(to='CHECK')), ('CHECK', 'control.cancel', {}),
        ('CHECK', 'control.take', {}),
        ('OTHER', 'goto', dict(lat=60.0, lon=25.0, alt_ft=5000.0)), ('OTHER', 'control.accept', {}), ('OTHER', 'control.take', {}),
        ('CHECK', 'goto', {}), ('CHECK', 'control.offer', {}),
        ('CHECK', 'plan', plan),
    ]


def python_answers(todo):
    sim = G.Sim()
    out = []
    for n, (station, name, args) in enumerate(todo):
        sim.set('/gcs/up/cmd', json.dumps(dict(seq=n + 1, station=station, name=name, args=args)))
        out.append(json.loads(sim.get('/gcs/down/ack')))
    before = sim.get('/gcs/down/ack')
    sim.set('/gcs/up/cmd', json.dumps(dict(seq=3, station='CHECK', name='start', args={})))       # an old number
    return out, sim.get('/gcs/down/ack') == before


async def flight(smoke):
    c = Station()
    await c.connect()
    c.listen_to('/gcs/down/ack', '/gcs/down/status', '/gcs/down/plan')
    seen = []                                    # the manager's and the link's events, in the order they came

    def status():
        s = c.status()
        for e in s.get('events', []):
            if e not in seen:
                seen.append(e)
        return s

    async def until(cond, sim_seconds, beat=True):
        end = simt() + sim_seconds
        while simt() < end:
            if beat:
                c.heartbeat()
            status()
            if cond():
                return True
            await asyncio.sleep(0.2)
        return False

    # ---- N1
    await asyncio.sleep(6)
    s = status()
    bad = nasal_errors()
    add('N1', 'the Nasal loads; a status a station can read', not bad and s.get('doing') == 'no plan' and s.get('started') is False,
        'status: doing "%s", started %s, %d keys; Nasal errors in the log: %s' % (s.get('doing'), s.get('started'), len(s), bad[:3] or 'none'))
    if not s:
        return

    # ---- N9 messages between two stations through FlightGear's own web server (not through the aircraft's commands)
    c2 = Station()
    await c2.connect()
    c.listen_to('/gcs/chat/line')
    c2.listen_to('/gcs/chat/line')
    await asyncio.sleep(0.5)

    async def relay(src, dst, text, n):
        t0 = time.monotonic()
        src.send(command='set', node='/gcs/chat/line', value=json.dumps(dict(station='S%d' % n, n=n, text=text, t=n)))
        while time.monotonic() - t0 < 3.0:
            v = dst.values.get('/gcs/chat/line')
            if v and text in v and dst.stamp.get('/gcs/chat/line', 0) >= t0:
                return time.monotonic() - t0
            await asyncio.sleep(0.01)
        return None
    d1 = await relay(c, c2, 'hold at 18,000 for the tanker', 1)
    d2 = await relay(c2, c, 'copy, camera is mine', 2)
    add('N9', 'a message between two stations', d1 is not None and d2 is not None and d1 < 1.0 and d2 < 1.0 and not nasal_errors(),
        'one station to the other in %s s and back in %s s (limit 1 s); Nasal errors: %s' % (
            '%.2f' % d1 if d1 is not None else 'never', '%.2f' % d2 if d2 is not None else 'never', nasal_errors()[:2] or 'none'))

    # ---- the plan, from where FlightGear put the aircraft
    here = [get('/position/latitude-deg'), get('/position/longitude-deg')]
    hdg = get('/orientation/heading-deg')
    elev = round(get('/position/altitude-ft') - get('/position/altitude-agl-ft'))
    p1 = offset(here, hdg, 8 * NM)
    p2 = offset(p1, hdg + 90, 12 * NM)
    p3 = offset(p2, hdg + 180, 40 * NM)
    fix = offset(here, hdg + 180, 10 * NM)
    aim = offset(here, hdg, 800.0)
    plan = dict(id='fg-check', field=dict(name='where FlightGear started', lat=here[0], lon=here[1], elev_ft=elev),
                items=[dict(kind='takeoff', start=here, end=offset(here, hdg, 9000.0)),
                       dict(kind='route', points=[p1 + [6000.0], p2 + [8000.0], p3 + [8000.0]])],
                lost_link=[dict(kind='route', points=[fix + [elev + 3500.0]]), dict(kind='land', fix=fix, aim=aim)],
                sites=[dict(name='home', aim=aim, course=hdg, elev_ft=elev)])

    # ---- N2
    todo = cases(plan)
    py, py_old_ignored = python_answers(todo)
    same, diff = 0, []
    for (station, name, args), want in zip(todo, py):
        got = await c.say(name, args, station=station)
        loose = want['reason'].startswith('bad arguments')
        ok = got is not None and got['status'] == want['status'] and (got['reason'] == want['reason'] or (loose and got['reason'].startswith('bad arguments')))
        same += ok
        if not ok:
            diff.append('%s %s: Python "%s %s", Nasal "%s"' % (station, name, want['status'], want['reason'], (got['status'] + ' ' + got['reason']) if got else 'no answer'))
    old = await c.say('start', {}, seq=3, wait=2.0)
    add('N2', 'the same answers as the Python end', same == len(todo) and old is None and py_old_ignored,
        '%d of %d commands answered alike; an old sequence number ignored by both: %s%s' % (same, len(todo), old is None and py_old_ignored, '; differences: ' + ' | '.join(diff[:4]) if diff else ''))
    if smoke:
        return

    # ---- N3
    post('/sim/speed-up', SPEED)
    a = await c.say('start')
    t0 = simt()
    up = await until(lambda: (get(J + 'aero/wheel-height-ft') or 0) > 100, 90)
    t_air = simt() - t0
    def gear():
        v = get(J + 'gear/gear-pos-norm')
        return 1.0 if v is None else v                               # 0 is up: not to be taken for "no answer"
    await until(lambda: gear() < 0.02 and status().get('kind') == 'route', 60)
    await until(lambda: False, 60)
    s = status()
    xt = abs(get(J + 'ap/leg-xt-ft') or 9e9) / NM
    add('N3', 'takeoff and onto the route by command alone', bool(a and a['status'] == 'accepted' and up and s.get('kind') == 'route' and xt < 0.25 and gear() < 0.02),
        'start %s; 100 ft above the runway %.0f s after it; then "%s"; %.2f nmi off the leg; gear %.2f; %.0f ft' % (
            a and a['status'], t_air, s.get('doing'), xt, gear(), get('/position/altitude-ft') or 0))

    # ---- N4
    pos = [get('/position/latitude-deg'), get('/position/longitude-deg')]
    g = offset(pos, (get('/orientation/heading-deg') or hdg) + 50, 6 * NM)
    a = await c.say('goto', dict(lat=g[0], lon=g[1], alt_ft=7000.0))
    in_hold = await until(lambda: status().get('kind') == 'hold', 400)
    hold = status().get('hold') or {}
    await until(lambda: False, 150)                                  # settle
    ratio, alts = [], []

    async def sample(seconds):
        end = simt() + seconds
        while simt() < end:
            c.heartbeat()
            status()
            p = [get('/position/latitude-deg'), get('/position/longitude-deg')]
            if hold and None not in p:
                ratio.append(MM.course((hold['lat'], hold['lon']), p)[1] / hold['radius_ft'])
                alts.append(get('/position/altitude-ft'))
            await asyncio.sleep(0.25)
    await sample(300)
    a2 = await c.say('altitude', dict(alt_ft=8000.0))
    climbed = await until(lambda: abs((get('/position/altitude-ft') or 0) - 8000.0) < 150, 240)
    a3 = await c.say('resume')
    await until(lambda: False, 10)
    s = status()
    ok = bool(a and a['status'] == 'accepted' and in_hold and ratio and max(abs(r - 1) for r in ratio) <= 0.15 and max(abs(h - 7000) for h in alts) <= 150
              and a2 and a2['status'] == 'accepted' and climbed and a3 and a3['status'] == 'accepted' and s.get('kind') == 'route' and s.get('off_plan') is None)
    add('N4', 'goto, hold, altitude, resume', ok, 'goto %s, holding: %s; over one turn the distance from the centre %.2f to %.2f of the radius (%.0f ft), height %.0f to %.0f ft; '
        'altitude 8000 %s, reached: %s; resume %s, then "%s", off the plan: %s' % (
            a and a['status'], in_hold, min(ratio or [0]), max(ratio or [0]), hold.get('radius_ft', 0), min(alts or [0]), max(alts or [0]),
            a2 and a2['status'], climbed, a3 and a3['status'], s.get('doing'), s.get('off_plan')))

    # ---- N5
    a = await c.say('manual', dict(mode=1))
    bank = []
    end = simt() + 10
    while simt() < end:
        c.heartbeat()
        c.send(command='set', node='/gcs/up/stick', value=json.dumps(dict(station='CHECK', p=0.0, r=0.5, y=0.0, t=0.6, s=0.0)))
        bank.append(get('/orientation/roll-deg') or 0.0)
        await asyncio.sleep(0.1)
    m1 = get(J + 'ap/manual')
    a2 = await c.say('manual', dict(mode=0))
    await until(lambda: False, 30)
    s = status()
    add('N5', 'flown by hand through the link, and back', bool(a and a['status'] == 'accepted' and m1 == 1 and max(bank) >= 10 and a2 and a2['status'] == 'accepted' and s.get('kind') == 'hold' and s.get('manual') == 0),
        'manual %s (mode %s); stick half right for 10 s: bank to %.1f deg; automatic %s, then "%s", manual %s' % (a and a['status'], m1, max(bank), a2 and a2['status'], s.get('doing'), s.get('manual')))
    a = await c.say('resume')
    await until(lambda: status().get('kind') == 'route', 20)

    # ---- N6
    timeout = status().get('link_timeout') or 30.0
    t0 = simt()
    lost = await until(lambda: status().get('link_lost') is True, timeout + 30, beat=False)
    t_lost = simt() - t0
    await until(lambda: status().get('contingency') == 'link', 10, beat=False)
    s = status()
    cont, doing = s.get('contingency'), s.get('doing')
    c.heartbeat()
    await asyncio.sleep(0.5)
    a = await c.say('resume')
    await until(lambda: False, 10)
    s2 = status()
    add('N6', 'link lost, the contingency route, and back', bool(lost and abs(t_lost - timeout) < 8 and cont == 'link' and a and a['status'] == 'accepted' and s2.get('contingency') is None and s2.get('link_lost') is False and s2.get('kind') == 'route'),
        'no heartbeat: lost after %.0f s (timeout %.0f); contingency "%s", "%s"; resume %s: contingency %s, link lost %s, "%s"' % (
            t_lost, timeout, cont, doing, a and a['status'], s2.get('contingency'), s2.get('link_lost'), s2.get('doing')))

    # ---- N8: home by the lost link, to a landing on FlightGear's ground (reported)
    fps = get('/sim/frame-rate')
    landed = await until(lambda: status().get('kind') == 'done' or (get(J + 'ap/rollout') == 1 and (get(J + 'ap/ground-speed-kt') or 99) < 15), 2400, beat=False)
    # The manager writes 'rollout over' on its next frame after the aircraft is under 15 kt, and at 4x speed and 2 frames a second that
    # frame can come after this one has read the events: wait for the event (a race that the first full rerun after the section's
    # moment was corrected lost, with the landing itself the same to 170 ft), so that N7 reads the manager's whole list.
    await until(lambda: any(e[1].startswith('rollout over') for e in seen), 60, beat=False)
    s = status()
    p = [get('/position/latitude-deg'), get('/position/longitude-deg')]
    brg, dist = MM.course(aim, p)
    along, across = dist * math.cos(math.radians(brg - hdg)), dist * math.sin(math.radians(brg - hdg))
    # the same landing in the flight model alone, at the weight FlightGear's aircraft landed with: where it is down
    # to 15 kt past the aiming point. A landing soon after takeoff is a heavy one (the approach's speed goes with
    # the root of the weight, the rollout's length with the weight), so a figure with no weight says nothing.
    weight = get(J + 'inertia/weight-lbs')
    model = model_landing(weight, elev)
    add('N8', 'the landing home, against the flight model alone', bool(landed) and abs(along - model) <= 0.10 * model and abs(across) <= 15,
        'link stopped: landed %s, "%s", at %.0f lb; under 15 kt %.0f ft past the aiming point (the flight model alone at that weight: %.0f ft, limit 10 %%) and %.0f ft right of the centreline, %.1f ft above the ground point; %s frames a second at %dx (reported)' % (
            landed, s.get('doing'), weight, along, model, across, get('/position/altitude-agl-ft') or -1, fps, SPEED))

    # ---- N7
    src = open(os.path.join(HERE, 'missionmgr.py')).read()
    want = ['begin takeoff', 'airborne, climb', 'begin route', 'climb to', 'begin hold', 'LINK LOST: the contingency route', 'begin land', 'glide path', 'rollout over']
    texts = [e[1] for e in sorted(seen)]
    at, found = 0, []
    for w in want:
        hit = next((i for i in range(at, len(texts)) if texts[i].startswith(w)), None)
        found.append(hit is not None)
        if hit is not None:
            at = hit + 1
    in_python = all(('begin ' in src and ("kind='%s'" % w[6:] in src or w[6:] in src)) if w.startswith('begin ') else w.split(' to')[0].split(':')[0] in src for w in want)      # 'begin ' + kind is put together there
    add('N7', "the manager's events, in the Python one's order", all(found) and in_python, 'in order: %s; each is a text the Python manager writes: %s; %d events seen' % (
        ', '.join('%s %s' % (w, 'yes' if f else 'NO') for w, f in zip(want, found)), in_python, len(texts)))
    bad = nasal_errors()
    add('N1b', 'no Nasal error by the end of the flight', not bad, '%s' % (bad[:3] or 'none'))


def main():
    smoke = 'smoke' in sys.argv[1:]
    proc, took = P9.start(['--airport=EFHK'], LOG)
    if took is None:
        P9.stop(proc)
        add('N1', 'FlightGear starts', False, 'it did not come up in 4 minutes (fdm/out/fg-link.log)')
    else:
        try:
            asyncio.run(flight(smoke))
        finally:
            P9.stop(proc)
    out = os.path.join(HERE, 'out', 'phase9b_checks.txt')
    with open(out, 'w') as fh:
        for r in rows:
            fh.write('%-3s %-46s %-5s %s\n' % r)
    print('%d checks, %d pass, %d miss' % (len(rows), sum(r[2] == 'pass' for r in rows), sum(r[2] != 'pass' for r in rows)))


if __name__ == '__main__':
    main()
