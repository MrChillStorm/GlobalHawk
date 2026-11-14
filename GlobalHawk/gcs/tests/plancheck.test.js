// node tests/plancheck.test.js : the ported plan check gives the aircraft's verdicts
const assert = require('assert');
const pc = require('../js/plancheck.js');
const geo = require('../js/geo.js');
const good = require('../../Missions/demo-local.json');
const copy = () => JSON.parse(JSON.stringify(good));
assert.strictEqual(pc.checkPlan(good), null);
const cases = [
  [(p) => (p.items[2].kind = 'loiter'), 'plan item 3: unknown kind "loiter"'],
  [(p) => (p.items[2].points[0][2] = 70000), 'plan item 3 (route) point 1: height 70000 ft is outside 0 to 65000 ft'],
  [(p) => (p.items[3].fix = geo.along(p.items[3].aim, 220, 3 * geo.NM)), 'plan item 4 (land): the fix is 3.0 nmi from the aiming point, less than 8'],
  [(p) => p.lost_link.pop(), 'lost-link route: it must begin with a route and end in a land'],
  [(p) => (p.items[2].points[1][0] = 95), 'plan item 3 (route) point 2: latitude 95 is not on the earth'],
  [(p) => p.items.splice(2, 1), 'plan item 2: a takeoff must be followed by a route'],
  [(p) => delete p.field.elev_ft, 'field: needs lat, lon and elev_ft'],
  [(p) => (p.items = []), 'plan: no items'],
  [(p) => (p.sites[0].course = 'north'), 'site 1: needs aim, course and elev_ft'],
];
for (const [damage, reason] of cases) {
  const p = copy();
  damage(p);
  assert.strictEqual(pc.checkPlan(p), reason);
}
assert.strictEqual(pc.checkPlan(null), 'not a plan');
// the legs the forecast takes: a takeoff, each route point, the fix, the landing
const legs = pc.legs(good.items, good.field.stand, good.field.elev_ft, { arcs: false }); // the straight lines between the points: the corners' arcs are tested below
assert.deepStrictEqual(legs.map((l) => l.kind || 'route'), ['takeoff', 'route', 'route', 'route', 'route', 'route', 'land']);
assert.ok(Math.abs(legs[1].dist_ft / geo.NM - 23.35) < 0.1);
assert.strictEqual(legs[6].alt_ft, good.field.elev_ft);
// a landing that carries its own elevation (landing at another field than it left) is forecast to that height
{
  const other = JSON.parse(JSON.stringify(good));
  other.items[3].elev_ft = 151;
  const l2 = pc.legs(other.items, good.field.stand, other.field);
  assert.strictEqual(l2[6].alt_ft, 151, 'the landing leg');
  assert.strictEqual(l2[0].alt_ft, good.field.elev_ft, 'the takeoff is still the field\'s');
  const ri = require('../js/routeinputs.js');
  other.items[2].points[3] = [other.items[3].fix[0], other.items[3].fix[1], 3700];
  assert.strictEqual(ri.goalOf(other).fix_alt_ft, 3700);
  other.items[2].points[3] = [0, 0, 9000];
  const FMx = require('../js/flightmath.js');
  const want = Math.round((151 + FMx.finalFixHeightAgl(geo.course(other.items[3].fix, other.items[3].aim).ft, 20000)) / 100) * 100;
  assert.strictEqual(ri.goalOf(other).fix_alt_ft, want, 'the landing\'s own 151 ft and the capability\'s height over it, to 100 ft, not the field\'s 2,300');
  assert.notStrictEqual(want, Math.round((2300 + FMx.finalFixHeightAgl(geo.course(other.items[3].fix, other.items[3].aim).ft, 20000)) / 100) * 100);
}

// the plan assessment (P3 of docs/PLAN.md, "The planner uses the aircraft's capability tables"): what the aircraft's capability says about a plan, in words with the numbers
{
  const NM = geo.NM;
  const here = [60.33, 24.96];
  const hdg = 153.1;
  const elev = 174;
  const mk = (a, b, fixNm, fixAlt) => {
    const p1 = geo.along(here, hdg, a * NM);
    const p2 = geo.along(p1, hdg + 90, b * NM);
    const fix = geo.along(here, hdg + 180, fixNm * NM);
    return { id: 't', field: { name: 'x', lat: here[0], lon: here[1], elev_ft: elev }, items: [{ kind: 'takeoff', start: here, end: geo.along(here, hdg, 9000) },
      { kind: 'route', points: [[p1[0], p1[1], elev + 3800], [p2[0], p2[1], elev + 3800], [fix[0], fix[1], fixAlt]] }, { kind: 'land', fix, aim: geo.along(here, hdg, 800) }] };
  };
  // nothing to say: the demo plan, the station's own local plan (90 deg corners, long legs, the fix under the path)
  assert.deepStrictEqual(pc.assess(good, { weight_lb: 20000 }), []);
  assert.deepStrictEqual(pc.assess(geo.localPlan(here, hdg, elev), { weight_lb: 20000 }), []);
  assert.deepStrictEqual(pc.assess(null), []);
  // a corner of 163 deg at the fix (the plan flown in FlightGear on 2026-11-14): it is flown over, about two radii off the new leg
  let a = pc.assess(mk(6, 5, 10, elev + 3500), { weight_lb: 14000 });
  assert.deepStrictEqual(a.map((x) => x.kind), ['corner', 'final'], 'the corner, and 3,500 ft over the fix is more than the path allows now (the gap it needs to settle in)');
  assert.strictEqual(pc.assess(mk(6, 5, 10, elev + 2000), { weight_lb: 14000 }).length, 1, 'the corner alone');
  assert.ok(/^The turn at the landing fix is 163°/.test(a[0].text) && /past 150° it flies over the point/.test(a[0].text) && /no turn is over 120°/.test(a[0].text), a[0].text);
  assert.ok(Math.abs(a[0].have - 163) < 1 && a[0].need === 120);
  // two corners over the limit, and a final that is too high
  a = pc.assess(mk(12, 15, 10, elev + 3500), { weight_lb: 14000 });
  assert.deepStrictEqual(a.map((x) => x.kind), ['corner', 'corner', 'final']);
  assert.ok(/^The turn at point 2 is 124°/.test(a[0].text) && /^The turn at the landing fix is 146°/.test(a[1].text));
  assert.ok(/too high/.test(a[2].text) && /farther out/.test(a[2].text), a[2].text);
  // the station's own local plan with the fix too high: 6,000 ft over the ground comes onto the path too high, and the words give a height and a distance that fix it
  const lp = (fixAlt, fixNm) => {
    const plan = geo.localPlan(here, hdg, elev);
    const pts = plan.items[1].points;
    if (fixNm) {
      const fix = geo.along(here, hdg + 180, fixNm * NM);
      pts[3] = [fix[0], fix[1], pts[3][2]];
      plan.items[2].fix = fix;
      plan.lost_link = null;
    }
    pts[3][2] = fixAlt;
    return plan;
  };
  a = pc.assess(lp(elev + 6000), { weight_lb: 14000 });
  assert.deepStrictEqual(a.map((x) => x.kind), ['final']);
  assert.ok(/too high/.test(a[0].text), a[0].text);
  const fixAt = Number(/Put the fix at (\d+) ft or lower/.exec(a[0].text)[1]);
  const farther = Number(/or ([\d.]+) nmi farther out/.exec(a[0].text)[1]);
  assert.ok(fixAt < elev + 6000 && farther > 1, a[0].text);
  // taking either piece of the advice makes the final quiet: the fix lowered to that height, or moved out by that distance
  assert.deepStrictEqual(pc.assess(lp(fixAt), { weight_lb: 14000 }), [], 'lowered to ' + fixAt);
  {
    // moved out by that distance the path is as high over the aircraft as the capability wants (the corner at the fix changes with the move, so this is worked by hand)
    const FMy = require('../js/flightmath.js');
    const dJoin = Number(/back on the final ([\d.]+) nmi out/.exec(a[0].text)[1]);
    assert.ok(FMy.pathHeightFt((dJoin + farther) * NM) - (6000 - 174 + 174 - 174) >= FMy.captureGapFt() - 60, 'moved out ' + farther);
  }
  // a close fix, 8 nmi out, 3,000 ft over the ground: the path comes down to the aircraft too soon after it is back on the final for the configuration to have settled
  a = pc.assess(lp(elev + 3000, 8), { weight_lb: 14000 });
  assert.deepStrictEqual(a.map((x) => x.kind), ['final']);
  assert.ok(/^The glide path is only \d+ ft above the aircraft where it is back on the final/.test(a[0].text) && /dives when the landing configuration goes on/.test(a[0].text), a[0].text);
  assert.ok(a[0].have < a[0].need, 'under the gap it needs');
  // 10 nmi out and low enough it is quiet, for a heavy aircraft and a light one alike (8 nmi is too short a final for the capture to be clean from any height the aircraft flies at: the path is under 3,300 ft there)
  assert.deepStrictEqual(pc.assess(lp(elev + 1700), { weight_lb: 26700 }), []);
  assert.deepStrictEqual(pc.assess(lp(elev + 1700), { weight_lb: 12000 }), []);
  // a leg shorter than the turns at its ends: two corners (60 and 30 deg) 0.8 nmi apart
  const p = mk(12, 15, 10, elev + 3500);
  const q = p.items[1].points;
  q.splice(1, 0, [...geo.along(q[0], hdg + 60, 0.8 * NM), q[0][2]]);
  a = pc.assess(p, { weight_lb: 20000 }).filter((x) => x.kind === 'leg');
  assert.ok(a.length >= 1 && /^The leg from point 1 to point 2 is 0\.8 nmi: the turns at its two ends take/.test(a[0].text), JSON.stringify(a));
  assert.ok(a[0].have < a[0].need);
}
// the arcs: each corner shortens the two legs by what the aircraft does not fly (2 R tan(delta / 2) - R delta, half on each), and the forecast flies that
{
  const FM = require('../js/flightmath.js');
  const items = [{ kind: 'route', points: [[35, -118, 20000], [35, -117, 20000], [35.5, -117, 20000]] }];
  const straight = pc.legs(items, null, 2300, { arcs: false });
  const arcs = pc.legs(items, null, 2300); // (no start: the first leg has no corner, so the 90 deg corner at the second point is the only one)
  const t = FM.turn({ delta_deg: 90, alt_ft: 20000, vg_fps: FM.lerp(require('../js/perfdata.js').alt_ft, require('../js/perfdata.js').ktas, 20000) * FM.KT, kcas: 150 });
  const cut = t.radius_ft * (1 - Math.PI / 4);
  assert.ok(Math.abs((straight[1].dist_ft - arcs[1].dist_ft) - cut) < 1 && Math.abs((straight[2].dist_ft - arcs[2].dist_ft) - cut) < 1, 'a 90 deg corner');
  assert.strictEqual(straight[0].dist_ft, arcs[0].dist_ft, 'the first leg has no corner');
  // a corner past the fly-by limit and a nearly straight one are left alone
  const odd = pc.legs([{ kind: 'route', points: [[35, -118, 20000], [35, -117, 20000], [35.001, -118, 20000]] }], null, 2300);
  assert.strictEqual(odd[1].dist_ft, pc.legs([{ kind: 'route', points: [[35, -118, 20000], [35, -117, 20000], [35.001, -118, 20000]] }], null, 2300, { arcs: false })[1].dist_ft);
}
console.log('plancheck OK');
