/**
 * What is under the pointer on the map. The belly camera locks on whatever is clicked: an aircraft, a landing site, a
 * point of a route, an airfield, or, failing those, the bare place clicked.
 *
 * items: [{ kind, name, p: [lat, lon], alt_ft?, prio }]; the lowest prio that has anything within `tol` pixels wins,
 * and among those the nearest. project: ([lat, lon]) => [x, y] on the screen.
 */
(function (root) {
  'use strict';

  function pick(items, project, x, y, tol) {
    let best = null;
    for (const it of items || []) {
      const q = project(it.p);
      const d = Math.hypot(q[0] - x, q[1] - y);
      if (d > (it.tol || tol)) continue;
      const prio = it.prio === undefined ? 5 : it.prio;
      if (!best || prio < best.prio || (prio === best.prio && d < best.d)) best = { item: it, prio, d };
    }
    return best ? best.item : null;
  }

  /** Everything on the map that can be clicked, from what the map holds (plan, traffic, airfields drawn). */
  function items(data, planLines) {
    const out = [];
    for (const t of data.traffic || []) out.push({ kind: 'aircraft', name: t.callsign, p: [t.lat, t.lon], alt_ft: t.alt_ft, prio: 0, tol: 14 });
    const p = data.plan;
    if (p) {
      for (const s of p.sites || []) out.push({ kind: 'site', name: s.name, p: s.aim, prio: 1 });
      const from = p.field && p.field.stand ? p.field.stand : null;
      let n = 0;
      for (const l of planLines(p.items, from)) {
        if (l.kind !== 'route') continue;
        l.points.slice(1).forEach((q, i) => out.push({ kind: 'point', name: `route point ${++n} (${Math.round((l.alts[i] || 0) / 100) * 100} ft)`, p: [q[0], q[1]], prio: 2 }));
      }
      if (p.lost_link) {
        n = 0;
        for (const l of planLines(p.lost_link, null)) {
          if (l.kind === 'route') l.points.forEach((q) => out.push({ kind: 'point', name: `lost-link route point ${++n}`, p: [q[0], q[1]], prio: 2 }));
        }
      }
    }
    for (const a of data.airfields || []) out.push({ kind: 'airfield', name: a.name, p: [a.lat, a.lon], prio: 1 });
    return out;
  }

  const api = { pick, items };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).pick = api;
})(typeof window !== 'undefined' ? window : globalThis);
