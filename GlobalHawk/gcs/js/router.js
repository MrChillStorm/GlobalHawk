/**
 * The route planner: the route of least fuel from where a route begins to the plan's landing fix, round what the map's layers say to
 * avoid, using the winds aloft. The method is this station's own (the real aircraft's DYNAMO is not public): it advises, it sends
 * nothing, and the aircraft still checks every plan.
 *
 *   - a lattice of latitude and longitude between start and goal, each point joined to its 16 nearest directions;
 *   - the cost of a join is the fuel for it at the cruise height: the level-flight flow of the station's table at the weight it would have
 *     there, times the time, which follows from the true airspeed and the wind along the join (one wind per lattice point, at the middle of
 *     the flight's hours); a join is cut where a sample every 4 nmi is in a hard-blocked place, and costs a quarter more in a soft zone;
 *   - Dijkstra's shortest path; the path thinned to where it turns, every kept chord checked again; a climb and a descent put in from the
 *     tables; each height in turn, and the cheapest whole plan kept.
 *
 * Hard-blocked: restricted, prohibited, danger and TFR areas whose heights reach the cruise height (1,000 ft of margin) and which do not
 * contain the start or the landing (the aircraft's own home airspace), with 2 nmi round them; turbulence and icing areas that reach the
 * height (NASA's rules 4 and 5); convective areas with 25 nmi round them at or below FL500, or where the tops are FL500 or more (rules 1
 * and 2a), and for tops below FL500 the tops plus 10,000 ft (rule 2b). Soft: MOAs, warning and alert areas. Nothing else is avoided: no
 * terrain, no radar echo, no traffic. A SIGMET area is the weather the station has, and a route round it is not a route round the weather.
 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const geo = node ? require('./geo.js') : root.GCS.geo;
  const A = node ? require('./airspace.js') : root.GCS.airspace;
  const FM = node ? require('./flightmath.js') : root.GCS.flightmath;
  const NM = geo.NM;
  const HARD_KINDS = ['restricted', 'prohibited', 'danger', 'tfr'];
  const SOFT_KINDS = ['moa', 'warning', 'alert'];
  const SOFT_FACTOR = 1.25;
  const ZONE_BUFFER_NM = 2;
  const CONVECTIVE_BUFFER_NM = 25;
  const BUFFERS = { zone: ZONE_BUFFER_NM, turb: 1.5, convective: CONVECTIVE_BUFFER_NM }; // turbulence and icing: the lattice's own tolerance (samples every 2 nmi, cells of 1.5)
  const CAUTIOUS_BUFFERS = { zone: 5, turb: 10, convective: 40 }; // assumed: the cautious route's room round things
  const REACH_FACTOR = 0.85; // of the aircraft's own glide radius: turns, wind, a worse glide than the book (mine)
  const ENTRY_NM = 5.3; // the entry point's distance from a site in the aircraft's planner
  const PREFER_PENALTY = 0.35; // extra cost of a join for the share of it out of reach of a landing site (mine)
  const NEAR_SITE_NM = 12; // within this of a site the aircraft is in its pattern: counted as in reach, whatever the height
  const SHORT_STRIP = 0.75; // the MV-22B finder's FORCED_RUN: a shorter strip that cannot hold the whole landing
  const HOME_RADIUS_NM = 10; // within this of the start and the landing nothing blocks: the aircraft has to get out of and into there
  const SAMPLE_NM = 4;
  const MAX_NODES = 6000;
  const ALTITUDES = [10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000, 55000, 60000, 65000]; // the heights tried when none is chosen: the ones the route is long enough to climb to and come down from are solved
  const MIN_GS_KT = 30;
  const JOIN_AT_FIX_DEG = 20; // a corner at the fix over this is moved out onto the final's extension: the aircraft is back on the line before the fix, and the height asked for over the fix counts no way for the turn; mine
  const JOIN_DEG = 90; // the corner the join onto the final may have (the aircraft's own limit is 120: this leaves room for wind); mine

  const distNm = (a, b) => geo.distance(a, b) / NM; // nmi in the tangent plane at a (WGS84, js/geo.js)
  // a number for each 1/40 degree cell (1.5 nmi): a Map keyed by numbers is several times quicker than one keyed by strings, and these are looked up half a million times
  const cellKey3 = (lat, lon) => (Math.round(lat * 20) + 1750) * 7250 + (Math.round(lon * 20) + 3625); // coverage changes slowly: 3 nmi cells
  const cellKey = (lat, lon) => (Math.round(lat * 40) + 3500) * 14500 + (Math.round(lon * 40) + 7250);

  /* ------------------------------------------------------------------ what is blocked */
  /**
   * The blocked places at one height. zones: airspace zones; hazards: weather hazards (js/weather.js); start, goal: [lat, lon];
   * opts: { now, hours (when the flight starts) }. blocker.at(lat, lon) => { hard: why | null, soft: bool }.
   */
  function blocker(zones, hazards, start, goal, alt_ft, opts) {
    opts = opts || {};
    const buf = Object.assign({}, BUFFERS, opts.buffers || {});
    const t0 = (opts.now || Date.now()) + (opts.hours || 0) * 3600000;
    const hard = [];
    const soft = [];
    for (const z of zones) {
      if (HARD_KINDS.includes(z.kind) && A.relevantAt(z, alt_ft, 1000)) {
        // the aircraft's own home airspace: a zone that holds the start or the landing cannot be avoided, and is not news
        if (A.contains(z, start[0], start[1]) || A.contains(z, goal[0], goal[1])) continue;
        hard.push({ z, buffer: buf.zone, why: `${z.name || A.KINDS[z.kind].label} (${A.KINDS[z.kind].label})` });
      } else if (SOFT_KINDS.includes(z.kind) && A.relevantAt(z, alt_ft, 0)) soft.push(z);
    }
    for (const h of hazards || []) {
      if (!['turb', 'ice', 'convective'].includes(h.kind) || (h.to && h.to < t0)) continue;
      let buffer = h.kind === 'convective' ? 0 : buf.turb;
      let lo = h.lo_ft;
      let hi = h.hi_ft;
      if (h.kind === 'convective') {
        if (alt_ft <= 50000 || h.hi_ft >= 50000) {
          buffer = buf.convective;
          lo = 0;
          hi = 99999;
        } else hi = h.hi_ft + 10000;
      }
      if (!(lo <= alt_ft && hi >= alt_ft)) continue;
      const z = A.make({ name: h.id, kind: 'other', rings: h.rings, lower: { ft: 0, ref: 'MSL' }, upper: { ft: 99999, ref: 'MSL' } });
      hard.push({ z, buffer, why: `${h.id} ${h.kind === 'convective' ? 'convection' : h.kind === 'turb' ? 'turbulence' : 'icing'}` });
    }
    const near = (z, lat, lon, nm, sc) => { // sc: geo.ftPerDeg(lat)
      const [kn, ke] = sc;
      const pad = (nm * NM) / kn + 0.01;
      const padLon = (pad * kn) / Math.max(0.2 * kn, ke); // a degree of longitude is never taken as less than a fifth of one of latitude
      return z.bbox && lat >= z.bbox[0] - pad && lat <= z.bbox[2] + pad && lon >= z.bbox[1] - padLon && lon <= z.bbox[3] + padLon;
    };
    const memo = new Map();
    const fStart = geo.prep(start);
    const fGoal = geo.prep(goal);
    return {
      hard,
      soft,
      at(lat, lon) {
        const key = cellKey(lat, lon);
        const m = memo.get(key);
        if (m) return m;
        let r = { hard: null, soft: false };
        const fp = geo.prep([lat, lon]);
        if (geo.distancePrep(fStart, fp) / NM <= HOME_RADIUS_NM || geo.distancePrep(fGoal, fp) / NM <= HOME_RADIUS_NM) r = { hard: null, soft: false };
        else {
          const sc = geo.ftPerDeg(lat);
          for (const b of hard) {
            if (!near(b.z, lat, lon, b.buffer, sc)) continue;
            if (A.contains(b.z, lat, lon) || (b.buffer > 0 && A.edge(b.z, lat, lon).nm <= b.buffer)) {
              r.hard = b.why;
              break;
            }
          }
          if (!r.hard) r.soft = soft.some((z) => near(z, lat, lon, 0, sc) && A.contains(z, lat, lon));
        }
        memo.set(key, r);
        return r;
      },
      /** The first hard-blocked place along a straight run, sampled every `step` nmi, or null. */
      along(a, b, step) {
        const n = Math.max(1, Math.ceil(distNm(a, b) / (step || SAMPLE_NM)));
        for (let k = 0; k <= n; k++) {
          const f = k / n;
          const r = this.at(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f);
          if (r.hard) return r.hard;
        }
        return null;
      },
    };
  }

  /* ------------------------------------------------------------------ emergency landing sites */
  /**
   * Which places have a landing site in glide reach at a height. sites: [{ lat, lon, elev_ft, name, tier }] (tier 1: a whole strip, 2: a shorter one);
   * glide(alt_ft, elev_ft) => nmi, still air, the aircraft's own planner's radius (js/reach.js); opts.short: count tier 2 as sites too.
   * A site is in reach when its distance plus the entry point's is at most REACH_FACTOR of that radius, or within NEAR_SITE_NM (its pattern). altSpec: the height, or a
   * function of the place (the height the aircraft will have there: low in the climb and the descent, not the cruise height).
   * cover.at(lat, lon) => the number of sites in reach; cover.names(lat, lon) => who.
   */
  function coverage(sites, glide, altSpec, opts) {
    opts = opts || {};
    const altAt = typeof altSpec === 'function' ? altSpec : () => altSpec;
    const top = opts.maxAlt !== undefined ? opts.maxAlt : typeof altSpec === 'function' ? 65000 : altSpec;
    const use = (sites || []).filter((x) => x.tier === 2 ? !!opts.short : true).sort((p, q) => p.lat - q.lat);
    const memo = new Map();
    const rmemo = new Map();
    // the radius for a site's height at a height: kept by 250 ft of height and 50 ft of elevation (the glide is a straight line in both)
    const radiusAt = (x, alt) => {
      const key = `${Math.round(alt / 250)}/${Math.round((x.elev_ft || 0) / 50)}`;
      let r = rmemo.get(key);
      if (r === undefined) {
        r = Math.max(NEAR_SITE_NM, REACH_FACTOR * glide(alt, x.elev_ft || 0) - ENTRY_NM);
        rmemo.set(key, r);
      }
      return r;
    };
    const rmax = use.length ? Math.max(...use.map((x) => radiusAt(x, top))) : 0;
    const lo = (lat) => { // first site whose latitude is not below lat
      let a = 0;
      let b = use.length;
      while (a < b) {
        const m = (a + b) >> 1;
        if (use[m].lat < lat) a = m + 1;
        else b = m;
      }
      return a;
    };
    const list = (lat, lon) => {
      const alt = altAt(lat, lon);
      const here = [lat, lon];
      const kn = geo.ftPerDeg(lat)[0] / NM; // nmi in a degree of latitude here
      const out = [];
      const band = (1.01 * rmax) / kn; // 1% over, for the plane's curvature and the scale's change over the radius
      for (let i = lo(lat - band); i < use.length && use[i].lat <= lat + band; i++) {
        const x = use[i];
        const r = radiusAt(x, alt);
        if (Math.abs(x.lat - lat) * kn > 1.01 * r) continue;
        if (distNm(here, [x.lat, x.lon]) <= r) out.push(x);
      }
      return out;
    };
    return {
      n: use.length,
      top,
      radius: (x, alt) => radiusAt(x, alt === undefined ? top : alt),
      names: list,
      at(lat, lon) {
        const key = cellKey3(lat, lon);
        let v = memo.get(key);
        if (v === undefined) {
          v = list(lat, lon).length;
          memo.set(key, v);
        }
        return v;
      },
    };
  }

  /**
   * What a route does with the sites: sampled every `step` nmi along [start, ...points], each sample at the height there (the
   * points' own heights, straight between them). Returns { share (of samples with a site in reach), longest_gap_nm, fewest, samples, gaps: [[a, b]] (lat/lon runs out of reach) }.
   */
  function coverageOf(path, sites, glide, opts) {
    opts = opts || {};
    const step = opts.step || 2;
    const pts = path.map((p) => ({ lat: p[0], lon: p[1], alt_ft: p[2] === undefined ? opts.alt_ft || 0 : p[2] }));
    const smp = A.samples(pts, step);
    // the heights: the forecast's own profile when it is given ([[ground distance ft, height ft, ...]]), else straight between the points'
    if (opts.profile && opts.profile.length > 1) {
      const pr = opts.profile;
      for (const q of smp) {
        const d = q.s_nm * NM;
        let i = 1;
        while (i < pr.length - 1 && pr[i][0] < d) i++;
        const f = pr[i][0] > pr[i - 1][0] ? Math.min(1, Math.max(0, (d - pr[i - 1][0]) / (pr[i][0] - pr[i - 1][0]))) : 0;
        q.alt_ft = pr[i - 1][1] + (pr[i][1] - pr[i - 1][1]) * f;
      }
    }
    const use = (sites || []).filter((x) => x.tier === 2 ? !!opts.short : true);
    let covered = 0;
    let gap = 0;
    let longest = 0;
    let fewest = Infinity;
    const gaps = [];
    let run = null;
    for (const q of smp) {
      let n = 0;
      for (const x of use) if (distNm([q.lat, q.lon], [x.lat, x.lon]) <= Math.max(NEAR_SITE_NM, REACH_FACTOR * glide(q.alt_ft, x.elev_ft || 0) - ENTRY_NM)) n++;
      fewest = Math.min(fewest, n);
      if (n > 0) {
        covered++;
        gap = 0;
        if (run) {
          gaps.push(run);
          run = null;
        }
      } else {
        gap += step;
        longest = Math.max(longest, gap);
        if (!run) run = [[q.lat, q.lon], [q.lat, q.lon]];
        else run[1] = [q.lat, q.lon];
      }
    }
    if (run) gaps.push(run);
    return { share: smp.length ? covered / smp.length : 1, longest_gap_nm: longest, fewest: Number.isFinite(fewest) ? fewest : 0, samples: smp.length, gaps, sites: use.length };
  }

  /* ------------------------------------------------------------------ the tables: climb and descent */
  /** The distance (nmi) over which the aircraft climbs from alt0 to alt1 at a weight, by 500 ft steps of the table: [{ d_nm, alt_ft }], ending where it tops out. */
  function climbProfile(fc, perf, alt0, alt1, weight, tail) {
    const out = [{ d_nm: 0, alt_ft: alt0 }];
    let a = alt0;
    let d = 0;
    let w = weight;
    while (a < alt1 - 1) {
      const step = Math.min(500, alt1 - a);
      const mid = a + step / 2;
      const rate = fc.look(perf.climb_fpm, mid, w);
      if (!(rate > 50)) break; // its ceiling for this weight
      const min = step / rate;
      d += (Math.max(fc.ktas(mid) + (tail || 0), MIN_GS_KT) * min) / 60;
      const flow = fc.look(perf.climb_pph, mid, w);
      w -= flow ? (flow * min) / 60 : 0;
      a += step;
      out.push({ d_nm: d, alt_ft: a });
    }
    out.fuel_lb = weight - w; // what the climb burns
    return out;
  }

  /** The distance (nmi) the descent from alt0 to alt1 takes, as [{ d_nm, alt_ft }] counted from the top. */
  function descentProfile(fc, perf, alt0, alt1, weight, tail) {
    const out = [{ d_nm: 0, alt_ft: alt0 }];
    let a = alt0;
    let d = 0;
    while (a > alt1 + 1) {
      const step = Math.min(1000, a - alt1);
      const mid = a - step / 2;
      const rate = Math.abs(fc.look(perf.descent_fpm, mid, weight)); // the table's descent rates are negative
      if (!(rate > 100)) return null;
      d += (Math.max(fc.ktas(mid) + (tail || 0), MIN_GS_KT) * (step / rate)) / 60;
      a -= step;
      out.push({ d_nm: d, alt_ft: a });
    }
    return out;
  }

  const interp = (prof, x, key) => {
    if (x <= prof[0].d_nm) return prof[0].alt_ft;
    for (let i = 1; i < prof.length; i++) if (x <= prof[i].d_nm) return prof[i - 1].alt_ft + ((prof[i].alt_ft - prof[i - 1].alt_ft) * (x - prof[i - 1].d_nm)) / (prof[i].d_nm - prof[i - 1].d_nm);
    return prof[prof.length - 1].alt_ft;
  };

  /* ------------------------------------------------------------------ the lattice */
  class Heap {
    constructor() {
      this.a = [];
    }

    push(k, v) {
      const a = this.a;
      a.push([k, v]);
      let i = a.length - 1;
      while (i > 0) {
        const p = (i - 1) >> 1;
        if (a[p][0] <= a[i][0]) break;
        [a[p], a[i]] = [a[i], a[p]];
        i = p;
      }
    }

    pop() {
      const a = this.a;
      const top = a[0];
      const last = a.pop();
      if (a.length) {
        a[0] = last;
        let i = 0;
        for (;;) {
          const l = 2 * i + 1;
          const r = l + 1;
          let m = i;
          if (l < a.length && a[l][0] < a[m][0]) m = l;
          if (r < a.length && a[r][0] < a[m][0]) m = r;
          if (m === i) break;
          [a[m], a[i]] = [a[i], a[m]];
          i = m;
        }
      }
      return top;
    }

    get size() {
      return this.a.length;
    }
  }

  const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1], [2, 1], [2, -1], [-2, 1], [-2, -1], [1, 2], [1, -2], [-1, 2], [-1, -2]];

  /**
   * One height: the least-fuel path on the lattice. o: { start, goal, alt_ft, weight_lb, fc, perf, wind (lat, lon, alt, hours) => { spd, dir } | null,
   * hours, blocker, stepDeg }. Returns { ok, points: [[lat, lon]], fuel_lb, time_h, soft, error }.
   */
  function solve(o) {
    const { start, goal, alt_ft, fc, perf } = o;
    const direct = distNm(start, goal);
    const lat0 = Math.min(start[0], goal[0]);
    const lat1 = Math.max(start[0], goal[0]);
    const lon0 = Math.min(start[1], goal[1]);
    const lon1 = Math.max(start[1], goal[1]);
    const [knMean, keMean] = geo.ftPerDeg((lat0 + lat1) / 2);
    const margin = Math.max(1.5, 0.35 * (Math.max(lat1 - lat0, ((lon1 - lon0) * keMean) / knMean) || 0)); // degrees of latitude
    const bLat0 = Math.max(-85, lat0 - margin);
    const bLat1 = Math.min(85, lat1 + margin);
    const midLat = (bLat0 + bLat1) / 2;
    const [knMid, keMid] = geo.ftPerDeg(midLat);
    const lonPerLat = Math.min(5, knMid / keMid); // degrees of longitude to as long as a degree of latitude at the lattice's middle (at most 5: the lattice does not go to the pole)
    const bLon0 = lon0 - margin * lonPerLat;
    const bLon1 = lon1 + margin * lonPerLat;
    let step = o.stepDeg || 0.25;
    for (;;) {
      const rows = Math.floor((bLat1 - bLat0) / step) + 1;
      const cols = Math.floor((bLon1 - bLon0) / (step * lonPerLat)) + 1;
      if (rows * cols <= MAX_NODES) break;
      step *= 1.15;
    }
    const stepLon = step * lonPerLat;
    const rows = Math.floor((bLat1 - bLat0) / step) + 1;
    const cols = Math.floor((bLon1 - bLon0) / stepLon) + 1;
    const N = rows * cols;
    const S = N;
    const G = N + 1;
    const pos = (k) => (k === S ? start : k === G ? goal : [bLat0 + Math.floor(k / cols) * step, bLon0 + (k % cols) * stepLon]);
    const hours = (o.hours || 0) + (direct / (fc.ktas(alt_ft) || 330)) / 2; // the wind at the middle of the flight's hours
    const windAt = new Map();
    const windOf = (k) => {
      if (!windAt.has(k)) {
        const p = pos(k);
        const w = o.wind ? o.wind(p[0], p[1], alt_ft, hours) : null;
        windAt.set(k, w && Number.isFinite(w.spd) && Number.isFinite(w.dir) ? w : null);
      }
      return windAt.get(k);
    };
    const tas = fc.ktas(alt_ft);
    const w0 = o.weight_lb;
    const byTime = o.objective === 'time';
    const mode = o.cover && o.siteMode ? o.siteMode : 'off';
    const radius = Math.max((3 * step * knMid) / NM, 30); // nmi round the start and the goal that join the lattice
    let flowFail = false;
    const comp = (w, course) => (w ? w.spd * Math.cos(((w.dir + 180 - course) * Math.PI) / 180) : 0);
    // a join between two places at a weight: { fuel, time_h, obj, soft } or null (blocked, or out of reach of every site when that is required).
    // tailOf(course) is the wind along it. obj is what is minimised: the fuel or the time, dearer in a soft zone and where no site is in reach.
    const join = (pa, pb, weight, tailOf, known) => {
      const run = known || geo.course(pa, pb);
      const dist = run.ft / NM;
      let softN = 0;
      let outN = 0;
      const n = Math.max(1, Math.ceil(dist / SAMPLE_NM));
      for (let k = 0; k <= n; k++) {
        const f = k / n;
        const la = pa[0] + (pb[0] - pa[0]) * f;
        const lo = pa[1] + (pb[1] - pa[1]) * f;
        const r = o.blocker.at(la, lo);
        if (r.hard) return null;
        if (r.soft) softN++;
        if (mode !== 'off' && o.cover.at(la, lo) === 0) {
          if (mode === 'require') return null;
          outN++;
        }
      }
      const course = run.deg;
      const gs = Math.max(tas + tailOf(course), MIN_GS_KT);
      const timeH = dist / gs;
      const flow = fc.look(perf.level_pph, alt_ft, weight);
      if (!(flow > 0)) {
        flowFail = true;
        return null;
      }
      const softFrac = softN / (n + 1);
      const outFrac = outN / (n + 1);
      const mult = (1 + (SOFT_FACTOR - 1) * softFrac) * (1 + PREFER_PENALTY * outFrac);
      const fuel = flow * timeH * (1 + (SOFT_FACTOR - 1) * softFrac);
      return { fuel, time_h: timeH, obj: (byTime ? timeH * (1 + (SOFT_FACTOR - 1) * softFrac) : flow * timeH * (1 + (SOFT_FACTOR - 1) * softFrac)) * (mode === 'prefer' ? 1 + PREFER_PENALTY * outFrac : 1), soft: softFrac * dist, mult };
    };
    const prepared = new Map(); // each lattice place's ECEF frame, made once: every join between two of them asks
    const prepOf = (k) => {
      let f = prepared.get(k);
      if (!f) prepared.set(k, (f = geo.prep(pos(k))));
      return f;
    };
    const cost = (a, b, weight) => join(pos(a), pos(b), weight, (course) => (comp(windOf(a), course) + comp(windOf(b), course)) / 2, geo.coursePrep(prepOf(a), prepOf(b)));
    // a straight run between any two places (the shortcut pass after the path is found): the wind at five places along it
    const chordCost = (pa, pb, weight) => join(pa, pb, weight, (course) => {
      if (!o.wind) return 0;
      let tail = 0;
      for (let k = 0; k < 5; k++) {
        const f = (k + 0.5) / 5;
        const w = o.wind(pa[0] + (pb[0] - pa[0]) * f, pa[1] + (pb[1] - pa[1]) * f, alt_ft, hours);
        if (w && Number.isFinite(w.spd) && Number.isFinite(w.dir)) tail += comp(w, course) / 5;
      }
      return tail;
    });
    const neighbours = (k) => {
      const out = [];
      if (k === S) {
        for (let m = 0; m < N; m++) if (distNm(start, pos(m)) <= radius) out.push(m);
        return out;
      }
      const i = Math.floor(k / cols);
      const j = k % cols;
      for (const [di, dj] of DIRS) {
        const ii = i + di;
        const jj = j + dj;
        if (ii >= 0 && ii < rows && jj >= 0 && jj < cols) out.push(ii * cols + jj);
      }
      if (distNm(pos(k), goal) <= radius) out.push(G);
      return out;
    };
    const g = new Map([[S, 0]]);
    const fuelUsed = new Map([[S, 0]]);
    const time = new Map([[S, 0]]);
    const soft = new Map([[S, 0]]);
    const prev = new Map();
    const done = new Set();
    const heap = new Heap();
    heap.push(0, S);
    // a start next to the goal: the straight join
    if (direct <= radius) {
      const c = cost(S, G, w0);
      if (c) return { ok: true, points: [start, goal], fuel_lb: c.fuel, time_h: c.time_h, soft_nm: c.soft, chordCost };
    }
    while (heap.size) {
      const [gk, k] = heap.pop();
      if (done.has(k)) continue;
      done.add(k);
      if (k === G) break;
      for (const m of neighbours(k)) {
        if (done.has(m)) continue;
        const c = cost(k, m, w0 - fuelUsed.get(k));
        if (!c) continue;
        const ng = gk + c.obj;
        if (!g.has(m) || ng < g.get(m) - 1e-9) {
          g.set(m, ng);
          fuelUsed.set(m, fuelUsed.get(k) + c.fuel);
          time.set(m, time.get(k) + c.time_h);
          soft.set(m, soft.get(k) + c.soft);
          prev.set(m, k);
          heap.push(ng, m);
        }
      }
    }
    if (!done.has(G)) {
      const why = [...new Set(o.blocker.hard.map((b) => b.why))].slice(0, 5);
      const noSite = mode === 'require';
      return { ok: false, error: flowFail ? 'the aircraft cannot hold this height at this weight' : noSite ? `no route keeps a landing site in glide reach all the way${why.length ? ' and round ' + why.join(', ') : ''}` : `no route round ${why.length ? why.join(', ') : 'the blocked areas'}`, blockedBy: why, required: noSite };
    }
    const nodes = [];
    for (let k = G; k !== undefined; k = prev.get(k)) nodes.push(k);
    nodes.reverse();
    return { ok: true, points: nodes.map(pos), fuel_lb: fuelUsed.get(G), time_h: time.get(G), soft_nm: soft.get(G), step_deg: step, nodes: N, chordCost };
  }

  /* ------------------------------------------------------------------ thinning */
  /** The distance (nmi) of p from the chord a-b, in the tangent plane at a. */
  function offChord(p, a, b) {
    const [by, bx] = geo.enu(a, b); // north, east: ft
    const [py, px] = geo.enu(a, p);
    const l2 = bx * bx + by * by;
    const t = l2 ? Math.max(0, Math.min(1, (px * bx + py * by) / l2)) : 0;
    return Math.hypot(px - t * bx, py - t * by) / NM;
  }

  /** Keep the points where the path turns: a chord replaces a stretch when it is free and the stretch is within tol nmi of it. */
  function thin(points, tol, free) {
    const keep = new Array(points.length).fill(false);
    keep[0] = keep[points.length - 1] = true;
    const rec = (i, j) => {
      if (j <= i + 1) return;
      let worst = -1;
      let wd = -1;
      for (let k = i + 1; k < j; k++) {
        const d = offChord(points[k], points[i], points[j]);
        if (d > wd) {
          wd = d;
          worst = k;
        }
      }
      if (wd <= tol && free(points[i], points[j])) return;
      const split = wd > tol ? worst : Math.floor((i + j) / 2);
      keep[split] = true;
      rec(i, split);
      rec(split, j);
    };
    rec(0, points.length - 1);
    return points.filter((_, i) => keep[i]);
  }

  /**
   * The corners a lattice leaves are cut where a straight run is free and costs no more than the stretch it replaces. points: the thinned path;
   * cost(a, b, weight) => { fuel } | null; free(a, b).
   */
  function shortcut(points, cost, free, weight) {
    const out = [points[0]];
    let i = 0;
    const seg = (a, b) => {
      const c = cost(points[a], points[b], weight);
      return c ? c.obj : Infinity;
    };
    while (i < points.length - 1) {
      let took = false;
      for (let j = points.length - 1; j >= i + 2; j--) {
        if (!free(points[i], points[j])) continue;
        const direct = seg(i, j);
        let along = 0;
        for (let k = i; k < j; k++) along += seg(k, k + 1);
        if (direct <= along * (1 + 1e-9)) {
          out.push(points[j]);
          i = j;
          took = true;
          break;
        }
      }
      if (!took) {
        out.push(points[i + 1]);
        i++;
      }
    }
    return out;
  }

  /* ------------------------------------------------------------------ the plan */
  const round6 = (x) => Math.round(x * 1e6) / 1e6;

  /** The point a distance (nmi) along a polyline. */
  function alongLine(line, nm) {
    let left = nm;
    for (let i = 0; i + 1 < line.length; i++) {
      const d = distNm(line[i], line[i + 1]);
      if (left <= d) {
        const f = d > 0 ? left / d : 0;
        return { p: [line[i][0] + (line[i + 1][0] - line[i][0]) * f, line[i][1] + (line[i + 1][1] - line[i][1]) * f], index: i };
      }
      left -= d;
    }
    return { p: line[line.length - 1], index: line.length - 2 };
  }

  /**
   * Turn a thinned path (start first, landing fix last) into route points with heights: the climb as the table allows, a top-of-descent point,
   * the descent to the fix. Returns [[lat, lon, alt_ft]] without the start.
   */

  /**
   * The join onto the final. The route's last leg meets the final's line at the fix; a corner there that the aircraft cannot fly well (a turn
   * over the limit in the capability file, or a leg too short for its lead) is avoided by a point on the final's extension, out from the fix,
   * that the last leg goes to, and when the route arrives from the far side of the line (the runway side of the fix) by a turning point beside it
   * first (a teardrop: out past the line, round, and onto it): [..., prev, T, J, fix] with J on the extension and T off it on the side the route
   * comes from. The search takes the join and the offset that keep the larger of the two corners smallest, each leg at least as long as the
   * turns at its ends need (the aircraft's own lead, from the capability file at the fix's height). Without an aiming point (o.aim) nothing is
   * changed. Returns { points, note }.
   */
  function joinFinal(points, o) {
    if (!o.aim || points.length < 2) return { points, note: null };
    const lim = FM.cap.turn.max_join_deg;
    const fix = points[points.length - 1];
    const prev = points[points.length - 2];
    const F = geo.course(fix, o.aim).deg;
    const vg = (o.fc ? o.fc.ktas(o.fix_alt_ft) : 200) * FM.KT;
    const lead = (delta) => FM.turn({ delta_deg: delta, alt_ft: o.fix_alt_ft, vg_fps: vg, weight_lb: o.weight_lb }).lead_ft;
    const turnAt = (a, b, c) => Math.abs(geo.turn(geo.course(a, b).deg, geo.course(b, c).deg));
    const fixTurn = turnAt(prev, fix, o.aim);
    if (fixTurn <= JOIN_AT_FIX_DEG && geo.course(prev, fix).ft >= lead(fixTurn)) return { points, note: null };
    const ext = (nm) => geo.along(fix, F + 180, nm * NM);
    // which side of the final's line the route comes from: right of it (looking down the final) is positive
    const side = Math.sin(((geo.course(fix, prev).deg - F) * Math.PI) / 180) >= 0 ? 1 : -1; // +1: on the right of the final's line, looking down it
    let best = null;
    const consider = (pts, corners) => {
      const worst = Math.max(...corners.map((c) => c.d));
      const ok = corners.every((c, i) => c.leg >= lead(c.d) + (i + 1 < corners.length ? lead(corners[i + 1].d) : 0));
      const score = worst + (ok ? 0 : 1000);
      if (!best || score < best.score - 1e-9) best = { score, pts, worst, ok };
    };
    for (let L = 4; L <= 40; L += 1) {
      const J = ext(L);
      consider([J], [{ d: turnAt(prev, J, fix), leg: geo.course(prev, J).ft }, { d: 0, leg: geo.course(J, fix).ft }]);
    }
    if (!best || best.worst > JOIN_DEG || !best.ok) {
      for (let L = 8; L <= 30; L += 2) {
        for (let D = 4; D <= 14; D += 2) {
          const J = ext(L);
          const T = geo.along(J, F + 90 * side, D * NM); // off the extension, on the side the route comes from
          consider([T, J], [{ d: turnAt(prev, T, J), leg: geo.course(prev, T).ft }, { d: turnAt(T, J, fix), leg: geo.course(T, J).ft }, { d: 0, leg: geo.course(J, fix).ft }]);
        }
      }
    }
    if (!best) return { points, note: null };
    const made = points.slice(0, -1).concat(best.pts.map((p) => [p[0], p[1]]), [fix]);
    const note = best.worst > lim ? `the route arrives ${Math.round(fixTurn)}° off the final and the best join still turns ${Math.round(best.worst)}°` : `joined onto the final by ${best.pts.length === 1 ? 'a point' : 'two points'} ${best.pts.length === 1 ? '' : 'a teardrop '}out on its extension (the corner at the fix was ${Math.round(fixTurn)}°)`;
    return { points: made, note, corner_deg: best.worst };
  }

  /**
   * The join after the takeoff. The aircraft arrives at the first leg on the takeoff's heading (o.start_hdg_deg). The first leg begins where it lifts off and has no
   * leg before it, so the corner at the takeoff's end is not flown with the lead and arc the turns between legs have: the aircraft sweeps off the line and takes
   * miles to be back on it (js/flightmath.js departureOffFt, from fdm/departure.py: a first point 90 deg off the heading is 6,300 ft off the line and 5.7 nmi to
   * settle; flown at 171 deg, a loop 1.3 nmi wide). So the first leg goes straight on, along the runway's extension to a point J, and the corners are J's and the
   * later ones, flown with the aircraft's own turns: J alone, J and a turning point T off the extension toward the first point, or J and two points that turn it
   * in three steps (a reversal: the corner limit is 120 deg and two corners of 90 deg are all a 180 deg reversal could have). The search takes the way that keeps
   * the largest corner smallest (corners under the join limit are equal: then the shortest), each leg at least as long as the turns at its ends need (the first
   * leg: the way to settle after its own corner, from the table). A first corner within what the table allows (the planner's limit off the line) and a long
   * enough leg is left alone, and without a heading (the aircraft is flying) nothing is changed.
   * Returns { points, note, corner_deg, added_nm }: points start first, the new ones between it and the first original point.
   */
  function joinDeparture(points, o) {
    const first0 = FM.departureMaxDeg();
    if (!Number.isFinite(o.start_hdg_deg) || points.length < 2 || first0 === null) return { points, note: null };
    const lim = JOIN_DEG;
    const H = o.start_hdg_deg;
    const start = points[0];
    const first = points[1];
    const next = points.length > 2 ? points[2] : null;
    // the leads are the aircraft's at the height the corner will be flown at, as plancheck.assess takes it: further out at the height the climb gives there
    // (o.climb_alt(nmi from the start) => ft, as withHeights gives the points their heights; without it, 5,000 ft over the start)
    const altAt = (nm) => Math.max(o.start_alt_ft || 0, Math.floor((o.climb_alt ? o.climb_alt(nm) : (o.start_alt_ft || 0) + 5000) / 100) * 100);
    const leadAt = (d, nm) => {
      const alt = altAt(nm);
      return FM.turn({ delta_deg: d, alt_ft: alt, vg_fps: (o.fc ? o.fc.ktas(alt) : 200) * FM.KT, weight_lb: o.weight_lb }).lead_ft;
    };
    const flown = (d) => d > 2.5;
    // the corners of a path [start, ...added, first, next]: the first from the heading, the rest between legs
    const corners = (pts) => {
      const d = [Math.abs(geo.turn(H, geo.course(pts[0], pts[1]).deg))];
      for (let k = 1; k + 1 < pts.length; k++) d.push(Math.abs(geo.turn(geo.course(pts[k - 1], pts[k]).deg, geo.course(pts[k], pts[k + 1]).deg)));
      return d;
    };
    // every leg long enough for what is done at its two ends: the first one settles after the takeoff's corner (the table), the others take their leads
    const check = (pts, d) => {
      let ok = true;
      let run = 0; // nmi along the path to pts[k]
      for (let k = 0; k + 1 < pts.length; k++) {
        const len = geo.course(pts[k], pts[k + 1]).ft;
        if (k + 1 >= d.length) break; // the last point's corner is not known
        const here = k === 0 ? FM.departureBackNm(d[0]) * NM : flown(d[k]) ? leadAt(d[k], run) : 0;
        const there = flown(d[k + 1]) ? leadAt(d[k + 1], run + len / NM) : 0;
        if (len < here + there) ok = false;
        run += len / NM;
      }
      return ok;
    };
    const whole = (added) => [start].concat(added, [first], next ? [next] : []);
    const lengthOf = (pts) => pts.slice(1).reduce((a, p, i) => a + geo.course(pts[i], p).ft, 0);
    const base = whole([]);
    const d0 = corners(base);
    if (d0[0] <= first0 + 0.5 && check(base, d0)) return { points, note: null };
    const side = Math.sin(((geo.course(start, first).deg - H) * Math.PI) / 180) >= 0 ? 1 : -1; // +1: the first point is on the right of the runway's line
    let best = null;
    const consider = (added) => {
      const pts = whole(added);
      const d = corners(pts);
      if (d[0] > first0 + 0.5) return; // the first leg goes straight on
      const w = Math.max(...d.slice(0, 1 + added.length + (next ? 1 : 0)));
      const ok = check(pts, d);
      const score = Math.max(w, lim + 0.5) + (ok ? 0 : 1000) + (0.001 * lengthOf(pts)) / NM;
      if (!best || score < best.score - 1e-9) best = { score, added, worst: w, ok, extra_nm: (lengthOf(pts) - lengthOf(base)) / NM };
    };
    for (let L = 3; L <= 40; L += 1) consider([geo.along(start, H, L * NM)]);
    for (let L = 3; L <= 24; L += 3) {
      const J = geo.along(start, H, L * NM);
      for (let A = 60; A <= 105; A += 15) for (let D = 4; D <= 20; D += 2) consider([J, geo.along(J, H + A * side, D * NM)]);
      // a turn in three steps (reversals): two legs each turning on by the step
      for (let phi = 45; phi <= 75; phi += 15) {
        for (let D = 3; D <= 14; D += 1) {
          const P2 = geo.along(J, H + phi * side, D * NM);
          consider([J, P2, geo.along(P2, H + 2 * phi * side, D * NM)]);
        }
      }
    }
    if (!best) return { points, note: null };
    const made = [start].concat(best.added.map((p) => [p[0], p[1]]), points.slice(1));
    const reported = d0[0];
    const note = best.worst > lim + 0.5
      ? `the first point is ${Math.round(reported)}° off the takeoff's heading and the best departure still turns ${Math.round(best.worst)}°`
      : `a departure of ${best.added.length === 1 ? 'one point' : best.added.length + ' points'} for a first point ${Math.round(reported)}° off the takeoff's heading (the largest corner ${Math.round(best.worst)}°, ${best.extra_nm.toFixed(1)} nmi more)`;
    return { points: made, note, corner_deg: best.worst, added_nm: best.extra_nm };
  }

  function withHeights(path, cruise, fixAlt, climb, descent, margin) {
    const mk_ = margin || { k: 1.05, extra: 3 };
    const total = path.slice(1).reduce((s, p, i) => s + distNm(path[i], p), 0);
    const pts = path.slice();
    // the top of the descent: on the path, as far before the fix as the descent needs (and 5 % over, and 3 nmi)
    const dTod = descent ? descent[descent.length - 1].d_nm * mk_.k + mk_.extra : 0;
    let tod = null;
    if (dTod > 0 && dTod < total) {
      const a = alongLine(pts.slice().reverse(), dTod); // along the path from the fix back
      tod = a.p;
      const idx = pts.length - 2 - a.index; // the segment (idx, idx + 1) holds it
      pts.splice(idx + 1, 0, tod);
    }
    let run = 0;
    const out = [];
    for (let i = 1; i < pts.length; i++) {
      run += distNm(pts[i - 1], pts[i]);
      const toFix = total - run;
      let alt = Math.min(cruise, interp(climb, run));
      // the height the descent allows this far from the fix: counted down from the top of the descent
      if (descent) alt = Math.min(alt, interp(descent, Math.max(0, dTod - toFix)));
      if (i === pts.length - 1) alt = fixAlt;
      out.push([round6(pts[i][0]), round6(pts[i][1]), Math.max(fixAlt, Math.floor(alt / 100) * 100)]);
    }
    return { points: out, total_nm: total, tod: !!tod };
  }

  /** The least distance (nmi) from a zone to a straight line a-b, sampled every 10 nmi (0 when the line goes through it). */
  function zoneToLine(z, a, b) {
    const n = Math.max(2, Math.ceil(distNm(a, b) / 10));
    let best = Infinity;
    for (let k = 0; k <= n; k++) {
      const f = k / n;
      const la = a[0] + (b[0] - a[0]) * f;
      const lo = a[1] + (b[1] - a[1]) * f;
      best = Math.min(best, A.contains(z, la, lo) ? 0 : A.edge(z, la, lo).nm);
      if (best === 0) break;
    }
    return best;
  }

  /**
   * The whole job for one way of choosing. o: { start, start_alt_ft, goal (the landing fix), fix_alt_ft, weight_lb, fuel_lb, fc (predict.make's), perf,
   * wind, hours, zones, hazards, now, altitudes, stepDeg, legsFor(points) => legs for fc.predict (from plancheck),
   * and for the emergency sites: sites [{ lat, lon, elev_ft, name, tier }], glide(alt_ft, elev_ft) => nmi, siteMode 'off' | 'prefer' | 'require', shortStrips;
   * objective 'fuel' (the default) or 'time'; buffers (the room round things) }.
   * Returns { ok, best: { alt_ft, points, fuel_lb, time_s, dist_nm, coverage, warnings }, options: [...], direct, notes } or { ok: false, error }.
   */
  function plan(o) {
    const fc = o.fc;
    const perf = o.perf;
    const notes = [];
    const altitudes = (o.altitudes && o.altitudes.length ? o.altitudes : ALTITUDES).slice();
    const direct = distNm(o.start, o.goal);
    if (direct < 5) return { ok: false, error: 'the start and the landing fix are less than 5 nmi apart: there is nothing to plan' };
    const mode = o.sites && o.glide && o.siteMode ? o.siteMode : 'off';
    const byTime = o.objective === 'time';
    const state = { alt_ft: o.start_alt_ft, weight_lb: o.weight_lb, fuel_lb: o.fuel_lb };
    const options = [];
    const errors = [];
    let required = false;
    const bearing = geo.course(o.start, o.goal).deg;
    // the wind along the route's course where the climb and the descent happen (at the middle of each, at its height): their distances change with it
    const tailNear = (p, alt) => {
      const w = o.wind ? o.wind(p[0], p[1], alt, o.hours || 0) : null;
      return w && Number.isFinite(w.spd) && Number.isFinite(w.dir) ? w.spd * Math.cos(((w.dir + 180 - bearing) * Math.PI) / 180) : 0;
    };
    const attempt = (alt, useCover, quiet) => {
      const bl = blocker(o.zones || [], o.hazards || [], o.start, o.goal, alt, { now: o.now, hours: o.hours, buffers: o.buffers });
      const tailUp = tailNear(o.start, (o.start_alt_ft + alt) / 2);
      const tailDown = tailNear(o.goal, (alt + o.fix_alt_ft) / 2);
      const climb = climbProfile(fc, perf, o.start_alt_ft, alt, o.weight_lb, tailUp);
      const reach = climb[climb.length - 1].alt_ft;
      if (reach < alt - 500) {
        if (!quiet) errors.push(`${alt} ft: it climbs only to ${Math.round(reach / 100) * 100} ft at this weight`);
        return null;
      }
      const cruiseWeight = o.weight_lb - climb.fuel_lb;
      // a first look at the descent, at a weight a little below the start's, to see whether the climb and the descent fit in the route at all
      const first = descentProfile(fc, perf, alt, o.fix_alt_ft, cruiseWeight - 0.1 * o.fuel_lb, tailDown);
      if (!first) {
        if (!quiet) errors.push(`${alt} ft: no descent from there in the table`);
        return null;
      }
      const need = climb[climb.length - 1].d_nm + first[first.length - 1].d_nm * 1.05 + 3;
      // the height the aircraft has at a place (never more than the climb allows this far from the start, or the descent this far from the fix): sites are judged at that
      const dTod0 = first[first.length - 1].d_nm * 1.05 + 3;
      const fStart = geo.prep(o.start);
      const fGoal = geo.prep(o.goal);
      // nmi in the tangent plane at the start and at the goal: good over a route's length for a height that changes this slowly
      const altFn = (la, lo) => {
        const fp = geo.prep([la, lo]);
        return Math.min(alt, interp(climb, geo.distancePrep(fStart, fp) / NM), interp(first, Math.max(0, dTod0 - geo.distancePrep(fGoal, fp) / NM)));
      };
      const cover = useCover && mode !== 'off' ? coverage(o.sites, o.glide, altFn, { short: o.shortStrips, maxAlt: alt }) : null;
      if (need > direct * 1.02) {
        if (!quiet) errors.push(`${alt} ft: the climb and the descent take ${Math.round(need)} nmi and the route is ${Math.round(direct)} nmi`);
        return null;
      }
      const s = solve({ start: o.start, goal: o.goal, alt_ft: alt, weight_lb: cruiseWeight, fc, perf, wind: o.wind, hours: o.hours, blocker: bl, stepDeg: o.stepDeg, cover, siteMode: cover ? mode : 'off', objective: o.objective });
      if (!s.ok) {
        if (!quiet) errors.push(`${alt} ft: ${s.error}`);
        if (s.required && !quiet) required = true;
        return null;
      }
      const free = (a, b) => !bl.along(a, b, 2) && (!cover || mode !== 'require' || sampleCovered(cover, a, b));
      const thinned0 = shortcut(thin(s.points, 3, free), s.chordCost, free, cruiseWeight);
      const joinedF = joinFinal(thinned0, o);
      const departed = joinDeparture(joinedF.points, Object.assign({}, o, { climb_alt: (nm) => Math.min(alt, interp(climb, nm)) }));
      const joined = { points: departed.points, note: [joinedF.note, departed.note].filter(Boolean).join('; ') || null };
      const thinned = joined.points;
      // the descent at the weight it will really have, and with the wind where the path really goes: its tail at the middle of the descent and of the climb
      const rough = descentProfile(fc, perf, alt, o.fix_alt_ft, cruiseWeight - s.fuel_lb, tailDown);
      if (!rough) {
        if (!quiet) errors.push(`${alt} ft: no descent from there in the table`);
        return null;
      }
      const tailOn = (fromStart, nm, a) => {
        const l = fromStart ? thinned : thinned.slice().reverse();
        const q = alongLine(l, nm);
        const seg = [l[q.index], l[q.index + 1]];
        const course = geo.course(seg[0], seg[1]).deg * (fromStart ? 1 : 1);
        const w = o.wind ? o.wind(q.p[0], q.p[1], a, o.hours || 0) : null;
        const c = fromStart ? course : (course + 180) % 360; // the aircraft flies toward the fix
        return w && Number.isFinite(w.spd) && Number.isFinite(w.dir) ? w.spd * Math.cos(((w.dir + 180 - c) * Math.PI) / 180) : 0;
      };
      const descent = descentProfile(fc, perf, alt, o.fix_alt_ft, cruiseWeight - s.fuel_lb, tailOn(false, rough[rough.length - 1].d_nm / 2, (alt + o.fix_alt_ft) / 2));
      const climbReal = climbProfile(fc, perf, o.start_alt_ft, alt, o.weight_lb, tailOn(true, climb[climb.length - 1].d_nm / 2, (o.start_alt_ft + alt) / 2));
      // the heights are the tables' own, in still air near enough; the forecast, which has the wind, says what is reached: points that are not reached are given the height the
      // aircraft does reach there, and if the fix itself is not reached the top of the descent moves back (up to three times)
      let h;
      let f;
      // the departure's points are corners the aircraft turns while it is climbing, and it climbs faster than the table: given the height the table says there, it levels off in the
      // middle of the turn and the turn goes 560 ft past its line (flown, docs/PLAN.md, "The turn after takeoff"; 54 ft with the climb going on through it). So they carry the first
      // route point's height, the climb goes on through them, and "not reached" is not said of them: the aircraft is on its way up there
      const nDep = departed.points.length - joinedF.points.length;
      const climbThrough = () => { for (let i = 0; i < nDep; i++) h.points[i][2] = h.points[nDep][2]; };
      for (let tries = 0, mg = { k: 1.05, extra: 3 }; tries < 4; tries++, mg = { k: mg.k + 0.15, extra: mg.extra + 6 }) {
        h = withHeights(thinned, alt, o.fix_alt_ft, climbReal, descent, mg);
        climbThrough();
        f = fc.predict(o.legsFor(h.points), state, { wind: o.wind, hours: o.hours });
        let changed = false;
        h.points.forEach((p, i) => {
          const pt = f.points[i];
          if (!pt || pt.reached || i === h.points.length - 1 || i < nDep) return;
          const prev = i ? h.points[i - 1][2] : o.start_alt_ft;
          const set = p[2] < prev ? Math.ceil(pt.alt_ft / 100) * 100 : Math.floor(pt.alt_ft / 100) * 100;
          if (set !== p[2]) {
            p[2] = set;
            changed = true;
          }
        });
        if (changed) {
          climbThrough();
          f = fc.predict(o.legsFor(h.points), state, { wind: o.wind, hours: o.hours });
        }
        f.warnings = f.warnings.filter((w) => !(nDep && /^point (\d+): .* is not reached by then/.test(w) && Number(/^point (\d+)/.exec(w)[1]) <= nDep));
        if (!f.warnings.some((w) => /not reached/.test(w))) break;
      }
      const cov = mode !== 'off' && useCover ? coverageOf([[o.start[0], o.start[1], o.start_alt_ft]].concat(h.points), o.sites, o.glide, { short: o.shortStrips, profile: f.profile }) : null;
      return { alt_ft: alt, join: joined.note, departure_points: departed.points.length - joinedF.points.length, points: h.points, fuel_lb: f.total.fuel_used_lb, time_s: f.total.t_s, dist_nm: f.total.dist_ft / NM, warnings: f.warnings, soft_nm: s.soft_nm, path_nm: h.total_nm, step_deg: s.step_deg, nodes: s.nodes, tod: h.tod, blockers: bl.hard.length, coverage: cov, quick: !useCover };
    };
    // with sites in mind each height costs about four times as much: so the heights are ranked first without them (cheap), and only the best of them are solved with them
    // (more of them while Require finds none: it needs the heights where the glide is long)
    const key0 = (p) => (byTime ? p.time_s : p.fuel_lb);
    if (mode !== 'off' && altitudes.length > 3) {
      const quick = altitudes.map((a) => attempt(a, false, false)).filter(Boolean).sort((p, q) => key0(p) - key0(q));
      let made = 0;
      for (const qk of quick) {
        const full = attempt(qk.alt_ft, true, made > 0);
        if (full) {
          options.push(full);
          made++;
        }
        if (made >= 3) break;
      }
    } else {
      for (const alt of altitudes) {
        const op = attempt(alt, true, false);
        if (op) options.push(op);
      }
    }
    if (!options.length) {
      let error = errors.length ? errors.join('; ') : 'no height could be flown';
      let directGap = null;
      if (required && o.sites) {
        // how long the direct route's stretch without a site is: what the operator is told, with the way out
        directGap = coverageOf([[o.start[0], o.start[1], 45000], [o.goal[0], o.goal[1], 45000]], o.sites, o.glide, { short: o.shortStrips }).longest_gap_nm;
        error = `no route keeps a landing site in glide reach all the way (the direct route has ${Math.round(directGap)} nmi without one): switch emergency sites to Prefer, or Off`;
      }
      return { ok: false, error, errors, required, direct_gap_nm: directGap };
    }
    const clean = options.filter((p) => !p.warnings.some((w) => /not reached|runs out/.test(w)));
    const pool = clean.length ? clean : options;
    // the cheapest, or for the cautious variant (pickByCover) the cheapest counting the share out of reach of a site as the lattice does
    const key = (p) => (byTime ? p.time_s : p.fuel_lb) * (o.pickByCover && mode === 'prefer' && p.coverage ? 1 + PREFER_PENALTY * (1 - p.coverage.share) : 1);
    const best = pool.reduce((a, b) => (key(b) < key(a) - 1e-6 ? b : a));
    if (!clean.length) notes.push('the forecast says the heights are not all reached on this route: see its warnings');
    // the direct route at the same height, for the comparison: what it would burn, and what it would cross
    const bl = blocker(o.zones || [], o.hazards || [], o.start, o.goal, best.alt_ft, { now: o.now, hours: o.hours, buffers: o.buffers });
    const climb = climbProfile(fc, perf, o.start_alt_ft, best.alt_ft, o.weight_lb, tailNear(o.start, (o.start_alt_ft + best.alt_ft) / 2));
    const descent = descentProfile(fc, perf, best.alt_ft, o.fix_alt_ft, o.weight_lb - best.fuel_lb, tailNear(o.goal, (best.alt_ft + o.fix_alt_ft) / 2));
    const dh = withHeights([o.start, o.goal], best.alt_ft, o.fix_alt_ft, climb, descent);
    const df = fc.predict(o.legsFor(dh.points), state, { wind: o.wind, hours: o.hours });
    const crosses = bl.along(o.start, o.goal, 2);
    const directCov = mode !== 'off' ? coverageOf([[o.start[0], o.start[1], o.start_alt_ft]].concat(dh.points), o.sites, o.glide, { short: o.shortStrips, profile: df.profile }) : null;
    const direct_ = { alt_ft: best.alt_ft, points: dh.points, fuel_lb: df.total.fuel_used_lb, time_s: df.total.t_s, dist_nm: df.total.dist_ft / NM, blocked_by: crosses, coverage: directCov, warnings: df.warnings };
    // what the route goes round: the hard-blocked things near the direct line
    const avoids = [...new Set(bl.hard.filter((b) => zoneToLine(b.z, o.start, o.goal) <= 60).map((b) => b.why))].slice(0, 6);
    return { ok: true, best: Object.assign(best, { avoids }), options, direct: direct_, notes, errors, mode };
  }

  /** Is every sampled place of the straight run a-b in reach of a site? (for the thinning under Require) */
  function sampleCovered(cover, a, b) {
    if (!cover) return true;
    const n = Math.max(1, Math.ceil(distNm(a, b) / 2));
    for (let k = 0; k <= n; k++) {
      const f = k / n;
      if (cover.at(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f) === 0) return false;
    }
    return true;
  }

  /** Are two routes practically one: every point of each within `nm` of the other's line, at the same height? */
  function similar(a, b, nm) {
    if (a.alt_ft !== b.alt_ft) return false;
    const line = (r) => [r.start].concat(r.points.map((p) => [p[0], p[1]]));
    const near = (p, line_) => {
      let best = Infinity;
      for (let i = 0; i + 1 < line_.length; i++) best = Math.min(best, offChordSeg(p, line_[i], line_[i + 1]));
      return best;
    };
    const la = line(a);
    const lb = line(b);
    return la.every((p) => near(p, lb) <= nm) && lb.every((p) => near(p, la) <= nm);
  }

  /** The distance (nmi) of p from the segment a-b (offChord clamps to the segment). */
  const offChordSeg = (p, a, b) => offChord(p, a, b);

  /**
   * Several routes, each for what it is for: Least fuel, Fastest, Cautious (emergency sites required where they can be, more room round hazards), and the Direct
   * route to compare with. o is plan()'s, with the operator's siteMode. Two that are practically one route are one card with both names.
   * Returns { ok, routes: [{ id, names, alt_ft, points, fuel_lb, time_s, dist_nm, coverage, avoids, blocked_by, warnings, vs_fuel: { time_s, fuel_lb, dist_nm } }], notes, errors }.
   */
  const VARIANTS = (o, mode) => [
    ['fuel', 'Least fuel', { objective: 'fuel' }],
    ['time', 'Fastest', { objective: 'time' }],
    ['safe', 'Cautious', { objective: 'fuel', buffers: CAUTIOUS_BUFFERS, siteMode: mode === 'off' ? 'off' : 'require', pickByCover: true }],
  ];

  /** One way of choosing, run: { id, name, r } or null (its error goes to ctx.errors). Cautious falls back to Prefer when Require finds nothing, and says so. */
  function runVariant(o, v, ctx) {
    const [id, name, over] = v;
    let r = plan(Object.assign({}, o, over));
    if (!r.ok && id === 'safe' && r.required) {
      ctx.notes.push('Cautious: no route keeps a landing site in reach all the way; the cautious route prefers one and keeps the wider room round hazards');
      r = plan(Object.assign({}, o, over, { siteMode: 'prefer' }));
    }
    if (!r.ok) {
      ctx.errors.push(`${name}: ${r.error}`);
      return null;
    }
    return { id, name, r };
  }

  /** The cards, from the variants that were run. */
  function assemble(o, results, ctx) {
    if (!results.length) return { ok: false, error: ctx.errors.join('; '), errors: ctx.errors };
    const direct = results[0].r.direct;
    // Least fuel and Fastest are each the best of every route either search found (the two searches differ by a lattice's noise, and the ordering must hold)
    const pooled = [];
    for (const x of results) if (x.id === 'fuel' || x.id === 'time') pooled.push(...x.r.options);
    const cleanPool = pooled.filter((p) => !p.warnings.some((w) => /not reached|runs out/.test(w)));
    const best = (key) => (cleanPool.length ? cleanPool : pooled).reduce((a, b) => (b[key] < a[key] - 1e-6 ? b : a));
    for (const x of results) {
      if (x.id === 'fuel' && pooled.length) x.r.best = Object.assign({}, best('fuel_lb'), { avoids: x.r.best.avoids });
      if (x.id === 'time' && pooled.length) x.r.best = Object.assign({}, best('time_s'), { avoids: x.r.best.avoids });
    }
    const routes = [];
    for (const { id, name, r } of results) {
      const b = r.best;
      const card = { id, names: [name], start: o.start, alt_ft: b.alt_ft, points: b.points, fuel_lb: b.fuel_lb, time_s: b.time_s, dist_nm: b.dist_nm, coverage: b.coverage, avoids: b.avoids, warnings: b.warnings, mode: r.mode };
      const twin = routes.find((c) => similar(c, card, 5));
      if (twin) twin.names.push(name);
      else routes.push(card);
    }
    const first = routes[0];
    for (const c of routes) c.vs_fuel = { time_s: c.time_s - first.time_s, fuel_lb: c.fuel_lb - first.fuel_lb, dist_nm: c.dist_nm - first.dist_nm };
    routes.push({ id: 'direct', names: ['Direct'], start: o.start, alt_ft: direct.alt_ft, points: direct.points, fuel_lb: direct.fuel_lb, time_s: direct.time_s, dist_nm: direct.dist_nm, coverage: direct.coverage, avoids: [], blocked_by: direct.blocked_by, warnings: direct.warnings, direct: true, vs_fuel: { time_s: direct.time_s - first.time_s, fuel_lb: direct.fuel_lb - first.fuel_lb, dist_nm: direct.dist_nm - first.dist_nm } });
    return { ok: true, routes, notes: ctx.notes, errors: ctx.errors };
  }

  /**
   * Several routes, each for what it is for: Least fuel, Fastest, Cautious (emergency sites required where they can be, more room round hazards), and the Direct
   * route to compare with. o is plan()'s, with the operator's siteMode. Two that are practically one route are one card with both names.
   * Returns { ok, routes: [{ id, names, alt_ft, points, fuel_lb, time_s, dist_nm, coverage, avoids, blocked_by, warnings, vs_fuel: { time_s, fuel_lb, dist_nm } }], notes, errors }.
   */
  function alternatives(o) {
    const mode = o.sites && o.glide && o.siteMode ? o.siteMode : 'off';
    const ctx = { notes: [], errors: [] };
    const results = [];
    for (const v of VARIANTS(o, mode)) {
      const x = runVariant(o, v, ctx);
      if (x) results.push(x);
    }
    return assemble(o, results, ctx);
  }

  /** The same, letting the page breathe between the ways of choosing (each takes a few seconds with real data); onStep(name) says which is next. */
  async function alternativesAsync(o, onStep) {
    const mode = o.sites && o.glide && o.siteMode ? o.siteMode : 'off';
    const ctx = { notes: [], errors: [] };
    const results = [];
    for (const v of VARIANTS(o, mode)) {
      if (onStep) onStep(v[1]);
      await new Promise((r) => setTimeout(r, 30));
      const x = runVariant(o, v, ctx);
      if (x) results.push(x);
    }
    return assemble(o, results, ctx);
  }

  const api = { joinFinal, joinDeparture, blocker, coverage, coverageOf, climbProfile, descentProfile, solve, thin, shortcut, withHeights, plan, alternatives, alternativesAsync, similar, offChord, REACH_FACTOR, ENTRY_NM, NEAR_SITE_NM, PREFER_PENALTY, SHORT_STRIP, CAUTIOUS_BUFFERS, ALTITUDES, HARD_KINDS, SOFT_KINDS, ZONE_BUFFER_NM, CONVECTIVE_BUFFER_NM, HOME_RADIUS_NM };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).router = api;
})(typeof window !== 'undefined' ? window : globalThis);
