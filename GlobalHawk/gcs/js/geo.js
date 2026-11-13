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

  /**
   * A local flight from where the aircraft stands, lined up on a runway: takeoff straight ahead, a box to the
   * right at 15,000 ft, and a landing back on the same runway; the lost-link route goes straight to that landing.
   * For flying from any airport FlightGear starts it at. here is [lat, lon], hdg the runway's course, elev the
   * ground's height there (ft).
   */
  function localPlan(here, hdg, elev) {
    const r = (v) => Math.round(v * 1e6) / 1e6;
    const pt = (p, alt) => (alt === undefined ? [r(p[0]), r(p[1])] : [r(p[0]), r(p[1]), alt]);
    const fixAlt = Math.round((elev + 3500) / 100) * 100;
    const p1 = along(here, hdg, 12 * NM);
    const p2 = along(p1, hdg + 90, 15 * NM);
    const p3 = along(p2, hdg + 180, 22 * NM);
    const fix = along(here, hdg + 180, 10 * NM);
    const aim = along(here, hdg, 800);
    const land = { kind: 'land', fix: pt(fix), aim: pt(aim) };
    return {
      id: 'local-from-here',
      note: 'A local flight from where the aircraft stood: takeoff, a box at 15,000 ft, landing on the same runway.',
      field: { name: 'here', lat: r(here[0]), lon: r(here[1]), elev_ft: Math.round(elev) },
      items: [
        { kind: 'takeoff', start: pt(here), end: pt(along(here, hdg, 9000)) },
        { kind: 'route', points: [pt(p1, 15000), pt(p2, 15000), pt(p3, 15000), pt(fix, fixAlt)] },
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
    const dn = (p[0] - centre[0]) * FT_PER_DEG;
    const de = (p[1] - centre[1]) * FT_PER_DEG * Math.cos(rad(centre[0]));
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
    return [centre[0] + dn / FT_PER_DEG, centre[1] + de / (FT_PER_DEG * Math.cos(rad(centre[0])))];
  }

  const api = { FT_PER_DEG, NM, course, along, turn, planLines, localPlan, toScreen, fromScreen };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).geo = api;
})(typeof window !== 'undefined' ? window : globalThis);
