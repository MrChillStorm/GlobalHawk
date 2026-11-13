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

// ---- the map's projection, north up and track up (the station gaps)
{
  const centre = [60.3, 25.0];
  const size = [800, 600];
  const fpp = 400;
  for (const up of [0, 37, 90, 180, 271.5, 359]) {
    for (const p of [[60.3, 25.0], [60.35, 25.1], [60.1, 24.7], [60.45, 25.4]]) {
      const [x, y] = g.toScreen(p, centre, up, fpp, size);
      const back = g.fromScreen(x, y, centre, up, fpp, size);
      const off = g.course(p, back).ft;
      assert.ok(off < 0.5, `round trip ${up} deg: ${off} ft`);
    }
  }
  // north up: north is up the screen, east is right
  let [x, y] = g.toScreen([60.31, 25.0], centre, 0, fpp, size);
  assert.ok(Math.abs(x - 400) < 1e-6 && y < 300);
  [x, y] = g.toScreen([60.3, 25.01], centre, 0, fpp, size);
  assert.ok(y === 300 && x > 400);
  // heading up: a point straight ahead of an aircraft on 090 (east) is straight up the screen, one to its right is to the right
  [x, y] = g.toScreen([60.3, 25.02], centre, 90, fpp, size);
  assert.ok(Math.abs(x - 400) < 1e-6 && y < 300, 'ahead is up');
  [x, y] = g.toScreen([60.28, 25.0], centre, 90, fpp, size);                 // south is to the right of an aircraft flying east
  assert.ok(Math.abs(y - 300) < 1e-6 && x > 400, 'right is right');
  // distances on the screen are the same whichever way it is turned
  const d0 = Math.hypot(...[0, 1].map((i) => g.toScreen([60.4, 25.2], centre, 0, fpp, size)[i] - g.toScreen([60.2, 24.9], centre, 0, fpp, size)[i]));
  const d1 = Math.hypot(...[0, 1].map((i) => g.toScreen([60.4, 25.2], centre, 123, fpp, size)[i] - g.toScreen([60.2, 24.9], centre, 123, fpp, size)[i]));
  assert.ok(Math.abs(d0 - d1) < 1e-6);
  // a click in track up lands where north up puts the same place: the same point of the earth, within a foot
  const p = [60.37, 25.08];
  const click = g.toScreen(p, centre, 213, fpp, size);
  const there = g.fromScreen(click[0], click[1], centre, 213, fpp, size);
  assert.ok(g.course(p, there).ft < 1);
}
console.log('geo: projection ok');
