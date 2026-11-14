// node tests/airports.test.js
// L4 of the map-layers plan (docs/PLAN.md): OurAirports' files, the runway test, the keeper. The CSV rows are OurAirports' own, saved 2026-11-14.
const assert = require('assert');
const fs = require('fs');
const AP = require('../js/airports.js');
const { Store } = require('../js/store.js');
const predict = require('../js/predict.js');
const perf = require('../js/perfdata.js');
const forecast = predict.make(perf);
const fx = (n) => fs.readFileSync(__dirname + '/fixtures/' + n, 'utf8');

// the CSV reader: quotes, commas inside, doubled quotes
assert.deepStrictEqual(AP.csvLine('1,"a, b",,"say ""hi""",x'), ['1', 'a, b', '', 'say "hi"', 'x']);

// airports: heliports are left out, the rest parse
const ap = AP.parseAirports(fx('ourairports-airports.csv'));
assert.deepStrictEqual(ap.map((a) => a.ident).sort(), ['KBFL', 'KEDW', 'KLAX', 'KMHV', 'KPMD', 'KSBA', 'KVCV', 'KWJF'], 'the heliport 00A is dropped');
const edw = ap.find((a) => a.ident === 'KEDW');
assert.strictEqual(edw.type, 'medium_airport');
assert.ok(Math.abs(edw.lat - 34.9) < 0.1 && Math.abs(edw.lon + 117.9) < 0.1);
assert.ok(edw.elev_ft > 2200 && edw.elev_ft < 2400, "elevation in feet: " + edw.elev_ft);
// a radius keeps what is near
const near = AP.parseAirports(fx('ourairports-airports.csv'), { center: [34.9, -117.88], radius_nm: 60 });
assert.ok(near.some((a) => a.ident === 'KEDW') && near.some((a) => a.ident === 'KPMD'));
assert.ok(!near.some((a) => a.ident === 'KLAX'), 'Los Angeles is further than 60 nmi');

// runways: closed ones and unknown fields are left out; the paved flag
const rw = AP.parseRunways(fx('ourairports-runways.csv'), null);
assert.strictEqual(rw.KEDW.length, 3);
assert.ok(rw.KEDW.some((r) => r.len_ft === 16798 && r.paved && r.le === '05R'));
assert.ok(rw['00A'][0].len_ft === 80);
const only = AP.parseRunways(fx('ourairports-runways.csv'), new Set(['KSBA']));
assert.deepStrictEqual(Object.keys(only), ['KSBA']);
const closed = 'airport_ident,length_ft,width_ft,surface,closed,le_ident,he_ident,le_heading_degT\nKXXX,9000,100,ASP,1,09,27,90\nKXXX,5000,100,GRS,0,18,36,180\n';
const rc = AP.parseRunways(closed, null);
assert.strictEqual(rc.KXXX.length, 1, 'closed: left out');
assert.strictEqual(rc.KXXX[0].paved, false, 'grass is not paved');

// merge: longest first; a field with no runway of 3,000 ft or more is dropped; paved length
const all = AP.merge(ap, rw);
assert.ok(all.length === 8);
assert.deepStrictEqual(all.find((a) => a.ident === 'KEDW').rwys.map((r) => r.len_ft), [16798, 12000, 8000]);
assert.strictEqual(all.find((a) => a.ident === 'KSBA').rwy_ft, 6037);
assert.strictEqual(AP.merge(ap, rw, 7000).some((a) => a.ident === 'KSBA'), false, 'a stricter minimum drops it');
assert.strictEqual(AP.merge(ap, rw, 7000).some((a) => a.ident === 'KEDW'), true);

// the test of a runway: the forecast's runway to have, plus the allowance
{
  const full = AP.need(forecast, 25600, 2300);
  assert.strictEqual(full.known, true);
  const L = forecast.landing(25600, 2300);
  assert.strictEqual(full.need_ft, Math.round(L.runway_ft + 800), 'the forecast plus 800 ft of aiming allowance');
  const light = AP.need(forecast, 16000, 2300);
  assert.ok(light.need_ft < full.need_ft - 1500, 'fewer fuel, less runway: ' + light.need_ft + ' against ' + full.need_ft);
  assert.strictEqual(AP.need({ landing: () => null }, 25600, 0).known, false, 'no table: the fallback, and it says so');
  assert.strictEqual(AP.need({ landing: () => null }, 25600, 0).need_ft, AP.FALLBACK_NEED_FT);
  assert.strictEqual(AP.need(null, 25600, 0).known, false);
  // which fields pass at 25,600 lb and at 16,000
  const byId = (id) => all.find((a) => a.ident === id);
  const cls = (id, w) => AP.usable(byId(id), AP.need(forecast, w, byId(id).elev_ft).need_ft, AP.need(forecast, 16000, byId(id).elev_ft).need_ft);
  assert.strictEqual(cls('KEDW', 25600), 'now');
  assert.strictEqual(cls('KVCV', 25600), 'now');
  assert.strictEqual(cls('KSBA', 25600), 'lighter', 'a 6,037 ft runway: not at full weight, yes at the reserve weight');
  assert.strictEqual(cls('KSBA', 16000), 'now');
  // a field whose only long runway is not paved does not count
  const grass = Object.assign({}, byId('KEDW'), { paved_ft: 0 });
  assert.strictEqual(AP.usable(grass, 5000, 4000), 'no');
}

// near and in a box
{
  const n = AP.nearest(all, 34.9, -117.88, 3);
  assert.deepStrictEqual(n.map((x) => x.a.ident)[0], 'KEDW');
  assert.ok(n[0].nm < 3 && n[1].nm >= n[0].nm);
  assert.strictEqual(AP.nearest(all, 34.9, -117.88, 3, (a) => a.ident !== 'KEDW')[0].a.ident === 'KEDW', false);
  const box = AP.inBox(all, [34, -119, 36, -117], 3);
  assert.strictEqual(box.length, 3);
  assert.ok(box[0].rwy_ft >= box[1].rwy_ft && box[1].rwy_ft >= box[2].rwy_ft, 'the longest runways first');
}

// crosswind
assert.ok(Math.abs(AP.crosswind(90, 20, 0) - 20) < 1e-9);
assert.ok(Math.abs(AP.crosswind(30, 20, 30)) < 1e-9);
assert.ok(Math.abs(AP.crosswind(270, 10, 240) - 5) < 1e-9);
assert.strictEqual(AP.crosswind(NaN, 10, 0), null);

(async () => {
  // the keeper: loads and keeps, covers, retries after a failure
  const store = new Store('t', null);
  let calls = 0;
  let fail = false;
  const fetchFn = async (u) => {
    calls++;
    if (fail) throw new Error('offline');
    return { ok: true, status: 200, text: async () => (u.endsWith('airports.csv') ? fx('ourairports-airports.csv') : fx('ourairports-runways.csv')) };
  };
  let t = 0;
  const A = new AP.Airports({ fetch: fetchFn, store, now: () => t });
  await A.ensure([34.9, -117.88], 100);
  assert.deepStrictEqual(A.list.map((a) => a.ident).sort(), ['KBFL', 'KEDW', 'KLAX', 'KMHV', 'KPMD', 'KVCV', 'KWJF'], 'within 100 nmi: Santa Barbara is further');
  assert.ok(/within 100 nmi/.test(A.status));
  assert.strictEqual(calls, 2, 'two files');
  assert.strictEqual(A.covers([34.9, -117.88]), true);
  assert.strictEqual(A.covers([34.9, -115]), false, 'more than 60 % of the radius away');
  await A.ensure([34.95, -117.85], 100);
  assert.strictEqual(calls, 2, 'covered: not asked again');
  // a new keeper restores from the store
  const B = new AP.Airports({ fetch: async () => { throw new Error('should not be asked'); }, store });
  await B.restore();
  assert.strictEqual(B.list.length, 7);
  assert.ok(/kept in this browser/.test(B.status));
  // failure: it says so, keeps what it has, and waits 60 s
  fail = true;
  await A.ensure([34.9, -115], 100);
  assert.ok(/could not load airports: offline.*kept ones are shown/.test(A.status), A.status);
  const before = calls;
  await A.ensure([34.9, -115], 100);
  assert.strictEqual(calls, before, 'not asked again within 60 s');
  t = 61000;
  await A.ensure([34.9, -115], 100);
  assert.ok(calls > before, 'asked again after 60 s');
  // a file the user loads
  const U = new AP.Airports({ fetch: fetchFn });
  assert.strictEqual(U.addFile(fx('ourairports-airports.csv'), fx('ourairports-runways.csv')), 8);
  assert.strictEqual(U.list.length, 8);
  assert.strictEqual(U.addFile(fx('ourairports-airports.csv'), fx('ourairports-runways.csv')), 8);
  assert.strictEqual(U.list.length, 8, 'twice is not twice');
  // the store itself: memory and a broken IndexedDB
  const s = new Store('x', null);
  assert.strictEqual(await s.get('k'), undefined);
  await s.set('k', { a: 1 });
  assert.deepStrictEqual(await s.get('k'), { a: 1 });
  await s.del('k');
  assert.strictEqual(await s.get('k'), undefined);
  const broken = new Store('y', { open: () => { throw new Error('no idb'); } });
  await broken.set('k', 5);
  assert.strictEqual(await broken.get('k'), 5, 'a store that cannot persist still remembers while the page lives');
  console.log('airports: ok');
})().catch((e) => { console.error(e); process.exit(1); });
