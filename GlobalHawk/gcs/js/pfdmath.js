/**
 * The numbers behind the flight display, apart from the drawing so that they can be tested.
 */
(function (root) {
  'use strict';
  const ZERO_LIFT_DEG = -4.5; // lift taken as linear in angle of attack from here (the ATTREX fit: lift at zero angle over its slope)
  const MACH_LIMIT = 0.63; // where the laws begin to pull the nose up
  const KCAS_LIMIT = 175;
  const TREND_S = 10;

  /**
   * The speeds the aircraft can fly at here, as calibrated airspeed: the low one where the angle of attack would be
   * at its limit in level flight, the high one the lower of the Mach and the speed limits. An approximation.
   */
  function speedLimits(kcas, alphaDeg, alphaLimitDeg, mach) {
    const lift = Math.max(alphaDeg - ZERO_LIFT_DEG, 0.5);
    const most = Math.max(alphaLimitDeg - ZERO_LIFT_DEG, 0.5);
    const low = kcas * Math.sqrt(lift / most);
    const high = Math.min(KCAS_LIMIT, mach > 0.05 ? (kcas * MACH_LIMIT) / mach : KCAS_LIMIT);
    return { low, high };
  }

  /** Where a value will be in 10 s at its present rate (per second). */
  const trend = (value, ratePerSec) => value + TREND_S * ratePerSec;

  /** Calibrated airspeed's rate from the true airspeed's: the same fraction per second. */
  const kcasRate = (kcas, vtFps, udotFps2) => (vtFps > 50 ? (kcas * udotFps2) / vtFps : 0);

  /** Smallest signed difference between two headings, deg. */
  const wrap = (d) => ((((d + 180) % 360) + 360) % 360) - 180;

  /** Pixels down from the horizon line for a pitch angle, at pxPerDeg. */
  const pitchY = (deg, pxPerDeg) => -deg * pxPerDeg;

  const api = { speedLimits, trend, kcasRate, wrap, pitchY, ZERO_LIFT_DEG, MACH_LIMIT, KCAS_LIMIT, TREND_S };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).pfdmath = api;
})(typeof window !== 'undefined' ? window : globalThis);
