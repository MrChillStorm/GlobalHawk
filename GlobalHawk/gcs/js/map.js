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
  const COL = { plan: '#c9d1d9', active: '#ff4fd8', lost: '#ffb000', preview: '#3fd0ff', site: '#7ee787', grid: '#1c2530', text: '#9aa7b4', own: '#ffffff', trail: '#5b6b7a' };

  class MapView {
    constructor(canvas) {
      this.c = canvas;
      this.ctx = canvas.getContext('2d');
      this.centre = [34.9, -117.88];
      this.ftPerPx = 600;
      this.follow = true;
      this.trail = [];
      this.onClick = null;
      this.data = {};
      let drag = null;
      canvas.addEventListener('pointerdown', (e) => {
        drag = { x: e.clientX, y: e.clientY, c: this.centre.slice(), moved: false };
        canvas.setPointerCapture(e.pointerId);
      });
      canvas.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const dx = e.clientX - drag.x;
        const dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
        if (drag.moved) {
          this.follow = false;
          this.centre = [drag.c[0] + (dy * this.ftPerPx) / geo.FT_PER_DEG, drag.c[1] - (dx * this.ftPerPx) / (geo.FT_PER_DEG * Math.cos((drag.c[0] * Math.PI) / 180))];
          this.draw();
        }
      });
      canvas.addEventListener('pointerup', (e) => {
        if (drag && !drag.moved && this.onClick) {
          const r = canvas.getBoundingClientRect();
          this.onClick(this.unproject(e.clientX - r.left, e.clientY - r.top));
        }
        drag = null;
      });
      canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        this.ftPerPx = Math.min(20000, Math.max(2, this.ftPerPx * (e.deltaY > 0 ? 1.25 : 0.8)));
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
      const k = Math.cos((this.centre[0] * Math.PI) / 180);
      return [this.w / 2 + ((p[1] - this.centre[1]) * geo.FT_PER_DEG * k) / this.ftPerPx, this.h / 2 - ((p[0] - this.centre[0]) * geo.FT_PER_DEG) / this.ftPerPx];
    }

    unproject(x, y) {
      const k = Math.cos((this.centre[0] * Math.PI) / 180);
      return [this.centre[0] - ((y - this.h / 2) * this.ftPerPx) / geo.FT_PER_DEG, this.centre[1] + ((x - this.w / 2) * this.ftPerPx) / (geo.FT_PER_DEG * k)];
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

    grid() {
      const x = this.ctx;
      const nm = this.ftPerPx / geo.NM;
      const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500];
      const step = steps.find((s) => s / nm >= 70) || 1000;
      const tl = this.unproject(0, 0);
      const br = this.unproject(this.w, this.h);
      const dLat = (step * geo.NM) / geo.FT_PER_DEG;
      const dLon = dLat / Math.cos((this.centre[0] * Math.PI) / 180);
      x.strokeStyle = COL.grid;
      x.lineWidth = 1;
      x.beginPath();
      for (let la = Math.floor(br[0] / dLat) * dLat; la <= tl[0]; la += dLat) {
        const y = this.project([la, 0])[1];
        x.moveTo(0, y);
        x.lineTo(this.w, y);
      }
      for (let lo = Math.floor(tl[1] / dLon) * dLon; lo <= br[1]; lo += dLon) {
        const px = this.project([0, lo])[0];
        x.moveTo(px, 0);
        x.lineTo(px, this.h);
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
      this.grid();
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
      // a command being prepared
      const pv = d.preview;
      if (pv) {
        if (pv.plan) this.plan(pv.plan, COL.preview, [6, 4], false);
        if (pv.line) this.line(pv.line, COL.preview, 2, [6, 4]);
        if (pv.circle) this.circle(pv.circle.centre, pv.circle.radiusFt, COL.preview, 2, [6, 4]);
        if (pv.label && pv.at) this.label(pv.at, pv.label, COL.preview);
      }
      this.line(this.trail, COL.trail, 1.5);
      if (this.own) {
        const q = this.project(this.own.p);
        x.save();
        x.translate(q[0], q[1]);
        x.rotate((this.own.heading * Math.PI) / 180);
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
    }
  }

  G.MapView = MapView;
  G.COL = COL;
})(window);
