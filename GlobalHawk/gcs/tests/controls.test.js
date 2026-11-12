// node tests/controls.test.js
const assert = require('assert');
const c = require('../js/controls.js');
const near = (a, b, tol) => assert.ok(Math.abs(a - b) <= (tol || 1e-9), `${a} vs ${b}`);
const rest = { p: 0, r: 0, y: 0, t: 0.5, s: 0 };

// gamepad: inside the dead zone is zero; full travel is full; pulled back (axis 1 positive) is nose up (p negative)
let g = c.fromGamepad([0.05, -0.07, 0.02, 0], [], rest, 0.05);
assert.deepStrictEqual([g.p, g.r, g.y], [0, 0, 0]);
g = c.fromGamepad([1, 1, -1, 0], [], rest, 0.05);
near(g.r, 1);
near(g.p, -1);
near(g.y, -1);
g = c.fromGamepad([0.54, 0, 0, 0], [], rest, 0.05);
near(g.r, 0.5, 1e-9);
// the triggers move the throttle lever, which stays where it is put
g = c.fromGamepad([0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, { value: 1 }], rest, 0.2);
near(g.t, 0.6);
g = c.fromGamepad([0, 0, 0, 0], [], g, 0.2);
near(g.t, 0.6);
g = c.fromGamepad([0, 0, 0, 0], [0, 0, 0, 0, 0, 0, { value: 1 }, 0], { ...rest, t: 0.02 }, 0.2);
near(g.t, 0);
// keys: up arrow is stick forward; held, the stick travels; released, it springs back
let k = rest;
for (let i = 0; i < 4; i++) k = c.fromKeys(new Set(['ArrowUp', 'ArrowRight']), k, 0.1);
near(k.p, 1);
near(k.r, 1);
k = c.fromKeys(new Set(['ArrowRight']), k, 0.1);
near(k.p, 0.6);
for (let i = 0; i < 3; i++) k = c.fromKeys(new Set(), k, 0.1);
near(k.p, 0);
near(k.r, 0);
k = c.fromKeys(new Set(['ArrowDown', 'q', 'w', 'x']), rest, 0.1);
assert.ok(k.p < 0 && k.y < 0 && k.t > 0.5 && k.s > 0);
console.log('controls OK');
