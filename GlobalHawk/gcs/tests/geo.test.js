// node tests/geo.test.js
const assert = require('assert');
const g = require('../js/geo.js');
const near = (a, b, tol) => assert.ok(Math.abs(a - b) <= tol, `${a} vs ${b}`);

const a = [34.9, -117.88];
const b = g.along(a, 40, 25 * g.NM);
const c = g.course(a, b);
near(c.deg, 40, 0.05);
near(c.ft / g.NM, 25, 0.01);
near(g.turn(350, 10), 20, 1e-9);
near(g.turn(10, 350), -20, 1e-9);
near(g.turn(0, 180), -180, 1e-9);

const lines = g.planLines([
  { kind: 'taxi', points: [[1, 1], [1, 2]] },
  { kind: 'takeoff', start: [1, 2], end: [1, 3] },
  { kind: 'route', points: [[2, 3, 20000], [3, 3, 20000]] },
  { kind: 'land', fix: [3, 4], aim: [3, 5] },
], [0, 0]);
assert.deepStrictEqual(lines.map((l) => l.kind), ['taxi', 'takeoff', 'route', 'land']);
assert.deepStrictEqual(lines[0].points[0], [0, 0]);
assert.deepStrictEqual(lines[2].points, [[1, 3], [2, 3], [3, 3]]);
assert.deepStrictEqual(lines[3].points, [[3, 3], [3, 4], [3, 5]]);
console.log('geo OK');

// a local plan from where the aircraft stands: one the aircraft's own check accepts, wherever it is
const pc = require('../js/plancheck.js');
for (const [at, hdg, elev] of [[[60.3172, 24.9633], 43, 179], [[34.9, -117.88], 220, 2300], [[-33.9, 151.2], 355, 21]]) {
  const p = g.localPlan(at, hdg, elev);
  assert.strictEqual(pc.checkPlan(p), null);
  near(g.course(p.items[0].start, p.items[0].end).deg, hdg, 0.1);
  near(g.course(p.items[2].fix, p.items[2].aim).deg, hdg, 0.2);            // it lands the way it took off (the flat-earth courses differ a little 10 nmi apart)
  assert.ok(g.course(p.items[2].fix, p.items[2].aim).ft / g.NM > 8);
  assert.deepStrictEqual(p.lost_link[1], p.items[2]);
}
console.log('geo: local plan ok');
