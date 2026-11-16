// node tests/demo.test.js : the stand-in aircraft of ?demo=1 keeps the link's contract
const assert = require('assert');
const { DemoAircraft } = require('../js/demo.js');
const plan = require('../js/demoplan.js');
const pc = require('../js/plancheck.js');
const pr = require('../js/predict.js').make(require('../js/perfdata.js'));
const copy = (x) => JSON.parse(JSON.stringify(x));

function rig() {
  const d = new DemoAircraft();
  d.manual = true; // no clock: the test advances it
  let seq = 0;
  let beat = 0;
  const cmd = (name, args, station) => {
    d.send('/gcs/up/cmd', JSON.stringify({ seq: ++seq, station: station || 'T', name, args: args || {} }));
    return JSON.parse(d.down['/gcs/down/ack']);
  };
  const run = (sec, silent) => {
    for (let i = 0; i < sec; i++) {
      if (!silent) d.send('/gcs/up/heartbeat', 'T:' + ++beat);
      d.advance(1);
    }
    return JSON.parse(d.down['/gcs/down/status']);
  };
  const until = (cond, limit, silent) => {
    let n = 0;
    while (!cond(JSON.parse(d.down['/gcs/down/status'])) && n < limit) {
      run(1, silent);
      n += 1;
    }
    return n < limit ? n : null;
  };
  return { d, cmd, run, until };
}

// refusals, with the aircraft's words
{
  const r = rig();
  assert.strictEqual(r.cmd('start').reason, 'no plan');
  assert.strictEqual(r.cmd('goto', { lat: 35, lon: -117, alt_ft: 20000 }).reason, 'only while enroute');
  const bad = copy(plan);
  bad.items[2].points[0][2] = 70000;
  assert.strictEqual(r.cmd('plan', bad).reason, pc.checkPlan(bad));
  assert.strictEqual(r.cmd('plan', plan).status, 'accepted');
  assert.deepStrictEqual(JSON.parse(r.d.down['/gcs/down/plan']), plan);
  assert.strictEqual(r.cmd('start').status, 'accepted');
  assert.strictEqual(r.cmd('start').reason, 'the plan has already begun');
  assert.strictEqual(r.cmd('hold', {}, 'OTHER').reason, 'T has control');
  assert.ok(/not in the demo/.test(r.cmd('manual', { mode: 1 }).reason));
  // a repeated seq is answered once
  const n = r.d.events.length;
  r.d.send('/gcs/up/cmd', JSON.stringify({ seq: 1, station: 'T', name: 'start' }));
  assert.strictEqual(r.d.events.length, n);
}
// the demo plan from start to stopped on the runway, against the forecast
{
  const r = rig();
  r.cmd('plan', plan);
  r.cmd('start');
  const kinds = [];
  const t = r.until((s) => {
    if (kinds[kinds.length - 1] !== s.kind) kinds.push(s.kind);
    return s.kind === 'done';
  }, 4 * 3600);
  assert.deepStrictEqual(kinds, ['taxi', 'takeoff', 'route', 'land', 'done']);
  const legs = pc.legs(plan.items, plan.field.stand, plan.field.elev_ft);
  const fc = pr.predict(legs, { alt_ft: plan.field.elev_ft, weight_lb: 25600, fuel_lb: 14150 });
  const flown = t - 60; // the forecast starts at the takeoff: about a minute of taxi comes before it
  assert.ok(Math.abs(flown / fc.total.t_s - 1) < 0.15, `demo ${(flown / 60).toFixed(1)} min, forecast ${(fc.total.t_s / 60).toFixed(1)}`);
  assert.ok(Math.abs(r.d.s.alt - plan.field.elev_ft) < 10 && r.d.s.tas === 0);
  const used = 14150 - r.d.s.fuel;
  assert.ok(Math.abs(used / fc.total.fuel_used_lb - 1) < 0.2, `fuel ${used.toFixed(0)} against ${fc.total.fuel_used_lb.toFixed(0)}`);
  console.log(`  demo plan: ${(t / 60).toFixed(1)} min in all, ${used.toFixed(0)} lb; forecast from the takeoff ${(fc.total.t_s / 60).toFixed(1)} min, ${fc.total.fuel_used_lb.toFixed(0)} lb`);
}
// go to, hold, altitude, resume
{
  const r = rig();
  r.cmd('plan', plan);
  r.cmd('start');
  r.until((s) => s.kind === 'route' && r.d.s.alt > 15000, 3600);
  const target = { lat: 35.42, lon: -117.45, alt_ft: 18000 };
  assert.strictEqual(r.cmd('goto', target).status, 'accepted');
  assert.ok(r.until((s) => s.kind === 'hold', 3600) !== null);
  let s = r.run(400);
  assert.strictEqual(s.off_plan, 'goto');
  assert.ok(Math.abs(r.d.s.alt - 18000) < 200, 'height ' + r.d.s.alt);
  const geo = require('../js/geo.js');
  const off = Math.abs(geo.course([target.lat, target.lon], [r.d.s.lat, r.d.s.lon]).ft - s.hold.radius_ft) / geo.NM;
  assert.ok(off < 0.5, 'off the circle ' + off.toFixed(2));
  assert.strictEqual(r.cmd('altitude', { alt_ft: 70000 }).status, 'rejected');
  r.cmd('altitude', { alt_ft: 19500 });
  r.run(300);
  assert.ok(Math.abs(r.d.s.alt - 19500) < 200);
  assert.strictEqual(r.cmd('resume').status, 'accepted');
  s = r.run(5);
  assert.strictEqual(s.kind, 'route');
  assert.strictEqual(s.off_plan, null);
  assert.strictEqual(r.cmd('resume').reason, 'not off the plan');
  // silence: 30 s later it turns for home, and lands
  const quiet = r.until((x) => x.contingency === 'link', 60, true);
  assert.ok(quiet !== null && Math.abs(quiet - 30) <= 2, 'lost link after ' + quiet);
  assert.ok(JSON.parse(r.d.down['/gcs/down/status']).alerts.some((a) => a.id === 'link'));
  assert.ok(r.until((x) => x.kind === 'done', 2 * 3600, true) !== null);
  assert.ok(Math.abs(r.d.s.alt - plan.field.elev_ft) < 10);
}
// the engine fails in reach: on the runway; out of reach: the alert
{
  const r = rig();
  r.cmd('plan', plan);
  r.cmd('start');
  r.until((s) => s.kind === 'route' && r.d.s.alt > 18000, 3600);
  r.d.send('/fdm/jsbsim/engine/failed', 1);
  let s = r.run(3);
  assert.strictEqual(s.contingency, 'engine');
  assert.ok(s.alerts.some((a) => a.id === 'engine' && /Demo field 04/.test(a.action)));
  assert.ok(!s.alerts.some((a) => a.id === 'no-site'));
  assert.strictEqual(r.cmd('resume').reason, 'the engine has failed');
  assert.ok(r.until((x) => x.kind === 'done', 2 * 3600) !== null, 'never landed');
  const geo = require('../js/geo.js');
  assert.ok(geo.course([r.d.s.lat, r.d.s.lon], plan.sites[0].aim).ft < 6000, 'stopped ' + geo.course([r.d.s.lat, r.d.s.lon], plan.sites[0].aim).ft + ' ft from the aiming point');
  const far = copy(plan);
  far.sites = [{ name: 'Far away', aim: [41, -110], course: 90, elev_ft: 4000 }];
  const q = rig();
  q.cmd('plan', far);
  q.cmd('start');
  q.until((x) => x.kind === 'route' && q.d.s.alt > 10000, 3600);
  q.d.send('/fdm/jsbsim/engine/failed', 1);
  s = q.run(3);
  assert.ok(s.alerts.some((a) => a.id === 'no-site'));
}
// the lost-link time-out set from the station: bounds as the aircraft's, and the loss at the time set
{
  const r = rig();
  assert.strictEqual(r.cmd('plan', copy(plan)).status, 'accepted');
  assert.strictEqual(r.cmd('start').status, 'accepted');
  r.run(5);
  for (const bad of [{ sec: 5 }, { sec: 400 }, { sec: 'abc' }, {}, { sec: NaN }]) assert.strictEqual(r.cmd('linktimeout', bad).status, 'rejected', JSON.stringify(bad));
  assert.strictEqual(r.cmd('linktimeout', { sec: 15 }, 'OTHER').status, 'rejected');          // not the station in control
  assert.strictEqual(r.cmd('linktimeout', { sec: 15 }).status, 'accepted');
  assert.strictEqual(r.run(1).link_timeout, 15);
  const n = r.until((s) => s.link_lost, 60, true);
  assert.ok(n >= 14 && n <= 17, 'lost after ' + n + ' s of silence');
  assert.strictEqual(r.cmd('linktimeout', { sec: 30 }).status, 'accepted');
}
// the ground map and the move to a stand (stage 1 of starting at a stand from the planner)
{
  const demoground = require('../js/demoground.js');
  const r = rig();
  assert.strictEqual(r.d.down['/gcs/down/airport'], '', 'nothing until asked');
  assert.ok(/four letters or digits/.test(r.cmd('airport', {}).reason));
  assert.ok(/four letters or digits/.test(r.cmd('airport', { icao: '12' }).reason));
  assert.strictEqual(r.cmd('airport', { icao: 'ZZZZ' }).reason, 'no ground network for ZZZZ in the scenery');
  assert.strictEqual(r.cmd('airport', { icao: 'xdm1' }).status, 'accepted');
  assert.deepStrictEqual(JSON.parse(r.d.down['/gcs/down/airport']), demoground);
  assert.strictEqual(r.cmd('airport', { icao: 'XDM1' }, 'OTHER').status, 'accepted', 'a station that does not hold control may read the map');
  assert.strictEqual(r.cmd('reposition', { lat: 34.9, lon: -117.8, heading: 10 }, 'OTHER').reason, 'T has control');
  assert.strictEqual(r.cmd('reposition', {}).reason, 'reposition: a point needs 2 numbers');
  assert.strictEqual(r.cmd('reposition', { lat: 95, lon: 0, heading: 0 }).reason, 'reposition: latitude 95 is not on the earth');
  assert.strictEqual(r.cmd('reposition', { lat: 34.9, lon: -117.8 }).reason, 'reposition: the heading is not a number');
  const s2 = demoground.parking[1];
  assert.strictEqual(r.cmd('reposition', { lat: s2.lat, lon: s2.lon, heading: s2.h }).status, 'accepted');
  assert.strictEqual(r.d.get('/position/latitude-deg'), s2.lat);
  assert.strictEqual(r.d.get('/position/longitude-deg'), s2.lon);
  assert.strictEqual(r.d.get('/orientation/heading-deg'), s2.h);
  r.cmd('plan', plan);
  r.cmd('start');
  assert.strictEqual(r.cmd('reposition', { lat: s2.lat, lon: s2.lon, heading: s2.h }).reason, 'the plan has begun');
}
// holds on a taxi item: the aircraft stops at each, says so, and goes on only when its id is cleared (docs/PLAN.md, "Hold points and clearances")
{
  const r = rig();
  const hp = copy(plan);
  hp.items[0].holds = [{ i: 0, id: 'H1', name: 'hold short of runway 04', kind: 'runway' }, { i: 1, id: 'H2', name: 'line up on runway 04', kind: 'takeoff' }];
  assert.strictEqual(r.cmd('plan', hp).status, 'accepted');
  const bad = copy(hp);
  bad.items[0].holds[1].i = 0;
  assert.ok(/point 1 is a hold already/.test(r.cmd('plan', bad).reason));
  assert.strictEqual(r.cmd('clear', { id: 'H1' }).reason, 'the plan has not begun');
  assert.strictEqual(r.cmd('start').status, 'accepted');
  assert.strictEqual(r.cmd('clear', { id: 'H1' }).reason, 'the aircraft is not waiting at a hold');
  assert.ok(r.until((s) => s.wait, 120), 'it stops at the first hold');
  let s = JSON.parse(r.d.down['/gcs/down/status']);
  assert.deepStrictEqual(Object.keys(s.wait).sort(), ['id', 'kind', 'name', 'since']);
  assert.strictEqual(s.wait.id, 'H1');
  assert.strictEqual(s.doing, 'HOLD: waiting for clearance: hold short of runway 04');
  assert.ok(s.alerts.some((a) => a.id === 'hold' && a.level === 'advisory' && /way is clear/.test(a.action)));
  const lat = r.d.get('/position/latitude-deg');
  s = r.run(30);
  assert.strictEqual(r.d.get('/position/latitude-deg'), lat, 'it does not move');
  assert.strictEqual(s.wait.id, 'H1', 'it waits as long as it is not cleared');
  assert.strictEqual(r.cmd('clear', { id: 'H2' }).reason, 'the aircraft is waiting at H1 (hold short of runway 04), not H2');
  assert.strictEqual(r.cmd('clear', {}).reason, 'clear: a hold is cleared by its id');
  assert.strictEqual(r.cmd('clear', { id: 'H1' }, 'OTHER').reason, 'T has control');
  assert.strictEqual(r.cmd('clear', { id: 'H1' }).status, 'accepted');
  assert.strictEqual(JSON.parse(r.d.down['/gcs/down/status']).wait, null, 'gone at once');
  assert.strictEqual(r.cmd('clear', { id: 'H1' }).reason, 'the aircraft is not waiting at a hold', 'a hold is cleared once');
  assert.ok(r.until((x) => x.wait && x.wait.id === 'H2', 120), 'and stops at the second, the item\'s last point');
  s = JSON.parse(r.d.down['/gcs/down/status']);
  assert.strictEqual(s.kind, 'taxi', 'the takeoff does not begin by itself');
  r.run(20);
  assert.strictEqual(JSON.parse(r.d.down['/gcs/down/status']).kind, 'taxi');
  assert.strictEqual(r.cmd('clear', { id: 'H2' }).status, 'accepted');
  assert.strictEqual(JSON.parse(r.d.down['/gcs/down/status']).kind, 'takeoff', 'cleared for takeoff');
  assert.deepStrictEqual(r.d.events.map((e) => e[1]).filter((e) => /^(holding|cleared)/.test(e)), ['holding at H1: hold short of runway 04', 'cleared at H1', 'holding at H2: line up on runway 04', 'cleared at H2']);
}
console.log('demo OK');
