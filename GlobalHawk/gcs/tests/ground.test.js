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
  assert.deepStrictEqual(p.items[0], { kind: 'taxi', points: r.out.points, speed: 15, turn_speed: 8, stop: true, holds: r.out.holds });
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

// the holds (docs/PLAN.md, "Hold points and clearances")
{
  const r = G.addTaxi(net, demoplan, { stand, heading: 310, exit: null });
  const taxi = r.plan.items.filter((i) => i.kind === 'taxi');
  const hs = taxi[0].holds;
  assert.deepStrictEqual(hs.map((h) => [h.id, h.kind]), [['H1', 'runway'], ['H2', 'takeoff']], 'a hold short of the runway, then the takeoff clearance');
  assert.strictEqual(hs[0].name, 'hold short of runway 04 at B', 'the runway entered, the taxiway it is entered by');
  assert.strictEqual(hs[1].name, 'lined up on runway 04: cleared for takeoff');
  assert.strictEqual(hs[1].i, taxi[0].points.length - 1, 'the takeoff hold is at the line-up point, the last');
  const q = fr.to(taxi[0].points[hs[0].i]);
  near(Math.abs(q[1]), 200, 1.5, 'the hold short is 200 ft from the centreline');
  near(q[0], 20, 2, '... on the straight into the runway');
  assert.ok(taxi[0].points.slice(0, hs[0].i).every((p) => Math.abs(fr.to(p)[1]) > 200), 'and the route is outside it until there');
  assert.strictEqual(taxi[1].holds, undefined, 'the taxi in leaves the runway: no hold');
  assert.deepStrictEqual(r.in.holds, []);
  assert.strictEqual(plancheck.checkPlan(r.plan), null, 'the aircraft takes the holds');
  // the route is the route without holds, with the hold's point put in
  const plain = G.addTaxi(net, demoplan, { stand, heading: 310, exit: null, holds: false });
  assert.strictEqual(plain.plan.items[0].holds, undefined, 'none asked for: none');
  assert.strictEqual(plain.plan.items[0].points.length + 1, taxi[0].points.length);
  assert.ok(G.routeFt(plain.plan.items[0].points) - G.routeFt(taxi[0].points) < 0.5 && G.routeFt(taxi[0].points) - G.routeFt(plain.plan.items[0].points) < 0.5, 'and as long');
  // again: the same
  assert.deepStrictEqual(G.addTaxi(net, r.plan, { stand, heading: 310, exit: null }).plan.items, r.plan.items, 'idempotent with holds');
  // taxiway names for the hold
  assert.strictEqual(G.taxiwayNear(net, net.nodes[0]), 'A');
  // the operator's: on the first taxi item, on A, 1,000 ft along it
  const onA = net.nodes.findIndex((p) => Math.abs(fr.to(p)[0] - 20) < 1 && Math.abs(fr.to(p)[1] - 300) < 1);
  assert.ok(onA >= 0);
  const a0 = r.plan.items[0].points[0];
  const click = geo.along(a0, geo.course(a0, r.plan.items[0].points[1]).deg, 150);
  const add = G.addHold(net, r.plan, 0, click);
  assert.ok(!add.error, add.error);
  const t0 = add.plan.items[0];
  assert.strictEqual(t0.holds.length, 3);
  assert.deepStrictEqual(t0.holds.map((h) => h.i), [1, 3, 8], 'the point is put into the route and the holds after it move up one');
  assert.strictEqual(t0.holds[0].id, 'H3', 'the first id not used');
  assert.strictEqual(t0.holds[0].kind, 'point');
  assert.strictEqual(t0.holds[0].name, 'hold on A');
  assert.strictEqual(t0.points.length, r.plan.items[0].points.length + 1);
  assert.strictEqual(plancheck.checkPlan(add.plan), null);
  assert.deepStrictEqual(t0.holds.slice(1).map((h) => h.name), hs.map((h) => h.name), 'the others are as they were');
  assert.ok(/there already/.test(G.addHold(net, add.plan, 0, click).error), 'not twice');
  assert.ok(/within 150 ft/.test(G.addHold(net, r.plan, 0, geo.along(a0, 0, 2000)).error), 'a click far from the route');
  assert.ok(/not a taxi route/.test(G.addHold(net, r.plan, 2, click).error));
  const gone = G.removeHold(add.plan, 'H3');
  assert.deepStrictEqual(gone.plan.items[0].holds.map((h) => h.id), ['H1', 'H2']);
  assert.deepStrictEqual(G.removeHold(G.removeHold(gone.plan, 'H1').plan, 'H2').plan.items[0].holds, undefined, 'no holds left: no list');
  assert.ok(/no such hold/.test(G.removeHold(gone.plan, 'H9').error));
  // a route that crosses a runway: a hold short of it, and none for the runway it leaves
  const m = JSON.parse(JSON.stringify(D));
  const f = new G.Frame([34.9, -117.88], 40);
  const cross = [f.ll(6500, 450), f.ll(6500, 300), f.ll(6500, -300), f.ll(6500, -450)]; // across runway 04/22 at 6,500 ft, from the right side to the left
  const rh = G.runwayHolds(net, cross, null);
  assert.strictEqual(rh.holds.length, 1);
  assert.strictEqual(rh.holds[0].name, 'hold short of runway 04/22 at A', 'a runway crossed is named by its pair (and the taxiway nearest)');
  near(Math.abs(f.to(rh.points[rh.holds[0].i])[1]), 200, 1.5, 'a hold 200 ft out on the side it comes from');
  assert.strictEqual(rh.points.length, 5);
  const back = G.runwayHolds(net, cross.slice().reverse(), null);
  assert.strictEqual(back.holds.length, 1, 'and the same from the other side');
  assert.ok(f.to(back.points[back.holds[0].i])[1] < -150, 'on its own side');
  assert.strictEqual(G.runwayHolds(net, [f.ll(6500, 0), f.ll(6500, 300)], null).holds.length, 0, 'a route that begins on the runway leaves it without a hold');
  assert.strictEqual(G.runwayHolds(net, [f.ll(6500, 450), f.ll(6500, 300)], null).holds.length, 0, 'one that stays outside needs none');
  void m;
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

// the runway picker (docs/PLAN.md, "Runway picker, stage 3": R1 to R5)
{
  // R1: the list, in the message's order, with the lengths
  const list = net.runwayList();
  assert.deepStrictEqual(list.map((r) => r.n), D.runways.map((r) => r.n));
  list.forEach((r) => {
    assert.ok(r.length_ft > 11900 && r.length_ft < 12100, `runway ${r.n} is 12,000 ft from end to end`);
    assert.strictEqual(r.displ_ft, 0);
  });
  // R2: a plan on every end, without a stand: takeoff, route, landing; both found on the same end again by the taxi builder's own lookup
  for (const end of net.runways) {
    const r = G.planOnRunway(net, end.n, 2300, 6500);
    assert.ok(!r.error, r.error);
    assert.deepStrictEqual(r.plan.items.map((i) => i.kind), ['takeoff', 'route', 'land'], end.n);
    assert.strictEqual(plancheck.checkPlan(r.plan), null, `the aircraft takes the plan on ${end.n}`);
    const t = r.plan.items[0];
    const l = r.plan.items[2];
    assert.strictEqual(net.runwayFor(t.start, geo.course(t.start, t.end).deg, -300, 3000).n, end.n, `the takeoff is on ${end.n}`);
    assert.strictEqual(net.runwayFor(l.aim, geo.course(l.fix, l.aim).deg, -300, 4000).n, end.n, `the landing is on ${end.n}`);
    near(end.frame.to(t.start)[0], 0, 1, 'the takeoff begins at the threshold');
    near(end.frame.to(l.aim)[0], 800, 1, 'the aiming point is 800 ft past the threshold');
    near(end.frame.to(l.fix)[0], -10 * geo.NM, 5, 'the fix is 10 nmi back on the centreline');
    near(end.frame.to(l.fix)[1], 0, 1, 'the fix is on the centreline');
    assert.deepStrictEqual(r.plan.lost_link.find((i) => i.kind === 'land').aim, l.aim, 'the lost-link route lands on the same aiming point');
    assert.deepStrictEqual(r.plan.sites[0].aim, l.aim, 'the home site is that aiming point');
    assert.strictEqual(r.plan.field.name, `XDM1 ${end.n}`);
    assert.strictEqual(r.plan.field.elev_ft, 2300);
    assert.ok(/runway /.test(r.plan.note) && r.plan.note.includes(end.n));
    assert.strictEqual(r.out, null);
  }
  // the box takes the height it is given
  assert.strictEqual(G.planOnRunway(net, '04', 2300, 9500).plan.items[1].points[0][2], 9500);
  // with a stand: the taxi routes at once, on that runway
  const r4 = G.planOnRunway(net, '04', 2300, 6500, { stand, heading: S1.h, exit: null, holds: true });
  assert.ok(!r4.error, r4.error);
  assert.deepStrictEqual(r4.plan.items.map((i) => i.kind), ['taxi', 'takeoff', 'route', 'land', 'taxi']);
  assert.strictEqual(r4.out.rw, '04');
  assert.strictEqual(r4.in.rw, '04');
  assert.strictEqual(plancheck.checkPlan(r4.plan), null, 'the aircraft takes the plan with its taxi routes and holds');
  assert.deepStrictEqual(r4.plan.field.stand, [S1.lat, S1.lon].map((v) => Math.round(v * 1e6) / 1e6));
  near(fr.to(r4.plan.items[1].start)[0], r4.out.lineup_ft, 1, 'the takeoff begins at the line-up point');
  const noHolds = G.planOnRunway(net, '04', 2300, 6500, { stand, heading: S1.h, exit: null, holds: false });
  assert.ok(noHolds.plan.items.every((i) => !i.holds), 'holds off: none');
  // R3: a runway the taxiways do not reach from that stand is refused in words, whole
  const bad = G.planOnRunway(net, '22', 2300, 6500, { stand, heading: S1.h, exit: null });
  assert.ok(/no taxiway leads from the stand to runway 22/.test(bad.error), bad.error);
  assert.strictEqual(bad.plan, undefined, 'a refusal gives no plan');
  assert.ok(G.planOnRunway(net, '22', 2300, 6500).plan, 'the same runway without a stand is a plan');
  // R4: the field's height is asked for, never made up; an end that is not there
  assert.ok(/height of the field is not known/.test(G.planOnRunway(net, '04', NaN, 6500).error));
  assert.ok(/height of the field is not known/.test(G.planOnRunway(net, '04', undefined, 6500).error));
  assert.ok(/no runway end 99/.test(G.planOnRunway(net, '99', 2300, 6500).error));
  // a displaced threshold: the aiming point is 800 ft past the displaced threshold, not past the pavement's end
  const m = clone(D);
  m.runways.find((r) => r.n === '04').displ = 300; // metres
  const nd = new G.Net(m);
  assert.strictEqual(nd.runwayList().find((r) => r.n === '04').displ_ft, 984);
  const rd = G.planOnRunway(nd, '04', 2300, 6500);
  assert.ok(!rd.error, rd.error);
  near(nd.end('04').frame.to(rd.plan.items[2].aim)[0], 984 + 800, 1, 'the aiming point past the displaced threshold');
  assert.strictEqual(nd.runwayFor(rd.plan.items[2].aim, geo.course(rd.plan.items[2].fix, rd.plan.items[2].aim).deg, -300, 4000).n, '04');
  // an intersection takeoff (EFHK 33 from stand 121 begins 4,400 ft down the runway): the plan is found on its runway again, so the taxi routes can be laid again or taken out
  const mid = G.planOnRunway(net, '04', 2300, 6500).plan;
  mid.items[0].start = fr.ll(4400, 0);
  mid.items[0].end = fr.ll(4400 + 9000, 0);
  const again = G.addTaxi(net, mid, { stand, heading: S1.h, exit: null });
  assert.ok(!again.error, again.error);
  assert.strictEqual(again.out.rw, '04');
  const gone = G.removeTaxi(net, again.plan);
  near(fr.to(gone.items[0].start)[0], 0, 1, 'taking the routes out puts the takeoff back at the threshold');
  // the way in takes the next exit when the first past the rollout leads nowhere (EFHK 04R: ZH does not); an exit named by the operator is taken or refused as it is
  const dead = clone(D);
  dead.arcs = dead.arcs.filter((a) => !(a[0] === 3 && a[1] === 14)); // C's other end: the taxiway at runway 04's exit C is now a spur that ends
  const nd2 = new G.Net(dead);
  const spur = G.taxiIn(nd2, nd2.end('04'), stand, 800, null);
  assert.ok(!spur.error, spur.error);
  assert.deepStrictEqual(spur.exit.names, ['D'], 'C leads nowhere: the way in leaves by D');
  assert.ok(/no taxiway leads from C on runway 04 to the stand/.test(G.taxiIn(nd2, nd2.end('04'), stand, 800, 10).error), 'C asked for by name: refused as before');
  assert.deepStrictEqual(G.taxiIn(net, net.end('04'), stand, 800, null).exit.names, ['C'], 'where the first exit leads home it is still the one taken');
  // the plan that replaces another begins with no taxi items: asking again for the same runway gives the same plan
  assert.deepStrictEqual(G.planOnRunway(net, '04', 2300, 6500).plan, G.planOnRunway(net, '04', 2300, 6500).plan);
}

console.log('ground: ok');
