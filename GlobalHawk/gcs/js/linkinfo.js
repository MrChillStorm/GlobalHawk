/*
 * What the station tells the operator about the link, apart from the alert list: the aircraft's count towards its
 * lost-link route, the message after a lost link comes back, and the warning before the page is closed in flight.
 * Plain functions of the aircraft's status and of the station's own state, so that they are tested without a browser.
 */
(function (root) {
  'use strict';
  const COUNTDOWN_FROM_S = 3;   // the aircraft has not heard the station in control for this long: the count is shown
  const RESTORED_MS = 20000;    // how long "link restored" stands
  const TIMEOUT_MIN = 10;       // as the aircraft's (fdm/onboard.py): what a time-out may be set to
  const TIMEOUT_MAX = 300;

  /** The silence the aircraft is counting, or null: { age, left, timeout, holder } in seconds. */
  function countdown(status) {
    if (!status || status.link_lost || status.link_age === null || status.link_age === undefined || !(status.link_timeout > 0)) return null;
    if (status.link_age < COUNTDOWN_FROM_S) return null;
    return {
      age: status.link_age,
      left: Math.max(0, status.link_timeout - status.link_age),
      timeout: status.link_timeout,
      holder: status.control && status.control.holder ? status.control.holder : null,
    };
  }

  /** The count in words, for the strip. `station`: this station's name. */
  function countdownText(c, station) {
    if (!c) return '';
    const who = !c.holder || c.holder === station ? 'this station' : c.holder;
    return `the aircraft has not heard ${who} for ${Math.round(c.age)} s: route home in ${Math.ceil(c.left)} s`;
  }

  /** Whether the link has come back: update(sending, now) is true for 20 s after a station that had a link and lost it has one again. */
  class Restored {
    constructor() {
      this.ever = false;
      this.down = false;
      this.until = 0;
    }

    update(sending, now) {
      if (sending) {
        if (this.ever && this.down) this.until = now + RESTORED_MS;
        this.ever = true;
        this.down = false;
      } else if (this.ever) this.down = true;
      return now < this.until;
    }
  }

  /** The warning for closing the page: text if it would cut the link of a station in control of a flight, else null. */
  function closingWarning(status, station) {
    if (!status || !status.started || status.kind === 'done') return null;
    if (!status.control || status.control.holder !== station) return null;
    return `Closing this page cuts the link: ${status.link_timeout || 30} s later the aircraft leaves its plan and flies its lost-link route home.`;
  }

  /** The time-out as a number the aircraft will take, or null. */
  function validTimeout(sec) {
    return Number.isFinite(sec) && sec >= TIMEOUT_MIN && sec <= TIMEOUT_MAX ? sec : null;
  }

  const api = { countdown, countdownText, Restored, closingWarning, validTimeout, COUNTDOWN_FROM_S, RESTORED_MS, TIMEOUT_MIN, TIMEOUT_MAX };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).linkinfo = api;
})(typeof window !== 'undefined' ? window : globalThis);
