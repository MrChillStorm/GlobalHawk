// node tests/linkinfo.test.js : the link's countdown, restored message, closing warning and time-out bounds
const assert = require('assert');
const L = require('../js/linkinfo.js');
const { Alerts } = require('../js/alerts.js');

const st = (o) => Object.assign({ started: true, kind: 'route', link_lost: false, link_age: 0.4, link_timeout: 30, control: { holder: 'LRE' } }, o || {});

// S2: no count while the uplink is heard; a count from 3 s; none once lost
assert.strictEqual(L.countdown(st()), null);
assert.strictEqual(L.countdown(st({ link_age: 2.9 })), null);
const c = L.countdown(st({ link_age: 12.4 }));
assert.ok(Math.abs(c.left - 17.6) < 1e-9 && c.age === 12.4 && c.holder === 'LRE');
assert.strictEqual(L.countdown(st({ link_age: 40, link_lost: true })), null);
assert.strictEqual(L.countdown(st({ link_age: null })), null);
assert.strictEqual(L.countdown(null), null);
assert.strictEqual(L.countdown(st({ link_age: 12, link_timeout: 15 })).left, 3);       // the time-out set, not 30
assert.strictEqual(L.countdown(st({ link_age: 31, link_timeout: 30 })).left, 0);       // never below zero
assert.strictEqual(L.countdownText(c, 'LRE'), 'the aircraft has not heard this station for 12 s: route home in 18 s');
assert.strictEqual(L.countdownText(c, 'MCE'), 'the aircraft has not heard LRE for 12 s: route home in 18 s');
assert.strictEqual(L.countdownText(null, 'LRE'), '');

// S3: restored only after a link that was had and lost, for 20 s
let r = new L.Restored();
assert.strictEqual(r.update(false, 0), false);          // never linked: not "restored"
assert.strictEqual(r.update(true, 1000), false);        // the first link
assert.strictEqual(r.update(true, 5000), false);
assert.strictEqual(r.update(false, 6000), false);       // lost
assert.strictEqual(r.update(false, 9000), false);
assert.strictEqual(r.update(true, 10000), true);        // back
assert.strictEqual(r.update(true, 10000 + L.RESTORED_MS - 1), true);
assert.strictEqual(r.update(true, 10000 + L.RESTORED_MS), false);
assert.strictEqual(r.update(false, 40000), false);
assert.strictEqual(r.update(true, 41000), true);        // and again

// S9: the warning only for the station in control of a flight in progress
assert.ok(/30 s later the aircraft leaves its plan/.test(L.closingWarning(st(), 'LRE')));
assert.ok(/15 s later/.test(L.closingWarning(st({ link_timeout: 15 }), 'LRE')));
assert.strictEqual(L.closingWarning(st(), 'MCE'), null);                  // a watcher may close its page
assert.strictEqual(L.closingWarning(st({ started: false }), 'LRE'), null);
assert.strictEqual(L.closingWarning(st({ kind: 'done' }), 'LRE'), null);
assert.strictEqual(L.closingWarning(null, 'LRE'), null);

// S1's station end: the bounds are the aircraft's
assert.strictEqual(L.validTimeout(10), 10);
assert.strictEqual(L.validTimeout(300), 300);
assert.strictEqual(L.validTimeout(9.9), null);
assert.strictEqual(L.validTimeout(300.1), null);
assert.strictEqual(L.validTimeout(NaN), null);
const src = require('fs').readFileSync(__dirname + '/../../../fdm/onboard.py', 'utf8');
assert.ok(src.includes(`LINK_TIMEOUT_MIN, LINK_TIMEOUT_MAX = ${L.TIMEOUT_MIN}.0, ${L.TIMEOUT_MAX}.0`), "the station's bounds are the aircraft's");

// S4: the link alerts have a tone of their own, ahead of the others; the rest as before
const a = new Alerts(() => 0);
a.update([{ id: 'engine', level: 'warning', text: 'ENGINE FAILED', action: '' }], 0, true, []);
assert.strictEqual(a.tone(), 'warning');
a.update([{ id: 'link', level: 'caution', text: 'LINK WAS LOST', action: '' }], 0, true, []);
assert.strictEqual(a.tone(), 'link');
a.update([{ id: 'engine', level: 'warning', text: 'ENGINE FAILED', action: '' }, { id: 'link', level: 'caution', text: 'LINK WAS LOST', action: '' }], 0, true, []);
assert.strictEqual(a.tone(), 'link', 'the link first');
a.acknowledge('link');
assert.strictEqual(a.tone(), 'warning', 'acknowledged, the next one sounds');
const b = new Alerts(() => 1000000);
b.update([], 0, true, []);                                                 // nothing heard for a long time: the station's own alert
assert.strictEqual(b.items[0].id, 'no-link');
assert.strictEqual(b.tone(), 'link');
const d = new Alerts(() => 0);
d.update([{ id: 'fuel-low', level: 'caution', text: 'FUEL LOW', action: '' }], 0, true, []);
assert.strictEqual(d.tone(), 'caution');
console.log('linkinfo OK');
