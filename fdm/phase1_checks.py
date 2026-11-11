#!/usr/bin/env python3
"""Phase 1 checks: geometry and mass against the published numbers. Reads fdm/data/geometry.json and mass.json.

The limits were written down before the measurements (the scale limits in the build plan; the others here, when
the 3-D model turned out not to be to scale). A miss stays in the list with its cause: fdm/data/README.md.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
g = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
m = json.load(open(os.path.join(HERE, 'data', 'mass.json')))
rows = []


def check(name, kind, value, target, limit_percent):
    err = 100.0 * (value - target) / target
    rows.append((name, kind, value, target, err, limit_percent, abs(err) <= limit_percent))


ms, sv, w = g['mesh_scale'], g['side_view'], g['wing']
# the 3-D model as a whole, scaled by its span
check('3-D model scaled by span: length, ft', 'measured', ms['length_if_scaled_by_span'], 44.4, 1.0)
check('3-D model scaled by span: height, ft', 'measured', ms['height_if_scaled_by_span'], 15.2, 3.0)
check('3-D model scaled by span: wing area, ft2', 'measured', ms['wing_area_if_scaled_by_span'], 540.0, 3.0)
# scaled by its length instead
check('3-D model scaled by length: span, ft', 'measured', ms['span_if_scaled_by_length'], 116.2, 1.0)
check('3-D model scaled by length: height, ft', 'measured', ms['height_if_scaled_by_length'], 15.2, 3.0)
check('3-D model, span by span and chords by length: wing area, ft2', 'measured', ms['wing_area_if_chords_by_length'], 540.0, 3.0)
# NASA's side view, scaled by the published length
check('side view: height, ft (NASA 15.2)', 'measured', sv['height'], 15.2, 3.0)
check('side view: height, ft (Northrop Grumman 14.6)', 'measured', sv['height'], 14.6, 3.0)
# what was built
check('wing as built: aspect ratio (Jane\'s 25.09)', 'by construction', w['aspect_ratio'], 25.09, 1.0)
check('wing as built: root chord with fillet against the side view, ft', 'measured',
      w['stations'][0]['chord'], sv['root_chord_as_drawn'], 5.0)
st = m['states']
check('weights add up to the published gross, lb', 'by construction', st[0]['weight'], 26750.0, 0.01)
check('without fuel: gross less fuel, lb', 'by construction', st[-1]['weight'], 26750.0 - 15300.0, 0.01)

print('%-66s %-16s %9s %9s %7s %6s' % ('check', 'kind', 'value', 'target', 'err %', 'limit'))
for name, kind, value, target, err, lim, ok in rows:
    print('%-66s %-16s %9.2f %9.2f %+7.1f %6.1f  %s' % (name, kind, value, target, err, lim, 'pass' if ok else 'MISS'))
print()
print('not checks, no published figure to compare with (estimates):')
print('  nose gear load %.1f to %.1f %% of the weight (looked for: 8 to 20 %%)' % (
    min(s['nose_gear_load_percent'] for s in st), max(s['nose_gear_load_percent'] for s in st)))
print('  centre of gravity %.1f to %.1f %% of the mean chord, full to no fuel' % (st[0]['cg_percent_mac'], st[-1]['cg_percent_mac']))
print('  V-tail volumes: horizontal %.3f, vertical %.4f' % (g['vtail']['horizontal_volume'], g['vtail']['vertical_volume']))
print('  the symbol on the side view sits at %.1f %% of the mean chord' % sv['symbol_percent_mac'])
missed = [r[0] for r in rows if not r[6]]
print('\n%d checks, %d pass, %d miss' % (len(rows), len(rows) - len(missed), len(missed)))
sys.exit(0)
