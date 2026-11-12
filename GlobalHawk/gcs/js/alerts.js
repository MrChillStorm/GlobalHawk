/**
 * The alert list: one list, ranked, with what to do.
 *
 * The aircraft raises its own alerts (in /gcs/down/status: { id, level, text, action }); the station adds what only
 * it can know (nothing heard from the aircraft). This keeps them in order (warning, caution, advisory; newest first
 * within a level), remembers which have been acknowledged, and says when a tone is due: once for each new warning
 * or caution, repeating until acknowledged. An alert goes when its condition ends and alerts again if it returns.
 * While the engine is out, the alerts that are only consequences of the glide are held back.
 */
(function (root) {
  'use strict';
  const RANK = { warning: 0, caution: 1, advisory: 2 };
  const HELD_BY = { engine: ['aoa', 'off-plan'] };
  const SILENT_MS = 3000;

  class Alerts {
    constructor(now) {
      this.now = now || (() => Date.now());
      this.items = []; // { id, level, text, action, since, acked }
    }

    /**
     * Take the aircraft's list and the link's state. `lastHeard`: when anything last came down (ms, or null);
     * `expected`: whether a link is expected at all (a station that has never connected does not alarm);
     * `own`: alerts the station raises itself.
     */
    update(fromAircraft, lastHeard, expected, own) {
      const t = this.now();
      const silent = expected && (lastHeard === null || t - lastHeard > SILENT_MS);
      let list = silent
        ? [{ id: 'no-link', level: 'warning', text: 'NO LINK TO THE AIRCRAFT', action: 'It flies its lost-link route by itself. Check the connection' }]
        : (fromAircraft || []).concat(own || []); // `own`: what the station itself sees, such as traffic
      const ids = new Set(list.map((a) => a.id));
      for (const root of Object.keys(HELD_BY)) if (ids.has(root)) list = list.filter((a) => !HELD_BY[root].includes(a.id));
      const next = [];
      for (const a of list) {
        const old = this.items.find((x) => x.id === a.id);
        next.push(old ? Object.assign(old, { level: a.level, text: a.text, action: a.action || '' }) : { id: a.id, level: a.level, text: a.text, action: a.action || '', since: t, acked: a.level === 'advisory' });
      }
      next.sort((a, b) => RANK[a.level] - RANK[b.level] || b.since - a.since);
      this.items = next;
      return next;
    }

    /** The level of tone due now: 'warning', 'caution' or null. */
    tone() {
      const un = this.items.filter((a) => !a.acked);
      return un.some((a) => a.level === 'warning') ? 'warning' : un.some((a) => a.level === 'caution') ? 'caution' : null;
    }

    /** Acknowledge one alert, or all of them. */
    acknowledge(id) {
      for (const a of this.items) if (id === undefined || a.id === id) a.acked = true;
    }
  }

  const api = { Alerts, SILENT_MS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else Object.assign((root.GCS = root.GCS || {}), api);
})(typeof window !== 'undefined' ? window : globalThis);
