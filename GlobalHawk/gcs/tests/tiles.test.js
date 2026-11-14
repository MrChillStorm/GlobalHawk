// node tests/tiles.test.js
// L3 of the map-layers plan (docs/PLAN.md): tile arithmetic, cover, mesh accuracy, cache limits.
const assert = require('assert');
const T = require('../js/tiles.js');
const geo = require('../js/geo.js');

// Greenwich at zoom 10 is tile 511, 340
{
  const p = T.tileXY(51.4779, -0.0015, 10);
  assert.strictEqual(Math.floor(p.x), 511);
  assert.strictEqual(Math.floor(p.y), 340);
  // the world is 2^z tiles wide, and its corners are where they should be
  assert.ok(Math.abs(T.tileXY(0, -180, 3).x - 0) < 1e-9);
  assert.ok(Math.abs(T.tileXY(0, 180, 3).x - 8) < 1e-9);
  assert.ok(Math.abs(T.tileXY(0, 0, 3).y - 4) < 1e-9);
  // round trip to a billionth of a degree
  for (const [la, lo, z] of [[34.9, -117.88, 12], [-33.9, 151.2, 7], [64.1, -21.9, 15], [0.5, 179.9, 2]]) {
    const q = T.tileXY(la, lo, z);
    const b = T.tileLatLon(q.x, q.y, z);
    assert.ok(Math.abs(b[0] - la) < 1e-9 && Math.abs(b[1] - lo) < 1e-9, `round trip ${la} ${lo}`);
  }
}

// the zoom chosen has tiles within a factor of 1.5 of the screen's scale
{
  for (const lat of [0, 35, 60]) {
    for (const ftPerPx of [3, 10, 40, 150, 600, 2400, 9000]) {
      const z = T.zoomFor(ftPerPx, lat, 22, 0);
      const exact = Math.log2((156543.03392 * Math.cos((lat * Math.PI) / 180)) / (ftPerPx * 0.3048));
      const factor = Math.pow(2, z - exact);
      if (z > 0 && z < 22) assert.ok(factor <= 1.5 && factor >= 1 / 1.5, `scale factor ${factor} at ${lat}, ${ftPerPx} ft/px`);
    }
  }
  assert.strictEqual(T.zoomFor(1, 35, 12, 0), 12, "clamped to the source's finest");
  assert.strictEqual(T.zoomFor(1e9, 35, 12, 3), 3, "and to its coarsest");
}

// the tiles asked for cover the screen, at most 80, north up and track up
{
  for (const up of [0, 37, 200]) {
    for (const ftPerPx of [8, 60, 600, 6000, 40000]) {
      for (const size of [[900, 600], [1600, 1000]]) {
        const view = { centre: [34.9, -117.88], up, ftPerPx, size };
        const z0 = T.zoomFor(ftPerPx, 34.9, 17, 0);
        const v = T.visibleTiles(view, z0);
        assert.ok(v.tiles.length <= T.MAX_TILES, `${v.tiles.length} tiles`);
        assert.ok(v.z <= z0);
        const have = new Set(v.tiles.map((t) => `${t.x}/${t.y}`));
        for (let a = 0; a <= 8; a++) {
          for (let b = 0; b <= 8; b++) {
            const p = geo.fromScreen((a / 8) * size[0], (b / 8) * size[1], view.centre, up, ftPerPx, size);
            const q = T.tileXY(p[0], p[1], v.z);
            assert.ok(have.has(`${Math.floor(q.x)}/${Math.floor(q.y)}`), `screen point ${a},${b} is on a tile asked for (up ${up}, ${ftPerPx} ft/px)`);
          }
        }
        // nearest the centre first
        const c = T.tileXY(34.9, -117.88, v.z);
        const d = (t) => Math.hypot(t.x + 0.5 - c.x, t.y + 0.5 - c.y);
        for (let i = 1; i < v.tiles.length; i++) assert.ok(d(v.tiles[i - 1]) <= d(v.tiles[i]) + 1e-9);
      }
    }
  }
  // across the date line the tiles wrap for asking and not for placing
  const v = T.visibleTiles({ centre: [10, 179.9], up: 0, ftPerPx: 4000, size: [900, 600] }, 6);
  assert.ok(v.tiles.some((t) => t.x >= Math.pow(2, v.z) && t.xw === t.x - Math.pow(2, v.z)), 'x past the edge is wrapped');
}

// the mesh puts every point of a tile within 0.5 px of the exact place
{
  const EQ = 156543.03392;
  for (const z of [5, 8, 12]) {
    for (const lat of [0, 35, 60]) {
      for (const scale of [0.5, 1, 2]) {
        for (const up of [0, 37]) {
          const ftPerPx = (EQ * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, z) / 0.3048 / scale;
          const centre = [lat, 10];
          const size = [900, 600];
          const project = (p) => geo.toScreen(p, centre, up, ftPerPx, size);
          const c = T.tileXY(lat, 10, z);
          const x = Math.floor(c.x);
          const y = Math.floor(c.y);
          const n = T.meshFor(z, x, y, project);
          const err = T.meshError(z, x, y, n, project);
          assert.ok(err <= 0.5, `mesh error ${err.toFixed(3)} px at zoom ${z}, lat ${lat}, scale ${scale}, up ${up} (mesh ${n})`);
          assert.ok(n <= 32);
          // and with one piece only it would NOT have been good enough somewhere: the mesh is doing something
          if (z === 5 && lat === 60 && scale === 1 && up === 0) assert.ok(n > 1, 'a zoom-5 tile at 60 N needs a mesh');
        }
      }
    }
  }
}

// drawing: one drawImage for each piece, each through its own transform
{
  const calls = { draw: 0, transform: 0, save: 0, restore: 0 };
  const ctx = { save: () => calls.save++, restore: () => calls.restore++, transform: () => calls.transform++, drawImage: () => calls.draw++ };
  const project = (p) => geo.toScreen(p, [60, 10], 0, 300, [900, 600]);
  const n = T.meshFor(5, 17, 8, project);
  T.drawTile(ctx, {}, 5, 17, 8, project, true);
  assert.strictEqual(calls.draw, n * n);
  assert.strictEqual(calls.transform, n * n);
  assert.strictEqual(calls.save, calls.restore);
}

// the cache: limits, retry, size
{
  let t = 0;
  const made = [];
  const cache = new T.TileCache({ makeImage: () => { const i = { set src(v) { this.url = v; } }; made.push(i); return i; }, now: () => t, maxLoads: 3, maxEntries: 5, retryMs: 30000 });
  let changed = 0;
  cache.onChange = () => changed++;
  const e1 = cache.get('a', 'http://x/a');
  cache.get('b', 'http://x/b');
  cache.get('c', 'http://x/c');
  assert.strictEqual(cache.get('d', 'http://x/d'), null, 'a fourth load waits for a place');
  assert.strictEqual(cache.loads, 3);
  made[0].onload();
  assert.strictEqual(e1.state, 'ok');
  assert.strictEqual(changed, 1);
  assert.ok(cache.get('d', 'http://x/d'), 'a place is free now');
  assert.strictEqual(cache.get('a', 'http://x/a'), e1, 'a loaded tile is not asked for again');
  assert.strictEqual(cache.requests, 4);
  // a failure is asked for again after 30 s, not at once
  made[1].onerror();
  const failed = cache.get('b', 'http://x/b');
  assert.strictEqual(failed.state, 'fail');
  assert.strictEqual(cache.requests, 4, 'not asked again at once');
  t = 29999;
  assert.strictEqual(cache.get('b', 'http://x/b').state, 'fail');
  assert.strictEqual(cache.requests, 4);
  t = 30001;
  const again = cache.get('b', 'http://x/b');
  assert.strictEqual(again.state, 'loading');
  assert.strictEqual(cache.requests, 5, 'asked again after 30 s');
  // it holds at most maxEntries
  for (const k of ['e', 'f', 'g', 'h', 'i', 'j']) {
    const m = cache.get(k, 'http://x/' + k);
    if (m) made[made.length - 1].onload();
  }
  assert.ok(cache.map.size <= 5, 'size ' + cache.map.size);
}

// WMS box and addresses
{
  const [a, b, c, d] = T.tileBBox(0, 0, 0).split(',').map(Number);
  assert.ok(Math.abs(a + 20037508.34) < 1 && Math.abs(b + 20037508.34) < 1 && Math.abs(c - 20037508.34) < 1 && Math.abs(d - 20037508.34) < 1);
  const [e, f, g, h] = T.tileBBox(1, 1, 0).split(',').map(Number);
  assert.ok(Math.abs(e - 0) < 1e-6 && Math.abs(f - 0) < 1e-6 && Math.abs(g - 20037508.34) < 1 && Math.abs(h - 20037508.34) < 1);
  assert.strictEqual(T.urlFor(T.BASES.streets, 5, 9, 12), 'https://tile.openstreetmap.org/5/9/12.png');
  assert.strictEqual(T.urlFor(T.BASES.topo, 5, 9, 12), 'https://a.tile.opentopomap.org/5/9/12.png');
  assert.strictEqual(T.urlFor(T.BASES.satellite, 5, 9, 12), 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/5/12/9');
  assert.strictEqual(T.urlFor(T.BASES.dark, 5, 9, 12, 'http://localhost:9/'), 'http://localhost:9/dark/5/9/12.png');
}

console.log('tiles: ok');
