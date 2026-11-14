/**
 * The map: the plan as the aircraft holds it, its lost-link route, landing sites, the leg or hold being flown, the
 * aircraft with its trail, and whatever command is being prepared (drawn before it is sent).
 *
 * No background map yet: a grid and a scale. Drag to move, wheel to zoom; "follow" keeps the aircraft centred.
 */
(function (root) {
  'use strict';
  const G = root.GCS;
  const geo = G.geo;
  const COL = { plan: '#c9d1d9', active: '#ff4fd8', lost: '#ffb000', preview: '#3fd0ff', site: '#7ee787', grid: '#1c2530', text: '#9aa7b4', own: '#ffffff', trail: '#5b6b7a', camera: '#39ff14' };

  class MapView {
    constructor(canvas) {
      this.c = canvas;
      this.ctx = canvas.getContext('2d');
      this.centre = [34.9, -117.88];
      this.ftPerPx = 600;
      this.follow = true;
      this.up = 0;                      // the compass heading at the top of the map: 0 north up, or the track
      this.trail = [];
      this.onClick = null;
      this.data = {};
      let drag = null;
      canvas.addEventListener('pointerdown', (e) => {
        const r = canvas.getBoundingClientRect();
        const h = this.handleAt(e.clientX - r.left, e.clientY - r.top);
        drag = { x: e.clientX, y: e.clientY, moved: false, handle: h, at: [e.clientX - r.left, e.clientY - r.top] };
        canvas.setPointerCapture(e.pointerId);
      });
      canvas.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const dx = e.clientX - drag.x;
        const dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
        if (drag.moved && drag.handle !== null) {
          const r = canvas.getBoundingClientRect();
          if (this.onHandle) this.onHandle(drag.handle, this.unproject(e.clientX - r.left, e.clientY - r.top), false);
        } else if (drag.moved) {
          this.follow = false;
          const r = canvas.getBoundingClientRect();
          const under = this.unproject(drag.at[0], drag.at[1]);
          const now = this.unproject(e.clientX - r.left, e.clientY - r.top);
          this.centre = [this.centre[0] + under[0] - now[0], this.centre[1] + under[1] - now[1]];
          drag.at = [e.clientX - r.left, e.clientY - r.top];
          this.draw();
        }
      });
      canvas.addEventListener('pointerup', (e) => {
        const r = canvas.getBoundingClientRect();
        if (drag && drag.handle !== null && this.onHandle) this.onHandle(drag.handle, drag.moved ? this.unproject(e.clientX - r.left, e.clientY - r.top) : null, true);
        else if (drag && !drag.moved && this.onClick) this.onClick(this.unproject(e.clientX - r.left, e.clientY - r.top), { x: e.clientX - r.left, y: e.clientY - r.top });
        drag = null;
      });
      canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        // Zoom by how far the wheel moved, not once per event: a trackpad sends dozens of small events for one
        // gesture, a mouse wheel one large one per notch (about 100, or 3 when it counts in lines). One notch is
        // about 12 %; a pinch (which arrives as a wheel event with ctrl) is finer-grained and gets more per unit.
        const dy = e.deltaY * (e.deltaMode === 1 ? 33 : e.deltaMode === 2 ? 300 : 1);
        const step = Math.max(-0.3, Math.min(0.3, dy * (e.ctrlKey ? 0.008 : 0.0012)));
        const r = canvas.getBoundingClientRect();
        const x = e.clientX - r.left;
        const y = e.clientY - r.top;
        const under = this.unproject(x, y);
        this.ftPerPx = Math.min(20000, Math.max(2, this.ftPerPx * Math.exp(step)));
        if (!this.follow) {
          // keep the place under the pointer where it is
          const now = this.unproject(x, y);
          this.centre = [this.centre[0] + under[0] - now[0], this.centre[1] + under[1] - now[1]];
        }
        this.draw();
      }, { passive: false });
    }

    resize() {
      const r = this.c.getBoundingClientRect();
      const dpr = root.devicePixelRatio || 1;
      this.w = Math.max(50, r.width);
      this.h = Math.max(50, r.height);
      this.c.width = Math.round(this.w * dpr);
      this.c.height = Math.round(this.h * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.draw();
    }

    project(p) {
      return geo.toScreen(p, this.centre, this.up, this.ftPerPx, [this.w, this.h]);
    }

    unproject(x, y) {
      return geo.fromScreen(x, y, this.centre, this.up, this.ftPerPx, [this.w, this.h]);
    }

    /** The index of the editing handle under a point of the canvas, or null. */
    handleAt(x, y) {
      const hs = this.data.handles || [];
      for (let i = hs.length - 1; i >= 0; i--) {
        const q = this.project(hs[i]);
        if (Math.hypot(q[0] - x, q[1] - y) < 11) return i;
      }
      return null;
    }

    /** The thing under a point of the canvas (an aircraft, a site, a route point, an airfield), or null: see js/pick.js. */
    pickAt(x, y) {
      return G.pick.pick(G.pick.items(this.data, geo.planLines), (p) => this.project(p), x, y, 12);
    }

    /** A ring and a few words where the user has just asked for something, for a moment (until the thing itself is drawn). */
    flash(p, text, ms) {
      this.flashing = { p, text, until: Date.now() + (ms || 2500) };
      this.draw();
    }

    /** Show all of these points. */
    fit(points) {
      if (!points.length) return;
      const lat = points.map((p) => p[0]);
      const lon = points.map((p) => p[1]);
      this.centre = [(Math.min(...lat) + Math.max(...lat)) / 2, (Math.min(...lon) + Math.max(...lon)) / 2];
      const k = Math.cos((this.centre[0] * Math.PI) / 180);
      const spanN = (Math.max(...lat) - Math.min(...lat)) * geo.FT_PER_DEG;
      const spanE = (Math.max(...lon) - Math.min(...lon)) * geo.FT_PER_DEG * k;
      this.ftPerPx = Math.max(2, 1.25 * Math.max(spanN / this.h, spanE / this.w, 1));
      this.follow = false;
      this.draw();
    }

    setAircraft(lat, lon, heading) {
      const last = this.trail[this.trail.length - 1];
      if (!last || geo.course(last, [lat, lon]).ft > 300) {
        this.trail.push([lat, lon]);
        if (this.trail.length > 4000) this.trail.shift();
      }
      this.own = { p: [lat, lon], heading };
      if (this.follow) this.centre = [lat, lon];
    }

    line(points, colour, width, dash) {
      const x = this.ctx;
      if (points.length < 2) return;
      x.beginPath();
      points.forEach((p, i) => {
        const q = this.project(p);
        if (i) x.lineTo(q[0], q[1]);
        else x.moveTo(q[0], q[1]);
      });
      x.strokeStyle = colour;
      x.lineWidth = width;
      x.setLineDash(dash || []);
      x.stroke();
      x.setLineDash([]);
    }

    circle(centre, radiusFt, colour, width, dash) {
      const x = this.ctx;
      const q = this.project(centre);
      x.beginPath();
      x.arc(q[0], q[1], Math.max(2, radiusFt / this.ftPerPx), 0, 2 * Math.PI);
      x.strokeStyle = colour;
      x.lineWidth = width;
      x.setLineDash(dash || []);
      x.stroke();
      x.setLineDash([]);
    }

    label(p, text, colour, dx, dy) {
      const x = this.ctx;
      const q = this.project(p);
      x.font = '12px ui-sans-serif, system-ui, sans-serif';
      x.fillStyle = colour;
      x.fillText(text, q[0] + (dx === undefined ? 8 : dx), q[1] + (dy === undefined ? -8 : dy));
    }

    plan(plan, colour, dash, labels) {
      if (!plan) return;
      const from = plan.field && plan.field.stand ? plan.field.stand : null;
      for (const l of geo.planLines(plan.items, from)) {
        this.line(l.points, colour, l.kind === 'route' ? 2 : 1.5, dash);
        if (l.kind === 'route') {
          l.points.slice(1).forEach((p, i) => {
            const q = this.project(p);
            this.ctx.fillStyle = colour;
            this.ctx.fillRect(q[0] - 3, q[1] - 3, 6, 6);
            if (labels) this.label(p, `${i + 1}  ${Math.round(l.alts[i] / 100) * 100} ft`, COL.text);
          });
        }
      }
    }

    /** Call a layer painter (js/overlays.js) at a stage of the drawing; a painter that fails must not take the map with it. */
    paint(stage) {
      const fn = this.stages && this.stages[stage];
      if (!fn) return;
      try {
        fn(this, this.ctx);
      } catch (e) {
        if (!this.paintFailed) console.error('map layer', stage, e);
        this.paintFailed = true;
      }
    }

    grid(noLines) {
      const x = this.ctx;
      const nm = this.ftPerPx / geo.NM;
      const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500];
      const step = steps.find((s) => s / nm >= 70) || 1000;
      const corners = [this.unproject(0, 0), this.unproject(this.w, 0), this.unproject(0, this.h), this.unproject(this.w, this.h)];
      const lat0 = Math.min(...corners.map((q) => q[0]));
      const lat1 = Math.max(...corners.map((q) => q[0]));
      const lon0 = Math.min(...corners.map((q) => q[1]));
      const lon1 = Math.max(...corners.map((q) => q[1]));
      const dLat = (step * geo.NM) / geo.FT_PER_DEG;
      const dLon = dLat / Math.cos((this.centre[0] * Math.PI) / 180);
      x.strokeStyle = COL.grid;
      x.lineWidth = 1;
      x.beginPath();
      if (!noLines) for (let la = Math.floor(lat0 / dLat) * dLat; la <= lat1; la += dLat) {
        const a1 = this.project([la, lon0]);
        const a2 = this.project([la, lon1]);
        x.moveTo(a1[0], a1[1]);
        x.lineTo(a2[0], a2[1]);
      }
      if (!noLines) for (let lo = Math.floor(lon0 / dLon) * dLon; lo <= lon1; lo += dLon) {
        const a1 = this.project([lat0, lo]);
        const a2 = this.project([lat1, lo]);
        x.moveTo(a1[0], a1[1]);
        x.lineTo(a2[0], a2[1]);
      }
      x.stroke();
      // scale bar
      const len = step / nm;
      x.strokeStyle = COL.text;
      x.lineWidth = 2;
      x.beginPath();
      x.moveTo(16, this.h - 18);
      x.lineTo(16 + len, this.h - 18);
      x.stroke();
      x.font = '12px ui-sans-serif, system-ui, sans-serif';
      x.fillStyle = COL.text;
      x.fillText(`${step} nmi`, 16, this.h - 24);
    }

    draw() {
      const x = this.ctx;
      const d = this.data;
      if (!this.w) return;
      x.clearRect(0, 0, this.w, this.h);
      const show = d.show || { trail: true, traffic: true, reach: true, camera: true };
      this.paint('base');
      this.paint('rasters');
      this.grid(!!this.baseOn); // with a map behind, the grid's lines go and the scale stays
      this.paint('under');
      // the plan the aircraft holds, its lost-link route and sites
      if (d.plan) {
        const p = d.plan;
        if (p.lost_link) {
          const first = p.lost_link[0] && p.lost_link[0].points ? p.lost_link[0].points[0] : null;
          this.plan({ items: p.lost_link }, COL.lost, [7, 5], false);
          if (first) this.label(first, d.lostLabel || 'lost-link route', COL.lost, 8, 16);
          if (this.own && first && d.airborne) this.line([this.own.p, first], COL.lost, 1, [2, 6]);
        }
        this.plan(p, COL.plan, null, true);
        for (const s of p.sites || []) {
          const q = this.project(s.aim);
          x.strokeStyle = COL.site;
          x.lineWidth = 2;
          x.strokeRect(q[0] - 5, q[1] - 5, 10, 10);
          this.label(s.aim, s.name, COL.site, 9, 4);
        }
      }
      // what is being flown now
      if (d.status) {
        if (d.status.leg && d.status.started) this.line(d.status.leg, COL.active, 3);
        if (d.status.hold) this.circle([d.status.hold.lat, d.status.hold.lon], d.status.hold.radius_ft, COL.active, 3);
      }
      // without the engine: how far the aircraft's own planner would count on gliding, and what it would have in hand at each site
      if (d.reach && this.own && show.reach) {
        this.circle(this.own.p, d.reach.radiusFt, COL.site, 1, [3, 7]);
        for (const s of d.reach.sites) this.label(s.aim, s.inReach ? `glide: ${Math.round(s.inHand / 100) * 100} ft in hand` : 'glide: OUT OF REACH', s.inReach ? COL.site : '#ff5252', 9, 18);
      }
      // what the belly camera is locked on: a cross, and the line of sight from the aircraft
      if (d.camera && show.camera) {
        const q = this.project(d.camera);
        if (this.own) this.line([this.own.p, d.camera], COL.camera, 1, [2, 4]);
        x.strokeStyle = COL.camera;
        x.lineWidth = 2;
        x.beginPath();
        x.moveTo(q[0] - 9, q[1]); x.lineTo(q[0] - 3, q[1]); x.moveTo(q[0] + 3, q[1]); x.lineTo(q[0] + 9, q[1]);
        x.moveTo(q[0], q[1] - 9); x.lineTo(q[0], q[1] - 3); x.moveTo(q[0], q[1] + 3); x.lineTo(q[0], q[1] + 9);
        x.stroke();
        this.label(d.camera, 'camera', COL.camera, 11, -8);
      }
      if (this.flashing) {
        if (Date.now() > this.flashing.until) this.flashing = null;
        else {
          const q = this.project(this.flashing.p);
          x.strokeStyle = COL.camera;
          x.lineWidth = 2;
          x.setLineDash([4, 3]);
          x.beginPath();
          x.arc(q[0], q[1], 14, 0, 2 * Math.PI);
          x.stroke();
          x.setLineDash([]);
          this.label(this.flashing.p, this.flashing.text, COL.camera, 18, -12);
        }
      }
      // a route from the route planner, chosen on its card: cyan dashes, and where no landing site is in glide reach in amber
      if (d.routeView && d.routeView.points.length > 1) {
        this.line(d.routeView.points, COL.preview, 3, [10, 5]);
        for (const g of d.routeView.gaps || []) this.line(g, COL.lost, 6);
        d.routeView.points.slice(1).forEach((p, i) => {
          const q = this.project(p);
          x.fillStyle = COL.preview;
          x.fillRect(q[0] - 3, q[1] - 3, 6, 6);
          if (p[2] !== undefined) this.label(p, `${Math.round(p[2] / 100) * 100} ft`, COL.preview, 8, -8);
        });
      }
      // a command being prepared
      const pv = d.preview;
      if (pv) {
        if (pv.plan) this.plan(pv.plan, COL.preview, [6, 4], false);
        if (pv.line) this.line(pv.line, COL.preview, 2, [6, 4]);
        if (pv.circle) this.circle(pv.circle.centre, pv.circle.radiusFt, COL.preview, 2, [6, 4]);
        if (pv.label && pv.at) this.label(pv.at, pv.label, COL.preview);
      }
      // the points of the route being edited: handles to drag
      (d.handles || []).forEach((p, i) => {
        const q = this.project(p);
        x.beginPath();
        x.arc(q[0], q[1], i === d.selected ? 8 : 6, 0, 2 * Math.PI);
        x.fillStyle = i === d.selected ? COL.preview : '#0b0e12';
        x.strokeStyle = COL.preview;
        x.lineWidth = 2;
        x.fill();
        x.stroke();
        this.label(p, String(i + 1), COL.preview, 11, -9);
      });
      // other aircraft: an arrowhead on its heading, its callsign and its height against ours in hundreds of feet
      for (const t of show.traffic ? d.traffic || [] : []) {
        const q = this.project([t.lat, t.lon]);
        if (q[0] < -30 || q[1] < -30 || q[0] > this.w + 30 || q[1] > this.h + 30) continue;
        const lvl = t.threat ? t.threat.level : null;
        const far = t.threat && (t.threat.dist_ft > 20 * geo.NM || Math.abs(t.threat.rel_ft) > 5000);
        const col = lvl === 'warning' ? '#ff3b3b' : lvl ? COL.lost : far ? '#6b7885' : '#e6edf3';
        x.save();
        x.translate(q[0], q[1]);
        x.rotate(((t.hdg - this.up) * Math.PI) / 180);
        x.beginPath();
        x.moveTo(0, -8);
        x.lineTo(6, 7);
        x.lineTo(0, 3);
        x.lineTo(-6, 7);
        x.closePath();
        x.fillStyle = lvl ? col : 'transparent';
        x.strokeStyle = col;
        x.lineWidth = 1.5;
        x.fill();
        x.stroke();
        x.restore();
        const rel = t.threat ? Math.round(t.threat.rel_ft / 100) : 0;
        const arrow = t.vs_fps > 8 ? ' ↑' : t.vs_fps < -8 ? ' ↓' : '';
        this.label([t.lat, t.lon], `${t.callsign} ${rel >= 0 ? '+' : '−'}${String(Math.abs(rel)).padStart(2, '0')}${arrow}`, col, 10, 4);
      }
      if (show.trail) this.line(this.trail, COL.trail, 1.5);
      if (this.own) {
        const q = this.project(this.own.p);
        x.save();
        x.translate(q[0], q[1]);
        x.rotate(((this.own.heading - this.up) * Math.PI) / 180);
        x.beginPath(); // a long-winged aircraft seen from above
        x.moveTo(0, -11);
        x.lineTo(2.5, -2);
        x.lineTo(17, 1);
        x.lineTo(17, 3);
        x.lineTo(2.5, 3);
        x.lineTo(1.5, 9);
        x.lineTo(5, 12);
        x.lineTo(-5, 12);
        x.lineTo(-1.5, 9);
        x.lineTo(-2.5, 3);
        x.lineTo(-17, 3);
        x.lineTo(-17, 1);
        x.lineTo(-2.5, -2);
        x.closePath();
        x.fillStyle = COL.own;
        x.strokeStyle = '#000';
        x.lineWidth = 1;
        x.fill();
        x.stroke();
        x.restore();
      }
      this.paint('over');
      // which way north is: an arrow that turns as the map does
      x.save();
      x.translate(this.w - 30, 62);
      x.rotate((-this.up * Math.PI) / 180);
      x.strokeStyle = COL.text;
      x.fillStyle = COL.text;
      x.lineWidth = 1.5;
      x.beginPath();
      x.moveTo(0, -14);
      x.lineTo(5, 0);
      x.lineTo(-5, 0);
      x.closePath();
      x.fill();
      x.beginPath();
      x.moveTo(0, 0);
      x.lineTo(0, 12);
      x.stroke();
      x.restore();
      x.font = '11px ui-sans-serif, system-ui, sans-serif';
      x.fillStyle = COL.text;
      x.textAlign = 'center';
      x.fillText('N', this.w - 30 - 11 * Math.sin((this.up * Math.PI) / 180), 62 - 20 * Math.cos((this.up * Math.PI) / 180) + 4);
      x.textAlign = 'start';
    }
  }

  G.MapView = MapView;
  G.COL = COL;
})(window);
