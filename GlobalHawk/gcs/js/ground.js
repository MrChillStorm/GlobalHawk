/**
 * An airport's ground network, and the taxi routes laid on it (docs/PLAN.md, "Starting at a stand from the planner").
 *
 * The aircraft sends the network when the station asks for it (the `airport` command; the message is described in fdm/airportdata.py): the stands, the taxi nodes
 * and the arcs between them, each arc named for its taxiway (or for the runway, "04R/22L"), and the runway ends. This module reads that, finds a route over
 * it, and lays the plan's taxi items: out from the stand to the runway's start, and in from the runway to the stand. It is the same method as fdm/groundplan.py,
 * which flew a taxi-box-taxi at EFHK, and it is checked against that (fdm/ground_checks.py): the same nodes, the same turn onto the centreline.
 *
 * Pure data, no page. Distances are feet, positions [lat, lon].
 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const geo = node ? require('./geo.js') : root.GCS.geo;
  const FT = geo.FT_PER_DEG;
  const rad = (d) => (d * Math.PI) / 180;
  const RUNWAY_ARC = /^\d\d[LRC]?\/\d\d[LRC]?$/; // how the groundnet names the arcs that lie on a runway
  const MIN_SPOT_RADIUS_M = 20; // the aircraft's wings are 116 ft (35 m) across: a stand of less than 20 m radius is marked as too small
  const STAND_PICK_FT = 100; // a click this near a stand picks the stand
  const FILLET_FT = 150; // the radius of the turn from the taxiway onto the runway's centreline (as groundplan.py)
  const LINEUP_FT = 450; // how far down the runway the aircraft lines up (at least; 150 ft past the end of the turn)
  const ROLLOUT_FT = 4700; // from the aiming point to where the rollout is over: 4,000 to 5,000 ft, flown at EFHK. The exit offered first lies beyond it.
  const CENTRE_FT = 12; // a node this near the centreline is on the runway, for the way back to the stand
  const ON_CENTRE_FT = 20; // a taxiway's end this near the centreline reaches the runway
  const ENTRY_FROM_FT = -100; // ... within this reach of the runway's start
  const ENTRY_TO_FT = 1500;
  const SQUARE_FT = 60; // a leg is square to the runway when its two ends are this near abreast
  const TAXI_KT = 15;
  const TURN_KT = 8;
  const TAKEOFF_FT = 9000;
  const HOLD_SHORT_FT = 200; // a runway is entered where the route comes within this of its centreline: the hold is there (docs/PLAN.md, "Hold points and clearances")
  const HOLD_NEAR_FT = 150; // a hold placed by hand takes the route's nearest point within this of the click
  const COURSE_TOL = 10; // degrees: a runway end is the plan's when its heading is this near the plan's course

  /** Distance in feet; the longitude scaled at the first point's latitude, as fdm/groundplan.py does (so that routes agree to the node). */
  function dist(p, q) {
    return Math.hypot((q[0] - p[0]) * FT, (q[1] - p[1]) * FT * Math.cos(rad(p[0])));
  }

  /** Feet along a runway's heading from its threshold and to the right of it, and back to latitude and longitude. */
  class Frame {
    constructor(thr, hdg) {
      this.thr = thr;
      this.hdg = hdg;
      this.h = rad(hdg);
    }

    to(p) {
      const n = (p[0] - this.thr[0]) * FT;
      const e = (p[1] - this.thr[1]) * FT * Math.cos(rad(this.thr[0]));
      return [n * Math.cos(this.h) + e * Math.sin(this.h), -n * Math.sin(this.h) + e * Math.cos(this.h)];
    }

    ll(a, l) {
      const n = a * Math.cos(this.h) - l * Math.sin(this.h);
      const e = a * Math.sin(this.h) + l * Math.cos(this.h);
      return [this.thr[0] + n / FT, this.thr[1] + e / (FT * Math.cos(rad(this.thr[0])))];
    }
  }

  const r6 = (x) => Math.round(x * 1e6) / 1e6;
  const pt = (p) => [r6(p[0]), r6(p[1])];
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const angle = (a, b) => Math.abs((((a - b + 180) % 360) + 360) % 360 - 180);

  /** null if the message is an airport message, or the first fault. */
  function check(m) {
    if (!m || typeof m !== 'object') return 'not an airport message';
    if (typeof m.icao !== 'string' || !Array.isArray(m.parking) || !Array.isArray(m.nodes) || !Array.isArray(m.arcs) || !Array.isArray(m.names) || !Array.isArray(m.runways)) return 'an airport message lacks a list';
    const p2 = (p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]) && Math.abs(p[0]) <= 90 && Math.abs(p[1]) <= 180;
    if (!m.nodes.every(p2)) return 'a taxi node is not a position';
    if (!m.arcs.every((a) => Array.isArray(a) && Number.isInteger(a[0]) && Number.isInteger(a[1]) && a[0] >= 0 && a[1] >= 0 && a[0] < m.nodes.length && a[1] < m.nodes.length && Number.isInteger(a[2]) && a[2] >= 0 && a[2] < m.names.length)) return 'an arc leaves the list of nodes';
    if (!m.parking.every((s) => s && p2([s.lat, s.lon]) && Number.isFinite(s.h) && Number.isFinite(s.r))) return 'a stand is not a position with a heading';
    if (!m.runways.every((r) => r && p2([r.lat, r.lon]) && Number.isFinite(r.h) && typeof r.n === 'string')) return 'a runway end is not a position with a heading';
    return null;
  }

  /** The other end's designator: 22L is 04R, 09 is 27. */
  function reciprocal(n) {
    const m = /^(\d\d)([LRC]?)$/.exec(n);
    if (!m) return null;
    const num = ((Number(m[1]) + 17) % 36) + 1;
    return String(num).padStart(2, '0') + ({ L: 'R', R: 'L', C: 'C', '': '' })[m[2]];
  }

  class Net {
    constructor(msg) {
      const bad = check(msg);
      if (bad) throw new Error(bad);
      this.icao = msg.icao;
      this.parking = msg.parking.map((s) => Object.assign({}, s, { fits: s.r >= MIN_SPOT_RADIUS_M }));
      this.nodes = msg.nodes;
      this.names = msg.names;
      this.arcs = msg.arcs;
      this.isRw = msg.names.map((n) => RUNWAY_ARC.test(n));
      this.adj = msg.nodes.map(() => []);
      for (const [a, b, k] of msg.arcs) {
        this.adj[a].push({ to: b, k });
        this.adj[b].push({ to: a, k });
      }
      this.runways = msg.runways.map((r) => Object.assign({}, r, { frame: new Frame([r.lat, r.lon], r.h) }));
    }

    nearestNode(p) {
      let best = -1;
      let bd = Infinity;
      this.nodes.forEach((q, i) => {
        const d = dist(p, q);
        if (d < bd) {
          bd = d;
          best = i;
        }
      });
      return best;
    }

    /** The stand nearest a point, if within STAND_PICK_FT; else null. */
    standNear(p, ft) {
      let best = null;
      let bd = ft === undefined ? STAND_PICK_FT : ft;
      for (const s of this.parking) {
        const d = dist(p, [s.lat, s.lon]);
        if (d <= bd) {
          bd = d;
          best = s;
        }
      }
      return best;
    }

    /** The cheapest way from node a to node b (Dijkstra, ties to the lower index as fdm/groundplan.py's heap does): the node indices, or null. forbid: nodes not to pass through. */
    route(a, b, forbid) {
      const best = new Map([[a, 0]]);
      const prev = new Map();
      const q = [[0, a]];
      const less = (x, y) => x[0] < y[0] || (x[0] === y[0] && x[1] < y[1]);
      const push = (v) => {
        q.push(v);
        let i = q.length - 1;
        while (i > 0) {
          const p = (i - 1) >> 1;
          if (!less(q[i], q[p])) break;
          [q[i], q[p]] = [q[p], q[i]];
          i = p;
        }
      };
      const pop = () => {
        const top = q[0];
        const last = q.pop();
        if (q.length) {
          q[0] = last;
          let i = 0;
          for (;;) {
            const l = 2 * i + 1;
            const r = l + 1;
            let s = i;
            if (l < q.length && less(q[l], q[s])) s = l;
            if (r < q.length && less(q[r], q[s])) s = r;
            if (s === i) break;
            [q[i], q[s]] = [q[s], q[i]];
            i = s;
          }
        }
        return top;
      };
      while (q.length) {
        const [d, x] = pop();
        if (x === b) break;
        if (d > (best.has(x) ? best.get(x) : Infinity)) continue;
        for (const e of this.adj[x]) {
          if (forbid && forbid.has(e.to) && e.to !== b) continue;
          const nd = d + dist(this.nodes[x], this.nodes[e.to]);
          if (nd < (best.has(e.to) ? best.get(e.to) : Infinity)) {
            best.set(e.to, nd);
            prev.set(e.to, x);
            push([nd, e.to]);
          }
        }
      }
      if (!best.has(b)) return null;
      const path = [b];
      while (path[path.length - 1] !== a) path.push(prev.get(path[path.length - 1]));
      return path.reverse();
    }

    length(nodes) {
      let s = 0;
      for (let i = 0; i + 1 < nodes.length; i++) s += dist(this.nodes[nodes[i]], this.nodes[nodes[i + 1]]);
      return s;
    }

    end(name) {
      return this.runways.find((r) => r.n === name) || null;
    }

    /** The runway's length in feet, threshold to threshold, if its other end is known. */
    runwayLength(rw) {
      const o = this.end(reciprocal(rw.n));
      return o ? dist([rw.lat, rw.lon], [o.lat, o.lon]) : null;
    }

    /** The runway end a point lies on the centreline of, flown along `course`: within `reach` feet along it (from `from` before the threshold). */
    runwayFor(point, course, from, to) {
      let best = null;
      let bl = Infinity;
      for (const r of this.runways) {
        if (angle(r.h, course) > COURSE_TOL) continue;
        const [a, l] = r.frame.to(point);
        if (a < from || a > to || Math.abs(l) > 150 || Math.abs(l) >= bl) continue;
        bl = Math.abs(l);
        best = r;
      }
      return best;
    }

    /** Where the runway can be left: the nodes on its centreline that a taxiway meets, from the threshold on, nearest first: [{ node, along, names }]. */
    exits(rw) {
      const len = this.runwayLength(rw);
      const out = [];
      this.nodes.forEach((p, i) => {
        const here = this.adj[i];
        if (!here.some((e) => this.isRw[e.k]) || !here.some((e) => !this.isRw[e.k])) return;
        const [a, l] = rw.frame.to(p);
        if (Math.abs(l) > 30 || a < 0 || (len !== null && a > len)) return;
        out.push({ node: i, along: a, names: [...new Set(here.filter((e) => !this.isRw[e.k]).map((e) => this.names[e.k]))] });
      });
      return out.sort((x, y) => x.along - y.along);
    }

    /** Labels for the taxiways: [{ name, at }], at the middle of the longest arc of each name. */
    labels() {
      if (this._labels) return this._labels;
      const best = new Map();
      for (const [a, b, k] of this.arcs) {
        if (this.isRw[k] || !this.names[k]) continue;
        const d = dist(this.nodes[a], this.nodes[b]);
        if (!best.has(k) || d > best.get(k).d) best.set(k, { d, at: [(this.nodes[a][0] + this.nodes[b][0]) / 2, (this.nodes[a][1] + this.nodes[b][1]) / 2] });
      }
      this._labels = [...best].map(([k, v]) => ({ name: this.names[k], at: v.at }));
      return this._labels;
    }
  }

  /**
   * From the stand to the runway's start: along the taxiways to the one that reaches the centreline nearest the threshold, the last straight square to the
   * runway, a turn of FILLET_FT radius onto the centreline (as fdm/groundplan.py), and down it to the line-up point. { points, entry, via, lineup_ft } or { error }.
   */
  function taxiOut(net, rw, stand) {
    const fr = rw.frame;
    const start = net.nearestNode(stand);
    if (start < 0) return { error: 'the airport has no taxi nodes' };
    const ends = [];
    net.nodes.forEach((p, i) => {
      const [a, l] = fr.to(p);
      if (a >= ENTRY_FROM_FT && a <= ENTRY_TO_FT && Math.abs(l) <= ON_CENTRE_FT && net.adj[i].some((e) => !net.isRw[e.k])) ends.push({ i, a });
    });
    ends.sort((x, y) => x.a - y.a);
    let nodes = null;
    for (const e of ends) {
      nodes = net.route(start, e.i);
      if (nodes) break;
    }
    if (!nodes) return { error: `no taxiway leads from the stand to runway ${rw.n}'s centreline within ${ENTRY_TO_FT.toLocaleString('en-US')} ft of its start` };
    const R = FILLET_FT;
    const al = nodes.map((i) => fr.to(net.nodes[i]));
    // the last node 150 ft or more from the centreline whose leg out is square to the runway: the turn begins on that leg
    let j = -1;
    for (let k = nodes.length - 2; k >= 0; k--) {
      if (Math.abs(al[k][1]) >= R && Math.abs(al[k + 1][0] - al[k][0]) < SQUARE_FT) {
        j = k;
        break;
      }
    }
    let pts;
    let lineup;
    let entry = null;
    if (j < 0) {
      pts = nodes.map((i) => net.nodes[i]);
      lineup = Math.max(LINEUP_FT, al[al.length - 1][0] + R);
    } else {
      const [a0, l0] = al[j];
      const side = l0 < 0 ? -1 : 1;
      entry = nodes[j];
      const square = j === 0 || Math.abs(al[j][0] - al[j - 1][0]) < SQUARE_FT; // the leg into it is square too: the turn starts where that one would have ended
      pts = nodes.slice(0, square ? j : j + 1).map((i) => net.nodes[i]);
      pts.push(fr.ll(a0, side * R));
      for (const t of [30, 60]) pts.push(fr.ll(a0 + R * (1 - Math.cos(rad(t))), side * (R - R * Math.sin(rad(t)))));
      pts.push(fr.ll(a0 + R, 0));
      lineup = Math.max(LINEUP_FT, a0 + 2 * R);
    }
    pts.push(fr.ll(lineup, 0));
    const via = [];
    for (let k = 1; k < nodes.length; k++) {
      const name = net.names[net.adj[nodes[k - 1]].find((e) => e.to === nodes[k]).k];
      if (name && via[via.length - 1] !== name) via.push(name);
    }
    return { points: pts.map(pt), entry, via, lineup_ft: lineup, nodes };
  }

  /**
   * From the centreline where the rollout is over, off by the exit and round to the stand: [the exit's junction, the taxiway's nodes, the stand].
   * exit: a node index from net.exits(rw), or null for the first one past the rollout (ROLLOUT_FT beyond the aiming point `aimAlong`).
   */
  function taxiIn(net, rw, stand, aimAlong, exit) {
    const fr = rw.frame;
    const list = net.exits(rw);
    let ex = exit === null || exit === undefined ? list.find((e) => e.along >= aimAlong + ROLLOUT_FT) : list.find((e) => e.node === exit);
    if (!ex) return { error: exit === null || exit === undefined ? `no taxiway leaves runway ${rw.n} beyond ${Math.round(aimAlong + ROLLOUT_FT).toLocaleString('en-US')} ft from its start` : 'that exit is not on the runway' };
    const end = net.nearestNode(stand);
    const forbid = new Set();
    net.nodes.forEach((p, i) => {
      if (Math.abs(fr.to(p)[1]) < CENTRE_FT) forbid.add(i);
    });
    let best = null;
    for (const e of net.adj[ex.node]) {
      if (net.isRw[e.k] || forbid.has(e.to)) continue;
      const nodes = net.route(e.to, end, forbid);
      if (nodes && (!best || net.length(nodes) < net.length(best))) best = nodes;
    }
    if (!best) return { error: `no taxiway leads from ${ex.names.join('/')} on runway ${rw.n} to the stand` };
    return { points: [net.nodes[ex.node]].concat(best.map((i) => net.nodes[i]), [stand]).map(pt), exit: ex, nodes: [ex.node].concat(best) };
  }

  const taxiItem = (points) => ({ kind: 'taxi', points, speed: TAXI_KT, turn_speed: TURN_KT, stop: true });

  /** The taxiway nearest a point: the name of the nearest arc that is not a runway's, or '' (a hold's name says where). */
  function taxiwayNear(net, p) {
    let best = '';
    let bd = Infinity;
    for (const [a, b, k] of net.arcs) {
      if (net.isRw[k] || !net.names[k]) continue;
      const q = net.nodes[a];
      const r = net.nodes[b];
      const n = [(r[0] - q[0]) * FT, (r[1] - q[1]) * FT * Math.cos(rad(q[0]))];
      const m = [(p[0] - q[0]) * FT, (p[1] - q[1]) * FT * Math.cos(rad(q[0]))];
      const w = Math.max(0, Math.min(1, (m[0] * n[0] + m[1] * n[1]) / Math.max(n[0] * n[0] + n[1] * n[1], 1e-9)));
      const d = Math.hypot(m[0] - w * n[0], m[1] - w * n[1]);
      if (d < bd) {
        bd = d;
        best = net.names[k];
      }
    }
    return bd < 400 ? best : '';
  }

  /** The runways as strips, once each: the end whose designator sorts first stands for the pair. */
  function strips(net) {
    return net.runways.filter((r) => {
      const o = reciprocal(r.n);
      return !o || !net.end(o) || r.n < o;
    }).map((r) => {
      const o = net.end(reciprocal(r.n));
      return { rw: r, name: o ? `${r.n}/${o.n}` : r.n, len: net.runwayLength(r) };
    });
  }

  /**
   * The holds of a taxi route: a hold short where the route first comes within HOLD_SHORT_FT of a runway's centreline (the point is put into the route where it is not one),
   * for every runway it enters or crosses; none for a runway it begins on. entering: the runway end the route is to line up on (named by its end, "22L", not by the pair).
   * Returns { points, holds: [{ i, kind: 'runway', name }] }, ids not yet given.
   */
  function runwayHolds(net, points, entering) {
    const found = [];
    for (const st of strips(net)) {
      const fr = st.rw.frame;
      const len = st.len === null ? 0 : st.len;
      const inside = (a, l) => Math.abs(l) <= HOLD_SHORT_FT && a >= -HOLD_SHORT_FT && a <= len + HOLD_SHORT_FT;
      const q = points.map((p) => fr.to(p));
      if (inside(q[0][0], q[0][1])) continue; // it begins on the runway: leaving it is no hold
      for (let k = 0; k + 1 < points.length; k++) {
        const [a0, l0] = q[k];
        const [a1, l1] = q[k + 1];
        const side = Math.sign(l0);
        if (Math.abs(l0) <= HOLD_SHORT_FT || side * l1 > HOLD_SHORT_FT) continue; // not outside to begin with, or the leg stays outside
        const w = (side * l0 - HOLD_SHORT_FT) / (side * l0 - side * l1); // where the leg comes to the line (a leg may cross the whole strip)
        if (!inside(a0 + w * (a1 - a0), HOLD_SHORT_FT * side)) continue;
        found.push({ k, w, name: entering && entering.n === st.rw.n || entering && entering.n === reciprocal(st.rw.n) ? entering.n : st.name });
        break;
      }
    }
    found.sort((x, y) => x.k - y.k || x.w - y.w);
    const out = points.map((p) => p);
    const holds = [];
    let shift = 0;
    for (const f of found) {
      const a = points[f.k];
      const b = points[f.k + 1];
      const at = f.w < 0.02 ? 0 : f.w > 0.98 ? 1 : f.w; // on a point already: no new one
      let i;
      if (at === 0) i = f.k + shift;
      else if (at === 1) i = f.k + 1 + shift;
      else {
        out.splice(f.k + 1 + shift, 0, pt([a[0] + at * (b[0] - a[0]), a[1] + at * (b[1] - a[1])]));
        i = f.k + 1 + shift;
        shift += 1;
      }
      const tw = taxiwayNear(net, out[i]);
      holds.push({ i, kind: 'runway', name: `hold short of runway ${f.name}${tw ? ' at ' + tw : ''}` });
    }
    return { points: out, holds };
  }

  /** Ids H1, H2, ... in the order of the plan's items and their holds. */
  function numberHolds(items) {
    let n = 0;
    for (const it of items) {
      if (it.kind !== 'taxi' || !it.holds) continue;
      it.holds.sort((a, b) => a.i - b.i);
      for (const h of it.holds) h.id = `H${++n}`;
    }
  }

  /**
   * The plan with taxi routes laid from the stand: a taxi item before the takeoff (the takeoff then begins at the line-up point) and one after the landing.
   * opts: { stand: [lat, lon], heading, exit (node index or null), holds (false: none; the default derives them) }. The result is { plan, out, in, notes } or { error }.
   */
  function addTaxi(net, plan, opts) {
    const p = clone(plan);
    const stand = opts.stand;
    if (!Array.isArray(stand) || !Number.isFinite(stand[0]) || !Number.isFinite(stand[1])) return { error: 'no stand chosen' };
    const items = p.items.filter((it, n, all) => !(it.kind === 'taxi' && (n === 0 || all[n - 1].kind === 'land')));
    const ti = items.findIndex((it) => it.kind === 'takeoff');
    const land = items.slice().reverse().find((it) => it.kind === 'land') || null;
    if (ti < 0 && !land) return { error: 'the plan has neither a takeoff nor a landing to taxi to or from' };
    const notes = [];
    let out = null;
    let into = null;
    if (ti >= 0) {
      const t = items[ti];
      const c = geo.course(t.start, t.end);
      const rw = net.runwayFor(t.start, c.deg, -300, 3000);
      if (!rw) return { error: `the takeoff is not on a runway of ${net.icao}: no runway end lies along its ${Math.round(c.deg)} deg course from its start` };
      out = taxiOut(net, rw, stand);
      if (out.error) return { error: out.error };
      const len = c.ft > 1000 ? c.ft : TAKEOFF_FT;
      t.start = pt(rw.frame.ll(out.lineup_ft, 0));
      t.end = pt(rw.frame.ll(out.lineup_ft + len, 0));
      out.rw = rw.n;
      out.length_ft = routeFt([stand].concat(out.points));
      if (ti > 0 && items[ti - 1].kind === 'taxi') items.splice(ti - 1, 1);
      const item = taxiItem(out.points);
      if (opts.holds !== false) {
        const rh = runwayHolds(net, out.points, rw);
        item.points = rh.points;
        item.holds = rh.holds.concat([{ i: rh.points.length - 1, kind: 'takeoff', name: `lined up on runway ${rw.n}: cleared for takeoff` }]);
        out.points = item.points;
        out.holds = item.holds;
      }
      items.splice(items.indexOf(t), 0, item);
      const rl = net.runwayLength(rw);
      if (rl !== null && out.lineup_ft + len > rl) notes.push(`the takeoff run from the line-up point (${Math.round(len).toLocaleString('en-US')} ft) is longer than runway ${rw.n} (${Math.round(rl).toLocaleString('en-US')} ft)`);
    }
    if (land) {
      const l = land;
      const c = geo.course(l.fix, l.aim);
      const rw = net.runwayFor(l.aim, c.deg, -300, 4000);
      if (!rw) return { error: `the landing is not on a runway of ${net.icao}: no runway end lies along its ${Math.round(c.deg)} deg course to its aiming point` };
      into = taxiIn(net, rw, stand, rw.frame.to(l.aim)[0], opts.exit);
      if (into.error) return { error: into.error };
      into.rw = rw.n;
      into.length_ft = routeFt(into.points);
      const item = taxiItem(into.points);
      if (opts.holds !== false) {
        const rh = runwayHolds(net, into.points, null);
        item.points = rh.points;
        if (rh.holds.length) item.holds = rh.holds;
        into.points = item.points;
        into.holds = rh.holds;
      }
      items.splice(items.indexOf(land) + 1, 0, item);
    }
    numberHolds(items);
    if (out && out.holds) out.holds = items.find((it) => it.kind === 'taxi' && it.holds && it.holds.some((h) => h.kind === 'takeoff')).holds;
    if (into && into.holds && into.holds.length) into.holds = items[items.length - 1].kind === 'taxi' ? items[items.length - 1].holds || [] : [];
    p.items = items;
    p.field = Object.assign({}, p.field, { stand: pt(stand), stand_heading: Math.round((opts.heading || 0) * 10) / 10 });
    return { plan: p, out, in: into, notes };
  }

  /**
   * A hold placed by the operator: on the taxi item `n` of the plan, at the point of its route nearest `at` (within HOLD_NEAR_FT; a point is put into the route where there
   * is none within 20 ft). Returns { plan } or { error }.
   */
  function addHold(net, plan, n, at) {
    const p = clone(plan);
    const it = p.items[n];
    if (!it || it.kind !== 'taxi') return { error: 'that is not a taxi route' };
    if ((it.holds || []).length >= 16) return { error: 'a taxi route carries at most 16 holds' };
    let best = null;
    for (let k = 0; k + 1 < it.points.length; k++) {
      const a = it.points[k];
      const b = it.points[k + 1];
      const v = [(b[0] - a[0]) * FT, (b[1] - a[1]) * FT * Math.cos(rad(a[0]))];
      const m = [(at[0] - a[0]) * FT, (at[1] - a[1]) * FT * Math.cos(rad(a[0]))];
      const w = Math.max(0, Math.min(1, (m[0] * v[0] + m[1] * v[1]) / Math.max(v[0] * v[0] + v[1] * v[1], 1e-9)));
      const d = Math.hypot(m[0] - w * v[0], m[1] - w * v[1]);
      if (!best || d < best.d) best = { k, w, d };
    }
    if (it.points.length === 1) {
      const d = dist(at, it.points[0]);
      best = d <= HOLD_NEAR_FT ? { k: 0, w: 0, d } : null;
    }
    if (!best || best.d > HOLD_NEAR_FT) return { error: `click within ${HOLD_NEAR_FT} ft of a taxi route` };
    let i;
    if (it.points.length === 1) i = 0;
    else {
      const a = it.points[best.k];
      const b = it.points[best.k + 1];
      const len = dist(a, b);
      if (best.w * len < 20) i = best.k;
      else if ((1 - best.w) * len < 20) i = best.k + 1;
      else {
        it.points.splice(best.k + 1, 0, pt([a[0] + best.w * (b[0] - a[0]), a[1] + best.w * (b[1] - a[1])]));
        i = best.k + 1;
        for (const h of it.holds || []) if (h.i >= i) h.i += 1; // the holds after the new point move up one
      }
    }
    if ((it.holds || []).some((h) => h.i === i)) return { error: 'there is a hold there already' };
    const tw = net ? taxiwayNear(net, it.points[i]) : '';
    const ids = new Set();
    for (const x of p.items) for (const h of x.holds || []) ids.add(h.id);
    let m = 1;
    while (ids.has(`H${m}`)) m++;
    it.holds = (it.holds || []).concat([{ i, id: `H${m}`, name: tw ? `hold on ${tw}` : 'hold', kind: 'point' }]).sort((x, y) => x.i - y.i);
    return { plan: p };
  }

  /** The plan without one hold (the point stays in the route). */
  function removeHold(plan, id) {
    const p = clone(plan);
    for (const it of p.items) {
      if (!it.holds) continue;
      const k = it.holds.findIndex((h) => h.id === id);
      if (k < 0) continue;
      it.holds.splice(k, 1);
      if (!it.holds.length) delete it.holds;
      return { plan: p };
    }
    return { error: 'no such hold' };
  }

  function routeFt(points) {
    let s = 0;
    for (let i = 0; i + 1 < points.length; i++) s += dist(points[i], points[i + 1]);
    return s;
  }

  /** The plan with its taxi items taken out and the takeoff back where the runway begins: not exact (the line-up point's 450 ft is gone only if the runway is known). */
  function removeTaxi(net, plan) {
    const p = clone(plan);
    p.items = p.items.filter((it) => it.kind !== 'taxi');
    if (net) {
      const t = p.items.find((it) => it.kind === 'takeoff');
      if (t) {
        const c = geo.course(t.start, t.end);
        const rw = net.runwayFor(t.start, c.deg, -300, 3000);
        if (rw) {
          t.start = pt([rw.lat, rw.lon]);
          t.end = pt(rw.frame.ll(c.ft, 0));
        }
      }
    }
    return p;
  }

  const api = {
    Net, Frame, check, reciprocal, dist, taxiOut, taxiIn, addTaxi, removeTaxi, routeFt, runwayHolds, addHold, removeHold, taxiwayNear, HOLD_SHORT_FT,
    MIN_SPOT_RADIUS_M, STAND_PICK_FT, FILLET_FT, LINEUP_FT, ROLLOUT_FT, TAXI_KT, TURN_KT, RUNWAY_ARC,
  };
  if (node) module.exports = api;
  else (root.GCS = root.GCS || {}).ground = api;
})(typeof window !== 'undefined' ? window : globalThis);
