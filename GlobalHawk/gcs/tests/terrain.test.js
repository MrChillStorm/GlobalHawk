// node tests/terrain.test.js
// Terrain against a height: the Terrarium encoding, the three classes at their edges, the shading of a tile.
const assert = require('assert');
const R = require('../js/terrain.js');
const enc = (m) => { const v = m + 32768; return [Math.floor(v / 256), Math.floor(v % 256), Math.round((v - Math.floor(v)) * 256) % 256]; };
// the encoding: sea level, a mountain, a fraction
assert.strictEqual(R.elevationM(128, 0, 0), 0);
assert.strictEqual(R.elevationM(...enc(701)), 701);
assert.ok(Math.abs(R.elevationM(...enc(4421.5)) - 4421.5) < 0.01);
assert.strictEqual(R.elevationM(...enc(-86)), -86, 'below sea level');
// the classes: 1,000 m = 3,281 ft
assert.strictEqual(R.classify(10000, 1000), 0, 'clear, 6,700 ft under');
assert.strictEqual(R.classify(3281 + 500, 1000), 0, 'exactly NEAR_FT above: clear');
assert.strictEqual(R.classify(3281 + 499, 1000), 1, 'within 500 ft');
assert.strictEqual(R.classify(3281, 1000), 1, 'at the height of the ground, to the foot: 1 (3,280.84 ft)');
assert.strictEqual(R.classify(3280, 1000), 2, 'below the ground');
assert.strictEqual(R.classify(2000, 1000), 2, 'under the ground');
assert.strictEqual(R.classify(100, 0), 0, 'sea level is not terrain');
assert.strictEqual(R.classify(-50, -86), 0, 'nor the Dead Sea');
// a tile: a ridge of 2,000 m across half of it, flat 700 m on the other half, seen from 7,000 ft (2,134 m) and from 6,000 ft
const rgba = new Uint8ClampedArray(256 * 256 * 4);
for (let i = 0; i < 256 * 256; i++) { const [r, g, b] = enc(i % 256 < 128 ? 700 : 2000); rgba.set([r, g, b, 255], i * 4); }
const out = new Uint8ClampedArray(rgba.length);
let n = R.shade(rgba, 7000, out);
assert.strictEqual(n[0] + n[1] + n[2], 65536);
assert.strictEqual(n[0], 32768, 'the 700 m half is 4,700 ft below: clear');
assert.strictEqual(n[1], 32768, 'the 2,000 m half is 6,562 ft: 438 ft under 7,000');
assert.deepStrictEqual([...out.slice(0, 4)], [0, 0, 0, 0]);
assert.strictEqual(out[128 * 4 + 3], 120);
n = R.shade(rgba, 6000, out);
assert.strictEqual(n[2], 32768, 'at 6,000 ft the ridge is above the aircraft');
assert.strictEqual(out[128 * 4 + 3], 150);
assert.strictEqual(R.urlFor(5, 5, 12), 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/5/5/12.png');
console.log('terrain: ok');
