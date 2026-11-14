/**
 * The line-of-sight limit of the ground station: how far away the aircraft can be and still be heard by a station
 * that needs to see it.
 *
 * It is geometry only: the radio horizon over a smooth earth, 1.23 × (√h₁ + √h₂) nautical miles with the heights in feet
 * (the usual 4/3-earth figure), no terrain and no link budget, so it is the most the link could reach and not what it does
 * reach. The station has no position of its own: it is taken to be at the field, with an antenna ANTENNA_FT up (assumed).
 * A satellite station (an MCE, or a delay of 600 ms and more) has no such limit, and no ring is drawn for it.
 *
 * The rule that shows the ring comes from NASA's human-factors list for remote pilot stations (P_1.5.5): a footprint that can be
 * hidden "should be automatically displayed when the RPA is approaching a location where a loss of link is likely".
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const K = 1.23;
  const ANTENNA_FT = 30;
  const NEAR_FRACTION = 0.85;
  const CROSS_MIN = 10;

  /** The radio horizon in nmi between two heights (ft above the smooth earth). */
  function horizonNm(h1, h2) {
    return K * (Math.sqrt(Math.max(0, h1)) + Math.sqrt(Math.max(0, h2 === undefined ? ANTENNA_FT : h2)));
  }

  /** A station that needs line of sight: not a satellite one. */
  function isLineOfSight(name, latencyMs) {
    return !(/^MCE/i.test(String(name || '')) || Number(latencyMs) >= 600);
  }

  /** Range at an altitude (MSL) from a station on ground at elev_ft. */
  function rangeNm(alt_ft, elev_ft, antenna_ft) {
    return horizonNm(Math.max(0, alt_ft - (elev_ft || 0)), antenna_ft === undefined ? ANTENNA_FT : antenna_ft);
  }

  /**
   * Where the aircraft stands against the limit. station: [lat, lon]; own: { lat, lon, alt_ft }.
   * path: [{ lat, lon, alt_ft }] with the aircraft first, or null; gs_kt for the time. Returns
   * { range_nm, dist_nm, frac, cross_nm, cross_min } where cross is where the path first goes beyond the range (null if it does not).
   */
  function margin(station, elev_ft, own, path, gs_kt) {
    const range = rangeNm(own.alt_ft, elev_ft);
    const dist = geo.course(station, [own.lat, own.lon]).ft / geo.NM;
    let cross = null;
    if (path && path.length > 1) {
      let s = 0;
      outer: for (let i = 0; i + 1 < path.length; i++) {
        const a = path[i];
        const b = path[i + 1];
        const leg = geo.course([a.lat, a.lon], [b.lat, b.lon]).ft / geo.NM;
        const n = Math.max(1, Math.ceil(leg / 2));
        for (let k = 1; k <= n; k++) {
          const f = k / n;
          const lat = a.lat + (b.lat - a.lat) * f;
          const lon = a.lon + (b.lon - a.lon) * f;
          const alt = a.alt_ft + (b.alt_ft - a.alt_ft) * f;
          if (geo.course(station, [lat, lon]).ft / geo.NM > rangeNm(alt, elev_ft)) {
            cross = s + leg * f;
            break outer;
          }
        }
        s += leg;
      }
    }
    return { range_nm: range, dist_nm: dist, frac: range > 0 ? dist / range : 0, cross_nm: cross, cross_min: cross !== null && gs_kt > 50 ? (cross / gs_kt) * 60 : null };
  }

  /** The layer's rule: { on, force, reason } or null. m is margin()'s answer, los whether the station needs line of sight. */
  function rule(los, m) {
    if (!los || !m) return null;
    if (m.frac >= NEAR_FRACTION) return { on: true, force: true, reason: `line-of-sight limit ${Math.round(m.range_nm)} nmi at this height: the aircraft is at ${Math.round(m.dist_nm)} nmi` };
    if (m.cross_min !== null && m.cross_min <= CROSS_MIN) return { on: true, force: true, reason: `the path leaves the line-of-sight range in ${Math.max(1, Math.round(m.cross_min))} min (limit ${Math.round(m.range_nm)} nmi)` };
    return null;
  }

  const api = { K, ANTENNA_FT, NEAR_FRACTION, CROSS_MIN, horizonNm, isLineOfSight, rangeNm, margin, rule };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).linkrange = api;
})(typeof window !== 'undefined' ? window : globalThis);
