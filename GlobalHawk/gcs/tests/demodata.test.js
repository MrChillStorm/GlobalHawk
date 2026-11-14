// node tests/demodata.test.js
// The demo's made-up wind must have everything the page reads from the real wind field (a missing `cells` once made the plan editor throw at every tick in the demo).
const assert = require('assert');
const D = require('../js/demodata.js');
const W = require('../js/weather.js');
const real = new W.WindField({ fetch: async () => { throw new Error('unused'); } });
const demo = new D.DemoWind();
for (const k of ['cells', 'step', 'status']) assert.ok(k in real && k in demo, `the page reads "${k}" of the wind field: the demo's must have it as the real one does`);
for (const m of ['at', 'arrows', 'ensure']) assert.strictEqual(typeof demo[m], 'function', m);
assert.ok(demo.cells instanceof Map && demo.cells.size === 0);
const w = demo.at(35, -118, 60000, 0);
assert.ok(w.spd > 40 && w.dir === 250);
assert.ok(demo.arrows([34, -119, 36, -116], 60000, 0).length > 5);
// the made-up zones, fields, hazard and report are all there and well formed
assert.strictEqual(D.zones().length, 4);
assert.ok(D.zones().every((z) => z.bbox));
assert.ok(D.airports().every((a) => a.paved_ft !== undefined && a.rwys.length));
assert.strictEqual(D.hazards(Date.now())[0].kind, 'turb');
assert.strictEqual(D.metar(Date.now()).cat, 'VFR');
console.log('demodata: ok');
