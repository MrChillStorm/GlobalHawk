// node tests/pick.test.js
// What a click on the map lands on, for the belly camera's lock; and the lock command it sends.
const assert = require('assert');
const P = require('../js/pick.js');
const geo = require('../js/geo.js');
const cam = require('../js/camera.js');
const plan = require('../js/demoplan.js');

const centre = [34.9, -117.88];
const size = [900, 600];
const ftPerPx = 600;
const project = (p) => geo.toScreen(p, centre, 0, ftPerPx, size);
const data = {
  plan,
  traffic: [{ callsign: 'N172', lat: 34.95, lon: -117.8, alt_ft: 19500 }, { callsign: 'FAR', lat: 36, lon: -117.8, alt_ft: 5000 }],
  airfields: [{ name: 'Test strip', lat: 34.82, lon: -117.95 }],
};
const items = P.items(data, geo.planLines);

// every kind shows up: aircraft, the site, route points of both routes, the airfield
const kinds = new Set(items.map((i) => i.kind));
assert.deepStrictEqual([...kinds].sort(), ['aircraft', 'airfield', 'point', 'site']);
assert.strictEqual(items.filter((i) => i.name.startsWith('route point')).length, 4, 'the plan has four route points');
assert.ok(items.some((i) => i.name === 'lost-link route point 1'));
assert.ok(items.some((i) => i.name === 'route point 1 (20000 ft)'), items.map((i) => i.name).join('; '));

// a click on each lands on it, a few pixels off
const near = (p, dx, dy) => { const q = project(p); return [q[0] + dx, q[1] + dy]; };
let q = near([34.95, -117.8], 5, -4);
let hit = P.pick(items, project, q[0], q[1], 12);
assert.strictEqual(hit.name, 'N172');
assert.strictEqual(hit.kind, 'aircraft');
assert.strictEqual(hit.alt_ft, 19500);
q = near(plan.sites[0].aim, 3, 3);
hit = P.pick(items, project, q[0], q[1], 12);
assert.strictEqual(hit.kind, 'site');
assert.strictEqual(hit.name, 'Demo field 04');
q = near([34.82, -117.95], -6, 2);
assert.strictEqual(P.pick(items, project, q[0], q[1], 12).name, 'Test strip');
const rp = plan.items.find((i) => i.kind === 'route').points[1];
q = near([rp[0], rp[1]], 2, 2);
hit = P.pick(items, project, q[0], q[1], 12);
assert.strictEqual(hit.kind, 'point');
assert.ok(hit.name.startsWith('route point 2'), hit.name);

// nothing within the reach: the bare place
q = near([34.7, -117.5], 0, 0);
assert.strictEqual(P.pick(items, project, q[0], q[1], 12), null);
q = near([34.95, -117.8], 13, 0);
assert.strictEqual(P.pick(items, project, q[0], q[1], 12).name, 'N172', 'an aircraft has 14 px of reach');
q = near([34.95, -117.8], 15, 0);
assert.strictEqual(P.pick(items, project, q[0], q[1], 12), null, 'not 15');
q = near(plan.sites[0].aim, 13, 0);
assert.strictEqual(P.pick(items, project, q[0], q[1], 12), null, 'a site has 12');

// two things on top of each other: the aircraft wins over a site, a site over a route point
const stack = [
  { kind: 'point', name: 'p', p: [34.9, -117.88], prio: 2 },
  { kind: 'site', name: 's', p: [34.9, -117.88], prio: 1 },
  { kind: 'aircraft', name: 'a', p: [34.9, -117.88], prio: 0, tol: 14 },
];
q = project([34.9, -117.88]);
assert.strictEqual(P.pick(stack, project, q[0], q[1], 12).name, 'a');
assert.strictEqual(P.pick(stack.slice(0, 2), project, q[0], q[1], 12).name, 's');
// and of equal rank the nearer
const two = [{ kind: 'point', name: 'far', p: [34.9005, -117.88], prio: 2 }, { kind: 'point', name: 'near', p: [34.9001, -117.88], prio: 2 }];
q = project([34.9, -117.88]);
assert.strictEqual(P.pick(two, project, q[0], q[1], 12).name, 'near');
// nothing on the map at all
assert.strictEqual(P.pick(P.items({}, geo.planLines), project, 10, 10, 12), null);

// the command: the ground there, or a height for an aircraft
assert.strictEqual(cam.point([34.95, -117.8]), 'point 34.950000 -117.800000');
assert.strictEqual(cam.point([34.95, -117.8], 19500), 'point 34.950000 -117.800000 19500');
assert.strictEqual(cam.point([34.95, -117.8], undefined), 'point 34.950000 -117.800000');
assert.strictEqual(cam.point([34.95, -117.8], NaN), 'point 34.950000 -117.800000');

console.log('pick: ok');
