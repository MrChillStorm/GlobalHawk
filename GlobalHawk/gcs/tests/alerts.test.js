// node tests/alerts.test.js
const assert = require('assert');
const { Alerts } = require('../js/alerts.js');
let now = 100000;
const A = new Alerts(() => now);
const ids = () => A.items.map((a) => a.id);
const al = (id, level) => ({ id, level, text: id.toUpperCase(), action: 'do ' + id });

// order: warnings, cautions, advisories; newest first within a level
A.update([al('fuel-low', 'caution')], now, true);
now += 1000;
A.update([al('fuel-low', 'caution'), al('off-plan', 'advisory'), al('nav-one', 'caution')], now, true);
now += 1000;
A.update([al('fuel-low', 'caution'), al('off-plan', 'advisory'), al('nav-one', 'caution'), al('structure', 'warning')], now, true);
assert.deepStrictEqual(ids(), ['structure', 'nav-one', 'fuel-low', 'off-plan']);
// a tone for the worst unacknowledged; advisories ask for none
assert.strictEqual(A.tone(), 'warning');
A.acknowledge('structure');
assert.strictEqual(A.tone(), 'caution');
A.acknowledge();
assert.strictEqual(A.tone(), null);
// acknowledged alerts stay listed while their condition lasts, and stay acknowledged
A.update([al('fuel-low', 'caution'), al('structure', 'warning')], now, true);
assert.deepStrictEqual(ids(), ['structure', 'fuel-low']);
assert.strictEqual(A.tone(), null);
// the condition ends: gone. It returns: alerts again
A.update([al('structure', 'warning')], now, true);
assert.deepStrictEqual(ids(), ['structure']);
now += 5000;
A.update([al('structure', 'warning'), al('fuel-low', 'caution')], now, true);
assert.strictEqual(A.tone(), 'caution');
assert.strictEqual(A.items.find((a) => a.id === 'fuel-low').since, now);
// the engine holds back what is only a consequence of the glide
A.update([al('engine', 'warning'), al('aoa', 'caution'), al('aoa-near', 'advisory'), al('off-plan', 'advisory'), al('fuel-low', 'caution')], now, true);
assert.deepStrictEqual(ids(), ['engine', 'fuel-low']);
assert.strictEqual(A.items[0].action, 'do engine');
// nothing heard for 3 s: one warning, the station's own; heard again: the aircraft's list is back
A.update([al('fuel-low', 'caution')], now - 3001, true);
assert.deepStrictEqual(ids(), ['no-link']);
assert.strictEqual(A.tone(), 'link');       // changed on purpose (Hobbs and Lyall P_1.5.2): the loss of the link has a sound of its own
A.update([al('fuel-low', 'caution')], now, true);
assert.deepStrictEqual(ids(), ['fuel-low']);
// a station that never expected a link does not alarm
const B = new Alerts(() => now);
B.update(null, null, false);
assert.deepStrictEqual(B.items, []);
B.update(null, null, true);
assert.deepStrictEqual(B.items.map((a) => a.id), ['no-link']);
console.log('alerts OK');
