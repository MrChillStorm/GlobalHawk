#!/usr/bin/env node
/**
 * A small helper for the ground station's weather layers.
 *
 *   node tools/awc-proxy.js [port]          (port 5402 unless given)
 *   then open the station with  index.html?awc=http://localhost:5402
 *
 * aviationweather.gov (SIGMET, G-AIRMET, METAR and TAF for the whole world, pilot reports) is public and needs no key, but it
 * does not send the header that lets a web page read it. This program sits between: the page asks it, it asks
 * aviationweather.gov, and it adds the header. It is not an open proxy: it answers GET for six paths under /api/data/ and nothing else,
 * only on this computer's own address, and it keeps nothing.
 */
'use strict';
const http = require('http');
const https = require('https');

const ALLOWED = /^\/api\/data\/(metar|taf|airsigmet|gairmet|pirep|cwa)$/;
const UPSTREAM = 'https://aviationweather.gov';
const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, OPTIONS', 'Access-Control-Allow-Headers': 'content-type' };

function createServer(opts) {
  const upstream = new URL((opts && opts.upstream) || UPSTREAM);
  const lib = upstream.protocol === 'https:' ? https : http;
  return http.createServer((req, res) => {
    const send = (code, body, type) => {
      res.writeHead(code, Object.assign({ 'Content-Type': type || 'text/plain' }, CORS));
      res.end(body);
    };
    if (req.method === 'OPTIONS') return send(204, '');
    if (req.method !== 'GET') return send(405, 'GET only');
    if (!req.url || req.url[0] !== '/') return send(400, 'a path, please');
    let u;
    try {
      u = new URL(req.url, 'http://localhost');
    } catch (e) {
      return send(400, 'bad address');
    }
    if (!ALLOWED.test(u.pathname)) return send(404, 'not one of the paths this helper passes on');
    const raw = req.url.includes('?') ? req.url.slice(req.url.indexOf('?') + 1) : ''; // as sent, before the parser tidies it
    if (raw.length > 1000 || /[^A-Za-z0-9=&,.\-_%:+]/.test(raw)) return send(400, 'the query is too long or has odd characters');
    const r = lib.request({ hostname: upstream.hostname, port: upstream.port || undefined, path: u.pathname + u.search, method: 'GET', headers: { 'User-Agent': 'globalhawk-gcs-helper', Accept: 'application/json' }, timeout: 10000 }, (up) => {
      res.writeHead(up.statusCode, Object.assign({ 'Content-Type': up.headers['content-type'] || 'application/json' }, CORS));
      up.pipe(res);
    });
    r.on('timeout', () => r.destroy(new Error('timeout')));
    r.on('error', (e) => send(502, 'aviationweather.gov did not answer: ' + e.message));
    r.end();
  });
}

if (require.main === module) {
  const port = Number(process.argv[2]) || 5402;
  createServer().listen(port, '127.0.0.1', () => console.log(`aviationweather.gov helper on http://localhost:${port} (open the station with ?awc=http://localhost:${port})`));
}

module.exports = { createServer, ALLOWED };
