// node tests/traffic.test.js
const assert = require('assert');
const T = require('../js/traffic.js');
const geo = require('../js/geo.js');
const own = { lat: 35, lon: -117, alt_ft: 20000, track: 0, kt: 200, vs_fps: 0 };
const at = (brg, nm, alt, hdg, kt, vs) => {
  const p = geo.along([own.lat, own.lon], brg, nm * geo.NM);
  return { callsign: 'X', lat: p[0], lon: p[1], alt_ft: alt, hdg, kt, vs_fps: vs || 0 };
};
// head-on, closing at 400 kt (675 ft/s): the volume's edge (0.75 nmi) is reached (d - 0.75) nmi / 400 kt later
const sec = (nm) => ((nm - 0.75) / 400) * 3600;
assert.ok(sec(10) > 55);
assert.strictEqual(T.threat(own, at(0, 10, 20000, 180, 200)).level, null);
const d55 = 0.75 + (400 * 50) / 3600; // 50 s from the volume
assert.strictEqual(T.threat(own, at(0, d55, 20000, 180, 200)).level, 'corrective');
const d25 = 0.75 + (400 * 20) / 3600;
const w = T.threat(own, at(0, d25, 20000, 180, 200));
assert.strictEqual(w.level, 'warning');
assert.ok(Math.abs(w.t_s - 20) <= 1.5, 'time to loss ' + w.t_s);
// the same 1,000 ft above: nothing
assert.strictEqual(T.threat(own, at(0, d25, 21000, 180, 200)).level, null);
// descending onto us from 1,000 ft above at 40 ft/s: it will be inside
assert.strictEqual(T.threat(own, at(0, d25, 21000, 180, 200, -40)).level, 'warning');
// passing 2 nmi abeam on a parallel opposite course: nothing
const abeam = (off, alt) => {
  const ahead = geo.along([own.lat, own.lon], 0, 3 * geo.NM);
  const p = geo.along(ahead, 90, off * geo.NM);
  return { callsign: 'Y', lat: p[0], lon: p[1], alt_ft: alt, hdg: 180, kt: 200, vs_fps: 0 };
};
assert.strictEqual(T.threat(own, abeam(2, 20000)).level, null);
// 0.9 nmi abeam and 600 ft above: preventive
assert.strictEqual(T.threat(own, abeam(0.9, 20600)).level, 'preventive');
// behind and going away: nothing
assert.strictEqual(T.threat(own, at(180, 1.5, 20000, 180, 200)).level, null);
// FlightGear's tree
const leafs = (o) => Object.keys(o).map((k) => (typeof o[k] === 'object' ? { name: k, children: leafs(o[k]) } : { name: k, value: o[k] }));
const tree = { name: 'models', children: [
  { name: 'aircraft', index: 0, children: leafs({ callsign: 'N172', valid: true, position: { 'latitude-deg': 35.1, 'longitude-deg': -117.2, 'altitude-ft': 19500 }, orientation: { 'true-heading-deg': 90 }, velocities: { 'true-airspeed-kt': 180, 'vertical-speed-fps': -5 } }) },
  { name: 'multiplayer', index: 0, children: leafs({ callsign: 'OH-ABC', position: { 'latitude-deg': 36, 'longitude-deg': -118, 'altitude-ft': 30000 }, orientation: { 'true-heading-deg': 270 }, velocities: { 'true-airspeed-kt': 400 } }) },
  { name: 'aircraft', index: 1, children: leafs({ callsign: 'GONE', valid: false, position: { 'latitude-deg': 1, 'longitude-deg': 1, 'altitude-ft': 1 } }) },
  { name: 'count', value: 3 },
] };
const list = T.parse(tree);
assert.deepStrictEqual(list.map((a) => a.callsign), ['N172', 'OH-ABC']);
assert.deepStrictEqual(list[0], { callsign: 'N172', lat: 35.1, lon: -117.2, alt_ft: 19500, hdg: 90, kt: 180, vs_fps: -5 });
assert.deepStrictEqual(T.parse(null), []);
// the alert is for the worst one
const a = T.alert([{ callsign: 'A', threat: { level: 'preventive', t_s: 30, dist_ft: 6000, rel_ft: 600 } }, { callsign: 'B', threat: { level: 'warning', t_s: 12, dist_ft: 9000, rel_ft: -200 } }, { callsign: 'C', threat: { level: null } }]);
assert.strictEqual(a.level, 'warning');
assert.ok(/^B, 1\.5 nmi, -200 ft/.test(a.action));
assert.strictEqual(T.alert([{ callsign: 'C', threat: { level: null } }]), null);
console.log('traffic OK');
