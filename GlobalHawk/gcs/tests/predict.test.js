// node tests/predict.test.js : the forecast's own logic (its numbers against the model: fdm/phase8c_checks.py)
const assert = require('assert');
const P = require('../js/perfdata.js');
const pr = require('../js/predict.js').make(P);
const NM = 6076.1;
const st = { alt_ft: 20000, weight_lb: 20000, fuel_lb: 8550 };
// level: time is distance over the schedule's speed
const lv = pr.predict([{ dist_ft: 100 * NM, alt_ft: 20000 }], st);
assert.ok(Math.abs(lv.total.t_s - (100 / pr.ktas(20000)) * 3600) < 25, 'level time');
assert.ok(lv.points[0].reached && !lv.warnings.length);
// fuel only falls, distance only grows, along the profile
for (let i = 1; i < lv.profile.length; i++) assert.ok(lv.profile[i][3] <= lv.profile[i - 1][3] && lv.profile[i][0] >= lv.profile[i - 1][0]);
// more distance never takes less time
assert.ok(pr.predict([{ dist_ft: 120 * NM, alt_ft: 20000 }], st).total.t_s > lv.total.t_s);
// a climb that fits is reached; one that cannot be made is reported, and the aircraft is left at its ceiling
const up = pr.predict([{ dist_ft: 100 * NM, alt_ft: 40000 }], st);
assert.ok(up.points[0].reached && Math.abs(up.points[0].alt_ft - 40000) <= 151);
const heavy = pr.predict([{ dist_ft: 400 * NM, alt_ft: 65000 }], { alt_ft: 20000, weight_lb: 26700, fuel_lb: 15250 });
assert.ok(!heavy.points[0].reached && heavy.points[0].alt_ft < 60000 && heavy.points[0].alt_ft > 45000, 'ceiling ' + heavy.points[0].alt_ft);
assert.ok(/not reached/.test(heavy.warnings[0]));
// too short to climb in: reported
assert.ok(!pr.predict([{ dist_ft: 5 * NM, alt_ft: 40000 }], st).points[0].reached);
// running low is said
const dry = pr.predict([{ dist_ft: 300 * NM, alt_ft: 20000 }], { alt_ft: 20000, weight_lb: 12300, fuel_lb: 850 });
assert.ok(dry.warnings.some((w) => /reserve|runs out/.test(w)));
// a landing leg ends at the field
const ld = pr.predict([{ kind: 'land', dist_ft: 16 * NM, alt_ft: 2300 }], { alt_ft: 7500, weight_lb: 15000, fuel_lb: 3550 });
assert.ok(Math.abs(ld.points[0].alt_ft - 2300) < 60, 'landing ends at ' + ld.points[0].alt_ft);
console.log('predict OK');
