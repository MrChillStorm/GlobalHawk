/**
 * The flight display, after the MV-22B's flight format and airliner conventions (FAA AC 25-11B): attitude with a
 * flight path marker and its acceleration chevron, a speed tape with both of its limits drawn on it, an altitude
 * tape, vertical speed, a heading tape with the track. The aircraft flies itself, so what it is flying towards
 * (magenta) is on every scale. Trend arrows show where speed and height will be in 10 s.
 *
 * draw(d): d has pitch, roll, hdg, track, gamma (deg), kcas, mach, alt (ft), vs (ft/s), alpha, alphaLimit (deg),
 * vt (ft/s), udot (ft/s2), bankLimit (deg), and target { alt_ft, kcas }, course (deg or null), mode (text),
 * caution (bool). Missing numbers leave their part blank.
 */
(function (root) {
  'use strict';
  const G = root.GCS;
  const M = G.pfdmath;
  const C = { sky: '#2a66c8', ground: '#70471f', white: '#f2f2f2', mag: '#ff5fe0', amber: '#ffb81a', red: '#ff3333', green: '#40f25a', grey: '#8c8c8c', back: '#0b0e12', tape: '#1a222dcc' };
  const W = 400;
  const H = 336;
  const AX0 = 76, AX1 = 300, AY0 = 30, AY1 = 270, CX = 188, CY = 150, K = 5; // attitude window, its centre, px per deg
  const ok = Number.isFinite;

  class FlightDisplay {
    constructor(canvas) {
      this.c = canvas;
      const dpr = root.devicePixelRatio || 1;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      this.x = canvas.getContext('2d');
      this.x.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.last = null; // what was drawn, for checking
    }

    text(s, x, y, colour, size, align) {
      const c = this.x;
      c.font = `600 ${size || 12}px ui-sans-serif, system-ui, sans-serif`;
      c.fillStyle = colour || C.white;
      c.textAlign = align || 'left';
      c.textBaseline = 'middle';
      c.fillText(s, x, y);
    }

    draw(d) {
      const c = this.x;
      c.clearRect(0, 0, W, H);
      c.fillStyle = C.back;
      c.fillRect(0, 0, W, H);
      this.last = {};
      if (!ok(d.pitch) || !ok(d.roll)) {
        this.text('no attitude data', W / 2, H / 2, C.grey, 14, 'center');
        return;
      }
      this.attitude(d);
      this.speed(d);
      this.altitude(d);
      this.heading(d);
      this.text(d.mode || '', W / 2, 13, d.caution ? C.amber : C.mag, 13, 'center');
    }

    attitude(d) {
      const c = this.x;
      c.save();
      c.beginPath();
      c.rect(AX0, AY0, AX1 - AX0, AY1 - AY0);
      c.clip();
      c.translate(CX, CY);
      c.rotate((-d.roll * Math.PI) / 180);
      const y0 = -M.pitchY(d.pitch, K); // the horizon, below the centre when the nose is up
      c.fillStyle = C.sky;
      c.fillRect(-400, y0 - 800, 800, 800);
      c.fillStyle = C.ground;
      c.fillRect(-400, y0, 800, 800);
      c.strokeStyle = C.white;
      c.lineWidth = 1.5;
      c.beginPath();
      c.moveTo(-400, y0);
      c.lineTo(400, y0);
      for (let p = -30; p <= 30; p += 5) {
        if (!p) continue;
        const y = y0 + M.pitchY(p, K);
        const half = p % 10 ? 12 : 26;
        c.moveTo(-half, y);
        c.lineTo(half, y);
      }
      c.stroke();
      for (let p = -30; p <= 30; p += 10) {
        if (!p) continue;
        const y = y0 + M.pitchY(p, K);
        this.text(String(Math.abs(p)), -32, y, C.white, 10, 'right');
        this.text(String(Math.abs(p)), 32, y, C.white, 10, 'left');
      }
      c.restore();
      // bank scale, fixed; the pointer turns with the bank; the limit in amber
      c.save();
      c.translate(CX, CY);
      c.strokeStyle = C.white;
      c.lineWidth = 1.5;
      const R = 108;
      for (const b of [-45, -30, -20, -10, 0, 10, 20, 30, 45]) {
        const a = ((b - 90) * Math.PI) / 180;
        const r1 = b % 30 === 0 ? R + 9 : R + 5;
        c.beginPath();
        c.moveTo(R * Math.cos(a), R * Math.sin(a));
        c.lineTo(r1 * Math.cos(a), r1 * Math.sin(a));
        c.stroke();
      }
      if (ok(d.bankLimit)) {
        c.strokeStyle = C.amber;
        c.lineWidth = 3;
        for (const b of [-d.bankLimit, d.bankLimit]) {
          const a = ((b - 90) * Math.PI) / 180;
          c.beginPath();
          c.moveTo((R - 1) * Math.cos(a), (R - 1) * Math.sin(a));
          c.lineTo((R + 10) * Math.cos(a), (R + 10) * Math.sin(a));
          c.stroke();
        }
      }
      c.rotate((-d.roll * Math.PI) / 180);
      c.fillStyle = C.white;
      c.beginPath();
      c.moveTo(0, -R + 1);
      c.lineTo(-6, -R + 11);
      c.lineTo(6, -R + 11);
      c.closePath();
      c.fill();
      c.restore();
      // the aircraft: fixed
      c.strokeStyle = '#000';
      c.lineWidth = 5;
      const wings = () => {
        c.beginPath();
        c.moveTo(CX - 46, CY);
        c.lineTo(CX - 16, CY);
        c.lineTo(CX - 16, CY + 6);
        c.moveTo(CX + 46, CY);
        c.lineTo(CX + 16, CY);
        c.lineTo(CX + 16, CY + 6);
        c.stroke();
      };
      wings();
      c.strokeStyle = C.amber;
      c.lineWidth = 3;
      wings();
      c.fillStyle = C.amber;
      c.fillRect(CX - 2, CY - 2, 4, 4);
      // flight path marker: where the aircraft is going, not where it points; the chevron is its acceleration
      if (ok(d.gamma) && ok(d.track) && ok(d.hdg) && ok(d.kcas) && d.kcas > 40) {
        const r = (-d.roll * Math.PI) / 180;
        const ex = M.wrap(d.track - d.hdg) * K;
        const ey = -(d.gamma - d.pitch) * K;
        const fx = CX + ex * Math.cos(r) - ey * Math.sin(r);
        const fy = CY + ex * Math.sin(r) + ey * Math.cos(r);
        this.last.fpm = [fx, fy];
        if (fx > AX0 + 12 && fx < AX1 - 12 && fy > AY0 + 12 && fy < AY1 - 12) {
          c.strokeStyle = C.green;
          c.lineWidth = 2;
          c.beginPath();
          c.arc(fx, fy, 6, 0, 2 * Math.PI);
          c.moveTo(fx - 6, fy);
          c.lineTo(fx - 18, fy);
          c.moveTo(fx + 6, fy);
          c.lineTo(fx + 18, fy);
          c.moveTo(fx, fy - 6);
          c.lineTo(fx, fy - 12);
          c.stroke();
          if (ok(d.udot)) {
            const ay = fy - Math.max(-30, Math.min(30, ((Math.asin(Math.max(-1, Math.min(1, d.udot / 32.174))) * 180) / Math.PI) * K));
            c.beginPath();
            c.moveTo(fx - 30, ay - 5);
            c.lineTo(fx - 23, ay);
            c.lineTo(fx - 30, ay + 5);
            c.stroke();
          }
        }
      }
      c.strokeStyle = C.grey;
      c.lineWidth = 1;
      c.strokeRect(AX0, AY0, AX1 - AX0, AY1 - AY0);
    }

    /** A vertical tape: value at the centre, px per unit; calls tick(y, value) for each tick in view. */
    tape(x0, x1, value, px, step, each) {
      const c = this.x;
      c.fillStyle = C.tape;
      c.fillRect(x0, AY0, x1 - x0, AY1 - AY0);
      c.save();
      c.beginPath();
      c.rect(x0, AY0, x1 - x0, AY1 - AY0);
      c.clip();
      const span = (AY1 - AY0) / 2 / px;
      for (let v = Math.ceil((value - span) / step) * step; v <= value + span; v += step) each(CY - (v - value) * px, v);
      c.restore();
    }

    speed(d) {
      const c = this.x;
      if (!ok(d.kcas)) return;
      const x0 = 8, x1 = 70, px = 2.2;
      const y = (v) => CY - (v - d.kcas) * px;
      this.tape(x0, x1, d.kcas, px, 10, (ty, v) => {
        if (v < 0) return;
        c.strokeStyle = C.white;
        c.lineWidth = 1.5;
        c.beginPath();
        c.moveTo(x1 - 8, ty);
        c.lineTo(x1, ty);
        c.stroke();
        if (v % 20 === 0) this.text(String(v), x1 - 12, ty, C.white, 11, 'right');
      });
      c.save();
      c.beginPath();
      c.rect(x0, AY0, x1 - x0 + 10, AY1 - AY0);
      c.clip();
      // the limits: red where the aircraft cannot be
      if (ok(d.alpha) && ok(d.alphaLimit) && ok(d.mach)) {
        const lim = M.speedLimits(d.kcas, d.alpha, d.alphaLimit, d.mach);
        this.last.limits = lim;
        c.fillStyle = C.red;
        c.fillRect(x1 - 5, y(lim.low), 5, 600);
        c.fillRect(x1 - 5, y(lim.high) - 600, 5, 600);
      }
      if (d.target && ok(d.target.kcas)) {
        const by = Math.max(AY0 + 4, Math.min(AY1 - 4, y(d.target.kcas)));
        c.fillStyle = C.mag;
        c.beginPath();
        c.moveTo(x1, by);
        c.lineTo(x1 + 9, by - 7);
        c.lineTo(x1 + 9, by + 7);
        c.closePath();
        c.fill();
      }
      if (ok(d.vt) && ok(d.udot)) {
        const t = M.trend(d.kcas, M.kcasRate(d.kcas, d.vt, d.udot));
        this.last.speedTrend = t;
        if (Math.abs(t - d.kcas) > 1) this.arrow(x1 + 4, CY, y(t), C.green);
      }
      c.restore();
      this.readout(x0, x1 - 9, String(Math.round(d.kcas)));
      this.text(ok(d.mach) ? 'M ' + d.mach.toFixed(3) : '', x0 + 2, AY1 + 12, C.white, 12);
      if (d.target && ok(d.target.kcas)) this.text(String(Math.round(d.target.kcas)), x0 + 2, AY0 - 9, C.mag, 12);
    }

    altitude(d) {
      const c = this.x;
      if (!ok(d.alt)) return;
      const x0 = 310, x1 = 372, px = 0.1;
      const y = (v) => CY - (v - d.alt) * px;
      this.tape(x0, x1, d.alt, px, 100, (ty, v) => {
        c.strokeStyle = C.white;
        c.lineWidth = 1.5;
        c.beginPath();
        c.moveTo(x0, ty);
        c.lineTo(x0 + (v % 500 ? 6 : 10), ty);
        c.stroke();
        if (v % 500 === 0) this.text(String(v), x0 + 14, ty, C.white, 11);
      });
      c.save();
      c.beginPath();
      c.rect(x0 - 10, AY0, x1 - x0 + 10, AY1 - AY0);
      c.clip();
      if (d.target && ok(d.target.alt_ft)) {
        const by = Math.max(AY0 + 4, Math.min(AY1 - 4, y(d.target.alt_ft)));
        c.fillStyle = C.mag;
        c.beginPath();
        c.moveTo(x0, by);
        c.lineTo(x0 - 9, by - 7);
        c.lineTo(x0 - 9, by + 7);
        c.closePath();
        c.fill();
      }
      if (ok(d.vs)) {
        const t = M.trend(d.alt, d.vs);
        this.last.altTrend = t;
        if (Math.abs(t - d.alt) > 20) this.arrow(x0 - 4, CY, y(t), C.green);
      }
      c.restore();
      this.readout(x0 + 9, x1, String(Math.round(d.alt / 10) * 10));
      if (d.target && ok(d.target.alt_ft)) this.text(String(Math.round(d.target.alt_ft)), x1 - 2, AY0 - 9, C.mag, 12, 'right');
      // vertical speed: a square-root scale to 3,000 ft/min, so small rates can be read
      if (ok(d.vs)) {
        const fpm = d.vs * 60;
        const vy = (f) => CY - Math.sign(f) * Math.sqrt(Math.min(3000, Math.abs(f)) / 3000) * 110;
        c.strokeStyle = C.grey;
        c.lineWidth = 1;
        for (const f of [-3000, -1000, -500, 0, 500, 1000, 3000]) {
          c.beginPath();
          c.moveTo(380, vy(f));
          c.lineTo(f ? 386 : 392, vy(f));
          c.stroke();
        }
        c.strokeStyle = C.white;
        c.lineWidth = 3;
        c.beginPath();
        c.moveTo(396, CY);
        c.lineTo(382, vy(fpm));
        c.stroke();
        this.text((fpm >= 0 ? '+' : '') + Math.round(fpm / 10) * 10, x1 + 24, AY1 + 12, C.white, 12, 'right');
      }
    }

    heading(d) {
      const c = this.x;
      if (!ok(d.hdg)) return;
      const y0 = 286, y1 = 326, px = 3.4;
      c.fillStyle = C.tape;
      c.fillRect(AX0, y0, AX1 - AX0, y1 - y0);
      c.save();
      c.beginPath();
      c.rect(AX0, y0, AX1 - AX0, y1 - y0);
      c.clip();
      const hx = (h) => CX + M.wrap(h - d.hdg) * px;
      for (let h = 0; h < 360; h += 5) {
        const x = hx(h);
        if (x < AX0 - 20 || x > AX1 + 20) continue;
        c.strokeStyle = C.white;
        c.lineWidth = 1.5;
        c.beginPath();
        c.moveTo(x, y0);
        c.lineTo(x, y0 + (h % 10 ? 5 : 9));
        c.stroke();
        if (h % 10 === 0) this.text(h % 90 === 0 ? 'NESW'[h / 90] : String(h / 10).padStart(2, '0'), x, y0 + 19, C.white, 11, 'center');
      }
      if (ok(d.course)) {
        const x = Math.max(AX0 + 5, Math.min(AX1 - 5, hx(d.course)));
        c.fillStyle = C.mag;
        c.fillRect(x - 5, y0, 10, 6);
      }
      if (ok(d.track)) {
        const x = hx(d.track);
        c.strokeStyle = C.green;
        c.lineWidth = 2;
        c.beginPath();
        c.moveTo(x, y0 + 2);
        c.lineTo(x + 5, y0 + 9);
        c.lineTo(x, y0 + 16);
        c.lineTo(x - 5, y0 + 9);
        c.closePath();
        c.stroke();
      }
      c.restore();
      c.fillStyle = C.back;
      c.fillRect(CX - 18, y1 - 14, 36, 14);
      c.strokeStyle = C.white;
      c.lineWidth = 1;
      c.strokeRect(CX - 18, y1 - 14, 36, 14);
      this.text(String(Math.round(d.hdg) % 360).padStart(3, '0'), CX, y1 - 7, C.white, 12, 'center');
    }

    arrow(x, y0, y1, colour) {
      const c = this.x;
      const s = Math.sign(y1 - y0);
      c.strokeStyle = colour;
      c.lineWidth = 2.5;
      c.beginPath();
      c.moveTo(x, y0);
      c.lineTo(x, y1);
      c.moveTo(x - 4, y1 - 6 * s);
      c.lineTo(x, y1);
      c.lineTo(x + 4, y1 - 6 * s);
      c.stroke();
    }

    readout(x0, x1, s) {
      const c = this.x;
      c.fillStyle = '#000';
      c.fillRect(x0, CY - 11, x1 - x0, 22);
      c.strokeStyle = C.white;
      c.lineWidth = 1.5;
      c.strokeRect(x0, CY - 11, x1 - x0, 22);
      this.text(s, x1 - 4, CY, C.white, 15, 'right');
    }
  }

  G.FlightDisplay = FlightDisplay;
})(window);
