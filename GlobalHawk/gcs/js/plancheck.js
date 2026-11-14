/**
 * The aircraft's plan check (fdm/onboard.py: check_plan), ported, so that a fault shows in the station before a
 * plan is sent. The aircraft still decides: this only saves a round trip. The two are run against each other on
 * damaged plans in fdm/phase8c_checks.py. Also: turning a plan's items into the legs the forecast takes.
 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const geo = node ? require('./geo.js') : root.GCS.geo;
  const FM = node ? require('./flightmath.js') : root.GCS.flightmath;
  const PERF = node ? require('./perfdata.js') : root.GCS.perfdata;
  const KINDS = ['taxi', 'takeoff', 'route', 'land', 'hold'];
  const MAX_ALT = 65000;
  const MAX_LEG_NM = 3000;
  const MIN_FINAL_NM = 8;
  const MAX_DESCENT_DEG = 6; // a route leg goes down no more steeply than this on average (the aircraft's own check; docs/PLAN.md, "The aircraft refuses what it cannot fly")
  const MIN_GRADIENT_LEG_NM = 2; // shorter legs are not judged on their slope
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
        if (kind === 'route') {
          for (let m = 0; m + 1 < pts.length; m++) {
            const ft = geo.course(pts[m], pts[m + 1]).ft;
            const drop = pts[m][2] - pts[m + 1][2];
            if (drop > 0 && ft / geo.NM >= MIN_GRADIENT_LEG_NM) {
              const deg = (Math.atan2(drop, ft) * 180) / Math.PI;
              if (deg > MAX_DESCENT_DEG) return `${w} (route): point ${m + 1} to point ${m + 2} goes down ${drop.toFixed(0)} ft in ${(ft / geo.NM).toFixed(1)} nmi, ${deg.toFixed(1)} deg: the aircraft does not come down more steeply than ${MAX_DESCENT_DEG} deg`;
            }
          }
        }
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
   * a land is one leg to the fix (level) and one down to the field; taxi is left out. field: the plan's field, or
   * just its height; its runway_past_aim_ft, if the plan gives one, goes with every landing (the station's own
   * note for the forecast: the aircraft does not read it).
   */
  function legs(items, from, field, opts) {
    const fieldElev = typeof field === 'object' && field !== null ? field.elev_ft : field;
    const runway = typeof field === 'object' && field !== null && Number(field.runway_past_aim_ft) > 0 ? Number(field.runway_past_aim_ft) : undefined;
    const out = [];
    let last = from;
    let alt = null;
    for (const it of items || []) {
      if (it.kind === 'takeoff') {
        out.push({ kind: 'takeoff', dist_ft: geo.course(it.start, it.end).ft, alt_ft: fieldElev, item: it });
        last = it.end;
      } else if (it.kind === 'route') {
        it.points.forEach((p, i) => {
          out.push({ dist_ft: last ? geo.course(last, p).ft : 0, alt_ft: p[2], item: it, index: i, at: [p[0], p[1]], from: last ? [last[0], last[1]] : null, name: String(i + 1) });
          last = p;
          alt = p[2];
        });
      } else if (it.kind === 'land') {
        // a landing may carry its own elevation (a plan that lands at another field than it left): the aircraft takes the item's before the field's
        const landElev = Number.isFinite(it.elev_ft) ? it.elev_ft : fieldElev;
        if (last) out.push({ dist_ft: geo.course(last, it.fix).ft, alt_ft: alt === null ? landElev + 4000 : alt, item: it, at: it.fix, from: [last[0], last[1]], label: 'fix', name: 'landing fix' });
        out.push({ kind: 'land', dist_ft: geo.course(it.fix, it.aim).ft, alt_ft: landElev, item: it, at: it.aim, from: [it.fix[0], it.fix[1]], label: 'land', runway_past_aim_ft: runway });
        last = it.aim;
      } else if (it.kind === 'taxi') {
        last = it.points[it.points.length - 1];
      }
    }
    // the aircraft flies each corner as an arc (js/flightmath.js): it starts the turn the lead before the point and the way round is shorter than the two legs to the
    // point by 2 R tan(delta / 2) - R delta; each leg gives half of that, so the forecast flies the distance the aircraft does
    if (!opts || opts.arcs !== false) {
      const kts = (alt) => FM.lerp(PERF.alt_ft, PERF.ktas, alt);
      for (let i = 0; i + 1 < out.length; i++) {
        const a = out[i];
        const b = out[i + 1];
        if (!a.from || !a.at || !b.from || !b.at || a.kind === 'takeoff' || b.kind === 'takeoff' || !Number.isFinite(a.alt_ft)) continue;
        if (Math.abs(a.at[0] - b.from[0]) > 1e-9 || Math.abs(a.at[1] - b.from[1]) > 1e-9) continue;
        const delta = geo.turn(geo.course(a.from, a.at).deg, geo.course(b.from, b.at).deg);
        if (Math.abs(delta) < 2.5 || Math.abs(delta) > FM.cap.turn.fly_by_max_deg) continue;
        const t = FM.turn({ delta_deg: delta, alt_ft: a.alt_ft, vg_fps: kts(a.alt_ft) * FM.KT });
        const d = (Math.abs(delta) * Math.PI) / 180;
        const cut = Math.max(0, t.radius_ft * Math.tan(d / 2) - (t.radius_ft * d) / 2);
        a.dist_ft = Math.max(a.dist_ft - cut, a.dist_ft * 0.2);
        b.dist_ft = Math.max(b.dist_ft - cut, b.dist_ft * 0.2);
        a.arc_cut_ft = (a.arc_cut_ft || 0) + cut;
        b.arc_cut_ft = (b.arc_cut_ft || 0) + cut;
      }
    }
    return out;
  }

  const nm = (ft) => (Math.round((ft / geo.NM) * 10) / 10).toFixed(1);

  /**
   * What the aircraft's capability says about a plan (the planner's word; the aircraft still decides what it accepts): the corners it
   * cannot fly well, the legs too short for the turns at their ends, and a final it cannot take. Each is { kind, at, text, have, need }
   * in words with the numbers and what to change; nothing for a plan that has none (no noise). The numbers are the laws' own
   * (js/flightmath.js reads js/capability.js, written by fdm/capability.py): the radius from the ground speed on the schedule and the bank
   * the aircraft uses at that height, the lead from it and the bank's delay. opts.weight_lb: the landing weight (default 20,000 lb); opts.field_wind: the wind at the landing field, { dir_deg, speed_kt, gust_kt, from }, for the crosswind check.
   */
  function assess(plan, opts) {
    const o = opts || {};
    const weight = o.weight_lb || 20000;
    const cap = FM.cap;
    const out = [];
    const chain = [];
    let n = 0;
    for (const it of (plan && plan.items) || []) {
      if (it.kind === 'takeoff') {
        chain.length = 0;
        // the takeoff's heading is the course the aircraft arrives on at the first leg: the run's start is the point before the corner at its end,
        // which the aircraft turns right after lift-off (500 ft up)
        chain.push({ p: it.start, alt: null, label: 'the start of the takeoff' });
        chain.push({ p: it.end, alt: ((plan.field && plan.field.elev_ft) || 0) + 500, label: 'the end of the takeoff', takeoff: true });
      } else if (it.kind === 'route') {
        for (const p of it.points) chain.push({ p: [p[0], p[1]], alt: p[2], label: `point ${++n}` });
      } else if (it.kind === 'land') {
        const last = chain[chain.length - 1];
        const elev = Number.isFinite(it.elev_ft) ? it.elev_ft : (plan.field && plan.field.elev_ft) || 0;
        if (last && geo.course(last.p, it.fix).ft < 600) {
          last.label = 'the landing fix';
          last.land = it;
          last.elev = elev;
        } else chain.push({ p: it.fix, alt: last ? last.alt : null, label: 'the landing fix', land: it, elev, assumed: true });
        chain.push({ p: it.aim, alt: null, label: 'the aiming point', aim: true });
      }
    }
    const ktas = (alt) => FM.lerp(PERF.alt_ft, PERF.ktas, alt);
    const corners = [];
    for (let i = 1; i + 1 < chain.length; i++) {
      const c = chain[i];
      if (c.aim || c.alt === null) continue;
      const delta = geo.turn(geo.course(chain[i - 1].p, c.p).deg, geo.course(c.p, chain[i + 1].p).deg);
      const vg = ktas(c.alt) * FM.KT;
      const t = FM.turn({ delta_deg: delta, alt_ft: c.alt, vg_fps: vg, weight_lb: weight });
      corners.push({ i, c, delta, t, flown: Math.abs(delta) > 2.5 });
      const firstMax = c.takeoff ? FM.departureMaxDeg() : null;
      if (c.takeoff && firstMax !== null && Math.abs(delta) > firstMax) {
        out.push({
          kind: 'corner', at: c.label, have: Math.abs(delta), need: firstMax,
          text: `The first point is ${Math.round(Math.abs(delta))}° off the takeoff's heading: the first leg begins at lift-off, so the aircraft is turned onto it without the lead it takes between legs, goes up to ${Math.round(FM.departureOffFt(delta) / 100) * 100} ft off the line and is back on it ${FM.departureBackNm(delta).toFixed(1)} nmi from the end of the takeoff. `
            + `Put a point ahead on the runway's extension (or a first point within ${Math.round(firstMax)}° of the runway's heading), so that no turn after it is over ${cap.turn.max_join_deg}°.`,
        });
      } else if (Math.abs(delta) > cap.turn.max_join_deg) {
        out.push({
          kind: 'corner', at: c.label, have: Math.abs(delta), need: cap.turn.max_join_deg,
          text: `The turn at ${c.label} is ${Math.round(Math.abs(delta))}°: the aircraft turns about ${Math.round(t.bank_deg)}° of bank there, a radius of ${nm(t.radius_ft)} nmi, and `
            + (Math.abs(delta) > cap.turn.fly_by_max_deg ? `past ${cap.turn.fly_by_max_deg}° it flies over the point and ends about ${nm(2 * t.radius_ft)} nmi off the new leg. ` : `starts it ${nm(t.lead_ft)} nmi before the point. `)
            + `Put a point in so that no turn is over ${cap.turn.max_join_deg}°.`,
        });
      }
    }
    for (let a = 0; a + 1 < corners.length; a++) {
      const A = corners[a];
      const B = corners[a + 1];
      if (!A.flown || !B.flown || B.i !== A.i + 1 || B.c.aim) continue;
      const len = geo.course(A.c.p, B.c.p).ft;
      const settle = A.c.takeoff && FM.departureBackNm(A.delta) !== null ? FM.departureBackNm(A.delta) * geo.NM : A.t.lead_ft; // after the takeoff's corner: until the aircraft is back on the line
      const need = settle + B.t.lead_ft;
      if (len < need) {
        out.push({
          kind: 'leg', at: `${A.c.label} to ${B.c.label}`, have: len, need,
          text: `The leg from ${A.c.label} to ${B.c.label} is ${nm(len)} nmi: the turns at its two ends take ${nm(settle)} and ${nm(B.t.lead_ft)} nmi of it, ${nm(need)} nmi in all. Make the leg longer than that, or take one point out.`,
        });
      }
    }
    // a descent the aircraft's cannot make in the length of the leg: from a point to the next that is lower by more than the flown descent allows in that distance
    for (let i = 0; i + 1 < chain.length; i++) {
      const a = chain[i];
      const b = chain[i + 1];
      if (b.aim || a.alt === null || b.alt === null || !(a.alt > b.alt + 200)) continue;
      const len = geo.course(a.p, b.p).ft / geo.NM;
      const need = descentNm(a.alt, b.alt, weight);
      if (need > len * DESCENT_SLACK) {
        const lower = descentFitsFrom(b.alt, len, weight);
        out.push({
          kind: 'descent', at: `${a.label} to ${b.label}`, have: len, need,
          text: `The leg from ${a.label} (${Math.round(a.alt)} ft) down to ${b.label} (${Math.round(b.alt)} ft) is ${nm(len * geo.NM)} nmi: the aircraft's descent takes about ${nm(need * geo.NM)} nmi for ${Math.round(a.alt - b.alt)} ft, so it arrives about ${Math.round(a.alt - b.alt - Math.max(0, lower - b.alt))} ft too high. `
            + `Lower ${a.label} to ${Math.round(lower)} ft or less, or put ${b.label} ${nm((need - len) * geo.NM)} nmi farther on.`,
        });
      }
    }
    // the final: where the aircraft is back on the final's line after the turn at the fix, and what it has left of height and of way
    const fixC = chain.find((c) => c.land && !c.assumed && c.alt !== null);
    if (fixC) {
      const k = corners.find((x) => x.c === fixC);
      const land = fixC.land;
      const aimP = chain[chain.indexOf(fixC) + 1].p;
      const dFix = geo.course(fixC.p, aimP).ft;
      const after = k && k.flown && Math.abs(k.delta) <= cap.turn.fly_by_max_deg ? k.t.lead_ft : 0;
      const dJoin = dFix - after;
      const agl = fixC.alt - fixC.elev;
      const pathAt = FM.pathHeightFt(dJoin);
      const sl = FM.slowing(weight);
      const slowFt = sl.slow_ft === null ? 0 : sl.slow_ft;
      const dCap = (agl - cap.approach.aim_height_ft) / cap.approach.glide_tan; // out from the aiming point where the path comes down to the aircraft's height
      if (agl > pathAt + 100) {
        // above the path where the aircraft is back on the final: lower the fix, or move it out, to the capability's gap under the path
        const want = FM.finalFixHeightAgl(dJoin, weight);
        out.push({
          kind: 'final', at: fixC.label, have: agl, need: pathAt,
          text: `The aircraft is ${Math.round(agl)} ft over the ground at the landing fix and is back on the final ${nm(dJoin)} nmi out after the turn there, where the glide path is ${Math.round(pathAt)} ft high: it comes onto the path ${Math.round(agl - pathAt)} ft too high. Put the fix at ${Math.round(fixC.elev + want)} ft or lower, or ${nm(Math.max((agl - want) / cap.approach.glide_tan, 0))} nmi farther out.`,
        });
      } else {
        const room = dJoin - dCap;
        const gapNeed = FM.captureGapFt();
        const gap = pathAt - agl; // how far under the path the aircraft is where it is back on the final
        if (gap < gapNeed) {
          const want = FM.finalFixHeightAgl(dJoin, weight);
          out.push({
            kind: 'final', at: fixC.label, have: gap, need: gapNeed,
            text: `The glide path is only ${Math.round(gap)} ft above the aircraft where it is back on the final (${Math.round(agl)} ft over the ground at the fix, the path ${Math.round(pathAt)} ft high there): the aircraft dives when the landing configuration goes on and climbs back, and the path should come down to it after that has settled, ${Math.round(gapNeed)} ft above it. Put the fix at ${Math.round(fixC.elev + want)} ft or lower, or ${nm(Math.max((agl - want) / cap.approach.glide_tan, 0))} nmi farther out.`,
          });
        } else if (room < slowFt) {
          out.push({
            kind: 'final', at: fixC.label, have: room, need: slowFt,
            text: `The aircraft takes about ${nm(slowFt)} nmi to slow from ${cap.approach.schedule_kcas} to within ${cap.approach.capture_speed_kt} kt of the approach speed (${Math.round(sl.approach_kcas)} KCAS at ${Math.round(weight / 100) * 100} lb), and the glide path comes down to it only ${nm(Math.max(room, 0))} nmi after the turn onto the final. Put the fix ${nm(slowFt - Math.max(room, 0))} nmi farther out, or lower.`,
          });
        }
      }
    }
    // the crosswind on the final: the wind reported at the field (opts.field_wind: { dir_deg, speed_kt, gust_kt, from }) across the final's course, against what the landing holds its
    // contracts in at this weight (fdm/landlimit.py): the gust counts, the limit being for a steady wind
    const fw = o.field_wind;
    const landIt = ((plan && plan.items) || []).find((it) => it.kind === 'land' && it.fix && it.aim);
    const xwLimit = FM.crosswindLimitKt(weight);
    if (fw && landIt && xwLimit !== null && Number.isFinite(fw.dir_deg) && Number.isFinite(fw.speed_kt)) {
      const course = geo.course(landIt.fix, landIt.aim).deg;
      const kt = Math.max(fw.speed_kt, fw.gust_kt || 0);
      const xw = Math.abs(kt * Math.sin(((fw.dir_deg - course) * Math.PI) / 180));
      if (xw > xwLimit) {
        out.push({
          kind: 'crosswind', at: 'the landing', have: xw, need: xwLimit,
          text: `The wind at the field${fw.from ? ' (' + fw.from + ')' : ''} is from ${Math.round(fw.dir_deg)} deg at ${Math.round(fw.speed_kt)} kt${fw.gust_kt ? ', gusting ' + Math.round(fw.gust_kt) : ''}: ${Math.round(xw)} kt across the final (course ${Math.round(course)} deg). `
            + `At ${Math.round(weight / 100) * 100} lb the aircraft's landing holds its limits to ${Math.round(xwLimit)} kt of crosswind (flown in the model, in steady wind: less in gusts). `
            + 'Land on the other runway or at another field, land lighter, or wait for the wind to ease.',
        });
      }
    }
    return out;
  }

  /**
   * How far the aircraft goes (nmi) in descending from one height to another at a weight: the flown descent rate (js/flightmath.js) at the speed the forecast
   * flies, in steps of 250 ft. 0 for a climb or no change.
   */
  function descentNm(fromFt, toFt, weight) {
    if (!(fromFt > toFt)) return 0;
    let nm = 0;
    for (let h = fromFt; h > toFt; h -= 250) {
      const step = Math.min(250, h - toFt);
      const mid = h - step / 2;
      const rate = -FM.descentFpm(mid, weight); // ft/min, positive
      const kt = FM.lerp(PERF.alt_ft, PERF.ktas, mid);
      nm += (step * kt) / (60 * Math.max(rate, 50));
    }
    return nm;
  }
  /** How much longer than the leg the descent may be before the assessment says so: the flown descent varies 10 % with weight and wind, and the dangerous plans are a multiple off (the local flight that came to the fix 9,000 ft high needed 3 times the leg); mine. */
  const DESCENT_SLACK = 1.1;
  /** The highest start height from which a descent to toFt fits in lenNm (within DESCENT_SLACK), to 500 ft: the height to lower a point to. */
  function descentFitsFrom(toFt, lenNm, weight) {
    let h = toFt;
    while (h + 500 <= MAX_ALT && descentNm(h + 500, toFt, weight) <= lenNm * DESCENT_SLACK) h += 500;
    return h;
  }
  /**
   * The height the station's local flight can have its box at: the highest of 15,000 ft down to the default (3,000 ft over the fix) at which the forecast reaches every height of the plan
   * (the climb to the box, and the descent from it to the landing fix), in steps of 500 ft. fc: predict.make's; state: { alt_ft, weight_lb, fuel_lb }.
   */
  function localBoxFt(here, hdg, elev, fc, state) {
    const lowest = geo.localPlan(here, hdg, elev).items[1].points[0][2]; // the default box: 3,000 ft over the fix
    for (let h = 15000; h >= lowest; h -= 500) {
      const plan = geo.localPlan(here, hdg, elev, h);
      const f = fc.predict(legs(plan.items, null, plan.field), state);
      if (!f.warnings.some((w) => /not reached/.test(w)) && !assess(plan, { weight_lb: state.weight_lb }).some((x) => x.kind === 'descent')) return h;
    }
    return lowest;
  }

  const api = { checkPlan, checkItems, legs, assess, descentNm, descentFitsFrom, localBoxFt, MAX_ALT };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).plancheck = api;
})(typeof window !== 'undefined' ? window : globalThis);
