// node tests/awcproxy.test.js
// The weather helper: it passes six paths on, adds the CORS header, and nothing else.
const assert = require('assert');
const http = require('http');
const { createServer } = require('../tools/awc-proxy.js');

const get = (port, path, method) => new Promise((resolve, reject) => {
  const r = http.request({ host: '127.0.0.1', port, path, method: method || 'GET' }, (res) => {
    let body = '';
    res.on('data', (d) => (body += d));
    res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
  });
  r.on('error', reject);
  r.end();
});

(async () => {
  const seen = [];
  const up = http.createServer((req, res) => {
    seen.push(req.url + ' ' + req.headers['user-agent']);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('[{"icaoId":"KTEST"}]');
  }).listen(0, '127.0.0.1');
  await new Promise((r) => up.on('listening', r));
  const proxy = createServer({ upstream: `http://127.0.0.1:${up.address().port}` }).listen(0, '127.0.0.1');
  await new Promise((r) => proxy.on('listening', r));
  const port = proxy.address().port;

  let r = await get(port, '/api/data/metar?ids=KEDW,KLAX&format=json');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.headers['access-control-allow-origin'], '*', 'the whole point');
  assert.strictEqual(r.body, '[{"icaoId":"KTEST"}]');
  assert.deepStrictEqual(seen, ['/api/data/metar?ids=KEDW,KLAX&format=json globalhawk-gcs-helper']);
  for (const p of ['airsigmet', 'gairmet', 'taf', 'pirep', 'cwa']) assert.strictEqual((await get(port, `/api/data/${p}?format=geojson`)).status, 200, p);
  // nothing else
  for (const p of ['/', '/etc/passwd', '/api/data/', '/api/data/metar/extra', '/api/data/../x', '/api/other', '/api/data/windtemp?region=all', 'http://evil.example/api/data/metar']) {
    r = await get(port, p);
    assert.ok(r.status === 404 || r.status === 400, `${p} -> ${r.status}`);
  }
  assert.strictEqual((await get(port, '/api/data/metar?ids=KEDW', 'POST')).status, 405);
  r = await get(port, '/api/data/metar', 'OPTIONS');
  assert.strictEqual(r.status, 204);
  assert.ok(/GET/.test(r.headers['access-control-allow-methods']));
  assert.strictEqual((await get(port, '/api/data/metar?ids=' + 'A'.repeat(1200))).status, 400, 'a long query');
  assert.strictEqual((await get(port, '/api/data/metar?ids=K<script>')).status, 400, 'odd characters');
  const before = seen.length;
  assert.strictEqual(seen.length, before, 'refused requests did not reach the service');
  // the service is down: 502 with the reason, still with the header
  up.close();
  await new Promise((r2) => setTimeout(r2, 50));
  r = await get(port, '/api/data/metar?ids=KEDW');
  assert.strictEqual(r.status, 502);
  assert.ok(/did not answer/.test(r.body));
  assert.strictEqual(r.headers['access-control-allow-origin'], '*');
  proxy.close();
  console.log('awc proxy: ok');
})().catch((e) => { console.error(e); process.exit(1); });
