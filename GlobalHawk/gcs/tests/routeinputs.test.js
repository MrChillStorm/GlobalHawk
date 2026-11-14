// node tests/routeinputs.test.js
const assert = require('assert');
const RI = require('../js/routeinputs.js');
const plan = require('../js/demoplan.js');
const predict = require('../js/predict.js');
const perf = require('../js/perfdata.js');
const fc = predict.make(perf);

// where it begins
let s = RI.startOf(plan, false, null, NaN);
assert.deepStrictEqual(s.pos, plan.items[1].end);
assert.strictEqual(s.alt_ft, plan.field.elev_ft + 100);
s = RI.startOf(plan, true, [35.1, -117.6], 21000);
assert.deepStrictEqual(s, { pos: [35.1, -117.6], alt_ft: 21000 });
const noTakeoff = JSON.parse(JSON.stringify(plan));
noTakeoff.items = noTakeoff.items.filter((i) => i.kind !== 'takeoff');
assert.deepStrictEqual(RI.startOf(noTakeoff, false, null, NaN).pos, [plan.field.lat, plan.field.lon]);
// the goal: the plan's own last point when it is at the fix, else the height over the ground the aircraft's capability asks for there (flightmath: the path comes down to it in time to be taken over cleanly), at the landing weight
const FM = require('../js/flightmath.js');
const geoR = require('../js/geo.js');
let g = RI.goalOf(plan);
assert.deepStrictEqual(g.fix, plan.items[3].fix);
assert.strictEqual(g.fix_alt_ft, 6500);
const other = JSON.parse(JSON.stringify(plan));
other.items[2].points[3] = [34.2, -117.0, 9000];
const askFor = (elev, land, w) => Math.round((elev + FM.finalFixHeightAgl(geoR.course(land.fix, land.aim).ft, w)) / 100) * 100;
assert.strictEqual(RI.goalOf(other).fix_alt_ft, askFor(2300, other.items[3], 20000), 'the field\'s 2,300 ft and the capability\'s height over it, to 100 ft');
assert.ok(RI.goalOf(other, 26700).fix_alt_ft <= RI.goalOf(other, 12000).fix_alt_ft + 3000 && Number.isFinite(RI.goalOf(other, 12000).fix_alt_ft), 'the weight is taken');
assert.ok(RI.goalOf(other).fix_alt_ft - 2300 <= FM.pathHeightFt(geoR.course(other.items[3].fix, other.items[3].aim).ft) - FM.captureGapFt() + 50, 'the path is the gap above the aircraft at the fix');
assert.strictEqual(RI.goalOf({ field: plan.field, items: [plan.items[0]] }), null);

// the sites that count: the plan's, and airports by what the landing needs
const airports = [
  { ident: 'KAAA', lat: 35.5, lon: -117, elev_ft: 2000, paved_ft: 12000 },
  { ident: 'KBBB', lat: 35.6, lon: -116, elev_ft: 2000, paved_ft: 6000 },
  { ident: 'KCCC', lat: 35.7, lon: -115, elev_ft: 2000, paved_ft: 4000 },
  { ident: 'KDDD', lat: plan.sites[0].aim[0], lon: plan.sites[0].aim[1], elev_ft: 2300, paved_ft: 12000 },
];
const r = RI.sites(plan, airports, fc, 25000);
const names = r.list.map((x) => `${x.name}:${x.tier}`);
assert.deepStrictEqual(names, ['Demo field 04:1', 'KAAA:1', 'KBBB:2'], names.join());
assert.ok(/1 of the plan's sites, 1 airports that can hold the landing at 25000 lb and 1 shorter strips/.test(r.note), r.note);
// lighter: the 6,000 ft one passes
assert.ok(RI.sites(plan, airports, fc, 15000).list.some((x) => x.name === 'KBBB' && x.tier === 1));
assert.ok(/no airports are loaded/.test(RI.sites(plan, [], fc, 25000).note));

// the words
const card = { names: ['Least fuel', 'Fastest'], time_s: 7500, fuel_lb: 1277.6, dist_nm: 510, alt_ft: 45000, coverage: { longest_gap_nm: 0, share: 1 }, avoids: ['R-2508 (restricted)'], warnings: [], vs_fuel: { time_s: 0, fuel_lb: 0, dist_nm: 0 } };
let w = RI.words(card);
assert.strictEqual(w.title, 'Least fuel · Fastest');
assert.strictEqual(w.stats, '2 h 05 min · 1278 lb · 510 nmi · 45,000 ft');
assert.strictEqual(w.reach, 'a landing site in glide reach all the way');
assert.strictEqual(w.avoids, 'goes round R-2508 (restricted)');
assert.strictEqual(w.diff, '');
w = RI.words(Object.assign({}, card, { names: ['Cautious'], coverage: { longest_gap_nm: 82, share: 0.8 }, vs_fuel: { time_s: 540, fuel_lb: -20.4, dist_nm: 36 } }));
assert.strictEqual(w.reach, 'no landing site in glide reach for up to 82 nmi (20 % of the route)');
assert.strictEqual(w.diff, '+9 min, −20 lb, +36 nmi against the least fuel');
w = RI.words({ names: ['Direct'], direct: true, blocked_by: 'R-2508 (restricted)', time_s: 6900, fuel_lb: 1250, dist_nm: 500, alt_ft: 45000, coverage: null, vs_fuel: { time_s: -600, fuel_lb: -27, dist_nm: -10 } });
assert.strictEqual(w.avoids, 'crosses R-2508 (restricted)');
assert.strictEqual(w.reach, '');
assert.ok(/−10 min/.test(w.diff));
// the minutes: never "1 h 60 min", never "−0 min"
w = RI.words(Object.assign({}, card, { time_s: 7190, vs_fuel: { time_s: -20, fuel_lb: -0.2, dist_nm: 0.1 } }));
assert.ok(/^2 h 00 min/.test(w.stats), w.stats);
assert.strictEqual(w.diff, '±0 min, ±0 lb, ±0 nmi against the least fuel');
assert.ok(/^59 min/.test(RI.words(Object.assign({}, card, { time_s: 3540 })).stats));
assert.ok(/^1 h 00 min/.test(RI.words(Object.assign({}, card, { time_s: 3571 })).stats));
console.log('routeinputs: ok');
