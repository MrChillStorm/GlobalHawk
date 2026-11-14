// node tests/layers.test.js
// L1 of the map-layers plan (docs/PLAN.md): the registry's rules, one assertion for each limit written there.
const assert = require('assert');
const L = require('../js/layers.js');

let t = 0;
const make = (storage) => {
  const r = new L.Layers({ now: () => t, storage });
  return r;
};
const ctx = {};
const rule = (key, reason, force) => (c) => (c[key] ? { on: true, reason: reason || key, force: !!force } : null);

// Off hides, On shows, Auto follows the rule
{
  t = 0;
  const r = make(null);
  r.define({ id: 'a', mode: 'auto', auto: rule('a') });
  r.define({ id: 'b', mode: 'on', auto: rule('b') });
  r.define({ id: 'c', mode: 'off', auto: rule('c') });
  const c = { a: true, b: false, c: true };
  r.update(c);
  assert.strictEqual(r.shown('b'), true, 'On shows with no reason');
  assert.strictEqual(r.state('b').source, 'on');
  assert.strictEqual(r.shown('c'), false, 'Off hides whatever the rule says');
  assert.strictEqual(r.shown('a'), false, 'Auto not yet: the rule must hold first');
  t = 2000;
  r.update(c);
  assert.strictEqual(r.shown('a'), true);
  assert.strictEqual(r.state('a').source, 'auto');
  assert.strictEqual(r.state('a').reason, 'a');
}

// 1.9 s is not enough, 2.0 s is
{
  t = 0;
  const r = make(null);
  r.define({ id: 'a', auto: rule('a') });
  const c = { a: true };
  r.update(c);
  t = 1900;
  r.update(c);
  assert.strictEqual(r.shown('a'), false, '1.9 s');
  t = 2000;
  r.update(c);
  assert.strictEqual(r.shown('a'), true, '2.0 s');
  // a rule that drops out for a moment before 2 s starts the count again
  t = 10000;
  const r2 = make(null);
  r2.define({ id: 'a', auto: rule('a') });
  const c2 = { a: true };
  r2.update(c2); // t=10000
  t = 11500;
  c2.a = false;
  r2.update(c2);
  t = 11600;
  c2.a = true;
  r2.update(c2);
  t = 13500;
  r2.update(c2);
  assert.strictEqual(r2.shown('a'), false, '1.9 s since it came back');
  t = 13600;
  r2.update(c2);
  assert.strictEqual(r2.shown('a'), true);
}

// false for 59 s keeps it, 60 s takes it away
{
  t = 0;
  const r = make(null);
  r.define({ id: 'a', auto: rule('a') });
  const c = { a: true };
  r.update(c);
  t = 2000;
  r.update(c);
  assert.strictEqual(r.shown('a'), true);
  c.a = false;
  t = 5000;
  r.update(c);
  t = 5000 + 59000;
  r.update(c);
  assert.strictEqual(r.shown('a'), true, '59 s false: still there');
  t = 5000 + 60000;
  r.update(c);
  assert.strictEqual(r.shown('a'), false, '60 s false: gone');
  // and a rule that returns inside the 60 s never lets it go
  c.a = true;
  t += 1000;
  r.update(c);
  t += 2000;
  r.update(c);
  assert.strictEqual(r.shown('a'), true);
}

// the fourth automatic layer waits; of any four the three most safety-relevant show
{
  t = 0;
  const r = make(null);
  r.define({ id: 'w1', rank: 40, auto: rule('on') });
  r.define({ id: 's1', rank: 10, auto: rule('on') });
  r.define({ id: 'g1', rank: 30, auto: rule('on') });
  r.define({ id: 'm1', rank: 20, auto: rule('on') });
  const c = { on: true };
  r.update(c);
  t = 2000;
  r.update(c);
  const shown = ['w1', 's1', 'g1', 'm1'].filter((id) => r.shown(id));
  assert.deepStrictEqual(shown.sort(), ['g1', 'm1', 's1'], 'the three lowest ranks');
  assert.deepStrictEqual(r.waiting(), ['w1']);
  assert.strictEqual(r.state('w1').source, 'waiting');
  assert.strictEqual(r.chips().length, 3);
  // a layer the user turned On does not use the budget
  r.setMode('w1', 'on');
  r.update(c);
  assert.strictEqual(r.shown('w1'), true);
  assert.strictEqual(['s1', 'm1', 'g1'].filter((id) => r.shown(id)).length, 3);
}

// layers that were always there do not use up the budget
{
  t = 0;
  const r = make(null);
  r.define({ id: 'old1', rank: 1, budget: false, auto: rule('on') });
  r.define({ id: 'old2', rank: 2, budget: false, auto: rule('on') });
  r.define({ id: 'n1', rank: 10, auto: rule('on') });
  r.define({ id: 'n2', rank: 11, auto: rule('on') });
  r.define({ id: 'n3', rank: 12, auto: rule('on') });
  r.define({ id: 'n4', rank: 13, auto: rule('on') });
  const c = { on: true };
  r.update(c);
  t = 2000;
  r.update(c);
  assert.deepStrictEqual(['old1', 'old2', 'n1', 'n2', 'n3', 'n4'].filter((id) => r.shown(id)), ['old1', 'old2', 'n1', 'n2', 'n3'], 'two old ones and three new ones');
  assert.deepStrictEqual(r.waiting(), ['n4']);
}

// a forced layer shows when Off and when decluttered, at once, and stops 60 s after its cause
{
  t = 0;
  const r = make(null);
  r.define({ id: 'f', mode: 'off', rank: 1, auto: rule('f', 'engine out', true) });
  r.define({ id: 'p', mode: 'on', auto: null });
  r.setDeclutter(true);
  const c = { f: true };
  r.update(c);
  assert.strictEqual(r.shown('f'), true, 'at once');
  assert.strictEqual(r.state('f').source, 'forced');
  assert.strictEqual(r.state('f').forced, true);
  assert.strictEqual(r.shown('p'), false, 'decluttered, though On');
  assert.strictEqual(r.dismiss('f'), false, 'a forced layer cannot be dismissed');
  c.f = false;
  t = 10000;
  r.update(c);
  t = 10000 + 59999;
  r.update(c);
  assert.strictEqual(r.shown('f'), true, 'cause ended 59.999 s ago');
  t = 10000 + 60000;
  r.update(c);
  assert.strictEqual(r.shown('f'), false, '60 s after the cause');
}

// dismiss holds until the rule has been false (10 s) and has come back (2 s)
{
  t = 0;
  const r = make(null);
  r.define({ id: 'a', auto: rule('a') });
  const c = { a: true };
  r.update(c);
  t = 2000;
  r.update(c);
  assert.strictEqual(r.shown('a'), true);
  assert.strictEqual(r.dismiss('a'), true);
  r.update(c);
  assert.strictEqual(r.shown('a'), false);
  assert.strictEqual(r.state('a').source, 'dismissed');
  t = 600000;
  r.update(c);
  assert.strictEqual(r.shown('a'), false, 'the reason stays: it stays away');
  c.a = false;
  t = 600000;
  r.update(c);
  t = 609000;
  r.update(c);
  c.a = true; // back after 9 s: not long enough
  t = 609500;
  r.update(c);
  t = 620000;
  r.update(c);
  assert.strictEqual(r.shown('a'), false, 'false for 9 s only');
  c.a = false;
  t = 621000;
  r.update(c);
  t = 631000; // 10 s
  r.update(c);
  assert.strictEqual(r.shown('a'), false, 'the reason has gone: nothing to show');
  c.a = true;
  t = 632000;
  r.update(c);
  t = 634000;
  r.update(c);
  assert.strictEqual(r.shown('a'), true, 'it came back and held 2 s');
}

// declutter, then undeclutter, gives the same modes and the same picture
{
  t = 0;
  const r = make(null);
  r.define({ id: 'a', auto: rule('a') });
  r.define({ id: 'b', mode: 'on' });
  r.define({ id: 'c', mode: 'off' });
  const c = { a: true };
  r.update(c);
  t = 2000;
  r.update(c);
  const before = JSON.stringify(r.update(c));
  const modes = JSON.stringify(r.modes);
  r.setDeclutter(true);
  const during = r.update(c);
  assert.ok(!during.a.shown && !during.b.shown && !during.c.shown, 'everything optional away');
  assert.strictEqual(during.b.source, 'declutter');
  r.setDeclutter(false);
  assert.strictEqual(JSON.stringify(r.update(c)), before);
  assert.strictEqual(JSON.stringify(r.modes), modes);
}

// keeping the choices; a storage that breaks changes nothing
{
  const bag = {};
  const storage = { getItem: (k) => (k in bag ? bag[k] : null), setItem: (k, v) => { bag[k] = v; } };
  const r = make(storage);
  r.define({ id: 'a' });
  r.define({ id: 'b', mode: 'on' });
  r.setMode('a', 'off');
  r.setMode('b', 'auto');
  assert.strictEqual(r.setMode('a', 'maybe'), false);
  assert.strictEqual(r.setMode('nope', 'on'), false);
  r.save({ base: 'topo' });
  const r2 = make(storage);
  r2.define({ id: 'a' });
  r2.define({ id: 'b', mode: 'on' });
  const rec = r2.load();
  assert.strictEqual(r2.mode('a'), 'off');
  assert.strictEqual(r2.mode('b'), 'auto');
  assert.strictEqual(rec.base, 'topo', 'extra preferences travel with the modes');
  // a layer saved and since removed, and a mode that is not one, are ignored
  bag['gcs.layers'] = JSON.stringify({ modes: { a: 'on', gone: 'on', b: 'sideways' } });
  const r3 = make(storage);
  r3.define({ id: 'a' });
  r3.define({ id: 'b', mode: 'on' });
  r3.load();
  assert.strictEqual(r3.mode('a'), 'on');
  assert.strictEqual(r3.mode('b'), 'on');
  const broken = { getItem: () => { throw new Error('no storage'); }, setItem: () => { throw new Error('no storage'); } };
  const r4 = make(broken);
  r4.define({ id: 'a', mode: 'on' });
  assert.strictEqual(r4.load(), null);
  r4.setMode('a', 'off');
  assert.strictEqual(r4.mode('a'), 'off', 'the choice lasts until the page closes');
  bag['gcs.layers'] = '{not json';
  const r5 = make(storage);
  r5.define({ id: 'a', mode: 'on' });
  assert.strictEqual(r5.load(), null);
  assert.strictEqual(r5.mode('a'), 'on');
}

// ?layers=
{
  const r = make(null);
  r.define({ id: 'airspace' });
  r.define({ id: 'wx-radar' });
  const done = r.applyQuery('airspace:on, wx-radar:off,unknown:on,airspace:sideways');
  assert.deepStrictEqual(done, { airspace: 'on', 'wx-radar': 'off' });
  assert.strictEqual(r.mode('airspace'), 'on');
}

// a rule that throws shows nothing and does not stop the others
{
  t = 0;
  const r = make(null);
  r.define({ id: 'bad', auto: () => { throw new Error('boom'); } });
  r.define({ id: 'good', auto: rule('on') });
  const c = { on: true };
  r.update(c);
  t = 2000;
  r.update(c);
  assert.strictEqual(r.shown('bad'), false);
  assert.strictEqual(r.shown('good'), true);
}

// defining twice is a mistake
{
  const r = make(null);
  r.define({ id: 'a' });
  assert.throws(() => r.define({ id: 'a' }));
}

console.log('layers: ok');
