/**
 * ?demo=1: a stand-in aircraft inside the page, for learning the station with nothing behind it.
 *
 * It keeps the link's contract (README.md): the same commands with the same answers, the same status and
 * telemetry. Inside it is NOT the flight model: a point that follows legs, turning at the bank the real aircraft
 * uses, climbing and descending by the forecast's table (js/perfdata.js), with taxi, takeoff and landing as simple
 * speed profiles. It has the lost link, an engine failure with a glide to a site in reach, holds, go to, resume,
 * home and the navigator switches. It has no flying by hand, no second station, and none of the alerts that need
 * the real model. The real thing is fdm/gcs_server.py (the flight model) or FlightGear.
 *
 * DemoAircraft is a transport for Link: { send(path, value), listen(paths), onValue, onState }.
 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const geo = node ? require('./geo.js') : root.GCS.geo;
  const plancheck = node ? require('./plancheck.js') : root.GCS.plancheck;
  const reach = node ? require('./reach.js') : root.GCS.reach;
  const predictApi = node ? require('./predict.js') : root.GCS.predict;
  const perfdata = node ? require('./perfdata.js') : root.GCS.perfdata;
  const NM = geo.NM;
  const KT = NM / 3600; // ft/s per kt
  const J = '/fdm/jsbsim/';
  const DRY_LB = 11450;
  const GLIDE_TAN = 0.07782;
  const LINK_TIMEOUT = 30;
  const LINK_TIMEOUT_MIN = 10; // as the aircraft's (fdm/onboard.py)
  const LINK_TIMEOUT_MAX = 300;
  const NAVS = ['kna', 'knb', 'lna', 'lnb'];
  const rad = (d) => (d * Math.PI) / 180;
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  const wrap = (d) => ((((d + 180) % 360) + 360) % 360) - 180;

  class DemoAircraft {
    constructor(o) {
      o = o || {};
      this.perf = predictApi.make(perfdata);
      this.speed = o.speed || 1;
      const f = o.field || { lat: 34.9, lon: -117.88, elev_ft: 2300, stand: [34.899922, -117.875789], stand_heading: 310 };
      const at = f.stand || [f.lat, f.lon];
      this.s = { t: 0, lat: at[0], lon: at[1], alt: f.elev_ft + 5, elev: f.elev_ft, hdg: f.stand_heading || 0, tas: 0, vs: 0, roll: 0, pitch: 0, fuel: 14150, thr: 0.05, failed: 0, ground: true };
      this.nav = { kna: 1, knb: 1, lna: 1, lnb: 1 };
      this.plan = null;
      this.items = [];
      this.i = 0;
      this.k = 0;
      this.started = false;
      this.done = false;
      this.off = null;
      this.saved = null;
      this.contingency = null;
      this.noSite = false;
      this.holder = null;
      this.stations = {};
      this.linkLast = null;
      this.linkLost = false;
      this.linkTimeout = LINK_TIMEOUT;
      this.answered = {};
      this.events = [];
      this.paths = [];
      this.last = {};
      this.down = { '/gcs/down/ack': '', '/gcs/down/status': '', '/gcs/down/plan': '' };
      this.onValue = () => {};
      this.onState = () => {};
      this.timer = null;
    }

    /* ------------------------------------------------------------ the transport's side */
    listen(paths) {
      for (const p of paths) if (!this.paths.includes(p)) this.paths.push(p);
      this.onState({ mode: 'live', message: 'demo: a stand-in aircraft in this page, not the flight model' });
      if (!this.timer && typeof setInterval !== 'undefined' && !this.manual) {
        let last = Date.now();
        this.timer = setInterval(() => {
          const now = Date.now();
          this.advance(Math.min(0.5, (now - last) / 1000) * this.speed);
          last = now;
        }, 50);
      }
      this.push();
    }

    send(path, value) {
      if (path === '/gcs/up/heartbeat') {
        const name = typeof value === 'string' && value.includes(':') ? value.slice(0, value.lastIndexOf(':')) : null;
        if (name === null) this.alive();
        else this.heard(name);
      } else if (path === '/gcs/up/cmd') this.command(value);
      else if (path === J + 'engine/failed') this.s.failed = value ? 1 : 0;
    }

    alive() {
      this.linkLast = this.s.t;
    }

    heard(name) {
      this.stations[name] = this.s.t;
      if (this.holder === null) {
        this.holder = name;
        this.note(`${name} has control`);
      }
      if (name === this.holder) this.alive();
    }

    note(text) {
      this.events.push([Math.round(this.s.t * 10) / 10, text]);
      if (this.events.length > 40) this.events.shift();
    }

    /** Run the aircraft on by dt seconds of its own time, in steps of a quarter second at most. */
    advance(dt) {
      let left = dt;
      while (left > 1e-9) {
        const h = Math.min(0.25, left);
        this.step(h);
        left -= h;
      }
      this.status();
      this.push();
    }

    push() {
      for (const p of this.paths) {
        const v = this.get(p);
        if (v !== undefined && this.last[p] !== v) {
          this.last[p] = v;
          this.onValue(p, v);
        }
      }
    }

    get(path) {
      const s = this.s;
      if (path in this.down) return this.down[path];
      const gs = s.tas / KT;
      const sigma = Math.pow(Math.max(0.05, 1 - 6.8756e-6 * s.alt), 4.2559);
      const a = 661.5 * Math.sqrt(Math.max(0.75, 1 - 6.8756e-6 * Math.min(s.alt, 36089)));
      const it = this.item();
      const tanks = [1736.5, 1736.5, 1557.3, 1557.3, 5624.4, 3088.0];
      const v = {
        '/position/latitude-deg': s.lat, '/position/longitude-deg': s.lon, '/position/altitude-ft': s.alt,
        '/orientation/heading-deg': (s.hdg + 360) % 360, '/orientation/pitch-deg': s.pitch, '/orientation/roll-deg': s.roll,
        '/velocities/airspeed-kt': gs * Math.sqrt(sigma), '/velocities/groundspeed-kt': gs, '/velocities/vertical-speed-fps': s.vs, '/velocities/mach': gs / a,
        [J + 'fuel/total-lbs']: s.fuel, [J + 'ctl/throttle-norm']: s.thr, [J + 'aero/alpha-deg']: s.ground ? 0 : 1.5, [J + 'ap/alpha-limit-deg']: gs / a > 0.5 ? 4 : 6,
        [J + 'flight-path/gamma-deg']: s.tas > 30 ? (Math.asin(clamp(s.vs / s.tas, -1, 1)) * 180) / Math.PI : 0, [J + 'flight-path/psi-gt-rad']: rad((s.hdg + 360) % 360),
        [J + 'accelerations/udot-ft_sec2']: s.udot || 0, [J + 'velocities/vt-fps']: s.tas, [J + 'ap/bank-limit-deg']: s.alt > 30000 ? 15 : 25,
        [J + 'engine/thrust-lbf']: s.failed ? 0 : 600 + 6400 * s.thr * sigma, [J + 'engine/fuel-flow-pph']: s.flow || 0, [J + 'engine/failed']: s.failed,
        [J + 'nav/miscompare']: 0, [J + 'inertia/weight-lbs']: DRY_LB + s.fuel,
      };
      tanks.forEach((c, n) => (v[`${J}propulsion/tank[${n}]/contents-lbs`] = (c * s.fuel) / 15300));
      NAVS.forEach((n) => (v[`${J}nav/${n}-on`] = this.nav[n]));
      void it;
      return v[path];
    }

    /** Other aircraft, made up, in the shape js/traffic.js gives: one shuttling across the first leg at 20,000 ft. */
    traffic() {
      const t = this.s.t;
      const period = (2 * 40 / 240) * 3600;
      const ph = (t % period) / period;
      const centre = geo.along([34.9, -117.88], 40, 18 * NM);
      const sAlong = ph < 0.5 ? ph * 80 - 20 : (1 - ph) * 80 - 20;
      const p = geo.along(centre, 130, sAlong * NM);
      return [{ callsign: 'SHUTTLE1', lat: p[0], lon: p[1], alt_ft: 20000, hdg: ph < 0.5 ? 130 : 310, kt: 240, vs_fps: 0 }];
    }

    /* ------------------------------------------------------------ the aircraft's end of the link */
    command(value) {
      let c;
      try {
        c = JSON.parse(value);
      } catch (e) {
        return;
      }
      const seq = Number(c.seq);
      const station = String(c.station || '');
      if (!Number.isFinite(seq) || typeof c.name !== 'string' || (this.answered[station] !== undefined && seq <= this.answered[station])) return;
      this.answered[station] = seq;
      this.heard(station);
      let reason;
      if (station !== this.holder) reason = `${this.holder} has control`;
      else {
        const fn = this['cmd_' + c.name.replace('.', '_')];
        try {
          reason = fn ? fn.call(this, c.args || {}) : c.name.startsWith('control.') || c.name === 'manual' ? 'not in the demo: it needs the flight model (fdm/gcs_server.py) or FlightGear' : 'unknown command';
        } catch (e) {
          reason = `bad arguments (${e.message})`;
        }
      }
      this.down['/gcs/down/ack'] = JSON.stringify({ seq, station, name: c.name, status: reason ? 'rejected' : 'accepted', reason: reason || '', t: Math.round(this.s.t * 100) / 100 });
      this.note(`${c.name} ${reason ? 'REJECTED: ' + reason : 'accepted'}`);
      this.status();
      this.push();
    }

    item() {
      return this.items[Math.min(this.i, this.items.length - 1)] || null;
    }

    airborne() {
      const it = this.item();
      return this.started && !this.done && it && (it.kind === 'route' || it.kind === 'hold');
    }

    cmd_plan(a) {
      const bad = plancheck.checkPlan(a);
      if (bad) return bad;
      if (this.started && !(this.airborne() && a.items[0].kind === 'route')) return 'a plan is being flown: a new one must begin with a route and be sent while enroute';
      this.plan = JSON.parse(JSON.stringify(a));
      if (this.started) {
        this.items = this.items.slice(0, this.i + 1).concat(JSON.parse(JSON.stringify(a.items)));
        this.off = this.saved = null;
        this.next();
      }
      this.down['/gcs/down/plan'] = JSON.stringify(a);
      return null;
    }

    cmd_start() {
      if (!this.plan) return 'no plan';
      if (this.started) return 'the plan has already begun';
      this.items = JSON.parse(JSON.stringify(this.plan.items));
      this.i = -1;
      this.started = true;
      this.next();
      return null;
    }

    remember() {
      const it = this.item();
      if (this.saved === null && it && it.kind === 'route' && !this.off) this.saved = [{ kind: 'route', points: it.points.slice(this.k) }].concat(JSON.parse(JSON.stringify(this.items.slice(this.i + 1))));
    }

    leave(items, what) {
      this.remember();
      this.items = this.items.slice(0, this.i + 1).concat(items);
      this.off = what;
      this.next();
    }

    cmd_goto(a) {
      if (!this.airborne()) return 'only while enroute';
      const p = [Number(a.lat), Number(a.lon), Number(a.alt_ft)];
      if (!p.every(Number.isFinite) || Math.abs(p[0]) > 90 || Math.abs(p[1]) > 180) return 'goto: a point needs 3 numbers';
      if (p[2] < 0 || p[2] > 65000) return `goto: height ${p[2]} ft is outside 0 to 65000 ft`;
      this.leave([{ kind: 'route', points: [p] }, { kind: 'hold', centre: [p[0], p[1]], alt: p[2] }], 'goto');
      return null;
    }

    holdRadius() {
      const v = Math.max(this.s.tas, 100);
      return (v * v) / (32.174 * Math.tan(rad(11.5)));
    }

    cmd_hold() {
      if (!this.airborne()) return 'only while enroute';
      const r = this.holdRadius();
      this.leave([{ kind: 'hold', centre: geo.along([this.s.lat, this.s.lon], this.s.hdg + 90, r), alt: this.target(), radius: r }], 'hold');
      return null;
    }

    cmd_altitude(a) {
      if (!this.airborne()) return 'only while enroute';
      const alt = a.alt_ft;
      if (!(typeof alt === 'number' && alt >= 0 && alt <= 65000)) return `height ${alt} ft is outside 0 to 65000 ft`;
      const it = this.item();
      if (it.kind === 'hold') it.alt = alt;
      else it.alt_override = alt;
      return null;
    }

    cmd_resume() {
      if (!this.started || this.saved === null) return 'not off the plan';
      if (this.contingency === 'engine') return 'the engine has failed';
      if (this.contingency === 'link') {
        this.contingency = null;
        this.linkLost = false;
      }
      this.items = this.items.slice(0, this.i + 1).concat(this.saved);
      this.saved = this.off = null;
      this.next();
      return null;
    }

    cmd_home() {
      if (!this.airborne()) return 'only while enroute';
      if (!this.plan.lost_link) return 'the plan has no contingency route';
      this.leave(JSON.parse(JSON.stringify(this.plan.lost_link)), 'home');
      return null;
    }

    cmd_linktimeout(a) {
      if (typeof a.sec !== 'number' || !Number.isFinite(a.sec)) return 'the time-out needs a number of seconds';
      if (a.sec < LINK_TIMEOUT_MIN || a.sec > LINK_TIMEOUT_MAX) return `the time-out is ${LINK_TIMEOUT_MIN} to ${LINK_TIMEOUT_MAX} s`;
      this.linkTimeout = a.sec;
      return null;
    }

    cmd_nav(a) {
      if (!NAVS.includes(a.name)) return 'unknown navigator';
      this.nav[a.name] = a.on ? 1 : 0;
      return null;
    }

    next() {
      this.i += 1;
      this.k = 0;
      if (this.i >= this.items.length) {
        this.done = true;
        this.note('plan complete');
        return;
      }
      const it = this.item();
      this.note('begin ' + it.kind);
      if (it.kind === 'engine_out') {
        const sites = (this.plan.sites || []).map((st) => ({ st, m: reach.margin(st, [this.s.lat, this.s.lon], this.s.alt, this.s.hdg) })).sort((a, b) => b.m - a.m);
        this.noSite = !sites.length || sites[0].m < 0;
        it.site = sites.length ? sites[0].st : null;
        it.task = 'glide';
        if (this.noSite) this.note('ALERT: no runway in reach');
      }
    }

    /** The height being flown towards. */
    target() {
      const it = this.item();
      if (!it) return this.s.alt;
      if (it.kind === 'hold') return it.alt;
      if (it.kind === 'route') return it.alt_override !== undefined ? it.alt_override : it.points[Math.min(this.k, it.points.length - 1)][2];
      return this.s.alt;
    }

    /* ------------------------------------------------------------ flying: a point, not a flight model */
    step(dt) {
      const s = this.s;
      s.t += dt;
      // the link: silence from the station in control for 30 s is a lost link
      if (this.linkLast !== null && !this.linkLost && s.t - this.linkLast > this.linkTimeout) {
        this.linkLost = true;
        const it = this.item();
        if (this.started && !this.done && this.contingency === null && it && (it.kind === 'route' || it.kind === 'hold') && this.plan.lost_link) {
          this.note('LINK LOST: the contingency route');
          this.contingency = 'link';
          this.leave(JSON.parse(JSON.stringify(this.plan.lost_link)), 'link');
        }
      }
      if (!this.started || this.done) {
        s.tas = Math.max(0, s.tas - 5 * dt);
        s.flow = s.failed ? 0 : 440;
        s.fuel = Math.max(0, s.fuel - (s.flow * dt) / 3600);
        return;
      }
      let it = this.item();
      if (s.failed && this.contingency !== 'engine' && !s.ground && it.kind !== 'engine_out' && (this.plan.sites || []).length) {
        this.note('ENGINE FAILED');
        this.contingency = 'engine';
        this.remember();
        this.items = this.items.slice(0, this.i + 1).concat([{ kind: 'engine_out' }]);
        this.off = 'engine';
        this.next();
        it = this.item();
      }
      const before = s.tas;
      const here = [s.lat, s.lon];
      let wantHdg = s.hdg;
      let bank = s.alt > 30000 ? 13 : 21.5;
      s.vs = 0;
      s.flow = 0;
      const w = DRY_LB + s.fuel;
      const fly = (targetAlt) => {
        // climb, level or descend towards a height, on the schedule's speed, as the forecast does
        s.tas += clamp(this.perf.ktas(s.alt) * KT - s.tas, -3 * dt, 3 * dt);
        if (s.alt < targetAlt - 150) {
          const r = this.perf.look(perfdata.climb_fpm, s.alt, w) / 60;
          s.vs = r > 50 / 60 ? r : 0;
          s.flow = this.perf.look(perfdata.climb_pph, s.alt, w);
          s.thr = 1;
          this.vmode = 'climb';
        } else if (s.alt > targetAlt + 150) {
          s.vs = this.perf.look(perfdata.descent_fpm, s.alt, w) / 60;
          s.flow = this.perf.look(perfdata.descent_pph, s.alt, w);
          s.thr = 0;
          this.vmode = 'descent';
        } else {
          s.vs = clamp((targetAlt - s.alt) / 10, -5, 5);
          const lv = this.perf.look(perfdata.level_pph, s.alt, w);
          s.flow = lv === null ? this.perf.look(perfdata.climb_pph, s.alt, w) : lv;
          s.thr = 0.25;
          this.vmode = 'level';
        }
      };
      const circle = (centre, radius, side) => {
        const c = geo.course(centre, here);
        return c.deg + 90 * side + side * clamp((60 * (c.ft - radius)) / radius, -30, 80);
      };
      const descendTo = (aim, elev) => {
        // level until the glide path comes down to the aircraft, then down it; true at touchdown
        const d = geo.course(here, aim);
        wantHdg = d.deg;
        const path = elev + 5 + d.ft * GLIDE_TAN;
        s.tas += clamp(133 * KT - s.tas, -2 * dt, 2 * dt);
        if (s.alt >= path) {
          s.vs = clamp((path - s.alt) / 2, -40, 0) - s.tas * GLIDE_TAN;
        }
        s.thr = 0;
        s.flow = s.failed ? 0 : this.perf.look(perfdata.descent_pph, s.alt, w);
        return d.ft < 400 || s.alt <= elev + 6;
      };
      if (it.kind === 'taxi') {
        s.ground = true;
        const p = it.points[this.k];
        const c = geo.course(here, p);
        wantHdg = c.deg;
        bank = 0;
        const last = this.k === it.points.length - 1;
        s.tas += clamp((last ? Math.min(it.speed || 15, Math.max(3, c.ft / 20)) : it.speed || 15) * KT - s.tas, -4 * dt, 3 * dt);
        s.hdg += clamp(wrap(wantHdg - s.hdg), -25 * dt, 25 * dt);
        s.flow = 450;
        s.thr = 0.1;
        if (c.ft < 25) {
          if (last) {
            s.tas = 0;
            this.next();
          } else this.k += 1;
        }
      } else if (it.kind === 'takeoff') {
        s.ground = s.tas < 140 * KT;
        s.hdg = geo.course(it.start, it.end).deg;
        wantHdg = s.hdg;
        s.tas += 3.5 * KT * dt * (s.tas < 150 * KT ? 1 : 0);
        s.thr = 1;
        s.flow = 2400;
        if (!s.ground) s.vs = 40;
        if (s.alt > s.elev + 100) {
          this.note('airborne, climb');
          this.next();
        }
      } else if (it.kind === 'route') {
        s.ground = false;
        const p = it.points[this.k];
        const c = geo.course(here, p);
        wantHdg = c.deg;
        fly(this.target());
        const radius = (s.tas * s.tas) / (32.174 * Math.tan(rad(bank)));
        const nextP = it.points[this.k + 1];
        const lead = nextP ? radius * Math.tan(rad(Math.abs(geo.turn(c.deg, geo.course(p, nextP).deg))) / 2) : 0;
        if (c.ft < Math.max(lead, 1500)) {
          if (nextP) {
            this.k += 1;
            delete it.alt_override;
            this.note(`leg ${this.k + 1}`);
          } else this.next();
        }
      } else if (it.kind === 'hold') {
        it.radius = it.radius || this.holdRadius();
        wantHdg = circle(it.centre, it.radius, 1);
        fly(it.alt);
      } else if (it.kind === 'land') {
        if (!it.onFinal && geo.course(here, it.fix).ft > 3000 && !it.passedFix) {
          wantHdg = geo.course(here, it.fix).deg;
          fly(s.alt);
          s.tas += clamp(133 * KT - s.tas, -2 * dt, 2 * dt);
        } else if (!it.rollout) {
          it.passedFix = true;
          if (descendTo(it.aim, s.elev)) {
            it.rollout = true;
            s.ground = true;
            s.alt = s.elev + 5;
          }
        } else this.rollout(dt);
      } else if (it.kind === 'engine_out') {
        const site = it.site;
        const ent = reach.entry(site);
        const d = geo.course(here, ent);
        const above = s.alt - site.elev_ft - reach.ENTRY_HEIGHT;
        if (it.task === 'glide') {
          wantHdg = d.deg;
          s.tas += clamp(125 * KT - s.tas, -2 * dt, 2 * dt);
          s.vs = -s.tas / 30;
          if (d.ft < 12000) it.task = above > 600 ? 'circle' : 'final';
        } else if (it.task === 'circle') {
          const r = 9000;
          const side = geo.turn(site.course, geo.course(ent, here).deg) >= 0 ? 1 : -1;
          const centre = geo.along(ent, site.course + 90 * side, r);
          wantHdg = circle(centre, r, side);
          s.vs = -25;
          if (above < 500 && Math.abs(geo.turn(s.hdg, site.course)) < 30) it.task = 'final';
          if (above < -300) it.task = 'final';
        } else if (!it.rollout) {
          if (descendTo(site.aim, site.elev_ft) || s.alt <= site.elev_ft + 6) {
            it.rollout = true;
            s.ground = true;
            s.alt = site.elev_ft + 5;
          }
        } else this.rollout(dt);
        s.thr = 0;
        s.flow = 0;
      }
      if (!s.ground) {
        // turn towards the wanted heading at the rate the bank gives
        const err = wrap(wantHdg - s.hdg);
        const rate = ((32.174 * Math.tan(rad(bank))) / Math.max(s.tas, 100)) * (180 / Math.PI);
        const turn = clamp(err, -rate * dt, rate * dt);
        s.hdg += turn;
        s.roll += clamp((Math.abs(err) > 1 ? Math.sign(err) * bank : 0) - s.roll, -5 * dt, 5 * dt);
        s.alt += s.vs * dt;
      } else s.roll = 0;
      s.pitch = s.ground ? 0 : clamp((Math.asin(clamp(s.vs / Math.max(s.tas, 100), -1, 1)) * 180) / Math.PI + 1.5, -15, 15);
      const pos = geo.along(here, s.hdg, s.tas * dt);
      s.lat = pos[0];
      s.lon = pos[1];
      s.udot = (s.tas - before) / dt;
      if (s.failed) s.flow = 0;
      s.fuel = Math.max(0, s.fuel - (s.flow * dt) / 3600);
    }

    rollout(dt) {
      const s = this.s;
      s.tas = Math.max(0, s.tas - 0.235 * 32.174 * dt);
      s.vs = 0;
      s.thr = 0;
      s.flow = s.failed ? 0 : 440;
      if (s.tas < 1) {
        s.tas = 0;
        this.note('rollout over');
        this.next();
      }
    }

    /* ------------------------------------------------------------ what it says it is doing */
    status() {
      const s = this.s;
      const it = this.item();
      const kind = !this.started ? null : this.done ? 'done' : it.kind;
      const st = {
        t: Math.round(s.t * 10) / 10, plan: this.plan ? this.plan.id || null : null, started: this.started, item: this.started ? this.i : null, kind,
        doing: !this.plan ? 'no plan' : !this.started ? 'waiting for start' : '', next: '', off_plan: this.off, contingency: this.contingency, alerts: [], hold: null, leg: null,
        link_lost: this.linkLost, link_age: this.linkLast === null ? null : Math.round((s.t - this.linkLast) * 10) / 10, link_timeout: this.linkTimeout,
        control: { holder: this.holder, offer_to: null, stations: Object.keys(this.stations).sort().map((n) => ({ name: n, age: Math.round((s.t - this.stations[n]) * 10) / 10 })) },
        manual: 0, target: { alt_ft: Math.round(this.target()), kcas: Math.round(this.get('/velocities/airspeed-kt') * 10) / 10 }, events: this.events.slice(-6),
      };
      const add = (id, level, text, action) => st.alerts.push({ id, level, text, action: action || '' });
      if (kind) {
        const rest = this.items.slice(this.i + 1).map((d) => d.kind);
        const after = { taxi: 'taxi', takeoff: 'takeoff', route: 'route', land: 'landing', hold: 'hold', engine_out: '' };
        const nxt = rest.length ? 'then ' + after[rest[0]] : 'end of plan';
        const togo = (p) => (geo.course([s.lat, s.lon], p).ft / NM).toFixed(0);
        if (kind === 'done') st.doing = 'plan complete';
        else if (kind === 'taxi') [st.doing, st.next] = [s.tas < 0.5 ? 'stopped' : `taxi, ${Math.round(s.tas / KT)} kt`, nxt];
        else if (kind === 'takeoff') [st.doing, st.next] = ['takeoff', nxt];
        else if (kind === 'route') {
          const head = { climb: 'climb to', descent: 'descend to', level: 'level at' }[this.vmode || 'level'];
          const p = it.points[this.k];
          st.doing = `${head} ${Math.round(this.target())} ft, leg ${this.k + 1} of ${it.points.length}, ${togo(p)} nmi to go`;
          st.next = this.k + 1 < it.points.length ? `then leg ${this.k + 2}` : nxt;
          st.leg = [[s.lat, s.lon], [p[0], p[1]]];
        } else if (kind === 'hold') {
          [st.doing, st.next] = [`hold at ${Math.round(it.alt)} ft`, 'until commanded'];
          st.hold = { lat: it.centre[0], lon: it.centre[1], radius_ft: Math.round(it.radius || this.holdRadius()), alt_ft: it.alt };
        } else if (kind === 'land') {
          st.doing = it.rollout ? 'rollout' : it.passedFix ? 'approach, glide path' : `level to the glide path, ${togo(it.aim)} nmi out`;
          st.next = it.rollout ? nxt : 'then landing';
          st.leg = [it.fix, it.aim];
        } else if (kind === 'engine_out') {
          st.doing = { glide: `ENGINE OUT: glide to ${it.site ? it.site.name : 'the runway'}`, circle: 'ENGINE OUT: circle to lose height', final: 'ENGINE OUT: final' }[it.task];
          st.next = { glide: 'then circle', circle: 'then final', final: 'then landing' }[it.task];
          st.site = it.site ? it.site.name : null;
        }
      }
      if (s.failed) add('engine', 'warning', 'ENGINE FAILED', `${it && it.kind === 'engine_out' && it.site ? `Gliding to ${it.site.name} by itself. Clear the runway. ` : ''}No restart is modelled`);
      if (this.noSite && s.failed) add('no-site', 'warning', 'NO RUNWAY IN REACH', 'Gliding towards the nearest');
      if (this.linkLost) add('link', 'caution', 'LINK WAS LOST', 'The aircraft left its plan when the link was lost. Resume when ready');
      const navs = NAVS.reduce((n, k) => n + this.nav[k], 0);
      if (navs < 2) add('nav-one', 'caution', navs === 1 ? 'ONE NAVIGATOR LEFT' : 'NO NAVIGATOR', 'No cross-check of attitude is left. Switch one on');
      if (s.fuel < 1500) add('fuel-low', 'caution', 'FUEL LOW', 'Return home');
      if (['goto', 'hold', 'home'].includes(this.off)) add('off-plan', 'advisory', 'OFF THE PLAN: ' + this.off.toUpperCase());
      this.down['/gcs/down/status'] = JSON.stringify(st);
      return st;
    }
  }

  const api = { DemoAircraft };
  if (node) module.exports = api;
  else Object.assign((root.GCS = root.GCS || {}), api);
})(typeof window !== 'undefined' ? window : globalThis);
