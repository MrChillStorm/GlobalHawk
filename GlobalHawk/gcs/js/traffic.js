/**
 * Other aircraft: read from FlightGear's AI and multiplayer tree, and judged against our own path.
 *
 * Alerting after NASA's detect-and-avoid studies (well clear: 0.75 nmi and 450 ft; warning when it is lost within
 * 25 s, corrective within 55 s, preventive for a pass inside 1.0 nmi and 700 ft). Simplified: both aircraft are
 * taken to fly straight on at their present velocities; the studies' "modified tau" is not computed.
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const HMD_FT = 0.75 * geo.NM;
  const ZTHR_FT = 450;
  const PREVENT_FT = 1.0 * geo.NM;
  const PREVENT_Z_FT = 700;
  const WARNING_S = 25;
  const CORRECTIVE_S = 55;
  const KT = 1.6878;

  /** FlightGear's /json/ai/models?d=3 into [{ callsign, lat, lon, alt_ft, hdg, kt, vs_fps }]. */
  function parse(tree) {
    const out = [];
    const leaf = (node, path) => {
      let n = node;
      for (const name of path) {
        n = n && n.children ? n.children.find((c) => c.name === name) : null;
        if (!n) return undefined;
      }
      return n.value;
    };
    for (const m of (tree && tree.children) || []) {
      if (!m.children || !['aircraft', 'multiplayer', 'tanker', 'swift'].includes(m.name)) continue;
      const lat = Number(leaf(m, ['position', 'latitude-deg']));
      const lon = Number(leaf(m, ['position', 'longitude-deg']));
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || leaf(m, ['valid']) === false) continue;
      out.push({
        callsign: String(leaf(m, ['callsign']) || '?'), lat, lon, alt_ft: Number(leaf(m, ['position', 'altitude-ft'])) || 0,
        hdg: Number(leaf(m, ['orientation', 'true-heading-deg'])) || 0, kt: Number(leaf(m, ['velocities', 'true-airspeed-kt'])) || 0,
        vs_fps: Number(leaf(m, ['velocities', 'vertical-speed-fps'])) || 0,
      });
    }
    return out;
  }

  /**
   * One aircraft against ours: { level: null | 'preventive' | 'corrective' | 'warning', t_s, dist_ft, rel_ft }.
   * own: { lat, lon, alt_ft, track, kt, vs_fps }.
   */
  function threat(own, t) {
    const c = geo.course([own.lat, own.lon], [t.lat, t.lon]);
    const rx = c.ft * Math.sin((c.deg * Math.PI) / 180); // east
    const ry = c.ft * Math.cos((c.deg * Math.PI) / 180); // north
    const v = (kt, hdg) => [kt * KT * Math.sin((hdg * Math.PI) / 180), kt * KT * Math.cos((hdg * Math.PI) / 180)];
    const vo = v(own.kt, own.track);
    const vt = v(t.kt, t.hdg);
    const vx = vt[0] - vo[0];
    const vy = vt[1] - vo[1];
    const rz = t.alt_ft - own.alt_ft;
    const vz = (t.vs_fps || 0) - (own.vs_fps || 0);
    const res = { level: null, t_s: null, dist_ft: c.ft, rel_ft: rz };
    // the first moment, up to two minutes on, inside a cylinder of radius r and half-height z
    const first = (r, z) => {
      for (let s = 0; s <= 120; s += 1) {
        if (Math.hypot(rx + vx * s, ry + vy * s) < r && Math.abs(rz + vz * s) < z) return s;
      }
      return null;
    };
    const loss = first(HMD_FT, ZTHR_FT);
    if (loss !== null && loss <= WARNING_S) return Object.assign(res, { level: 'warning', t_s: loss });
    if (loss !== null && loss <= CORRECTIVE_S) return Object.assign(res, { level: 'corrective', t_s: loss });
    const near = first(PREVENT_FT, PREVENT_Z_FT);
    if (near !== null && near <= CORRECTIVE_S && (loss === null || loss > CORRECTIVE_S)) return Object.assign(res, { level: 'preventive', t_s: near });
    return res;
  }

  /** The station's alert for the worst of them, or null. */
  function alert(list) {
    const rank = { warning: 0, corrective: 1, preventive: 2 };
    const bad = list.filter((t) => t.threat && t.threat.level).sort((a, b) => rank[a.threat.level] - rank[b.threat.level] || a.threat.t_s - b.threat.t_s)[0];
    if (!bad) return null;
    const where = `${bad.callsign}, ${(bad.threat.dist_ft / geo.NM).toFixed(1)} nmi, ${bad.threat.rel_ft >= 0 ? '+' : '-'}${Math.round(Math.abs(bad.threat.rel_ft) / 100) * 100} ft`;
    if (bad.threat.level === 'warning') return { id: 'traffic', level: 'warning', text: 'TRAFFIC, MANEUVER NOW', action: `${where}: inside 25 s. Change height or go to a point away from it at once` };
    if (bad.threat.level === 'corrective') return { id: 'traffic', level: 'caution', text: 'TRAFFIC, AVOID', action: `${where}: inside 55 s. Change height or route` };
    return { id: 'traffic', level: 'advisory', text: 'TRAFFIC, MONITOR', action: `${where}: will pass close; nothing to do yet` };
  }

  const api = { parse, threat, alert, HMD_FT, ZTHR_FT };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).traffic = api;
})(typeof window !== 'undefined' ? window : globalThis);
