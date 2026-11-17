// node tests/link.test.js : the command link's station end, with a fake transport and a fake clock
const assert = require('assert');
const { Link, ANSWER_MS } = require('../js/link.js');
const demoground = require('../js/demoground.js');

function rig(opts) {
  let now = 1000000;
  const timers = [];
  const sent = [];
  const transport = { send: (p, v) => sent.push({ t: now, path: p, value: v }), listen: (p) => (transport.paths = p) };
  const link = new Link(Object.assign({ transport, station: 'T', firstSeq: 10, now: () => now, setTimeout: (fn, ms) => timers.push({ at: now + ms, fn }) }, opts || {}));
  const advance = (ms) => {
    const end = now + ms;
    for (;;) {
      timers.sort((a, b) => a.at - b.at);
      if (!timers.length || timers[0].at > end) break;
      const t = timers.shift();
      now = t.at;
      t.fn();
    }
    now = end;
  };
  const ack = (seq, status, reason, station) => transport.onValue('/gcs/down/ack', JSON.stringify({ seq, station: station || 'T', status, reason: reason || '' }));
  return { link, sent, advance, ack, transport, cmds: () => sent.filter((s) => s.path === '/gcs/up/cmd'), beats: () => sent.filter((s) => s.path === '/gcs/up/heartbeat') };
}

// a command is sent with the next seq and counts only when acknowledged
{
  const r = rig();
  const c = r.link.command('goto', { lat: 1, lon: 2, alt_ft: 3 });
  assert.strictEqual(c.state, 'sent');
  assert.deepStrictEqual(JSON.parse(r.cmds()[0].value), { seq: 11, station: 'T', name: 'goto', args: { lat: 1, lon: 2, alt_ft: 3 } });
  r.ack(11, 'accepted');
  assert.strictEqual(c.state, 'accepted');
}
// rejected, with the aircraft's reason
{
  const r = rig();
  const c = r.link.command('start');
  r.ack(11, 'rejected', 'no plan');
  assert.strictEqual(c.state, 'rejected');
  assert.strictEqual(c.reason, 'no plan');
}
// someone else's answer, or an old seq, changes nothing
{
  const r = rig();
  const c = r.link.command('hold');
  r.ack(11, 'accepted', '', 'OTHER');
  r.ack(10, 'accepted');
  assert.strictEqual(c.state, 'sent');
}
// no answer after 5 s; a late answer still counts
{
  const r = rig();
  const c = r.link.command('hold');
  r.advance(ANSWER_MS - 100);
  assert.strictEqual(c.state, 'sent');
  r.advance(200);
  assert.strictEqual(c.state, 'no answer');
  r.ack(11, 'accepted');
  assert.strictEqual(c.state, 'accepted');
}
// the heartbeat: once a second, a changing counter; stop() ends it
{
  const r = rig();
  r.link.start([]);
  r.advance(5000);
  const b = r.beats();
  assert.ok(b.length >= 5 && b.length <= 6, 'beats in 5 s: ' + b.length);
  assert.strictEqual(new Set(b.map((x) => x.value)).size, b.length);
  r.link.stop();
  r.advance(5000);
  assert.strictEqual(r.beats().length, b.length);
  assert.ok(r.transport.paths.includes('/gcs/down/status'));
}
// the heartbeat names its station; control is what the aircraft says it is
{
  const r = rig();
  r.link.start([]);
  r.advance(1000);
  assert.ok(/^T:\d+$/.test(r.beats()[0].value), r.beats()[0].value);
  assert.strictEqual(r.link.inControl(), false);
  r.transport.onValue('/gcs/down/status', JSON.stringify({ control: { holder: 'T' } }));
  assert.strictEqual(r.link.inControl(), true);
  r.transport.onValue('/gcs/down/status', JSON.stringify({ control: { holder: 'OTHER' } }));
  assert.strictEqual(r.link.inControl(), false);
}
// the stick goes up with the station's name, late by the delay
{
  const r = rig({ latency: 300 });
  r.link.stick({ p: -1, r: 0.5, y: 0, t: 0.7, s: 0 });
  const sticks = () => r.sent.filter((x) => x.path === '/gcs/up/stick');
  assert.strictEqual(sticks().length, 0);
  r.advance(300);
  assert.deepStrictEqual(JSON.parse(sticks()[0].value), { station: 'T', p: -1, r: 0.5, y: 0, t: 0.7, s: 0 });
}
// satellite latency: the uplink leaves late, the answer arrives late, and "no answer" allows for both
{
  const r = rig({ latency: 1200 });
  const c = r.link.command('hold');
  assert.strictEqual(r.cmds().length, 0);
  r.advance(1199);
  assert.strictEqual(r.cmds().length, 0);
  r.advance(2);
  assert.strictEqual(r.cmds().length, 1);
  r.ack(11, 'accepted');
  assert.strictEqual(c.state, 'sent');
  r.advance(1200);
  assert.strictEqual(c.state, 'accepted');
  const d = r.link.command('hold');
  r.advance(ANSWER_MS + 1000);
  assert.strictEqual(d.state, 'sent', 'still inside the time a delayed link needs');
  r.advance(1500);
  assert.strictEqual(d.state, 'no answer');
}
// status and plan come through parsed; rubbish is ignored
{
  const r = rig();
  const seen = [];
  r.link.on((what) => seen.push(what));
  r.transport.onValue('/gcs/down/status', JSON.stringify({ doing: 'hold at 18000 ft' }));
  r.transport.onValue('/gcs/down/status', '{not json');
  r.transport.onValue('/gcs/down/plan', JSON.stringify({ id: 'p' }));
  assert.strictEqual(r.link.status.doing, 'hold at 18000 ft');
  assert.strictEqual(r.link.plan.id, 'p');
  assert.ok(seen.includes('status') && seen.includes('plan'));
}
console.log('link OK');

// ---- messages between stations and the measured answer time (the station gaps)
{
  const { CHAT } = require('../js/link.js');
  // S8: a message goes out at once, with no delay; the link's own delay is on commands, not on talk between crews
  const R = rig({ latency: 600 });
  const m = R.link.say('  hold at 18,000 for the tanker  ');
  assert.deepStrictEqual([m.station, m.text], ['T', 'hold at 18,000 for the tanker']);
  assert.strictEqual(R.sent.filter((x) => x.path === CHAT).length, 1, 'sent at once, not after 600 ms');
  assert.strictEqual(R.link.say('   '), null);
  assert.strictEqual(R.link.say('x'.repeat(201)), null);
  assert.ok(R.link.say('x'.repeat(200)));
  assert.strictEqual(R.link.messages.length, 2);
  assert.ok(R.link.messages.every((x) => x.mine));
  // heard from another station at once, and our own coming back is not shown twice
  const heard = [];
  R.link.on((what, x) => what === 'message' && heard.push(x));
  R.transport.onValue(CHAT, JSON.stringify({ station: 'MCE', n: 7, text: 'copy', t: 123 }));
  assert.strictEqual(heard.length, 1);
  assert.deepStrictEqual([heard[0].station, heard[0].text, heard[0].mine], ['MCE', 'copy', false]);
  R.transport.onValue(CHAT, JSON.stringify({ station: 'MCE', n: 7, text: 'copy', t: 123 }));       // twice: once
  R.transport.onValue(CHAT, JSON.stringify(m));                                                       // our own, echoed
  assert.strictEqual(heard.length, 1);
  assert.strictEqual(R.link.messages.length, 3);
  // not messages: ignored
  for (const junk of ['', 'not json', '{}', JSON.stringify({ station: 'X', n: 'a', text: 'b' }), JSON.stringify({ station: 'X', n: 1, text: 'y'.repeat(201) })]) R.transport.onValue(CHAT, junk);
  assert.strictEqual(R.link.messages.length, 3);
  R.link.start([]);
  assert.ok(R.transport.paths.includes(CHAT), 'listening to the messages');
  R.link.stop();
  // only the last fifty are kept
  for (let i = 0; i < 60; i++) R.transport.onValue(CHAT, JSON.stringify({ station: 'MCE', n: 100 + i, text: 'm' + i, t: i }));
  assert.strictEqual(R.link.messages.length, 50);
  assert.strictEqual(R.link.messages[49].text, 'm59');

  // S5: the answer time is the median of the last five answered commands, ms
  const Q = rig({ latency: 0 });
  assert.strictEqual(Q.link.answerMs(), null);
  for (const wait of [1000, 1100, 5000, 1200, 1300, 1150]) {
    const c = Q.link.command('hold');
    Q.advance(wait);
    if (wait < 5000) Q.ack(c.seq, 'accepted');
    else Q.advance(1000);                                  // no answer: not counted
  }
  const last5 = [1100, 1200, 1300, 1150].sort((a, b) => a - b);
  assert.ok([1000, ...last5].length >= 5);
  const med = Q.link.answerMs();
  assert.ok(med >= 1100 && med <= 1200, 'median of the last answered, got ' + med);
  // the delay may be changed while running, and takes effect on the next message
  Q.link.latency = 300;
  const n0 = Q.cmds().length;
  Q.link.command('hold');
  Q.advance(299);
  assert.strictEqual(Q.cmds().length, n0, 'not yet');
  Q.advance(2);
  assert.strictEqual(Q.cmds().length, n0 + 1, 'after the new delay');
}
// the airport's ground map comes down on its own path, as an object; nonsense is not kept
{
  const r = rig();
  r.link.start();
  assert.ok(r.transport.paths.includes('/gcs/down/airport'), 'listened to');
  const seen = [];
  r.link.on((what, data) => what === 'airport' && seen.push(data));
  r.transport.onValue('/gcs/down/airport', JSON.stringify(demoground));
  assert.strictEqual(r.link.airport.icao, 'XDM1');
  assert.strictEqual(seen.length, 1);
  r.transport.onValue('/gcs/down/airport', '{"icao":"X"}');
  assert.strictEqual(r.link.airport, null, 'a message without its lists is not an airport');
  r.transport.onValue('/gcs/down/airport', '{broken');
  assert.strictEqual(seen.length, 2, 'unreadable text changes nothing');
  r.transport.onValue('/gcs/down/airport', '');
  assert.strictEqual(r.link.airport, null);
}
// the aircraft takes a minute to answer a reposition (FlightGear loads the scenery at the new place); the others have five seconds
{
  const r = rig();
  const a = r.link.command('reposition', { lat: 1, lon: 2, heading: 3 });
  const b = r.link.command('hold');
  r.advance(ANSWER_MS + 100);
  assert.strictEqual(a.state, 'sent', 'still waiting');
  assert.strictEqual(b.state, 'no answer');
  r.advance(60000);
  assert.strictEqual(a.state, 'no answer', 'after a minute');
  r.ack(a.seq, 'accepted');
  assert.strictEqual(a.state, 'accepted', 'a late answer still counts');
}
console.log('link messages OK');

// a heartbeat that went late is recorded (the browser slowing the page, a stall of the machine), and a normal one is not
{
  const r = rig();
  r.link.start([]);
  r.advance(5000);
  assert.strictEqual(r.link.stalls.length, 0, 'beats on time: no stall');
  // the page stops for 20 s: the next tick finds the gap
  r.link.beating = false;
  r.advance(20000);
  r.link.beating = true;
  r.link.lastTick = r.link.lastTick; // unchanged: the gap is measured against the last tick
  r.advance(1500);
  r.link.start([]);
  assert.ok(r.link.stalls.length >= 1 && r.link.stalls[0].gapMs >= 19000, 'a gap of 20 s is recorded: ' + JSON.stringify(r.link.stalls));
}
// without workers (node) the default timer is the page's own setTimeout and the link works
{
  const sent = [];
  const link = new Link({ transport: { send: (p, v) => sent.push(p), listen: () => {} }, station: 'T' });
  assert.strictEqual(typeof link.timer, 'function');
  link.start([]);
  link.stop();
  assert.ok(sent.some((p) => p === '/gcs/up/heartbeat'), 'it beats at once');
}
console.log('link stalls: ok');
