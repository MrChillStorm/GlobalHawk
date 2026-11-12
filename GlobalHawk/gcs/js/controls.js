/**
 * Hand controls for flying the aircraft from the station: a gamepad or the keyboard, turned into the stick message
 * { p, r, y, t, s }: pitch (forward positive), roll (right positive), pedals (nose right positive), each -1..1;
 * throttle and spoilers 0..1. Pure functions, so they can be tested; the page reads the devices.
 */
(function (root) {
  'use strict';
  const DEAD = 0.08; // a gamepad stick never rests exactly at zero
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  const dead = (x) => (Math.abs(x) < DEAD ? 0 : (Math.sign(x) * (Math.abs(x) - DEAD)) / (1 - DEAD));

  /**
   * A standard-mapping gamepad: left stick roll (axis 0) and pitch (axis 1: pulled back reads positive on a
   * gamepad, and here that is nose up, so the sign is turned), right stick X (axis 2) pedals. The right trigger (button 7) raises the
   * throttle and the left (button 6) lowers it, at up to 0.5 a second; the bumpers (5, 4) move the spoilers.
   * `prev` is the last result (for throttle and spoilers, which are levers: they stay where they are put).
   */
  function fromGamepad(axes, buttons, prev, dt) {
    const b = (i) => (buttons && buttons[i] ? (typeof buttons[i] === 'number' ? buttons[i] : buttons[i].value || 0) : 0);
    return {
      p: -clamp(dead(axes[1] || 0), -1, 1) || 0,
      r: clamp(dead(axes[0] || 0), -1, 1),
      y: clamp(dead(axes[2] || 0), -1, 1),
      t: clamp(prev.t + 0.5 * dt * (b(7) - b(6)), 0, 1),
      s: clamp(prev.s + 0.5 * dt * (b(5) - b(4)), 0, 1),
    };
  }

  /**
   * The keyboard: arrows for the stick (up = stick forward = nose down, as on a flight simulator), Q/E pedals,
   * W/S throttle, X/Z spoilers out and in. Keys are on or off, so the stick moves towards its end at 2.5 a second
   * and springs back at 4 a second when let go. `down` is a Set of key names.
   */
  function fromKeys(down, prev, dt) {
    const axis = (now, neg, pos) => {
      const want = (down.has(pos) ? 1 : 0) - (down.has(neg) ? 1 : 0);
      const rate = want === 0 ? 4 : 2.5;
      return want === 0 ? (Math.abs(now) <= rate * dt ? 0 : now - Math.sign(now) * rate * dt) : clamp(now + want * rate * dt, -1, 1);
    };
    return {
      p: axis(prev.p, 'ArrowDown', 'ArrowUp'),
      r: axis(prev.r, 'ArrowLeft', 'ArrowRight'),
      y: axis(prev.y, 'q', 'e'),
      t: clamp(prev.t + 0.4 * dt * ((down.has('w') ? 1 : 0) - (down.has('s') ? 1 : 0)), 0, 1),
      s: clamp(prev.s + 0.4 * dt * ((down.has('x') ? 1 : 0) - (down.has('z') ? 1 : 0)), 0, 1),
    };
  }

  const api = { fromGamepad, fromKeys, DEAD };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).controls = api;
})(typeof window !== 'undefined' ? window : globalThis);
