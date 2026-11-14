// node tests/router.test.js
// The route planner's limits R2 to R9 (docs/PLAN.md), and the emergency sites (E1 to E4) and several routes (A1 to A5) added to them.
const assert = require('assert');
const R = require('../js/router.js');
const P = require('../js/predict.js');
const perf = require('../js/perfdata.js');
const pc = require('../js/plancheck.js');
const geo = require('../js/geo.js');
const A = require('../js/airspace.js');
const W = require('../js/weather.js');
const reach = require('../js/reach.js');
const { PlanEditor } = require('../js/editor.js');
const demo = require('../js/demoplan.js');
const fc = P.make(perf);
const NM = geo.NM;
const T0 = Date.UTC(2026, 10, 14, 6, 0, 0);
const START = [35, -118];
const glide = (alt, elev) => reach.radius(alt, elev) / NM;
const sd = (n) => { let s = n * 2654435761 % 2147483647 || 1; return () => (s = (s * 48271) % 2147483647) / 2147483647; };
const mk = (nm, over) => {
  const goal = geo.along(START, 90, nm * NM);
  const legsFor = (pts) => pc.legs([{ kind: 'route', points: pts }, { kind: 'land', fix: [goal[0], goal[1]], aim: geo.along(goal, 90, 10 * NM) }], START, 2300);
  return Object.assign({ start: START, start_alt_ft: 2400, goal, fix_alt_ft: 5800, weight_lb: 22000, fuel_lb: 11000, fc, perf, wind: null, hours: 0, zones: [], hazards: [], now: T0, legsFor, altitudes: [45000, 50000] }, over);
};
// the heights from the forecast's own profile, sampled by the test's own walk, and the sites in reach by its own formula
const covIndep = (o, points, sites, step) => {
  const f = fc.predict(o.legsFor(points), { alt_ft: o.start_alt_ft, weight_lb: o.weight_lb, fuel_lb: o.fuel_lb }, { wind: o.wind, hours: o.hours });
  const alt = (d) => { const pr = f.profile; let i = 1; while (i < pr.length - 1 && pr[i][0] < d) i++; const t = pr[i][0] > pr[i - 1][0] ? Math.min(1, Math.max(0, (d - pr[i - 1][0]) / (pr[i][0] - pr[i - 1][0]))) : 0; return pr[i - 1][1] + (pr[i][1] - pr[i - 1][1]) * t; };
  const l = [o.start].concat(points.map((p) => [p[0], p[1]]));
  let covered = 0; let n = 0; let gap = 0; let longest = 0; let ran = 0;
  for (let i = 0; i + 1 < l.length; i++) {
    const d = geo.course(l[i], l[i + 1]).ft / NM;
    for (let x = 0; x < d; x += step || 2) {
      const q = [l[i][0] + (l[i + 1][0] - l[i][0]) * x / d, l[i][1] + (l[i + 1][1] - l[i][1]) * x / d];
      const a = alt((ran + x) * NM);
      const k = sites.filter((s) => geo.course(q, [s.lat, s.lon]).ft / NM <= Math.max(12, 0.85 * glide(a, s.elev_ft) - 5.3)).length;
      n++;
      if (k) { covered++; gap = 0; } else { gap += step || 2; longest = Math.max(longest, gap); }
    }
    ran += d;
  }
  return { share: covered / n, longest_gap_nm: longest };
};
const line = (r, start) => [start || START].concat(r.points.map((p) => [p[0], p[1]]));
const lenNm = (l) => l.slice(1).reduce((s, p, i) => s + geo.course(l[i], p).ft / NM, 0);
const sampleLine = (l, nm) => { const out = []; for (let i = 0; i + 1 < l.length; i++) { const d = geo.course(l[i], l[i + 1]).ft / NM; const n = Math.max(1, Math.ceil(d / nm)); for (let k = 0; k < n; k++) out.push([l[i][0] + (l[i + 1][0] - l[i][0]) * k / n, l[i][1] + (l[i + 1][1] - l[i][1]) * k / n]); } out.push(l[l.length - 1]); return out; };
const circle = (name, lat, lon, nm, kind) => A.make({ name, kind: kind || 'restricted', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 99999, ref: 'MSL' }, circle: { lat, lon, r_ft: nm * NM } });
const box = (lat, lon, dLat, dLon) => [[lat + dLat, lon - dLon], [lat + dLat, lon + dLon], [lat - dLat, lon + dLon], [lat - dLat, lon - dLon]];
const haz = (id, kind, lo, hi, ring) => ({ source: 'SIGMET', id, hazard: kind.toUpperCase(), kind, severity: 5, lo_ft: lo, hi_ft: hi, from: T0 - 1e6, to: T0 + 9e6, rings: [ring] });

// R2 geometry: no wind, nothing blocked
{
  const r = R.plan(mk(500));
  assert.ok(r.ok, r.error);
  const direct = geo.course(START, mk(500).goal).ft / NM;
  assert.ok(Math.abs(r.best.path_nm - direct) / direct < 0.01, `path ${r.best.path_nm} against ${direct}`);
  assert.ok(Math.abs(r.best.fuel_lb - r.direct.fuel_lb) / r.direct.fuel_lb < 0.02, 'fuel within 2 % of the forecast\'s own straight run');
  assert.deepStrictEqual(r.best.warnings, [], 'the forecast reaches every height');
  assert.ok(r.best.tod, 'a top of descent');
  assert.strictEqual(r.best.points[r.best.points.length - 1][2], 5800, 'the last point is the fix at its height');
  assert.ok(r.best.points[0][2] <= r.best.alt_ft, 'the heights climb');
}

// R3 wind: a band of westerly wind from 36 to 38 N
{
  const band = (dir) => (la) => (la >= 36 && la <= 38 ? { spd: 70, dir } : null);
  let r = R.plan(mk(600, { wind: band(270) }));
  assert.ok(r.ok, r.error);
  assert.ok(r.best.points.some((p) => p[0] >= 36), 'the route enters the band');
  assert.ok(r.best.fuel_lb < r.direct.fuel_lb * 0.97, `tailwind band: ${r.best.fuel_lb.toFixed(0)} against the direct route's ${r.direct.fuel_lb.toFixed(0)} lb`);
  r = R.plan(mk(600, { wind: band(90) }));
  assert.ok(r.best.fuel_lb <= r.direct.fuel_lb * (1 + 1e-9), 'a headwind band: no worse than the direct route');
  assert.ok(r.best.points.every((p) => p[0] < 36), 'and not through it');
}

// R4, R5, R6 blocked areas: a property test, the buffers of NASA's rules, and the other code agreeing
const ex = (z, start, goal) => A.contains(z, start[0], start[1]) || A.contains(z, goal[0], goal[1]);
const violations = (r, alt, zones, hazards, start, goal) => {
  const bad = [];
  const l = line(r, start);
  for (const q of sampleLine(l, 1)) {
    if (geo.course(start, q).ft / NM <= 10 || geo.course(goal, q).ft / NM <= 10) continue;
    for (const z of zones) if (!ex(z, start, goal) && A.relevantAt(z, alt, 1000) && ['restricted', 'prohibited', 'danger', 'tfr'].includes(z.kind) && A.contains(z, q[0], q[1])) bad.push(['zone', z.name, q]);
    for (const h of hazards) {
      const z = A.make({ rings: h.rings });
      const d = A.contains(z, q[0], q[1]) ? 0 : A.edge(z, q[0], q[1]).nm;
      if (h.kind === 'convective') {
        if ((alt <= 50000 || h.hi_ft >= 50000) && d < 24) bad.push(['convective', h.id, q, d]);
        else if (alt < h.hi_ft + 10000 && d === 0) bad.push(['convective-over', h.id, q]);
      } else if (h.lo_ft <= alt && h.hi_ft >= alt && d === 0) bad.push([h.kind, h.id, q]);
    }
  }
  return bad;
};
{
  let ok = 0;
  for (let k = 1; k <= 30; k++) {
    const rnd = sd(k);
    const zones = [];
    const hazards = [];
    for (let i = 0; i < 3 + Math.floor(rnd() * 4); i++) zones.push(circle(`R-${k}${i}`, 34 + rnd() * 3, -116 + rnd() * 4, 8 + rnd() * 30));
    for (let i = 0; i < 2 + Math.floor(rnd() * 3); i++) {
      const kind = ['turb', 'ice', 'convective'][Math.floor(rnd() * 3)];
      hazards.push(haz(`H${k}${i}`, kind, kind === 'convective' ? 0 : 20000, kind === 'convective' ? 30000 + rnd() * 25000 : 70000, box(34 + rnd() * 3, -116 + rnd() * 4, 0.3 + rnd() * 0.5, 0.4 + rnd() * 0.6)));
    }
    const o = mk(400, { zones, hazards });
    const r = R.plan(o);
    if (!r.ok) { assert.ok(r.error && r.error.length > 10, 'an error says something'); continue; }
    ok++;
    const bad = violations(r.best, r.best.alt_ft, zones, hazards, o.start, o.goal);
    assert.deepStrictEqual(bad.slice(0, 2), [], `set ${k}: the route is in a blocked place`);
    // R6: the airspace and hazard advisories, written independently, raise nothing hard on the cruise height
    const path = line(r.best).map((p) => ({ lat: p[0], lon: p[1], alt_ft: r.best.alt_ft }));
    const adv = A.advisories(zones.filter((z) => !ex(z, o.start, o.goal)), path, { gs_kt: 300, ahead_nm: 1e6 }).filter((a) => ['inside', 'ahead', 'plan'].includes(a.where) && a.level === 'caution');
    assert.deepStrictEqual(adv.map((a) => a.text), [], `set ${k}: the airspace advisories find the route in a zone`);
    const hadv = W.hazardAdvisories(hazards, path.slice(1, -1).concat([]), { now: T0, gs_kt: 300 }).filter((a) => ['inside', 'ahead', 'plan'].includes(a.where));
    // (the cruise stretch only: the climb and the descent are not looked at, and the first and last points are in the exempt rings)
    assert.deepStrictEqual(hadv.filter((a) => a.hazard.kind !== 'convective' || a.where === 'inside').map((a) => a.text), [], `set ${k}: the hazard advisories find the route in an area`);
  }
  assert.ok(ok >= 20, `only ${ok} of 30 random sets had a route`);
  // a goal ringed by areas: no route, and the error names them
  const goal = mk(400).goal;
  const ring = [0, 60, 120, 180, 240, 300].map((b, i) => { const c = geo.along(goal, b, 50 * NM); return circle(`R-RING${i}`, c[0], c[1], 45); });
  const r = R.plan(mk(400, { zones: ring }));
  assert.ok(!r.ok);
  assert.ok(/R-RING\d \(restricted\)/.test(r.error) || /round/.test(r.error), r.error);
  // a zone that holds the goal (home airspace) is not a block
  const home = circle('R-HOME', goal[0], goal[1], 30);
  assert.ok(R.plan(mk(400, { zones: [home] })).ok, 'the home zone is exempt');
}
{
  // R5: the same convective area (tops FL410) at the heights of NASA's rules
  const mid = geo.along(START, 90, 200 * NM);
  const conv = (hi) => haz('CONV', 'convective', 0, hi, box(mid[0], mid[1], 0.8, 0.9));
  const light = { weight_lb: 16000, fuel_lb: 5000 };
  const dist = (r) => Math.min(...sampleLine(line(r), 1).map((q) => { const z = A.make({ rings: conv(41000).rings }); return A.contains(z, q[0], q[1]) ? 0 : A.edge(z, q[0], q[1]).nm; }));
  let r = R.plan(mk(400, Object.assign({ hazards: [conv(41000)], altitudes: [50000] }, light)));
  assert.ok(r.ok, r.error);
  assert.ok(dist(r.best) >= 24, `FL500 over tops of FL410: ${dist(r.best).toFixed(1)} nmi`);
  r = R.plan(mk(400, Object.assign({ hazards: [conv(41000)], altitudes: [55000] }, light)));
  assert.ok(r.ok, r.error);
  assert.strictEqual(dist(r.best), 0, '55,000 ft over tops of FL410 (51,000 with the 10,000 ft): straight over it');
  r = R.plan(mk(400, Object.assign({ hazards: [conv(52000)], altitudes: [55000] }, light)));
  assert.ok(dist(r.best) >= 24, `tops of FL520: 25 nmi whatever the height: ${dist(r.best).toFixed(1)}`);
}

// R7 the same twice, and fast
{
  const zones = [circle('R-1', 35.3, -112, 25), circle('R-2', 34.6, -109.5, 20)];
  const o = mk(600, { zones, altitudes: undefined, wind: (la) => (la > 36 ? { spd: 40, dir: 280 } : null) });
  let t = Date.now();
  const a = R.plan(o);
  const ms = Date.now() - t;
  assert.ok(a.ok, a.error);
  assert.strictEqual(JSON.stringify(a), JSON.stringify(R.plan(o)), 'the same twice');
  assert.ok(ms < 3000, `600 nmi took ${ms} ms`);
  t = Date.now();
  const long = R.plan(mk(2500, { weight_lb: 25000, fuel_lb: 14000, altitudes: [45000, 50000] }));
  const ms2 = Date.now() - t;
  assert.ok(long.ok, long.error);
  assert.ok(ms2 < 8000, `2,500 nmi took ${ms2} ms`);
}

// R8 heights
{
  const all = R.plan(mk(500, { altitudes: [45000, 50000, 55000] }));
  const each = [45000, 50000, 55000].map((a) => R.plan(mk(500, { altitudes: [a] })).best.fuel_lb);
  assert.ok(Math.abs(all.best.fuel_lb - Math.min(...each)) < 1e-6, 'the cheapest height is chosen');
  const heavy = R.plan(mk(500, { weight_lb: 25000, fuel_lb: 14000, altitudes: [55000, 60000, 65000] }));
  assert.ok(!heavy.ok || heavy.options.every((p) => p.alt_ft <= 55000), 'a height the weight does not reach is not offered');
  assert.ok((heavy.errors || []).some((e) => /climbs only to/.test(e)), 'and the reason is given');
  const lightW = { weight_lb: 17000, fuel_lb: 6000 };
  const high = (la, lo, alt) => (alt >= 52000 ? { spd: 90, dir: 270 } : null);
  const w = R.plan(mk(500, Object.assign({ wind: high, altitudes: [45000, 50000, 55000, 60000] }, lightW)));
  assert.ok(w.ok, w.error);
  assert.ok(w.best.alt_ft >= 55000, 'a wind only above 52,000 ft: ' + w.best.alt_ft);
  const low = R.plan(mk(500, Object.assign({ wind: high, altitudes: [45000] }, lightW)));
  assert.ok(w.best.fuel_lb < low.best.fuel_lb * 0.92, 'and it burns at least 8 % less than 45,000 ft (measured 10.0 %: 931 lb against 1,034 lb; the 10 % in the plan was a guess that the climb to 60,000 ft eats into)');
  const short = R.plan(mk(150, { altitudes: [25000, 35000, 40000, 45000, 55000] }));
  assert.deepStrictEqual(short.options.map((p) => p.alt_ft), [25000, 35000], 'a 150 nmi route: the table needs 155 nmi for 40,000 ft, 193 for 45,000, 349 for 55,000');
  assert.ok(short.errors.some((e) => /55000 ft: the climb and the descent take 3\d\d nmi and the route is 150/.test(e)));
}

// R9 the plan, and the editor's undo
{
  const o = mk(500, { wind: (la) => (la > 35.5 ? { spd: 50, dir: 270 } : null) });
  const r = R.plan(o);
  const plan = JSON.parse(JSON.stringify(demo));
  plan.items = [plan.items[0], plan.items[1], { kind: 'route', points: r.best.points }, Object.assign({}, plan.items[3], { fix: o.goal.map((x) => Math.round(x * 1e6) / 1e6) })];
  plan.items[3].aim = geo.along(o.goal, 90, 10 * NM);
  assert.strictEqual(pc.checkPlan(plan), null, 'the plan passes the aircraft\'s own check');
  assert.ok(r.best.tod && r.best.warnings.length === 0);
  const ed = new PlanEditor(demo);
  const before = JSON.stringify(ed.plan);
  assert.ok(ed.setRoute(r.best.points));
  assert.deepStrictEqual(ed.points().map((p) => p[2]), r.best.points.map((p) => p[2]));
  assert.ok(/\(edited\)$/.test(ed.plan.id));
  assert.ok(ed.undoRoute());
  assert.strictEqual(JSON.stringify(ed.plan), before, 'Undo gives back the route exactly');
  assert.strictEqual(ed.undoRoute(), false, 'one undo');
  assert.strictEqual(ed.setRoute([]), false);
}

// ------------------------------------------------------------------ emergency landing sites
const site = (lat, lon, elev, name, tier) => ({ lat, lon, elev_ft: elev === undefined ? 2300 : elev, name: name || 'S', tier: tier || 1 });
{
  // E1 the glide radius and the coverage at its edge
  assert.ok(Math.abs(glide(45000, 2300) - 129.0) < 0.1, 'the planner\'s own radius at 45,000 ft: ' + glide(45000, 2300));
  const s1 = site(35, -118, 2300);
  const cov = R.coverage([s1], glide, 45000);
  const at = (nm) => { const p = geo.along([35, -118], 90, nm * NM); return cov.names(p[0], p[1]).length; }; // exact: at() keeps answers by 1.5 nmi cell
  assert.ok(Math.abs(0.85 * 129.0 - 5.3 - 104.35) < 0.1);
  assert.strictEqual(at(104), 1, '104 nmi out is covered');
  assert.strictEqual(at(105), 0, '105 nmi out is not');
  const tall = R.coverage([site(35, -118, 6000)], glide, 45000);
  const p100 = geo.along([35, -118], 90, 100 * NM);
  assert.strictEqual(tall.names(p100[0], p100[1]).length, 0, 'a 6,000 ft site covers less');
  assert.strictEqual(R.coverage([site(35, -118, 2300, 'short', 2)], glide, 45000).at(35, -117.5), 0, 'a shorter strip does not count even close, unless asked');
  assert.strictEqual(R.coverage([site(36, -118, 2300, 'short', 2)], glide, 45000).at(35, -118), 0, 'a shorter strip does not count unless asked');
  assert.strictEqual(R.coverage([site(36, -118, 2300, 'short', 2)], glide, 45000, { short: true }).at(35, -118), 1, 'and counts when asked');
  // at 5,000 ft the radius is nothing, but within 12 nmi (the pattern) a site is still in reach
  const low = R.coverage([s1], glide, 5000);
  assert.strictEqual(low.at(35.1, -118), 1);
  assert.strictEqual(low.at(35.4, -118), 0);
  // the height at a place can be a function: low near the start, high far away
  const climbing = R.coverage([s1], glide, (la, lo) => (geo.course(START, [la, lo]).ft / NM < 50 ? 10000 : 45000));
  const out = (nm) => { const p = geo.along([35, -118], 90, nm * NM); return climbing.names(p[0], p[1]).length; };
  assert.strictEqual(out(40), 0, '40 nmi out the aircraft is at 10,000 ft: its radius there is the 12 nmi of the pattern, no more');
  assert.strictEqual(out(60), 1, '60 nmi out it is at 45,000 ft: in reach');
  // the metrics against an independent sampler on 10 random paths
  for (let k = 1; k <= 10; k++) {
    const rnd = sd(100 + k);
    const sites = [site(34.5 + rnd(), -117 + rnd() * 3), site(35 + rnd(), -113 + rnd() * 3, 3000), site(34 + rnd(), -110 + rnd() * 3, 1500)];
    const path = [[35, -118, 40000], [35 + rnd() - 0.5, -113 + rnd(), 50000 - rnd() * 8000], [35 + rnd() - 0.5, -108 + rnd() * 2, 45000], [35, -105, 12000]];
    const m = R.coverageOf(path, sites, glide);
    // independent: walk the path by the metre
    let covered = 0; let n = 0; let gap = 0; let longest = 0; let fewest = 99;
    for (let i = 0; i + 1 < path.length; i++) {
      const d = geo.course(path[i], path[i + 1]).ft / NM;
      for (let x = 0; x < d; x += 2) {
        const f = x / d;
        const q = [path[i][0] + (path[i + 1][0] - path[i][0]) * f, path[i][1] + (path[i + 1][1] - path[i][1]) * f];
        const alt = path[i][2] + (path[i + 1][2] - path[i][2]) * f;
        const k2 = sites.filter((s) => geo.course(q, [s.lat, s.lon]).ft / NM <= Math.max(12, 0.85 * glide(alt, s.elev_ft) - 5.3)).length;
        n++; fewest = Math.min(fewest, k2);
        if (k2) { covered++; gap = 0; } else { gap += 2; longest = Math.max(longest, gap); }
      }
    }
    assert.ok(Math.abs(m.share - covered / n) < 0.02, `path ${k}: share ${m.share.toFixed(3)} against ${(covered / n).toFixed(3)}`);
    assert.ok(Math.abs(m.longest_gap_nm - longest) <= 4, `path ${k}: gap ${m.longest_gap_nm} against ${longest}`);
    assert.ok(m.fewest <= fewest + 1 && m.fewest >= fewest - 1, `path ${k}: fewest ${m.fewest} against ${fewest}`);
  }
}
{
  // E2 Require: a property test over random sets of sites
  let found = 0;
  for (let k = 1; k <= 20; k++) {
    const rnd = sd(300 + k);
    const o0 = mk(400, { altitudes: [45000] });
    const sites = [site(35, -118, 2300, 'HOME'), site(o0.goal[0], o0.goal[1], 2300, 'GOAL')];
    for (let i = 0; i < 45 + Math.floor(rnd() * 20); i++) sites.push(site(33.5 + rnd() * 3, -117 + rnd() * 7, 1500 + rnd() * 3000, "S" + i));
    const r = R.plan(Object.assign({}, o0, { sites, glide, siteMode: 'require' }));
    if (r.ok) {
      found++;
      const m = covIndep(o0, r.best.points, sites);
      assert.ok(m.longest_gap_nm <= 6, `set ${k}: a stretch of ${m.longest_gap_nm} nmi out of reach in a Require route (the lattice's tolerance is a join's 4 nmi sample and a 1.5 nmi cell)`);
      assert.ok(r.best.coverage.longest_gap_nm <= 6, 'and the card says the same');
    } else {
      assert.ok(/landing site in glide reach/.test(r.error), r.error);
      assert.ok(R.plan(Object.assign({}, o0, { sites, glide, siteMode: 'prefer' })).ok, `set ${k}: Prefer finds a route where Require does not`);
    }
  }
  assert.ok(found >= 5, `Require found a route in only ${found} of 20 sets`);
}
{
  // E3 Prefer, Off, and Off is the same as no sites
  const o0 = mk(400, { altitudes: [45000] });
  const sites = [site(35, -118, 2300, 'HOME'), site(o0.goal[0], o0.goal[1], 2300, 'GOAL'), site(36.2, -114.2, 2300, 'NORTH')];
  const gapOf = (r) => covIndep(o0, r.best.points, sites).longest_gap_nm;
  const off = R.plan(Object.assign({}, o0, { sites, glide, siteMode: 'off' }));
  const none = R.plan(o0);
  assert.strictEqual(JSON.stringify(off), JSON.stringify(none), 'Off is the same as leaving the sites out');
  const prefer = R.plan(Object.assign({}, o0, { sites, glide, siteMode: 'prefer' }));
  assert.ok(prefer.ok && off.ok);
  const directNm = geo.course(START, o0.goal).ft / NM;
  assert.ok(gapOf(off) > 0, 'the direct route has a gap in the cover: ' + gapOf(off));
  assert.ok(gapOf(prefer) <= gapOf(off), `Prefer's longest gap ${gapOf(prefer)} is no longer than Off's ${gapOf(off)}`);
  assert.ok(gapOf(prefer) < gapOf(off) || prefer.best.path_nm >= off.best.path_nm, 'it shortens the gap, or it could not');
  assert.ok(prefer.best.path_nm <= directNm * 1.35, 'a detour of at most a third');
  assert.ok(prefer.best.path_nm > off.best.path_nm - 1e-9, 'and it costs distance');
}

// ------------------------------------------------------------------ several routes
{
  // A1 to A5 on random wind fields, with zones, a hazard and sites
  let merged = 0;
  const t0 = Date.now();
  for (let k = 1; k <= 10; k++) {
    const rnd = sd(500 + k);
    const lat0 = 35.5 + rnd() * 2;
    const spd = 30 + rnd() * 60;
    const dir = rnd() < 0.5 ? 270 : 90;
    const o0 = mk(600, { wind: (la) => (Math.abs(la - lat0) < 1 ? { spd, dir } : null), zones: [circle('R-A', 35 + rnd(), -112 + rnd() * 2, 20)], hazards: [haz('SIGMET A', 'convective', 0, 41000, box(35 + rnd(), -109 + rnd(), 0.5, 0.6))], altitudes: [45000, 50000] });
    const sites = [site(35, -118, 2300, 'HOME'), site(o0.goal[0], o0.goal[1], 2300, 'GOAL')];
    for (let i = 0; i < 8; i++) sites.push(site(33.5 + rnd() * 3.5, -117 + rnd() * 8, 2000, 'S' + i));
    const r = R.alternatives(Object.assign({}, o0, { sites, glide, siteMode: 'prefer' }));
    assert.ok(r.ok, r.error);
    const card = (n) => r.routes.find((c) => c.names.includes(n));
    const fuel = card('Least fuel');
    const fast = card('Fastest');
    assert.ok(fuel && fast, 'both cards exist');
    assert.ok(fast.time_s <= fuel.time_s + 1e-6, `field ${k}: Fastest ${fast.time_s} s is slower than Least fuel ${fuel.time_s} s`);
    assert.ok(fuel.fuel_lb <= fast.fuel_lb + 1e-6, `field ${k}: Least fuel burns more than Fastest`);
    assert.strictEqual(r.routes[0].names[0], 'Least fuel', 'A4: Least fuel first');
    assert.strictEqual(r.routes[r.routes.length - 1].id, 'direct', 'and Direct last');
    assert.ok(r.routes.every((c) => c.vs_fuel && Number.isFinite(c.vs_fuel.time_s)), 'each says how it differs from Least fuel');
    // A3: the cautious route's longest gap is zero when Require was possible; its room round the hazard is no less
    const safe = card('Cautious');
    if (safe && !r.notes.length) assert.strictEqual(safe.coverage.longest_gap_nm, 0, 'Cautious with Require: no stretch out of reach');
    const hz = A.make({ rings: o0.hazards[0].rings });
    const room = (c) => Math.min(...sampleLine(line(c), 2).filter((q) => geo.course(START, q).ft / NM > 10 && geo.course(o0.goal, q).ft / NM > 10).map((q) => (A.contains(hz, q[0], q[1]) ? 0 : A.edge(hz, q[0], q[1]).nm)));
    if (safe && fuel !== safe && fuel.alt_ft <= 50000 && safe.alt_ft <= 50000) assert.ok(room(safe) >= room(fuel) - 1, `field ${k}: Cautious room ${room(safe).toFixed(1)} against ${room(fuel).toFixed(1)}`);
    // E4: the card's metrics against the independent sampler
    for (const c of r.routes.filter((x) => x.coverage)) {
      const m = covIndep(o0, c.points, sites);
      assert.ok(Math.abs(m.share - c.coverage.share) < 0.02 && Math.abs(m.longest_gap_nm - c.coverage.longest_gap_nm) <= 4, `field ${k} ${c.names}: the card's metrics: share ${c.coverage.share.toFixed(3)} against ${m.share.toFixed(3)}, gap ${c.coverage.longest_gap_nm} against ${m.longest_gap_nm}`);
    }
    if (r.routes.some((c) => c.names.length > 1)) merged++;
  }
  const per = (Date.now() - t0) / 10;
  assert.ok(per < 3000, `all four cards took ${per} ms on average at 600 nmi`);
  // A2: with nothing in the way the three are one route with three names
  const quiet = R.alternatives(mk(500, { altitudes: [45000] }));
  assert.ok(quiet.ok);
  assert.deepStrictEqual(quiet.routes[0].names, ['Least fuel', 'Fastest', 'Cautious']);
  assert.strictEqual(quiet.routes.length, 2, 'one route and the direct one');
  assert.ok(R.similar(quiet.routes[0], Object.assign({}, quiet.routes[0], { points: quiet.routes[0].points.map((p) => [p[0] + 0.05, p[1], p[2]]) }), 5), 'within 5 nmi is one route');
  assert.ok(!R.similar(quiet.routes[0], Object.assign({}, quiet.routes[0], { points: quiet.routes[0].points.map((p) => [p[0] + 0.2, p[1], p[2]]) }), 5), '12 nmi apart is two');
  assert.ok(!R.similar(quiet.routes[0], Object.assign({}, quiet.routes[0], { alt_ft: 50000 }), 5), 'another height is another route');
  // with the switch off nothing is said about sites
  const none = R.alternatives(mk(500, { altitudes: [45000], sites: [site(35, -118)], glide, siteMode: 'off' }));
  assert.ok(none.routes.every((c) => c.coverage === null || c.coverage === undefined), 'Off: no coverage on the cards');
  // an impossible Require: the cards that cannot be made are said, Cautious falls back to Prefer and says so
  const hard = R.alternatives(mk(400, { altitudes: [45000], sites: [site(35, -118, 2300, 'HOME')], glide, siteMode: 'require' }));
  assert.ok(hard.errors.length >= 1 && /landing site in glide reach/.test(hard.errors[0]), JSON.stringify(hard.errors));
  assert.ok(hard.notes.some((n) => /Cautious/.test(n)));
}

// the join onto the final (P4 of docs/PLAN.md, "The planner uses the aircraft's capability tables"): the route's own corner at the fix, and the teardrop when it arrives from the far side
{
  const cap = require('../js/capability.js');
  const aim = [35, -118];
  const final = 90;
  const fix = geo.along(aim, final + 180, 10 * NM);
  const corners = (pts) => { const out = []; for (let i = 1; i + 1 < pts.length; i++) out.push(Math.abs(geo.turn(geo.course(pts[i - 1], pts[i]).deg, geo.course(pts[i], pts[i + 1]).deg))); return out; };
  for (const bearing of [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]) { // where the route comes from, bearing from the fix
    const prev = geo.along(fix, bearing, 80 * NM);
    const j = R.joinFinal([prev, fix], { aim, fc, fix_alt_ft: 5800 });
    const turns = corners(j.points.concat([aim]));
    assert.ok(Math.max(...turns) <= 96 && Math.max(...turns) <= cap.turn.max_join_deg, `from ${bearing}: corners ${turns.map(Math.round)}`);
    const here = Math.abs(geo.turn(geo.course(prev, fix).deg, final));
    if (here <= 20) assert.strictEqual(j.points.length, 2, `from ${bearing}: a corner of ${Math.round(here)} deg is left alone`);
    else assert.ok(j.points.length > 2 && j.note, `from ${bearing}: a corner of ${Math.round(here)} deg is moved out onto the final`);
    assert.ok(Math.abs(geo.turn(geo.course(j.points[j.points.length - 2], fix).deg, final)) < 0.5 || j.points.length === 2, 'the last leg is down the final');
  }
  // without an aiming point nothing is changed
  assert.deepStrictEqual(R.joinFinal([geo.along(fix, 90, 80 * NM), fix], { fc, fix_alt_ft: 5800 }).points.length, 2);
  // the router's own plans on twenty arrivals: no corner over the limit, no leg too short, the fix under the path with room to slow: the assessment has nothing to say
  const plans = [];
  for (let k = 0; k < 20; k++) {
    const F = (k * 47) % 360;
    const fx = geo.along(aim, F + 180, 10 * NM);
    const start = geo.along(fx, (k * 83 + 11) % 360, (90 + ((k * 37) % 300)) * NM);
    const legsFor = (pts) => pc.legs([{ kind: 'route', points: pts }, { kind: 'land', fix: fx, aim }], start, 2300);
    const FMr = require('../js/flightmath.js');
    const fixAlt = Math.round((2300 + FMr.finalFixHeightAgl(10 * NM, 22000)) / 100) * 100; // the height the aircraft's capability asks for over the fix
    const r = R.plan({ start, start_alt_ft: 2400, goal: fx, aim, fix_alt_ft: fixAlt, weight_lb: 22000, fuel_lb: 11000, fc, perf, wind: null, hours: 0, zones: [], hazards: [], now: T0, legsFor, altitudes: [20000, 30000] });
    assert.ok(r.ok, `case ${k}: ${r.error}`);
    const plan = { field: { lat: aim[0], lon: aim[1], elev_ft: 2300 }, items: [{ kind: 'route', points: r.best.points }, { kind: 'land', fix: fx, aim, elev_ft: 2300 }] };
    assert.deepStrictEqual(pc.assess(plan, { weight_lb: 22000 }), [], `case ${k}`);
    plans.push(r.best.join ? 1 : 0);
  }
  assert.ok(plans.reduce((a, b) => a + b, 0) >= 5, 'about half of the arrivals need a join: ' + plans.join(''));
}
// the page's version lets it breathe between the ways of choosing, and says which is next, and gives the same cards
(async () => {
  const o = mk(500, { altitudes: [45000], sites: [site(35, -118)], glide, siteMode: 'prefer', zones: [circle('R-X', 35.2, -112, 15)] });
  const steps = [];
  const a = await R.alternativesAsync(o, (n) => steps.push(n));
  assert.deepStrictEqual(steps, ['Least fuel', 'Fastest', 'Cautious']);
  assert.strictEqual(JSON.stringify(a), JSON.stringify(R.alternatives(o)), 'the same cards');
  console.log('router: ok');
})().catch((e) => { console.error(e); process.exit(1); });
