// node tests/reach.test.js
const assert = require('assert');
const r = require('../js/reach.js');
const geo = require('../js/geo.js');
const site = { aim: [34.9, -117.88], course: 40, elev_ft: 2300 };
// the entry point is 5.29 nmi out on the reciprocal of the runway's course
const e = r.entry(site);
const back = geo.course(e, site.aim);
assert.ok(Math.abs(back.ft / geo.NM - 2500 / 0.07782 / geo.NM) < 0.01 && Math.abs(back.deg - 40) < 0.05);
// over the entry point, heading at it: what is in hand is the height above the runway, the entry height and the 1,000 ft
const over = geo.along(e, 220, 1);
assert.ok(Math.abs(r.margin(site, over, 10000, 40) - (10000 - 2300 - 2500 - 1000)) < 1);
// 20 nmi further out costs 20 nmi / 20; flying away costs two quarter turns more
const far = geo.along(e, 220, 20 * geo.NM);
assert.ok(Math.abs(r.margin(site, far, 20000, 40) - (20000 - 20 * geo.NM / 20 - 5800)) < 15); // flat-earth distances differ a little with where they are measured from
assert.ok(Math.abs(r.margin(site, far, 20000, 40) - r.margin(site, far, 20000, 220) - 600) < 2);
assert.strictEqual(r.radius(5000, 2300), 0);
assert.ok(Math.abs(r.radius(25800, 2300) - 20000 * 20) < 1e-6);
console.log('reach OK');
