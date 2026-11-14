/**
 * Airports for the map, from OurAirports' open CSV files (public domain), and the test of whether the aircraft could
 * land on one.
 *
 * The Global Hawk needs a long paved runway: the station's own landing forecast (js/predict.js, from the flight model's
 * landings) says how much runway to have past the aiming point at a weight. A field is "usable now" when its longest
 * paved runway is at least that plus AIM_ALLOWANCE_FT (the aiming point is not at the threshold: the demo plan puts it
 * 800 ft in, an assumed allowance), "usable lighter" when it would be at the weight with only the reserve left, and
 * otherwise not. Nothing about the field's weather, surface condition, lights, approach or permission is known here.
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const AIM_ALLOWANCE_FT = 800;
  const FALLBACK_NEED_FT = 7500; // when the forecast has no landings table: an assumption, and the panel says so
  const MIN_RUNWAY_FT = 3000;
  const CSV_BASE = 'https://davidmegginson.github.io/ourairports-data';

  /** One CSV line into fields (quotes, commas inside quotes, doubled quotes). */
  function csvLine(line) {
    const out = [];
    let cur = '';
    let q = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (q) {
        if (c === '"') {
          if (line[i + 1] === '"') {
            cur += '"';
            i++;
          } else q = false;
        } else cur += c;
      } else if (c === '"') q = true;
      else if (c === ',') {
        out.push(cur);
        cur = '';
      } else cur += c;
    }
    out.push(cur);
    return out;
  }

  const lines = (text) => String(text).split(/\r?\n/).filter((l) => l.length);

  /** airports.csv into [{ ident, name, lat, lon, elev_ft, type, country, city }]; heliports, seaplane bases, closed fields are left out. opts: { center: [lat, lon], radius_nm }. */
  function parseAirports(text, opts) {
    opts = opts || {};
    const L = lines(text);
    if (!L.length) return [];
    const head = csvLine(L[0]);
    const ix = (n) => head.indexOf(n);
    const iT = ix('type');
    const iN = ix('name');
    const iLa = ix('latitude_deg');
    const iLo = ix('longitude_deg');
    const iE = ix('elevation_ft');
    const iId = ix('ident');
    const iC = ix('iso_country');
    const iM = ix('municipality');
    const out = [];
    for (let k = 1; k < L.length; k++) {
      const f = csvLine(L[k]);
      if (!/^(small_airport|medium_airport|large_airport)$/.test(f[iT])) continue;
      const lat = parseFloat(f[iLa]);
      const lon = parseFloat(f[iLo]);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      if (opts.center && geo.course(opts.center, [lat, lon]).ft / geo.NM > (opts.radius_nm || 500)) continue;
      out.push({ ident: f[iId], name: f[iN], lat, lon, elev_ft: parseFloat(f[iE]) || 0, type: f[iT], country: f[iC], city: f[iM] || '' });
    }
    return out;
  }

  const PAVED = /^(ASP|CON|PEM|BIT|TAR|MAC|PAV)/i;

  /** runways.csv into { ident: [{ len_ft, width_ft, surface, paved, le, he, hdg }] }; closed runways are left out. idents: a Set to keep, or null for all. */
  function parseRunways(text, idents) {
    const L = lines(text);
    if (!L.length) return {};
    const head = csvLine(L[0]);
    const ix = (n) => head.indexOf(n);
    const iA = ix('airport_ident');
    const iL = ix('length_ft');
    const iW = ix('width_ft');
    const iS = ix('surface');
    const iC = ix('closed');
    const iLe = ix('le_ident');
    const iHe = ix('he_ident');
    const iH = ix('le_heading_degT');
    const out = {};
    for (let k = 1; k < L.length; k++) {
      const f = csvLine(L[k]);
      if (f[iC] === '1') continue;
      if (idents && !idents.has(f[iA])) continue;
      const len = parseFloat(f[iL]);
      if (!Number.isFinite(len)) continue;
      (out[f[iA]] = out[f[iA]] || []).push({ len_ft: Math.round(len), width_ft: Math.round(parseFloat(f[iW]) || 0), surface: f[iS], paved: PAVED.test(f[iS] || ''), le: f[iLe], he: f[iHe], hdg: parseFloat(f[iH]) });
    }
    return out;
  }

  /** Fields with their runways, longest first; fields with no runway of at least minFt are dropped. */
  function merge(airports, runways, minFt) {
    const out = [];
    for (const a of airports) {
      const r = (runways[a.ident] || []).slice().sort((x, y) => y.len_ft - x.len_ft);
      if (!r.length || r[0].len_ft < (minFt === undefined ? MIN_RUNWAY_FT : minFt)) continue;
      const paved = r.filter((x) => x.paved);
      out.push(Object.assign({}, a, { rwys: r, rwy_ft: r[0].len_ft, paved_ft: paved.length ? paved[0].len_ft : 0 }));
    }
    return out;
  }

  /** The runway length a landing at a weight asks for on a field at a height, from the station's forecast: { need_ft, known }. */
  function need(forecast, weight_lb, elev_ft) {
    let L = null;
    try {
      L = forecast && forecast.landing ? forecast.landing(weight_lb, elev_ft) : null;
    } catch (e) {
      L = null;
    }
    return L && Number.isFinite(L.runway_ft) ? { need_ft: Math.round(L.runway_ft + AIM_ALLOWANCE_FT), known: true } : { need_ft: FALLBACK_NEED_FT, known: false };
  }

  /** 'now' (usable at this weight), 'lighter' (at the reserve weight) or 'no'. */
  function usable(ap, needNow, needLight) {
    if (ap.paved_ft >= needNow) return 'now';
    if (needLight !== undefined && ap.paved_ft >= needLight) return 'lighter';
    return 'no';
  }

  function nearest(list, lat, lon, n, pred) {
    return list
      .filter((a) => !pred || pred(a))
      .map((a) => ({ a, nm: geo.course([lat, lon], [a.lat, a.lon]).ft / geo.NM }))
      .sort((x, y) => x.nm - y.nm)
      .slice(0, n || 5);
  }

  /** The fields inside a lat/lon box, the longest runways first, at most `max`: so that a zoomed-out map shows the big ones. */
  function inBox(list, box, max) {
    return list.filter((a) => a.lat >= box[0] && a.lat <= box[2] && a.lon >= box[1] && a.lon <= box[3]).sort((x, y) => y.rwy_ft - x.rwy_ft).slice(0, max || 60);
  }

  /** Headwind-independent crosswind (kt) of a wind on a runway: |speed × sin(wind from − runway heading)|. */
  function crosswind(wdir, wspd, rwyHdg) {
    if (![wdir, wspd, rwyHdg].every(Number.isFinite)) return null;
    return Math.abs(wspd * Math.sin(((wdir - rwyHdg) * Math.PI) / 180));
  }

  /* ------------------------------------------------------------------ the keeper */
  /**
   * The airports around a place, kept in the browser. deps: { fetch, store, base (a mirror's address, for tests) }.
   * `ensure(centre, radius_nm)` loads what the store has, or downloads the two CSV files (17 MB) once, keeps the fields inside
   * the radius that have a runway of 3,000 ft or more, and says what happened in `status`.
   */
  class Airports {
    constructor(deps) {
      this.fetch = deps.fetch;
      this.store = deps.store || null;
      this.base = deps.base || CSV_BASE;
      this.list = [];
      this.coverage = null;
      this.status = 'not loaded';
      this.busy = false;
      this.failedAt = -Infinity;
      this.now = deps.now || (() => Date.now());
    }

    covers(centre) {
      return !!(this.coverage && geo.course(this.coverage.centre, centre).ft / geo.NM < this.coverage.radius_nm * 0.6);
    }

    async restore() {
      if (!this.store) return;
      const s = await this.store.get('airports');
      if (s && s.list && s.list.length) {
        this.list = s.list;
        this.coverage = s.coverage;
        this.status = `${this.list.length} fields kept in this browser`;
      }
    }

    /** Add a file the user loaded (airports.csv format, with or without its runways). */
    addFile(airportsText, runwaysText) {
      const ap = parseAirports(airportsText);
      const rw = runwaysText ? parseRunways(runwaysText, null) : {};
      const have = runwaysText ? merge(ap, rw) : ap.map((a) => Object.assign({ rwys: [], rwy_ft: 0, paved_ft: 0 }, a));
      const known = new Set(this.list.map((a) => a.ident));
      for (const a of have) if (!known.has(a.ident)) this.list.push(a);
      this.status = `${this.list.length} fields (a file loaded)`;
      return have.length;
    }

    async ensure(centre, radius_nm) {
      if (this.busy || this.covers(centre) || this.now() - this.failedAt < 60000) return;
      this.busy = true;
      this.status = 'loading airports…';
      try {
        const [a, r] = await Promise.all([this.fetch(this.base + '/airports.csv'), this.fetch(this.base + '/runways.csv')]);
        if (!a.ok || !r.ok) throw new Error('HTTP ' + (a.ok ? r.status : a.status));
        const ap = parseAirports(await a.text(), { center: centre, radius_nm: radius_nm || 500 });
        const rw = parseRunways(await r.text(), new Set(ap.map((x) => x.ident)));
        const user = this.list.filter((x) => x.userFile);
        this.list = merge(ap, rw).concat(user);
        this.coverage = { centre, radius_nm: radius_nm || 500 };
        this.status = `${this.list.length} fields within ${radius_nm || 500} nmi (OurAirports)`;
        if (this.store) await this.store.set('airports', { list: this.list, coverage: this.coverage });
      } catch (e) {
        this.failedAt = this.now();
        this.status = 'could not load airports: ' + e.message + (this.list.length ? ' (the kept ones are shown)' : '');
      }
      this.busy = false;
    }
  }

  const api = { csvLine, parseAirports, parseRunways, merge, need, usable, nearest, inBox, crosswind, Airports, AIM_ALLOWANCE_FT, FALLBACK_NEED_FT, MIN_RUNWAY_FT, CSV_BASE };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).airports = api;
})(typeof window !== 'undefined' ? window : globalThis);
