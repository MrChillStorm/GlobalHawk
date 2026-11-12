// node tests/editor.test.js
const assert = require('assert');
const { PlanEditor } = require('../js/editor.js');
const pc = require('../js/plancheck.js');
const plan = require('../../Missions/demo-local.json');
const before = JSON.stringify(plan);

const e = new PlanEditor(plan);
assert.strictEqual(e.points().length, 4);
assert.strictEqual(e.selected, 3);
// add after the selected point, at its height
e.selected = 1;
e.add([35.5, -117.2]);
assert.deepStrictEqual(e.points()[2], [35.5, -117.2, 20000]);
assert.strictEqual(e.points().length, 5);
assert.strictEqual(e.selected, 2);
// move, height
e.move(2, [35.6123456789, -117.3]);
e.setAlt(2, 30000);
assert.deepStrictEqual(e.points()[2], [35.612346, -117.3, 30000]);
// delete; a route keeps one point
assert.ok(e.remove(2));
assert.strictEqual(e.points().length, 4);
const one = new PlanEditor(plan);
one.remove(0);
one.remove(0);
one.remove(0);
assert.strictEqual(one.remove(0), false);
assert.strictEqual(one.points().length, 1);
// the original is untouched; the edited copy says so and still passes the aircraft's check
assert.strictEqual(JSON.stringify(plan), before);
assert.ok(/\(edited\)$/.test(e.plan.id));
assert.strictEqual(pc.checkPlan(e.plan), null);
// a fault made by editing is said
e.setAlt(0, 70000);
assert.ok(/height 70000 ft/.test(pc.checkPlan(e.plan)));
e.setAlt(0, 20000);
// the lost-link route is edited apart from the route
const routeBefore = JSON.stringify(e.points());
e.edit('lost');
assert.strictEqual(e.points().length, 1);
e.add([34.7, -118.3]);
assert.strictEqual(e.plan.lost_link[0].points.length, 2);
e.edit('route');
assert.strictEqual(JSON.stringify(e.points()), routeBefore);
// a plan without one gets a lost-link route to its own landing when asked
const bare = JSON.parse(before);
delete bare.lost_link;
const b = new PlanEditor(bare);
b.edit('lost');
assert.strictEqual(pc.checkPlan(b.plan), null);
assert.deepStrictEqual(b.plan.lost_link.map((i) => i.kind), ['route', 'land']);
// enroute only the route onward is sent
assert.deepStrictEqual(e.toSend(false).items.map((i) => i.kind), ['taxi', 'takeoff', 'route', 'land']);
assert.deepStrictEqual(e.toSend(true).items.map((i) => i.kind), ['route', 'land']);
assert.ok(e.toSend(true).lost_link && e.toSend(true).sites);
console.log('editor OK');
