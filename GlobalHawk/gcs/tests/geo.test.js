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
  near(g.course(p.items[2].fix, p.items[2].aim).deg, hdg, 0.2);            // it lands the way it took off (a course read at the fix and one read at the runway differ a little 10 nmi apart)
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
  assert.ok(Math.abs(y - 300) < 0.01 && x > 400); // a point due east on the same parallel is a little below the tangent plane's east line (0.13 ft at 0.01 deg east, 60 deg N): within a hundredth of a pixel, not exactly level
  // heading up: a point straight ahead of an aircraft on 090 (east) is straight up the screen, one to its right is to the right
  [x, y] = g.toScreen([60.3, 25.02], centre, 90, fpp, size);
  assert.ok(Math.abs(x - 400) < 0.01 && y < 300, 'ahead is up'); // (due east on a parallel bends a little south of the plane's east line: 0.5 ft here, a hundredth of a pixel at most)
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

// ---- WGS84: the one geometry of the earth (fdm/wgs84.py is the reference; fdm/data/wgs84_vectors.json holds what it computed, to full precision)
{
  const fs = require('fs');
  const path = require('path');
  const file = process.env.WGS84_VECTORS || path.join(__dirname, '..', '..', '..', 'fdm', 'data', 'wgs84_vectors.json');
  assert.ok(fs.existsSync(file), `the vectors fdm/wgs84.py wrote are not at ${file} (WGS84_VECTORS names another place)`);
  const cases = JSON.parse(fs.readFileSync(file, 'utf8')).cases;
  assert.ok(cases.length >= 30);
  const FT = 1e-4; // ft
  const DEG = 1e-7; // deg of latitude or longitude, 0.04 ft
  let worst = { enu: 0, from: 0, dist: 0, brg: 0, along: 0, alongLL: 0 };
  const bump = (k, v) => { worst[k] = Math.max(worst[k], v); };
  for (const c of cases) {
    const tag = JSON.stringify(c.o) + ' ' + c.n + ' ' + c.e;
    // from_enu: the point at (n, e) ft
    const p = g.fromEnu(c.o, c.n, c.e);
    bump('from', Math.max(Math.abs(p[0] - c.p[0]), Math.abs(p[1] - c.p[1])));
    assert.ok(Math.abs(p[0] - c.p[0]) <= DEG && Math.abs(p[1] - c.p[1]) <= DEG, `fromEnu ${tag}: ${p} against ${c.p}`);
    // enu: north and east of that point, back
    const ne = g.enu(c.o, c.p);
    bump('enu', Math.max(Math.abs(ne[0] - c.enu[0]), Math.abs(ne[1] - c.enu[1])));
    assert.ok(Math.abs(ne[0] - c.enu[0]) <= FT && Math.abs(ne[1] - c.enu[1]) <= FT, `enu ${tag}: ${ne} against ${c.enu}`);
    // course and distance from the origin to that point
    const k = g.course(c.o, c.p);
    bump('dist', Math.abs(k.ft - c.dist));
    bump('brg', Math.abs(((k.deg - c.course + 540) % 360) - 180));
    assert.ok(Math.abs(k.ft - c.dist) <= FT, `course ft ${tag}: ${k.ft} against ${c.dist}`);
    assert.ok(Math.abs(((k.deg - c.course + 540) % 360) - 180) <= DEG, `course deg ${tag}: ${k.deg} against ${c.course}`);
    assert.ok(Math.abs(g.distance(c.o, c.p) - c.dist) <= FT);
    const kp = g.coursePrep(g.prep(c.o), g.prep(c.p)); // the prepared forms ask the same thing
    assert.ok(Math.abs(kp.ft - k.ft) < 1e-9 && Math.abs(kp.deg - k.deg) < 1e-9 && Math.abs(g.distancePrep(g.prep(c.o), g.prep(c.p)) - k.ft) < 1e-9);
    // along: the point ft along a course
    const q = g.along(c.o, c.deg, c.ft);
    bump('alongLL', Math.max(Math.abs(q[0] - c.along[0]), Math.abs(q[1] - c.along[1])));
    assert.ok(Math.abs(q[0] - c.along[0]) <= DEG && Math.abs(q[1] - c.along[1]) <= DEG, `along ${tag}: ${q} against ${c.along}`);
    const a = g.enu(c.o, q);
    const b = g.enu(c.o, c.along);
    bump('along', Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])));
    assert.ok(Math.abs(a[0] - b[0]) <= FT && Math.abs(a[1] - b[1]) <= FT, `along (enu) ${tag}`);
    // ... and it is that far along that course (a point the plane's frame puts exactly there)
    assert.ok(Math.abs(a[0] - c.ft * Math.cos((c.deg * Math.PI) / 180)) <= FT * 2 && Math.abs(a[1] - c.ft * Math.sin((c.deg * Math.PI) / 180)) <= FT * 2, `along lands ${tag}`);
  }
  console.log(`geo: WGS84 against fdm/wgs84.py, ${cases.length} cases: worst enu ${worst.enu.toExponential(1)} ft, course distance ${worst.dist.toExponential(1)} ft, along ${worst.along.toExponential(1)} ft, lat/lon ${Math.max(worst.from, worst.alongLL).toExponential(1)} deg, bearing ${worst.brg.toExponential(1)} deg`);

  // the round trip, at many origins and offsets (to 300 nmi out; Newton stops at 1e-5 ft). Twelve Newton steps do not reach that 300 nmi east of a point poleward of about 65 deg (3 ft short at
  // 78 N, in fdm/wgs84.py too, which this is the same method as): the far offsets are asked of the origins nearer the equator, and 100 nmi of every one
  let rt = 0;
  let count = 0;
  for (const o of [[0, 0], [35, -117], [-33.9, 151.2], [60.33, 24.97], [78, 15], [-60, -70], [10, 179.9]]) {
    for (const n of [0, 1, -5000, 250000, -1.8e6]) {
      for (const e of [0, 1, 7000, -250000, 1.8e6]) {
        if (Math.abs(o[0]) > 65 && Math.abs(e) > 6e5) continue;
        count++;
        const p = g.fromEnu(o, n, e);
        const back = g.enu(o, p);
        rt = Math.max(rt, Math.abs(back[0] - n), Math.abs(back[1] - e));
        assert.ok(Math.abs(back[0] - n) < 1e-3 && Math.abs(back[1] - e) < 1e-3, `round trip ${o} ${n} ${e}: ${back}`); // fdm/wgs84.py's own claim: well under a thousandth of a foot (2e-4 ft at the far corners)
        const there = g.enu(o, g.fromEnu(o, n, e));
        assert.ok(Math.abs(Math.hypot(there[0], there[1]) - Math.hypot(n, e)) < 1e-3);
      }
    }
    // the point itself: from_enu(enu(p)) is p, across the date line too
    for (const d of [[0.3, 0.4], [-1.1, 2.5], [4, -3]]) {
      const p = [o[0] + d[0], o[1] + d[1]];
      const ne = g.enu(o, p);
      const back = g.fromEnu(o, ne[0], ne[1]);
      assert.ok(Math.abs(back[0] - p[0]) < 1e-8 && Math.abs(back[1] - p[1]) < 1e-8, `from_enu(enu(p)) ${o} ${d}: ${back} against ${p}`);
    }
  }
  console.log(`geo: WGS84 round trip over ${count} offsets, worst ${rt.toExponential(1)} ft`);

  // ftPerDeg is the slope of enu: the ft in a degree at the equator and at 60 N are the ellipsoid's, not the old 364,567.2
  for (const lat of [0, 35, 60.33, -33.9, 80]) {
    const [kn, ke] = g.ftPerDeg(lat);
    const h = 1e-6;
    const dn = g.enu([lat, 10], [lat + h, 10])[0] / h;
    const de = g.enu([lat, 10], [lat, 10 + h])[1] / h;
    assert.ok(Math.abs(dn - kn) / kn < 1e-6 && Math.abs(de - ke) / ke < 1e-6, `ftPerDeg ${lat}: ${kn} ${ke} against ${dn} ${de}`);
  }
  // (the published lengths of a degree: 110,574.39 and 111,319.49 m at the equator, 111,412.84 and 55,799.97 m at 60 deg)
  near(g.ftPerDeg(0)[0], 110574.39 / 0.3048, 2, 'a degree of latitude at the equator');
  near(g.ftPerDeg(0)[1], 111319.49 / 0.3048, 2, 'a degree of longitude at the equator');
  near(g.ftPerDeg(60)[0], 111412.84 / 0.3048, 2, 'a degree of latitude at 60 N');
  near(g.ftPerDeg(60)[1], 55799.97 / 0.3048, 2, 'a degree of longitude at 60 N');

  // course and along agree with each other, any way round, and a runway's centreline is straight at 60 N
  const thr = [60.3172, 24.9633];
  for (const h of [0, 33, 90, 153.1, 270, 359.5]) {
    const far = g.along(thr, h, 5 * g.NM);
    near(g.turn(g.course(thr, far).deg, h), 0, 1e-9, `bearing out ${h}`);
    near(g.course(thr, far).ft, 5 * g.NM, 1e-4, `distance out ${h}`);
    // ... the final's 5 nmi in a runway frame: on the centreline, not a tenth of a degree off it
    const [al, cross] = (() => { const ne = g.enu(thr, far); const c = Math.cos((h * Math.PI) / 180); const s = Math.sin((h * Math.PI) / 180); return [ne[0] * c + ne[1] * s, -ne[0] * s + ne[1] * c]; })();
    near(al, 5 * g.NM, 1e-4, 'along the centreline');
    near(cross, 0, 1e-4, 'across it');
  }
}
console.log('geo: WGS84 ok');
