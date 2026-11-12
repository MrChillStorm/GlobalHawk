// node tests/link.test.js : the command link's station end, with a fake transport and a fake clock
const assert = require('assert');
const { Link, ANSWER_MS } = require('../js/link.js');

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
