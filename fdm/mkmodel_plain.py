#!/usr/bin/env python3
"""The 3-D model for FlightGear, generated from fdm/data/geometry.json: a first shape, right in its dimensions and
plain in its looks. Fuselage, wing, V-tail, nacelle and gear as simple lofts; ailerons, ruddervators, spoilers and
gear as separate objects that move with the flight model's own properties.

    python3 fdm/mkmodel.py        writes GlobalHawk/Models/GlobalHawk.ac and GlobalHawk.xml, and tests itself

Frames. The geometry is in feet: x aft from the nose, y to the right, z up from the ground, which is also the
flight model's structural frame (its visual reference point is the origin). FlightGear's model frame is the same
in metres. An .ac file has y up and z towards the viewer: a point (x, y, z) is written (x, z, -y).

What is assumed, not measured: the fuselage's width along its length (the side view gives only depth), the wing
section's shape (a plain 15 % thick lens), where the spoilers are, the gear legs.
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'GlobalHawk', 'Models')
G = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
FT = 0.3048
AILERON = dict(inner=0.55, outer=0.95, chord=0.25)         # as fdm/strips.py
RUDDERVATOR = dict(chord=0.30)
SPOILER = dict(inner=0.18, outer=0.50, front=0.62, back=0.76, travel_deg=45.0)     # assumed position on the wing
WHITE, GREY, DARK = 0, 1, 2
J = 'fdm/jsbsim/'


class Obj:
    def __init__(self, name, mat=WHITE):
        self.name, self.mat, self.v, self.f = name, mat, [], []

    def add(self, pts):
        n = len(self.v)
        self.v += [tuple(p) for p in pts]
        return list(range(n, n + len(pts)))

    def ring_loft(self, rings, close_ends=True):
        """Skin a list of rings (each a list of points, all the same length)."""
        idx = [self.add(r) for r in rings]
        m = len(rings[0])
        for a, b in zip(idx[:-1], idx[1:]):
            for k in range(m):
                self.f.append((a[k], a[(k + 1) % m], b[(k + 1) % m], b[k]))
        if close_ends:
            self.f.append(tuple(reversed(idx[0])))
            self.f.append(tuple(idx[-1]))

    def write(self, fh):
        fh.write('OBJECT poly\nname "%s"\nnumvert %d\n' % (self.name, len(self.v)))
        for x, y, z in self.v:
            fh.write('%.4f %.4f %.4f\n' % (x * FT, z * FT, -y * FT))
        fh.write('numsurf %d\n' % len(self.f))
        for f in self.f:
            fh.write('SURF 0x30\nmat %d\nrefs %d\n' % (self.mat, len(f)))      # 0x30: two-sided, smooth shaded
            for i in f:
                fh.write('%d 0 0\n' % i)
        fh.write('kids 0\n')


def section(le, chord, normal, tc, x0=0.0, x1=1.0, n=7):
    """A closed lens-shaped section from x0 to x1 of the chord: points around it. le: leading edge (x, y, z);
    the chord runs aft along x; thickness along `normal`."""
    xs = np.linspace(x0, x1, n)
    t = lambda x: 2.6 * tc * (math.sqrt(max(x, 0.0)) * (1 - x)) + 0.004      # about tc thick at 30 % chord
    up = [(le[0] + x * chord, le[1] + normal[1] * t(x) * chord / 2, le[2] + normal[2] * t(x) * chord / 2) for x in xs]
    dn = [(le[0] + x * chord, le[1] - normal[1] * t(x) * chord / 2, le[2] - normal[2] * t(x) * chord / 2) for x in reversed(xs)]
    return up + dn


def wing_le(y):
    w = G['wing']
    return (w['le_centreline_x'] + abs(y) * math.tan(math.radians(w['sweep_le_deg'])), y, w['z'])


def wing_chord(y):
    w = G['wing']
    return w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * abs(y) / (w['span'] / 2)


def panel(name, ys, le, chord, normal, tc, x0, x1, mat=WHITE):
    o = Obj(name, mat)
    o.ring_loft([section(le(y), chord(y), normal, tc, x0, x1) for y in ys])
    return o


def tail_geom(side):
    t = G['vtail']
    d = math.radians(t['dihedral_deg'])
    root = np.array([t['root_le_x'], side * t['root_y'], t['root_z']])
    tip = np.array([t['tip_le_x'], side * (t['root_y'] + t['panel_span'] * math.cos(d)), t['root_z'] + t['panel_span'] * math.sin(d)])
    le = lambda s: tuple(root + (tip - root) * s)
    chord = lambda s: t['root_chord'] + (t['tip_chord'] - t['root_chord']) * s
    return le, chord, (0.0, -side * math.sin(d), math.cos(d))


def cylinder(o, a, b, r, n=14, axis='x'):
    rings = []
    for p in (a, b):
        if axis == 'x':
            rings.append([(p[0], p[1] + r * math.cos(2 * math.pi * k / n), p[2] + r * math.sin(2 * math.pi * k / n)) for k in range(n)])
        else:   # along y: a wheel
            rings.append([(p[0] + r * math.cos(2 * math.pi * k / n), p[1], p[2] + r * math.sin(2 * math.pi * k / n)) for k in range(n)])
    o.ring_loft(rings)


def build():
    objs, anims = [], []
    w, half = G['wing'], G['wing']['span'] / 2
    # fuselage: the side view's depth; the width is assumed to follow it up to the published maximum
    f = G['fuselage']
    fus = Obj('fuselage')
    rings = []
    for s in f['profile']:
        a = max((s['z_top'] - s['z_bottom']) / 2, 0.02)
        b = min(f['max_width'] / 2, a * f['max_width'] / f['max_depth'] * 1.25)
        zc = (s['z_top'] + s['z_bottom']) / 2
        rings.append([(s['x'], b * math.cos(2 * math.pi * k / 16), zc + a * math.sin(2 * math.pi * k / 16)) for k in range(16)])
    fus.ring_loft(rings)
    objs.append(fus)
    # nacelle on the back
    n = G['nacelle']
    nac = Obj('nacelle', GREY)
    cylinder(nac, (n['inlet_x'], 0, n['thrust_line_z']), (n['exhaust_x'], 0, n['thrust_line_z']), n['diameter'] / 2)
    objs.append(nac)
    up = (0.0, 0.0, 1.0)
    for side, sn in ((1, 'right'), (-1, 'left')):
        ya, yb = AILERON['inner'] * half, AILERON['outer'] * half
        le = lambda y, side=side: wing_le(side * y)
        ch = lambda y: wing_chord(y)
        hinge = 1 - AILERON['chord']
        objs.append(panel('wing-%s-inner' % sn, np.linspace(0.0, ya, 6), le, ch, up, w['tc'], 0, 1))
        objs.append(panel('wing-%s-mid' % sn, np.linspace(ya, yb, 5), le, ch, up, w['tc'], 0, hinge))
        objs.append(panel('wing-%s-tip' % sn, np.linspace(yb, half, 3), le, ch, up, w['tc'], 0, 1))
        objs.append(panel('aileron-%s' % sn, np.linspace(ya, yb, 5), le, ch, up, w['tc'], hinge, 1, GREY))
        h0, h1 = np.array(le(ya)) + [hinge * ch(ya), 0, 0], np.array(le(yb)) + [hinge * ch(yb), 0, 0]
        # ctl/aileron-deg: right trailing edge down positive; the left moves the other way
        anims.append(dict(obj='aileron-%s' % sn, prop=J + 'ctl/aileron-deg', factor=1.0 if side > 0 else -1.0, a=h0, b=h1, down=side))
        # spoiler: a plate on the upper surface, hinged at its front edge
        sa, sb = SPOILER['inner'] * half, SPOILER['outer'] * half
        sp = Obj('spoiler-%s' % sn, DARK)
        rs = []
        for y in (sa, sb):
            c = ch(y)
            top = lambda x, c=c: w['z'] + 1.3 * w['tc'] * (math.sqrt(x) * (1 - x)) * c + 0.03
            x0, x1 = le(y)[0] + SPOILER['front'] * c, le(y)[0] + SPOILER['back'] * c
            rs.append([(x0, side * y, top(SPOILER['front'])), (x1, side * y, top(SPOILER['back'])), (x1, side * y, top(SPOILER['back']) + 0.04), (x0, side * y, top(SPOILER['front']) + 0.04)])
        sp.ring_loft(rs)
        objs.append(sp)
        anims.append(dict(obj='spoiler-%s' % sn, prop=J + 'ctl/spoiler-norm', factor=SPOILER['travel_deg'], a=np.array(rs[0][0]), b=np.array(rs[1][0]), down=-side))
        # V-tail: a fixed front and the ruddervator
        tle, tch, tn = tail_geom(side)
        th = 1 - RUDDERVATOR['chord']
        ss = np.linspace(0, 1, 5)
        objs.append(panel('tail-%s' % sn, ss, tle, tch, tn, 0.10, 0, th))
        objs.append(panel('ruddervator-%s' % sn, ss, tle, tch, tn, 0.10, th, 1, GREY))
        r0, r1 = np.array(tle(0)) + [th * tch(0), 0, 0], np.array(tle(1)) + [th * tch(1), 0, 0]
        # ctl/pitch-deg: both trailing edges down positive; ctl/yaw-deg: nose right positive, which is the right
        # panel's trailing edge down and the left one's up... as seen from each panel's own upper side
        anims.append(dict(obj='ruddervator-%s' % sn, expr=(J + 'ctl/pitch-deg', J + 'ctl/yaw-deg', 1.0 if side < 0 else -1.0), a=r0, b=r1, down=side))
    # gear: a leg and two wheels on each main, one on the nose (photographs); shown while the gear is not up
    g = G['gear']
    for name, x, y, axle, d in (('gear-nose', g['nose_x'], 0.0, g['nose_axle_z'], g['nose_wheel_diameter']),
                                ('gear-left', g['main_x'], -g['main_track'] / 2, g['main_axle_z'], g['main_wheel_diameter']),
                                ('gear-right', g['main_x'], g['main_track'] / 2, g['main_axle_z'], g['main_wheel_diameter'])):
        o = Obj(name, DARK)
        sp = g['main_wheel_spacing'] if 'nose' not in name else 0.5
        for s in ((0,) if 'nose' in name else (-1, 1)):
            cylinder(o, (x, y + s * sp / 2 - 0.22, axle), (x, y + s * sp / 2 + 0.22, axle), d / 2, axis='y')
        top = G['wing']['z'] - 0.3 if 'nose' not in name else 3.6
        leg = [(x - 0.15, y - 0.15), (x + 0.15, y - 0.15), (x + 0.15, y + 0.15), (x - 0.15, y + 0.15)]
        o.ring_loft([[(px, py, axle) for px, py in leg], [(px, py, top) for px, py in leg]])
        objs.append(o)
    return objs, anims


def write(objs, anims):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'GlobalHawk.ac'), 'w') as fh:
        fh.write('AC3Db\n')
        for rgb, name in (((0.93, 0.93, 0.93), 'white'), ((0.72, 0.74, 0.76), 'grey'), ((0.12, 0.12, 0.13), 'dark')):
            fh.write('MATERIAL "%s" rgb %g %g %g  amb 0.7 0.7 0.7  emis 0 0 0  spec 0.2 0.2 0.2  shi 20  trans 0\n' % ((name,) + rgb))
        fh.write('OBJECT world\nkids %d\n' % len(objs))
        for o in objs:
            o.write(fh)
    x = ['<?xml version="1.0"?>', '<!-- Generated by fdm/mkmodel.py from fdm/data/geometry.json: a first shape, right in its dimensions, plain in its looks. -->',
         '<PropertyList>', ' <path>GlobalHawk.ac</path>']
    for a in anims:
        p0, p1 = a['a'] * FT, a['b'] * FT
        x.append(' <animation><type>rotate</type><object-name>%s</object-name>' % a['obj'])
        if 'expr' in a:
            pitch, yaw, sign = a['expr']
            x.append('  <expression><sum><property>%s</property><product><value>%g</value><property>%s</property></product></sum></expression>' % (pitch, sign, yaw))
            x.append('  <factor>%g</factor>' % a['down'])
        else:
            x.append('  <property>%s</property><factor>%g</factor>' % (a['prop'], a['factor'] * a['down']))
        x.append('  <axis><x1-m>%.4f</x1-m><y1-m>%.4f</y1-m><z1-m>%.4f</z1-m><x2-m>%.4f</x2-m><y2-m>%.4f</y2-m><z2-m>%.4f</z2-m></axis></animation>' % (
            p0[0], p0[1], p0[2], p1[0], p1[1], p1[2]))
    x.append(' <animation><type>select</type><object-name>gear-nose</object-name><object-name>gear-left</object-name><object-name>gear-right</object-name>')
    x.append('  <condition><greater-than><property>%sgear/gear-pos-norm</property><value>0.02</value></greater-than></condition></animation>' % J)
    x.append('</PropertyList>')
    open(os.path.join(OUT, 'GlobalHawk.xml'), 'w').write('\n'.join(x) + '\n')


def test(objs, anims):
    """F4: the generated shape has the published dimensions; every moving part exists and has its property."""
    v = np.array([p for o in objs for p in o.v])
    span, length, height = np.ptp(v[:, 1]), np.ptp(v[:, 0]), v[:, 2].max()
    tail_tip = G['vtail']['root_z'] + G['vtail']['panel_span'] * math.sin(math.radians(G['vtail']['dihedral_deg']))
    rows = [('span', span, G['wing']['span']), ('length', length, G['fuselage']['length']), ('height', height, max(tail_tip, G['nacelle']['top_z'])),
            ('lowest point (the tyres on the ground)', v[:, 2].min(), 0.0)]
    ok = True
    for name, got, want in rows:
        good = abs(got - want) <= max(0.01 * abs(want), 0.15)
        ok &= good
        print('  %-40s %7.2f ft, published %7.2f  %s' % (name, got, want, 'pass' if good else 'MISS'))
    names = {o.name for o in objs}
    for a in anims:
        good = a['obj'] in names and ('prop' in a or 'expr' in a)
        ok &= good
    print('  %d objects, %d vertices, %d faces; %d moving parts, each with its property: %s' % (len(objs), len(v), sum(len(o.f) for o in objs), len(anims) + 3, 'pass' if ok else 'MISS'))
    return ok


if __name__ == '__main__':
    objs, anims = build()
    write(objs, anims)
    print('wrote GlobalHawk/Models/GlobalHawk.ac and GlobalHawk.xml')
    raise SystemExit(0 if test(objs, anims) else 1)
