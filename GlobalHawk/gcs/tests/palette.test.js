// node tests/palette.test.js
// L2 of the map-layers plan (docs/PLAN.md): no overlay's colour is mistaken for the station's own or for another overlay's.
const assert = require('assert');
const P = require('../js/palette.js');
const fs = require('fs');
const map = fs.readFileSync(__dirname + '/../js/map.js', 'utf8');
// the existing seven are the ones map.js really uses
const COL = /const COL = \{([^}]*)\}/.exec(map)[1];
for (const [k, v] of Object.entries(P.EXISTING)) assert.ok(new RegExp(`${k}: '${v}'`).test(COL), `${k} ${v} is map.js's`);
const names = Object.keys(P.LAYERS);
for (const n of names) {
  for (const [k, v] of Object.entries(P.EXISTING)) assert.ok(P.distance(P.LAYERS[n], v) >= P.MIN_DISTANCE, `${n} ${P.LAYERS[n]} is ${P.distance(P.LAYERS[n], v).toFixed(0)} from the station's ${k} ${v}`);
  for (const m of names) if (m < n) assert.ok(P.distance(P.LAYERS[n], P.LAYERS[m]) >= P.MIN_DISTANCE, `${n} and ${m} are ${P.distance(P.LAYERS[n], P.LAYERS[m]).toFixed(0)} apart`);
}
console.log('palette: ok');
