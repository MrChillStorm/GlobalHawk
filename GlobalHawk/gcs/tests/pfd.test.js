// node tests/pfd.test.js : the flight display's numbers
const assert = require('assert');
const m = require('../js/pfdmath.js');
const near = (a, b, tol) => assert.ok(Math.abs(a - b) <= tol, `${a} vs ${b}`);

// cruise at 60,000 ft, Mach 0.6, 15,000 lb: 105.6 KCAS-ish, angle of attack 0.9 deg, limit 3.5 deg (the model's trim)
const cruise = m.speedLimits(108, 0.9, 3.5, 0.6);
assert.ok(cruise.low < 108 && cruise.high > 108, 'the present speed is inside');
assert.ok(cruise.high - cruise.low < 25, `coffin corner: ${(cruise.high - cruise.low).toFixed(1)} kt wide`);
near(cruise.high, 108 * 0.63 / 0.6, 0.01);
// climb at 20,000 ft, 150 KCAS: Mach 0.33, angle of attack 0.5 deg, limit 5.8 deg
const climb = m.speedLimits(150, 0.5, 5.8, 0.33);
assert.ok(climb.high - climb.low > 50, `wide lower down: ${(climb.high - climb.low).toFixed(1)}`);
near(climb.high, 175, 1e-9);
// at the limit the low speed is the present speed
near(m.speedLimits(100, 6, 6, 0.2).low, 100, 1e-9);
// trends
near(m.trend(150, -1.5), 135, 1e-9);
near(m.kcasRate(150, 500, 5), 1.5, 1e-9);
near(m.kcasRate(0, 0, 5), 0, 1e-9);
// heading wrap and the pitch scale
near(m.wrap(350 - 10), -20, 1e-9);
near(m.wrap(10 - 350), 20, 1e-9);
near(m.wrap(180), -180, 1e-9);
near(m.pitchY(10, 6), -60, 1e-9);
console.log('pfd OK');
