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
const legs = pc.legs(good.items, good.field.stand, good.field.elev_ft);
assert.deepStrictEqual(legs.map((l) => l.kind || 'route'), ['takeoff', 'route', 'route', 'route', 'route', 'route', 'land']);
assert.ok(Math.abs(legs[1].dist_ft / geo.NM - 23.35) < 0.1);
assert.strictEqual(legs[6].alt_ft, good.field.elev_ft);
console.log('plancheck OK');
