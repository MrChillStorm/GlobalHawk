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
 *   /gcs/down/airport   the ground network and runway ends of the airport the `airport` command asked for (fdm/airportdata.py)
 *
 * Link takes a transport { send(path, value), listen(paths), onValue, onState } so that the same code runs in the
 * browser (WsTransport) and in the node tests (a fake). `latency` (ms) delays everything going up and coming
 * down, as a satellite link does.
 */
(function (root) {
  'use strict';
  const ANSWER_MS = 5000;
  const ANSWER_LONG = { reposition: 60000 }; // FlightGear answers after it has loaded the scenery at the new place: 20 s and more (found 2026-11-16)
  const BEAT_MS = 1000;
  const CAMERA = '/sim/globalhawk/camera/';
  const CHAT = '/gcs/chat/line';  // the stations' messages to each other: one property all of them listen to
  const CHAT_MAX = 200;
  const CHAT_KEPT = 50;
  const SLEW_MS = 170;

  /**
   * A setTimeout that a browser does not slow when the page is behind another window. A page's own timers are cut to one a second after it has been hidden for ten, and to one a minute after five
   * minutes (Chrome, Brave, Edge; a window another one covers counts as hidden), and the aircraft counts the silence of the station's heartbeat in its own seconds: with FlightGear's speed-up on, a
   * few real seconds of silence are the link's 30 s and it flies its lost-link route home (2026-11-17: "I don't know why it loses the link so easily"). A dedicated worker's timers are not slowed.
   * Made from a Blob so that it works from a page opened as a file; null where there are no workers, and the plain setTimeout is used.
   */
  function backgroundTimer() {
    try {
      if (typeof Worker === 'undefined' || typeof Blob === 'undefined' || typeof URL === 'undefined' || !URL.createObjectURL) return null;
      const w = new Worker(URL.createObjectURL(new Blob(['onmessage=function(e){var id=e.data[0];setTimeout(function(){postMessage(id)},e.data[1])}'], { type: 'text/javascript' })));
      const pending = new Map();
      let n = 0;
      let broken = false;
      w.onmessage = (e) => {
        const f = pending.get(e.data);
        pending.delete(e.data);
        if (f) f();
      };
      w.onerror = () => {
        broken = true; // the worker died: what it held is run by the page's own timer, late rather than never
        for (const f of pending.values()) setTimeout(f, 0);
        pending.clear();
      };
      return (fn, ms) => {
        if (broken) return setTimeout(fn, ms);
        n += 1;
        pending.set(n, fn);
        w.postMessage([n, ms]);
      };
    } catch (e) {
      return null;
    }
  }

  class Link {
    constructor(o) {
      this.t = o.transport;
      this.station = o.station || 'LRE';
      this.latency = o.latency || 0;
      this.now = o.now || (() => Date.now());
      this.timer = o.setTimeout || backgroundTimer() || ((fn, ms) => setTimeout(fn, ms));
      this.lastTick = null; // when the heartbeat last went, and the late ones: { at, gapMs }, the last ten
      this.stalls = [];
      this.seq = o.firstSeq !== undefined ? o.firstSeq : Math.floor(this.now() / 1000) % 1000000000; // never reused after a reload
      this.beat = Math.floor(this.now() / 1000) % 1000000;
      this.commands = []; // newest last: { seq, name, args, state, reason, sentAt, answeredAt }
      this.values = {};
      this.listeners = [];
      this.state = { mode: 'idle' };
      this.beating = false;
      this.beatMs = BEAT_MS;
      this.lastDown = null; // when anything last came down
      this.messages = []; // newest last: { station, n, text, t (ms, the sender's clock), mine }
      this.chatN = Math.floor(this.now() / 1000) % 1000000000; // never reused after a reload
      // a message between crews is not a command and not telemetry: the link's delay is not put on it (the crews talk by voice in the real thing)
      this.t.onValue = (path, value) => (path === CHAT ? this.receiveChat(value) : this.later(() => this.receive(path, value)));
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
      this.t.listen(['/gcs/down/ack', '/gcs/down/status', '/gcs/down/plan', '/gcs/down/airport', CHAT].concat(paths || []));
      this.beating = true;
      try {
        // a page that holds a lock is not frozen by the browser when it is in the background
        if (typeof navigator !== 'undefined' && navigator.locks && navigator.locks.request) navigator.locks.request('gcs-link', () => new Promise(() => {})).catch(() => {});
      } catch (e) {
        /* no locks here */
      }
      const tick = () => {
        if (!this.beating) return;
        const t = this.now();
        if (this.lastTick !== null && t - this.lastTick > 3000 + 2 * this.beatMs) {
          this.stalls.push({ at: t, gapMs: t - this.lastTick });
          if (this.stalls.length > 10) this.stalls.shift();
        }
        this.lastTick = t;
        this.beat += 1;
        const b = `${this.station}:${this.beat}`;
        this.later(() => this.t.send('/gcs/up/heartbeat', b));
        this.expire();
        this.timer(tick, this.beatMs);
      };
      tick();
    }

    /**
     * How often to beat, in real milliseconds. The aircraft counts the silence in its own seconds, so when the simulation runs `k` times as fast as the clock the
     * station has to beat `k` times as often, or the aircraft sees a gap of `k` seconds between beats and says it has not heard the station: the page does that at
     * `?speed=` in the demo and when FlightGear's speed-up is on. Between 100 ms and the usual second.
     */
    setBeatMs(ms) {
      this.beatMs = Math.max(100, Math.min(BEAT_MS, Math.round(ms)));
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
      this.timer(() => this.expire(), this.waitMs(c) + 50);
      this.emit('command', c);
      return c;
    }

    /** How long a command may go unanswered, ms. */
    waitMs(c) {
      return (ANSWER_LONG[c.name] || ANSWER_MS) + 2 * this.latency;
    }

    /** Say something to the other stations. Returns the message, or null if it is empty or over 200 characters. */
    say(text) {
      text = String(text === undefined || text === null ? '' : text).trim();
      if (!text || text.length > CHAT_MAX) return null;
      this.chatN += 1;
      const m = { station: this.station, n: this.chatN, text, t: this.now() };
      this.keep(Object.assign({ mine: true }, m));
      this.t.send(CHAT, JSON.stringify(m)); // straight away: not through the delay
      return m;
    }

    receiveChat(value) {
      let m;
      try {
        m = value ? JSON.parse(value) : null;
      } catch (e) {
        return;
      }
      if (!m || typeof m.station !== 'string' || !Number.isFinite(m.n) || typeof m.text !== 'string' || m.text.length > CHAT_MAX) return;
      if (this.messages.some((x) => x.station === m.station && x.n === m.n)) return; // our own, coming back, or heard twice
      this.keep({ station: m.station, n: m.n, text: m.text, t: m.t, mine: false });
    }

    keep(m) {
      m.at = this.now(); // when it reached this station: the senders' clocks may differ
      this.messages.push(m);
      if (this.messages.length > CHAT_KEPT) this.messages.shift();
      this.emit('message', m);
    }

    /** How long the aircraft takes to answer a command, ms: the median of the last five that were answered. Null if none yet. */
    answerMs() {
      const d = this.commands.filter((c) => c.answeredAt !== null && c.state !== 'no answer').slice(-5).map((c) => c.answeredAt - c.sentAt).sort((a, b) => a - b);
      return d.length ? d[Math.floor(d.length / 2)] : null;
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
        if (c.state === 'sent' && t - c.sentAt >= this.waitMs(c)) {
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
      } else if (path === '/gcs/down/airport') {
        let j = null;
        try {
          j = value ? JSON.parse(value) : null;
        } catch (e) {
          return;
        }
        this.airport = j && typeof j.icao === 'string' && Array.isArray(j.parking) && Array.isArray(j.nodes) && Array.isArray(j.arcs) ? j : null;
        this.emit('airport', this.airport);
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

  const api = { Link, WsTransport, ANSWER_MS, BEAT_MS, CHAT, CHAT_MAX };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else Object.assign((root.GCS = root.GCS || {}), api);
})(typeof window !== 'undefined' ? window : globalThis);
