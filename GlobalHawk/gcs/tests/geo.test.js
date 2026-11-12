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
