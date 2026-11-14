/**
 * What the layers need to know: the situation, worked out from the station's telemetry, the aircraft's status and the plan
 * (pure, so that node can test it), and the layers themselves with the rule that brings each up by itself.
 *
 * The rules are written out in docs/PLAN.md ("GCS map layers") and tested in tests/overlayctx.test.js for ten stated situations.
 * Where they lean on NASA's rules for this aircraft (the weather ones) or its human-factors list (the link's footprint) the reason says so.
 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const geo = node ? require('./geo.js') : root.GCS.geo;
  const A = node ? require('./airspace.js') : root.GCS.airspace;
  const W = node ? require('./weather.js') : root.GCS.weather;
  const LR = node ? require('./linkrange.js') : root.GCS.linkrange;
  const AP = node ? require('./airports.js') : root.GCS.airports;
  const P = node ? require('./palette.js') : root.GCS.palette;
  const NM = geo.NM;
  const FL500 = 50000;
  const FIELD_KINDS = ['taxi', 'takeoff', 'land'];
  const HEIGHT_BELOW_AIRPORTS = 18000;
  const HEIGHT_BELOW_TERRAIN = 15000;
  const MIN_AGL_TERRAIN_FT = 1000; // lower than this, on takeoff and landing, all the ground around is "above the aircraft": no use as a picture
  const NEAR_LANDING_NM = 100;
  const TRAFFIC_NM = 60;
  const STRONG_HEADWIND_KT = 40;
  const REFRESH_MS = 1000;

  /** The route points of a plan, with their heights: [{ lat, lon, alt_ft }]. */
  function routePoints(plan, which) {
    const items = which === 'lost' ? (plan && plan.lost_link) || [] : (plan && plan.items) || [];
    const out = [];
    for (const it of items) if (it.kind === 'route') for (const p of it.points) out.push({ lat: p[0], lon: p[1], alt_ft: p[2] === undefined ? 0 : p[2] });
    return out;
  }

  /**
   * The path from the aircraft: its active leg's end and what follows on the plan; or, when that cannot be told (a go to, a hold, no leg),
   * twenty minutes straight ahead on its track. [{ lat, lon, alt_ft }], the aircraft first.
   */
  function pathAhead(own, status, plan) {
    if (!own) return [];
    const here = { lat: own.lat, lon: own.lon, alt_ft: own.alt_ft };
    const pts = routePoints(plan);
    const end = status && status.leg && status.kind === 'route' ? status.leg[1] : null;
    if (end && pts.length) {
      const k = pts.findIndex((p) => Math.abs(p.lat - end[0]) < 0.002 && Math.abs(p.lon - end[1]) < 0.002);
      if (k >= 0) return [here].concat(pts.slice(k));
    }
    if (Number.isFinite(own.track) && own.gs_kt > 50) {
      const p = geo.along([own.lat, own.lon], own.track, (own.gs_kt / 3) * NM);
      return [here, { lat: p[0], lon: p[1], alt_ft: own.alt_ft }];
    }
    return [here];
  }

  class Situation {
    /** deps: { zones: () => [], hazards: () => [], wind: WindField | null, now } */
    constructor(deps) {
      this.deps = deps || {};
      this.at = -Infinity;
      this.cache = null;
    }

    /**
     * input: { now, own: { lat, lon, alt_ft, agl_ft, track, gs_kt, vs_fps } | null, status, plan, editing, station, latency,
     *   traffic: [{ lat, lon, alt_ft, threat }], alertIds: [], cameraLocked, areas: n, hours }
     */
    update(input) {
      const now = input.now === undefined ? Date.now() : input.now;
      const own = input.own || null;
      const s = input.status || null;
      const plan = input.plan || null;
      const started = !!(s && s.started);
      const kind = s && s.kind;
      const engineOut = !!(s && s.contingency === 'engine') || !!input.engineOut;
      const enroute = started && (kind === 'route' || kind === 'hold');
      const contingency = !!(s && (s.contingency || s.link_lost)) || engineOut;
      const field = started && FIELD_KINDS.includes(kind);
      const phase = contingency ? 'contingency' : enroute ? 'enroute' : field ? 'field' : 'idle';
      const airborne = !!(own && (enroute || (started && kind === 'land' && own.alt_ft - ((plan && plan.field && plan.field.elev_ft) || 0) > 100)));
      const alertIds = input.alertIds || [];
      const trafficNear = own ? (input.traffic || []).filter((t) => geo.course([own.lat, own.lon], [t.lat, t.lon]).ft / NM <= TRAFFIC_NM).length : 0;
      const sites = (plan && plan.sites) || [];
      let nearLandingNm = null;
      if (own) for (const st of sites) nearLandingNm = Math.min(nearLandingNm === null ? Infinity : nearLandingNm, geo.course([own.lat, own.lon], st.aim).ft / NM);
      const ctx = {
        now, own, plan, phase, started, kind, enroute, airborne, field, contingency, engineOut, editing: !!input.editing, alertIds, trafficNear, nearLandingNm, cameraLocked: !!input.cameraLocked, areas: input.areas || 0, hours: input.hours || 0,
        station: input.station || '', latency: input.latency || 0,
      };
      // the heavy parts are redone once a second, or at once when the situation they depend on changes (who is asking, what is being done, where the aircraft is)
      const key = [ctx.station, ctx.latency, ctx.editing, kind, started, plan && plan.id, engineOut, contingency, own ? Math.round(own.lat * 100) + '/' + Math.round(own.lon * 100) + '/' + Math.round(own.alt_ft / 100) : '', s && s.leg ? s.leg[1][0] : ''].join('|');
      if (now - this.at >= REFRESH_MS || !this.cache || key !== this.key) {
        this.at = now;
        this.key = key;
        this.cache = this.heavy(ctx, input, plan, s);
      }
      return Object.assign(ctx, this.cache);
    }

    /** The parts that look at every zone and every hazard: done once a second. */
    heavy(ctx, input, plan, s) {
      const own = ctx.own;
      const path = pathAhead(own, s, plan);
      const planPath = plan ? [own ? { lat: own.lat, lon: own.lon, alt_ft: own.alt_ft } : null].concat(routePoints(plan)).filter(Boolean) : [];
      let zones = this.deps.zones ? this.deps.zones() : [];
      // the airspace of the aircraft's own field (the controlled B, C and D around the departure and the landing) is not news to the station
      const homes = ((plan && plan.sites) || []).map((st) => st.aim).concat(plan && plan.field && Number.isFinite(plan.field.lat) ? [[plan.field.lat, plan.field.lon]] : []);
      zones = zones.filter((z) => !(['classB', 'classC', 'classD'].includes(z.kind) && homes.some((h) => A.contains(z, h[0], h[1]))));
      const hazards = this.deps.hazards ? this.deps.hazards() : [];
      const gs = own ? own.gs_kt : 0;
      const look = ctx.editing ? planPath : path;
      const asp = look.length && (ctx.airborne || ctx.editing) ? A.advisories(zones, look, { gs_kt: gs }) : [];
      const hazAdv = look.length && (ctx.airborne || ctx.editing) ? W.hazardAdvisories(hazards, look, { now: ctx.now, gs_kt: gs }) : [];
      // the line-of-sight limit: the station is taken to be at the field
      const field = plan && plan.field;
      const los = LR.isLineOfSight(ctx.station, ctx.latency);
      const stationPos = field && Number.isFinite(field.lat) ? [field.lat, field.lon] : null;
      // only while flying: on the ground and climbing out the straight-ahead path at that low height would "leave" a range that grows as it climbs
      const flying = ctx.enroute || (ctx.contingency && ctx.airborne);
      const link = { los, station: stationPos, elev_ft: field ? field.elev_ft || 0 : 0, m: flying && own && stationPos && los ? LR.margin(stationPos, field.elev_ft || 0, own, path, gs) : null };
      // the wind on the active leg, from the field of winds (when there is one)
      let wind = null;
      if (this.deps.wind && own && path.length > 1) {
        const legs = W.legWinds(path.slice(0, 2), (la, lo, alt) => this.deps.wind.at(la, lo, alt, ctx.hours));
        if (legs.length) wind = legs[0];
      }
      return { path, planPath, asp, hazAdv, link, wind, zonesLoaded: zones.length, hazardsLoaded: hazards.length };
    }
  }

  const hundredsFt = (v) => Math.round(v / 100) * 100;

  /** The aircraft's height above the ground: the telemetry's, or its altitude less the field's. */
  const aglOf = (c) => (c.own && Number.isFinite(c.own.agl_ft) ? c.own.agl_ft : c.own ? c.own.alt_ft - ((c.plan && c.plan.field && c.plan.field.elev_ft) || 0) : 0);

  /** Why the airports are wanted, or null: on the field, in a contingency, when planning, low, or near the landing. */
  function airportsRule(c) {
    const rule = (on, reason) => (on ? { on: true, reason, force: false } : null);
    return c.contingency ? rule(true, c.engineOut ? 'engine out: where it could land' : 'contingency: where it could land')
      : c.field ? rule(true, 'at the field: takeoff or landing')
        : c.editing ? rule(true, 'planning: alternates and the landing')
          : c.airborne && c.own && c.own.alt_ft < HEIGHT_BELOW_AIRPORTS ? rule(true, `below ${HEIGHT_BELOW_AIRPORTS.toLocaleString('en-US')} ft`)
            : c.airborne && c.nearLandingNm !== null && c.nearLandingNm <= NEAR_LANDING_NM ? rule(true, `landing site ${Math.round(c.nearLandingNm)} nmi away`) : null;
  }

  /** Put the layers into a registry. `L` is a Layers; the rules read the ctx that Situation.update gives. */
  function defineLayers(L) {
    const rule = (on, reason, force) => (on ? { on: true, reason, force: !!force } : null);
    L.define({
      id: 'link', group: 'Safety', label: 'Link range', rank: 10, colour: P.LAYERS.link,
      tip: 'How far a station that needs line of sight can hear the aircraft at its height (the radio horizon: the most the link could reach, over a smooth earth, not what it does reach). Comes up by itself near the limit.',
      auto: (c) => LR.rule(c.link.los, c.link.m),
    });
    L.define({
      id: 'traffic', group: 'Safety', label: 'Traffic', rank: 12, budget: false,
      tip: 'Other aircraft FlightGear has (AI and multiplayer). Auto: any within 60 nmi; always while a traffic alert stands.',
      auto: (c) => (c.alertIds.includes('traffic') ? rule(true, 'a traffic alert stands', true) : rule(c.trafficNear > 0, `${c.trafficNear} aircraft within ${TRAFFIC_NM} nmi`)),
    });
    L.define({
      id: 'reach', group: 'Safety', label: 'Glide reach', rank: 14, budget: false,
      tip: 'How far the aircraft\'s own planner would count on gliding without the engine, and what it would have in hand at each landing site. Auto: while flying; always when the engine is out.',
      auto: (c) => (c.engineOut ? rule(true, 'the engine is out', true) : rule(c.enroute, 'flying: where it could glide to')),
    });
    L.define({
      id: 'airspace', group: 'Safety', label: 'Airspace', rank: 20, colour: P.LAYERS.airspace,
      tip: 'Restricted, prohibited, warning, danger and alert areas, MOAs, TFRs and controlled B, C, D. Auto shows the zones that reach the aircraft\'s height; On shows all heights. Times of use are not read. From a file you load or from the FAA\'s open service (US).',
      auto: (c) => (c.asp.length ? rule(true, shortAdv(c.asp[0])) : c.editing ? rule(true, 'planning: the plan against the airspace') : null),
    });
    L.define({
      id: 'wx-hazard', group: 'Weather', label: 'Weather hazards', rank: 22, colour: P.LAYERS['wx-hazard'],
      tip: 'SIGMET and G-AIRMET areas for turbulence, icing, convection and ash, at the aircraft\'s height. Real-world data, through the helper (tools/awc-proxy.js). Comes up when one meets the path (NASA\'s 2012 rules for this aircraft).',
      auto: (c) => (c.hazAdv.length ? rule(true, shortAdv(c.hazAdv[0])) : null),
    });
    L.define({
      id: 'airports', group: 'Ground', label: 'Airports', rank: 24, colour: P.LAYERS.airports, mode: 'auto',
      tip: 'Fields with a long runway, marked by whether the aircraft could land there at its present weight (from the station\'s landing forecast, plus 800 ft for the aiming point) or only lighter. On shows all of them. Auto: on the field, in a contingency, when planning, below 18,000 ft or near the landing.',
      auto: airportsRule,
    });
    L.define({
      id: 'terrain', group: 'Ground', label: 'Terrain', rank: 26, colour: P.LAYERS.terrain,
      tip: 'Ground that is within 500 ft of the aircraft\'s height (lighter) or above it (darker), from Terrarium elevation tiles. Auto: flying below 15,000 ft and more than 1,000 ft above the ground, and when the engine is out.',
      auto: (c) => (c.engineOut && c.airborne ? rule(true, 'engine out: the ground it is gliding over') : c.airborne && c.own && c.own.alt_ft < HEIGHT_BELOW_TERRAIN && aglOf(c) > MIN_AGL_TERRAIN_FT ? rule(true, `below ${HEIGHT_BELOW_TERRAIN.toLocaleString('en-US')} ft`) : null),
    });
    L.define({
      id: 'wx-radar', group: 'Weather', label: 'Rain radar', rank: 30,
      tip: 'The newest radar picture (RainViewer). Real-world weather, not the simulator\'s. Auto: at or below FL500 while flying, where NASA\'s rule is to stay 25 nmi from thunderstorms.',
      auto: (c) => rule(c.enroute && c.own && c.own.alt_ft <= FL500, 'at or below FL500: NASA\'s rule is 25 nmi from thunderstorms'),
    });
    L.define({
      id: 'wx-sat', group: 'Weather', label: 'Cloud tops (infrared)', rank: 32,
      tip: 'Infrared satellite: the colder, the higher the cloud top. NASA GIBS (GOES, Himawari) or EUMETSAT (Meteosat), whichever looks at the map\'s centre. Auto: above FL500 while flying, where tops matter, and when planning.',
      auto: (c) => (c.enroute && c.own && c.own.alt_ft > FL500 ? rule(true, 'above FL500: cloud tops matter (cold = high)') : c.editing ? rule(true, 'planning: cloud tops along the route') : null),
    });
    L.define({
      id: 'wind', group: 'Weather', label: 'Winds aloft', rank: 34, colour: P.LAYERS.wind,
      tip: 'Wind arrows at the pressure level nearest the aircraft\'s height (Open-Meteo), and the head or tail wind on each leg. Auto: when planning, and when a headwind of 40 kt or more is on the leg.',
      auto: (c) => (c.editing ? rule(true, 'planning: head and tail winds on each leg') : c.wind && c.wind.tail_kt <= -STRONG_HEADWIND_KT ? rule(true, `headwind ${Math.round(-c.wind.tail_kt)} kt on this leg`) : null),
    });
    L.define({
      id: 'metar', group: 'Weather', label: 'Airport weather (METAR)', rank: 25,
      tip: 'Wind, visibility and ceiling at the landing sites and the fields shown: the US from the National Weather Service, the rest through the helper. Comes with the airports.',
      auto: (c) => (airportsRule(c) ? rule(true, 'with the airports') : null),
    });
    L.define({
      id: 'areas', group: 'Mission', label: 'Loaded areas', rank: 40, colour: P.LAYERS.areas,
      tip: 'Areas, lines and points from a GeoJSON file you loaded: a survey box, a storm to chase. Drop a file on the map or use Load in this panel.',
      auto: (c) => rule(c.areas > 0, `${c.areas} loaded`),
    });
    L.define({
      id: 'camera', group: 'Mission', label: 'Camera target', rank: 18, budget: false,
      tip: 'The cross and sight line of the belly camera\'s lock. Auto: while it is locked.',
      auto: (c) => rule(c.cameraLocked, 'the camera is locked'),
    });
    L.define({
      id: 'trail', group: 'Mission', label: 'Trail', rank: 60, mode: 'on',
      tip: 'Where the aircraft has been.',
      auto: null,
    });
  }

  /** A line for a chip from an advisory's longer text. */
  function shortAdv(a) {
    return a.text.replace(/^(AIRSPACE|WEATHER): /, '').replace(/ \((?:[^()]*|\([^()]*\))*\)/g, '').replace(/, valid until \d\d:\d\dZ/, '');
  }

  const api = { Situation, defineLayers, aglOf, MIN_AGL_TERRAIN_FT, routePoints, pathAhead, shortAdv, FL500, HEIGHT_BELOW_AIRPORTS, HEIGHT_BELOW_TERRAIN, NEAR_LANDING_NM, TRAFFIC_NM, STRONG_HEADWIND_KT, hundredsFt };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).overlayctx = api;
})(typeof window !== 'undefined' ? window : globalThis);
