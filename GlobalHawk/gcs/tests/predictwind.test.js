// node tests/predictwind.test.js
// R1 of the route planner's limits (docs/PLAN.md): the forecast's wind option. No wind: nothing changes. A wind: the ground speed, the time and the fuel.
const assert = require('assert');
const NEW = require('../js/predict.js');
const OLD = require('./fixtures/predict-before-wind.js');
const perf = require('../js/perfdata.js');
const pc = require('../js/plancheck.js');
const geo = require('../js/geo.js');
const plan = require('../js/demoplan.js');
const fcNew = NEW.make(perf);
const fcOld = OLD.make(perf);

// no wind, no change: the demo plan and six random plans, compared as JSON
{
  const st = { alt_ft: 2300, weight_lb: 25600, fuel_lb: 14150 };
  const legs = pc.legs(plan.items, plan.field.stand, plan.field);
  assert.strictEqual(JSON.stringify(fcNew.predict(legs, st)), JSON.stringify(fcOld.predict(legs, st)), 'the demo plan');
  assert.strictEqual(JSON.stringify(fcNew.predict(legs, st, {})), JSON.stringify(fcOld.predict(legs, st)), 'with empty options');
  assert.strictEqual(JSON.stringify(fcNew.predict(legs, st, { wind: null, hours: 5 })), JSON.stringify(fcOld.predict(legs, st)), 'with no wind');
  let seed = 7;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  for (let k = 0; k < 6; k++) {
    const n = 3 + Math.floor(rnd() * 4);
    const pts = [];
    let p = [34.9, -117.88];
    for (let i = 0; i < n; i++) {
      p = geo.along(p, rnd() * 360, (20 + rnd() * 120) * geo.NM);
      pts.push([p[0], p[1], 8000 + Math.floor(rnd() * 11) * 5000]);
    }
    const items = [{ kind: 'takeoff', start: [34.9, -117.88], end: [34.92, -117.86] }, { kind: 'route', points: pts }, { kind: 'land', fix: [34.7, -118.1], aim: [34.9, -117.88] }];
    const l = pc.legs(items, null, plan.field);
    assert.strictEqual(JSON.stringify(fcNew.predict(l, st)), JSON.stringify(fcOld.predict(l, st)), `random plan ${k + 1}`);
  }
}

// a level leg of 100 nmi at 40,000 ft heading east
const from = [35, -118];
const at = geo.along(from, 90, 100 * geo.NM);
const leg = { dist_ft: 100 * geo.NM, alt_ft: 40000, from, at, name: '1' };
const st = { alt_ft: 40000, weight_lb: 22000, fuel_lb: 9000 };
const base = fcNew.predict([leg], st);
const tas = fcNew.ktas(40000);
const hoursOf = (r) => r.total.t_s / 3600;
assert.ok(Math.abs(hoursOf(base) - 100 / tas) / (100 / tas) < 0.01, 'no wind: 100 nmi at the true airspeed');
for (const [name, dir, kt] of [['tailwind', 270, 60], ['headwind', 90, 60], ['strong tailwind', 270, 100]]) {
  const sign = dir === 270 ? 1 : -1;
  const r = fcNew.predict([leg], st, { wind: () => ({ spd: kt, dir }) });
  const want = 100 / (tas + sign * kt);
  assert.ok(Math.abs(hoursOf(r) - want) / want < 0.01, `${name}: ${hoursOf(r).toFixed(4)} h against ${want.toFixed(4)} h`);
  // the fuel follows the time: the same flow, a different number of hours
  const ratio = r.total.fuel_used_lb / base.total.fuel_used_lb;
  assert.ok(Math.abs(ratio - hoursOf(r) / hoursOf(base)) < 0.015, `${name}: fuel ratio ${ratio.toFixed(4)} against time ratio ${(hoursOf(r) / hoursOf(base)).toFixed(4)}`);
  assert.ok(Math.abs(r.total.dist_ft - 100 * geo.NM) < 200, 'the distance over the ground is the leg');
}
// a tailwind saves, a headwind costs
{
  const tail = fcNew.predict([leg], st, { wind: () => ({ spd: 60, dir: 270 }) });
  const head = fcNew.predict([leg], st, { wind: () => ({ spd: 60, dir: 90 }) });
  assert.ok(tail.total.fuel_used_lb < base.total.fuel_used_lb && head.total.fuel_used_lb > base.total.fuel_used_lb);
  // a crosswind: nothing changes (the aircraft crabs and keeps its track)
  const cross = fcNew.predict([leg], st, { wind: () => ({ spd: 60, dir: 0 }) });
  assert.ok(Math.abs(cross.total.t_s - base.total.t_s) / base.total.t_s < 1e-6, 'a crosswind changes nothing');
  // a wind the function cannot give (null, NaN): the leg is flown as if calm
  const none = fcNew.predict([leg], st, { wind: () => null });
  assert.strictEqual(JSON.stringify(none), JSON.stringify(base));
  const nan = fcNew.predict([leg], st, { wind: () => ({ spd: NaN, dir: 270 }) });
  assert.strictEqual(JSON.stringify(nan), JSON.stringify(base));
  // a headwind stronger than the aircraft's speed: it still moves (the floor is 30 kt)
  const gale = fcNew.predict([leg], st, { wind: () => ({ spd: 600, dir: 90 }) });
  assert.ok(Number.isFinite(gale.total.t_s) && gale.total.t_s > 3 * base.total.t_s);
}
// the wind function is asked where and when: along the leg, at its height, at the hour
{
  const asked = [];
  fcNew.predict([leg], st, { hours: 3, wind: (la, lo, alt, h) => { asked.push([la, lo, alt, h]); return { spd: 20, dir: 270 }; } });
  assert.ok(asked.length > 5);
  assert.ok(Math.abs(asked[0][0] - 35) < 0.01 && Math.abs(asked[0][1] + 118) < 0.01, 'first asked at the start');
  assert.ok(asked.every((a) => Math.abs(a[0] - 35) < 0.02 && a[1] >= -118.001 && a[1] <= at[1] + 0.001), 'along the leg');
  assert.ok(asked.every((a) => Math.abs(a[2] - 40000) < 1));
  assert.ok(Math.abs(asked[0][3] - 3) < 0.01 && asked[asked.length - 1][3] > 3.1 && asked[asked.length - 1][3] < 3.5, 'the hour moves on with the flight');
  // a wind that changes with place: the first half calm, the second a tailwind
  const half = fcNew.predict([leg], st, { wind: (la, lo) => (lo > (from[1] + at[1]) / 2 ? { spd: 60, dir: 270 } : null) });
  const tail = fcNew.predict([leg], st, { wind: () => ({ spd: 60, dir: 270 }) });
  assert.ok(half.total.t_s < base.total.t_s && half.total.t_s > tail.total.t_s, 'a tailwind over half of it is in between');
}
// a landing leg is flown without wind (the surface wind is not the wind aloft)
{
  const items = [{ kind: 'route', points: [[34.95, -117.5, 20000]] }, { kind: 'land', fix: [34.7, -118.1], aim: [34.9, -117.88] }];
  const l = pc.legs(items, [34.9, -117.88], plan.field);
  const calm = fcNew.predict(l, { alt_ft: 20000, weight_lb: 20000, fuel_lb: 8000 });
  const w = fcNew.predict(l, { alt_ft: 20000, weight_lb: 20000, fuel_lb: 8000 }, { wind: () => ({ spd: 50, dir: 270 }) });
  const lastCalm = calm.points[calm.points.length - 1];
  const lastW = w.points[w.points.length - 1];
  assert.ok(lastW.t_s !== lastCalm.t_s, 'the legs before the landing feel the wind');
  const finalCalm = calm.points[calm.points.length - 1].t_s - calm.points[calm.points.length - 2].t_s;
  const finalW = w.points[w.points.length - 1].t_s - w.points[w.points.length - 2].t_s;
  // (the approach speed is the aircraft's own for the weight it arrives with, and that differs by the fuel the wind cost on the legs before: a fraction of a second)
  assert.ok(Math.abs(finalCalm - finalW) < 0.5, 'the final approach takes as long: ' + finalCalm + ' ' + finalW);
}
// the legs know where they start
{
  const legs = pc.legs(plan.items, plan.field.stand, plan.field);
  assert.strictEqual(legs[0].from, undefined, 'a takeoff leg has none');
  assert.deepStrictEqual(legs[1].from, plan.items[1].end);
  assert.deepStrictEqual(legs[2].from, [plan.items[2].points[0][0], plan.items[2].points[0][1]]);
  assert.ok(legs[5].from && legs[5].at, 'the fix leg has both');
}
console.log('predictwind: ok');
