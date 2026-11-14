// node tests/linkrange.test.js
// L6 of the map-layers plan (docs/PLAN.md): the radio horizon and the rule that shows it.
const assert = require('assert');
const L = require('../js/linkrange.js');
const geo = require('../js/geo.js');

// 1.23 (sqrt 60,000 + sqrt 30) = 308 nmi
assert.ok(Math.abs(L.horizonNm(60000, 30) - 1.23 * (Math.sqrt(60000) + Math.sqrt(30))) < 1e-9);
assert.strictEqual(Math.round(L.horizonNm(60000, 30)), 308);
assert.strictEqual(Math.round(L.horizonNm(20000, 30)), 181);
assert.strictEqual(Math.round(L.horizonNm(0, 30)), 7);
assert.ok(L.horizonNm(-5, 30) >= 0, 'below the ground is not a negative range');
// the station's field height is taken off
assert.strictEqual(Math.round(L.rangeNm(62300, 2300)), 308);

// which stations need line of sight
assert.strictEqual(L.isLineOfSight('LRE', 0), true);
assert.strictEqual(L.isLineOfSight('MCE', 0), false);
assert.strictEqual(L.isLineOfSight('mce-2', 0), false);
assert.strictEqual(L.isLineOfSight('LRE', 600), false, '600 ms and over is a satellite');
assert.strictEqual(L.isLineOfSight('LRE', 599), true);
assert.strictEqual(L.isLineOfSight('OPS', 0), true, 'unknown names: line of sight');

// the forced rule: 85 % and "the path reaches the ring within 10 min", not otherwise
const st = [35, -118];
const elev = 2300;
const alt = 40000;
const range = L.rangeNm(alt, elev);
const at = (nm) => { const p = geo.along(st, 90, nm * geo.NM); return { lat: p[0], lon: p[1], alt_ft: alt }; };
{
  let m = L.margin(st, elev, at(0.84 * range), null, 300);
  assert.ok(Math.abs(m.frac - 0.84) < 0.005);
  assert.strictEqual(L.rule(true, m), null, '84 %: nothing');
  m = L.margin(st, elev, at(0.86 * range), null, 300);
  const r = L.rule(true, m);
  assert.ok(r && r.force && r.on, '86 %: forced');
  assert.ok(/line-of-sight limit \d+ nmi at this height: the aircraft is at \d+ nmi/.test(r.reason), r.reason);
  // 85 % exactly
  assert.ok(L.rule(true, L.margin(st, elev, at(0.85 * range + 0.01), null, 300)));
  // a satellite station: never
  assert.strictEqual(L.rule(false, L.margin(st, elev, at(0.99 * range), null, 300)), null);
}
// the path: 70 % out, flying outward at 300 kt; the ring is 30 % of 252 nmi (about 76 nmi) away = 15 min
{
  const own = at(0.7 * range);
  const out = [own, at(1.5 * range)];
  let m = L.margin(st, elev, own, out, 300);
  assert.ok(Math.abs(m.cross_nm - 0.3 * range) < 2.5, 'crosses ' + m.cross_nm + ' nmi along, expected ' + 0.3 * range);
  assert.ok(Math.abs(m.cross_min - (m.cross_nm / 300) * 60) < 1e-9);
  assert.strictEqual(L.rule(true, m), null, '15 minutes away: not yet');
  const own2 = at(0.8 * range);
  m = L.margin(st, elev, own2, [own2, at(1.5 * range)], 300);
  assert.ok(m.cross_min <= 10 && m.cross_min > 7, 'about ' + (0.2 * range / 300 * 60).toFixed(1) + ' min: ' + m.cross_min);
  const r = L.rule(true, m);
  assert.ok(r && r.force, 'inside 10 minutes of the ring: forced');
  assert.ok(/leaves the line-of-sight range in \d+ min/.test(r.reason), r.reason);
  // a path that climbs: the ring grows with the height, so the same ground distance can stay inside
  const climbing = [at(0.8 * range), Object.assign(at(0.95 * range), { alt_ft: 60000 })];
  m = L.margin(st, elev, climbing[0], climbing, 300);
  assert.strictEqual(m.cross_nm, null, 'at 60,000 ft the range is 308 nmi, further than the path goes');
  // flying home: nothing to cross
  m = L.margin(st, elev, at(0.7 * range), [at(0.7 * range), at(0.1 * range)], 300);
  assert.strictEqual(m.cross_nm, null);
  // no speed: no minutes, so only the 85 % applies
  m = L.margin(st, elev, at(0.8 * range), [at(0.8 * range), at(1.5 * range)], 0);
  assert.strictEqual(m.cross_min, null);
  assert.strictEqual(L.rule(true, m), null);
}
console.log('linkrange: ok');
