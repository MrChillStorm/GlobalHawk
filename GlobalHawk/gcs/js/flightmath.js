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
  /** The speed the laws hold in cruise at a pressure height, KCAS: 150 low down, above FL220 the scheduled Mach (fdm/laws.py SCHEDULE) as calibrated airspeed. */
  function scheduleKcas(altFt) {
    const A = cap.approach;
    const knee = A.schedule_mach[1][0];
    if (altFt < knee) return A.schedule_kcas;
    const m = pairs(A.schedule_mach, altFt);
    const p = Math.pow(1 - 6.87559e-6 * altFt, 5.25588); // pressure over the sea level's, ISA
    const qc = p * (Math.pow(1 + 0.2 * m * m, 3.5) - 1);
    return 661.47 * Math.sqrt(5 * (Math.pow(qc + 1, 2 / 7) - 1));
  }

  /**
   * The bank the aircraft flies over the bank it is commanded in a turn, at a weight, a pressure height and a calibrated airspeed: the turn performance table
   * (fdm/turnperf.py, in the capability file; the same one the laws read), trilinear and held at its ends; 1 when the file has none.
   */
  function turnTable(grid, weightLb, altFt, kcas) {
    const P = cap.turn.performance;
    const at = (xs, x) => {
      if (x <= xs[0]) return [0, 0];
      if (x >= xs[xs.length - 1]) return [xs.length - 2, 1];
      let i = 0;
      while (xs[i + 1] < x) i++;
      return [i, (x - xs[i]) / (xs[i + 1] - xs[i])];
    };
    const [ik, fk] = at(P.axes.speed_kcas, kcas);
    const [iw, fw] = at(P.axes.weight_lb, weightLb);
    const [ih, fh] = at(P.axes.pressure_alt_ft, altFt);
    let v = 0;
    for (let a = 0; a < 2; a++) for (let b = 0; b < 2; b++) for (let c = 0; c < 2; c++) {
      v += (a ? fk : 1 - fk) * (b ? fw : 1 - fw) * (c ? fh : 1 - fh) * grid[ik + a][iw + b][ih + c];
    }
    return v;
  }
  function bankRatio(weightLb, altFt, kcas) {
    const P = cap.turn.performance;
    return P ? 1 + turnTable(P.flown_per_cmd, weightLb, altFt, kcas) : 1;
  }
  /** The bank's effective delay rolling into a turn at a weight, a pressure height and a calibrated airspeed, s (turnperf.py: the area between the steady bank and its response, less the command's ramp); the delay of rolltest.py when the file has none. */
  function turnLagInS(weightLb, altFt, kcas) {
    const P = cap.turn.performance;
    return P && P.lag_in_s ? turnTable(P.lag_in_s, weightLb, altFt, kcas) : rollLagS(kcas);
  }
  const DEFAULT_WEIGHT_LB = 20000; // when the caller has no weight

  /**
   * The steady crosswind the landing holds its contracts in at a weight, kt (fdm/landlimit.py, in the capability file: found by flying the final and the landing in steadily
   * stronger wind until a contract broke; linear between the weights it flew and held at its ends); null when the file has none.
   */
  function crosswindLimitKt(weightLb) {
    const L = cap.landing && cap.landing.crosswind;
    if (!L) return null;
    const ok = L.limit_kt.every((v) => v !== null && v !== undefined);
    return ok ? lerp(L.weight_lb, L.limit_kt, weightLb) : null;
  }

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
    const kcas = Number.isFinite(o.kcas) ? o.kcas : scheduleKcas(o.alt_ft);
    // flown at the bank the table says the aircraft flies for the bank commanded, as the laws work it out (ap/turn-bank-flown-deg)
    const flown = bank * bankRatio(Number.isFinite(o.weight_lb) ? o.weight_lb : DEFAULT_WEIGHT_LB, o.alt_ft, kcas);
    const radius = (vg * vg) / (cap.turn.g_fps2 * Math.tan(flown * RAD));
    const weight = Number.isFinite(o.weight_lb) ? o.weight_lb : DEFAULT_WEIGHT_LB;
    const roll = (0.5 * bank) / cap.turn.bank_rate_dps + turnLagInS(weight, o.alt_ft, kcas);
    const d = Math.min(Math.abs(o.delta_deg), cap.turn.fly_by_max_deg);
    // the roll out's sideways drift (the response's moment, fdm/turnperf.py): g tan(bank) times it to the outside at the exit, over sin(the corner) in the lead; none under the first
    // corner of the fade and all over the second (the roll in and the roll out overlap in a small turn), and none where the lead is the old one (under the wind's least corner, or a fly-over)
    const P = cap.turn.performance;
    let drift = 0;
    if (P && P.moment_out_s2 && Math.abs(o.delta_deg) > cap.turn.wind_min_deg && Math.abs(o.delta_deg) < cap.turn.fly_by_max_deg) {
      const [f0, f1] = cap.turn.drift_fade_deg;
      const fade = Math.max(0, Math.min(1, (Math.abs(o.delta_deg) - f0) / (f1 - f0)));
      drift = (cap.turn.g_fps2 * Math.tan(flown * RAD) * turnTable(P.moment_out_s2, weight, o.alt_ft, kcas) * fade) / Math.sin(Math.abs(o.delta_deg) * RAD);
    }
    const lead = radius * Math.tan((0.5 * d) * RAD) + vg * roll + drift;
    // flown over (past the limit) the aircraft ends about two radii off the new line
    const over = Math.abs(o.delta_deg) > cap.turn.fly_by_max_deg;
    return { bank_deg: bank, bank_flown_deg: flown, radius_ft: radius, lead_ft: lead, rate_dps: ((cap.turn.g_fps2 * Math.tan(flown * RAD)) / vg) / RAD, over, off_ft: over ? 2 * radius : 0 };
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

  /**
   * The turn onto the first leg after takeoff, as the aircraft flies it (fdm/departure.py, in the capability file): the manager starts the first leg where
   * the aircraft lifts off and has no leg before it, so the corner between the runway's heading and that leg has none of the lead and arc the turns between
   * legs have; the aircraft sweeps off the line before it is back on it. By the corner's size in degrees: how far off the line it goes (ft) and how far from
   * the takeoff's end it is back within 150 ft of it (nmi). null when the file has no table.
   */
  const DEPART_OFF_LIMIT_FT = 700; // how far off the first leg's line the aircraft may go after takeoff, in the planner's plans; mine
  const departureRows = () => (cap.flown.departure && cap.flown.departure.rows) || null;
  function departureOffFt(deltaDeg) {
    const r = departureRows();
    return r ? lerp(r.map((x) => x.delta_deg), r.map((x) => x.off_ft), Math.abs(deltaDeg)) : null;
  }
  function departureBackNm(deltaDeg) {
    const r = departureRows();
    return r ? lerp(r.map((x) => x.delta_deg), r.map((x) => x.back_nm), Math.abs(deltaDeg)) : null;
  }
  /** The largest first corner the aircraft flies within the planner's limit off the line (deg), or null with no table. */
  function departureMaxDeg(limitFt) {
    const r = departureRows();
    if (!r) return null;
    const lim = limitFt === undefined ? DEPART_OFF_LIMIT_FT : limitFt;
    if (r[0].off_ft > lim) return 0;
    for (let i = 1; i < r.length; i++) {
      if (r[i].off_ft > lim) return r[i - 1].delta_deg + ((r[i].delta_deg - r[i - 1].delta_deg) * (lim - r[i - 1].off_ft)) / (r[i].off_ft - r[i - 1].off_ft);
    }
    return r[r.length - 1].delta_deg;
  }

  const api = { lerp, bankLimitDeg, rollLagS, alphaLimitDeg, scheduleKcas, bankRatio, turnLagInS, crosswindLimitKt, turn, approachKcas, pathHeightFt, slowing, finalBankDeg, descentFpm, captureGapFt, finalFixHeightAgl, departureOffFt, departureBackNm, departureMaxDeg, DEPART_OFF_LIMIT_FT, KT, cap };
  if (node) module.exports = api;
  else (root.GCS = root.GCS || {}).flightmath = api;
})(typeof window !== 'undefined' ? window : globalThis);
