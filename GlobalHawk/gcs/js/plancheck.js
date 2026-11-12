/**
 * The aircraft's plan check (fdm/onboard.py: check_plan), ported, so that a fault shows in the station before a
 * plan is sent. The aircraft still decides: this only saves a round trip. The two are run against each other on
 * damaged plans in fdm/phase8c_checks.py. Also: turning a plan's items into the legs the forecast takes.
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const KINDS = ['taxi', 'takeoff', 'route', 'land', 'hold'];
  const MAX_ALT = 65000;
  const MAX_LEG_NM = 3000;
  const MIN_FINAL_NM = 8;
  const num = (x) => typeof x === 'number' && Number.isFinite(x);
  const g = (x) => String(Number(Number(x).toPrecision(6))); // as Python's %g prints

  function point(p, n, what) {
    if (!(Array.isArray(p) && p.length === n && p.every(num))) return `${what}: a point needs ${n} numbers`;
    if (!(p[0] >= -90 && p[0] <= 90)) return `${what}: latitude ${g(p[0])} is not on the earth`;
    if (!(p[1] >= -180 && p[1] <= 180)) return `${what}: longitude ${g(p[1])} is not on the earth`;
    if (n === 3 && !(p[2] >= 0 && p[2] <= MAX_ALT)) return `${what}: height ${g(p[2])} ft is outside 0 to ${MAX_ALT} ft`;
    return null;
  }

  function checkItems(items, what) {
    if (!Array.isArray(items) || !items.length) return `${what}: no items`;
    for (let n = 0; n < items.length; n++) {
      const it = items[n];
      const isItem = it && typeof it === 'object' && !Array.isArray(it);
      if (!isItem || !KINDS.includes(it.kind)) return `${what} item ${n + 1}: unknown kind ${JSON.stringify(isItem ? (it.kind === undefined ? null : it.kind) : it)}`;
    }
    for (let n = 0; n < items.length; n++) {
      const it = items[n];
      const w = `${what} item ${n + 1}`;
      const kind = it.kind;
      if (kind === 'taxi' || kind === 'route') {
        const pts = it.points;
        if (!Array.isArray(pts) || !pts.length) return `${w} (${kind}): no points`;
        for (let m = 0; m < pts.length; m++) {
          const bad = point(pts[m], kind === 'route' ? 3 : 2, `${w} (${kind}) point ${m + 1}`);
          if (bad) return bad;
        }
        for (let m = 0; m + 1 < pts.length; m++) if (geo.course(pts[m], pts[m + 1]).ft / geo.NM > MAX_LEG_NM) return `${w} (${kind}): a leg longer than ${MAX_LEG_NM} nmi`;
      } else if (kind === 'takeoff') {
        const bad = point(it.start, 2, `${w} (takeoff) start`) || point(it.end, 2, `${w} (takeoff) end`);
        if (bad) return bad;
        if (n + 1 >= items.length || items[n + 1].kind !== 'route') return `${w}: a takeoff must be followed by a route`;
      } else if (kind === 'land') {
        const bad = point(it.fix, 2, `${w} (land) fix`) || point(it.aim, 2, `${w} (land) aim`);
        if (bad) return bad;
        const d = geo.course(it.fix, it.aim).ft / geo.NM;
        if (d < MIN_FINAL_NM) return `${w} (land): the fix is ${d.toFixed(1)} nmi from the aiming point, less than ${MIN_FINAL_NM}`;
      } else if (kind === 'hold') {
        const bad = point((Array.isArray(it.centre) ? it.centre : []).concat([it.alt]), 3, `${w} (hold)`);
        if (bad) return bad;
      }
    }
    return null;
  }

  /** null if the plan is good, or the first fault as text. */
  function checkPlan(plan) {
    if (!plan || typeof plan !== 'object' || Array.isArray(plan)) return 'not a plan';
    const f = plan.field;
    if (!(f && typeof f === 'object' && num(f.elev_ft) && point([f.lat, f.lon], 2, 'field') === null)) return 'field: needs lat, lon and elev_ft';
    let bad = checkItems(plan.items, 'plan');
    if (bad) return bad;
    if (plan.lost_link !== undefined && plan.lost_link !== null) {
      bad = checkItems(plan.lost_link, 'lost-link route');
      if (bad) return bad;
      if (plan.lost_link[0].kind !== 'route' || plan.lost_link[plan.lost_link.length - 1].kind !== 'land') return 'lost-link route: it must begin with a route and end in a land';
    }
    const sites = plan.sites || [];
    for (let n = 0; n < sites.length; n++) {
      const s = sites[n];
      if (!(s && typeof s === 'object' && point(s.aim, 2, `site ${n + 1}`) === null && num(s.course) && num(s.elev_ft))) return `site ${n + 1}: needs aim, course and elev_ft`;
    }
    return null;
  }

  /**
   * The legs the forecast takes, from a list of items and where it begins ([lat, lon]). Each route point is a leg;
   * a land is one leg to the fix (level) and one down to the field; taxi is left out.
   */
  function legs(items, from, fieldElev) {
    const out = [];
    let last = from;
    let alt = null;
    for (const it of items || []) {
      if (it.kind === 'takeoff') {
        out.push({ kind: 'takeoff', dist_ft: geo.course(it.start, it.end).ft, alt_ft: fieldElev, item: it });
        last = it.end;
      } else if (it.kind === 'route') {
        it.points.forEach((p, i) => {
          out.push({ dist_ft: last ? geo.course(last, p).ft : 0, alt_ft: p[2], item: it, index: i, at: [p[0], p[1]], name: String(i + 1) });
          last = p;
          alt = p[2];
        });
      } else if (it.kind === 'land') {
        if (last) out.push({ dist_ft: geo.course(last, it.fix).ft, alt_ft: alt === null ? fieldElev + 4000 : alt, item: it, at: it.fix, label: 'fix', name: 'landing fix' });
        out.push({ kind: 'land', dist_ft: geo.course(it.fix, it.aim).ft, alt_ft: fieldElev, item: it, at: it.aim, label: 'land' });
        last = it.aim;
      } else if (it.kind === 'taxi') {
        last = it.points[it.points.length - 1];
      }
    }
    return out;
  }

  const api = { checkPlan, checkItems, legs, MAX_ALT };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).plancheck = api;
})(typeof window !== 'undefined' ? window : globalThis);
