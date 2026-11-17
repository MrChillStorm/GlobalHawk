/**
 * Map tiles: slippy-map (web mercator) arithmetic, a cache that asks for few tiles at a time, and the drawing of
 * a tile through the station's own projection (js/geo.js: the tangent plane about the map's centre, turning with "track up").
 *
 * The station's projection is nearly linear in latitude and longitude (a plane: it bends a little at the edge of a wide view); a tile's rows are not (mercator). A tile is therefore
 * drawn as a small mesh of sub-quads, each placed by three corners; the mesh is made as fine as needed for the
 * error to stay under MESH_PX of a pixel (checked in tests/tiles.test.js at several zooms and latitudes).
 *
 * Sources are free services whose own terms ask for attribution, which the map prints. Whatever is asked for is
 * asked of someone else's server: "Go offline" in the page stops all of it.
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const RAD = Math.PI / 180;
  const M_PER_FT = 0.3048;
  const MESH_PX = 0.35;
  const MAX_TILES = 80;
  const EQ_MPP = 156543.03392; // metres per pixel of a 256-px tile at zoom 0, on the equator

  /** Fractional tile coordinates of a point at a zoom. */
  function tileXY(lat, lon, z) {
    const n = Math.pow(2, z);
    const la = Math.max(-85.0511, Math.min(85.0511, lat)) * RAD;
    return { x: ((lon + 180) / 360) * n, y: ((1 - Math.log(Math.tan(la) + 1 / Math.cos(la)) / Math.PI) / 2) * n };
  }

  /** The point at fractional tile coordinates: [lat, lon]. */
  function tileLatLon(x, y, z) {
    const n = Math.pow(2, z);
    return [Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / n))) / RAD, (x / n) * 360 - 180];
  }

  /** The zoom whose 256-px tiles come nearest to one tile pixel per screen pixel here, within [min, max]. */
  function zoomFor(ftPerPx, lat, maxZoom, minZoom) {
    const mpp = ftPerPx * M_PER_FT;
    const exact = Math.log2((EQ_MPP * Math.cos(Math.min(85, Math.abs(lat)) * RAD)) / mpp);
    return Math.max(minZoom || 0, Math.min(maxZoom, Math.round(exact)));
  }

  /**
   * The tiles that cover the screen. view: { centre, up, ftPerPx, size: [w, h] }. At most `max` (the zoom is lowered
   * until they fit). Returns { z, tiles: [{ x, y, xw }] } with x unwrapped (for placing) and xw wrapped (for asking),
   * nearest the centre first.
   */
  function visibleTiles(view, z, max) {
    max = max || MAX_TILES;
    const [w, h] = view.size;
    // a grid over the screen, not its four corners: the plane bends away from the centre, so an edge is a curve in latitude and longitude and its middle can lie beyond its ends
    const grid = [];
    for (let i = 0; i <= 16; i++) for (let j = 0; j <= 16; j++) grid.push([(i / 16) * w, (j / 16) * h]);
    const corners = grid.map((c) => geo.fromScreen(c[0], c[1], view.centre, view.up, view.ftPerPx, view.size));
    for (let zz = z; zz >= 0; zz--) {
      const n = Math.pow(2, zz);
      const xy = corners.map((c) => tileXY(c[0], c[1], zz));
      const x0 = Math.floor(Math.min(...xy.map((p) => p.x)));
      const x1 = Math.floor(Math.max(...xy.map((p) => p.x)));
      const y0 = Math.max(0, Math.floor(Math.min(...xy.map((p) => p.y))));
      const y1 = Math.min(n - 1, Math.floor(Math.max(...xy.map((p) => p.y))));
      if ((x1 - x0 + 1) * (y1 - y0 + 1) > max && zz > 0) continue;
      const c = tileXY(view.centre[0], view.centre[1], zz);
      const tiles = [];
      for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) tiles.push({ x, y, xw: ((x % n) + n) % n });
      tiles.sort((a, b) => Math.hypot(a.x + 0.5 - c.x, a.y + 0.5 - c.y) - Math.hypot(b.x + 0.5 - c.x, b.y + 0.5 - c.y));
      return { z: zz, tiles };
    }
    return { z: 0, tiles: [{ x: 0, y: 0, xw: 0 }] };
  }

  /** Where a point of a tile (fx, fy in 0..1) is on the screen, exactly. project: ([lat, lon]) => [x, y]. */
  function exactPoint(z, x, y, fx, fy, project) {
    return project(tileLatLon(x + fx, y + fy, z));
  }

  /**
   * The affine map of one sub-quad of the mesh: the image's rectangle (sx, sy, sw, sh) in tile pixels (a tile is
   * 256) to the screen, from three corners placed exactly.
   */
  function quad(z, x, y, n, i, j, project) {
    const s = 256 / n;
    const p00 = exactPoint(z, x, y, i / n, j / n, project);
    const p10 = exactPoint(z, x, y, (i + 1) / n, j / n, project);
    const p01 = exactPoint(z, x, y, i / n, (j + 1) / n, project);
    return { sx: i * s, sy: j * s, sw: s, sh: s, m: [(p10[0] - p00[0]) / s, (p10[1] - p00[1]) / s, (p01[0] - p00[0]) / s, (p01[1] - p00[1]) / s, p00[0], p00[1]] };
  }

  /** Where the mesh puts a point of the tile (fx, fy in 0..1) on the screen. */
  function meshPoint(z, x, y, n, fx, fy, project) {
    const i = Math.min(n - 1, Math.floor(fx * n));
    const j = Math.min(n - 1, Math.floor(fy * n));
    const q = quad(z, x, y, n, i, j, project);
    const u = fx * 256 - q.sx;
    const v = fy * 256 - q.sy;
    return [q.m[0] * u + q.m[2] * v + q.m[4], q.m[1] * u + q.m[3] * v + q.m[5]];
  }

  /** The worst distance, in pixels, between the mesh and the exact place over a grid of points of the tile. */
  function meshError(z, x, y, n, project) {
    let worst = 0;
    for (let a = 0; a <= 10; a++) {
      for (let b = 0; b <= 10; b++) {
        const e = exactPoint(z, x, y, a / 10, b / 10, project);
        const m = meshPoint(z, x, y, n, a / 10, b / 10, project);
        worst = Math.max(worst, Math.hypot(e[0] - m[0], e[1] - m[1]));
      }
    }
    return worst;
  }

  /** The coarsest mesh (1, 2, 4, 8, 16, 32 to a side) that keeps within MESH_PX. */
  function meshFor(z, x, y, project) {
    for (const n of [1, 2, 4, 8, 16, 32]) if (meshError(z, x, y, n, project) <= MESH_PX) return n;
    return 32;
  }

  /** Draw one tile image through the projection. `seam`: grow each piece a little so that opaque tiles show no cracks. */
  function drawTile(ctx, img, z, x, y, project, seam) {
    const n = meshFor(z, x, y, project);
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const q = quad(z, x, y, n, i, j, project);
        ctx.save();
        ctx.transform(q.m[0], q.m[1], q.m[2], q.m[3], q.m[4], q.m[5]);
        const g = seam ? 0.6 : 0;
        ctx.drawImage(img, q.sx, q.sy, q.sw, q.sh, -g, -g, q.sw + 2 * g, q.sh + 2 * g);
        ctx.restore();
      }
    }
  }

  /** The web-mercator bounding box (EPSG:3857) of a tile, as WMS wants it: "minx,miny,maxx,maxy". */
  function tileBBox(z, x, y) {
    const EARTH = 40075016.686;
    const half = EARTH / 2;
    const n = Math.pow(2, z);
    const s = EARTH / n;
    return `${x * s - half},${half - (y + 1) * s},${(x + 1) * s - half},${half - y * s}`;
  }

  /* ------------------------------------------------------------------ the cache */
  /**
   * Images by key. At most `maxLoads` are being fetched at once (a request that does not fit is refused and made
   * again on the next draw), a failed one is asked for again after `retryMs`, and the cache keeps `maxEntries`.
   * opts: { makeImage: () => image, now, maxLoads, maxEntries, retryMs, onChange }
   */
  class TileCache {
    constructor(opts) {
      opts = opts || {};
      this.makeImage = opts.makeImage || (() => new root.Image());
      this.now = opts.now || (() => Date.now());
      this.maxLoads = opts.maxLoads || 8;
      this.maxEntries = opts.maxEntries || 500;
      this.retryMs = opts.retryMs === undefined ? 30000 : opts.retryMs;
      this.onChange = opts.onChange || null;
      this.map = new Map();
      this.loads = 0;
      this.requests = 0;
    }

    /** The entry for a key: { state: 'loading'|'ok'|'fail', img }, or null when it must wait for a free place. */
    get(key, url, crossOrigin) {
      let e = this.map.get(key);
      if (e) {
        if (e.state !== 'fail' || this.now() - e.failedAt < this.retryMs) {
          this.map.delete(key); // keep it as the newest
          this.map.set(key, e);
          return e;
        }
        this.map.delete(key);
      }
      if (this.loads >= this.maxLoads) return null;
      const img = this.makeImage();
      e = { state: 'loading', img, failedAt: 0 };
      this.map.set(key, e);
      while (this.map.size > this.maxEntries) this.map.delete(this.map.keys().next().value);
      this.loads++;
      this.requests++;
      img.onload = () => {
        this.loads--;
        e.state = 'ok';
        if (this.onChange) this.onChange();
      };
      img.onerror = () => {
        this.loads--;
        e.state = 'fail';
        e.failedAt = this.now();
      };
      if (crossOrigin) img.crossOrigin = crossOrigin;
      img.src = url;
      return e;
    }
  }

  /* ------------------------------------------------------------------ the sources */
  /** Base maps. `url` has {z} {x} {y} and {s} for a subdomain. */
  const BASES = {
    none: { id: 'none', label: 'None (grid)', url: null, attr: '' },
    // Esri's dark gray canvas, with its place names as a second, transparent layer on top. (CARTO's dark tiles were tried first and
    // answer with a picture that says "API KEY REQUIRED": a status of 200 was not enough to know.)
    dark: { id: 'dark', label: 'Dark', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', subs: [''], max: 16, attr: 'Esri, HERE, Garmin, © OpenStreetMap contributors', ref: { id: 'dark-ref', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', subs: [''], max: 16 } },
    streets: { id: 'streets', label: 'Streets', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', subs: [''], max: 19, attr: '© OpenStreetMap contributors' },
    topo: { id: 'topo', label: 'Topo', url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', subs: ['a', 'b', 'c'], max: 17, attr: '© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)' },
    satellite: { id: 'satellite', label: 'Satellite', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', subs: [''], max: 18, attr: 'Esri, Maxar, Earthstar Geographics, and the GIS User Community' },
  };

  /** The address of a tile. `override`: a base address (the page's ?tiles=) that serves {id}/{z}/{x}/{y}.png for every source, for testing against a local fake. */
  function urlFor(src, z, x, y, override) {
    if (override) return `${override.replace(/\/$/, '')}/${src.id}/${z}/${x}/${y}.png`;
    const subs = src.subs && src.subs.length ? src.subs : [''];
    return src.url.replace('{s}', subs[(x + y) % subs.length]).replace('{z}', z).replace('{x}', x).replace('{y}', y);
  }

  const api = { tileXY, tileLatLon, zoomFor, visibleTiles, exactPoint, quad, meshPoint, meshError, meshFor, drawTile, tileBBox, TileCache, BASES, urlFor, MAX_TILES, MESH_PX };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).tiles = api;
})(typeof window !== 'undefined' ? window : globalThis);
