/**
 * The map's layers: which are shown, and why.
 *
 * Every optional layer has a mode: Off, Auto or On. On and Off are the user's and beat Auto. Auto asks the layer's own
 * rule (a function of the situation, see js/overlayctx.js) and shows the layer while the rule holds, with the reason
 * in words. The rules that follow come from the station's human-factors notes (NASA, remote pilot stations): an
 * automatic display "should not create unacceptable clutter", so
 *
 *   - a rule must hold for ON_AFTER_MS before the layer comes up and be false for OFF_AFTER_MS before it goes
 *     (limits chosen here: none is published), so a flickering condition does not flicker the map;
 *   - at most MAX_AUTO layers come up by themselves at once on top of the station's own picture (an assumed number), the most
 *     safety-relevant first; the others wait, and the panel says so. The layers that were always there (def.budget === false) are not counted;
 *   - a layer the user has put away with its chip's cross stays away until its reason has been false for
 *     DISMISS_CLEAR_MS and has come back;
 *   - a layer whose rule says `force` is shown even when Off or decluttered, at once, while the cause lasts (and
 *     OFF_AFTER_MS after it): the link's edge, a traffic alert, an engine out. Forced layers cannot be dismissed;
 *   - declutter puts every optional layer away and a second call brings the same modes back.
 *
 * Nothing here moves the map, takes focus or opens a window, and nothing here sends a command.
 */
(function (root) {
  'use strict';
  const ON_AFTER_MS = 2000;
  const OFF_AFTER_MS = 60000;
  const DISMISS_CLEAR_MS = 10000;
  const MAX_AUTO = 3;
  const MODES = ['off', 'auto', 'on'];
  const GROUPS = ['Map', 'Safety', 'Weather', 'Ground', 'Mission'];

  class Layers {
    /** opts: { now: () => ms, storage: { getItem, setItem } | null, key: string } */
    constructor(opts) {
      opts = opts || {};
      this.now = opts.now || (() => Date.now());
      this.storage = opts.storage || null;
      this.key = opts.key || 'gcs.layers';
      this.defs = [];
      this.modes = {};
      this.track = {}; // per layer: { since, clearSince, up, dismissed, fClear, forcedUp, reason }
      this.declutter = false;
      this.out = {};
    }

    /**
     * Add a layer. def: { id, group, label, tip, rank (lower is more safety-relevant), mode ('auto' default),
     * auto: (ctx) => { on, reason, force } | null }. Layers are listed in the order they are defined.
     */
    define(def) {
      if (this.defs.some((d) => d.id === def.id)) throw new Error('layer defined twice: ' + def.id);
      this.defs.push(Object.assign({ rank: 50, mode: 'auto', group: 'Mission', label: def.id, tip: '', auto: null }, def));
      this.modes[def.id] = MODES.includes(def.mode) ? def.mode : 'auto';
      this.track[def.id] = { since: null, clearSince: null, up: false, dismissed: false, fClear: null, forcedUp: false, reason: '' };
    }

    def(id) {
      return this.defs.find((d) => d.id === id) || null;
    }

    mode(id) {
      return this.modes[id];
    }

    setMode(id, mode) {
      if (!this.modes.hasOwnProperty(id) || !MODES.includes(mode)) return false;
      this.modes[id] = mode;
      this.track[id].dismissed = false;
      this.save();
      return true;
    }

    setDeclutter(on) {
      this.declutter = !!on;
    }

    /** The user's cross on a chip: away until the reason has gone and come back. Forced layers refuse. */
    dismiss(id) {
      const t = this.track[id];
      if (!t || t.forcedUp) return false;
      t.dismissed = true;
      return true;
    }

    /** Take the situation and work out every layer's state. Call it often (every few hundred ms). */
    update(ctx) {
      const now = this.now();
      const wantAuto = [];
      for (const d of this.defs) {
        const t = this.track[d.id];
        let r = null;
        if (d.auto) {
          try {
            r = d.auto(ctx) || null;
          } catch (e) {
            r = null; // a rule that fails shows nothing: it must not take the page with it
          }
        }
        const trig = !!(r && r.on);
        const force = trig && !!r.force;
        t.reason = r && r.reason ? r.reason : '';
        // the ordinary latch: up after ON_AFTER_MS of the rule holding, down after OFF_AFTER_MS of it not
        if (trig) {
          t.clearSince = null;
          if (t.since === null) t.since = now;
          if (!t.up && now - t.since >= ON_AFTER_MS) t.up = true;
        } else {
          t.since = null;
          if (t.clearSince === null) t.clearSince = now;
          if (t.up && now - t.clearSince >= OFF_AFTER_MS) t.up = false;
          if (t.dismissed && now - t.clearSince >= DISMISS_CLEAR_MS) {
            t.dismissed = false;
            t.up = false; // the layer must earn its place again: it may not come back with a reason that has gone
          }
        }
        // the forced latch: up at once, down after OFF_AFTER_MS
        if (force) {
          t.fClear = null;
          t.forcedUp = true;
        } else {
          if (t.fClear === null) t.fClear = now;
          if (t.forcedUp && now - t.fClear >= OFF_AFTER_MS) t.forcedUp = false;
        }
        if (t.forcedUp) t.dismissed = false;
        if (this.modes[d.id] === 'auto' && t.up && !t.dismissed && !t.forcedUp) wantAuto.push(d);
      }
      // the budget of layers that may come up by themselves: it limits what is added on top of the station's own picture, so the
      // layers that were always there (budget: false: traffic, the glide ring, the camera's cross) do not use it up
      wantAuto.sort((a, b) => a.rank - b.rank || this.track[a.id].since - this.track[b.id].since);
      const counted = wantAuto.filter((d) => d.budget !== false);
      const free = wantAuto.filter((d) => d.budget === false);
      const allowed = new Set(this.declutter ? [] : free.concat(counted.slice(0, MAX_AUTO)).map((d) => d.id));
      const waiting = new Set(this.declutter ? [] : counted.slice(MAX_AUTO).map((d) => d.id));
      const out = {};
      for (const d of this.defs) {
        const t = this.track[d.id];
        const mode = this.modes[d.id];
        let shown = false;
        let source = 'off';
        if (t.forcedUp) {
          shown = true;
          source = 'forced';
        } else if (this.declutter && mode !== 'off') {
          source = 'declutter';
        } else if (mode === 'on') {
          shown = true;
          source = 'on';
        } else if (mode === 'auto') {
          if (allowed.has(d.id)) {
            shown = true;
            source = 'auto';
          } else if (waiting.has(d.id)) source = 'waiting';
          else if (t.dismissed && t.up) source = 'dismissed';
          else source = 'idle';
        }
        out[d.id] = { id: d.id, mode, shown, source, reason: t.reason, forced: source === 'forced' };
      }
      this.out = out;
      return out;
    }

    state(id) {
      return this.out[id] || { id, mode: this.modes[id], shown: false, source: 'off', reason: '', forced: false };
    }

    shown(id) {
      return !!(this.out[id] && this.out[id].shown);
    }

    /** The layers that are up because of a rule, not because the user asked: what the chips under the toolbar say. */
    chips() {
      return this.defs.filter((d) => this.out[d.id] && (this.out[d.id].source === 'auto' || this.out[d.id].source === 'forced')).map((d) => ({ id: d.id, label: d.label, reason: this.out[d.id].reason, forced: this.out[d.id].forced }));
    }

    /** The layers whose rule holds but that wait for a place (the budget). */
    waiting() {
      return this.defs.filter((d) => this.out[d.id] && this.out[d.id].source === 'waiting').map((d) => d.id);
    }

    /* ----------------------------------------------------------- keeping the choices */
    save(extra) {
      if (!this.storage) return;
      try {
        const old = this.load(true) || {};
        this.storage.setItem(this.key, JSON.stringify(Object.assign({}, old, { modes: this.modes }, extra || {})));
      } catch (e) {
        /* private windows and file pages may refuse: the choices then last until the page closes */
      }
    }

    /** The saved record, or null. With `raw` nothing is applied. Otherwise the saved modes are applied (unknown ids and modes are ignored). */
    load(raw) {
      if (!this.storage) return null;
      try {
        const s = JSON.parse(this.storage.getItem(this.key) || 'null');
        if (!s || typeof s !== 'object') return null;
        if (!raw && s.modes) for (const id of Object.keys(s.modes)) if (this.modes.hasOwnProperty(id) && MODES.includes(s.modes[id])) this.modes[id] = s.modes[id];
        return s;
      } catch (e) {
        return null;
      }
    }

    /** "airspace:on,wx-radar:off" (the page's ?layers=) into modes. Returns what it applied. */
    applyQuery(text) {
      const done = {};
      for (const part of String(text || '').split(',')) {
        const [id, mode] = part.split(':').map((s) => s.trim());
        if (id && this.modes.hasOwnProperty(id) && MODES.includes(mode)) {
          this.modes[id] = mode;
          done[id] = mode;
        }
      }
      return done;
    }
  }

  const api = { Layers, ON_AFTER_MS, OFF_AFTER_MS, DISMISS_CLEAR_MS, MAX_AUTO, MODES, GROUPS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).layers = api;
})(typeof window !== 'undefined' ? window : globalThis);
