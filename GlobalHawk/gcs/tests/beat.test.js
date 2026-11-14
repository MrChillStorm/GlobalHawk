// node tests/beat.test.js
// The station's heartbeat follows the simulation's speed: the aircraft counts the silence in its own seconds.
const assert = require('assert');
const { Link } = require('../js/link.js');
const timers = [];
const sent = [];
const t = { send: (p, v) => sent.push([p, v]), listen: () => {} };
const link = new Link({ transport: t, setTimeout: (fn, ms) => timers.push([ms, fn]), now: () => 1000000 });
link.start([]);
assert.strictEqual(timers[timers.length - 1][0], 1000, 'a beat a second by default');
link.setBeatMs(250);
timers.pop()[1](); // the next tick runs and schedules the one after at the new interval
assert.strictEqual(timers[timers.length - 1][0], 250, 'at four times as fast a simulation, four beats a second');
assert.strictEqual(sent.filter((x) => x[0] === '/gcs/up/heartbeat').length, 2);
link.setBeatMs(10);
assert.strictEqual(link.beatMs, 100, 'never faster than 100 ms');
link.setBeatMs(5000);
assert.strictEqual(link.beatMs, 1000, 'never slower than the usual second');
link.setBeatMs(1000 / 4);
assert.strictEqual(link.beatMs, 250);
// the count of the silence in the aircraft's seconds: with a beat every 250 ms real at 4 x the gap is one simulated second, under the 3 s the note waits for
const gapSim = (link.beatMs / 1000) * 4;
assert.ok(gapSim <= 1.0 + 1e-9);
const li = require('../js/linkinfo.js');
assert.strictEqual(li.countdown({ link_age: gapSim, link_timeout: 120 }), null, 'no note');
assert.ok(li.countdown({ link_age: 4, link_timeout: 120 }), 'a beat a real second at 4 x is a 4 s gap: the note flickers');
console.log('beat: ok');
