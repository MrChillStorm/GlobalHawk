#!/usr/bin/env python3
"""Phase 8 part E checks: the traffic the server makes up reaches the page's reader; the demo's stand-in aircraft
against the real model; the demo plan in the page is the mission file.

    python3 fdm/phase8e_checks.py        about 10 s; needs node

The demo's own behaviour and the traffic alerting are tested in GlobalHawk/gcs/tests/ (demo.test.js, traffic.test.js).
"""
import json
import os
import sys
import urllib.request
import asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcs_server as G              # noqa: E402
import phase8c_checks as C          # noqa: E402

PORT = 5473
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))


def main():
    plan = json.load(open(C.PLAN))
    # T2: over HTTP from the server, into the page's reader
    sim = G.Sim(C.PLAN)
    server = G.Server(sim, 1.0)

    async def get():
        srv = await asyncio.start_server(server.handle, '127.0.0.1', PORT)
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json/ai/models?d=3' % PORT, timeout=3).read().decode()))
        finally:
            srv.close()
    tree = asyncio.run(get())
    got = C.node("const T = require('./js/traffic.js'); console.log(JSON.stringify(T.parse(input)));", tree)
    add('T2', 'the server\'s traffic reaches the page\'s reader', [a['callsign'] for a in got] == ['SHUTTLE1', 'HIGH22'] and got[0]['alt_ft'] == 20000 and got[0]['kt'] == 240,
        '%s' % ', '.join('%s at %.0f ft, %.0f kt on %03.0f' % (a['callsign'], a['alt_ft'], a['kt'], a['hdg']) for a in got))
    # the demo plan in the page is the mission file
    same = C.node("console.log(JSON.stringify(require('./js/demoplan.js')));", None) == plan
    add('D2', 'the page\'s demo plan is the mission file', same, 'js/demoplan.js equals Missions/demo-local.json: %s' % same)
    # D2: the stand-in against the model, start of the takeoff to touchdown
    t0, end = C.fly(plan, lambda f, m: f['ap/rollout'] == 1)
    demo = C.node("""
const { DemoAircraft } = require('./js/demo.js');
const d = new DemoAircraft(); d.manual = true;
d.send('/gcs/up/cmd', JSON.stringify({ seq: 1, station: 'T', name: 'plan', args: input }));
d.send('/gcs/up/cmd', JSON.stringify({ seq: 2, station: 'T', name: 'start' }));
let t0 = null, t1 = null, f0 = null, f1 = null;
for (let i = 0; i < 4 * 3600 * 4 && t1 === null; i++) {
  if (i % 4 === 0) d.send('/gcs/up/heartbeat', 'T:' + i);
  d.advance(0.25);
  const it = d.item();
  if (t0 === null && it.kind === 'takeoff') { t0 = d.s.t; f0 = d.s.fuel; }
  if (it.kind === 'land' && it.rollout) { t1 = d.s.t; f1 = d.s.fuel; }
}
console.log(JSON.stringify({ t: t1 - t0, fuel: f0 - f1 }));
""", plan)
    tm, fm = end['t'] - t0['t'], t0['fuel'] - end['fuel']
    add('D2', 'the demo\'s stand-in against the model', abs(demo['t'] / tm - 1) <= 0.10,
        'the demo plan, takeoff to touchdown: the stand-in %.1f min and %.0f lb, the model %.1f min and %.0f lb (%+.1f %%, %+.1f %%)' % (
            demo['t'] / 60, demo['fuel'], tm / 60, fm, 100 * (demo['t'] / tm - 1), 100 * (demo['fuel'] / fm - 1)))
    for tag, name, ok, detail in rows:
        print('%-3s %-46s %-5s %s' % (tag, name, ok, detail))
    miss = sum(1 for r in rows if r[2] == 'MISS')
    print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - miss, miss))


if __name__ == '__main__':
    main()
