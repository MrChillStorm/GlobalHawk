// node tests/ground.test.js
// Stage 1 of "starting at a stand from the planner" (docs/PLAN.md, S3): the ground network and the taxi routes on it, on the made-up field XDM1
// (fdm/mkdemoground.py; no scenery data is committed). fdm/ground_checks.py runs the same module against groundplan.py, which flew the routes at EFHK.
const assert = require('assert');
const G = require('../js/ground.js');
const D = require('../js/demoground.js');
const plancheck = require('../js/plancheck.js');
const geo = require('../js/geo.js');
const demoplan = require('../js/demoplan.js');

const clone = (x) => JSON.parse(JSON.stringify(x));
const net = new G.Net(D);
const rw04 = net.end('04');
const fr = rw04.frame;
const near = (a, b, tol, what) => assert.ok(Math.abs(a - b) <= tol, `${what}: ${a} is not within ${tol} of ${b}`);
const standOf = (n) => net.parking.find((s) => s.n === n);
const S1 = standOf('S1');
const stand = [S1.lat, S1.lon];

// the message
{
  assert.strictEqual(G.check(D), null);
  assert.ok(/not an airport message/.test(G.check(null)));
  assert.ok(/lacks a list/.test(G.check({ icao: 'X' })));
  assert.ok(/arc leaves/.test(G.check(Object.assign(clone(D), { arcs: [[0, 99, 0]] }))));
  assert.ok(/not a position/.test(G.check(Object.assign(clone(D), { nodes: [[95, 0]] }))));
  assert.throws(() => new G.Net({ icao: 'ZZZZ' }), /lacks a list/);
  assert.strictEqual(net.icao, 'XDM1');
  assert.strictEqual(net.parking.length, 3);
  assert.deepStrictEqual(net.parking.map((s) => s.fits), [true, true, false], 'the third stand (radius 15 m) is too small for the 116 ft wings');
  assert.strictEqual(G.MIN_SPOT_RADIUS_M, 20);
  assert.strictEqual(G.reciprocal('22L'), '04R');
  assert.strictEqual(G.reciprocal('04'), '22');
  assert.strictEqual(G.reciprocal('36'), '18');
  assert.strictEqual(G.reciprocal('18'), '36');
  assert.strictEqual(G.reciprocal('09C'), '27C');
  assert.strictEqual(G.reciprocal('xx'), null);
  near(net.runwayLength(rw04), 12000, 2, 'runway 04 is 12,000 ft');
  assert.deepStrictEqual(net.labels().map((l) => l.name).sort(), ['A', 'B', 'C', 'D', 'E'], 'the runway arcs are not labelled');
}

// picking a stand with a click
{
  assert.strictEqual(net.standNear(geo.along(stand, 0, 30)).n, 'S1');
  assert.strictEqual(net.standNear(geo.along(stand, 0, 300)), null, 'a click nowhere near a stand');
  assert.strictEqual(net.standNear(geo.along(stand, 0, 300), 400).n, 'S1', 'a wider reach');
}

// routes
{
  const a = net.nearestNode(stand);
  assert.deepStrictEqual(net.nodes[a], D.nodes[a]);
  const [al, la] = fr.to(net.nodes[a]);
  near(al, -400, 1, 'the stand\'s node is the west end of A');
  near(la, 300, 1, 'A is 300 ft right of the runway');
  const r = net.route(a, net.nodes.findIndex((p) => Math.abs(fr.to(p)[0] - 170) < 1 && Math.abs(fr.to(p)[1]) < 1));
  assert.ok(r && r.length === 4, 'A west, A at B, B square, B on the centreline: ' + JSON.stringify(r));
  assert.strictEqual(net.route(a, a).length, 1);
  assert.strictEqual(net.route(a, 9999 % net.nodes.length, new Set(net.nodes.map((_, i) => i).filter((i) => i !== a))), net.route(a, 9999 % net.nodes.length, new Set(net.nodes.map((_, i) => i).filter((i) => i !== a))) && null, 'every other node forbidden: no way unless it is next door');
}

// the exits of runway 04, nearest first
{
  const ex = net.exits(rw04);
  assert.deepStrictEqual(ex.map((e) => e.names.join()), ['E', 'C', 'D']);
  [4000, 6000, 9500].forEach((v, i) => near(ex[i].along, v, 1, `exit ${i}`));
  assert.strictEqual(net.exits(net.end('22')).map((e) => e.names.join()).join(), 'D,C,E', 'from the other end the order is the other way');
}

// taxi out
{
  const o = G.taxiOut(net, rw04, stand);
  assert.ok(!o.error, o.error);
  assert.deepStrictEqual(o.via, ['A', 'B']);
  assert.strictEqual(o.nodes.length, 4, 'the route to the end of B on the centreline');
  const p = o.points.map((q) => fr.to(q));
  near(p[0][0], -400, 1, 'begins at the nearest node, west end of A');
  near(p[1][0], 20, 1, 'then along A to the entry');
  near(p[2][0], 20, 1, 'the turn begins on the square leg ...');
  near(p[2][1], 150, 1, '... 150 ft from the centreline');
  // the turn is an arc of 150 ft radius about (20 + 150, 150)... its end is on the centreline 150 ft further on
  const c = [170, 150];
  for (const q of p.slice(2, 5)) near(Math.hypot(q[0] - c[0], q[1] - c[1]), 150, 0.6, 'on the arc');
  near(p[p.length - 2][0], 170, 1, 'the arc ends on the centreline');
  near(p[p.length - 2][1], 0, 0.6, '... on it');
  near(p[p.length - 1][0], 450, 1, 'the line-up point is 450 ft down the runway');
  near(p[p.length - 1][1], 0, 0.6, '... on the centreline');
  assert.strictEqual(o.lineup_ft, 450);
  assert.strictEqual(o.entry, net.nodes.findIndex((q) => Math.abs(fr.to(q)[0] - 20) < 1 && Math.abs(fr.to(q)[1] - 300) < 1), 'the entry is where A meets B');
  // from the second stand the same way in
  const o2 = G.taxiOut(net, rw04, [standOf('S2').lat, standOf('S2').lon]);
  assert.deepStrictEqual(o2.points, o.points, 'the nearest node of the second stand is the same');
  // from the other end: the taxiway ends nearest the threshold of 22 are far away; there is none within 1,500 ft of its start
  const bad = G.taxiOut(net, net.end('22'), stand);
  assert.ok(/no taxiway leads/.test(bad.error), bad.error);
}

// taxi in
{
  const aim = fr.to(demoplan.items.find((i) => i.kind === 'land').aim)[0];
  near(aim, 0, 1, 'the demo plan aims at the threshold');
  const i = G.taxiIn(net, rw04, stand, aim, null);
  assert.ok(!i.error, i.error);
  assert.deepStrictEqual(i.exit.names, ['C'], 'the first exit 4,700 ft past the aiming point: C at 6,000 ft, not E at 4,000');
  near(fr.to(i.points[0])[0], 6000, 1, 'begins on the centreline at the exit');
  near(fr.to(i.points[0])[1], 0, 1, '... on it');
  near(fr.to(i.points[1])[1], 39, 1, 'then the first node of C, off it');
  assert.deepStrictEqual(i.points[i.points.length - 1], [r6(stand[0]), r6(stand[1])], 'ends at the stand');
  assert.ok(i.points.slice(1).every((q) => Math.abs(fr.to(q)[1]) > 11), 'never back along the centreline');
  // the other exits by name
  const e = net.exits(rw04);
  const viaE = G.taxiIn(net, rw04, stand, aim, e[0].node);
  assert.deepStrictEqual(viaE.exit.names, ['E']);
  assert.ok(viaE.points.length < i.points.length + 3 && G.routeFt(viaE.points) < G.routeFt(i.points), 'E is closer to the stand than C');
  assert.ok(/not on the runway/.test(G.taxiIn(net, rw04, stand, aim, 0).error));
  assert.ok(/beyond 14,000 ft/.test(G.taxiIn(net, rw04, stand, 9300, null).error), 'no exit 4,700 ft past an aiming point 9,300 ft down');
}

function r6(x) {
  return Math.round(x * 1e6) / 1e6;
}

// the plan
{
  const r = G.addTaxi(net, demoplan, { stand, heading: 310, exit: null });
  assert.ok(!r.error, r.error);
  const p = r.plan;
  assert.deepStrictEqual(p.items.map((i) => i.kind), ['taxi', 'takeoff', 'route', 'land', 'taxi']);
  assert.strictEqual(plancheck.checkPlan(p), null, 'the aircraft takes it');
  assert.deepStrictEqual(p.items.slice(2, 4), demoplan.items.slice(2, 4), 'the route and the landing are as they were');
  assert.deepStrictEqual(p.lost_link, demoplan.lost_link);
  assert.deepStrictEqual(p.sites, demoplan.sites);
  assert.deepStrictEqual(p.field.stand, [r6(stand[0]), r6(stand[1])]);
  assert.strictEqual(p.field.stand_heading, 310);
  assert.strictEqual(p.field.name, demoplan.field.name, 'the rest of the field is kept');
  const t = p.items[1];
  near(fr.to(t.start)[0], 450, 0.5, 'the takeoff begins at the line-up point');
  near(geo.course(t.start, t.end).ft, geo.course(demoplan.items[1].start, demoplan.items[1].end).ft, 120, 'and is as long as it was');
  assert.deepStrictEqual(p.items[0], { kind: 'taxi', points: r.out.points, speed: 15, turn_speed: 8, stop: true });
  assert.deepStrictEqual(p.items[4].points, r.in.points);
  assert.strictEqual(r.out.rw, '04');
  assert.strictEqual(r.in.rw, '04');
  near(r.out.length_ft, 1183, 3, 'out');
  assert.ok(r.in.length_ft > 7000 && r.in.length_ft < 7700, 'in: ' + r.in.length_ft);
  assert.deepStrictEqual(demoplan.items.map((i) => i.kind), ['taxi', 'takeoff', 'route', 'land'], 'the plan given is not changed');
  // again: the same plan, the old taxi items replaced
  const r2 = G.addTaxi(net, p, { stand, heading: 310, exit: null });
  assert.deepStrictEqual(r2.plan.items, p.items, 'idempotent');
  // another exit
  const r3 = G.addTaxi(net, p, { stand, heading: 310, exit: net.exits(rw04)[2].node });
  assert.ok(r3.plan.items[4].points.length > 0 && r3.in.exit.names[0] === 'D');
  // removed
  const back = G.removeTaxi(net, p);
  assert.deepStrictEqual(back.items.map((i) => i.kind), ['takeoff', 'route', 'land']);
  assert.deepStrictEqual(back.items[0].start, [34.9, -117.88], 'the takeoff begins at the threshold again');
  near(geo.course(back.items[0].start, back.items[0].end).ft, geo.course(t.start, t.end).ft, 1, 'its length is kept');
  assert.deepStrictEqual(G.removeTaxi(null, p).items.map((i) => i.kind), ['takeoff', 'route', 'land']);
  // a plan that lands only, or takes off only
  const landOnly = Object.assign(clone(demoplan), { items: demoplan.items.filter((i) => i.kind === 'route' || i.kind === 'land') });
  const r4 = G.addTaxi(net, landOnly, { stand, heading: 310, exit: null });
  assert.deepStrictEqual(r4.plan.items.map((i) => i.kind), ['route', 'land', 'taxi']);
  // faults
  assert.ok(/no stand/.test(G.addTaxi(net, demoplan, { stand: null }).error));
  assert.ok(/neither a takeoff nor a landing/.test(G.addTaxi(net, Object.assign(clone(demoplan), { items: [demoplan.items[2]] }), { stand }).error));
  const off = clone(demoplan);
  off.items[1].start = geo.along([34.9, -117.88], 130, 2000);
  off.items[1].end = geo.along(off.items[1].start, 40, 9000);
  assert.ok(/not on a runway of XDM1/.test(G.addTaxi(net, off, { stand }).error), 'a takeoff 2,000 ft beside the runway');
  const wrongWay = clone(demoplan);
  wrongWay.items[1].end = geo.along(wrongWay.items[1].start, 100, 9000);
  assert.ok(/not on a runway of XDM1/.test(G.addTaxi(net, wrongWay, { stand }).error), 'a takeoff along no runway');
}

// a taxiway that meets the runway at a slant: no turn is laid, the route is followed to the centreline and on down it
{
  const m = {
    icao: 'XSLT', parking: [{ n: 'P', t: 'misc', lat: 34.9, lon: -117.88, h: 0, r: 25 }],
    nodes: [], arcs: [[0, 1, 0]], names: ['X'], runways: [{ n: '04', lat: 34.9, lon: -117.88, h: 40, displ: 0, stopw: 0 }],
  };
  const f = new G.Frame([34.9, -117.88], 40);
  m.nodes = [f.ll(-200, 200), f.ll(100, 0)];
  m.parking[0].lat = m.nodes[0][0];
  m.parking[0].lon = m.nodes[0][1];
  const n2 = new G.Net(m);
  const o = G.taxiOut(n2, n2.end('04'), m.nodes[0]);
  assert.ok(!o.error, o.error);
  assert.strictEqual(o.entry, null, 'no square leg: no turn');
  assert.strictEqual(o.points.length, 3);
  near(n2.end('04').frame.to(o.points[2])[0], 450, 1, 'the line-up point');
  assert.ok(/no taxiway leaves runway 04 beyond 4,700 ft/.test(G.addTaxi(n2, demoplan, { stand: m.nodes[0] }).error), 'a network with no exit from the runway: said so');
}

console.log('ground: ok');
