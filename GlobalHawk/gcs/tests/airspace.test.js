// node tests/airspace.test.js
// L5 of the map-layers plan (docs/PLAN.md): parsing, geometry, heights, paths, advisories, the FAA loader.
const assert = require('assert');
const fs = require('fs');
const A = require('../js/airspace.js');
const geo = require('../js/geo.js');

// heights
assert.deepStrictEqual(A.parseAlt('FL195'), { ft: 19500, ref: 'FL' });
assert.deepStrictEqual(A.parseAlt('FL 245'), { ft: 24500, ref: 'FL' });
assert.deepStrictEqual(A.parseAlt('5000ft AGL'), { ft: 5000, ref: 'AGL' });
assert.deepStrictEqual(A.parseAlt('SFC'), { ft: 0, ref: 'AGL' });
assert.deepStrictEqual(A.parseAlt('GND'), { ft: 0, ref: 'AGL' });
assert.deepStrictEqual(A.parseAlt('UNL'), { ft: 99999, ref: 'MSL' });
assert.deepStrictEqual(A.parseAlt('3000 AMSL'), { ft: 3000, ref: 'MSL' });
assert.deepStrictEqual(A.parseAlt('1500 m'), { ft: 4921, ref: 'MSL' });
assert.strictEqual(A.fmtLimit({ ft: 18000, ref: 'FL' }), 'FL180');
assert.strictEqual(A.fmtLimit({ ft: 99999, ref: 'MSL' }), 'unlimited');
assert.strictEqual(A.fmtLimit({ ft: 4800, ref: 'MSL' }), '4,800 ft MSL');

// one made-up zone, written three ways, comes out as the same record
const OPENAIR = `* a made-up restricted area, for tests
AC R
AN R-9901 DEMO NORTH
AL SFC
AH FL600
DP 35:00:00 N 118:00:00 W
DP 35:00:00 N 117:00:00 W
DP 34:00:00 N 117:00:00 W
DP 34:00:00 N 118:00:00 W
`;
const ring = [[35, -118], [35, -117], [34, -117], [34, -118]];
const FAA = { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { NAME: 'R-9901 DEMO NORTH', TYPE_CODE: 'R', CLASS: null, LOWER_VAL: '0', LOWER_UOM: 'FT', LOWER_CODE: 'SFC', UPPER_VAL: '600', UPPER_UOM: 'FL', UPPER_CODE: 'STD', TIMESOFUSE: 'BY NOTAM' }, geometry: { type: 'Polygon', coordinates: [ring.map((p) => [p[1], p[0]])] } }] };
const OAIP = { items: [{ name: 'R-9901 DEMO NORTH', type: 1, icaoClass: 8, lowerLimit: { value: 0, unit: 1, referenceDatum: 0 }, upperLimit: { value: 600, unit: 6, referenceDatum: 2 }, geometry: { type: 'Polygon', coordinates: [ring.map((p) => [p[1], p[0]])] } }] };
const a = A.parseOpenAir(OPENAIR)[0];
const b = A.parseGeoJSON(FAA)[0];
const c = A.parseGeoJSON(OAIP)[0];
for (const [label, z] of [['OpenAir', a], ['FAA', b], ['OpenAIP', c]]) {
  assert.strictEqual(z.name, 'R-9901 DEMO NORTH', label);
  assert.strictEqual(z.kind, 'restricted', label);
  assert.deepStrictEqual(z.lower, { ft: 0, ref: 'AGL' }, label);
  assert.deepStrictEqual(z.upper, { ft: 60000, ref: 'FL' }, label);
  assert.deepStrictEqual(z.bbox.map((v) => Math.round(v)), [34, -118, 35, -117], label);
  assert.strictEqual(z.rings[0].length, 4, label);
}
assert.strictEqual(b.times, 'BY NOTAM');
assert.strictEqual(A.parse(OPENAIR)[0].name, 'R-9901 DEMO NORTH');
assert.strictEqual(A.parse(JSON.stringify(FAA))[0].kind, 'restricted');
assert.deepStrictEqual(A.parse('{ not json'), []);

// OpenAir: circles, arcs, the class letters, names that say MOA and WARNING
const OA2 = `AC D
AN TEST CTR
AL SFC
AH 2500 AMSL
V X=36:00:00 N 119:00:00 W
DC 5
AC W
AN W-9902 WARNING AREA
AL SFC
AH UNL
V X=36:30:00 N 119:00:00 W
V D=-
DP 36:30:00 N 119:10:00 W
DB 36:30:00 N 119:10:00 W, 36:40:00 N 119:00:00 W
DP 36:20:00 N 118:50:00 W
AC C
AN SOMEWHERE MOA
AL 5000 AGL
AH 17999 AMSL
V X=37:00:00 N 119:00:00 W
DA 10, 0, 90
DP 37:00:00 N 119:00:00 W
`;
const z2 = A.parseOpenAir(OA2);
assert.strictEqual(z2.length, 3);
assert.strictEqual(z2[0].kind, 'classD');
assert.strictEqual(Math.round(z2[0].circle.r_ft / geo.NM), 5);
assert.strictEqual(z2[1].kind, 'warning');
assert.ok(z2[1].rings[0].length > 5, 'an arc becomes points');
assert.strictEqual(z2[2].kind, 'moa');
assert.deepStrictEqual(z2[2].lower, { ft: 5000, ref: 'AGL' });

// point in polygon: six cases, a concave zone and one with a hole
const sq = A.make({ rings: [[[0, 0], [0, 2], [2, 2], [2, 0]]] });
assert.strictEqual(A.contains(sq, 1, 1), true, 'inside');
assert.strictEqual(A.contains(sq, 3, 1), false, 'outside, north');
assert.strictEqual(A.contains(sq, 1, -0.5), false, 'outside, west');
const C = A.make({ rings: [[[0, 0], [0, 3], [1, 3], [1, 1], [2, 1], [2, 3], [3, 3], [3, 0]]] }); // a "U" opening to the east side
assert.strictEqual(A.contains(C, 0.5, 2), true, 'in the bottom arm of the U');
assert.strictEqual(A.contains(C, 1.5, 2), false, 'in the notch of the U');
assert.strictEqual(A.contains(C, 2.5, 2), true, 'in the top arm of the U');
const H = A.make({ rings: [[[0, 0], [0, 4], [4, 4], [4, 0]]], holes: [[[1, 1], [1, 3], [3, 3], [3, 1]]] });
assert.strictEqual(A.contains(H, 0.5, 0.5), true, 'in the ring around a hole');
assert.strictEqual(A.contains(H, 2, 2), false, 'in the hole');
const circ = A.make({ circle: { lat: 35, lon: -118, r_ft: 10 * geo.NM } });
assert.strictEqual(A.contains(circ, 35.1, -118), true);
assert.strictEqual(A.contains(circ, 35.2, -118), false);

// the distance to the edge against the great circle (haversine) at 100 nmi, within 1 %
const hav = (p, q) => {
  const R = 3440.065; // nmi
  const r = Math.PI / 180;
  const h = Math.sin(((q[0] - p[0]) * r) / 2) ** 2 + Math.cos(p[0] * r) * Math.cos(q[0] * r) * Math.sin(((q[1] - p[1]) * r) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};
{
  const wall = A.make({ rings: [[[30, -120], [40, -120], [40, -119.9], [30, -119.9]]] });
  for (const lat of [10, 35, 60]) {
    const dLon = 100 / 60 / Math.cos((lat * Math.PI) / 180);
    const p = [lat, -119.9 + dLon];
    const truth = hav(p, [lat, -119.9]);
    const got = A.edge(wall.rings && A.make({ rings: [[[lat - 5, -120], [lat + 5, -120], [lat + 5, -119.9], [lat - 5, -119.9]]] }), p[0], p[1]);
    assert.ok(!got.inside);
    assert.ok(Math.abs(got.nm - truth) / truth < 0.01, `edge ${got.nm.toFixed(2)} against ${truth.toFixed(2)} nmi at ${lat} N`);
    assert.ok(Math.abs(truth - 100) < 3);
  }
  // and from inside: the distance to the nearest side
  const e = A.edge(sq, 1, 0.5);
  assert.strictEqual(e.inside, true);
  assert.ok(Math.abs(e.nm - 0.5 * 60 * Math.cos((1 * Math.PI) / 180)) < 0.3, 'inside, 0.5 deg from the west side');
  assert.ok(Math.abs(A.edge(circ, 35, -118 + 20 / 60 / Math.cos((35 * Math.PI) / 180)).nm - 10) < 0.2, 'a circle: 20 nmi out, 10 from the edge');
}

// heights: at the edges of a band
{
  const z = A.make({ lower: { ft: 18000, ref: 'FL' }, upper: { ft: 60000, ref: 'FL' }, rings: [[[0, 0], [0, 1], [1, 1]]] });
  assert.strictEqual(A.relevantAt(z, 17000), true, '17,000 with 1,000 of margin reaches 18,000');
  assert.strictEqual(A.relevantAt(z, 16999), false);
  assert.strictEqual(A.relevantAt(z, 61000), true);
  assert.strictEqual(A.relevantAt(z, 61001), false);
  assert.strictEqual(A.relevantAt(z, 16000, 2000), true, 'a wider margin');
  assert.strictEqual(A.bandMeets(z, 60000, 70000), true);
  assert.strictEqual(A.bandMeets(z, 60001, 70000), false);
}

// paths: a crossing, a pass 12 nmi off, one that is inside to begin with
{
  const R = A.make({ name: 'R-9903 TEST', kind: 'restricted', lower: { ft: 18000, ref: 'FL' }, upper: { ft: 99999, ref: 'MSL' }, circle: { lat: 35, lon: -118, r_ft: 10 * geo.NM } });
  const from = geo.along([35, -118], 180, 70 * geo.NM); // 70 nmi south of the centre
  const north = (alt) => [{ lat: from[0], lon: from[1], alt_ft: alt }, { lat: geo.along([35, -118], 0, 70 * geo.NM)[0], lon: -118, alt_ft: alt }];
  let adv = A.advisories([R], north(20000), { gs_kt: 300 });
  assert.strictEqual(adv.length, 1);
  assert.strictEqual(adv[0].where, 'ahead');
  assert.ok(Math.abs(adv[0].enter_nm - 60) < 2.1, 'enters 60 nmi along, within the 2 nmi step: ' + adv[0].enter_nm);
  assert.strictEqual(adv[0].level, 'caution', 'a restricted area is a caution');
  assert.ok(adv[0].text.includes('R-9903 TEST') && adv[0].text.includes('restricted') && adv[0].text.includes('FL180 to unlimited'), adv[0].text);
  assert.ok(/in 12 min/.test(adv[0].text), 'at 300 kt, 60 nmi is 12 min: ' + adv[0].text);
  assert.ok(/times of use/.test(adv[0].action), 'it says the times were not read');
  // below the zone's floor by more than the margin: nothing
  assert.strictEqual(A.advisories([R], north(15000), { gs_kt: 300 }).length, 0, 'under the floor');
  // 9 nmi from the edge is "near" (the limit is 10), 12 from the edge is nothing
  const side = (off) => {
    const a0 = geo.along([35, -118], 90, off * geo.NM);
    return [{ lat: a0[0] - 0.5, lon: a0[1], alt_ft: 20000 }, { lat: a0[0] + 0.5, lon: a0[1], alt_ft: 20000 }];
  };
  assert.strictEqual(A.advisories([R], side(19), { gs_kt: 300 })[0].where, 'near', '19 nmi off the centre is 9 off the edge');
  assert.strictEqual(A.advisories([R], side(22), { gs_kt: 300 }).length, 0, '22 nmi off the centre is 12 off the edge');
  // inside at the start
  adv = A.advisories([R], [{ lat: 35, lon: -118, alt_ft: 20000 }, { lat: 36, lon: -118, alt_ft: 20000 }], { gs_kt: 300 });
  assert.strictEqual(adv[0].where, 'inside');
  // the plan crosses, but far along: marked as on the plan
  const far = [{ lat: from[0], lon: from[1], alt_ft: 20000 }, { lat: 33, lon: -118, alt_ft: 20000 }, { lat: 36, lon: -118, alt_ft: 20000 }];
  const long = A.advisories([R], [{ lat: 30, lon: -118, alt_ft: 20000 }, { lat: 36, lon: -118, alt_ft: 20000 }], { gs_kt: 300 });
  assert.strictEqual(long[0].where, 'plan', 'entered 300 nmi along: not "ahead"');
  assert.ok(far.length === 3);
  // a zone in several parts is one advisory; and the words change for a route
  const part1 = A.make({ name: 'R-9906 TEST', kind: 'restricted', lower: { ft: 18000, ref: 'FL' }, upper: { ft: 99999, ref: 'MSL' }, circle: { lat: 35, lon: -118, r_ft: 10 * geo.NM } });
  const part2 = A.make({ name: 'R-9906 TEST', kind: 'restricted', lower: { ft: 18000, ref: 'FL' }, upper: { ft: 99999, ref: 'MSL' }, circle: { lat: 35.05, lon: -118, r_ft: 10 * geo.NM } });
  adv = A.advisories([part1, part2], north(20000), { gs_kt: 300 });
  assert.strictEqual(adv.length, 1, 'two parts of R-9906 are one advisory');
  adv = A.advisories([R], north(20000), { gs_kt: 300, route: true });
  assert.ok(/entered \d+ nmi along the route/.test(adv[0].text) && !/in \d+ min/.test(adv[0].text), adv[0].text);
  adv = A.advisories([R], [{ lat: 35, lon: -118, alt_ft: 20000 }, { lat: 36, lon: -118, alt_ft: 20000 }], { gs_kt: 300, route: true });
  assert.ok(/the route starts inside it/.test(adv[0].text), adv[0].text);
  // a MOA is an advisory, a restricted area a caution, and the worst comes first
  const M = A.make({ name: 'SOME MOA', kind: 'moa', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 18000, ref: 'MSL' }, circle: { lat: 35, lon: -118, r_ft: 10 * geo.NM } });
  adv = A.advisories([M, R], north(18500), { gs_kt: 300 });
  assert.deepStrictEqual(adv.map((x) => x.kind), ['restricted', 'moa']);
  assert.strictEqual(adv[1].level, 'advisory');
  // Class A and E are never advised or drawn
  const CA = A.make({ name: 'CLASS A', kind: 'classA', lower: { ft: 18000, ref: 'MSL' }, upper: { ft: 60000, ref: 'FL' }, circle: { lat: 35, lon: -118, r_ft: 50 * geo.NM } });
  assert.strictEqual(A.advisories([CA], north(30000)).length, 0);
  assert.strictEqual(A.visible([CA, R, M], 30000).length, 1, 'only the restricted area is both drawn and at that height');
  assert.strictEqual(A.visible([CA, R, M], 30000, true).length, 2, 'all heights: the MOA too, but never Class A');
  // an AGL floor is marked as read as MSL
  const G = A.make({ name: 'LOW ONE', kind: 'moa', lower: { ft: 3000, ref: 'AGL' }, upper: { ft: 99999, ref: 'MSL' }, circle: { lat: 35, lon: -118, r_ft: 10 * geo.NM } });
  assert.ok(/AGL limit read as MSL/.test(A.describe(G)));
  assert.ok(!/AGL limit/.test(A.describe(R)), 'FL is not AGL');
}

// real answers from the FAA's service, saved 2026-11-14 (heights as strings, "SFC" meaning above the ground)
{
  const sua = A.parseGeoJSON(JSON.parse(fs.readFileSync(__dirname + '/fixtures/faa-sua.json', 'utf8')));
  assert.strictEqual(sua.length, 12);
  const bak = sua.find((z) => z.name === 'BAKERSFIELD MOA');
  assert.strictEqual(bak.kind, 'moa');
  assert.deepStrictEqual(bak.lower, { ft: 2000, ref: 'AGL' });
  assert.deepStrictEqual(bak.upper, { ft: 18000, ref: 'FL' });
  assert.ok(/INTERMITTENT/.test(bak.times));
  const isa = sua.filter((z) => z.name === 'ISABELLA MOA');
  assert.ok(isa.some((z) => z.upper.ref === 'MSL' && z.upper.ft === 18000 && z.lower.ft === 4800));
  const cls = A.parseGeoJSON(JSON.parse(fs.readFileSync(__dirname + '/fixtures/faa-class.json', 'utf8')));
  const edw = cls.find((z) => z.name === 'EDWARDS AFB CLASS D');
  assert.strictEqual(edw.kind, 'classD');
  assert.deepStrictEqual(edw.upper, { ft: 4800, ref: 'MSL' });
  assert.deepStrictEqual(edw.lower, { ft: 0, ref: 'AGL' });
  assert.ok(cls.some((z) => z.kind === 'other' && /MODE C/.test(z.name)), 'a Mode C veil is not a class');
  // a Class D is not relevant at 60,000 ft and is at 3,000
  assert.strictEqual(A.relevantAt(edw, 60000), false);
  assert.strictEqual(A.relevantAt(edw, 3000), true);
}

// the loader: a page, a second page, the quota, a network failure
(async () => {
  const sua = JSON.parse(fs.readFileSync(__dirname + '/fixtures/faa-sua.json', 'utf8'));
  const urls = [];
  const page1 = Object.assign({}, sua, { properties: { exceededTransferLimit: true } });
  const page2 = { type: 'FeatureCollection', features: sua.features.slice(0, 2) };
  const mk = (...answers) => async (u) => {
    urls.push(u);
    const a = answers.shift();
    if (a instanceof Error) throw a;
    return { ok: true, status: 200, json: async () => a };
  };
  let r = await A.loadFaa(mk(page1, page2), [34, -119, 35, -117], ['Special_Use_Airspace']);
  assert.strictEqual(r.zones.length, 14, 'two pages');
  assert.ok(/resultOffset=12/.test(urls[1]), 'the second page starts after the first: ' + urls[1]);
  assert.ok(/geometry=-119%2C34%2C-117%2C35/.test(urls[0]), 'lon,lat order for the envelope');
  assert.strictEqual(r.status, 'ok');
  assert.ok(r.zones.every((z) => z.src === 'FAA Special_Use_Airspace'));
  r = await A.loadFaa(mk({ error: { code: 429, message: '', details: ['API calls quota exceeded'] } }), [34, -119, 35, -117], ['Special_Use_Airspace']);
  assert.strictEqual(r.zones.length, 0);
  assert.strictEqual(r.retryMs, 60000);
  assert.ok(/busy.*60 s/.test(r.status), r.status);
  r = await A.loadFaa(mk(new Error('offline')), [34, -119, 35, -117], ['Special_Use_Airspace']);
  assert.ok(/failed: offline/.test(r.status));
  assert.strictEqual(r.retryMs, 60000);
  // a TFR layer's zones are TFRs whatever their fields say
  r = await A.loadFaa(mk(page2), [34, -119, 35, -117], ['National_Defense_Airspace_TFR_Areas']);
  assert.ok(r.zones.every((z) => z.kind === 'tfr'));
  console.log('airspace: ok');
})().catch((e) => { console.error(e); process.exit(1); });
