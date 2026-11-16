// node tests/overlayctx.test.js
// L8 of the map-layers plan (docs/PLAN.md): each layer's Auto rule, in ten stated situations, and through the registry.
const assert = require('assert');
const X = require('../js/overlayctx.js');
const { Layers } = require('../js/layers.js');
const A = require('../js/airspace.js');
const W = require('../js/weather.js');
const LR = require('../js/linkrange.js');
const geo = require('../js/geo.js');
const plan = require('../js/demoplan.js');

const FIELD = [plan.field.lat, plan.field.lon];
let T = 1000000;
const mk = (deps) => {
  const L = new Layers({ now: () => T });
  X.defineLayers(L);
  const S = new X.Situation(Object.assign({ zones: () => [], hazards: () => [], wind: null }, deps));
  return { L, S };
};
const own = (lat, lon, alt, extra) => Object.assign({ lat, lon, alt_ft: alt, agl_ft: alt - 2300, track: 0, gs_kt: 300, vs_fps: 0 }, extra);
const here = (alt, nmNorth) => { const p = geo.along(FIELD, 0, (nmNorth || 0) * geo.NM); return own(p[0], p[1], alt); };
const status = (kind, extra) => Object.assign({ started: true, kind, contingency: null, link_lost: false }, extra);
const ctxOf = (S, o) => S.update(Object.assign({ now: T, plan, station: 'LRE', latency: 0, traffic: [], alertIds: [] }, o));
const on = (L, ctx, id) => { const r = L.def(id).auto && L.def(id).auto(ctx); return !!(r && r.on); };
const why = (L, ctx, id) => { const r = L.def(id).auto && L.def(id).auto(ctx); return r ? r.reason : null; };
const set = (L, ctx) => ['link', 'traffic', 'reach', 'airspace', 'wx-hazard', 'airports', 'taxiways', 'parking', 'terrain', 'wx-radar', 'wx-sat', 'wind', 'areas', 'camera'].filter((id) => L.def(id).auto && on(L, ctx, id));

// the layers and their groups, as the plan lists them
{
  const { L } = mk();
  assert.deepStrictEqual(L.defs.map((d) => d.id), ['link', 'traffic', 'reach', 'airspace', 'wx-hazard', 'airports', 'taxiways', 'parking', 'terrain', 'wx-radar', 'wx-sat', 'wind', 'metar', 'areas', 'camera', 'trail']);
  assert.strictEqual(L.mode('trail'), 'on');
  assert.ok(L.defs.filter((d) => d.id !== 'trail').every((d) => d.mode === 'auto'), 'everything but the trail starts on Auto');
  assert.ok(L.defs.every((d) => d.tip.length > 20), 'each has a tip');
}

// 1. on the stand, nothing started
{
  const { L, S } = mk();
  const c = ctxOf(S, { own: here(2300), status: { started: false, kind: 'idle' } });
  assert.strictEqual(c.phase, 'idle');
  assert.deepStrictEqual(set(L, c), [], 'a quiet screen');
}
// 2. takeoff
{
  const { L, S } = mk();
  const c = ctxOf(S, { own: here(2400), status: status('takeoff') });
  assert.strictEqual(c.phase, 'field');
  assert.deepStrictEqual(set(L, c), ['airports'], 'no terrain on the runway: all the ground around is above the aircraft');
  assert.ok(/at the field/.test(why(L, c, 'airports')));
}
// 3. climbing through 14,000 and through 16,000 (route, 8 nmi out)
{
  const { L, S } = mk();
  let c = ctxOf(S, { own: here(14000, 8), status: status('route') });
  assert.strictEqual(c.phase, 'enroute');
  assert.deepStrictEqual(set(L, c), ['reach', 'airports', 'terrain', 'wx-radar']);
  c = ctxOf(S, { own: here(16000, 8), status: status('route') });
  assert.deepStrictEqual(set(L, c), ['reach', 'airports', 'wx-radar'], 'above 15,000 the terrain goes');
  c = ctxOf(S, { own: Object.assign(here(2900, 3), { agl_ft: 600 }), status: status('route') });
  assert.ok(!on(L, c, 'terrain'), '600 ft above the ground: too low for a picture');
  c = ctxOf(S, { own: Object.assign(here(3400, 3), { agl_ft: 1100 }), status: status('route') });
  assert.ok(on(L, c, 'terrain'), '1,100 ft above the ground');
  const noAgl = here(3400, 3);
  delete noAgl.agl_ft;
  c = ctxOf(S, { own: noAgl, status: status('route') });
  assert.ok(on(L, c, 'terrain'), 'no height above the ground in the telemetry: the altitude less the field (1,100 ft)');
  c = ctxOf(S, { own: Object.assign(here(2900, 3), { agl_ft: undefined }), status: status('route') });
  assert.ok(!on(L, c, 'terrain'), '600 ft over the field, from the altitude alone');
  c = ctxOf(S, { own: here(18500, 90), status: status('route') });
  assert.deepStrictEqual(set(L, c), ['reach', 'airports', 'wx-radar'], 'above 18,000 but 90 nmi from the landing: within the 100');
  assert.ok(/landing site 90 nmi away/.test(why(L, c, 'airports')));
  c = ctxOf(S, { own: here(18500, 105), status: status('route') });
  assert.deepStrictEqual(set(L, c), ['reach', 'wx-radar'], '105 nmi from the landing and above 18,000: no airports');
}
// 4. cruise at FL600, far from the field: satellite, not radar, no airports
{
  const { L, S } = mk();
  const c = ctxOf(S, { own: own(36.5, -117, 60000), status: status('route') });
  assert.deepStrictEqual(set(L, c), ['reach', 'wx-sat']);
  assert.ok(/above FL500/.test(why(L, c, 'wx-sat')));
}
// 5. cruise at FL450: radar, not satellite; and exactly FL500 is still "at or below"
{
  const { L, S } = mk();
  let c = ctxOf(S, { own: own(36.5, -117, 45000), status: status('route') });
  assert.deepStrictEqual(set(L, c), ['reach', 'wx-radar']);
  assert.ok(/25 nmi from thunderstorms/.test(why(L, c, 'wx-radar')));
  c = ctxOf(S, { own: own(36.5, -117, 50000), status: status('route') });
  assert.ok(on(L, c, 'wx-radar') && !on(L, c, 'wx-sat'));
  c = ctxOf(S, { own: own(36.5, -117, 50001), status: status('route') });
  assert.ok(!on(L, c, 'wx-radar') && on(L, c, 'wx-sat'));
}
// 6. descent, 50 nmi from the landing, 12,000 ft
{
  const { L, S } = mk();
  const c = ctxOf(S, { own: here(12000, 50), status: status('route') });
  assert.deepStrictEqual(set(L, c), ['reach', 'airports', 'terrain', 'wx-radar']);
  const sites = c.nearLandingNm;
  assert.ok(Math.abs(sites - 50) < 1.5, 'the landing is 50 nmi off: ' + sites);
}
// 7. engine out: the glide ring forced, the airports and the ground
{
  const { L, S } = mk();
  const c = ctxOf(S, { own: own(36.5, -117, 55000), status: status('route', { contingency: 'engine' }) });
  assert.strictEqual(c.phase, 'contingency');
  assert.ok(c.engineOut);
  assert.strictEqual(L.def('reach').auto(c).force, true, 'forced');
  assert.ok(/the engine is out/.test(why(L, c, 'reach')));
  assert.ok(on(L, c, 'airports') && /engine out/.test(why(L, c, 'airports')));
  assert.ok(on(L, c, 'terrain'), 'the ground under the glide, even from 55,000 ft');
  // and the lost-link contingency: airports yes, no forced glide ring
  const c2 = ctxOf(S, { own: own(36.5, -117, 55000), status: status('route', { contingency: 'link', link_lost: true }) });
  assert.strictEqual(c2.phase, 'contingency');
  assert.ok(on(L, c2, 'airports'));
  assert.ok(!L.def('reach').auto(c2).force);
}
// 8. the edge of the line of sight: 90 % out and flying outward, for an LRE; nothing for an MCE
{
  const { L, S } = mk();
  const range = LR.rangeNm(40000, plan.field.elev_ft);
  const p = geo.along(FIELD, 90, 0.9 * range * geo.NM);
  const far = own(p[0], p[1], 40000, { track: 90 });
  let c = ctxOf(S, { own: far, status: status('route') });
  const r = L.def('link').auto(c);
  assert.ok(r && r.force && r.on, 'forced at 90 %');
  assert.ok(/line-of-sight limit \d+ nmi at this height/.test(r.reason));
  c = ctxOf(S, { own: far, status: status('route'), station: 'MCE' });
  assert.strictEqual(L.def('link').auto(c), null, 'a satellite station has no ring');
  c = ctxOf(S, { own: far, status: status('route'), station: 'LRE', latency: 1200 });
  assert.strictEqual(L.def('link').auto(c), null, 'nor one with 1.2 s of delay');
  const near = geo.along(FIELD, 90, 0.5 * range * geo.NM);
  c = ctxOf(S, { own: own(near[0], near[1], 40000, { track: 90 }), status: status('route') });
  assert.strictEqual(L.def('link').auto(c), null, '50 %, flying outward at 300 kt: more than 10 minutes to the ring');
}
// 9. planning: the plan being edited
{
  const { L, S } = mk();
  const c = ctxOf(S, { own: here(2300), status: { started: false, kind: 'idle' }, editing: true });
  assert.deepStrictEqual(set(L, c), ['airspace', 'airports', 'wx-sat', 'wind']);
  assert.ok(/planning/.test(why(L, c, 'airspace')));
  assert.ok(c.planPath.length === 5, 'the aircraft and the four route points: ' + c.planPath.length);
}
// 10. a zone ahead on the active leg, and a hazard
{
  const route = plan.items.find((i) => i.kind === 'route').points;
  const a = route[0];
  const mid = [(a[0] + route[1][0]) / 2, (a[1] + route[1][1]) / 2];
  const R = A.make({ name: 'R-9904 TEST', kind: 'restricted', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 99999, ref: 'MSL' }, circle: { lat: mid[0], lon: mid[1], r_ft: 4 * geo.NM } });
  const H = { source: 'SIGMET', id: 'SIGMET TEST', hazard: 'TURB', kind: 'turb', severity: 5, lo_ft: 10000, hi_ft: 30000, from: T - 1000, to: T + 3600000, rings: [[[mid[0] + 0.3, mid[1] - 0.3], [mid[0] + 0.3, mid[1] + 0.3], [mid[0] - 0.3, mid[1] + 0.3], [mid[0] - 0.3, mid[1] - 0.3]]] };
  const { L, S } = mk({ zones: () => [R], hazards: () => [H] });
  const p0 = geo.along([a[0], a[1]], geo.course([a[0], a[1]], [route[1][0], route[1][1]]).deg + 180, 5 * geo.NM);
  const c = ctxOf(S, { own: own(p0[0], p0[1], 20000, { track: geo.course([a[0], a[1]], route[1]).deg }), status: status('route', { leg: [[a[0], a[1]], [route[1][0], route[1][1]]] }) });
  assert.ok(c.asp.length >= 1 && c.asp[0].zone === R, 'the restricted area is on the path');
  assert.ok(on(L, c, 'airspace'));
  assert.ok(/^R-9904 TEST: entered \d+ nmi ahead, in \d+ min$/.test(why(L, c, 'airspace')), why(L, c, 'airspace'));
  assert.ok(on(L, c, 'wx-hazard'));
  assert.ok(/SIGMET TEST turbulence/.test(why(L, c, 'wx-hazard')), why(L, c, 'wx-hazard'));
  // the same zone but the aircraft far above its band: nothing
  const R2 = A.make({ name: 'R-9905 LOW', kind: 'restricted', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 12000, ref: 'MSL' }, circle: { lat: mid[0], lon: mid[1], r_ft: 4 * geo.NM } });
  const m2 = mk({ zones: () => [R2] });
  const c2 = ctxOf(m2.S, { own: own(p0[0], p0[1], 20000), status: status('route', { leg: [[a[0], a[1]], [route[1][0], route[1][1]]] }) });
  assert.ok(!on(m2.L, c2, 'airspace'));
}
// 10b. the airspace of the aircraft's own field is not news; another field's is, and nothing is advised on the ground
{
  const home = A.make({ name: 'HOME CLASS D', kind: 'classD', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 4800, ref: 'MSL' }, circle: { lat: FIELD[0], lon: FIELD[1], r_ft: 5 * geo.NM } });
  const p2 = geo.along(FIELD, 0, 25 * geo.NM);
  const other = A.make({ name: 'OTHER CLASS D', kind: 'classD', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 4800, ref: 'MSL' }, circle: { lat: p2[0], lon: p2[1], r_ft: 5 * geo.NM } });
  const { L, S } = mk({ zones: () => [home, other] });
  let c = ctxOf(S, { own: here(2300), status: status('takeoff') });
  assert.strictEqual(c.asp.length, 0, 'on the ground at the field: nothing');
  assert.ok(!on(L, c, 'airspace'));
  c = ctxOf(S, { own: here(3000, 1), status: status('route'), });
  assert.deepStrictEqual(c.asp.map((a) => a.zone.name), ['OTHER CLASS D'], 'climbing out through HOME CLASS D: only the other one is news');
  assert.ok(on(L, c, 'airspace'));
}
// 11. traffic, areas, the camera
{
  const { L, S } = mk();
  const p = geo.along(FIELD, 0, 30 * geo.NM);
  const t = [{ lat: p[0], lon: p[1], alt_ft: 30000 }];
  let c = ctxOf(S, { own: here(30000, 0), status: status('route'), traffic: t });
  assert.ok(on(L, c, 'traffic') && /1 aircraft within 60 nmi/.test(why(L, c, 'traffic')));
  assert.ok(!L.def('traffic').auto(c).force);
  c = ctxOf(S, { own: here(30000, 0), status: status('route'), traffic: t, alertIds: ['traffic'] });
  assert.strictEqual(L.def('traffic').auto(c).force, true, 'forced while the alert stands');
  c = ctxOf(S, { own: here(30000, 0), status: status('route'), traffic: [{ lat: p[0] + 3, lon: p[1], alt_ft: 30000 }] });
  assert.ok(!on(L, c, 'traffic'), 'more than 60 nmi away');
  c = ctxOf(S, { own: here(30000, 0), status: status('route'), cameraLocked: true, areas: 2 });
  assert.ok(on(L, c, 'camera') && on(L, c, 'areas'));
}
// 12. a strong headwind on the leg brings the winds
{
  const route = plan.items.find((i) => i.kind === 'route').points;
  const course = geo.course(FIELD, [route[0][0], route[0][1]]).deg;
  const wind = { at: () => ({ spd: 60, dir: course }) }; // from the direction it is flying to: a headwind
  const { L, S } = mk({ wind });
  const c = ctxOf(S, { own: here(60000, 0, { track: course }), status: status('route', { leg: [FIELD, [route[0][0], route[0][1]]] }) });
  assert.ok(c.wind && c.wind.tail_kt < -59, 'a 60 kt headwind: ' + JSON.stringify(c.wind));
  assert.ok(on(L, c, 'wind') && /headwind 60 kt on this leg/.test(why(L, c, 'wind')));
  const calm = mk({ wind: { at: () => ({ spd: 30, dir: course }) } });
  assert.ok(!on(calm.L, ctxOf(calm.S, { own: here(60000, 0), status: status('route', { leg: [FIELD, [route[0][0], route[0][1]]] }) }), 'wind'), '30 kt is not enough');
}

// through the registry: an engine out wants four layers; three show, the forced one stays out of the count, and the radar waits
{
  const { L, S } = mk();
  const c = () => ctxOf(S, { own: own(36.5, -117, 45000), status: status('route', { contingency: 'engine' }) });
  L.update(c());
  T += 2100;
  L.update(c());
  const shown = L.defs.filter((d) => L.shown(d.id)).map((d) => d.id).sort();
  assert.deepStrictEqual(shown, ['airports', 'metar', 'reach', 'terrain', 'trail'], shown.join());
  assert.strictEqual(L.state('reach').source, 'forced');
  assert.deepStrictEqual(L.waiting(), ['wx-radar'], 'the radar waits for a place');
  assert.ok(L.chips().some((x) => x.id === 'reach' && x.forced));
  // and a quiet screen has only the trail
  const q = mk();
  q.L.update(ctxOf(q.S, { own: here(2300), status: { started: false, kind: 'idle' } }));
  T += 2100;
  q.L.update(ctxOf(q.S, { own: here(2300), status: { started: false, kind: 'idle' } }));
  assert.deepStrictEqual(q.L.defs.filter((d) => q.L.shown(d.id)).map((d) => d.id), ['trail']);
}

// 13. the airport's ground map (stage 1 of starting at a stand): the taxiways and the stands come up while planning at that airport, the taxiways also while taxiing,
// both while the aircraft stands with the plan not begun; never without a map, never in flight
{
  const { L, S } = mk();
  const ground = { icao: 'XDM1', stands: 3 };
  const stood = { own: Object.assign(here(2305), { agl_ft: 5, gs_kt: 0 }), status: { started: false, kind: 'idle' } };
  let c = ctxOf(S, Object.assign({ ground: null }, stood));
  assert.deepStrictEqual(set(L, c), [], 'no map from the aircraft: nothing to show');
  c = ctxOf(S, Object.assign({ ground }, stood));
  assert.deepStrictEqual(set(L, c), ['taxiways', 'parking']);
  assert.strictEqual(why(L, c, 'parking'), 'on the ground at XDM1: the stands');
  c = ctxOf(S, { ground, own: Object.assign(here(2305), { agl_ft: 5, gs_kt: 0 }), status: status('taxi'), editing: false });
  assert.deepStrictEqual(set(L, c), ['airports', 'taxiways'], 'taxiing: the taxiways, not the stands');
  assert.strictEqual(why(L, c, 'taxiways'), 'taxiing at XDM1');
  c = ctxOf(S, { ground, own: here(15000, 8), status: status('route') });
  assert.ok(!set(L, c).includes('taxiways') && !set(L, c).includes('parking'), 'in flight neither');
  c = ctxOf(S, { ground, own: here(15000, 8), status: { started: false, kind: 'idle' }, editing: true });
  assert.deepStrictEqual(set(L, c).filter((x) => x === 'taxiways' || x === 'parking'), ['taxiways', 'parking'], 'planning: both');
  assert.strictEqual(why(L, c, 'taxiways'), 'planning at XDM1: the taxiways');
  assert.ok(L.def('taxiways').budget === false && L.def('parking').budget === false, 'they do not take a place from the safety layers');
  assert.ok(L.def('taxiways').group === 'Ground' && L.def('parking').group === 'Ground');
}

// pathAhead: along the plan from the active leg's end, or straight on
{
  const route = plan.items.find((i) => i.kind === 'route').points;
  const o = own(35.1, -117.7, 20000, { track: 30, gs_kt: 300 });
  const along = X.pathAhead(o, status('route', { leg: [[0, 0], [route[1][0], route[1][1]]] }), plan);
  assert.strictEqual(along.length, 1 + 3, 'the aircraft, then route points 2 to 4');
  assert.strictEqual(along[1].lat, route[1][0]);
  assert.strictEqual(along[1].alt_ft, route[1][2]);
  const straight = X.pathAhead(o, status('hold'), plan);
  assert.strictEqual(straight.length, 2);
  assert.ok(Math.abs(geo.course([o.lat, o.lon], [straight[1].lat, straight[1].lon]).ft / geo.NM - 100) < 0.5, 'twenty minutes at 300 kt is 100 nmi');
  assert.strictEqual(X.pathAhead(null, null, plan).length, 0);
  assert.strictEqual(X.pathAhead(own(35, -117, 100, { gs_kt: 10 }), null, plan).length, 1, 'standing still: just the aircraft');
  assert.strictEqual(X.routePoints(plan, 'lost').length, 1);
  assert.strictEqual(X.shortAdv({ text: 'AIRSPACE: R-9903 TEST (restricted, FL180 to unlimited): entered 60 nmi ahead, in 12 min' }), 'R-9903 TEST: entered 60 nmi ahead, in 12 min');
}
console.log('overlayctx: ok');
