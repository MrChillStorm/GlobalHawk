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
console.log('demo OK');
