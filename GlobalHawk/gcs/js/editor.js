/**
 * Editing a plan: its route and its lost-link route, point by point. Taxi, takeoff and landing items are kept as
 * they came. Pure data, no page: the page draws what this holds and sends what toSend() gives.
 */
(function (root) {
  'use strict';
  const clone = (x) => JSON.parse(JSON.stringify(x));

  class PlanEditor {
    constructor(plan) {
      this.plan = clone(plan);
      this.which = 'route'; // or 'lost'
      this.selected = null;
      if (!this.plan.id) this.plan.id = 'plan';
      this.selected = this.points().length - 1;
    }

    /** The route item being edited: the plan's first route, or the lost-link route's. */
    item() {
      const list = this.which === 'route' ? this.plan.items : this.plan.lost_link || [];
      return list.find((it) => it.kind === 'route') || null;
    }

    points() {
      const it = this.item();
      return it ? it.points : [];
    }

    edit(which) {
      this.which = which;
      if (which === 'lost' && !this.item()) {
        // no lost-link route yet: straight to the plan's own landing
        const land = this.plan.items.find((it) => it.kind === 'land');
        if (land) this.plan.lost_link = [{ kind: 'route', points: [[land.fix[0], land.fix[1], 6500]] }, clone(land)];
      }
      this.selected = this.points().length - 1;
    }

    /** A new point after the selected one, at that one's height (or 20,000 ft). It becomes the selected one. */
    add(latlon) {
      const pts = this.points();
      if (!this.item()) return;
      const i = this.selected === null || this.selected < 0 ? pts.length - 1 : this.selected;
      const alt = pts[i] ? pts[i][2] : 20000;
      pts.splice(i + 1, 0, [round6(latlon[0]), round6(latlon[1]), alt]);
      this.selected = i + 1;
      this.touch();
    }

    move(i, latlon) {
      const p = this.points()[i];
      if (!p) return;
      p[0] = round6(latlon[0]);
      p[1] = round6(latlon[1]);
      this.touch();
    }

    setAlt(i, alt) {
      const p = this.points()[i];
      if (p && Number.isFinite(alt)) {
        p[2] = alt;
        this.touch();
      }
    }

    remove(i) {
      const pts = this.points();
      if (pts.length <= 1 || !pts[i]) return false; // a route keeps at least one point
      pts.splice(i, 1);
      this.selected = Math.min(i, pts.length - 1);
      this.touch();
      return true;
    }

    touch() {
      if (!/ \(edited\)$/.test(this.plan.id)) this.plan.id += ' (edited)';
    }

    /** What goes up the link. Enroute the aircraft takes only a plan that begins with a route. */
    toSend(enroute) {
      const p = clone(this.plan);
      if (enroute) {
        const first = p.items.findIndex((it) => it.kind === 'route');
        p.items = first >= 0 ? p.items.slice(first) : p.items;
      }
      return p;
    }
  }

  const round6 = (x) => Math.round(x * 1e6) / 1e6;
  const api = { PlanEditor };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else Object.assign((root.GCS = root.GCS || {}), api);
})(typeof window !== 'undefined' ? window : globalThis);
