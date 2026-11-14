#!/usr/bin/env node
/**
 * Asks the real services the map's layers use, through the station's own modules, and says what came back. Not a test (it needs a
 * network and the services change); run it when a layer says its data failed:
 *
 *   node tools/overlay-probe.js            (add  --awc http://localhost:5402  to try the helper too)
 */
'use strict';
const W = require('../js/weather.js');
const A = require('../js/airspace.js');
const AP = require('../js/airports.js');
const R = require('../js/terrain.js');
const T = require('../js/tiles.js');

const awcArg = process.argv.indexOf('--awc') >= 0 ? process.argv[process.argv.indexOf('--awc') + 1] : null;
const box = [34.4, -118.4, 35.4, -117.4]; // the demo field's neighbourhood
const centre = [34.9, -117.88];
const out = [];
const check = async (name, fn) => {
  const t0 = Date.now();
  try {
    out.push(`ok    ${name}: ${await fn()} (${Date.now() - t0} ms)`);
  } catch (e) {
    out.push(`FAIL  ${name}: ${e.message}`);
  }
};
const f = (u) => fetch(u, { headers: { 'User-Agent': 'globalhawk-gcs-probe' } });
const png = async (u) => {
  const r = await f(u);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const b = Buffer.from(await r.arrayBuffer());
  const kind = b.slice(1, 4).toString() === 'PNG' ? 'PNG' : b[0] === 0xff && b[1] === 0xd8 ? 'JPEG' : null;
  if (!kind) throw new Error('not a picture');
  return `${kind}, ${b.length} bytes`;
};

(async () => {
  for (const id of ['dark', 'streets', 'topo', 'satellite']) await check(`base map ${id} (look at one tile by eye: ${id} 8/45/102 or so)`, () => png(T.urlFor(T.BASES[id], 8, 45, 102)));
  await check('terrain tile', () => png(R.urlFor(8, 45, 102)));
  await check('RainViewer', async () => {
    const r = W.parseRain(await (await f(W.RAIN)).json());
    return `${r.frames.length} frames, newest ${Math.round((Date.now() - r.newest.time * 1000) / 60000)} min old; one tile ${await png(W.rainUrl(r.host, r.newest, 5, 5, 12))}`;
  });
  for (const lon of [-118, -75, 10, 140]) await check(`satellite at ${lon}`, () => png(W.satUrl(W.satFor(lon), 3, 2, 3, T.tileBBox(3, 2, 3))));
  await check('Open-Meteo winds at 70 hPa', async () => {
    const cells = [{ lat: 34.5, lon: -118.5 }, { lat: 35.5, lon: -117.5 }];
    const w = W.parseWinds(await (await f(W.windUrl(cells, 70))).json(), 70);
    return `${w.length} places, ${w[0].spd[0]} kt from ${w[0].dir[0]} deg now`;
  });
  await check('NWS observation KEDW', async () => {
    const o = W.parseNws(await (await f('https://api.weather.gov/stations/KEDW/observations/latest')).json(), 'KEDW');
    return `${o.cat}, wind ${o.wdir}/${o.wspd} kt, "${o.raw.slice(0, 50)}"`;
  });
  await check('FAA airspace around the demo field', async () => {
    const r = await A.loadFaa(f, box);
    return `${r.zones.length} zones (${[...new Set(r.zones.map((z) => z.kind))].join(', ')}); status: ${r.status}`;
  });
  await check('OurAirports within 120 nmi (downloads 17 MB)', async () => {
    const [a, r] = await Promise.all([f(AP.CSV_BASE + '/airports.csv'), f(AP.CSV_BASE + '/runways.csv')]);
    const ap = AP.parseAirports(await a.text(), { center: centre, radius_nm: 120 });
    const list = AP.merge(ap, AP.parseRunways(await r.text(), new Set(ap.map((x) => x.ident))));
    return `${list.length} fields with a runway of 3,000 ft or more; longest ${list.sort((x, y) => y.rwy_ft - x.rwy_ft)[0].ident} ${list[0].rwy_ft} ft`;
  });
  if (awcArg) {
    const h = new W.Hazards({ fetch: f, awc: awcArg });
    await check('hazards through the helper', async () => {
      await h.ensure();
      return h.status;
    });
    const m = new W.Metars({ fetch: f, awc: awcArg });
    await check('METAR through the helper (EDDF)', async () => {
      await m.ensure(['EDDF']);
      return m.get('EDDF') ? `${m.get('EDDF').cat} ${m.get('EDDF').raw.slice(0, 50)}` : 'no report';
    });
  } else out.push('skip  the helper: add  --awc http://localhost:5402  with tools/awc-proxy.js running');
  console.log(out.join('\n'));
  process.exit(out.some((l) => l.startsWith('FAIL')) ? 1 : 0);
})();
