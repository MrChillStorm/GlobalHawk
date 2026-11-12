// node tests/camera.test.js
const assert = require('assert');
const c = require('../js/camera.js');
const { Link } = require('../js/link.js');

// nothing heard yet, and a camera that is free
assert.strictEqual(c.state({}).mode, 'free');
assert.strictEqual(c.state({ [c.PATHS.lock]: '', [c.PATHS.lat]: '', [c.PATHS.lon]: '' }).target, null);
// free, with an old target still in the properties: not shown as locked
assert.strictEqual(c.state({ [c.PATHS.lock]: 'free', [c.PATHS.lat]: 60.3, [c.PATHS.lon]: 25.0 }).mode, 'free');
// a point and an object
let s = c.state({ [c.PATHS.lock]: 'point', [c.PATHS.lat]: '60.45', [c.PATHS.lon]: '-25.1', [c.PATHS.range]: 23.04, [c.PATHS.level]: 1 });
assert.deepStrictEqual(s.target, [60.45, -25.1]);
assert.strictEqual(s.text, 'locked on the point 60.4500 N 25.1000 W, 23.0 nmi');
assert.strictEqual(s.level, true);
s = c.state({ [c.PATHS.lock]: 'object', [c.PATHS.name]: 'ship 3', [c.PATHS.lat]: -1.5, [c.PATHS.lon]: 30 });
assert.strictEqual(s.text, 'locked on ship 3 at 1.5000 S 30.0000 E');
assert.strictEqual(c.point([60.123456789, 24.5]), 'point 60.123457 24.500000');

// the link: a camera command goes to the camera's property, late by the link's delay, and not up the command link
const sent = [];
let timers = [];
const t = { send: (p, v) => sent.push([p, v]), listen: () => {} };
const link = new Link({ transport: t, latency: 600, setTimeout: (fn, ms) => timers.push([ms, fn]), now: () => 0 });
link.camera('nearest');
assert.strictEqual(sent.length, 0);
assert.strictEqual(timers[0][0], 600);
timers.shift()[1]();
assert.deepStrictEqual(sent, [[c.CAM + 'command', 'nearest']]);
assert.strictEqual(link.commands.length, 0);
// a slew: the rate, then zero again
sent.length = 0;
timers = [];
link.cameraSlew(1, -1);
timers.sort((a, b) => a[0] - b[0]).forEach((x) => x[1]());
assert.deepStrictEqual(sent, [[c.CAM + 'slew-right', 1], [c.CAM + 'slew-up', -1], [c.CAM + 'slew-right', 0], [c.CAM + 'slew-up', 0]]);
console.log('camera: ok');
