// node tests/weather.test.js
// L7 of the map-layers plan (docs/PLAN.md): the parsers on answers saved from the real services on 2026-11-14, the choices of level and
// satellite, the winds, the hazards against a path by NASA's rules, and the feeds with a fake network.
const assert = require('assert');
const fs = require('fs');
const W = require('../js/weather.js');
const A = require('../js/airspace.js');
const geo = require('../js/geo.js');
const fx = (n) => JSON.parse(fs.readFileSync(__dirname + '/fixtures/' + n, 'utf8'));

// radar
{
  const r = W.parseRain(fx('rainviewer.json'));
  assert.strictEqual(r.host, 'https://tilecache.rainviewer.com');
  assert.ok(r.frames.length >= 6, 'past frames: ' + r.frames.length);
  assert.ok(r.newest.path.startsWith('/v2/radar/'));
  assert.strictEqual(W.rainUrl(r.host, r.newest, 5, 5, 12), `https://tilecache.rainviewer.com${r.newest.path}/256/5/5/12/2/1_1.png`);
  assert.deepStrictEqual(W.parseRain({}).frames, []);
  assert.strictEqual(W.ageMin({ time: 1000 }, 1000 * 1000 + 600000), 10);
}

// satellite: which one looks at a longitude, and the address
assert.strictEqual(W.satFor(-118).id, 'goes-west');
assert.strictEqual(W.satFor(-75).id, 'goes-east');
assert.strictEqual(W.satFor(10).id, 'meteosat');
assert.strictEqual(W.satFor(140).id, 'himawari');
assert.strictEqual(W.satFor(-170).id, 'himawari');
assert.strictEqual(W.satFor(190).id, 'himawari', 'longitudes past 180 wrap');
assert.strictEqual(W.satUrl(W.satFor(-118), 3, 5, 2), 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/GOES-West_ABI_Band13_Clean_Infrared/default/default/GoogleMapsCompatible_Level6/3/2/5.png');
assert.ok(/view\.eumetsat\.int.*layers=msg_fes%3Air108.*bbox=1,2,3,4/.test(W.satUrl(W.satFor(10), 3, 5, 2, '1,2,3,4')));

// the pressure level for a height
assert.ok(Math.abs(W.pressureHpa(0) - 1013.25) < 1e-6);
assert.ok(Math.abs(W.pressureHpa(18000) - 506) < 3);
assert.ok(Math.abs(W.pressureHpa(30000) - 301) < 3);
assert.ok(Math.abs(W.pressureHpa(36089) - 226.3) < 0.5, 'the tropopause, and the two formulas meet');
assert.ok(Math.abs(W.pressureHpa(60000) - 72) < 3);
assert.ok(Math.abs(W.pressureHpa(65000) - 56.4) < 2);
for (const [ft, hpa] of [[0, 1000], [10000, 700], [20000, 500], [30000, 300], [40000, 200], [45000, 150], [50000, 100], [60000, 70], [65000, 50]]) assert.strictEqual(W.levelFor(ft), hpa, `${ft} ft`);

// wind against a course
{
  const near = (a, b) => Math.abs(a - b) < 1e-9;
  let c = W.components(90, 270, 60);
  assert.ok(near(c.tail_kt, 60) && near(c.cross_kt, 0), 'from the west, flying east: tail');
  c = W.components(270, 270, 60);
  assert.ok(near(c.tail_kt, -60), 'from the west, flying west: head');
  c = W.components(0, 270, 60);
  assert.ok(near(c.tail_kt, 0) && near(c.cross_kt, -60), 'from the west, flying north: from the left');
  c = W.components(0, 90, 60);
  assert.ok(near(c.cross_kt, 60), 'from the east, flying north: from the right');
  c = W.components(45, 225, 40);
  assert.ok(near(c.tail_kt, 0 + 40 * Math.cos(0)), 'dir 225 course 45: the wind blows toward 45');
}

// winds aloft: Open-Meteo's own answer, saved
{
  const j = fx('open-meteo-winds.json');
  const w = W.parseWinds(j, 70);
  assert.strictEqual(w.length, 2);
  assert.strictEqual(w[0].times.length, 6);
  assert.ok(w[0].spd.every(Number.isFinite) && w[0].dir.every(Number.isFinite));
  const url = W.windUrl([{ lat: 34.5, lon: -118.5 }, { lat: 35.5, lon: -117.5 }], 70);
  assert.ok(/latitude=34.5,35.5&longitude=-118.5,-117.5&hourly=wind_speed_70hPa,wind_direction_70hPa&forecast_days=2&wind_speed_unit=kn/.test(url), url);
  assert.strictEqual(W.parseWinds(j[0], 200).length, 1, 'one object, not an array, is also fine');
}

// the field: fetches a lattice in groups, interpolates, keeps, backs off
(async () => {
  let t = Date.UTC(2026, 10, 14, 6, 0, 0);
  const times = [0, 1, 2, 3, 4, 5, 6, 7].map((h) => new Date(Date.UTC(2026, 10, 14, 6 + h, 0, 0)).toISOString().slice(0, 16));
  const asked = [];
  let mode = 'west';
  const fetchFn = async (u) => {
    asked.push(u);
    const lat = u.match(/latitude=([^&]*)/)[1].split(',').map(Number);
    const lon = u.match(/longitude=([^&]*)/)[1].split(',').map(Number);
    const lvl = u.match(/wind_speed_(\d+)hPa/)[1];
    if (mode === '429') return { ok: false, status: 429, json: async () => ({}) };
    if (mode === 'down') throw new Error('offline');
    const arr = lat.map((la, i) => ({ latitude: la, longitude: lon[i], hourly: { time: times, [`wind_speed_${lvl}hPa`]: times.map((_, h) => 40 + h), [`wind_direction_${lvl}hPa`]: times.map(() => 270) } }));
    return { ok: true, status: 200, json: async () => (arr.length === 1 ? arr[0] : arr) };
  };
  const F = new W.WindField({ fetch: fetchFn, now: () => t });
  const box = [33, -120, 37, -116];
  await F.ensure(box, 70);
  assert.ok(asked.length === 1 && asked[0].includes('wind_speed_70hPa'));
  assert.ok(asked[0].split('latitude=')[1].split('&')[0].split(',').length <= 30, 'at most 30 places a request');
  assert.ok(/places added/.test(F.status));
  // steady west wind, 40 kt in the first hour and 41 the next
  let w = F.at(35.1, -118.2, 60000, 0);
  assert.ok(w && Math.abs(w.spd - 40) < 1e-6 && Math.abs(w.dir - 270) < 1e-6, JSON.stringify(w));
  assert.strictEqual(w.level, 70);
  w = F.at(35.1, -118.2, 60000, 3);
  assert.ok(Math.abs(w.spd - 43) < 1e-6, 'three hours on');
  // six seconds between requests
  await F.ensure(box, 70);
  assert.strictEqual(asked.length, 1, 'not again before 6 s');
  t += 6001;
  await F.ensure(box, 70);
  const n2 = asked.length;
  t += 6001;
  await F.ensure(box, 70);
  assert.ok(asked.length <= n2 + 1);
  // arrows on the lattice
  const arrows = F.arrows(box, 60000, 0);
  assert.ok(arrows.length > 5 && arrows.every((a) => Math.abs(a.dir - 270) < 1e-6));
  // between two cells with different winds the vectors average: 40 kt from the west and 40 kt from the east make calm halfway
  const G = new W.WindField({ fetch: async () => { throw new Error('unused'); }, now: () => t });
  G.step = 1;
  G.cells.set('70/1/35/-118', { t, times, spd: times.map(() => 40), dir: times.map(() => 270) });
  G.cells.set('70/1/35/-117', { t, times, spd: times.map(() => 40), dir: times.map(() => 90) });
  G.cells.set('70/1/36/-118', { t, times, spd: times.map(() => 40), dir: times.map(() => 270) });
  G.cells.set('70/1/36/-117', { t, times, spd: times.map(() => 40), dir: times.map(() => 90) });
  assert.ok(G.at(35.5, -117.5, 60000, 0).spd < 1e-6, 'calm halfway');
  assert.ok(Math.abs(G.at(35.5, -117.75, 60000, 0).spd - 20) < 1e-6, 'a quarter of the way: 20 kt');
  assert.strictEqual(G.at(10, 10, 60000, 0), null, 'no cells there');
  // failures: 429 pauses five minutes, a network error one
  const H = new W.WindField({ fetch: fetchFn, now: () => t });
  mode = '429';
  await H.ensure(box, 70);
  assert.ok(/too many requests: pausing 5 min/.test(H.status));
  const before = asked.length;
  t += 120000;
  await H.ensure(box, 70);
  assert.strictEqual(asked.length, before, 'paused');
  t += 200000;
  mode = 'down';
  await H.ensure(box, 70);
  assert.ok(/winds failed: offline; trying again in 1 min/.test(H.status));
  mode = 'west';

  // the planner's prefetch: all levels in each request
  {
    const urls2 = [];
    const f2 = async (u) => {
      urls2.push(u);
      const lat = u.match(/latitude=([^&]*)/)[1].split(',').map(Number);
      const lon = u.match(/longitude=([^&]*)/)[1].split(',').map(Number);
      const hourly = { time: times };
      for (const l of [100, 70]) { hourly[`wind_speed_${l}hPa`] = times.map(() => 30 + l / 10); hourly[`wind_direction_${l}hPa`] = times.map(() => 250); }
      const arr = lat.map((la, i) => ({ latitude: la, longitude: lon[i], hourly }));
      return { ok: true, status: 200, json: async () => (arr.length === 1 ? arr[0] : arr) };
    };
    const P2 = new W.WindField({ fetch: f2, now: () => t });
    const r2 = await P2.prefetch([33, -120, 37, -116], [100, 70]);
    assert.ok(r2.ok && r2.places > 5, JSON.stringify(r2));
    assert.ok(urls2.every((u) => /wind_speed_100hPa,wind_direction_100hPa,wind_speed_70hPa,wind_direction_70hPa/.test(u)), 'both levels in every request');
    assert.ok(urls2.every((u) => u.match(/latitude=([^&]*)/)[1].split(',').length <= 30));
    assert.ok(Math.abs(P2.at(35.1, -118.2, 60000, 0).spd - 37) < 1e-6, '70 hPa for 60,000 ft');
    assert.ok(Math.abs(P2.at(35.1, -118.2, 53000, 0).spd - 40) < 1e-6, '100 hPa for 53,000 ft');
    const n3 = urls2.length;
    await P2.prefetch([33, -120, 37, -116], [100, 70]);
    assert.strictEqual(urls2.length, n3, 'fresh: not asked again');
    const bad = new W.WindField({ fetch: async () => ({ ok: false, status: 429, json: async () => ({}) }), now: () => t });
    const rb = await bad.prefetch([33, -120, 37, -116], [100]);
    assert.ok(!rb.ok && /too many requests/.test(rb.status));
  }

  // wind on the legs of a path
  const path = [{ lat: 35, lon: -119, alt_ft: 60000 }, { lat: 35, lon: -117, alt_ft: 60000 }, { lat: 35, lon: -119, alt_ft: 60000 }];
  const legs = W.legWinds(path, () => ({ spd: 50, dir: 270 }));
  assert.strictEqual(legs.length, 2);
  assert.ok(Math.abs(legs[0].tail_kt - 50) < 0.5 && Math.abs(legs[1].tail_kt + 50) < 0.5, 'out with the wind, back against it');
  assert.strictEqual(W.legWinds(path, () => null).length, 0);

  // the hazards, as the service gives them
  const as = W.parseAirSigmet(fx('awc-airsigmet.json'));
  assert.strictEqual(as.length, 2);
  const turb = as.find((h) => h.kind === 'turb');
  assert.strictEqual(turb.lo_ft, 18000);
  assert.strictEqual(turb.hi_ft, 33000);
  assert.strictEqual(turb.source, 'SIGMET');
  assert.ok(turb.to > turb.from && turb.rings[0].length >= 4);
  const conv = as.find((h) => h.kind === 'convective');
  assert.strictEqual(conv.lo_ft, 0, 'a convective SIGMET gives tops only: from the ground up');
  assert.strictEqual(conv.hi_ft, 41000);
  const ga = W.parseGairmet(fx('awc-gairmet.json'));
  assert.ok(ga.length >= 4 && ga.every((h) => h.rings.length), 'polygons only: the freezing-level line is skipped');
  const tlo = ga.find((h) => h.hazard === 'TURB-LO');
  assert.strictEqual(tlo.lo_ft, 0);
  assert.strictEqual(tlo.hi_ft, 12000);
  assert.strictEqual(tlo.kind, 'turb');
  assert.strictEqual(ga.find((h) => h.hazard === 'IFR').kind, 'vis');
  assert.strictEqual(W.hazardRelevant(turb, 25000), true);
  assert.strictEqual(W.hazardRelevant(turb, 60000), false, 'FL600 is above FL330');
  assert.strictEqual(W.hazardRelevant(turb, 17500), false);
  assert.strictEqual(W.hazardRelevant(turb, 17500, 600), true);
  assert.strictEqual(W.hazardRelevant(ga.find((h) => h.hazard === 'IFR'), 5000), false, 'a visibility area is not a flight hazard here');

  // NASA's rules against a path. A 4 degree square, 31 to 35 N, 119 to 115 W, at each rule's heights.
  const sq = [[35, -119], [35, -115], [31, -115], [31, -119]];
  const H0 = { source: 'SIGMET', id: 'SIGMET TEST', hazard: 'TURB', severity: 5, from: t - 3600000, to: t + 3600000, rings: [sq] };
  const flyN = (alt, lonCentre) => [{ lat: 30, lon: lonCentre || -117, alt_ft: alt }, { lat: 38, lon: lonCentre || -117, alt_ft: alt }];
  const adv = (h, p) => W.hazardAdvisories([h], p, { now: t, gs_kt: 300 });
  // rule 5: turbulence, only at its heights
  assert.strictEqual(adv(Object.assign({ kind: 'turb', lo_ft: 18000, hi_ft: 33000 }, H0), flyN(25000)).length, 1);
  assert.strictEqual(adv(Object.assign({ kind: 'turb', lo_ft: 18000, hi_ft: 33000 }, H0), flyN(60000)).length, 0, 'above it: nothing');
  const a1 = adv(Object.assign({ kind: 'turb', lo_ft: 18000, hi_ft: 33000 }, H0), flyN(25000))[0];
  assert.strictEqual(a1.level, 'caution');
  assert.strictEqual(a1.where, 'ahead');
  assert.ok(/WEATHER: SIGMET TEST turbulence \(severity 5\), FL180 to FL330, valid until \d\d:\d\dZ: entered \d+ nmi ahead/.test(a1.text), a1.text);
  assert.ok(/NASA 2012 rule: no flight into forecast or reported moderate or severe turbulence/.test(a1.action));
  assert.ok(/compares the path with the area, not with the weather itself/.test(a1.action));
  // rule 4: icing
  assert.strictEqual(adv(Object.assign({ kind: 'ice', lo_ft: 0, hi_ft: 25000 }, H0), flyN(20000))[0].kind, 'ice');
  // expired: nothing
  assert.strictEqual(adv(Object.assign({ kind: 'turb', lo_ft: 0, hi_ft: 99999 }, H0, { to: t - 1 }), flyN(25000)).length, 0);
  // rule 1: at or below FL500, 25 nmi from convection, whatever the height of the tops
  const conv1 = Object.assign({ kind: 'convective', lo_ft: 0, hi_ft: 41000, hazard: 'CONVECTIVE' }, H0);
  const off = (nm) => flyN(45000, -115 + nm / 60 / Math.cos((33 * Math.PI) / 180));
  assert.strictEqual(adv(conv1, off(20))[0].where, 'near', '20 nmi off the edge at FL450: inside the 25');
  assert.ok(/comes within 20 nmi/.test(adv(conv1, off(20))[0].text) || /within 2\d nmi/.test(adv(conv1, off(20))[0].text), adv(conv1, off(20))[0].text);
  assert.strictEqual(adv(conv1, off(30)).length, 0, '30 nmi off: clear');
  assert.strictEqual(adv(conv1, flyN(45000))[0].where, 'ahead', 'through it');
  assert.ok(/25 nmi from thunderstorms/.test(adv(conv1, off(20))[0].action));
  // rule 2b: above FL500 with tops below it, 10,000 ft over the tops
  const aboveLow = (alt) => adv(conv1, flyN(alt));
  assert.strictEqual(aboveLow(54000).length, 0, '41,000 + 10,000 = 51,000: 54,000 clears it, and the 25 nmi rule is for FL500 and below');
  assert.strictEqual(aboveLow(50500).length, 1, '50,500 is above FL500 and under 51,000');
  // rule 2a: tops at FL520: 25 nmi whatever the height, even far above them
  const conv2 = Object.assign({}, conv1, { hi_ft: 52000 });
  assert.strictEqual(adv(conv2, flyN(60000))[0].where, 'ahead');
  assert.strictEqual(adv(conv2, flyN(60000, -115 + 20 / 60 / Math.cos((33 * Math.PI) / 180)))[0].where, 'near', '20 nmi off, at FL600, tops at FL520');
  // only flight hazards are advised
  assert.strictEqual(adv(Object.assign({ kind: 'vis', lo_ft: 0, hi_ft: 99999 }, H0), flyN(25000)).length, 0);
  // the worst first: inside before ahead
  const two = W.hazardAdvisories([Object.assign({ kind: 'turb', lo_ft: 0, hi_ft: 99999 }, H0, { id: 'FAR', rings: [[[38, -119], [38, -115], [34.5, -115], [34.5, -119]]] }), Object.assign({ kind: 'ice', lo_ft: 0, hi_ft: 99999 }, H0, { id: 'HERE' })], [{ lat: 33, lon: -117, alt_ft: 30000 }, { lat: 39, lon: -117, alt_ft: 30000 }], { now: t, gs_kt: 300 });
  assert.deepStrictEqual(two.map((x) => x.where), ['inside', 'ahead']);

  // observations: NWS's own answer, saved (km/h and metres), and aviationweather.gov's
  const nws = W.parseNws(fx('nws-observation.json'), 'KEDW');
  assert.strictEqual(nws.wdir, 220);
  assert.strictEqual(nws.wspd, 9, '16.56 km/h is 9 kt');
  assert.ok(Math.abs(nws.vis_sm - 50) < 0.1);
  assert.strictEqual(nws.ceiling_ft, null, 'scattered only: no ceiling');
  assert.strictEqual(nws.cat, 'VFR');
  assert.ok(/^KEDW /.test(nws.raw));
  assert.strictEqual(W.parseNws({}, 'X'), null);
  const mt = W.parseAwcMetar(fx('awc-metar.json'));
  assert.deepStrictEqual(mt.map((m) => m.id), ['KEDW', 'KLAX']);
  assert.strictEqual(mt[0].wdir, 220);
  assert.strictEqual(mt[0].wgst, 14);
  assert.strictEqual(mt[0].ceiling_ft, 28000, 'the broken layer at 28,000 is the ceiling');
  assert.strictEqual(mt[0].cat, 'VFR');
  assert.ok(Math.abs(mt[0].lat - 34.9) < 0.1);
  assert.deepStrictEqual(W.parseAwcMetar({}), []);
  // flight category at its edges
  const fc = W.flightCategory;
  assert.deepStrictEqual([fc(10, 5000), fc(4, 2500), fc(2, 5000), fc(0.5, 5000), fc(10, 400), fc(10, 900), fc(10, 3000), fc(6, 3001), fc(5, null), fc(3, null), fc(2.9, null), fc(1, 1000), fc(0.9, null), fc(10, 500), fc(10, 499)], ['VFR', 'MVFR', 'IFR', 'LIFR', 'LIFR', 'IFR', 'MVFR', 'VFR', 'MVFR', 'MVFR', 'IFR', 'IFR', 'LIFR', 'IFR', 'LIFR']);

  // the hazards feed: no helper, no request; with it, merged and kept five minutes; failures say so
  const urls = [];
  const feed = (ok) => async (u) => { urls.push(u); if (ok === 'throw') throw new Error('refused'); return { ok: true, status: 200, json: async () => (u.includes('airsigmet') ? fx('awc-airsigmet.json') : fx('awc-gairmet.json')) }; };
  const none = new W.Hazards({ fetch: feed(true), awc: null, now: () => t });
  await none.ensure();
  assert.strictEqual(urls.length, 0);
  assert.ok(/needs the helper.*awc-proxy.*\?awc=/.test(none.status), none.status);
  const hz = new W.Hazards({ fetch: feed(true), awc: 'http://localhost:5402/', now: () => t });
  await hz.ensure();
  assert.deepStrictEqual(urls, ['http://localhost:5402/api/data/airsigmet?format=geojson', 'http://localhost:5402/api/data/gairmet?format=geojson']);
  assert.ok(hz.list.length >= 6);
  assert.ok(/areas \(SIGMET and G-AIRMET.*read \d\d:\d\dZ/.test(hz.status), hz.status);
  await hz.ensure();
  assert.strictEqual(urls.length, 2, 'five minutes of life');
  t += 301000;
  await hz.ensure();
  assert.strictEqual(urls.length, 4);
  const bad = new W.Hazards({ fetch: feed('throw'), awc: 'http://localhost:5402', now: () => t });
  await bad.ensure();
  assert.ok(/hazards failed: refused/.test(bad.status));
  assert.strictEqual(W.awcUrl(null, 'metar', 'a=b'), null);

  // the observations feed: NWS for US stations, the helper for the rest, ten minutes' life
  const seen = [];
  const mf = async (u) => {
    seen.push(u);
    if (u.startsWith('https://api.weather.gov/')) return { ok: true, status: 200, json: async () => fx('nws-observation.json') };
    return { ok: true, status: 200, json: async () => fx('awc-metar.json') };
  };
  const M = new W.Metars({ fetch: mf, awc: null, now: () => t });
  await M.ensure(['KEDW', 'EDDF']);
  assert.deepStrictEqual(seen, ['https://api.weather.gov/stations/KEDW/observations/latest']);
  assert.strictEqual(M.get('KEDW').wspd, 9);
  assert.strictEqual(M.get('EDDF'), null);
  assert.ok(/outside the US need the helper/.test(M.status));
  await M.ensure(['KEDW']);
  assert.strictEqual(seen.length, 1, 'ten minutes of life');
  const M2 = new W.Metars({ fetch: mf, awc: 'http://localhost:5402', now: () => t });
  await M2.ensure(['KEDW', 'KLAX', 'EDDF']);
  assert.ok(seen.some((u) => u === 'http://localhost:5402/api/data/metar?ids=EDDF&format=json'), seen.join(' '));
  console.log('weather: ok');
}
)().catch((e) => { console.error(e); process.exit(1); });
