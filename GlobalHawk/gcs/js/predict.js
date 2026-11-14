/**
 * The station's forecast: time, fuel and height along a list of legs, from a table sampled from the flight model
 * (js/perfdata.js, written by fdm/gcs_perf.py). The aircraft does not use this: it is what the station draws
 * before a command is sent. Standard atmosphere, no turns, and no wind unless a wind is given (opts.wind of predict: the ground speed then
 * follows the wind along each leg; without it every answer is what it was before the option existed).
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const NM = 6076.1;
  const STEP_S = 20;
  const CAPTURE_FT = 150; // the manager flies level within this of a commanded height
  const APPROACH_KT = 140; // true airspeed down the final, about
  const TAKEOFF = { seconds: 95, fuel_lb: 55, climb_ft: 100 }; // start of the roll to the manager's "airborne": measured in fdm/phase8c_checks.py
  const RESERVE_LB = 765; // 5 % of full tanks
  const ROLL_MARGIN = 1.15; // runway asked for over the forecast roll: an assumed allowance (no wind, a dry level runway, in the table)

  function make(P) {
    const A = P.alt_ft;
    const Wt = P.weight_lb;
    /** Bilinear lookup; a null corner (the aircraft cannot do this there) makes the result null. */
    function look(table, alt, weight) {
      const a = Math.min(Math.max(alt, A[0]), A[A.length - 1]);
      const w = Math.min(Math.max(weight, Wt[0]), Wt[Wt.length - 1]);
      let i = 0;
      while (i < A.length - 2 && a > A[i + 1]) i++;
      let j = 0;
      while (j < Wt.length - 2 && w > Wt[j + 1]) j++;
      const fa = (a - A[i]) / (A[i + 1] - A[i]);
      const fw = (w - Wt[j]) / (Wt[j + 1] - Wt[j]);
      const c = [table[i][j], table[i][j + 1], table[i + 1][j], table[i + 1][j + 1]];
      if (c.some((v) => v === null)) {
        // take the nearest corner if it has a value: a hole in the table is the edge of what the aircraft can do
        const near = table[fa < 0.5 ? i : i + 1][fw < 0.5 ? j : j + 1];
        return near;
      }
      return (c[0] * (1 - fw) + c[1] * fw) * (1 - fa) + (c[2] * (1 - fw) + c[3] * fw) * fa;
    }
    function ktas(alt) {
      const a = Math.min(Math.max(alt, A[0]), A[A.length - 1]);
      let i = 0;
      while (i < A.length - 2 && a > A[i + 1]) i++;
      return P.ktas[i] + ((P.ktas[i + 1] - P.ktas[i]) * (a - A[i])) / (A[i + 1] - A[i]);
    }

    /**
     * The landing at a weight on a field at a height, from the flight model's own landings: how far past the aiming
     * point it touches down, how far past it the rollout ends (15 kt, where the taxi begins), and the runway to
     * have past the aiming point (the rollout with the margin). null if the table has no landings.
     */
    function landing(weight, elev) {
      const L = P.landing;
      if (!L) return null;
      const W = L.weight_lb;
      const E = L.elev_ft;
      const w = Math.min(Math.max(weight, W[0]), W[W.length - 1]);
      const e = Math.min(Math.max(elev, E[0]), E[E.length - 1]);
      let j = 0;
      while (j < W.length - 2 && w > W[j + 1]) j++;
      let i = 0;
      while (i < E.length - 2 && e > E[i + 1]) i++;
      const fw = (w - W[j]) / (W[j + 1] - W[j]);
      const fe = (e - E[i]) / (E[i + 1] - E[i]);
      const at = (T) => (T[i][j] * (1 - fw) + T[i][j + 1] * fw) * (1 - fe) + (T[i + 1][j] * (1 - fw) + T[i + 1][j + 1] * fw) * fe;
      const slow = at(L.slow_ft);
      return { weight_lb: weight, touchdown_ft: at(L.touchdown_ft), slow_ft: slow, runway_ft: slow * ROLL_MARGIN };
    }

    /**
     * legs: [{ dist_ft, alt_ft, kind? }] ('land' flies down to alt_ft at approach speed; 'takeoff' is the fixed
     * allowance). state: { alt_ft, weight_lb, fuel_lb }. Returns { points: [{ t_s, fuel_lb, alt_ft, dist_ft,
     * reached }], total: { t_s, fuel_used_lb, dist_ft }, profile: [[dist_ft, alt_ft, t_s, fuel_lb]], warnings: [text] }.
     * A 'land' leg's point also has landing: what landing() gives for the weight it arrives with; and if the leg
     * says how much runway there is past the aiming point (runway_past_aim_ft), too little is a warning.
     */
    function predict(legs, state, opts) {
      // opts.wind(lat, lon, alt_ft, hours) => { spd (kt), dir (deg, it blows FROM) } | null, and opts.hours: when the flight starts (hours from now).
      // The wind changes the ground speed only: along the leg, a tailwind adds to it and a headwind takes from it (the aircraft crabs and
      // keeps its track, so the crosswind costs nothing here), and the time on a leg and so its fuel change with it. No wind given, no change at all.
      const wind = opts && opts.wind ? opts.wind : null;
      let t = 0;
      let alt = state.alt_ft;
      let fuel = state.fuel_lb;
      const dry = state.weight_lb - state.fuel_lb;
      let dist = 0;
      const points = [];
      const profile = [[0, alt, 0, fuel]];
      const warnings = [];
      legs.forEach((leg, n) => {
        if (leg.kind === 'takeoff') {
          t += TAKEOFF.seconds;
          fuel -= TAKEOFF.fuel_lb;
          alt += TAKEOFF.climb_ft;
          dist += leg.dist_ft;
          profile.push([dist, alt, t, fuel]);
          points.push({ t_s: t, fuel_lb: fuel, alt_ft: alt, dist_ft: dist, reached: true });
          return;
        }
        let left = leg.dist_ft;
        let guard = 0;
        const course = wind && leg.from && leg.at && leg.kind !== 'land' ? geo.course(leg.from, leg.at).deg : null;
        while (left > 1 && guard++ < 20000) {
          const w = dry + Math.max(fuel, 0);
          let v = ktas(alt) * (NM / 3600); // ft/s
          let rate = 0; // ft/s
          let flow; // lb/h
          if (leg.kind === 'land') {
            v = APPROACH_KT * (NM / 3600);
            rate = alt > leg.alt_ft ? -Math.min((alt - leg.alt_ft) / Math.max(left / v, 1), 40) : 0;
            flow = look(P.descent_pph, alt, w);
          } else if (alt < leg.alt_ft - CAPTURE_FT) {
            rate = look(P.climb_fpm, alt, w) / 60;
            flow = look(P.climb_pph, alt, w);
            if (rate < 50 / 60) {
              rate = 0; // at its ceiling for this weight: it stays here at maximum thrust
            }
          } else if (alt > leg.alt_ft + CAPTURE_FT) {
            rate = look(P.descent_fpm, alt, w) / 60;
            flow = look(P.descent_pph, alt, w);
          } else {
            flow = look(P.level_pph, alt, w);
            if (flow === null) flow = look(P.climb_pph, alt, w);
          }
          let vg = v; // ground speed, ft/s
          if (course !== null) {
            const f = leg.dist_ft > 0 ? 1 - left / leg.dist_ft : 0;
            const here = [leg.from[0] + (leg.at[0] - leg.from[0]) * f, leg.from[1] + (leg.at[1] - leg.from[1]) * f];
            const wv = wind(here[0], here[1], alt, ((opts.hours || 0) * 3600 + t) / 3600);
            if (wv && Number.isFinite(wv.spd) && Number.isFinite(wv.dir)) vg = Math.max(v + wv.spd * Math.cos(((wv.dir + 180 - course) * Math.PI) / 180) * (NM / 3600), 30 * (NM / 3600));
          }
          let dt = Math.min(STEP_S, left / vg);
          if (rate > 0) dt = Math.min(dt, Math.max((leg.alt_ft - alt) / rate, 0.5));
          if (rate < 0 && leg.kind !== 'land') dt = Math.min(dt, Math.max((alt - leg.alt_ft) / -rate, 0.5));
          alt += rate * dt;
          fuel -= (flow * dt) / 3600;
          t += dt;
          left -= vg * dt;
          dist += vg * dt;
          profile.push([dist, alt, t, fuel]);
        }
        const reached = leg.kind === 'land' || Math.abs(alt - leg.alt_ft) <= CAPTURE_FT + 1;
        if (!reached) warnings.push(`${leg.name ? (/^\d+$/.test(leg.name) ? 'point ' + leg.name : 'the ' + leg.name) : 'point ' + (n + 1)}: ${Math.round(leg.alt_ft)} ft is not reached by then (${Math.round(alt / 100) * 100} ft)`);
        const pt = { t_s: t, fuel_lb: fuel, alt_ft: alt, dist_ft: dist, reached };
        if (leg.kind === 'land') {
          pt.landing = landing(dry + Math.max(fuel, 0), leg.alt_ft);
          const have = Number(leg.runway_past_aim_ft);
          if (pt.landing && have > 0 && pt.landing.runway_ft > have) {
            warnings.push(`the landing at ${Math.round(pt.landing.weight_lb / 100) * 100} lb needs ${Math.round(pt.landing.runway_ft / 100) * 100} ft of runway past the aiming point (the rollout ${Math.round(pt.landing.slow_ft / 100) * 100} ft and 15 % in hand): the plan says there are ${Math.round(have)} ft`);
          }
        }
        points.push(pt);
      });
      if (fuel < RESERVE_LB) warnings.push(fuel <= 0 ? 'the fuel runs out before the end' : `fuel at the end ${Math.round(fuel)} lb: under the reserve of ${RESERVE_LB} lb`);
      return { points, total: { t_s: t, fuel_used_lb: state.fuel_lb - fuel, dist_ft: dist }, profile, warnings };
    }
    return { predict, ktas, look, landing };
  }

  const api = { make, TAKEOFF, RESERVE_LB, ROLL_MARGIN, NM };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).predict = api;
})(typeof window !== 'undefined' ? window : globalThis);
