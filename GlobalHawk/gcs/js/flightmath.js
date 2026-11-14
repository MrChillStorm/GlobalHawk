/**
 * The aircraft's turns and approach as the planner needs them, from the capability file (js/capability.js, written by
 * fdm/capability.py from the aircraft's own laws and from flying them): the bank it uses, the radius and the lead of a turn, the
 * approach speed, the glide path, how far it takes to slow down. The same formulas as the laws' (fdm/laws.py: ap/turn-*), so that
 * the planner never plans a turn the aircraft will fly differently. Pure: node can test it.
 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const cap = node ? require('./capability.js') : root.GCS.capability;
  const KT = 1.6878099; // ft/s per knot
  const RAD = Math.PI / 180;

  /** Linear lookup of ys at x over the ascending xs, held at the ends. */
  function lerp(xs, ys, x) {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[xs.length - 1]) return ys[ys.length - 1];
    let i = 0;
    while (xs[i + 1] < x) i++;
    return ys[i] + ((ys[i + 1] - ys[i]) * (x - xs[i])) / (xs[i + 1] - xs[i]);
  }
  const pairs = (pts, x) => lerp(pts.map((p) => p[0]), pts.map((p) => p[1]), x);

  /** The bank the laws command at most at a pressure height, deg (their bank limit times the command fraction). */
  const bankLimitDeg = (altFt) => pairs(cap.turn.bank_limit, altFt) * cap.turn.bank_command;
  /** The bank's delay behind its target at a calibrated speed, s (measured by fdm/rolltest.py). */
  const rollLagS = (kcas) => lerp(cap.turn.roll_delay.kcas, cap.turn.roll_delay.delay_s, kcas);
  /** The angle-of-attack limit at a Mach number, deg. */
  const alphaLimitDeg = (mach) => pairs(cap.turn.alpha_limit, mach);

  /**
   * A turn of delta deg at a ground speed (ft/s) and a calibrated speed, with a bank (default: the limit at that height).
   * radius_ft: ground speed squared over g tan(bank); lead_ft: where it starts before the corner (the arc joins the two legs, less
   * half the roll in and the bank's delay), and also how far past the corner the aircraft is back on the new line; a corner past the
   * fly-by limit is led as one at the limit (the aircraft flies it over the point). rate_dps: the track's turn rate.
   */
  function turn(o) {
    const bank = Number.isFinite(o.bank_deg) ? o.bank_deg : bankLimitDeg(o.alt_ft);
    const vg = Math.max(o.vg_fps, 60);
    const radius = (vg * vg) / (cap.turn.g_fps2 * Math.tan(bank * RAD));
    const roll = (0.5 * bank) / cap.turn.bank_rate_dps + rollLagS(o.kcas);
    const d = Math.min(Math.abs(o.delta_deg), cap.turn.fly_by_max_deg);
    const lead = radius * Math.tan((0.5 * d) * RAD) + vg * roll;
    // flown over (past the limit) the aircraft ends about two radii off the new line
    const over = Math.abs(o.delta_deg) > cap.turn.fly_by_max_deg;
    return { bank_deg: bank, radius_ft: radius, lead_ft: lead, rate_dps: ((cap.turn.g_fps2 * Math.tan(bank * RAD)) / vg) / RAD, over, off_ft: over ? 2 * radius : 0 };
  }

  /** The approach speed at a weight, KCAS: the speed for the approach lift coefficient. */
  const approachKcas = (weight) => Math.sqrt(weight / (cap.approach.cl * cap.approach.wing_area_ft2 * 0.5 * 0.0023769)) / KT;
  /** The height of the glide path over the ground at a distance from the aiming point, ft. */
  const pathHeightFt = (distFt) => cap.approach.aim_height_ft + cap.approach.glide_tan * Math.max(0, distFt);

  /** What flying the slowing down in the landing configuration from the schedule's speed took, at a weight: { slow_s, slow_ft, alpha_level, approach_kcas }. */
  function slowing(weight) {
    const S = cap.flown.slowing;
    const w = S.map((s) => s.weight_lb);
    const get = (k) => {
      const ys = S.map((s) => s[k]);
      return ys.every((v) => v !== null && v !== undefined) ? lerp(w, ys, weight) : null;
    };
    return { slow_s: get('slow_s'), slow_ft: get('slow_ft'), alpha_level: get('alpha_level'), approach_kcas: approachKcas(weight) };
  }


  /**
   * How far under the glide path the aircraft must be at the fix for the manager to take the path over cleanly, ft: what
   * fdm/capability.py flew (the landing item begun level at the fix, 10 nmi out, at heights down from 4,600 ft over the ground; the capture clean
   * at that height and at every lower one tried), plus the planner's margin. The aircraft dives when the gear and spoilers go on and the altitude
   * hold climbs it back: the path has to come down to it after that has settled.
   */
  const GAP_MARGIN_FT = 150; // mine
  function captureGapFt() {
    // not smooth in weight (at 15,000 lb a crossing from 3,600 down to 2,600 ft over the ground, none at 12,000 or 19,000: the phase the aircraft's
    // oscillation is in when the path comes down to it): the planner takes the worst of the weights flown
    const ys = cap.flown.slowing.map((s) => s.capture_gap_ft);
    return ys.some((v) => v === null || v === undefined) ? 0 : Math.max(...ys) + GAP_MARGIN_FT;
  }
  /** The height over the ground to be at over the landing fix, ft: the glide path's height where the aircraft is back on the final (distFt from the aiming point, less afterFt: the way a turn at the fix takes before the aircraft is back on the line) less the gap; to 100 ft, not under 1,000. */
  const FIX_CORNER_FT = 2000; // the way a corner at the fix of up to 20 deg takes (R tan(10 deg) and the roll in), counted when the corner is not known; mine
  function finalFixHeightAgl(distFt, weight, afterFt) {
    return Math.max(1000, Math.floor((pathHeightFt(distFt - (afterFt === undefined ? FIX_CORNER_FT : afterFt)) - captureGapFt()) / 100) * 100);
  }

  /**
   * The bank the angle-of-attack margin allows on the final, in the landing configuration at the approach speed and a weight: the
   * laws' own: acos(1 / n), n the load factor at which the angle reaches its limit less the margin, the lift's slope taken from the
   * angle above the zero-lift angle. Never under the laws' least bank nor over their limit.
   */
  function finalBankDeg(weight) {
    const s = slowing(weight);
    const mach = (s.approach_kcas * KT) / 1116;
    if (s.alpha_level === null) return bankLimitDeg(0);
    const slope = Math.max(0.5, s.alpha_level - cap.turn.alpha_zero_lift_deg);
    const n = 1 + (alphaLimitDeg(mach) - cap.turn.alpha_margin_deg - s.alpha_level) / slope;
    const bank = Math.acos(1 / Math.max(1.0001, n)) / RAD;
    return Math.min(bankLimitDeg(0), Math.max(cap.turn.min_bank_deg, bank));
  }

  /** The descent the aircraft flies (ft/min, negative) from a height at a weight, as the manager flies it. */
  function descentFpm(altFt, weight) {
    const F = cap.flown;
    const rows = F.alt_ft.map((_, i) => lerp(F.weight_lb, F.descent_fpm[i], weight));
    return lerp(F.alt_ft, rows, altFt);
  }

  const api = { lerp, bankLimitDeg, rollLagS, alphaLimitDeg, turn, approachKcas, pathHeightFt, slowing, finalBankDeg, descentFpm, captureGapFt, finalFixHeightAgl, KT, cap };
  if (node) module.exports = api;
  else (root.GCS = root.GCS || {}).flightmath = api;
})(typeof window !== 'undefined' ? window : globalThis);
