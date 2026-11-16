#!/usr/bin/env python3
"""Stage 2 of "starting at a stand from the planner": the checks for the limits H1 to H7 in docs/PLAN.md ("Hold points and clearances"). H8 (the whole chain through the page against
FlightGear) is by hand in the browser pane and written up there.

    python3 hold_checks.py          headless: the plan check (the same words in JS and Python: phase8c C2c), the manager and the commands on the flight model, the station's derivation
                                    (against the made-up field XDM1 and, where the scenery has it, EFHK)
    python3 hold_checks.py fg       the same stops and clearances in FlightGear's Nasal (the screen must be unlocked): the taxi-box-taxi from stand 121 with the holds the station derives,
                                    each cleared when the aircraft has waited 20 s (about 11 minutes at 4x)
"""
import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import airportdata as AD            # noqa: E402
import gcs_server as G              # noqa: E402
import ground_checks as GC          # noqa: E402
import groundplan as GP             # noqa: E402
import harness as H                 # noqa: E402

GCS = os.path.join(HERE, '..', 'GlobalHawk', 'gcs')
MISSIONS = os.path.join(HERE, '..', 'GlobalHawk', 'Missions')
FT = 364567.2
import missionmgr as MM         # noqa: E402
NOSE_FT = MM.NOSE_FT
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))
    print('%-5s %-70s %-5s %s' % rows[-1], flush=True)


def feet(a, b):
    return math.hypot((a[0] - b[0]) * FT, (a[1] - b[1]) * FT * math.cos(math.radians(a[0])))


def short_by(pos, hold, prev):
    """How far short of the hold point the aircraft stands, ft along the way it came (negative: past it)."""
    cos = math.cos(math.radians(hold[0]))
    vn, ve = (hold[0] - prev[0]) * FT, (hold[1] - prev[1]) * FT * cos
    n = math.hypot(vn, ve)
    dn, de = (hold[0] - pos[0]) * FT, (hold[1] - pos[1]) * FT * cos
    return (dn * vn + de * ve) / n


# --------------------------------------------------------------------------------------------------------------------------------------------------- H5
def derive():
    """The station's holds at the made-up field and at EFHK."""
    demo = json.load(open(os.path.join(MISSIONS, 'demo-local.json')))
    xdm = AD.load('XDM1', [os.path.join(GCS, 'tests', 'fixtures', 'scenery')])
    s1 = xdm['parking'][0]
    r = GC.lay(xdm, demo, (s1['lat'], s1['lon']), s1['h'], True)
    taxi = [i for i in r['plan']['items'] if i['kind'] == 'taxi']
    hs = taxi[0].get('holds', [])
    add('H5.1', 'XDM1: a hold short of runway 04 on B and the takeoff hold; none on the way in', [(h['kind'], h['id']) for h in hs] == [('runway', 'H1'), ('takeoff', 'H2')] and 'holds' not in taxi[1]
        and hs[0]['name'] == 'hold short of runway 04 at B', '; '.join('%s %s (point %d)' % (h['id'], h['name'], h['i']) for h in hs))
    out = {'xdm': r['plan']}
    if GC.have_efhk():
        ref = json.load(open(os.path.join(MISSIONS, 'efhk-taxi-box-taxi.json')))
        sp = GP.Net('EFHK').park['121']
        e = GC.lay(AD.load('EFHK'), ref, (sp['lat'], sp['lon']), sp['heading'], True)
        et = [i for i in e['plan']['items'] if i['kind'] == 'taxi']
        eh = et[0].get('holds', [])
        names = [h['name'] for h in eh]
        add('H5.2', 'EFHK 121 to 22L: 15/33 crossed at Z, 22L entered at ZA, the takeoff hold; none on the way in',
            names == ['hold short of runway 15/33 at Z', 'hold short of runway 22L at ZA', 'lined up on runway 22L: cleared for takeoff'] and 'holds' not in et[1], '; '.join('%s %s' % (h['id'], h['name']) for h in eh))
        out['efhk'] = e['plan']
    return out


# --------------------------------------------------------------------------------------------------------------------------------------------------- H2 to H4, headless
def flight(plan):
    """The Python flight model on the field of the plan, the plan sent and started."""
    d = tempfile.mkdtemp()
    path = os.path.join(d, 'plan.json')
    json.dump(plan, open(path, 'w'))
    sim = G.Sim(path)
    seq = [0]

    def say(name, args, station='T'):
        seq[0] += 1
        sim.set('/gcs/up/cmd', json.dumps(dict(seq=seq[0], station=station, name=name, args=args)))
        return json.loads(sim.get('/gcs/down/ack'))

    def run(sec, beat=True):
        for n in range(int(sec * H.HZ)):
            sim.step()
            if beat and n % int(H.HZ) == 0:
                sim.set('/gcs/up/heartbeat', 'T:%d' % int(sim.f['simulation/sim-time-sec']))

    def st():
        return json.loads(sim.get('/gcs/down/status'))
    return sim, say, run, st


def until(run, st, cond, limit=300):
    for _ in range(limit // 2):
        run(2)
        if cond(st()):
            return True
    return False


def headless(plans):
    plan = plans['xdm']
    taxi = plan['items'][0]
    holds = taxi['holds']
    pts = [tuple(p) for p in taxi['points']]
    sim, say, run, st = flight(plan)
    f = sim.f
    pos = lambda: (f['position/lat-geod-deg'], f['position/long-gc-deg'])

    def nose():
        """Where the nose is, the position FlightGear gives the aircraft: NOSE_FT ahead of the centre of gravity."""
        c, p = math.radians(f['attitude/psi-deg']), pos()
        return (p[0] + NOSE_FT * math.cos(c) / FT, p[1] + NOSE_FT * math.sin(c) / (FT * math.cos(math.radians(p[0]))))
    a = say('plan', plan)
    add('H1', 'the plan with holds is accepted (Python check)', a['status'] == 'accepted', a['reason'] or 'accepted')
    pre = say('clear', dict(id='H1'))
    add('H3.1', 'clear before the plan has begun: refused', pre['status'] == 'rejected' and pre['reason'] == 'the plan has not begun', pre['reason'])
    say('start', {})
    nw = say('clear', dict(id='H1'))
    add('H3.2', 'clear while not waiting at a hold: refused', nw['reason'] == 'the aircraft is not waiting at a hold', nw['reason'])
    got = until(run, st, lambda s: s.get('wait'))
    run(5)                                           # it has stopped when the laws say so; settled a few seconds later
    s = st()
    h1 = pts[holds[0]['i']]
    prev = pts[holds[0]['i'] - 1]
    short = short_by(nose(), h1, prev)
    kt = f['ap/ground-speed-kt']
    add('H2.1', 'its nose stops at the first hold: within 15 ft short, not 3 ft past, under 0.3 kt', got and -3.0 <= short <= 15.0 and kt < 0.3, '%.1f ft short of %s, %.2f kt' % (short, holds[0]['id'], kt))
    add('H4.1', 'status.wait, doing, the advisory alert and the events say so', got and s['wait']['id'] == 'H1' and s['wait']['kind'] == 'runway' and s['doing'].startswith('HOLD: waiting for clearance: hold short')
        and any(al['id'] == 'hold' and al['level'] == 'advisory' and 'clear it' in al['action'] for al in s['alerts']) and any('holding at H1' in e[1] for e in s['events']), '%s | %s' % (s['doing'], [al['text'] for al in s['alerts']]))
    p0 = pos()
    run(60)
    drift = feet(pos(), p0)
    add('H2.2', 'it stays there for 60 s within 2 ft and does not take the next leg', drift <= 2.0 and st().get('wait', {}).get('id') == 'H1' and f['ap/ground-speed-kt'] < 0.3, '%.2f ft in 60 s, %.2f kt' % (drift, f['ap/ground-speed-kt']))
    wrong = say('clear', dict(id='H2'))
    noid = say('clear', {})
    other = say('clear', dict(id='H1'), station='OTHER')
    add('H3.3', 'refused: the wrong id (the right one named), no id, a station without control',
        wrong['reason'].startswith('the aircraft is waiting at H1 (hold short of runway 04 at B), not H2') and noid['reason'] == 'clear: a hold is cleared by its id' and other['reason'] == 'T has control', '%s | %s | %s' % (wrong['reason'], noid['reason'], other['reason']))
    ok = say('clear', dict(id='H1'))
    s = st()
    add('H3.4', 'the right id is accepted; the wait and the alert are gone at once', ok['status'] == 'accepted' and s['wait'] is None and not any(al['id'] == 'hold' for al in s['alerts']), '%s, wait %s' % (ok['status'], s['wait']))
    again = say('clear', dict(id='H1'))
    add('H3.5', 'cleared twice: the second is refused', again['reason'] == 'the aircraft is not waiting at a hold', again['reason'])
    run(10)
    add('H2.3', 'it moves at 3 kt or more within 10 s of the clearance', f['ap/ground-speed-kt'] >= 3.0, '%.1f kt' % f['ap/ground-speed-kt'])
    got = until(run, st, lambda s: s.get('wait'))
    run(5)
    s = st()
    h2 = pts[holds[1]['i']]
    short = short_by(nose(), h2, pts[holds[1]['i'] - 1])
    add('H2.4', 'it stops at the takeoff hold, the last point, within 15 ft short', got and s['wait']['id'] == 'H2' and s['kind'] == 'taxi' and -3.0 <= short <= 15.0 and f['ap/ground-speed-kt'] < 0.3,
        '%.1f ft short of %s, %.2f kt, item %s' % (short, holds[1]['id'], f['ap/ground-speed-kt'], s['kind']))
    run(20)
    add('H2.5', 'and the takeoff does not begin by itself in 20 s', st()['kind'] == 'taxi' and st()['wait'] is not None, st()['kind'])
    t0 = f['simulation/sim-time-sec']
    ok = say('clear', dict(id='H2'))
    s = st()
    run(5)
    add('H2.6', 'cleared: the takeoff begins at once and the roll has begun within 5 s', ok['status'] == 'accepted' and s['kind'] == 'takeoff' and f['ap/ground-speed-kt'] > 3.0, '%s, %s, %.1f kt after 5 s' % (ok['status'], s['kind'], f['ap/ground-speed-kt']))
    ev = [e[1] for e in sim.ob.mgr.events]            # the whole list: the status keeps the last six
    add('H2.7', 'the manager\'s events: holding and cleared at each, in order', [e for e in ev if e.startswith(('holding', 'cleared'))][-4:] == [
        'holding at H1: hold short of runway 04 at B', 'cleared at H1', 'holding at H2: lined up on runway 04: cleared for takeoff', 'cleared at H2'], str([e for e in ev if e.startswith(('holding', 'cleared'))]))
    # the link lost at a hold
    sim, say, run, st = flight(plan)
    f = sim.f
    say('plan', plan)
    say('start', {})
    until(run, st, lambda s: s.get('wait'))
    p0 = (f['position/lat-geod-deg'], f['position/long-gc-deg'])
    run(50, beat=False)
    s = st()
    ids = {al['id'] for al in s['alerts']}
    add('H4.2', 'link lost at a hold: it stays, the link alert stands beside the hold\'s', feet((f['position/lat-geod-deg'], f['position/long-gc-deg']), p0) <= 2.0 and s['wait'] and s['link_lost'] and {'link', 'hold'} <= ids,
        'moved %.2f ft in 50 s without the station; alerts %s' % (feet((f['position/lat-geod-deg'], f['position/long-gc-deg']), p0), sorted(ids)))


# --------------------------------------------------------------------------------------------------------------------------------------------------- H7: a plan without holds
def without():
    demo = json.load(open(os.path.join(MISSIONS, 'demo-local.json')))
    sim, say, run, st = flight(demo)
    say('plan', demo)
    say('start', {})
    run(1)
    got = until(run, st, lambda s: s['kind'] == 'takeoff', 300)
    s = st()
    add('H7.1', 'a plan with no holds taxis and takes off as before: no wait, no hold alert', got and s['wait'] is None and not any(al['id'] == 'hold' for al in s['alerts']), 'kind %s' % s['kind'])


def node_tests():
    out = subprocess.run(['npm', 'test'], cwd=GCS, capture_output=True, text=True)
    add('H6.1', 'the station\'s node tests: the derivation, the demo\'s holds, the plan check (npm test)', out.returncode == 0, (out.stdout.strip().splitlines() or [out.stderr[-150:]])[-1])


def main():
    plans = derive()
    if 'fg' not in sys.argv[1:]:
        headless(plans)
        without()
        node_tests()
    outp = os.path.join(HERE, 'out', 'hold_checks%s.txt' % ('_fg' if 'fg' in sys.argv[1:] else ''))
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    with open(outp, 'w') as fh:
        for r in rows:
            fh.write('%-5s %-70s %-5s %s\n' % r)
    print('%d checks, %d pass, %d miss' % (len(rows), sum(r[2] == 'pass' for r in rows), sum(r[2] != 'pass' for r in rows)))


if __name__ == '__main__':
    main()
