/**
 * The layers on the page: what is drawn on the map for each, the data each one fetches, and the panel that chooses them.
 * (The rules that bring a layer up by itself are in js/overlayctx.js; the registry is js/layers.js.)
 *
 * Nothing here opens a window or moves the map. Every request to someone else's server is made through `this.net`, which
 * is off when the page was told to go offline (the tiles and data requests show the area being looked at to whoever serves them).
 */
(function (root) {
  'use strict';
  const G = root.GCS;
  const geo = G.geo;
  const T = G.tiles;
  const A = G.airspace;
  const W = G.weather;
  const AP = G.airports;
  const LR = G.linkrange;
  const X = G.overlayctx;
  const PAL = G.palette;
  const NM = geo.NM;
  const FONT = '11px ui-sans-serif, system-ui, sans-serif';
  const HAZARD_COLOURS = { turb: PAL.LAYERS['wx-hazard'], ice: '#9fb7ff', convective: '#c0392b', ash: '#8d8d8d' };
  const CAT_COLOURS = { VFR: '#3fa84d', MVFR: '#4a7fe0', IFR: '#e04a4a', LIFR: '#c040c0' };
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /** The latitude/longitude box [lat0, lon0, lat1, lon1] the map shows. */
  function viewBox(map) {
    const c = [map.unproject(0, 0), map.unproject(map.w, 0), map.unproject(0, map.h), map.unproject(map.w, map.h)];
    return [Math.min(...c.map((p) => p[0])), Math.min(...c.map((p) => p[1])), Math.max(...c.map((p) => p[0])), Math.max(...c.map((p) => p[1]))];
  }

  const hexAlpha = (hex, a) => `rgba(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(',')},${a})`;

  /** GeoJSON the user loaded that is not airspace: polygons, lines and points to draw as they are. */
  function parseAreas(json, name) {
    const feats = json && json.type === 'FeatureCollection' ? json.features : json && json.type === 'Feature' ? [json] : [];
    const out = [];
    const swap = (r) => r.map((c) => [c[1], c[0]]);
    for (const f of feats) {
      const g = f.geometry;
      if (!g) continue;
      const p = f.properties || {};
      const label = p.name || p.NAME || p.title || '';
      if (g.type === 'Polygon') out.push({ kind: 'polygon', rings: [swap(g.coordinates[0])], name: label, file: name });
      else if (g.type === 'MultiPolygon') g.coordinates.forEach((q) => out.push({ kind: 'polygon', rings: [swap(q[0])], name: label, file: name }));
      else if (g.type === 'LineString') out.push({ kind: 'line', pts: swap(g.coordinates), name: label, file: name });
      else if (g.type === 'MultiLineString') g.coordinates.forEach((l) => out.push({ kind: 'line', pts: swap(l), name: label, file: name }));
      else if (g.type === 'Point') out.push({ kind: 'point', p: [g.coordinates[1], g.coordinates[0]], name: label, file: name });
    }
    return out;
  }

  /** Is this GeoJSON airspace (records with limits or a type) rather than plain areas? */
  const looksLikeAirspace = (json) => {
    const feats = (json && (json.features || json.items)) || (Array.isArray(json) ? json : []);
    return feats.some((f) => {
      const p = f.properties || f;
      return ['TYPE_CODE', 'LOWER_VAL', 'UPPER_VAL', 'lowerLimit', 'upperLimit', 'icaoClass', 'lower_ft', 'upper_ft', 'kind'].some((k) => p[k] !== undefined);
    });
  };

  class Overlays {
    /**
     * o: { map, layers, store, fetch, demo, awc, tiles (a ?tiles= base address), offline, panel: { button, declutter, chips, box, legend }, now }
     */
    constructor(o) {
      this.map = o.map;
      this.layers = o.layers;
      this.fetch = o.fetch;
      this.now = o.now || (() => Date.now());
      this.demo = !!o.demo;
      this.tilesOverride = o.tiles || null;
      this.store = o.store || null;
      this.dom = o.panel || null;
      this.prefs = Object.assign({ base: 'dark', offline: false, windHours: 0 }, o.prefs || {});
      if (o.offline) this.prefs.offline = true;
      this.cache = new T.TileCache({ makeImage: () => new root.Image(), onChange: () => this.redraw() });
      this.userZones = [];
      this.faaZones = [];
      this.faaCells = new Map();
      this.faaRetryAt = 0;
      this.faaStatus = o.demo ? '' : 'FAA open data: not asked yet';
      this.areas = [];
      this.rain = null;
      this.rainAt = -Infinity;
      this.rainStatus = 'off';
      this.fileStatus = '';
      this.drawnFields = [];
      this.ground = null; // the ground network the aircraft sent (js/ground.js Net), or null
      this.groundStatus = '';
      this.stand = null; // the plan's stand: { at: [lat, lon], heading }
      this.airports = new AP.Airports({ fetch: (u) => this.net(u), store: o.store || null, base: o.sourcesBase });
      this.hazards = new W.Hazards({ fetch: (u) => this.net(u), awc: o.awc || null });
      this.metars = new W.Metars({ fetch: (u) => this.net(u), awc: o.awc || null });
      this.wind = this.demo ? new G.demodata.DemoWind() : new W.WindField({ fetch: (u) => this.net(u) });
      this.demoZones = this.demo ? G.demodata.zones() : [];
      if (this.demo) {
        this.airports.list = G.demodata.airports();
        this.airports.coverage = { centre: G.demodata.FIELD, radius_nm: 500 };
        this.airports.status = 'made-up fields for the demo';
        this.hazardsDemo = G.demodata.hazards(this.now());
        this.hazards.status = 'a made-up area for the demo';
        this.metars.byId.set('XDM1', G.demodata.metar(this.now()));
        this.metars.status = 'made-up report for the demo';
      }
      this.situation = new X.Situation({ zones: () => this.zones(), hazards: () => this.hazardList(), wind: this.wind });
      this.last = null;
      this.ctx = null;
      this.pending = false;
      this.install();
      if (this.dom) this.buildPanel();
      if (this.store) this.restore();
    }

    /** The airport's ground network, from the aircraft (null: none); drawn by the Taxiways and Stands layers. */
    setGround(net, status) {
      this.ground = net;
      this.groundStatus = status || (net ? `${net.icao}: ${net.parking.length} stands, ${net.arcs.length} taxiway segments` : '');
      this.redraw();
    }

    /** Every request to a third party goes through here: refused when the page is offline. */
    net(url, opts) {
      if (this.prefs.offline) return Promise.reject(new Error('offline: the page was told not to ask anyone'));
      return this.fetch(url, opts);
    }

    zones() {
      return this.userZones.concat(this.faaZones, this.demoZones);
    }

    hazardList() {
      return this.hazards.list.concat(this.hazardsDemo || []);
    }

    redraw() {
      if (this.pending) return;
      this.pending = true;
      (root.requestAnimationFrame || ((f) => setTimeout(f, 16)))(() => {
        this.pending = false;
        this.map.draw();
      });
    }

    async restore() {
      const z = await this.store.get('zones-user');
      if (Array.isArray(z) && z.length) this.userZones = z;
      const a = await this.store.get('areas-user');
      if (Array.isArray(a) && a.length) this.areas = a;
      await this.airports.restore();
      this.redraw();
    }

    setPref(k, v) {
      this.prefs[k] = v;
      this.layers.save({ prefs: this.prefs });
      this.redraw();
    }

    /* ------------------------------------------------------------------ files */
    /** Files the user loaded or dropped: airspace (OpenAir, GeoJSON, OpenAIP), airports and runways (OurAirports CSV), areas (GeoJSON). */
    async loadFiles(files) {
      const texts = [];
      for (const f of files) texts.push({ name: f.name, text: await f.text() });
      const csvAp = texts.find((t) => /latitude_deg/.test(t.text.slice(0, 600)) && /ident/.test(t.text.slice(0, 600)));
      const csvRw = texts.find((t) => /airport_ident/.test(t.text.slice(0, 600)) && /length_ft/.test(t.text.slice(0, 600)));
      const notes = [];
      if (csvAp) {
        const n = this.airports.addFile(csvAp.text, csvRw ? csvRw.text : null);
        notes.push(`${n} fields from ${csvAp.name}${csvRw ? '' : ' (no runways file: their runways are unknown)'}`);
      }
      for (const t of texts) {
        if (t === csvAp || t === csvRw) continue;
        let json = null;
        const s = t.text.trim();
        if (s[0] === '{' || s[0] === '[') {
          try {
            json = JSON.parse(s);
          } catch (e) {
            notes.push(`${t.name}: not valid JSON`);
            continue;
          }
        }
        if (json && !looksLikeAirspace(json)) {
          const got = parseAreas(json, t.name);
          this.areas = this.areas.filter((a) => a.file !== t.name).concat(got);
          if (this.store) this.store.set('areas-user', this.areas);
          notes.push(`${got.length} areas from ${t.name}`);
        } else {
          const got = A.parse(t.text);
          got.forEach((z) => (z.src = t.name));
          this.userZones = this.userZones.filter((z) => z.src !== t.name).concat(got);
          if (this.store) this.store.set('zones-user', this.userZones);
          notes.push(got.length ? `${got.length} airspace zones from ${t.name}` : `${t.name}: nothing in it that this page reads (OpenAir, GeoJSON, OpenAIP JSON, OurAirports CSV)`);
        }
      }
      this.fileStatus = notes.join('; ');
      this.refreshPanel();
      this.redraw();
      return this.fileStatus;
    }

    /* ------------------------------------------------------------------ the page's heartbeat */
    /**
     * Called every few hundred ms with the situation: works out what to fetch and puts the layers' switches where map.js draws.
     */
    tick(ctx) {
      this.ctx = ctx;
      const L = this.layers;
      const now = this.now();
      const m = this.map;
      m.data.show = { trail: L.shown('trail'), traffic: L.shown('traffic'), reach: L.shown('reach'), camera: L.shown('camera') };
      if (this.prefs.offline) {
        this.refreshPanel();
        return;
      }
      const own = ctx.own;
      const centre = m.centre;
      // airspace for the area of the plan and the aircraft: wanted even while the layer is hidden, because the rule that brings it up needs it
      if ((ctx.started || ctx.editing || own) && !this.demo) this.wantFaa(ctx);
      if (L.shown('airports') && !this.demo) this.airports.ensure([centre[0], centre[1]], 500);
      if (this.hazards.awc) this.hazards.ensure();
      if (own && (ctx.enroute || ctx.editing || L.shown('wind')) && !this.demo) {
        const box = this.windBox(ctx);
        if (box) this.wind.ensure(box, W.levelFor(own.alt_ft));
      }
      if (L.shown('wx-radar') && now - this.rainAt > 300000) this.loadRain();
      if (L.shown('metar')) this.wantMetars();
      this.refreshPanel();
    }

    windBox(ctx) {
      const pts = (ctx.editing ? ctx.planPath : ctx.path).concat(ctx.own ? [{ lat: ctx.own.lat, lon: ctx.own.lon }] : []);
      if (!pts.length) return null;
      const la = pts.map((p) => p.lat);
      const lo = pts.map((p) => p.lon);
      const v = this.map.w ? viewBox(this.map) : null;
      return [Math.min(...la, v ? v[0] : 90) - 0.5, Math.min(...lo, v ? v[1] : 180) - 0.5, Math.max(...la, v ? v[2] : -90) + 0.5, Math.max(...lo, v ? v[3] : -180) + 0.5].map((x, i) => (i < 2 ? Math.max(i ? -180 : -85, x) : Math.min(i === 2 ? 85 : 180, x)));
    }

    /** The FAA's open airspace service covers the US: ask for 2-degree cells around the plan and the aircraft, one at a time, backing off when it is busy. */
    wantFaa(ctx) {
      if (this.faaBusy || this.now() < this.faaRetryAt) return;
      const pts = ctx.planPath.concat(ctx.own ? [ctx.own] : []);
      if (!pts.length) return;
      const cells = new Set();
      for (const p of pts) {
        if (p.lat < 15 || p.lat > 72 || p.lon < -180 || p.lon > -60) continue; // outside the service's area
        for (const [di, dj] of [[0, 0], [0, 1], [1, 0], [1, 1], [-1, 0], [0, -1], [-1, -1], [1, -1], [-1, 1]]) cells.add(`${Math.floor(p.lat / 2) + di}/${Math.floor(p.lon / 2) + dj}`);
      }
      const todo = [...cells].find((k) => !this.faaCells.has(k) || this.now() - this.faaCells.get(k) > 86400000);
      if (!todo) return;
      const [i, j] = todo.split('/').map(Number);
      this.faaBusy = true;
      A.loadFaa((u) => this.net(u), [i * 2, j * 2, i * 2 + 2, j * 2 + 2]).then((r) => {
        this.faaBusy = false;
        this.faaStatus = r.status === 'ok' ? `${this.faaZones.length + r.zones.length} zones kept (FAA open data)` : r.status;
        if (r.retryMs) this.faaRetryAt = this.now() + r.retryMs;
        else {
          this.faaCells.set(todo, this.now());
          this.faaZones = this.faaZones.filter((z) => z.cell !== todo).concat(r.zones.map((z) => Object.assign(z, { cell: todo })));
        }
        this.redraw();
      }).catch((e) => {
        this.faaBusy = false;
        this.faaStatus = 'airspace failed: ' + e.message;
        this.faaRetryAt = this.now() + 60000;
      });
    }

    loadRain() {
      this.rainAt = this.now();
      this.net(W.RAIN).then((r) => r.json()).then((j) => {
        this.rain = W.parseRain(j);
        const age = W.ageMin(this.rain.newest, this.now());
        this.rainStatus = this.rain.newest ? `newest frame ${age} min old (RainViewer)` : 'no frames';
        this.redraw();
      }).catch((e) => {
        this.rainStatus = 'radar failed: ' + e.message;
        this.rainAt = this.now() - 240000; // again in a minute
      });
    }

    wantMetars() {
      const ids = this.drawnFields.map((f) => f.ident);
      const plan = this.ctx && this.ctx.plan;
      // the landing sites of the plan first: the nearest field to each
      for (const s of (plan && plan.sites) || []) {
        const n = AP.nearest(this.airports.list, s.aim[0], s.aim[1], 1)[0];
        if (n && n.nm < 3) ids.unshift(n.a.ident);
      }
      if (ids.length && !this.demo) this.metars.ensure([...new Set(ids)]).then(() => this.redraw());
    }

    /* ------------------------------------------------------------------ what the aircraft and the editor are told */
    /** The station's own alerts from the layers: the worst two airspace and the worst two hazard advisories that are inside or ahead. */
    alerts(ctx) {
      if (!ctx || !ctx.airborne || ctx.editing) return [];
      const pick = (list) => list.filter((a) => a.where === 'inside' || a.where === 'ahead').slice(0, 2).map((a) => ({ id: a.id, level: a.level, text: a.text.length > 110 ? a.text.slice(0, 107) + '…' : a.text, action: a.action }));
      return pick(ctx.asp).concat(pick(ctx.hazAdv));
    }

    /** Lines for the plan editor's warnings: what the plan being edited does with airspace, hazards and the line-of-sight limit. Plain text. */
    editNotes(plan, which, gs) {
      const path = X.routePoints(plan, which);
      if (path.length < 2) return [];
      // the sums look at every zone: once a second, or at once when the route or the data changes
      const key = JSON.stringify(path) + '|' + this.zones().length + '|' + this.hazardList().length + '|' + which + '|' + this.prefs.windHours + '|' + (this.wind.cells ? this.wind.cells.size : 0);
      if (this.notesMemo && this.notesMemo.key === key && this.now() - this.notesMemo.at < 1000) return this.notesMemo.out;
      const out = this.editNotesNow(plan, path, which, gs);
      this.notesMemo = { key, at: this.now(), out };
      return out;
    }

    editNotesNow(plan, path, which, gs) {
      const out = [];
      const asp = A.advisories(this.zones(), path, { gs_kt: gs || 0, ahead_nm: 1e6, route: true });
      asp.slice(0, 5).forEach((a) => out.push(`${a.text}.`));
      const haz = W.hazardAdvisories(this.hazardList(), path, { now: this.now(), gs_kt: gs || 0, route: true });
      haz.slice(0, 5).forEach((a) => out.push(`${a.text}.`));
      const field = plan.field;
      if (field && Number.isFinite(field.lat) && LR.isLineOfSight(this.ctx ? this.ctx.station : 'LRE', this.ctx ? this.ctx.latency : 0)) {
        const m = LR.margin([field.lat, field.lon], field.elev_ft || 0, { lat: path[0].lat, lon: path[0].lon, alt_ft: path[0].alt_ft }, path, 0);
        if (m.cross_nm !== null) out.push(`The route leaves the line-of-sight range of a station at the field ${Math.round(m.cross_nm)} nmi along it: a satellite station has to have the aircraft by then (the limit is the radio horizon over a smooth earth).`);
      }
      const wl = W.legWinds(path, (la, lo, alt) => this.wind.at(la, lo, alt, this.prefs.windHours));
      if (wl.length) {
        const mean = wl.reduce((s, l) => s + l.tail_kt, 0) / wl.length;
        out.push(`Wind aloft (${this.prefs.windHours ? '+' + this.prefs.windHours + ' h, ' : 'now, '}${this.demo ? 'made up' : 'Open-Meteo'}): ${mean >= 0 ? 'a tailwind' : 'a headwind'} of ${Math.abs(Math.round(mean))} kt on average over the legs; the forecast above does not use it.`);
      }
      return out;
    }

    /* ------------------------------------------------------------------ drawing */
    install() {
      const self = this;
      this.map.stages = {
        base: (m, x) => self.paintBase(m, x),
        rasters: (m, x) => self.paintRasters(m, x),
        under: (m, x) => self.paintUnder(m, x),
        over: (m, x) => self.paintOver(m, x),
      };
    }

    tileLayer(m, x, src, key, urlFn, maxZoom, minZoom, opacity, seam, bias) {
      const view = { centre: m.centre, up: m.up, ftPerPx: m.ftPerPx, size: [m.w, m.h] };
      const z0 = Math.max(minZoom, T.zoomFor(m.ftPerPx, m.centre[0], maxZoom, minZoom) + (bias || 0));
      const v = T.visibleTiles(view, Math.min(maxZoom, z0));
      const project = (p) => m.project(p);
      let missing = 0;
      let drawn = 0;
      x.save();
      x.globalAlpha = opacity;
      for (const t of v.tiles) {
        const e = this.cache.get(`${key}/${v.z}/${t.xw}/${t.y}`, urlFn(v.z, t.xw, t.y), 'anonymous');
        if (e && e.state === 'ok') {
          T.drawTile(x, e.img, v.z, t.x, t.y, project, seam);
          drawn++;
        } else missing++;
      }
      x.restore();
      return { drawn, missing };
    }

    paintBase(m, x) {
      const src = T.BASES[this.prefs.base];
      m.baseOn = false;
      if (!src || !src.url || this.prefs.offline) return;
      // the grid's lines stay until a map is really behind them: no connection, no map, and the grid shows
      const r = this.tileLayer(m, x, src, 'base/' + src.id, (z, tx, ty) => T.urlFor(src, z, tx, ty, this.tilesOverride), src.max, 0, 1, true, 0);
      m.baseOn = r.drawn > 0 && r.missing <= r.drawn;
      this.baseDrawn = r.drawn;
      if (src.ref && m.baseOn) {
        // the place names, on top of the map
        const rf = src.ref;
        this.tileLayer(m, x, rf, 'base/' + rf.id, (z, tx, ty) => T.urlFor(rf, z, tx, ty, this.tilesOverride), rf.max, 0, 1, false, 0);
      }
    }

    /** Ground against the aircraft's height, from Terrarium tiles shaded once for each 200 ft band of height. */
    paintTerrain(m, x) {
      const ctx = this.ctx;
      const alt = ctx && ctx.own ? ctx.own.alt_ft : ctx && ctx.planPath && ctx.planPath[0] ? ctx.planPath[0].alt_ft : null;
      if (alt === null) return;
      if (ctx.own && X.aglOf(ctx) < 300) {
        this.terrainStatus = 'on the ground or just above it: not shaded (all the ground around would be above the aircraft)';
        return;
      }
      const view = { centre: m.centre, up: m.up, ftPerPx: m.ftPerPx, size: [m.w, m.h] };
      const v = T.visibleTiles(view, Math.max(3, Math.min(11, T.zoomFor(m.ftPerPx, m.centre[0], 12, 3) - 1)));
      const band = Math.floor(alt / 200);
      this.shaded = this.shaded || new Map();
      let loaded = 0;
      for (const t of v.tiles) {
        const key = `terr/${v.z}/${t.xw}/${t.y}`;
        const e = this.cache.get(key, this.tilesOverride ? T.urlFor({ id: 'terrain' }, v.z, t.xw, t.y, this.tilesOverride) : G.terrain.urlFor(v.z, t.xw, t.y), 'anonymous');
        if (!e || e.state !== 'ok') continue;
        let sh = this.shaded.get(key);
        if (!sh || sh.band !== band) {
          try {
            const c = sh ? sh.canvas : document.createElement('canvas');
            c.width = c.height = 256;
            const g = c.getContext('2d');
            g.clearRect(0, 0, 256, 256);
            g.drawImage(e.img, 0, 0, 256, 256);
            const src = g.getImageData(0, 0, 256, 256);
            const out = g.createImageData(256, 256);
            G.terrain.shade(src.data, alt, out.data);
            g.putImageData(out, 0, 0);
            sh = { canvas: c, band };
            this.shaded.set(key, sh);
            if (this.shaded.size > 200) this.shaded.delete(this.shaded.keys().next().value);
          } catch (err) {
            this.terrainStatus = 'cannot read the elevation tiles: ' + err.message;
            continue;
          }
        }
        T.drawTile(x, sh.canvas, v.z, t.x, t.y, (p) => m.project(p), true);
        loaded++;
      }
      this.terrainStatus = loaded ? `${loaded} tiles, ground within ${G.terrain.NEAR_FT} ft below FL${Math.round(alt / 100)} lighter, above it darker (Terrarium)` : this.terrainStatus || 'loading elevation tiles…';
      this.attrs.push('Terrain tiles: Mapzen, AWS');
    }

    paintRasters(m, x) {
      const L = this.layers;
      this.attrs = [];
      if (this.prefs.offline) return;
      if (L.shown('terrain')) this.paintTerrain(m, x);
      if (L.shown('wx-sat')) {
        const sat = W.satFor(m.centre[1]);
        this.tileLayer(m, x, sat, `sat/${sat.id}`, (z, tx, ty) => (this.tilesOverride ? T.urlFor({ id: 'sat' }, z, tx, ty, this.tilesOverride) : W.satUrl(sat, z, tx, ty, T.tileBBox(z, tx, ty))), sat.maxZoom, 1, 0.65, false, -1);
        this.attrs.push(sat.attr);
      }
      if (L.shown('wx-radar') && this.rain && this.rain.newest) {
        const f = this.rain.newest;
        this.tileLayer(m, x, { id: 'radar' }, `rain/${f.path}`, (z, tx, ty) => (this.tilesOverride ? T.urlFor({ id: 'radar' }, z, tx, ty, this.tilesOverride) : W.rainUrl(this.rain.host, f, z, tx, ty)), 7, 1, 0.7, false, -1);
        this.attrs.push('Weather data by RainViewer');
      }
    }

    poly(x, m, ring) {
      ring.forEach((p, i) => {
        const q = m.project(p);
        if (i) x.lineTo(q[0], q[1]);
        else x.moveTo(q[0], q[1]);
      });
      x.closePath();
    }

    text(x, s, px, py, colour, bg) {
      x.font = FONT;
      if (bg) {
        const w = x.measureText(s).width;
        x.fillStyle = 'rgba(11,14,18,0.72)';
        x.fillRect(px - 2, py - 10, w + 4, 14);
      }
      x.fillStyle = colour;
      x.fillText(s, px, py);
    }

    paintUnder(m, x) {
      const L = this.layers;
      const ctx = this.ctx;
      const own = ctx && ctx.own;
      const alt = own ? own.alt_ft : ctx && ctx.planPath && ctx.planPath[0] ? ctx.planPath[0].alt_ft : 0;
      const vb = m.w ? viewBox(m) : null;
      const inView = (b) => !b || !vb || !(b[2] < vb[0] || b[0] > vb[2] || b[3] < vb[1] || b[1] > vb[3]);
      if (L.shown('airspace')) this.paintAirspace(m, x, alt, L.mode('airspace') === 'on', inView);
      if (L.shown('wx-hazard')) this.paintHazards(m, x, alt, L.mode('wx-hazard') === 'on', inView);
      if (L.shown('areas')) this.paintAreas(m, x);
      if (L.shown('link')) this.paintLink(m, x, ctx);
      if (L.shown('wind')) this.paintWind(m, x, ctx, vb);
      if (this.ground && vb) {
        if (L.shown('taxiways')) this.paintTaxiways(m, x, vb);
        if (L.shown('parking')) this.paintParking(m, x, vb);
      }
      this.drawnFields = [];
      if (L.shown('airports')) this.paintAirports(m, x, ctx, vb);
      m.data.airfields = this.drawnFields;
    }

    /** The taxiways of the airport the aircraft sent: a band as wide as a taxiway (75 ft, at least 2 px), the runway's own arcs as a thin dotted line, names and runway ends when close. */
    paintTaxiways(m, x, vb) {
      const net = this.ground;
      const col = PAL.LAYERS.taxiways;
      const pad = 0.004;
      const seen = (p) => p[0] >= vb[0] - pad && p[0] <= vb[2] + pad && p[1] >= vb[1] - pad && p[1] <= vb[3] + pad;
      x.save();
      x.lineCap = 'round';
      x.lineJoin = 'round';
      x.strokeStyle = hexAlpha(col, 0.4);
      x.lineWidth = Math.min(10, Math.max(2, 75 / m.ftPerPx));
      x.beginPath();
      for (const [a, b, k] of net.arcs) {
        if (net.isRw[k] || !(seen(net.nodes[a]) || seen(net.nodes[b]))) continue;
        const p = m.project(net.nodes[a]);
        const q = m.project(net.nodes[b]);
        x.moveTo(p[0], p[1]);
        x.lineTo(q[0], q[1]);
      }
      x.stroke();
      x.strokeStyle = col;
      x.lineWidth = 1;
      x.beginPath();
      for (const [a, b, k] of net.arcs) {
        if (net.isRw[k] || !(seen(net.nodes[a]) || seen(net.nodes[b]))) continue;
        const p = m.project(net.nodes[a]);
        const q = m.project(net.nodes[b]);
        x.moveTo(p[0], p[1]);
        x.lineTo(q[0], q[1]);
      }
      x.stroke();
      x.strokeStyle = hexAlpha(col, 0.55);
      x.setLineDash([2, 5]);
      x.beginPath();
      for (const [a, b, k] of net.arcs) {
        if (!net.isRw[k] || !(seen(net.nodes[a]) || seen(net.nodes[b]))) continue;
        const p = m.project(net.nodes[a]);
        const q = m.project(net.nodes[b]);
        x.moveTo(p[0], p[1]);
        x.lineTo(q[0], q[1]);
      }
      x.stroke();
      x.setLineDash([]);
      if (m.ftPerPx < 40) {
        for (const l of net.labels()) if (seen(l.at)) {
          const q = m.project(l.at);
          this.text(x, l.name, q[0] + 4, q[1] - 4, col, true);
        }
        for (const r of net.runways) if (seen([r.lat, r.lon])) {
          const q = m.project([r.lat, r.lon]);
          x.fillStyle = col;
          x.beginPath();
          x.arc(q[0], q[1], 3, 0, 2 * Math.PI);
          x.fill();
          this.text(x, `${r.n}`, q[0] + 6, q[1] + 4, col, true);
        }
      }
      x.restore();
    }

    /** The stands: a ring of the stand's radius with a tick for the way it faces; dashed and marked when the aircraft does not fit (under 20 m); the plan's stand ringed in white. */
    paintParking(m, x, vb) {
      const net = this.ground;
      const col = PAL.LAYERS.parking;
      const pad = 0.002;
      const near = m.ftPerPx < 14;
      x.save();
      for (const s of net.parking) {
        if (s.lat < vb[0] - pad || s.lat > vb[2] + pad || s.lon < vb[1] - pad || s.lon > vb[3] + pad) continue;
        const q = m.project([s.lat, s.lon]);
        const rft = Math.max(s.r, 6) * 3.2808;
        const r = Math.max(3.5, rft / m.ftPerPx);
        const tip = m.project(geo.along([s.lat, s.lon], s.h, rft));
        x.strokeStyle = col;
        x.fillStyle = hexAlpha(col, s.fits ? 0.18 : 0.06);
        x.lineWidth = 1.5;
        x.setLineDash(s.fits ? [] : [3, 3]);
        x.beginPath();
        x.arc(q[0], q[1], r, 0, 2 * Math.PI);
        x.fill();
        x.stroke();
        x.setLineDash([]);
        x.beginPath();
        x.moveTo(q[0], q[1]);
        x.lineTo(tip[0], tip[1]);
        x.stroke();
        if (!s.fits && near) {
          x.beginPath();
          x.moveTo(q[0] - 4, q[1] - 4);
          x.lineTo(q[0] + 4, q[1] + 4);
          x.moveTo(q[0] + 4, q[1] - 4);
          x.lineTo(q[0] - 4, q[1] + 4);
          x.stroke();
        }
        if (near || m.ftPerPx < 30) this.text(x, `${s.n}${s.fits ? '' : ' (too small)'}`, q[0] + r + 3, q[1] + 4, col, true);
      }
      const st = this.stand;
      if (st && st.at) {
        const q = m.project(st.at);
        const tip = m.project(geo.along(st.at, st.heading || 0, 90));
        x.strokeStyle = '#ffffff';
        x.lineWidth = 2.5;
        x.beginPath();
        x.arc(q[0], q[1], 9, 0, 2 * Math.PI);
        const d = Math.hypot(tip[0] - q[0], tip[1] - q[1]) || 1;
        x.moveTo(q[0] + ((tip[0] - q[0]) / d) * 9, q[1] + ((tip[1] - q[1]) / d) * 9);
        x.lineTo(q[0] + ((tip[0] - q[0]) / d) * 32, q[1] + ((tip[1] - q[1]) / d) * 32);
        x.stroke();
      }
      x.restore();
    }

    paintAirspace(m, x, alt, all, inView) {
      const zs = A.visible(this.zones(), alt, all).filter((z) => inView(z.bbox));
      x.save();
      for (const z of zs) {
        const k = A.KINDS[z.kind] || A.KINDS.other;
        const strong = k.level === 'caution';
        x.strokeStyle = k.colour;
        x.fillStyle = hexAlpha(k.colour, strong ? 0.06 : 0.035); // light: a zone in several parts stacks
        x.lineWidth = strong ? 2 : 1.2;
        x.setLineDash(z.kind === 'classD' ? [4, 4] : z.kind === 'moa' || z.kind === 'warning' || z.kind === 'alert' ? [8, 4] : []);
        let c;
        if (z.circle) {
          c = m.project([z.circle.lat, z.circle.lon]);
          x.beginPath();
          x.arc(c[0], c[1], Math.max(2, z.circle.r_ft / m.ftPerPx), 0, 2 * Math.PI);
        } else {
          x.beginPath();
          z.rings.forEach((r) => this.poly(x, m, r));
          z.holes.forEach((r) => this.poly(x, m, r));
          const q = z.rings[0].map((p) => m.project(p));
          c = [q.reduce((s, p) => s + p[0], 0) / q.length, q.reduce((s, p) => s + p[1], 0) / q.length];
        }
        x.fill('evenodd');
        x.stroke();
        x.setLineDash([]);
        const lim = `${A.fmtLimit(z.lower).replace(' ft MSL', '').replace('the surface', 'SFC')}–${A.fmtLimit(z.upper).replace(' ft MSL', '').replace('unlimited', 'UNL')}`;
        this.text(x, `${z.name || k.label}  ${lim}`, c[0] - 40, c[1], k.colour, true);
      }
      x.restore();
    }

    paintHazards(m, x, alt, all, inView) {
      x.save();
      for (const h of this.hazardList()) {
        if (!W.FLIGHT_HAZARDS.includes(h.kind) || (h.to && h.to < this.now()) || (!all && !W.hazardRelevant(h, alt, 0))) continue;
        const col = HAZARD_COLOURS[h.kind] || PAL.LAYERS['wx-hazard'];
        x.strokeStyle = col;
        x.fillStyle = hexAlpha(col, 0.1);
        x.lineWidth = 2;
        x.setLineDash([3, 5]);
        x.beginPath();
        h.rings.forEach((r) => this.poly(x, m, r));
        x.fill();
        x.stroke();
        x.setLineDash([]);
        const q = m.project(h.rings[0][0]);
        this.text(x, `${h.id} ${W.HAZARD_WORDS[h.kind]} ${A.fmtLimit({ ft: h.lo_ft, ref: h.lo_ft >= 18000 ? 'FL' : 'MSL' }).replace(' ft MSL', '')}–${A.fmtLimit({ ft: h.hi_ft, ref: h.hi_ft >= 18000 && h.hi_ft < 99999 ? 'FL' : 'MSL' }).replace(' ft MSL', '').replace('unlimited', 'UNL')}`, q[0] + 4, q[1] + 14, col, true);
      }
      x.restore();
    }

    paintAreas(m, x) {
      x.save();
      x.strokeStyle = PAL.LAYERS.areas;
      x.fillStyle = hexAlpha(PAL.LAYERS.areas, 0.08);
      x.lineWidth = 2;
      for (const a of this.areas) {
        if (a.kind === 'polygon') {
          x.beginPath();
          a.rings.forEach((r) => this.poly(x, m, r));
          x.fill();
          x.stroke();
          if (a.name) {
            const q = m.project(a.rings[0][0]);
            this.text(x, a.name, q[0] + 4, q[1] - 4, PAL.LAYERS.areas, true);
          }
        } else if (a.kind === 'line') m.line(a.pts, PAL.LAYERS.areas, 2);
        else {
          const q = m.project(a.p);
          x.beginPath();
          x.arc(q[0], q[1], 5, 0, 2 * Math.PI);
          x.fillStyle = PAL.LAYERS.areas;
          x.fill();
          if (a.name) this.text(x, a.name, q[0] + 8, q[1] + 4, PAL.LAYERS.areas, true);
          x.fillStyle = hexAlpha(PAL.LAYERS.areas, 0.08);
        }
      }
      x.restore();
    }

    paintLink(m, x, ctx) {
      const link = ctx && ctx.link;
      if (!link || !link.station || !link.los) return;
      const own = ctx.own;
      const col = PAL.LAYERS.link;
      const c = m.project(link.station);
      x.save();
      x.strokeStyle = col;
      x.fillStyle = col;
      x.lineWidth = 2;
      if (own) {
        const r = LR.rangeNm(own.alt_ft, link.elev_ft);
        x.setLineDash([10, 6]);
        x.beginPath();
        x.arc(c[0], c[1], (r * NM) / m.ftPerPx, 0, 2 * Math.PI);
        x.stroke();
        this.text(x, `line of sight at this height: ${Math.round(r)} nmi (radio horizon)`, c[0] + 8, c[1] - (r * NM) / m.ftPerPx - 6, col, true);
        // and at the highest point of the plan
        const top = Math.max(...ctx.planPath.map((p) => p.alt_ft), 0);
        if (top > own.alt_ft + 2000) {
          const r2 = LR.rangeNm(top, link.elev_ft);
          x.setLineDash([2, 6]);
          x.lineWidth = 1.2;
          x.beginPath();
          x.arc(c[0], c[1], (r2 * NM) / m.ftPerPx, 0, 2 * Math.PI);
          x.stroke();
          this.text(x, `at the plan's highest point: ${Math.round(r2)} nmi`, c[0] + 8, c[1] - (r2 * NM) / m.ftPerPx - 6, col, true);
        }
      }
      x.setLineDash([]);
      x.beginPath(); // the station: a small triangle
      x.moveTo(c[0], c[1] - 8);
      x.lineTo(c[0] + 7, c[1] + 6);
      x.lineTo(c[0] - 7, c[1] + 6);
      x.closePath();
      x.fill();
      this.text(x, ctx.station || 'station', c[0] + 10, c[1] + 4, col, true);
      x.restore();
    }

    paintWind(m, x, ctx, vb) {
      if (!vb || !ctx) return;
      const own = ctx.own;
      const alt = own ? own.alt_ft : ctx.planPath[0] ? ctx.planPath[0].alt_ft : 40000;
      const hours = this.prefs.windHours;
      const col = PAL.LAYERS.wind;
      const arrows = this.wind.arrows(vb, alt, hours);
      x.save();
      x.strokeStyle = col;
      x.fillStyle = col;
      x.lineWidth = 1.5;
      let n = 0;
      for (const a of arrows) {
        const q = m.project([a.lat, a.lon]);
        if (q[0] < -20 || q[1] < -20 || q[0] > m.w + 20 || q[1] > m.h + 20) continue;
        if (++n > 120) break;
        const len = Math.min(44, 10 + a.spd * 0.28);
        const ang = (((a.dir + 180 - m.up) % 360) * Math.PI) / 180; // where the air goes, on this map
        const dx = Math.sin(ang) * len;
        const dy = -Math.cos(ang) * len;
        x.beginPath();
        x.moveTo(q[0] - dx / 2, q[1] - dy / 2);
        x.lineTo(q[0] + dx / 2, q[1] + dy / 2);
        x.stroke();
        x.beginPath();
        x.moveTo(q[0] + dx / 2, q[1] + dy / 2);
        x.lineTo(q[0] + dx / 2 - Math.sin(ang - 0.45) * 7, q[1] + dy / 2 + Math.cos(ang - 0.45) * 7);
        x.lineTo(q[0] + dx / 2 - Math.sin(ang + 0.45) * 7, q[1] + dy / 2 + Math.cos(ang + 0.45) * 7);
        x.closePath();
        x.fill();
        if (n % 3 === 0) this.text(x, String(Math.round(a.spd)), q[0] + 4, q[1] - 5, col, false);
      }
      // the head or tail wind on each leg, from the plan being edited or the way ahead
      const path = ctx.editing ? ctx.planPath : ctx.path;
      const legs = W.legWinds(path, (la, lo, al) => this.wind.at(la, lo, al, hours));
      legs.forEach((l) => {
        const a = path[l.i];
        const b = path[l.i + 1];
        const q = m.project([(a.lat + b.lat) / 2, (a.lon + b.lon) / 2]);
        this.text(x, `${l.tail_kt >= 0 ? 'tail' : 'head'} ${Math.abs(Math.round(l.tail_kt))} kt`, q[0] + 6, q[1] - 6, col, true);
      });
      x.restore();
      this.windNote = `wind at ${W.levelFor(alt)} hPa (about FL${Math.round(alt / 1000) * 10}), ${hours ? '+' + hours + ' h' : 'now'}`;
    }

    paintAirports(m, x, ctx, vb) {
      if (!vb || !ctx) return;
      const st = ctx.own ? { weight_lb: this.weightNow || 25600, fuel_lb: this.fuelNow || 14150 } : { weight_lb: 25600, fuel_lb: 14150 };
      const all = this.layers.mode('airports') === 'on';
      const across = (vb[3] - vb[1]) * 60 * Math.cos((m.centre[0] * Math.PI) / 180);
      const max = across < 60 ? 40 : across < 200 ? 20 : 10;
      const fc = this.forecast;
      const list = AP.inBox(this.airports.list, vb, 400);
      const shown = [];
      for (const a of list) {
        const needNow = AP.need(fc, st.weight_lb, a.elev_ft).need_ft;
        const needLight = AP.need(fc, st.weight_lb - st.fuel_lb + 765, a.elev_ft).need_ft;
        const u = AP.usable(a, needNow, needLight);
        if (u === 'no' && !all) continue;
        shown.push({ a, u, needNow });
        if (shown.length >= max) break;
      }
      x.save();
      for (const s of shown) {
        const q = m.project([s.a.lat, s.a.lon]);
        x.lineWidth = 2;
        x.strokeStyle = s.u === 'no' ? '#8d99a6' : PAL.LAYERS.airports;
        x.fillStyle = s.u === 'now' ? PAL.LAYERS.airports : 'rgba(11,14,18,0.8)';
        x.setLineDash(s.u === 'lighter' ? [3, 2] : []);
        x.beginPath();
        x.arc(q[0], q[1], s.u === 'no' ? 3.5 : 6, 0, 2 * Math.PI);
        x.fill();
        x.stroke();
        x.setLineDash([]);
        const tag = `${s.a.ident}  ${s.a.paved_ft ? Math.round(s.a.paved_ft / 100) * 100 : '?'} ft${s.u === 'lighter' ? '  (lighter)' : s.u === 'no' ? '  (too short)' : ''}`;
        this.text(x, tag, q[0] + 9, q[1] + 4, s.u === 'no' ? '#8d99a6' : PAL.LAYERS.airports, true);
        this.drawnFields.push({ ident: s.a.ident, name: `${s.a.ident} ${s.a.name}`, lat: s.a.lat, lon: s.a.lon });
        if (this.layers.shown('metar')) this.paintMetar(m, x, s.a, q);
      }
      x.restore();
    }

    paintMetar(m, x, a, q) {
      const r = this.metars.get(a.ident);
      if (!r) return;
      const col = CAT_COLOURS[r.cat] || '#8d99a6';
      x.fillStyle = col;
      x.fillRect(q[0] + 9, q[1] + 8, 18, 12);
      x.font = 'bold 9px ui-sans-serif, system-ui, sans-serif';
      x.fillStyle = '#fff';
      x.fillText(r.cat, q[0] + 10, q[1] + 17);
      let xw = '';
      const hdgs = (a.rwys || []).filter((w) => Number.isFinite(w.hdg)).map((w) => w.hdg);
      if (r.wdir !== null && Number.isFinite(r.wspd) && hdgs.length) xw = ` xw ${Math.round(Math.min(...hdgs.map((h) => AP.crosswind(r.wdir, r.wspd, h))))}`;
      const wind = r.wdir === null ? 'wind variable' : `${String(Math.round(r.wdir)).padStart(3, '0')}/${r.wspd}${r.wgst ? 'G' + r.wgst : ''}`;
      this.text(x, `${wind}${xw}${r.src && /demo/.test(r.src) ? '  (made up)' : ''}`, q[0] + 30, q[1] + 18, col, true);
    }

    paintOver(m, x) {
      const parts = [];
      if (this.prefs.base !== 'none' && !this.prefs.offline && T.BASES[this.prefs.base]) parts.push(T.BASES[this.prefs.base].attr);
      (this.attrs || []).forEach((a) => parts.push(a));
      if (this.layers.shown('airports') && this.airports.list.length && !this.demo) parts.push('OurAirports');
      if (this.layers.shown('wind') && !this.demo) parts.push('Open-Meteo.com');
      if (this.layers.shown('airspace') && this.faaZones.length) parts.push('FAA open data');
      if (parts.length) {
        x.save();
        x.font = '10px ui-sans-serif, system-ui, sans-serif';
        const s = [...new Set(parts)].join(' | ');
        const w = x.measureText(s).width;
        x.fillStyle = 'rgba(11,14,18,0.7)';
        x.fillRect(m.w - w - 12, m.h - 18, w + 10, 14);
        x.fillStyle = '#9aa7b4';
        x.fillText(s, m.w - w - 7, m.h - 7);
        x.restore();
      }
    }

    /* ------------------------------------------------------------------ the panel */
    buildPanel() {
      const d = this.dom;
      d.button.addEventListener('click', () => {
        d.box.hidden = !d.box.hidden;
        d.button.classList.toggle('on', !d.box.hidden);
        this.refreshPanel(true);
      });
      d.declutter.addEventListener('click', () => {
        this.layers.setDeclutter(!this.layers.declutter);
        d.declutter.classList.toggle('on', this.layers.declutter);
        this.redraw();
      });
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !d.box.hidden) {
          d.box.hidden = true;
          d.button.classList.remove('on');
        }
      });
      d.box.addEventListener('click', (e) => this.panelClick(e));
      d.box.addEventListener('change', (e) => this.panelChange(e));
      d.chips.addEventListener('click', (e) => {
        const id = e.target.getAttribute('data-dismiss');
        if (id) {
          this.layers.dismiss(id);
          this.redraw();
        } else if (e.target.closest('.chip-l')) {
          d.box.hidden = false;
          d.button.classList.add('on');
          this.refreshPanel(true);
        }
      });
      const mapEl = this.map.c;
      mapEl.addEventListener('dragover', (e) => e.preventDefault());
      mapEl.addEventListener('drop', (e) => {
        e.preventDefault();
        if (e.dataTransfer && e.dataTransfer.files.length) this.loadFiles([...e.dataTransfer.files]);
      });
    }

    panelClick(e) {
      const b = e.target.closest('[data-mode]');
      if (b) {
        this.layers.setMode(b.getAttribute('data-layer'), b.getAttribute('data-mode'));
        this.refreshPanel(true);
        this.redraw();
      }
      if (e.target.id === 'ov-offline') {
        this.setPref('offline', !this.prefs.offline);
        this.refreshPanel(true);
      }
    }

    panelChange(e) {
      if (e.target.id === 'ov-base') this.setPref('base', e.target.value);
      else if (e.target.id === 'ov-hours') this.setPref('windHours', Number(e.target.value));
      else if (e.target.id === 'ov-file' && e.target.files.length) this.loadFiles([...e.target.files]);
      this.refreshPanel(true);
    }

    /** What a row says under its name: why it is on, or what its data is doing. */
    statusOf(id) {
      const s = this.layers.state(id);
      const lead = s.source === 'forced' ? 'forced: ' : s.source === 'auto' ? 'auto: ' : s.source === 'waiting' ? 'waiting for a place: ' : s.source === 'dismissed' ? 'put away: ' : '';
      const reason = s.reason ? lead + s.reason : '';
      const data = {
        airspace: [this.zones().length ? `${this.zones().length} zones` : 'none loaded', this.faaStatus].filter(Boolean).join('; '),
        airports: this.airports.status,
        metar: this.metars.status,
        'wx-radar': this.rainStatus,
        'wx-hazard': this.hazards.status,
        wind: this.wind.status,
        areas: this.areas.length ? `${this.areas.length} areas loaded` : 'nothing loaded',
        taxiways: this.groundStatus || 'no ground map: load an airport in the plan editor',
        parking: this.groundStatus || 'no ground map: load an airport in the plan editor',
        terrain: this.prefs.offline ? 'offline' : this.terrainStatus || 'not drawn yet',
      }[id];
      return [reason, data].filter(Boolean).join(' · ');
    }

    refreshPanel(force) {
      const d = this.dom;
      if (!d) return;
      const L = this.layers;
      // the chips under the toolbar: what came up by itself, and why
      const chips = L.chips().filter((c) => c.id !== 'trail');
      const waiting = L.waiting();
      const chipHtml = chips.map((c) => `<span class="chip-l ${c.forced ? 'forced' : ''}" title="${esc(c.reason)}"><b>${esc(c.label)}</b> ${esc(c.reason)}${c.forced ? ' <i>forced</i>' : ` <button data-dismiss="${c.id}" title="put it away until its reason has gone and come back">✕</button>`}</span>`).join('') + (waiting.length ? `<span class="chip-l waiting">+${waiting.length} waiting</span>` : '') + (this.prefs.offline ? '<span class="chip-l offline">offline</span>' : '');
      if (d.chips.dataset.html !== chipHtml) {
        d.chips.innerHTML = chipHtml;
        d.chips.dataset.html = chipHtml;
      }
      d.declutter.classList.toggle('on', L.declutter);
      if (d.box.hidden) return;
      if (!force && d.box.contains(document.activeElement) && document.activeElement.tagName !== 'BODY') {
        // keep what the user is working on: refresh only the status lines
        d.box.querySelectorAll('[data-status]').forEach((el) => (el.textContent = this.statusOf(el.getAttribute('data-status'))));
        return;
      }
      const row = (def) => {
        const s = L.state(def.id);
        const seg = ['off', 'auto', 'on'].map((m) => `<button data-layer="${def.id}" data-mode="${m}" class="${L.mode(def.id) === m ? 'sel' : ''}">${m === 'off' ? 'Off' : m === 'auto' ? 'Auto' : 'On'}</button>`).join('');
        return `<div class="lrow ${s.shown ? 'shown' : ''}"><span class="sw" style="background:${def.colour || '#5b6b7a'}"></span><div class="lname" title="${esc(def.tip)}"><b>${esc(def.label)}</b><div class="small" data-status="${def.id}">${esc(this.statusOf(def.id))}</div></div><div class="seg">${seg}</div></div>`;
      };
      const groups = G.layers.GROUPS.map((g) => {
        const defs = L.defs.filter((x) => x.group === g);
        return defs.length ? `<h3>${g}</h3>${defs.map(row).join('')}` : '';
      }).join('');
      const bases = Object.values(T.BASES).map((b) => `<option value="${b.id}" ${this.prefs.base === b.id ? 'selected' : ''}>${b.label}</option>`).join('');
      const html = `<div class="lhead"><b>Map layers</b> <span class="small">Auto shows a layer when its reason holds and says why. On and Off are yours. Declutter puts everything optional away; a second click brings it back.</span></div>
        <label class="lbase">Map <select id="ov-base">${bases}</select></label>
        ${groups}
        <label class="lbase">Winds: <select id="ov-hours">${[0, 3, 6, 12, 24].map((h) => `<option value="${h}" ${this.prefs.windHours === h ? 'selected' : ''}>${h ? '+' + h + ' h' : 'now'}</option>`).join('')}</select></label>
        <div class="lfoot"><label class="filebtn">Load a file…<input type="file" id="ov-file" multiple accept=".txt,.json,.geojson,.csv"></label> <span class="small">airspace (OpenAir, GeoJSON, OpenAIP), airports and runways (OurAirports CSV), areas (GeoJSON); or drop it on the map. ${esc(this.fileStatus)}</span></div>
        <div class="lfoot"><button id="ov-offline" class="${this.prefs.offline ? 'on' : ''}">${this.prefs.offline ? 'Offline: nothing leaves this page. Go online' : 'Go offline'}</button> <span class="small">Maps and data come from other people's servers, which see the area looked at. Real-world data, not the simulator's weather; nothing here is a clearance.</span></div>`;
      if (d.box.dataset.html !== html) {
        d.box.innerHTML = html;
        d.box.dataset.html = html;
      }
    }

    /** The legend entries for what is shown, for the page to put under the map's. */
    legendHtml() {
      const L = this.layers;
      const sw = (c, dash, t) => `<span class="k2" style="border-top:3px ${dash ? 'dashed' : 'solid'} ${c}">${t}</span>`;
      const out = [];
      if (L.shown('airspace')) out.push(sw(A.KINDS.restricted.colour, false, 'restricted') + sw(A.KINDS.moa.colour, true, 'MOA, warning') + sw(A.KINDS.classB.colour, false, 'controlled'));
      if (L.shown('wx-hazard')) out.push(sw(PAL.LAYERS['wx-hazard'], true, 'SIGMET area'));
      if (L.shown('link')) out.push(sw(PAL.LAYERS.link, true, 'line of sight'));
      if (L.shown('wind') && this.windNote) out.push(sw(PAL.LAYERS.wind, false, this.windNote));
      if (L.shown('airports')) out.push(sw(PAL.LAYERS.airports, false, 'field: usable now') + sw(PAL.LAYERS.airports, true, 'only lighter'));
      if (L.shown('areas')) out.push(sw(PAL.LAYERS.areas, false, 'loaded areas'));
      if (this.ground && L.shown('taxiways')) out.push(sw(PAL.LAYERS.taxiways, false, 'taxiway'));
      if (this.ground && L.shown('parking')) out.push(sw(PAL.LAYERS.parking, false, 'stand') + sw(PAL.LAYERS.parking, true, 'too small (< 20 m)'));
      return out.join('');
    }
  }

  G.Overlays = Overlays;
  G.overlayHelpers = { viewBox, parseAreas, looksLikeAirspace };
})(window);
