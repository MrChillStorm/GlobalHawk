#!/usr/bin/env python3
"""Stage 1 of "starting at a stand from the planner": the checks for the limits S1 to S5 in docs/PLAN.md. (S6, the whole chain through the station's page against
FlightGear, is done by hand in the browser pane and written up there.)

    python3 ground_checks.py          headless: S1 and S2 at the Python end (airportdata.py, onboard.py), S3 (the station's routing against groundplan.py, which flew them
                                      at EFHK; skipped, said so, where the scenery has no EFHK), the station's node tests
    python3 ground_checks.py fg       S1 and S2 in FlightGear itself, driven through its web port as the station drives it (opens a window; the screen must be unlocked); about 2 minutes

The scenery is read from where FlightGear keeps it on this machine (fdm/airportdata.py scenery_dirs).
"""
import asyncio
import json
import math
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import airportdata as AD            # noqa: E402
import gcs_server as G              # noqa: E402
import groundplan as GP             # noqa: E402
import harness as H                 # noqa: E402

GCS = os.path.join(HERE, '..', 'GlobalHawk', 'gcs')
FT = 364567.2
SPOT = '121'
J = '/fdm/jsbsim/'
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))
    print('%-5s %-62s %-5s %s' % rows[-1], flush=True)


def have_efhk():
    try:
        AD.load('EFHK')
        return True
    except ValueError:
        return False


def feet(a, b):
    return math.hypot((a[0] - b[0]) * FT, (a[1] - b[1]) * FT * math.cos(math.radians(a[0])))


# ------------------------------------------------------------------------------------------------------------------------------------- S1, Python end
def s1_python():
    if not have_efhk():
        add('S1', 'EFHK in the scenery', False, 'no EFHK ground network found: the checks that need it were not made')
        return
    t0 = time.time()
    msg = AD.load('EFHK')
    took = time.time() - t0
    size = len(AD.dumps(msg))
    add('S1.1', 'EFHK from the Python reader: time, size, stands, runway ends', took < 2.0 and size <= AD.MAX_BYTES and len(msg['parking']) == 117 and len(msg['runways']) == 6,
        '%.2f s, %d bytes, %d stands, %d nodes, %d arcs, %d names, runway ends %s' % (took, size, len(msg['parking']), len(msg['nodes']), len(msg['arcs']), len(msg['names']), ' '.join(r['n'] for r in msg['runways'])))
    r22 = [r for r in msg['runways'] if r['n'] == '22L'][0]
    add('S1.2', 'runway end 22L is the threshold file\'s', abs(r22['lat'] - 60.330658) < 1e-6 and abs(r22['lon'] - 24.979042) < 1e-6 and r22['h'] == 227.51, str(r22))
    idx = {tuple(n) for n in msg['nodes']}
    add('S1.3', 'every arc joins two listed nodes, once each', all(0 <= a < len(msg['nodes']) and 0 <= b < len(msg['nodes']) for a, b, k in msg['arcs'])
        and len({(min(a, b), max(a, b), k) for a, b, k in msg['arcs']}) == len(msg['arcs']), '%d distinct nodes' % len(idx))
    want = {'': 'an airport is four letters or digits, like EFHK', '12': 'an airport is four letters or digits, like EFHK', 'ZZZZ': 'no ground network for ZZZZ in the scenery'}
    got = {}
    for k in want:
        try:
            AD.load(k)
            got[k] = 'accepted'
        except ValueError as e:
            got[k] = str(e)
    try:
        AD.load(None)
        got[None] = 'accepted'
    except ValueError as e:
        got[None] = str(e)
    add('S1.4', 'bad code, no code, no network: refused with a reason', got == {**want, None: want['']}, str(got))
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'Airports', 'Q', 'Q', 'Q'))
        open(os.path.join(d, 'Airports', 'Q', 'Q', 'Q', 'QQQQ.groundnet.xml'), 'w').write('<groundnet><parkingList>')
        try:
            AD.load('QQQQ', [d])
            why = 'accepted'
        except ValueError as e:
            why = str(e)
    add('S1.5', 'a ground network that is not XML: refused, not crashed', why.startswith('the ground network of QQQQ cannot be read'), why)
    old = AD.MAX_BYTES
    AD.MAX_BYTES = 1000
    try:
        AD.load('EFHK')
        why = 'accepted'
    except ValueError as e:
        why = str(e)
    AD.MAX_BYTES = old
    add('S1.6', 'a network over the size the link takes: refused', 'too big' in why, why)


# ------------------------------------------------------------------------------------------------------------------------------------- S2, Python end
def say(sim, seq, name, args, station='CHECK'):
    sim.set('/gcs/up/cmd', json.dumps(dict(seq=seq, station=station, name=name, args=args)))
    return json.loads(sim.get('/gcs/down/ack'))


def s2_python():
    spot = GP.Net('EFHK').park[SPOT] if have_efhk() else dict(lat=60.32097, lon=24.96737, heading=138.0)
    sim = G.Sim()
    a = say(sim, 1, 'reposition', dict(lat=spot['lat'], lon=spot['lon'], heading=spot['heading']))
    for _ in range(int(6 * H.HZ)):
        sim.step()
    f = sim.f
    off = feet((f['position/lat-geod-deg'], f['position/long-gc-deg']), (spot['lat'], spot['lon']))
    dh = abs((f['attitude/psi-deg'] - spot['heading'] + 180) % 360 - 180)
    add('S2.1', 'reposition accepted on the ground, before the plan: at the stand, on its wheels (Python)', a['status'] == 'accepted' and off < 40 and dh < 1 and f['ap/on-mains'] == 2 and f['ap/ground-speed-kt'] < 0.5,
        '%s; %.1f ft from the stand, heading %.1f off, mains %s, %.2f kt' % (a['status'], off, dh, f['ap/on-mains'], f['ap/ground-speed-kt']))
    add('S2.1b', 'the structure\'s latches are clear after it (Python)', f['limits/overstress'] == 0 and f['limits/failed'] == 0 and not any(al.get('id') == 'structure' for al in json.loads(sim.get('/gcs/down/status')).get('alerts', [])),
        'overstress %s, failed %s' % (f['limits/overstress'], f['limits/failed']))
    bad = [say(sim, 2, 'reposition', {}), say(sim, 3, 'reposition', dict(lat=95, lon=0, heading=0)), say(sim, 4, 'reposition', dict(lat=60, lon=25))]
    add('S2.2', 'nonsense is refused with the reason', all(b['status'] == 'rejected' for b in bad), ' | '.join(b['reason'] for b in bad))
    f['ic/vc-kts'] = 12.0
    f.run_ic()
    f.run()
    moving = say(sim, 5, 'reposition', dict(lat=spot['lat'], lon=spot['lon'], heading=spot['heading']))
    add('S2.3', 'refused while the aircraft moves (over 2 kt)', moving['status'] == 'rejected' and 'only when the aircraft stands' in moving['reason'], moving['reason'])
    air = G.Sim()
    H.state(air.f, dict(alt=6000.0, kcas=200.0, weight=25600.0, lat=60.3, lon=25.0), 2.0, 0.0, 0.5)
    air.step()
    inair = say(air, 1, 'reposition', dict(lat=spot['lat'], lon=spot['lon'], heading=0))
    add('S2.4', 'refused in the air', inair['status'] == 'rejected' and inair['reason'] == 'only on the ground', inair['reason'])
    plan = json.load(open(os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json')))
    sim2 = G.Sim(os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json'))
    say(sim2, 1, 'plan', plan)
    say(sim2, 2, 'start', {})
    begun = say(sim2, 3, 'reposition', dict(lat=spot['lat'], lon=spot['lon'], heading=0))
    add('S2.5', 'refused once the plan has begun', begun['status'] == 'rejected' and begun['reason'] == 'the plan has begun', begun['reason'])
    other = say(G.Sim(), 1, 'airport', dict(icao='ZZZZ'), station='A')
    holder = G.Sim()
    say(holder, 1, 'start', {}, station='A')
    other2 = say(holder, 1, 'airport', dict(icao='EFHK' if have_efhk() else 'ZZZZ'), station='B')
    add('S2.6', 'the airport command is open to a station that does not hold control; reposition is not', other['reason'].startswith('no ground network') and other2['status'] == ('accepted' if have_efhk() else 'rejected')
        and say(holder, 2, 'reposition', dict(lat=60, lon=25, heading=0), station='B')['reason'] == 'A has control', '%s / %s' % (other['reason'], other2['reason'] or 'accepted'))


# ------------------------------------------------------------------------------------------------------------------------------------- S3
NODE = r"""
const G = require(process.argv[2] + '/js/ground.js');
const fs = require('fs');
const [msgPath, planPath, lat, lon, hdg, holds] = process.argv.slice(3);
const net = new G.Net(JSON.parse(fs.readFileSync(msgPath)));
const plan = JSON.parse(fs.readFileSync(planPath));
const r = G.addTaxi(net, plan, { stand: [Number(lat), Number(lon)], heading: Number(hdg), exit: null, holds: holds === '1' });
console.log(JSON.stringify(r));
"""


def lay(msg, plan, stand, heading, holds=False):
    """What the station's module (js/ground.js addTaxi) makes of a plan, run in node; holds: with the holds it derives (they put points into the route: the geometry checks of S3 ask for none)."""
    with tempfile.TemporaryDirectory() as d:
        mp, pp, sp = (os.path.join(d, n) for n in ('msg.json', 'plan.json', 'run.js'))
        json.dump(msg, open(mp, 'w'))
        json.dump(plan, open(pp, 'w'))
        open(sp, 'w').write(NODE)
        out = subprocess.run(['node', sp, os.path.abspath(GCS), mp, pp, str(stand[0]), str(stand[1]), str(heading), '1' if holds else '0'], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr[-300:])
    return json.loads(out.stdout)


NODE_RWY = r"""
const G = require(process.argv[2] + '/js/ground.js');
const geo = require(process.argv[2] + '/js/geo.js');
const fs = require('fs');
const [msgPath, lat, lon, hdg, elev, holds] = process.argv.slice(3);
const net = new G.Net(JSON.parse(fs.readFileSync(msgPath)));
const stand = lat === 'none' ? null : { stand: [Number(lat), Number(lon)], heading: Number(hdg), exit: null, holds: holds === '1' };
const out = net.runways.map((e) => {
  const r = G.planOnRunway(net, e.n, Number(elev), 7500, stand);
  if (r.error) return { n: e.n, error: r.error };
  const t = r.plan.items.find((i) => i.kind === 'takeoff');
  const l = r.plan.items.find((i) => i.kind === 'land');
  const a = net.runwayFor(t.start, geo.course(t.start, t.end).deg, -300, 12000);
  const b = net.runwayFor(l.aim, geo.course(l.fix, l.aim).deg, -300, 4000);
  return { n: e.n, plan: r.plan, takeoffOn: a && a.n, landOn: b && b.n, out: r.out && { rw: r.out.rw, via: r.out.via, ft: r.out.length_ft }, in: r.in && { rw: r.in.rw, exit: r.in.exit.names, ft: r.in.length_ft } };
});
console.log(JSON.stringify(out));
"""


def runway_plans(msg, stand, heading, elev, holds=True):
    """What the station's module (js/ground.js planOnRunway) makes for each runway end of the airport, run in node: a list of { n, error | plan, takeoffOn, landOn, out, in }."""
    with tempfile.TemporaryDirectory() as d:
        mp, sp = (os.path.join(d, n) for n in ('msg.json', 'run.js'))
        json.dump(msg, open(mp, 'w'))
        open(sp, 'w').write(NODE_RWY)
        args = ['none', '0', '0'] if stand is None else [str(stand[0]), str(stand[1]), str(heading)]
        out = subprocess.run(['node', sp, os.path.abspath(GCS), mp] + args + [str(elev), '1' if holds else '0'], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr[-300:])
    return json.loads(out.stdout)


def r_runways():
    """R2, R3 (docs/PLAN.md, "Runway picker, stage 3"): the plan on every runway end of the made-up field and of EFHK, with and without the stand: the aircraft takes it, the takeoff
    and the landing are on that end, and a runway the taxiways do not reach is refused in words, never laid on another end."""
    xdm = AD.load('XDM1', [os.path.join(GCS, 'tests', 'fixtures', 'scenery')])
    cases = [('XDM1', xdm, None, None, 2300), ('XDM1', xdm, (xdm['parking'][0]['lat'], xdm['parking'][0]['lon']), xdm['parking'][0]['h'], 2300)]
    if have_efhk():
        sp = GP.Net('EFHK').park[SPOT]
        efhk = AD.load('EFHK')
        cases += [('EFHK', efhk, None, None, 167), ('EFHK', efhk, (sp['lat'], sp['lon']), sp['heading'], 167)]
    for icao, msg, stand, heading, elev in cases:
        res = runway_plans(msg, stand, heading, elev)
        sim = G.Sim()
        bad, said, done = [], [], 0
        for r in res:
            if 'error' in r:
                if stand is None or not r['error'].strip():       # without a stand every end is a plan; with one a refusal must say why
                    bad.append('%s: refused (%s)' % (r['n'], r['error']))
                said.append('%s refused: %s' % (r['n'], r['error']))
                continue
            done += 1
            a = say(sim, done, 'plan', r['plan'])
            if a['status'] != 'accepted':
                bad.append('%s: the aircraft says %s %s' % (r['n'], a['status'], a.get('reason', '')))
            if r['takeoffOn'] != r['n'] or r['landOn'] != r['n']:
                bad.append('%s: takeoff on %s, landing on %s' % (r['n'], r['takeoffOn'], r['landOn']))
            if stand is not None:
                if not (r['out'] and r['out']['rw'] == r['n'] and r['in'] and r['in']['rw'] == r['n']):
                    bad.append('%s: taxi routes not on that runway' % r['n'])
                kinds = [i['kind'] for i in r['plan']['items']]
                if kinds[:2] != ['taxi', 'takeoff'] or kinds[-1] != 'taxi':
                    bad.append('%s: items %s' % (r['n'], kinds))
            said.append('%s %s' % (r['n'], ('out %d ft by %s, in %d ft by %s' % (r['out']['ft'], ','.join(r['out']['via']), r['in']['ft'], '/'.join(r['in']['exit']))) if stand is not None else 'plan'))
        n = len(res)
        add('R3.1' if stand is not None else 'R2.1', 'the plan on each of the %d runway ends of %s%s' % (n, icao, ' from the stand' if stand is not None else ''),
            not bad and done >= 1 and (stand is not None or done == n), '; '.join(bad) if bad else '%d of %d laid and taken by the aircraft; %s' % (done, n, '; '.join(said)))


def s4_plans():
    """S4: the plans the station lays pass the aircraft's own check, Python's here (Nasal's in FlightGear: python3 ground_checks.py fg)."""
    demo = json.load(open(os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json')))
    xdm = AD.load('XDM1', [os.path.join(GCS, 'tests', 'fixtures', 'scenery')])
    r = lay(xdm, demo, (xdm['parking'][0]['lat'], xdm['parking'][0]['lon']), xdm['parking'][0]['h'], True)
    plans = [('XDM1', r)]
    if have_efhk():
        ref = json.load(open(os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'efhk-taxi-box-taxi.json')))
        sp = GP.Net('EFHK').park[SPOT]
        plans.append(('EFHK', lay(AD.load('EFHK'), ref, (sp['lat'], sp['lon']), sp['heading'], True)))
    for name, r in plans:
        if 'error' in r:
            add('S4.1', 'the station lays the taxi routes at %s' % name, False, r['error'])
            continue
        sim = G.Sim()
        a = say(sim, 1, 'plan', r['plan'])
        kinds = ' '.join(i['kind'] for i in r['plan']['items'])
        add('S4.1', 'the plan the station lays at %s is accepted by the aircraft (Python)' % name, a['status'] == 'accepted' and kinds.startswith('taxi takeoff route land taxi'), '%s: %s %s' % (kinds, a['status'], a['reason']))


def s3():
    if not have_efhk():
        add('S3', 'routing against groundplan.py at EFHK', False, 'no EFHK ground network found: not made')
        return
    msg = AD.load('EFHK')
    spot = GP.Net('EFHK').park[SPOT]
    ref = json.load(open(os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'efhk-taxi-box-taxi.json')))      # what groundplan.py built and the aircraft flew
    plan = json.loads(json.dumps(ref))
    plan['items'] = [i for i in plan['items'] if i['kind'] != 'taxi']
    # the station's route takes the plan with its takeoff wherever it begins on the runway; the reference's begins at the line-up point: leave it there, the station moves it by itself
    with tempfile.TemporaryDirectory() as d:
        mp, pp, sp = (os.path.join(d, n) for n in ('msg.json', 'plan.json', 'run.js'))
        json.dump(msg, open(mp, 'w'))
        json.dump(plan, open(pp, 'w'))
        open(sp, 'w').write(NODE)
        out = subprocess.run(['node', sp, os.path.abspath(GCS), mp, pp, str(spot['lat']), str(spot['lon']), str(spot['heading']), '0'], capture_output=True, text=True)
    if out.returncode:
        add('S3.1', 'the station\'s module runs', False, out.stderr[-300:])
        return
    r = json.loads(out.stdout)
    if 'error' in r:
        add('S3.1', 'the station lays the taxi routes at EFHK', False, r['error'])
        return
    mine_out, mine_in = r['plan']['items'][0], r['plan']['items'][-1]
    ref_out, ref_in = [i for i in ref['items'] if i['kind'] == 'taxi'][0], [i for i in ref['items'] if i['kind'] == 'taxi'][1]
    # the points are the same to a foot: the station has the runway end as the message gives it (6 decimals), groundplan.py as threshold.xml gives it (8): the turn's points move by a tenth of a foot
    close = lambda a, b: len(a) == len(b) and max(feet(x, y) for x, y in zip(a, b)) < 1.0
    same_out, same_in = close(mine_out['points'], ref_out['points']), close(mine_in['points'], ref_in['points'])
    ln = lambda pts: sum(feet(a, b) for a, b in zip(pts[:-1], pts[1:]))
    lo, li = ln(mine_out['points']), ln(mine_in['points'])
    add('S3.1', 'taxi out from stand %s to 22L: the same points as groundplan.py (to a foot)' % SPOT, same_out and abs(lo / ln(ref_out['points']) - 1) < 0.01,
        '%d points, %.0f ft (groundplan.py %d points, %.0f ft); same to a foot: %s' % (len(mine_out['points']), lo, len(ref_out['points']), ln(ref_out['points']), same_out))
    add('S3.2', 'taxi in from the runway to the stand: the same points (to a foot)', same_in and abs(li / ln(ref_in['points']) - 1) < 0.01,
        '%d points, %.0f ft (groundplan.py %d points, %.0f ft); same to a foot: %s' % (len(mine_in['points']), li, len(ref_in['points']), ln(ref_in['points']), same_in))
    t0 = [i for i in r['plan']['items'] if i['kind'] == 'takeoff'][0]
    t1 = [i for i in ref['items'] if i['kind'] == 'takeoff'][0]
    add('S3.3', 'the takeoff begins at the same line-up point', feet(t0['start'], t1['start']) < 1.0 and feet(t0['end'], t1['end']) < 1.0, '%s against %s' % (t0['start'], t1['start']))
    add('S3.4', 'the rest of the plan is as it was', [i for i in r['plan']['items'] if i['kind'] in ('route', 'land')] == [i for i in ref['items'] if i['kind'] in ('route', 'land')]
        and r['plan']['lost_link'] == ref['lost_link'], 'route and land equal')


def node_tests():
    out = subprocess.run(['npm', 'test'], cwd=GCS, capture_output=True, text=True)
    last = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr[-200:]
    add('S5.1', 'the station\'s node tests (npm test)', out.returncode == 0, last)


# ------------------------------------------------------------------------------------------------------------------------------------- S1 and S2 in FlightGear
def fg():
    import phase8a_checks as P8
    import phase9a_checks as P9
    import phase9b_checks as B
    log = os.path.join(HERE, 'out', 'fg-ground-stage1.log')
    B.LOG = log
    P8.PORT = P9.PORT
    proc, took = P9.start(['--airport=EFHK'], log)
    if took is None:
        P9.stop(proc)
        add('S1', 'FlightGear starts', False, 'it did not come up (%s)' % log)
        return
    try:
        asyncio.run(fg_run(B, P9))
    finally:
        P9.stop(proc)


async def fg_run(B, P9):
    c = B.Station()
    await c.connect()
    c.listen_to('/gcs/down/ack', '/gcs/down/status')
    for _ in range(4):
        c.heartbeat()
        await asyncio.sleep(0.5)
    t0 = time.time()
    a = await c.say('airport', dict(icao='EFHK'), wait=10)
    took = time.time() - t0
    raw = B.get('/gcs/down/airport') or ''
    n = json.loads(raw) if raw else {}
    p = AD.load('EFHK')
    worst = 0.0
    for x, y in zip(n.get('parking', []), p['parking']):
        worst = max(worst, abs(x['lat'] - y['lat']), abs(x['lon'] - y['lon']), abs(x['h'] - y['h']), abs(x['r'] - y['r']))
        if x['n'] != y['n'] or x['t'] != y['t']:
            worst = 9e9
    for x, y in zip(n.get('nodes', []), p['nodes']):
        worst = max(worst, abs(x[0] - y[0]), abs(x[1] - y[1]))
    add('S1.7', 'EFHK from FlightGear\'s Nasal: answered, under 2 s, 100 kB, 117 stands', bool(a) and a['status'] == 'accepted' and took < 2.0 and 0 < len(raw) <= 100000 and len(n.get('parking', [])) == 117,
        '%s in %.2f s, %d bytes, %d stands, %d nodes, %d arcs, %d runway ends' % (a and a['status'], took, len(raw), len(n.get('parking', [])), len(n.get('nodes', [])), len(n.get('arcs', [])), len(n.get('runways', []))))
    add('S1.8', 'counts equal the Python reader\'s; positions within 1e-6 deg', all(len(n.get(k, [])) == len(p[k]) for k in ('parking', 'nodes', 'arcs', 'names', 'runways')) and worst <= 1e-6,
        'worst difference %.2g deg' % worst)
    add('S1.9', 'the arcs, the names and the runway ends are the Python reader\'s', n.get('arcs') == p['arcs'] and n.get('names') == p['names'] and n.get('runways') == p['runways'],
        'arcs equal %s, names equal %s, runways equal %s' % (n.get('arcs') == p['arcs'], n.get('names') == p['names'], n.get('runways') == p['runways']))
    same = True
    detail = []
    for args in (dict(icao='ZZZZ'), dict(icao='12'), {}, dict(icao='efhk')):
        a = await c.say('airport', args, wait=6)
        try:
            AD.load(args.get('icao'))
            want = ''
        except ValueError as e:
            want = str(e)
        same = same and bool(a) and a['reason'] == want
        detail.append('%s -> %s' % (args or '{}', (a or {}).get('reason') or 'accepted'))
    add('S1.10', 'the same refusals as the Python reader, in the same words', same, '; '.join(detail))
    # the move to a stand
    sp = GP.Net('EFHK').park[SPOT]
    before = (B.get('/position/latitude-deg'), B.get('/position/longitude-deg'))
    a = await c.say('reposition', dict(lat=sp['lat'], lon=sp['lon'], heading=sp['heading']), wait=90)
    end = time.time() + 120
    while time.time() < end and not B.get('/sim/sceneryloaded'):
        c.heartbeat()
        await asyncio.sleep(1)
    for _ in range(8):
        c.heartbeat()
        await asyncio.sleep(1.0)
    here = (B.get('/position/latitude-deg'), B.get('/position/longitude-deg'))
    off = feet(here, (sp['lat'], sp['lon']))
    hdg = B.get('/orientation/heading-deg')
    dh = abs((hdg - sp['heading'] + 180) % 360 - 180)
    mains, kt = B.get('/fdm/jsbsim/ap/on-mains'), B.get('/fdm/jsbsim/ap/ground-speed-kt')
    add('S2.7', 'FlightGear: reposition to stand %s within 40 ft, heading within 1 deg, on its wheels, still' % SPOT, bool(a) and off < 40 and dh < 1 and mains == 2 and kt < 0.5,
        'ack %s; %.1f ft from the stand (before: %.0f ft), heading %.1f off, mains %s, %.3f kt' % (a and a['status'], off, feet(before, (sp['lat'], sp['lon'])), dh, mains, kt))
    st = c.status()
    add('S2.8', 'the aircraft goes on answering and holds no plan', st.get('doing') == 'no plan' and not st.get('started'), 'doing "%s"' % st.get('doing'))
    over, failed = B.get(J + 'limits/overstress'), B.get(J + 'limits/failed')
    alerts = [al.get('text') for al in c.status().get('alerts', [])]
    add('S2.8b', 'no STRUCTURAL LIMIT PASSED after the move (the latches were found set 2026-11-16)', over == 0 and failed == 0 and not alerts, 'overstress %s, failed %s, alerts %s' % (over, failed, alerts or 'none'))
    ok = await c.say('reposition', dict(lat=sp['lat'], lon=sp['lon'], heading=sp['heading']), wait=90)
    add('S2.9', 'and again to the same stand', bool(ok) and ok['status'] == 'accepted', str(ok and ok['reason'] or 'accepted'))
    bad = B.nasal_errors()
    end = time.time() + 120
    while time.time() < end and not B.get('/sim/sceneryloaded'):
        c.heartbeat()
        await asyncio.sleep(1)
    for _ in range(12):
        c.heartbeat()
        await asyncio.sleep(1.0)
    over2, failed2 = B.get(J + 'limits/overstress'), B.get(J + 'limits/failed')
    add('S2.9b', 'nor after the second move', over2 == 0 and failed2 == 0, 'overstress %s, failed %s' % (over2, failed2))
    add('S2.10', 'no Nasal error in FlightGear\'s log', not bad, '; '.join(bad[:3]) or 'none')


def main():
    if 'fg' in sys.argv[1:]:
        fg()
    else:
        s1_python()
        s2_python()
        s3()
        s4_plans()
        r_runways()
        node_tests()
    out = os.path.join(HERE, 'out', 'ground_checks%s.txt' % ('_fg' if 'fg' in sys.argv[1:] else ''))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as fh:
        for r in rows:
            fh.write('%-5s %-62s %-5s %s\n' % r)
    print('%d checks, %d pass, %d miss' % (len(rows), sum(r[2] == 'pass' for r in rows), sum(r[2] != 'pass' for r in rows)))


if __name__ == '__main__':
    main()
