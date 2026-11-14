/**
 * What the route planner (js/router.js) is given, worked out from a plan and what the station knows (pure, so node can test it), and the words
 * for its cards. Where the route begins, the landing fix and its height, the landing sites that count (the plan's own and the airports that can
 * hold the landing at this weight: whole strips, and shorter ones as a last resort), and what a card says about itself.
 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const geo = node ? require('./geo.js') : root.GCS.geo;
  const AP = node ? require('./airports.js') : root.GCS.airports;
  const FM = node ? require('./flightmath.js') : root.GCS.flightmath;
  const NM = geo.NM;
  const SHORT_STRIP = 0.75; // the MV-22B finder's FORCED_RUN: a strip that cannot hold the whole landing but is the best ground in reach

  const landOf = (plan) => (plan && plan.items ? plan.items.find((i) => i.kind === 'land') : null) || null;

  /** Where the route begins: the aircraft when it is flying, else the takeoff's end, else the field. { pos, alt_ft }. */
  function startOf(plan, flying, here, alt_ft) {
    const elev = plan.field.elev_ft || 0;
    if (flying && here && Number.isFinite(alt_ft)) return { pos: [here[0], here[1]], alt_ft };
    const t = plan.items.find((i) => i.kind === 'takeoff');
    if (t) return { pos: [t.end[0], t.end[1]], alt_ft: elev + 100 }; // the forecast's takeoff ends 100 ft up
    return { pos: [plan.field.lat, plan.field.lon], alt_ft: elev + 100 };
  }

  /** The landing fix, and the height to be at over it: the plan's own last route point there, else the height the aircraft's capability asks for over the ground (js/flightmath.js: the path comes down to it in time to be taken over cleanly) at the landing weight. null with no landing. */
  function goalOf(plan, weight_lb) {
    const land = landOf(plan);
    if (!land) return null;
    const elev = Number.isFinite(land.elev_ft) ? land.elev_ft : plan.field.elev_ft || 0; // the landing's own, as the aircraft takes it
    const route = plan.items.filter((i) => i.kind === 'route').pop();
    const last = route && route.points[route.points.length - 1];
    const same = last && Math.abs(last[0] - land.fix[0]) < 0.001 && Math.abs(last[1] - land.fix[1]) < 0.001;
    return { fix: [land.fix[0], land.fix[1]], fix_alt_ft: same ? last[2] : Math.round((elev + FM.finalFixHeightAgl(geo.course(land.fix, land.aim).ft, weight_lb || 20000)) / 100) * 100, land };
  }

  /**
   * The sites that count: the plan's, and the airports with a paved runway of at least what the landing asks at this weight (tier 1) or of at least 0.75 of it (tier 2).
   * Returns { list: [{ lat, lon, elev_ft, name, tier }], note }.
   */
  function sites(plan, airports, forecast, weight_lb) {
    const list = [];
    for (const s of (plan && plan.sites) || []) list.push({ lat: s.aim[0], lon: s.aim[1], elev_ft: s.elev_ft || 0, name: s.name || 'site', tier: 1 });
    let n1 = 0;
    let n2 = 0;
    for (const a of airports || []) {
      if (list.some((s) => geo.course([s.lat, s.lon], [a.lat, a.lon]).ft / NM < 1.5)) continue;
      const need = AP.need(forecast, weight_lb, a.elev_ft).need_ft;
      const have = a.paved_ft || 0;
      if (have >= need) {
        list.push({ lat: a.lat, lon: a.lon, elev_ft: a.elev_ft, name: a.ident, tier: 1 });
        n1++;
      } else if (have >= SHORT_STRIP * need) {
        list.push({ lat: a.lat, lon: a.lon, elev_ft: a.elev_ft, name: a.ident, tier: 2 });
        n2++;
      }
    }
    const note = (airports || []).length ? `${(plan && plan.sites ? plan.sites.length : 0)} of the plan's sites, ${n1} airports that can hold the landing at ${Math.round(weight_lb / 100) * 100} lb and ${n2} shorter strips` : `the plan's own ${(plan && plan.sites ? plan.sites.length : 0)} sites only: no airports are loaded`;
    return { list, note };
  }

  const hm = (s) => {
    const min = Math.round(s / 60); // whole minutes first, so that 1 h 59.6 min is 2 h 00 min and never "1 h 60 min"
    return min >= 60 ? `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')} min` : `${min} min`;
  };
  const sgn = (v, unit, digits) => {
    const k = Math.pow(10, digits || 0);
    const r = Math.round(v * k) / k;
    return `${r > 0 ? '+' : r < 0 ? '−' : '±'}${Math.abs(r).toFixed(digits || 0)} ${unit}`;
  };

  /** The words on a card: { title, stats, diff, reach, avoids, warnings }. */
  function words(card) {
    const c = card.coverage;
    const reach = !c ? '' : c.longest_gap_nm <= 6 ? 'a landing site in glide reach all the way' : `no landing site in glide reach for up to ${Math.round(c.longest_gap_nm)} nmi (${Math.round((1 - c.share) * 100)} % of the route)`;
    const vs = card.vs_fuel;
    const diff = !vs || (Math.abs(vs.time_s) < 1 && Math.abs(vs.fuel_lb) < 0.5 && Math.abs(vs.dist_nm) < 0.5) ? '' : `${sgn(vs.time_s / 60, 'min')}, ${sgn(vs.fuel_lb, 'lb')}, ${sgn(vs.dist_nm, 'nmi')} against the least fuel`;
    const avoids = card.direct ? (card.blocked_by ? `crosses ${card.blocked_by}` : 'crosses nothing the layers know of') : card.avoids && card.avoids.length ? `goes round ${card.avoids.join(', ')}` : '';
    return { title: card.names.join(' · '), stats: `${hm(card.time_s)} · ${Math.round(card.fuel_lb)} lb · ${Math.round(card.dist_nm)} nmi · ${card.alt_ft.toLocaleString('en-US')} ft`, diff, reach, avoids, warnings: card.warnings || [] };
  }

  const api = { landOf, startOf, goalOf, sites, words, SHORT_STRIP };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).routeinputs = api;
})(typeof window !== 'undefined' ? window : globalThis);
