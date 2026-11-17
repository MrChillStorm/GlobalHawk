/**
 * The one geometry of the earth the station uses: WGS84, the ellipsoid GPS, FlightGear and JSBSim fly on, the same as the aircraft's mission manager
 * (Nasal/missionmgr.nas, fdm/missionmgr.py) and fdm/wgs84.py, whose test vectors tests/geo.test.js checks this file against.
 *
 * Points are [lat, lon] in degrees (geodetic latitude). A local frame is the tangent plane at an origin point, north and east in feet:
 *   enu(o, p)          -> [north_ft, east_ft] of p in the tangent plane at o (through the points' ECEF coordinates: exact)
 *   fromEnu(o, n, e)   -> [lat, lon] of the surface point at (n, e) ft in that plane (the inverse, by Newton steps on enu)
 *   ftPerDeg(lat)      -> [ft in a degree of latitude, ft in a degree of longitude] there
 *   course(a, b)       -> { deg true, ft }: the bearing from a to b at a, and the distance in the tangent plane at a
 *   along(a, deg, ft)  -> the point ft along the course deg from a
 *   distance(a, b)     -> ft, course(a, b).ft without the bearing
 *   prep(p), enuPrep(f, q), coursePrep(f, q), distancePrep(f, q): the same from points prepared once, for a loop that asks about the same points many times (a lattice, a ring's vertices)
 * A straight line in the tangent plane at its start is the normal section towards its end, the geodesic to a few micrometres over a 5 nmi final, so a
 * runway's centreline is a straight line there. (The earlier flat model, 364,567.2 ft a degree of latitude and the same times cos(lat) for a degree of
 * longitude everywhere, tilted a final by 0.05 deg at 60 deg N.) The map's projection is the same plane about the map's centre: a plane, so a view some hundreds of
 * nmi across bends a little at its edges (a parallel 300 nmi east of the centre lies 9 nmi off the plane's east line at 35 deg N), and one wider than the earth's face (tens of
 * thousands of ft a pixel) is not a view of anything. fromEnu's twelve steps reach 1e-5 ft to 300 nmi, and to 3 ft at 78 N (as fdm/wgs84.py does).
 */
(function (root) {
  'use strict';
  const A_M = 6378137.0; // WGS84 semi-major axis, m
  const F_INV = 298.257223563; // WGS84 flattening: 1 / F_INV
  const E2 = (1.0 / F_INV) * (2.0 - 1.0 / F_INV); // first eccentricity squared
  const FT_PER_M = 1.0 / 0.3048;
  const NM = 6076.1;
  const rad = (d) => (d * Math.PI) / 180;
  const deg = (r) => (r * 180) / Math.PI;
  const D2R = Math.PI / 180;

  /** A point prepared for many enu() calls (as the origin, or as the point): its ECEF coordinates (metres from the earth's centre) and the sines and cosines of its latitude and longitude. */
  function prep(p) {
    const lat = p[0] * D2R;
    const lon = p[1] * D2R;
    const sp = Math.sin(lat);
    const cp = Math.cos(lat);
    const sl = Math.sin(lon);
    const cl = Math.cos(lon);
    const n = A_M / Math.sqrt(1.0 - E2 * sp * sp);
    return { lat: p[0], lon: p[1], x: n * cp * cl, y: n * cp * sl, z: n * (1.0 - E2) * sp, sp, cp, sl, cl };
  }

  /** [north, east] ft of the prepared point q in the tangent plane at the prepared point f. */
  function enuPrep(f, q) {
    const dx = q.x - f.x;
    const dy = q.y - f.y;
    const dz = q.z - f.z;
    const e = -f.sl * dx + f.cl * dy;
    const n = -f.sp * f.cl * dx - f.sp * f.sl * dy + f.cp * dz;
    return [n * FT_PER_M, e * FT_PER_M];
  }

  // the last origin's frame: a map draws thousands of points about one centre, a ring is looked at from one point
  let frame = null;

  /** [north, east] ft of the point p in the tangent plane at o. */
  function enu(o, p) {
    if (!frame || frame.lat !== o[0] || frame.lon !== o[1]) frame = prep(o);
    return enuPrep(frame, prep(p));
  }

  /** [ft in a degree of latitude, ft in a degree of longitude] at a latitude (the meridian's and the parallel's radii of the ellipsoid). */
  function ftPerDeg(lat) {
    const s = Math.sin(lat * D2R);
    const w = Math.sqrt(1.0 - E2 * s * s);
    const m = (A_M * (1.0 - E2)) / (w * w * w);
    const nn = A_M / w;
    return [m * D2R * FT_PER_M, nn * Math.cos(lat * D2R) * D2R * FT_PER_M];
  }

  /** [lat, lon] of the surface point at (n, e) ft in the tangent plane at o: Newton steps on enu() from the local scale, to 1e-5 ft (at most 12). */
  function fromEnu(o, n, e) {
    let [kn, ke] = ftPerDeg(o[0]);
    let lat = o[0] + n / kn;
    let lon = o[1] + e / ke;
    for (let i = 0; i < 12; i++) {
      const [cn, ce] = enu(o, [lat, lon]);
      if (Math.abs(n - cn) < 1e-5 && Math.abs(e - ce) < 1e-5) break;
      [kn, ke] = ftPerDeg(lat);
      lat += (n - cn) / kn;
      lon += (e - ce) / ke;
    }
    return [lat, lon];
  }

  /** Course (deg true) and distance (ft) from a to b; points are [lat, lon]. */
  function course(a, b) {
    return courseOf(enu(a, b));
  }

  const courseOf = (ne) => ({ deg: (deg(Math.atan2(ne[1], ne[0])) + 360) % 360, ft: Math.sqrt(ne[0] * ne[0] + ne[1] * ne[1]) });

  /** Distance (ft) from a to b in the tangent plane at a: course(a, b).ft without the bearing. */
  function distance(a, b) {
    const [dn, de] = enu(a, b);
    return Math.sqrt(dn * dn + de * de);
  }

  /** course() and distance() from prepared points (prep): for a lattice whose every join asks. */
  function coursePrep(fa, fb) {
    return courseOf(enuPrep(fa, fb));
  }
  function distancePrep(fa, fb) {
    const [dn, de] = enuPrep(fa, fb);
    return Math.sqrt(dn * dn + de * de);
  }

  /** The point a distance (ft) along a course (deg) from a. */
  function along(a, courseDeg, ft) {
    const c = rad(courseDeg);
    return fromEnu(a, ft * Math.cos(c), ft * Math.sin(c));
  }

  /** Smallest turn from course c0 to c1, deg, right positive. */
  function turn(c0, c1) {
    return ((((c1 - c0 + 180) % 360) + 360) % 360) - 180;
  }

  /** The line a plan's items draw: a list of [lat, lon] runs, one per item, each tagged with its kind. */
  function planLines(items, from) {
    const out = [];
    let last = from || null;
    for (const it of items || []) {
      let pts = [];
      if (it.kind === 'taxi') pts = (last ? [last] : []).concat(it.points);
      else if (it.kind === 'takeoff') pts = [it.start, it.end];
      else if (it.kind === 'route') pts = (last ? [last] : []).concat(it.points.map((p) => [p[0], p[1]]));
      else if (it.kind === 'land') pts = (last ? [last] : []).concat([it.fix, it.aim]);
      else if (it.kind === 'hold') pts = [it.centre];
      if (pts.length) {
        out.push({ kind: it.kind, points: pts, alts: it.kind === 'route' ? it.points.map((p) => p[2]) : null });
        last = pts[pts.length - 1];
      }
    }
    return out;
  }

  /** The holds of a plan's taxi items, placed: [{ id, name, kind, at: [lat, lon], course }], course the way the route goes there (deg). */
  function planHolds(items, from) {
    const out = [];
    let last = from || null;
    for (const it of items || []) {
      let end = null;
      if (it.kind === 'taxi') {
        const pts = (last ? [last] : []).concat(it.points);
        const off = last ? 1 : 0;
        for (const h of it.holds || []) {
          const k = h.i + off;
          if (!pts[k]) continue;
          const c = k > 0 ? course(pts[k - 1], pts[k]).deg : pts[k + 1] ? course(pts[k], pts[k + 1]).deg : 0;
          out.push({ id: h.id, name: h.name, kind: h.kind, at: [pts[k][0], pts[k][1]], course: c });
        }
        end = it.points[it.points.length - 1];
      } else if (it.kind === 'takeoff') end = it.end;
      else if (it.kind === 'route') end = it.points[it.points.length - 1];
      else if (it.kind === 'land') end = it.aim;
      else if (it.kind === 'hold') end = it.centre;
      if (end) last = end;
    }
    return out;
  }

  /**
   * A local flight from where the aircraft stands, lined up on a runway: takeoff straight ahead, a box to the
   * right at boxFt (default 3,000 ft over the fix; js/plancheck.js localBoxFt picks the height the aircraft can climb to and come down from), and a landing back on the same runway; the lost-link route goes straight to that landing.
   * For flying from any airport FlightGear starts it at. here is [lat, lon], hdg the runway's course, elev the
   * ground's height there (ft).
   */
  function localPlan(here, hdg, elev, boxFt) {
    const r = (v) => Math.round(v * 1e6) / 1e6;
    const pt = (p, alt) => (alt === undefined ? [r(p[0]), r(p[1])] : [r(p[0]), r(p[1]), alt]);
    // the height over the fix the aircraft's capability asks for: the path comes down to it in time to be taken over cleanly (js/flightmath.js), the way the 90 deg corner at the fix takes counted
    const FM = typeof module !== 'undefined' && module.exports ? require('./flightmath.js') : root.GCS.flightmath;
    const lead = FM.turn({ delta_deg: 90, alt_ft: elev + 3000, vg_fps: 250 }).lead_ft;
    const fixAlt = Math.round((elev + FM.finalFixHeightAgl(10 * NM, 20000, lead)) / 100) * 100;
    // the box's height: given (js/plancheck.js localBoxFt picks the highest the aircraft can climb to and come down from), else 3,000 ft over the fix: a descent that is 2 deg in the 15 nmi to it, at any field
    const box = Number.isFinite(boxFt) ? boxFt : Math.round((fixAlt + 3000) / 500) * 500;
    const p1 = along(here, hdg, 12 * NM);
    const p2 = along(p1, hdg + 90, 15 * NM);
    const p3 = along(p2, hdg + 180, 22 * NM);
    const fix = along(here, hdg + 180, 10 * NM);
    const aim = along(here, hdg, 800);
    const land = { kind: 'land', fix: pt(fix), aim: pt(aim) };
    return {
      id: 'local-from-here',
      note: 'A local flight from where the aircraft stood: takeoff, a box at ' + box.toLocaleString('en-US') + ' ft, landing on the same runway.',
      field: { name: 'here', lat: r(here[0]), lon: r(here[1]), elev_ft: Math.round(elev) },
      items: [
        { kind: 'takeoff', start: pt(here), end: pt(along(here, hdg, 9000)) },
        { kind: 'route', points: [pt(p1, box), pt(p2, box), pt(p3, box), pt(fix, fixAlt)] },
        land,
      ],
      lost_link: [{ kind: 'route', points: [pt(fix, fixAlt)] }, land],
      sites: [{ name: 'home', aim: pt(aim), course: Math.round(((hdg % 360) + 360) % 360 * 10) / 10, elev_ft: Math.round(elev) }],
    };
  }

  /**
   * The map's projection: a point [lat, lon] to the screen (x right, y down, in pixels) about a centre, with the
   * compass heading `up` at the top of the screen (0: north up; the aircraft's track: track up). `size` is [w, h].
   */
  function toScreen(p, centre, up, ftPerPx, size) {
    const [dn, de] = enu(centre, p);
    const c = Math.cos(rad(up));
    const s = Math.sin(rad(up));
    return [size[0] / 2 + (de * c - dn * s) / ftPerPx, size[1] / 2 - (dn * c + de * s) / ftPerPx];
  }

  /** The inverse: a point of the screen to [lat, lon]. */
  function fromScreen(x, y, centre, up, ftPerPx, size) {
    const right = (x - size[0] / 2) * ftPerPx;
    const top = (size[1] / 2 - y) * ftPerPx;
    const c = Math.cos(rad(up));
    const s = Math.sin(rad(up));
    const de = right * c + top * s;
    const dn = top * c - right * s;
    return fromEnu(centre, dn, de);
  }

  const api = { NM, enu, fromEnu, ftPerDeg, prep, enuPrep, course, coursePrep, distance, distancePrep, along, turn, planLines, planHolds, localPlan, toScreen, fromScreen };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).geo = api;
})(typeof window !== 'undefined' ? window : globalThis);
