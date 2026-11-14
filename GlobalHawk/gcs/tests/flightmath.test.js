// node tests/flightmath.test.js : the planner's turn and approach maths, against hand-worked numbers and the capability file (P1, P3 of docs/PLAN.md, "The planner uses the aircraft's capability tables")
const assert = require('assert');
const FM = require('../js/flightmath.js');
const cap = require('../js/capability.js');
const near = (a, b, tol, what) => assert.ok(Math.abs(a - b) <= tol, `${what}: ${a} against ${b}`);
const RAD = Math.PI / 180;

// the bank the laws use: their bank limit (25 deg to 30,000 ft, 15 deg at 50,000) times the command fraction
near(FM.bankLimitDeg(4000), 25 * cap.turn.bank_command, 1e-9, 'bank at 4,000 ft');
near(FM.bankLimitDeg(50000), 15 * cap.turn.bank_command, 1e-9, 'bank at 50,000 ft');
near(FM.bankLimitDeg(40000), (25 + (15 - 25) * (40000 - 30000) / 20000) * cap.turn.bank_command, 1e-9, 'bank between');
// the turn performance table (fdm/turnperf.py): the bank flown over the bank commanded, at a table point exactly, trilinear between, held at the ends
{
  const P = cap.turn.performance;
  assert.ok(P, 'the capability file carries the turn performance table');
  P.axes.speed_kcas.forEach((k, i) => P.axes.weight_lb.forEach((w, j) => P.axes.pressure_alt_ft.forEach((h, l) => {
    near(FM.bankRatio(w, h, k), 1 + P.flown_per_cmd[i][j][l], 1e-12, `table point ${k} ${w} ${h}`);
  })));
  const [k0, k1] = P.axes.speed_kcas, [w0, w1] = P.axes.weight_lb, [h0, h1] = P.axes.pressure_alt_ft;
  near(FM.bankRatio((w0 + w1) / 2, h0, k0), 1 + (P.flown_per_cmd[0][0][0] + P.flown_per_cmd[0][1][0]) / 2, 1e-12, 'halfway in weight');
  near(FM.bankRatio(w0, (h0 + h1) / 2, k1), 1 + (P.flown_per_cmd[1][0][0] + P.flown_per_cmd[1][0][1]) / 2, 1e-12, 'halfway in height');
  near(FM.bankRatio(w0 - 5000, h0 - 1000, k0 - 50), FM.bankRatio(w0, h0, k0), 1e-12, 'held below');
  const last = (xs) => xs[xs.length - 1];
  near(FM.bankRatio(last(P.axes.weight_lb) + 9000, last(P.axes.pressure_alt_ft) + 9000, last(P.axes.speed_kcas) + 50), 1 + P.flown_per_cmd[P.axes.speed_kcas.length - 1][P.axes.weight_lb.length - 1][P.axes.pressure_alt_ft.length - 1], 1e-12, 'held above');
  // the flown bank is above the commanded one, most when slow, heavy and low
  assert.ok(FM.bankRatio(26000, 4174, 110) > FM.bankRatio(26000, 4174, 150) && FM.bankRatio(26000, 4174, 150) > FM.bankRatio(12000, 4174, 150) && FM.bankRatio(12000, 4174, 150) > FM.bankRatio(12000, 30174, 150));
  assert.ok(FM.bankRatio(12000, 4174, 150) > 1);
}
// the effective roll-in delay (fdm/turnperf.py, from the heading): at a table point exactly, longer than the delay table's, growing with speed and falling with height
{
  const P = cap.turn.performance;
  assert.ok(P.lag_in_s && P.lag_out_s, 'the capability file carries the delays');
  P.axes.speed_kcas.forEach((k, i) => P.axes.weight_lb.forEach((w, j) => P.axes.pressure_alt_ft.forEach((h, l) => {
    near(FM.turnLagInS(w, h, k), P.lag_in_s[i][j][l], 1e-12, `delay at table point ${k} ${w} ${h}`);
  })));
  assert.ok(FM.turnLagInS(20000, 4174, 150) > FM.rollLagS(150), 'the heading\'s delay is longer than the bank\'s');
  assert.ok(FM.turnLagInS(20000, 4174, 170) > FM.turnLagInS(20000, 4174, 130));
  assert.ok(FM.turnLagInS(20000, 4174, 150) > FM.turnLagInS(20000, 30174, 150));
}
// the speed the laws hold: 150 KCAS up to FL220, above it the scheduled Mach
near(FM.scheduleKcas(4000), 150, 1e-12, 'schedule low down');
assert.ok(FM.scheduleKcas(45000) > 120 && FM.scheduleKcas(45000) < 160, 'schedule at FL450: ' + FM.scheduleKcas(45000));
// a turn worked by hand: 90 deg at 250 ft/s and 150 KCAS, the bank at 4,000 ft, flown at the table's bank for 20,000 lb
{
  const bank = 25 * cap.turn.bank_command;
  const ratio = FM.bankRatio(20000, 4000, 150);
  const R = 250 * 250 / (32.174 * Math.tan(bank * ratio * RAD));
  const lag = FM.turnLagInS(20000, 4000, 150);        // the table's effective delay (the heading's), not the delay table's
  const t = FM.turn({ delta_deg: 90, alt_ft: 4000, vg_fps: 250, kcas: 150 });
  near(t.radius_ft, R, 1e-6, 'radius');
  near(t.bank_flown_deg, bank * ratio, 1e-9, 'bank flown');
  const mom = (w, h, k) => {      // the roll out's moment, from the table by hand
    const P = cap.turn.performance;
    const at = (xs, x) => { if (x <= xs[0]) return [0, 0]; if (x >= xs[xs.length - 1]) return [xs.length - 2, 1]; let i = 0; while (xs[i + 1] < x) i++; return [i, (x - xs[i]) / (xs[i + 1] - xs[i])]; };
    const [ik, fk] = at(P.axes.speed_kcas, k), [iw, fw] = at(P.axes.weight_lb, w), [ih, fh] = at(P.axes.pressure_alt_ft, h);
    let v = 0;
    for (let a = 0; a < 2; a++) for (let b = 0; b < 2; b++) for (let c = 0; c < 2; c++) v += (a ? fk : 1 - fk) * (b ? fw : 1 - fw) * (c ? fh : 1 - fh) * P.moment_out_s2[ik + a][iw + b][ih + c];
    return v;
  };
  const drift90 = 32.174 * Math.tan(bank * ratio * RAD) * mom(20000, 4000, 150);      // over sin 90 deg
  assert.ok(drift90 > 10, 'the roll out drifts: ' + drift90);
  near(t.lead_ft, R * Math.tan(45 * RAD) + 250 * (0.5 * bank / cap.turn.bank_rate_dps + lag) + drift90, 1e-6, 'lead');
  assert.ok(!t.over && t.off_ft === 0);
  near(t.rate_dps, (32.174 * Math.tan(bank * ratio * RAD) / 250) / RAD, 1e-6, 'turn rate');
  // the drift fades in between the corners cap.turn.drift_fade_deg, and is not in a corner under the wind's least or over the fly-by limit
  {
    const L = (d) => FM.turn({ delta_deg: d, alt_ft: 4000, vg_fps: 250, kcas: 150 }).lead_ft;
    const base = (d) => { const tt = FM.turn({ delta_deg: d, alt_ft: 4000, vg_fps: 250, kcas: 150 }); return tt.radius_ft * Math.tan(0.5 * Math.min(d, cap.turn.fly_by_max_deg) * RAD) + 250 * (0.5 * bank / cap.turn.bank_rate_dps + lag); };
    const [f0, f1] = cap.turn.drift_fade_deg;
    near(L(f0 - 1) - base(f0 - 1), 0, 1e-6, 'no drift under the fade');
    const mid = (f0 + f1) / 2;
    near(L(mid) - base(mid), (L(f1) - base(f1)) * (Math.sin(f1 * RAD) / Math.sin(mid * RAD)) * 0.5, 1e-6, 'half the drift halfway through the fade (over the sine of the corner)');
    near(L(5) - base(5), 0, 1e-6, 'none in a small turn');
    near(L(cap.turn.fly_by_max_deg + 10) - base(cap.turn.fly_by_max_deg + 10), 0, 1e-6, 'none in a fly-over');
  }
  // heavier, the aircraft flies more bank for the command and turns tighter
  assert.ok(FM.turn({ delta_deg: 90, alt_ft: 4000, vg_fps: 250, kcas: 150, weight_lb: 26000 }).radius_ft < t.radius_ft);
  // the wind is in the ground speed: a slower aircraft turns tighter and starts later
  const slow = FM.turn({ delta_deg: 90, alt_ft: 4000, vg_fps: 200, kcas: 150 });
  assert.ok(slow.radius_ft < t.radius_ft && slow.lead_ft < t.lead_ft);
}
// past the fly-by limit the corner is led as one at the limit and flown over: two radii off the new line
{
  const t = FM.turn({ delta_deg: 160, alt_ft: 4000, vg_fps: 250, kcas: 150 });
  const edge = FM.turn({ delta_deg: cap.turn.fly_by_max_deg, alt_ft: 4000, vg_fps: 250, kcas: 150 });
  assert.ok(t.over && !edge.over);
  near(t.lead_ft, edge.lead_ft, 1e-9, 'led as the limit');
  near(t.off_ft, 2 * t.radius_ft, 1e-9, 'off the new line');
  const left = FM.turn({ delta_deg: -90, alt_ft: 4000, vg_fps: 250, kcas: 150 });
  near(left.lead_ft, FM.turn({ delta_deg: 90, alt_ft: 4000, vg_fps: 250, kcas: 150 }).lead_ft, 1e-9, 'left as right');
}
// the roll delay table is the measured one, held at its ends
assert.deepStrictEqual(cap.turn.roll_delay.kcas, [110, 150, 200]);
near(FM.rollLagS(150), cap.turn.roll_delay.delay_s[1], 1e-12, 'lag at a table point');
near(FM.rollLagS(50), cap.turn.roll_delay.delay_s[0], 1e-12, 'lag below');
near(FM.rollLagS(300), cap.turn.roll_delay.delay_s[2], 1e-12, 'lag above');
// the approach: the speed for the approach lift coefficient (the aircraft's), and the glide path
near(FM.approachKcas(20000), Math.sqrt(20000 / (0.645 * 540 * 0.5 * 0.0023769)) / 1.6878099, 1e-9, 'approach speed');
near(FM.approachKcas(20000), 130.2, 0.1, 'approach speed at 20,000 lb: what the aircraft flies');
near(FM.pathHeightFt(60761), 5.3 + 0.07782 * 60761, 1e-6, 'path height at 10 nmi');
// the slowing down, flown: a light aircraft takes distance to slow to the approach speed, a heavy one almost none
{
  const light = FM.slowing(12000);
  const heavy = FM.slowing(26700);
  assert.ok(light.slow_ft > 4000 && heavy.slow_ft < 500 && light.slow_s > heavy.slow_s);
  near(FM.slowing(cap.flown.slowing[2].weight_lb).slow_ft, cap.flown.slowing[2].slow_ft, 1e-9, 'at a table point');
}
// the bank the angle-of-attack margin allows on the final: the least bank for a light aircraft in the landing configuration, the full bank for a heavy one
assert.strictEqual(FM.finalBankDeg(12000), cap.turn.min_bank_deg);
near(FM.finalBankDeg(26700), FM.bankLimitDeg(0), 1e-9, 'final bank, heavy');
// the descent as flown: steeper at a lighter weight and at height, and a table point is the table's
assert.ok(FM.descentFpm(20000, 14000) < FM.descentFpm(20000, 22000));
assert.ok(FM.descentFpm(30000, 22000) < FM.descentFpm(10000, 22000));
near(FM.descentFpm(cap.flown.alt_ft[4], cap.flown.weight_lb[2]), cap.flown.descent_fpm[4][2], 1e-9, 'descent at a table point');
// no hole in the descent table (the unsettled corner is filled from the trim, and says so)
cap.flown.descent_fpm.forEach((row) => row.forEach((v) => assert.ok(Number.isFinite(v) && v < 0)));
// the turn onto the first leg after takeoff (fdm/departure.py's table): off the line grows with the corner, so does the way back; the limit's corner is where the table crosses it
{
  const rows = cap.flown.departure.rows;
  assert.ok(rows.length >= 6 && rows[0].delta_deg === 0 && rows[0].off_ft < 50, 'straight on: no sweep');
  for (let i = 1; i < rows.length; i++) assert.ok(rows[i].off_ft > rows[i - 1].off_ft && rows[i].turned_deg >= rows[i - 1].turned_deg, `row ${i}`);
  near(FM.departureOffFt(rows[3].delta_deg), rows[3].off_ft, 1e-9, 'off at a table row');
  near(FM.departureOffFt(-rows[3].delta_deg), rows[3].off_ft, 1e-9, 'either side');
  near(FM.departureBackNm(rows[4].delta_deg), rows[4].back_nm, 1e-9, 'back at a table row');
  const m = FM.departureMaxDeg();
  near(FM.departureOffFt(m), FM.DEPART_OFF_LIMIT_FT, 1e-6, 'the limit corner is flown 700 ft off');
  assert.ok(FM.departureMaxDeg(2000) > m && FM.departureMaxDeg(300) < m, 'a looser limit allows a larger corner');
  assert.strictEqual(FM.departureMaxDeg(1e9), rows[rows.length - 1].delta_deg);
}
// one source: no capability number is typed in the station's planner modules (the aircraft's laws, missionmgr and the flown tables have them)
const fs = require('fs');
for (const f of ['plancheck.js', 'router.js', 'predict.js', 'flightmath.js']) {
  const src = fs.readFileSync(`${__dirname}/../js/${f}`, 'utf8');
  for (const typed of ['0.07782', '0.645', 'APPROACH_KT', 'BANK_LIMIT', '0.86']) assert.ok(!src.includes(typed), `${f} types ${typed}`);
}
console.log('flightmath: ok');
