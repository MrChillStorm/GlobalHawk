/**
 * Small-area geometry on a flat earth, as the aircraft's mission manager does it (fdm/missionmgr.py):
 * good for drawing and for previews over tens to hundreds of miles, not for navigation.
 */
(function (root) {
  'use strict';
  const FT_PER_DEG = 364567.2;
  const NM = 6076.1;
  const rad = (d) => (d * Math.PI) / 180;
  const deg = (r) => (r * 180) / Math.PI;

  /** Course (deg true) and distance (ft) from a to b; points are [lat, lon]. */
  function course(a, b) {
    const dn = (b[0] - a[0]) * FT_PER_DEG;
    const de = (b[1] - a[1]) * FT_PER_DEG * Math.cos(rad(a[0]));
    return { deg: (deg(Math.atan2(de, dn)) + 360) % 360, ft: Math.hypot(dn, de) };
  }

  /** The point a distance (ft) along a course (deg) from a. */
  function along(a, courseDeg, ft) {
    const c = rad(courseDeg);
    return [a[0] + (ft * Math.cos(c)) / FT_PER_DEG, a[1] + (ft * Math.sin(c)) / (FT_PER_DEG * Math.cos(rad(a[0])))];
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

  const api = { FT_PER_DEG, NM, course, along, turn, planLines };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).geo = api;
})(typeof window !== 'undefined' ? window : globalThis);
