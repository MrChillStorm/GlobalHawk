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
// a turn worked by hand: 90 deg at 250 ft/s and 150 KCAS, the bank at 4,000 ft
{
  const bank = 25 * cap.turn.bank_command;
  const R = 250 * 250 / (32.174 * Math.tan(bank * RAD));
  const lag = FM.rollLagS(150);
  const t = FM.turn({ delta_deg: 90, alt_ft: 4000, vg_fps: 250, kcas: 150 });
  near(t.radius_ft, R, 1e-6, 'radius');
  near(t.lead_ft, R * Math.tan(45 * RAD) + 250 * (0.5 * bank / cap.turn.bank_rate_dps + lag), 1e-6, 'lead');
  assert.ok(!t.over && t.off_ft === 0);
  near(t.rate_dps, (32.174 * Math.tan(bank * RAD) / 250) / RAD, 1e-6, 'turn rate');
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
// one source: no capability number is typed in the station's planner modules (the aircraft's laws, missionmgr and the flown tables have them)
const fs = require('fs');
for (const f of ['plancheck.js', 'router.js', 'predict.js', 'flightmath.js']) {
  const src = fs.readFileSync(`${__dirname}/../js/${f}`, 'utf8');
  for (const typed of ['0.07782', '0.645', 'APPROACH_KT', 'BANK_LIMIT', '0.86']) assert.ok(!src.includes(typed), `${f} types ${typed}`);
}
console.log('flightmath: ok');
