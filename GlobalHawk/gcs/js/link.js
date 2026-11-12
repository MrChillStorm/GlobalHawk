/**
 * The station's end of the command link.
 *
 * The aircraft is reached through FlightGear's web server (or fdm/gcs_server.py, which speaks the same):
 *   ws://HOST:PORT/PropertyListener   {"command":"addListener"|"get"|"set","node":path[,"value":v]}
 *
 * The contract with the aircraft (see README.md):
 *   /gcs/up/heartbeat   "STATION:n", once a second. If the station that holds control stops, the aircraft flies its
 *                       lost-link route.
 *   /gcs/up/stick       {"station","p","r","y","t","s"} twenty times a second while the aircraft is flown by hand
 *   /gcs/up/cmd         {"seq","station","name","args"} as a JSON string
 *   /gcs/down/ack       {"seq","status":"accepted"|"rejected","reason"} : a command counts only when this comes back
 *   /gcs/down/status    what the aircraft is doing; /gcs/down/plan the plan it holds
 *
 * Link takes a transport { send(path, value), listen(paths), onValue, onState } so that the same code runs in the
 * browser (WsTransport) and in the node tests (a fake). `latency` (ms) delays everything going up and coming
 * down, as a satellite link does.
 */
(function (root) {
  'use strict';
  const ANSWER_MS = 5000;
  const BEAT_MS = 1000;
  const CAMERA = '/sim/globalhawk/camera/';
  const SLEW_MS = 170;

  class Link {
    constructor(o) {
      this.t = o.transport;
      this.station = o.station || 'LRE';
      this.latency = o.latency || 0;
      this.now = o.now || (() => Date.now());
      this.timer = o.setTimeout || ((fn, ms) => setTimeout(fn, ms));
      this.seq = o.firstSeq !== undefined ? o.firstSeq : Math.floor(this.now() / 1000) % 1000000000; // never reused after a reload
      this.beat = Math.floor(this.now() / 1000) % 1000000;
      this.commands = []; // newest last: { seq, name, args, state, reason, sentAt, answeredAt }
      this.values = {};
      this.listeners = [];
      this.state = { mode: 'idle' };
      this.beating = false;
      this.lastDown = null; // when anything last came down
      this.t.onValue = (path, value) => this.later(() => this.receive(path, value));
      this.t.onState = (s) => {
        this.state = s;
        this.emit('state');
      };
    }

    later(fn) {
      if (this.latency > 0) this.timer(fn, this.latency);
      else fn();
    }

    on(fn) {
      this.listeners.push(fn);
    }

    emit(what, data) {
      for (const fn of this.listeners) fn(what, data);
    }

    /** Start listening to properties and beating. */
    start(paths) {
      this.t.listen(['/gcs/down/ack', '/gcs/down/status', '/gcs/down/plan'].concat(paths || []));
      this.beating = true;
      const tick = () => {
        if (!this.beating) return;
        this.beat += 1;
        const b = `${this.station}:${this.beat}`;
        this.later(() => this.t.send('/gcs/up/heartbeat', b));
        this.expire();
        this.timer(tick, BEAT_MS);
      };
      tick();
    }

    /** Stop beating: to the aircraft this is a lost link. */
    stop() {
      this.beating = false;
    }

    /** Send a command. Returns its record, whose state goes 'sent' -> 'accepted' | 'rejected' | 'no answer'. */
    command(name, args) {
      this.seq += 1;
      const c = { seq: this.seq, name, args: args || {}, state: 'sent', reason: '', sentAt: this.now(), answeredAt: null };
      this.commands.push(c);
      if (this.commands.length > 50) this.commands.shift();
      const msg = JSON.stringify({ seq: c.seq, station: this.station, name, args: c.args });
      this.later(() => this.t.send('/gcs/up/cmd', msg));
      this.timer(() => this.expire(), ANSWER_MS + 2 * this.latency + 50);
      this.emit('command', c);
      return c;
    }

    /** Does the aircraft say this station holds control? */
    inControl() {
      return !!(this.status && this.status.control && this.status.control.holder === this.station);
    }

    /** One stick sample up the link: { p, r, y, t, s }. It arrives late by the delay, like everything else. */
    stick(v) {
      const msg = JSON.stringify({ station: this.station, p: v.p, r: v.r, y: v.y, t: v.t, s: v.s });
      this.later(() => this.t.send('/gcs/up/stick', msg));
    }

    /** The sensor operator's command to the belly camera ("cross", "nearest", "unlock", "point lat lon", "level",
     *  "level off"): to the camera itself, not a flight command, so it has no sequence number and no answer. */
    camera(text) {
      this.later(() => this.t.send(CAMERA + 'command', text));
    }

    /** Turn the camera for a moment (right and up, -1 to 1): a nudge of about a tenth of the picture. */
    cameraSlew(right, up) {
      this.later(() => {
        this.t.send(CAMERA + 'slew-right', right);
        this.t.send(CAMERA + 'slew-up', up);
      });
      this.timer(() => {
        this.t.send(CAMERA + 'slew-right', 0);
        this.t.send(CAMERA + 'slew-up', 0);
      }, this.latency + SLEW_MS);
    }

    expire() {
      const t = this.now();
      for (const c of this.commands) {
        if (c.state === 'sent' && t - c.sentAt >= ANSWER_MS + 2 * this.latency) {
          c.state = 'no answer';
          this.emit('command', c);
        }
      }
    }

    receive(path, value) {
      this.lastDown = this.now();
      this.values[path] = value;
      if (path === '/gcs/down/ack' && value) {
        let a;
        try {
          a = JSON.parse(value);
        } catch (e) {
          return;
        }
        const c = this.commands.find((x) => x.seq === a.seq && a.station === this.station);
        if (c && (c.state === 'sent' || c.state === 'no answer')) {
          c.state = a.status === 'accepted' ? 'accepted' : 'rejected';
          c.reason = a.reason || '';
          c.answeredAt = this.now();
          this.emit('command', c);
        }
      } else if (path === '/gcs/down/status' || path === '/gcs/down/plan') {
        let j = null;
        try {
          j = value ? JSON.parse(value) : null;
        } catch (e) {
          return;
        }
        this[path === '/gcs/down/status' ? 'status' : 'plan'] = j;
        this.emit(path === '/gcs/down/status' ? 'status' : 'plan', j);
      }
      this.emit('value', path);
    }
  }

  /** FlightGear's PropertyListener websocket. Reconnects by itself. */
  class WsTransport {
    constructor(host, port) {
      this.url = `ws://${host}:${port}/PropertyListener`;
      this.paths = [];
      this.ws = null;
      this.onValue = () => {};
      this.onState = () => {};
      this.closed = false;
    }

    listen(paths) {
      for (const p of paths) if (!this.paths.includes(p)) this.paths.push(p);
      if (!this.ws) this.connect();
      else if (this.ws.readyState === 1) this.subscribe(paths);
    }

    subscribe(paths) {
      for (const p of paths) {
        this.ws.send(JSON.stringify({ command: 'addListener', node: p }));
        this.ws.send(JSON.stringify({ command: 'get', node: p }));
      }
    }

    connect() {
      if (this.closed) return;
      this.onState({ mode: 'connecting', message: this.url });
      let ws;
      try {
        ws = new WebSocket(this.url);
      } catch (e) {
        setTimeout(() => this.connect(), 2000);
        return;
      }
      this.ws = ws;
      ws.onopen = () => {
        this.onState({ mode: 'live', message: this.url });
        this.subscribe(this.paths);
      };
      ws.onmessage = (ev) => {
        let msgs;
        try {
          msgs = JSON.parse(ev.data);
        } catch (e) {
          return;
        }
        if (!Array.isArray(msgs)) msgs = [msgs];
        for (const m of msgs) if (m && (m.path || m.node) !== undefined) this.onValue(m.path || m.node, m.value);
      };
      ws.onclose = () => {
        this.onState({ mode: 'down', message: 'no connection to ' + this.url });
        setTimeout(() => this.connect(), 2000);
      };
      ws.onerror = () => {};
    }

    send(path, value) {
      if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ command: 'set', node: path, value }));
    }
  }

  const api = { Link, WsTransport, ANSWER_MS, BEAT_MS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else Object.assign((root.GCS = root.GCS || {}), api);
})(typeof window !== 'undefined' ? window : globalThis);
