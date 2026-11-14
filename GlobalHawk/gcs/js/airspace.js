/**
 * Airspace: parsing (OpenAir text, GeoJSON as the FAA's open-data service gives it, OpenAIP-style JSON), the
 * geometry of a zone against a point or a path, and the advisories the station raises: "the plan crosses R-2508".
 *
 * A zone: { id, name, kind, cls, lower: {ft, ref}, upper: {ft, ref}, rings: [[[lat, lon], …]], holes, circle, bbox, times, src }.
 * Heights are feet; ref is MSL, AGL or FL. An AGL limit is read as MSL (the terrain is not looked up) and the text says so.
 * Times of use are not interpreted: a zone is taken as active, and the advisory says the times were not checked.
 * Advisory only: no layer or advisory here refuses, changes or sends a command.
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const NM = geo.NM;
  const FT_PER_M = 3.28084;
  const RAD = Math.PI / 180;

  /** How each kind is drawn and how loudly it is advised. `drawn`: in Auto and by default (Class A and E are not drawn). */
  const KINDS = {
    prohibited: { label: 'prohibited', level: 'caution', colour: '#ff5252', drawn: true },
    restricted: { label: 'restricted', level: 'caution', colour: '#ff5252', drawn: true },
    danger: { label: 'danger', level: 'caution', colour: '#ff5252', drawn: true },
    tfr: { label: 'temporary flight restriction', level: 'caution', colour: '#ff5252', drawn: true },
    warning: { label: 'warning area', level: 'advisory', colour: '#b388ff', drawn: true },
    alert: { label: 'alert area', level: 'advisory', colour: '#b388ff', drawn: true },
    moa: { label: 'military operations area', level: 'advisory', colour: '#b388ff', drawn: true },
    classB: { label: 'Class B', level: 'advisory', colour: '#5b9dff', drawn: true },
    classC: { label: 'Class C', level: 'advisory', colour: '#5b9dff', drawn: true },
    classD: { label: 'Class D', level: 'advisory', colour: '#5b9dff', drawn: true },
    other: { label: 'airspace', level: 'advisory', colour: '#8d99a6', drawn: true },
    classA: { label: 'Class A', level: 'advisory', colour: '#5b9dff', drawn: false },
    classE: { label: 'Class E', level: 'advisory', colour: '#5b9dff', drawn: false },
  };

  /* ------------------------------------------------------------------ heights */
  /** "FL195", "5000ft AGL", "SFC", "UNL", "3000 AMSL", "1500 m" into { ft, ref }. */
  function parseAlt(text) {
    const s = String(text === undefined || text === null ? '' : text).trim().toUpperCase();
    if (/UNL|UNLIM/.test(s)) return { ft: 99999, ref: 'MSL' };
    if (/^(GND|SFC|SURFACE)/.test(s)) return { ft: 0, ref: 'AGL' };
    let m = /FL\s*(\d+)/.exec(s);
    if (m) return { ft: Number(m[1]) * 100, ref: 'FL' };
    m = /(-?\d+(?:\.\d+)?)\s*(FT|F|'|M)?\s*(AMSL|MSL|AGL|GND|STD)?/.exec(s);
    if (!m) return { ft: 0, ref: 'MSL' };
    let ft = Number(m[1]);
    if (m[2] === 'M') ft *= FT_PER_M;
    const ref = /AGL|GND/.test(m[3] || s) ? 'AGL' : /STD/.test(m[3] || '') ? 'FL' : 'MSL';
    return { ft: Math.round(ft), ref };
  }

  const fmtLimit = (a) => (a.ft >= 99999 ? 'unlimited' : a.ft === 0 && a.ref === 'AGL' ? 'the surface' : a.ref === 'FL' ? `FL${String(Math.round(a.ft / 100)).padStart(3, '0')}` : `${Math.round(a.ft).toLocaleString('en-US')} ft ${a.ref}`);

  /* ------------------------------------------------------------------ the record */
  let counter = 0;
  function make(o) {
    const z = Object.assign({ id: 'z' + ++counter, name: '', kind: 'other', cls: '', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 99999, ref: 'MSL' }, rings: [], holes: [], circle: null, times: '', src: '' }, o);
    const pts = z.circle ? [] : [].concat(...z.rings);
    if (z.circle) {
      const dLat = z.circle.r_ft / (NM * 60);
      const dLon = dLat / Math.max(0.01, Math.cos(z.circle.lat * RAD));
      z.bbox = [z.circle.lat - dLat, z.circle.lon - dLon, z.circle.lat + dLat, z.circle.lon + dLon];
    } else if (pts.length) {
      z.bbox = [Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1])), Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))];
    } else z.bbox = null;
    return z;
  }

  /* ------------------------------------------------------------------ OpenAir */
  function oaCoord(s) {
    const m = /(\d+):(\d+)(?::(\d+(?:\.\d+)?))?\s*([NS])\s+(\d+):(\d+)(?::(\d+(?:\.\d+)?))?\s*([EW])/i.exec(s);
    if (!m) return null;
    const lat = (+m[1] + +m[2] / 60 + (+m[3] || 0) / 3600) * (m[4].toUpperCase() === 'S' ? -1 : 1);
    const lon = (+m[5] + +m[6] / 60 + (+m[7] || 0) / 3600) * (m[8].toUpperCase() === 'W' ? -1 : 1);
    return [lat, lon];
  }

  /** The point at a bearing (deg) and distance (ft) from a, flat earth. */
  const at = (a, brg, ft) => geo.along(a, brg, ft);

  function oaKind(code, name) {
    const c = String(code).toUpperCase().trim();
    const n = String(name).toUpperCase();
    if (c === 'P') return 'prohibited';
    if (c === 'R') return 'restricted';
    if (c === 'Q') return 'danger';
    if (/\bTFR\b/.test(n)) return 'tfr';
    if (/\bMOA\b/.test(n)) return 'moa';
    if (/WARNING/.test(n)) return 'warning';
    if (/ALERT/.test(n)) return 'alert';
    if (c === 'A') return 'classA';
    if (c === 'B') return 'classB';
    if (c === 'C') return 'classC';
    if (c === 'D' || c === 'CTR') return 'classD';
    if (c === 'E') return 'classE';
    return 'other';
  }

  function parseOpenAir(text) {
    const out = [];
    let cur = null;
    let centre = null;
    let cw = true;
    const flush = () => {
      if (cur && (cur.circle || cur.pts.length >= 3)) {
        out.push(make({ name: cur.name, kind: oaKind(cur.code, cur.name), cls: cur.code, lower: cur.lower, upper: cur.upper, rings: cur.circle ? [] : [cur.pts], circle: cur.circle, src: 'OpenAir' }));
      }
      cur = null;
    };
    for (const raw of String(text).split(/\r?\n/)) {
      const line = raw.replace(/\*.*$/, '').trim();
      if (!line) continue;
      const tag = line.slice(0, 2).toUpperCase();
      const rest = line.slice(2).trim();
      if (tag === 'AC') {
        flush();
        cur = { code: rest, name: '', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 99999, ref: 'MSL' }, pts: [], circle: null };
        centre = null;
        cw = true;
      } else if (!cur) continue;
      else if (tag === 'AN') cur.name = rest;
      else if (tag === 'AL') cur.lower = parseAlt(rest);
      else if (tag === 'AH') cur.upper = parseAlt(rest);
      else if (tag === 'DP') {
        const c = oaCoord(rest);
        if (c) cur.pts.push(c);
      } else if (/^V\s*X\s*=/i.test(line)) centre = oaCoord(line.replace(/^V\s*X\s*=/i, ''));
      else if (/^V\s*D\s*=/i.test(line)) cw = line.replace(/^V\s*D\s*=/i, '').trim() !== '-';
      else if (tag === 'DC' && centre) cur.circle = { lat: centre[0], lon: centre[1], r_ft: parseFloat(rest) * NM };
      else if ((tag === 'DB' || tag === 'DA') && centre) {
        let a0;
        let a1;
        let r;
        if (tag === 'DB') {
          const [p, q] = rest.split(',').map((s) => oaCoord(s));
          if (!p || !q) continue;
          r = geo.course(centre, p).ft;
          a0 = geo.course(centre, p).deg;
          a1 = geo.course(centre, q).deg;
        } else {
          const w = rest.split(',').map((s) => parseFloat(s));
          r = w[0] * NM;
          a0 = w[1];
          a1 = w[2];
        }
        const span = cw ? (a1 - a0 + 360) % 360 : -((a0 - a1 + 360) % 360);
        const n = Math.max(2, Math.ceil(Math.abs(span) / 5));
        for (let i = 0; i <= n; i++) cur.pts.push(at(centre, a0 + (span * i) / n, r));
      }
    }
    flush();
    return out;
  }

  /* ------------------------------------------------------------------ GeoJSON: FAA and OpenAIP */
  function faaKind(p) {
    const t = String(p.TYPE_CODE || p.TYPE || '').toUpperCase();
    const c = String(p.CLASS || p.CLASS_CODE || '').toUpperCase().replace('CLASS', '').trim();
    const n = String(p.NAME || p.NAME_TXT || '').toUpperCase();
    if (/^P$|PROHIB/.test(t)) return 'prohibited';
    if (/^R(EST)?$|^R-|RESTRICT/.test(t) || /^R-?\d{3,4}/.test(n)) return 'restricted';
    if (/MOA/.test(t) || /\bMOA\b/.test(n)) return 'moa';
    if (/^W(ARN)?/.test(t) || /WARNING/.test(t)) return 'warning';
    if (/^A(LERT)?$/.test(t) || /ALERT/.test(t)) return 'alert';
    if (/^D(ANGER)?$/.test(t) || /DANGER/.test(t)) return 'danger';
    if (/TFR|NATIONAL DEFENSE|SECURITY/.test(t + ' ' + n)) return 'tfr';
    if (c === 'A') return 'classA';
    if (c === 'B') return 'classB';
    if (c === 'C') return 'classC';
    if (c === 'D') return 'classD';
    if (c === 'E') return 'classE';
    return 'other';
  }

  /** A height of the FAA's records: UPPER_VAL, UPPER_UOM, UPPER_CODE (or the DISTVERT… names of the other layer). */
  function faaAlt(p, which) {
    const val = p[which + '_VAL'] !== undefined ? p[which + '_VAL'] : p['DISTVERT' + which + '_VAL'];
    const uom = String(p[which + '_UOM'] || p['DISTVERT' + which + '_UOM'] || 'FT').toUpperCase();
    const code = String(p[which + '_CODE'] || p['DISTVERT' + which + '_CODE'] || '').toUpperCase();
    if (val === undefined || val === null || val === '' || Number(val) === -9998) return which === 'LOWER' ? { ft: 0, ref: 'AGL' } : { ft: 99999, ref: 'MSL' };
    if (/SFC|GND/.test(code) && Number(val) === 0) return { ft: 0, ref: 'AGL' };
    let ft = Number(val);
    if (uom === 'FL') return { ft: ft * 100, ref: 'FL' };
    if (uom === 'M') ft *= FT_PER_M;
    if (ft >= 99999 || /UNL/.test(code)) return { ft: 99999, ref: 'MSL' };
    return { ft: Math.round(ft), ref: /AGL|SFC/.test(code) ? 'AGL' : code === 'STD' ? 'FL' : 'MSL' };
  }

  function openAipAlt(l) {
    if (!l || l.value === undefined || l.value === null) return null;
    const v = Number(l.value);
    const ref = l.referenceDatum === 0 ? 'AGL' : l.referenceDatum === 2 ? 'FL' : 'MSL';
    if (l.unit === 6) return { ft: v * 100, ref: 'FL' };
    return { ft: Math.round(l.unit === 0 ? v * FT_PER_M : v), ref };
  }

  const OAIP_TYPES = { 1: 'restricted', 2: 'danger', 3: 'prohibited', 12: 'alert', 13: 'warning' };
  const OAIP_CLASS = { 0: 'classA', 1: 'classB', 2: 'classC', 3: 'classD', 4: 'classE' };

  function ringsOf(g) {
    if (!g) return [];
    const swap = (r) => r.map((c) => [c[1], c[0]]);
    if (g.type === 'Polygon') return [{ outer: swap(g.coordinates[0]), holes: g.coordinates.slice(1).map(swap) }];
    if (g.type === 'MultiPolygon') return g.coordinates.map((p) => ({ outer: swap(p[0]), holes: p.slice(1).map(swap) }));
    return [];
  }

  /** A GeoJSON FeatureCollection, or an OpenAIP-style { items: [...] } or array, into zones. */
  function parseGeoJSON(json) {
    const feats = Array.isArray(json) ? json : json && json.features ? json.features : json && json.items ? json.items : [];
    const out = [];
    for (const f of feats) {
      const g = f.geometry;
      const p = f.properties || f;
      const polys = ringsOf(g);
      if (!polys.length) continue;
      let o;
      if (p.lowerLimit !== undefined || p.upperLimit !== undefined || p.icaoClass !== undefined) {
        o = {
          name: p.name || '',
          kind: OAIP_TYPES[p.type] || OAIP_CLASS[p.icaoClass] || 'other',
          cls: p.icaoClass !== undefined ? 'ABCDEFG'[p.icaoClass] || '' : '',
          lower: openAipAlt(p.lowerLimit) || { ft: 0, ref: 'AGL' },
          upper: openAipAlt(p.upperLimit) || { ft: 99999, ref: 'MSL' },
          src: 'OpenAIP',
        };
      } else {
        o = {
          name: p.NAME || p.NAME_TXT || p.name || p.IDENT_TXT || '',
          kind: p.kind && KINDS[p.kind] ? p.kind : faaKind(p),
          cls: String(p.CLASS || p.CLASS_CODE || ''),
          lower: p.lower_ft !== undefined ? { ft: Number(p.lower_ft), ref: 'MSL' } : faaAlt(p, 'LOWER'),
          upper: p.upper_ft !== undefined ? { ft: Number(p.upper_ft), ref: 'MSL' } : faaAlt(p, 'UPPER'),
          times: String(p.TIMESOFUSE || p.WORKHR_CODE || '').trim(),
          src: 'GeoJSON',
        };
      }
      for (const poly of polys) out.push(make(Object.assign({}, o, { rings: [poly.outer], holes: poly.holes })));
    }
    return out;
  }

  /** Text of a file, whichever of the formats it is. */
  function parse(text) {
    const s = String(text).trim();
    if (s[0] === '{' || s[0] === '[') {
      try {
        return parseGeoJSON(JSON.parse(s));
      } catch (e) {
        return [];
      }
    }
    return parseOpenAir(s);
  }

  /* ------------------------------------------------------------------ geometry */
  /** Flat metres east and north of an origin: good over the few hundred miles a zone is looked at across. */
  function local(origin, p) {
    let dLon = p[1] - origin[1];
    if (dLon > 180) dLon -= 360;
    if (dLon < -180) dLon += 360;
    const k = Math.cos(((origin[0] + p[0]) / 2) * RAD);
    return [dLon * geo.FT_PER_DEG * k, (p[0] - origin[0]) * geo.FT_PER_DEG];
  }

  function inRing(ring, lat, lon) {
    const o = [lat, lon];
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = local(o, ring[i]);
      const b = local(o, ring[j]);
      if (a[1] > 0 !== b[1] > 0 && 0 < ((b[0] - a[0]) * (0 - a[1])) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  }

  function segDist(ax, ay, bx, by) {
    const dx = bx - ax;
    const dy = by - ay;
    const l2 = dx * dx + dy * dy;
    const t = l2 ? Math.max(0, Math.min(1, (-ax * dx - ay * dy) / l2)) : 0;
    return Math.hypot(ax + t * dx, ay + t * dy);
  }

  function contains(z, lat, lon) {
    if (z.bbox && (lat < z.bbox[0] || lat > z.bbox[2] || lon < z.bbox[1] || lon > z.bbox[3])) return false;
    if (z.circle) return geo.course([z.circle.lat, z.circle.lon], [lat, lon]).ft <= z.circle.r_ft;
    return z.rings.some((r) => inRing(r, lat, lon)) && !z.holes.some((r) => inRing(r, lat, lon));
  }

  /** The distance (nmi) from a point to the zone's edge, and whether the point is inside. */
  function edge(z, lat, lon) {
    const inside = contains(z, lat, lon);
    if (z.circle) return { nm: Math.abs(geo.course([z.circle.lat, z.circle.lon], [lat, lon]).ft - z.circle.r_ft) / NM, inside };
    let best = Infinity;
    const o = [lat, lon];
    for (const ring of z.rings.concat(z.holes)) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const a = local(o, ring[i]);
        const b = local(o, ring[j]);
        best = Math.min(best, segDist(a[0], a[1], b[0], b[1]));
      }
    }
    return { nm: best / NM, inside };
  }

  /** Does the zone's height band meet [lo, hi] ft? An AGL limit is read as MSL. */
  const bandMeets = (z, lo, hi) => z.lower.ft <= hi && z.upper.ft >= lo;

  /** Is the zone one that matters at this height (± margin)? */
  const relevantAt = (z, alt_ft, margin) => bandMeets(z, alt_ft - (margin === undefined ? 1000 : margin), alt_ft + (margin === undefined ? 1000 : margin));

  /** A path of { lat, lon, alt_ft } points into samples every step nmi: { lat, lon, alt_ft, s_nm }. */
  function samples(path, step) {
    step = step || 2;
    const out = [];
    let s = 0;
    for (let i = 0; i < path.length; i++) {
      const a = path[i];
      if (i === 0) out.push({ lat: a.lat, lon: a.lon, alt_ft: a.alt_ft, s_nm: 0 });
      if (i + 1 >= path.length) break;
      const b = path[i + 1];
      const leg = geo.course([a.lat, a.lon], [b.lat, b.lon]).ft / NM;
      const n = Math.max(1, Math.ceil(leg / step));
      for (let k = 1; k <= n; k++) {
        const f = k / n;
        out.push({ lat: a.lat + (b.lat - a.lat) * f, lon: a.lon + (b.lon - a.lon) * f, alt_ft: a.alt_ft + (b.alt_ft - a.alt_ft) * f, s_nm: s + leg * f });
      }
      s += leg;
    }
    return out;
  }

  /**
   * One zone against a path's samples: where it is entered, left, and how near the path comes (in height and out).
   * { inside0, enter_nm, exit_nm, near_nm }
   */
  function along(z, smp, vmargin) {
    let inside0 = false;
    let enter = null;
    let exit = null;
    let near = Infinity;
    let was = false;
    const pad = 0.5;
    for (let i = 0; i < smp.length; i++) {
      const s = smp[i];
      if (z.bbox && (s.lat < z.bbox[0] - pad || s.lat > z.bbox[2] + pad || s.lon < z.bbox[1] - pad || s.lon > z.bbox[3] + pad)) {
        if (was && exit === null) exit = s.s_nm;
        was = false;
        continue;
      }
      if (!relevantAt(z, s.alt_ft, vmargin)) {
        if (was && exit === null) exit = s.s_nm;
        was = false;
        continue;
      }
      const e = edge(z, s.lat, s.lon);
      near = Math.min(near, e.inside ? 0 : e.nm);
      if (e.inside) {
        if (!was && enter === null) {
          enter = s.s_nm;
          if (i === 0) inside0 = true;
        }
        was = true;
      } else {
        if (was && exit === null) exit = s.s_nm;
        was = false;
      }
    }
    return { inside0, enter_nm: enter, exit_nm: exit, near_nm: near };
  }

  /* ------------------------------------------------------------------ advisories */
  const hundred = (v) => Math.round(v / 100) * 100;

  /** The words for a zone: its name, what it is, and its limits. */
  function describe(z) {
    const k = KINDS[z.kind] || KINDS.other;
    const agl = z.lower.ref === 'AGL' && z.lower.ft > 0 ? ' (an AGL limit read as MSL)' : '';
    return `${z.name || k.label} (${k.label}, ${fmtLimit(z.lower)} to ${fmtLimit(z.upper)}${agl})`;
  }

  /**
   * What the path does with the zones. path: [{ lat, lon, alt_ft }] (the aircraft first). opts: { ahead_nm: how far along the path
   * counts as "ahead" (20 minutes of flying), near_nm: how close counts as near (10), vmargin_ft, gs_kt }. Returns
   * [{ id, zone, kind, level, where: 'inside'|'ahead'|'plan'|'near', enter_nm, text, action }], the worst first.
   */
  function advisories(zones, path, opts) {
    opts = opts || {};
    const gs = opts.gs_kt || 0;
    const aheadNm = opts.ahead_nm || (gs > 50 ? gs / 3 : 60); // twenty minutes of flying, or 60 nmi when the speed is not known
    const nearNm = opts.near_nm === undefined ? 10 : opts.near_nm;
    const smp = samples(path, 2);
    const out = [];
    for (const z of zones) {
      const k = KINDS[z.kind] || KINDS.other;
      if (!k.drawn) continue;
      const r = along(z, smp, opts.vmargin_ft);
      let where = null;
      if (r.inside0) where = 'inside';
      else if (r.enter_nm !== null && r.enter_nm <= aheadNm) where = 'ahead';
      else if (r.enter_nm !== null) where = 'plan';
      else if (r.near_nm <= nearNm) where = 'near';
      if (!where) continue;
      const mins = gs > 50 && r.enter_nm ? Math.round((r.enter_nm / gs) * 60) : null;
      const route = !!opts.route; // looking at a plan, not at the aircraft: the words change, not the sums
      const when = where === 'inside' ? (route ? 'the route starts inside it' : 'the aircraft is inside it') : where === 'near' ? `the ${route ? 'route' : 'path'} passes ${r.near_nm.toFixed(0)} nmi off` : route ? `entered ${Math.round(r.enter_nm)} nmi along the route` : `entered ${Math.round(r.enter_nm)} nmi ahead${mins !== null ? `, in ${mins} min` : ''}${where === 'plan' ? ' on the plan' : ''}`;
      out.push({
        id: 'airspace-' + z.id,
        zone: z,
        kind: z.kind,
        level: where === 'near' ? 'advisory' : k.level,
        where,
        enter_nm: r.enter_nm === null ? 0 : r.enter_nm,
        text: `AIRSPACE: ${describe(z)}: ${when}`,
        action: `Check the clearance and the times of use (not read here)${k.level === 'caution' ? '; hold or change the plan if there is none' : ''}`,
      });
    }
    const rank = { caution: 0, advisory: 1 };
    const w = { inside: 0, ahead: 1, plan: 2, near: 3 };
    out.sort((a, b) => rank[a.level] - rank[b.level] || w[a.where] - w[b.where] || a.enter_nm - b.enter_nm);
    // a zone that comes in several parts (R-2508 has its sub-areas) is one advisory: the first, which is the nearest
    const seen = new Set();
    return out.filter((a) => {
      const key = `${a.zone.name}|${a.kind}|${a.where}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  /** The zones worth drawing at a height: the relevant ones whose kind is drawn. `all` draws every zone of a drawn kind whatever its height. */
  function visible(zones, alt_ft, all, kinds) {
    return zones.filter((z) => (kinds ? kinds[z.kind] !== false : KINDS[z.kind].drawn) && (all || relevantAt(z, alt_ft)));
  }

  /* ------------------------------------------------------------------ the FAA's open-data service */
  const FAA = 'https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/ArcGIS/rest/services';
  const FAA_LAYERS = ['Special_Use_Airspace', 'Class_Airspace', 'National_Defense_Airspace_TFR_Areas'];

  function faaUrl(layer, box, offset) {
    const q = {
      where: '1=1', geometry: `${box[1]},${box[0]},${box[3]},${box[2]}`, geometryType: 'esriGeometryEnvelope', inSR: '4326', spatialRel: 'esriSpatialRelIntersects',
      outFields: '*', returnGeometry: 'true', maxAllowableOffset: '0.004', geometryPrecision: '4', resultOffset: String(offset || 0), resultRecordCount: '1000', f: 'geojson',
    };
    return `${FAA}/${layer}/FeatureServer/0/query?` + Object.keys(q).map((k) => `${k}=${encodeURIComponent(q[k])}`).join('&');
  }

  /**
   * The zones of a box from the FAA's service. It shares a quota with everyone ("429, retry after 60 s"): that is not an
   * error, it is a wait, and it comes back as status. fetchFn: (url) => Promise<{ ok, status, json() }>.
   * Returns { zones, status, retryMs }.
   */
  async function loadFaa(fetchFn, box, layers) {
    const zones = [];
    let status = 'ok';
    let retryMs = 0;
    for (const layer of layers || FAA_LAYERS) {
      for (let offset = 0, page = 0; page < 6; page++) {
        let j;
        try {
          const r = await fetchFn(faaUrl(layer, box, offset));
          if (!r.ok) throw new Error('HTTP ' + r.status);
          j = await r.json();
        } catch (e) {
          status = 'failed: ' + e.message;
          retryMs = 60000;
          break;
        }
        if (j && j.error) {
          status = j.error.code === 429 ? 'the FAA service is busy (shared quota): asking again in 60 s' : 'the FAA service says: ' + (j.error.message || j.error.code);
          retryMs = 60000;
          break;
        }
        const got = parseGeoJSON(j);
        got.forEach((z) => {
          z.src = 'FAA ' + layer;
          if (layer === 'National_Defense_Airspace_TFR_Areas') z.kind = 'tfr';
        });
        zones.push(...got);
        const n = (j.features || []).length;
        if (!(j.exceededTransferLimit || (j.properties && j.properties.exceededTransferLimit)) || !n) break;
        offset += n;
      }
    }
    return { zones, status, retryMs };
  }

  const api = { KINDS, parseAlt, fmtLimit, make, parseOpenAir, parseGeoJSON, parse, contains, edge, bandMeets, relevantAt, samples, along, advisories, describe, visible, faaUrl, loadFaa, FAA_LAYERS, hundred };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).airspace = api;
})(typeof window !== 'undefined' ? window : globalThis);
