/**
 * Weather for the map: parsers for the free services a browser page can read, the choice of what applies at a height,
 * and the advisories that follow from NASA's own rules for this aircraft.
 *
 *   rain radar     RainViewer (global composite, past frames)
 *   satellite      infrared cloud tops: NASA GIBS (GOES-East, GOES-West, Himawari), EUMETSAT (Meteosat)
 *   winds aloft    Open-Meteo, on pressure levels, at the level nearest the aircraft's height
 *   hazards        SIGMET and G-AIRMET polygons (turbulence, icing, convection, ash) from aviationweather.gov, through the helper
 *                  in tools/awc-proxy.js: that service sends no CORS header, so a page cannot read it itself
 *   observations   METAR at fields: NWS (US), or aviationweather.gov through the helper
 *
 * All of it is real-world data, not the simulator's weather, and none of it is a clearance: NASA's weather-avoidance
 * guidelines (Cecil et al., NASA NTRS 20140008781) call turbulence "by far the most probable hazard" and lightning and cloud tops
 * its proxy, and say that a cell that matters can grow faster than data can show it. The rules the station applies to the polygons:
 *   at or below FL500: stay 25 nmi from thunderstorms; above FL500: 25 nmi from reported lightning where the tops are FL500 or
 *   higher, and 10,000 ft above it where they are lower; no flight into forecast or reported icing; none into forecast or
 *   reported moderate or severe turbulence.
 * A SIGMET is not a thunderstorm report and a polygon is not the weather, so the text says what was compared with what.
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const A = typeof module !== 'undefined' && module.exports ? require('./airspace.js') : root.GCS.airspace;
  const NM = geo.NM;
  const OPEN_METEO = 'https://api.open-meteo.com/v1/forecast';
  const RAIN = 'https://api.rainviewer.com/public/weather-maps.json';
  const NWS = 'https://api.weather.gov/stations/';
  const AWC = 'https://aviationweather.gov/api/data/';
  const LEVELS = [1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30];
  const KT_PER_KMH = 0.539957;

  /* ------------------------------------------------------------------ atmosphere */
  /** Standard-atmosphere pressure (hPa) at a height (ft): the troposphere's formula, then the isothermal layer up to 65,617 ft. */
  function pressureHpa(alt_ft) {
    const h = Math.max(0, alt_ft);
    if (h <= 36089) return 1013.25 * Math.pow(1 - 6.8756e-6 * h, 5.2559);
    if (h <= 65617) return 226.32 * Math.exp(-(h - 36089) / 20806.7);
    return 54.75 * Math.pow(1 + (h - 65617) * 1.5e-5 * 0.5, -34.16); // a little above 20 km: not needed to be exact here
  }

  /** The Open-Meteo level (hPa) nearest a height, in pressure's logarithm. */
  function levelFor(alt_ft) {
    const lp = Math.log(pressureHpa(alt_ft));
    return LEVELS.reduce((best, l) => (Math.abs(Math.log(l) - lp) < Math.abs(Math.log(best) - lp) ? l : best), LEVELS[0]);
  }

  /** Wind (direction it blows FROM, deg; speed kt) against a course: tail (+) or head (−) and the crosswind (+ from the right). */
  function components(course, dir, spd) {
    const toward = ((dir + 180 - course) * Math.PI) / 180;
    return { tail_kt: spd * Math.cos(toward), cross_kt: -spd * Math.sin(toward) };
  }

  const uv = (dir, spd) => [-spd * Math.sin((dir * Math.PI) / 180), -spd * Math.cos((dir * Math.PI) / 180)];
  const fromUv = (u, v) => ({ spd: Math.hypot(u, v), dir: ((Math.atan2(-u, -v) * 180) / Math.PI + 360) % 360 });

  /* ------------------------------------------------------------------ radar and satellite */
  function parseRain(json) {
    const r = (json && json.radar) || {};
    const frames = (r.past || []).concat(r.nowcast || []);
    return { host: (json && json.host) || '', frames, newest: frames.length ? frames[frames.length - 1] : null };
  }

  const rainUrl = (host, frame, z, x, y) => `${host}${frame.path}/256/${z}/${x}/${y}/2/1_1.png`;

  const SATS = [
    { id: 'goes-west', label: 'GOES-West', kind: 'gibs', layer: 'GOES-West_ABI_Band13_Clean_Infrared', maxZoom: 6, attr: 'NASA GIBS, NOAA GOES-West' },
    { id: 'goes-east', label: 'GOES-East', kind: 'gibs', layer: 'GOES-East_ABI_Band13_Clean_Infrared', maxZoom: 6, attr: 'NASA GIBS, NOAA GOES-East' },
    { id: 'meteosat', label: 'Meteosat', kind: 'wms', layer: 'msg_fes:ir108', maxZoom: 8, attr: '© EUMETSAT' },
    { id: 'himawari', label: 'Himawari', kind: 'gibs', layer: 'Himawari_AHI_Band13_Clean_Infrared', maxZoom: 6, attr: 'NASA GIBS, JMA Himawari' },
  ];

  /** The geostationary satellite that looks at a longitude. */
  function satFor(lon) {
    const l = ((lon + 540) % 360) - 180;
    if (l >= -165 && l < -105) return SATS[0];
    if (l >= -105 && l < -20) return SATS[1];
    if (l >= -20 && l < 60) return SATS[2];
    return SATS[3];
  }

  function satUrl(src, z, x, y, bbox) {
    if (src.kind === 'wms') return `https://view.eumetsat.int/geoserver/wms?service=WMS&version=1.3.0&request=GetMap&layers=${encodeURIComponent(src.layer)}&styles=&format=image/png&transparent=true&crs=EPSG:3857&width=256&height=256&bbox=${bbox}`;
    return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${src.layer}/default/default/GoogleMapsCompatible_Level6/${z}/${y}/${x}.png`;
  }

  /* ------------------------------------------------------------------ hazards */
  const HAZARD_KINDS = { TURB: 'turb', 'TURB-HI': 'turb', 'TURB-LO': 'turb', ICE: 'ice', ICING: 'ice', CONVECTIVE: 'convective', CONV: 'convective', ASH: 'ash', VA: 'ash', IFR: 'vis', MT_OBSC: 'vis', 'MTN OBSCN': 'vis', LLWS: 'low', SFC_WND: 'low', FZLVL: 'info', M_FZLVL: 'info' };
  const HAZARD_WORDS = { turb: 'turbulence', ice: 'icing', convective: 'convection', ash: 'volcanic ash', vis: 'low visibility', low: 'low-level wind', info: 'freezing level', other: 'weather' };
  /** The kinds that bear on this aircraft's heights; the others are low-level or informative. */
  const FLIGHT_HAZARDS = ['turb', 'ice', 'convective', 'ash'];

  const hundreds = (v) => {
    if (v === undefined || v === null || v === '') return null;
    if (/^SFC$/i.test(String(v))) return 0;
    if (/^FZL$/i.test(String(v))) return 0;
    const n = Number(v);
    return Number.isFinite(n) ? n * 100 : null;
  };

  function toRings(g) {
    if (!g) return [];
    const swap = (r) => r.map((c) => [c[1], c[0]]);
    if (g.type === 'Polygon') return [swap(g.coordinates[0])];
    if (g.type === 'MultiPolygon') return g.coordinates.map((p) => swap(p[0]));
    return [];
  }

  /** aviationweather.gov's SIGMET and AIRMET GeoJSON (the airsigmet endpoint) into hazards. */
  function parseAirSigmet(json) {
    const out = [];
    for (const f of (json && json.features) || []) {
      const p = f.properties || {};
      const rings = toRings(f.geometry);
      if (!rings.length) continue;
      const lows = [p.altitudeLow1, p.altitudeLow2].filter((v) => v !== null && v !== undefined);
      const highs = [p.altitudeHi1, p.altitudeHi2].filter((v) => v !== null && v !== undefined);
      const kind = HAZARD_KINDS[String(p.hazard || '').toUpperCase()] || 'other';
      out.push({
        id: `${p.airSigmetType || 'SIGMET'} ${p.seriesId || p.alphaChar || ''}`.trim(),
        source: p.airSigmetType || 'SIGMET',
        hazard: String(p.hazard || ''),
        kind,
        severity: p.severity,
        lo_ft: lows.length ? Math.min(...lows) : 0,
        hi_ft: highs.length ? Math.max(...highs) : 99999,
        from: Date.parse(p.validTimeFrom) || 0,
        to: Date.parse(p.validTimeTo) || 0,
        rings,
        text: p.rawAirSigmet || '',
      });
    }
    return out;
  }

  /** G-AIRMET GeoJSON (the gairmet endpoint): polygons only (the freezing-level lines are skipped). */
  function parseGairmet(json) {
    const out = [];
    for (const f of (json && json.features) || []) {
      const p = f.properties || {};
      const rings = toRings(f.geometry);
      if (!rings.length) continue;
      const kind = HAZARD_KINDS[String(p.hazard || '').toUpperCase()] || 'other';
      const lo = hundreds(p.base);
      const hi = hundreds(p.top);
      out.push({
        id: `G-AIRMET ${p.product || ''} ${p.tag || ''}`.trim(),
        source: 'G-AIRMET',
        hazard: String(p.hazard || ''),
        kind,
        severity: p.severity || '',
        lo_ft: lo === null ? 0 : lo,
        hi_ft: hi === null ? (kind === 'vis' || kind === 'low' ? 18000 : 99999) : hi,
        from: Date.parse(p.issueTime) || 0,
        to: Date.parse(p.validTime) || 0,
        forecast_h: p.forecast,
        rings,
        text: p.dueTo || '',
      });
    }
    return out;
  }

  /** A hazard that bears on the flight at a height (turbulence, icing, convection, ash whose band reaches it). */
  function hazardRelevant(h, alt_ft, margin) {
    const m = margin || 0;
    return FLIGHT_HAZARDS.includes(h.kind) && h.lo_ft <= alt_ft + m && h.hi_ft >= alt_ft - m;
  }

  const hh = (ms) => new Date(ms).toISOString().slice(11, 16) + 'Z';

  /**
   * What the path does with the hazards, by NASA's rules. path: [{ lat, lon, alt_ft }] (the aircraft first). opts: { now (ms), gs_kt }.
   * Returns [{ id, hazard, level: 'caution', where, text, action }], inside first.
   */
  function hazardAdvisories(hazards, path, opts) {
    opts = opts || {};
    const now = opts.now || Date.now();
    const gs = opts.gs_kt || 0;
    const aheadNm = gs > 50 ? gs / 3 : 60;
    const smp = A.samples(path, 2);
    const out = [];
    for (const h of hazards) {
      if (!FLIGHT_HAZARDS.includes(h.kind)) continue;
      if (h.to && h.to < now) continue;
      let buffer = 0;
      let hi = h.hi_ft;
      let rule = '';
      if (h.kind === 'convective') {
        const top = Math.max(...smp.map((s) => s.alt_ft));
        if (top <= 50000 || h.hi_ft >= 50000) {
          buffer = 25;
          rule = 'NASA 2012 rule: stay 25 nmi from thunderstorms (at or below FL500; above it where the tops are FL500 or higher)';
        } else {
          hi = h.hi_ft + 10000;
          rule = 'NASA 2012 rule: stay 10,000 ft above lightning when the tops are below FL500';
        }
      } else if (h.kind === 'ice') rule = 'NASA 2012 rule: no flight into forecast or reported icing';
      else if (h.kind === 'turb') rule = 'NASA 2012 rule: no flight into forecast or reported moderate or severe turbulence';
      // with a horizontal buffer (the 25 nmi rules) the height does not matter: the rule is about approaching the cell at any height
      const zone = A.make({ name: h.id, kind: 'other', lower: { ft: buffer ? 0 : h.lo_ft, ref: 'MSL' }, upper: { ft: buffer ? 99999 : hi, ref: 'MSL' }, rings: h.rings });
      const r = A.along(zone, smp, 0);
      let where = null;
      if (r.inside0) where = 'inside';
      else if (r.enter_nm !== null && r.enter_nm <= aheadNm) where = 'ahead';
      else if (r.enter_nm !== null) where = 'plan';
      else if (buffer && r.near_nm <= buffer) where = 'near';
      if (!where) continue;
      const band = `${A.fmtLimit({ ft: h.lo_ft, ref: h.lo_ft >= 18000 ? 'FL' : 'MSL' })} to ${A.fmtLimit({ ft: h.hi_ft, ref: h.hi_ft >= 18000 && h.hi_ft < 99999 ? 'FL' : 'MSL' })}`;
      const route = !!opts.route;
      const when = where === 'inside' ? (route ? 'the route starts inside it' : 'the aircraft is inside it') : where === 'near' ? `the ${route ? 'route' : 'path'} comes within ${Math.round(r.near_nm)} nmi of it` : route ? `entered ${Math.round(r.enter_nm)} nmi along the route` : `entered ${Math.round(r.enter_nm)} nmi ahead${where === 'plan' ? ' on the plan' : ''}`;
      out.push({
        id: `weather-${h.source}-${h.id}`.replace(/\s+/g, '-'),
        hazard: h,
        kind: h.kind,
        level: 'caution',
        where,
        enter_nm: r.enter_nm === null ? 0 : r.enter_nm,
        text: `WEATHER: ${h.id} ${HAZARD_WORDS[h.kind]}${h.severity ? ` (severity ${h.severity})` : ''}, ${band}${h.to ? `, valid until ${hh(h.to)}` : ''}: ${when}`,
        action: `${rule}. This compares the path with the area, not with the weather itself`,
      });
    }
    const w = { inside: 0, ahead: 1, plan: 2, near: 3 };
    out.sort((a, b) => w[a.where] - w[b.where] || a.enter_nm - b.enter_nm);
    return out;
  }

  /* ------------------------------------------------------------------ observations */
  /** Flight category from visibility (statute miles) and ceiling (ft; null for none). */
  function flightCategory(vis_sm, ceiling_ft) {
    const c = ceiling_ft === null || ceiling_ft === undefined ? Infinity : ceiling_ft;
    const v = vis_sm === null || vis_sm === undefined ? Infinity : vis_sm;
    if (c < 500 || v < 1) return 'LIFR';
    if (c < 1000 || v < 3) return 'IFR';
    if (c <= 3000 || v <= 5) return 'MVFR';
    return 'VFR';
  }

  const ceilingOf = (layers) => {
    const lows = (layers || []).filter((l) => /^(BKN|OVC|VV)$/i.test(l.cover || l.amount || '') && Number.isFinite(l.base)).map((l) => l.base);
    return lows.length ? Math.min(...lows) : null;
  };

  /** aviationweather.gov's METAR JSON into [{ id, lat, lon, wdir, wspd, wgst, vis_sm, ceiling_ft, cat, raw, time, src }]. */
  function parseAwcMetar(json) {
    return (Array.isArray(json) ? json : []).map((m) => {
      const vis = typeof m.visib === 'string' ? parseFloat(m.visib) : m.visib;
      const ceil = ceilingOf(m.clouds);
      return { id: m.icaoId, lat: m.lat, lon: m.lon, wdir: typeof m.wdir === 'number' ? m.wdir : null, wspd: m.wspd, wgst: m.wgst || null, vis_sm: Number.isFinite(vis) ? vis : null, ceiling_ft: ceil, cat: m.fltCat || flightCategory(vis, ceil), raw: m.rawOb || '', time: (m.obsTime || 0) * 1000, src: 'aviationweather.gov' };
    });
  }

  /** api.weather.gov's latest observation of a station into the same record (it counts in km/h and metres). */
  function parseNws(json, id) {
    const p = json && json.properties;
    if (!p) return null;
    const val = (q) => (q && Number.isFinite(q.value) ? q.value : null);
    const spd = val(p.windSpeed);
    const gst = val(p.windGust);
    const vis = val(p.visibility);
    const layers = (p.cloudLayers || []).map((l) => ({ cover: l.amount, base: val(l.base) === null ? null : val(l.base) * 3.28084 }));
    const ceil = ceilingOf(layers);
    const vis_sm = vis === null ? null : vis / 1609.34;
    return { id, wdir: val(p.windDirection), wspd: spd === null ? null : Math.round(spd * KT_PER_KMH), wgst: gst === null ? null : Math.round(gst * KT_PER_KMH), vis_sm, ceiling_ft: ceil === null ? null : Math.round(ceil), cat: flightCategory(vis_sm, ceil), raw: p.rawMessage || '', time: Date.parse(p.timestamp) || 0, src: 'api.weather.gov' };
  }

  /* ------------------------------------------------------------------ winds aloft */
  function windUrl(cells, level) {
    return `${OPEN_METEO}?latitude=${cells.map((c) => c.lat).join(',')}&longitude=${cells.map((c) => c.lon).join(',')}&hourly=wind_speed_${level}hPa,wind_direction_${level}hPa&forecast_days=2&wind_speed_unit=kn&timezone=GMT`;
  }

  /** Open-Meteo's answer (one object, or an array for several places) into [{ times, spd, dir }]. */
  function parseWinds(json, level) {
    const arr = Array.isArray(json) ? json : [json];
    return arr.map((o) => ({ lat: o.latitude, lon: o.longitude, times: o.hourly.time, spd: o.hourly[`wind_speed_${level}hPa`], dir: o.hourly[`wind_direction_${level}hPa`] }));
  }

  /** The wind field: cells of a fixed lattice, kept an hour, fetched in groups of at most 30, six seconds apart. */
  class WindField {
    constructor(deps) {
      this.fetch = deps.fetch;
      this.now = deps.now || (() => Date.now());
      this.cells = new Map();
      this.step = 2;
      this.status = 'off';
      this.busy = false;
      this.nextAt = 0;
      this.failUntil = 0;
    }

    static stepFor(box) {
      const raw = Math.max(box[2] - box[0], box[3] - box[1]) / 7;
      return [0.5, 1, 2, 4, 8].find((v) => v >= raw) || 8;
    }

    static lattice(box, step) {
      const out = [];
      for (let i = Math.floor(box[0] / step); i <= Math.ceil(box[2] / step); i++) for (let j = Math.floor(box[1] / step); j <= Math.ceil(box[3] / step); j++) out.push({ i, j, lat: +(i * step).toFixed(3), lon: +(j * step).toFixed(3) });
      return out;
    }

    async ensure(box, level) {
      const t = this.now();
      if (this.busy || t < this.failUntil || t < this.nextAt) return;
      const step = WindField.stepFor(box);
      this.step = step;
      let cells = WindField.lattice(box, step);
      if (cells.length > 90) cells = cells.slice(0, 90);
      const missing = cells.filter((c) => {
        const e = this.cells.get(`${level}/${step}/${c.i}/${c.j}`);
        return !e || t - e.t > 3600000;
      }).slice(0, 30);
      if (!missing.length) return;
      this.busy = true;
      this.nextAt = t + 6000;
      try {
        const r = await this.fetch(windUrl(missing, level));
        if (!r.ok) throw Object.assign(new Error('HTTP ' + r.status), { status: r.status });
        const got = parseWinds(await r.json(), level);
        got.forEach((g, k) => this.cells.set(`${level}/${step}/${missing[k].i}/${missing[k].j}`, { t, times: g.times, spd: g.spd, dir: g.dir }));
        if (this.cells.size > 900) for (const k of [...this.cells.keys()].slice(0, 200)) this.cells.delete(k);
        this.status = `${got.length} places added (Open-Meteo, ${level} hPa)`;
      } catch (e) {
        this.failUntil = this.now() + (e.status === 429 ? 300000 : 60000);
        this.status = e.status === 429 ? 'Open-Meteo says too many requests: pausing 5 min' : 'winds failed: ' + e.message + '; trying again in 1 min';
      }
      this.busy = false;
    }

    /**
     * For the route planner: every level in `levels` over a box, in as few requests as possible (a request carries at most 30 places and all the levels of
     * them), one after the other with no pause between (the planner waits for them). Returns { ok, status, places }.
     */
    async prefetch(box, levels) {
      const t = this.now();
      if (t < this.failUntil) return { ok: false, status: this.status };
      const step = WindField.stepFor(box);
      this.step = step;
      const cells = WindField.lattice(box, step).slice(0, 120);
      const fresh = (l, c) => {
        const e = this.cells.get(`${l}/${step}/${c.i}/${c.j}`);
        return e && t - e.t < 3600000;
      };
      const need = cells.filter((c) => levels.some((l) => !fresh(l, c)));
      let got = 0;
      try {
        while (need.length) {
          const batch = need.splice(0, 30);
          const vars = levels.map((l) => `wind_speed_${l}hPa,wind_direction_${l}hPa`).join(',');
          const url = `${OPEN_METEO}?latitude=${batch.map((c) => c.lat).join(',')}&longitude=${batch.map((c) => c.lon).join(',')}&hourly=${vars}&forecast_days=2&wind_speed_unit=kn&timezone=GMT`;
          const r = await this.fetch(url);
          if (!r.ok) throw Object.assign(new Error('HTTP ' + r.status), { status: r.status });
          const j = await r.json();
          for (const l of levels) parseWinds(j, l).forEach((g, k) => this.cells.set(`${l}/${step}/${batch[k].i}/${batch[k].j}`, { t, times: g.times, spd: g.spd, dir: g.dir }));
          got += batch.length;
        }
        this.status = got ? `${got} places on ${levels.length} levels added for the route (Open-Meteo)` : this.status;
        return { ok: true, status: this.status, places: got };
      } catch (e) {
        this.failUntil = this.now() + (e.status === 429 ? 300000 : 60000);
        this.status = e.status === 429 ? 'Open-Meteo says too many requests: pausing 5 min' : 'winds failed: ' + e.message;
        return { ok: false, status: this.status };
      }
    }

    /** The wind at a place, height and hours from now: { spd, dir (from), level } or null. Bilinear between the lattice cells that are there. */
    at(lat, lon, alt_ft, hours) {
      const level = levelFor(alt_ft);
      const step = this.step;
      const i0 = Math.floor(lat / step);
      const j0 = Math.floor(lon / step);
      const want = new Date(this.now() + (hours || 0) * 3600000).toISOString().slice(0, 13);
      let su = 0;
      let sv = 0;
      let sw = 0;
      for (const [di, dj] of [[0, 0], [0, 1], [1, 0], [1, 1]]) {
        const e = this.cells.get(`${level}/${step}/${i0 + di}/${j0 + dj}`);
        if (!e) continue;
        let k = e.times.findIndex((s) => s.slice(0, 13) === want);
        if (k < 0) k = Math.min(e.times.length - 1, Math.max(0, hours || 0));
        const spd = e.spd[k];
        const dir = e.dir[k];
        if (!Number.isFinite(spd) || !Number.isFinite(dir)) continue;
        const w = (1 - Math.abs(lat / step - (i0 + di))) * (1 - Math.abs(lon / step - (j0 + dj)));
        const [u, v] = uv(dir, spd);
        su += u * w;
        sv += v * w;
        sw += w;
      }
      if (sw <= 0) return null;
      return Object.assign(fromUv(su / sw, sv / sw), { level });
    }

    /** Arrows to draw for a box at a height: [{ lat, lon, spd, dir }] on the lattice. */
    arrows(box, alt_ft, hours) {
      const out = [];
      for (const c of WindField.lattice(box, this.step)) {
        const w = this.at(c.lat, c.lon, alt_ft, hours);
        if (w) out.push({ lat: c.lat, lon: c.lon, spd: w.spd, dir: w.dir });
      }
      return out;
    }
  }

  /**
   * The wind on each leg of a path: [{ i, course, tail_kt, cross_kt, spd, dir }], from the wind at the middle of the leg at its mean height.
   * windAt: (lat, lon, alt_ft) => { spd, dir } | null.
   */
  function legWinds(path, windAt) {
    const out = [];
    for (let i = 0; i + 1 < path.length; i++) {
      const a = path[i];
      const b = path[i + 1];
      const mid = [(a.lat + b.lat) / 2, (a.lon + b.lon) / 2];
      const alt = (a.alt_ft + b.alt_ft) / 2;
      const w = windAt(mid[0], mid[1], alt);
      if (!w) continue;
      const course = geo.course([a.lat, a.lon], [b.lat, b.lon]).deg;
      out.push(Object.assign({ i, course, spd: w.spd, dir: w.dir }, components(course, w.dir, w.spd)));
    }
    return out;
  }

  /* ------------------------------------------------------------------ the feeds that need a helper or a service */
  /** aviationweather.gov's address through the helper (awc: its base, e.g. http://localhost:5402), or null when there is none. */
  const awcUrl = (awc, path, query) => (awc ? `${awc.replace(/\/$/, '')}/api/data/${path}?${query}` : null);

  /** The hazard polygons: SIGMETs and G-AIRMETs, refreshed every five minutes, through the helper. */
  class Hazards {
    constructor(deps) {
      this.fetch = deps.fetch;
      this.awc = deps.awc || null;
      this.now = deps.now || (() => Date.now());
      this.list = [];
      this.fetched = 0;
      this.status = this.awc ? 'not loaded' : 'needs the helper: aviationweather.gov does not let a web page read it (run tools/awc-proxy.js and open this page with ?awc=http://localhost:5402)';
      this.failedAt = -Infinity;
      this.busy = false;
    }

    async ensure() {
      if (!this.awc || this.busy || this.now() - this.fetched < 300000 || this.now() - this.failedAt < 60000) return;
      this.busy = true;
      try {
        const [a, g] = await Promise.all([this.fetch(awcUrl(this.awc, 'airsigmet', 'format=geojson')), this.fetch(awcUrl(this.awc, 'gairmet', 'format=geojson'))]);
        if (!a.ok || !g.ok) throw new Error('HTTP ' + (a.ok ? g.status : a.status));
        this.list = parseAirSigmet(await a.json()).concat(parseGairmet(await g.json()));
        this.fetched = this.now();
        this.status = `${this.list.length} areas (SIGMET and G-AIRMET, aviationweather.gov), read ${hh(this.fetched)}`;
      } catch (e) {
        this.failedAt = this.now();
        this.status = 'hazards failed: ' + e.message + (this.list.length ? ' (the last ones are shown)' : '');
      }
      this.busy = false;
    }
  }

  /** METAR for a list of fields: NWS for US stations, aviationweather.gov through the helper for the rest. Ten minutes' life. */
  class Metars {
    constructor(deps) {
      this.fetch = deps.fetch;
      this.awc = deps.awc || null;
      this.now = deps.now || (() => Date.now());
      this.byId = new Map();
      this.tried = new Map();
      this.status = 'not loaded';
    }

    get(id) {
      return this.byId.get(id) || null;
    }

    async ensure(ids) {
      const t = this.now();
      const want = ids.filter((id) => !this.tried.has(id) || t - this.tried.get(id) > 600000).slice(0, 12);
      if (!want.length) return;
      want.forEach((id) => this.tried.set(id, t));
      const us = want.filter((id) => /^(K[A-Z0-9]{3}|P[AGHW][A-Z0-9]{2})$/.test(id));
      const other = want.filter((id) => !us.includes(id));
      let got = 0;
      await Promise.all(us.map(async (id) => {
        try {
          const r = await this.fetch(`${NWS}${id}/observations/latest`);
          if (!r.ok) return;
          const o = parseNws(await r.json(), id);
          if (o) {
            this.byId.set(id, o);
            got++;
          }
        } catch (e) { /* a station with no report is just not shown */ }
      }));
      if (other.length && this.awc) {
        try {
          const r = await this.fetch(awcUrl(this.awc, 'metar', `ids=${other.join(',')}&format=json`));
          if (r.ok) for (const m of parseAwcMetar(await r.json())) {
            this.byId.set(m.id, m);
            got++;
          }
        } catch (e) { /* likewise */ }
      }
      this.status = `${this.byId.size} reports (${got} new)${other.length && !this.awc ? '; fields outside the US need the helper' : ''}`;
    }
  }

  /** The newest rain frame's age in minutes, for the row's status. */
  const ageMin = (frame, now) => (frame ? Math.round((now - frame.time * 1000) / 60000) : null);

  const api = { LEVELS, pressureHpa, levelFor, components, uv, fromUv, parseRain, rainUrl, SATS, satFor, satUrl, HAZARD_WORDS, FLIGHT_HAZARDS, parseAirSigmet, parseGairmet, hazardRelevant, hazardAdvisories, flightCategory, parseAwcMetar, parseNws, windUrl, parseWinds, WindField, legWinds, awcUrl, Hazards, Metars, ageMin, RAIN };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).weather = api;
})(typeof window !== 'undefined' ? window : globalThis);
