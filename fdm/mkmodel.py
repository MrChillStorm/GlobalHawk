#!/usr/bin/env python3
"""The 3-D model for FlightGear, made from NASA's own 3-D model of the Global Hawk.

    python3 fdm/mkmodel.py        writes GlobalHawk/Models/GlobalHawk.ac and GlobalHawk.xml, and tests itself

NASA's model (refs/model3d/NASA-3D-Global-Hawk.glb, from NASA 3D Resources; not in this repository) has the
aircraft's real shapes: the bulged nose, the nacelle with its intake duct, the gear with struts, braces and doors.
Its proportions are not the aircraft's: scaled to the right length its span is 90 ft, not 116. So:

- everything is scaled by one factor, the one that gives the published length (44.4 ft). The fuselage's width and
  depth then come out within 2 % of the published ones;
- the wing alone is stretched: along the span, outboard of the fuselage side, to the published 116.2 ft, and along
  the chord by the factor that gives the published wing area (fdm/geometry.py found both);
- the ailerons and ruddervators are cut out of the skin along their hinge lines (fdm/strips.py's: the outer wing's
  last quarter chord from 55 to 95 % of the half span; the tail panels' last 30 %), so they can move;
- the gear's pieces are grouped into three legs that fold away and are hidden when up. How the real gear folds
  is not in our sources: the mains swing inboard (their braces run inboard), the nose leg forward. Assumed.
- spoilers: thin plates on the upper surface where fdm/mkmodel_plain.py put them. Their real place is not known.

NASA's media guidelines allow this use (NASA material is generally not copyrighted; credit NASA; no endorsement
implied; no NASA insignia: the model carries none and none is added). The README says so.

Frames: NASA's file has x along the span, y up, z forward with the nose at +110.7. Ours, in feet: x aft from the
nose, y right, z up from the ground. An .ac file has y up and z towards the viewer: (x, y, z) is written (x, z, -y).
"""
import json
import math
import os
import sys

import numpy as np
import trimesh
from trimesh.intersections import slice_mesh_plane

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import glb          # noqa: E402

OUT = os.path.join(HERE, '..', 'GlobalHawk', 'Models')
G = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
FT = 0.3048
J = 'fdm/jsbsim/'
AILERON = dict(inner=0.55, outer=0.95, chord=0.25)
RUDDERVATOR = dict(chord=0.30)
SPOILER = dict(inner=0.18, outer=0.50, front=0.62, back=0.76, travel_deg=45.0)
WHITE, GREY, DARK, TYRE = 0, 1, 2, 3
RED_LIGHT, GREEN_LIGHT, WHITE_LIGHT = 4, 5, 6      # lamps: they glow by themselves
BLUE = 7                                         # the stripe
STRIPE = (4.05, 4.30, 1.0, 40.0)                 # ft: the blue stripe's lower and upper edge and its fore and aft ends
L = '/sim/model/globalhawk/lights/'               # what switches each lamp (Nasal/globalhawk.nas)
BAY_X = (22.0, 24.3)                      # ft: the opening in the gear fairing's underside, fore and aft of the wheels
KNEE = 0.15                               # where the main gear's side brace is jointed, as a fraction of its length from the fuselage
MAIN_OUT = G['gear']['main_out']           # ft: how much further out the main legs stand than in NASA's model (fdm/geometry.py)
NOSE_BAY = (6.7, 12.1, 0.7)               # ft: the nose gear bay's fore and aft ends and half width. It reaches as far forward as the wheel
# does when folded (the leg is 3.6 ft from pivot to axle and folds forward): with the bay where NASA's model has its doors, 1.9 ft
# further aft, the tyre came up through the skin ahead of the opening
DISC_X = 37.2                             # ft: where the vane disc is put, 3 ft inside the nozzle's mouth
NOZZLE = dict(x=(38.3, 38.7), y=-0.083, z=9.646, r=1.45)  # ft: the vane disc in NASA's model: flat, 1 in thick, centred here (its rings' own centre).
# Not the two rings further aft: they are the nozzle's lip, on a slightly different centre, and turned with the disc they made the whole nozzle seem to turn
# The fan and the turbine are drawn turning far slower than they do. Anything with evenly spaced blades looks frozen, or
# seems to shake back and forth, once it turns more than half a blade spacing between two frames: the 20-blade fan may
# turn 9 deg a frame, the 60-vane turbine disc only 3. At 20 frames a second that is 30 and 10 turns a minute.
SHOWN = {'fan': 0.004, 'fan-spinner': 0.004, 'turbine': 0.0012}      # fraction of the real speed (8,700 rpm at most)
S = G['fuselage']['length'] / G['mesh']['extent_length']          # ft per unit: the published length
SIDE = 13.0 * S                                                    # ft: the fuselage side, where the wing's stretch begins
HALF = G['wing']['span'] / 2
HEIGHT = 15.2                                                      # ft: NASA's published height, ground to the V-tail's tips on its wheels
KZ = 1.0                                                           # heights in NASA's model times this give HEIGHT (set in build)
WHEEL_TOP = 1.45                                                   # ft: below this a gear part is wheel, and keeps its shape
BEND = (10.0, 16.0, 22.0, 28.0, 38.0, 44.0, 50.0)                 # ft from the centreline: where the bending wing is hinged (and at the aileron's ends)
PODS = 8.0                                                         # ft: outboard of the gear fairings at the wing root; the wing's stretch begins here
ROOT_TE_X = 25.70                                                  # ft: the trailing edge just outboard of the fairings, which runs nearly square to the fuselage
WING_MID_X = 23.05                                                 # ft: the wing's mid-chord at that station in NASA's model
K_SPAN = (HALF - PODS) / (G['mesh']['half_span'] * S - PODS)
K_CHORD = G['wing']['chord_scale_ft_per_unit'] / S


def to_aircraft(v):
    m = G['mesh']
    return np.c_[(m['nose_z'] - v[:, 2]) * S, v[:, 0] * S, (v[:, 1] - m['ground_y']) * S]


def stretch_wing(v):
    """The wing to its published span and area. NASA's model has the two fairings at the wing root's trailing edge
    that the main gear folds into, and they are the right size as they are (the gear under them is). So nothing is
    stretched inboard of them: the stretch starts outboard of the fairings, at PODS, and takes the rest of the wing
    out to the published span; the chord's stretch comes in over the next 3 ft. (Stretched from the fuselage side,
    the fairings were pulled out into two fat lobes, away from the gear.)"""
    v = v.copy()
    # The trailing edge at the root. NASA's model carries it 1.8 ft aft between the fuselage and the gear, as a broad
    # fillet. Photographs of the aircraft (NASA 872 in flight; an RQ-4 on the ramp from behind) show the trailing
    # edge running straight to the fuselage, with only a small fairing at the gear standing a little behind it. So
    # what lies aft of the straight trailing edge there is drawn in to a quarter of its length.
    root = (np.abs(v[:, 1]) > 2.9) & (np.abs(v[:, 1]) < PODS) & (v[:, 0] > ROOT_TE_X) & (v[:, 0] < 29.0) & (v[:, 2] > 3.6 * KZ) & (v[:, 2] < 5.6 * KZ)
    v[root, 0] = ROOT_TE_X + (v[root, 0] - ROOT_TE_X) * 0.25
    wing = (np.abs(v[:, 1]) > PODS) & (v[:, 0] < 0.74 * G['fuselage']['length'])
    y = np.abs(v[wing, 1])
    blend = np.clip((y - PODS) / 3.0, 0.0, 1.0)
    # each point's chordwise place is kept about the wing's own mid-chord line there, which sweeps back with span
    sweep = math.tan(math.radians(G['wing']['sweep_quarter_deg']))
    xc = WING_MID_X + (y - PODS) * sweep
    v[wing, 0] = xc + (v[wing, 0] - xc) * (1 + (K_CHORD - 1) * blend)
    v[wing, 1] = np.sign(v[wing, 1]) * (PODS + (y - PODS) * K_SPAN)
    return v


def keep(mesh, normal, origin):
    """The part of a mesh on the positive side of a plane (cut exactly, triangles split)."""
    if mesh is None or len(mesh.faces) == 0:
        return None
    out = slice_mesh_plane(mesh, np.asarray(normal, float), np.asarray(origin, float), cap=False)
    return out if out is not None and len(out.faces) else None


def cut_out(mesh, planes):
    """Cut a convex region out of a mesh. planes: (normal, origin) pairs whose positive sides together are the region.
    Returns (what is inside, what is left)."""
    inside, rest = mesh, []
    for n, o in planes:
        n = np.asarray(n, float)
        out = keep(inside, -n, o)
        if out is not None:
            rest.append(out)
        inside = keep(inside, n, o)
        if inside is None:
            break
    return inside, trimesh.util.concatenate(rest) if rest else None


def chord_at(mesh, y, zlo=None, zhi=None):
    """Leading and trailing edge x of the wing at a span station."""
    sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])      # the skin is coarse along the span: cut it, don't look for vertices
    p = np.asarray(sec.vertices)
    p = p[p[:, 0] < 0.74 * G['fuselage']['length']]                         # not the tail, which reaches out over the inner wing
    return float(p[:, 0].min()), float(p[:, 0].max()), float(np.median(p[:, 2]))


def in_nozzle(b):
    """Is this piece of NASA's mesh part of the vane disc inside the nozzle? Inside a cylinder on the nozzle's axis."""
    v = b.vertices
    return bool(v[:, 0].min() > NOZZLE['x'][0] and v[:, 0].max() < NOZZLE['x'][1] and
                np.hypot(v[:, 1] - NOZZLE['y'], v[:, 2] - NOZZLE['z']).max() < NOZZLE['r'])


def nozzle_pipes(b):
    """NASA's model has two pipes standing in the nozzle, one inside the other, each built of strips with a flat ring
    on either end. They are square to the fuselage's axis while the nacelle's mouth is
    cut on the slant, so they meet neither the skin nor each other: in FlightGear, from behind, crescents of pipe
    edge one behind the other. Kept whole, kept in part, merged and unmerged were all tried and looked wrong. They
    are left out: the nacelle's own skin turns in at the mouth and runs forward as the duct's wall, and the vane
    disc sits in that."""
    v = b.vertices
    r = np.hypot(v[:, 1] + 0.05, v[:, 2] - 9.66)
    # Only the pipes: strips and rings between x 37.1 and 40.04. The few small pieces right on the mouth (x 40.07 to
    # 40.19) are not pipe: they fill two slots in the nacelle's lip, and with them gone the lip had two holes in it
    return bool(v[:, 0].min() > 37.0 and v[:, 0].max() < 40.06 and r.max() < 1.7 and r.min() > 1.1)


def gear_fairing(side):
    """The fairing under the wing root that a main leg folds into: NASA's 3-D model has none. NASA's photographs of
    872 show a blister low beside the fuselage behind the wing with the gear up, and the leg coming out from under
    the wing root with it down; that is all there is to go on, so its shape here is made up to do the job: a
    teardrop from ahead of the leg to a little behind the trailing edge, wide enough to take the leg lying inboard
    from its pivot and deep enough for the wheels. Its top is buried in the wing. Returns the shell, and the part of
    its underside that is the doors: closed over the leg when the gear is up, gone when it is down."""
    x0, x1, yc, top, n = 20.8, 27.6, 4.55 + MAIN_OUT / 2, 4.72 * KZ, 28
    xs = np.linspace(x0, x1, 26)
    rings = []
    for x in xs:
        t = (x - x0) / (x1 - x0)
        f = max(math.sin(math.pi * t ** 0.75), 0.0) ** 0.8
        a, b = (2.5 + MAIN_OUT / 2) * f ** 0.5, 0.95 * f
        rings.append([(x, side * (yc + a * math.cos(2 * math.pi * k / n)), top - b + b * math.sin(2 * math.pi * k / n)) for k in range(n)])
    v = np.array([p for r in rings for p in r])
    shell, doors = [], []
    for i in range(len(rings) - 1):
        for k in range(n):
            a0, a1, b0, b1 = i * n + k, i * n + (k + 1) % n, (i + 1) * n + k, (i + 1) * n + (k + 1) % n
            c = v[[a0, a1, b0, b1]].mean(axis=0)
            under = math.sin(2 * math.pi * (k + 0.5) / n) < -0.3
            tris = [(a0, a1, b1), (a0, b1, b0)] if side > 0 else [(a0, b1, a1), (a0, b0, b1)]
            (doors if under and BAY_X[0] < c[0] < BAY_X[1] else shell).extend(tris)
    mk = lambda f: trimesh.Trimesh(v, np.array(f), process=True)
    return mk(shell), mk(doors)


class Obj:
    def __init__(self, name, mesh, mat=WHITE):
        self.name, self.mesh, self.mat = name, mesh, mat

    def write(self, fh):
        v, f = self.mesh.vertices, self.mesh.faces
        fh.write('OBJECT poly\nname "%s"\ncrease 40.0\nnumvert %d\n' % (self.name, len(v)))
        for x, y, z in v:
            fh.write('%.4f %.4f %.4f\n' % (x * FT, z * FT, -y * FT))
        fh.write('numsurf %d\n' % len(f))
        for a, b, c in f:
            fh.write('SURF 0x%s\nmat %d\nrefs 3\n%d 0 0\n%d 0 0\n%d 0 0\n' % ('30', self.mat, a, b, c))   # smooth, and drawn from both sides: NASA's pieces don't all face the same way, and one-sided some vanish   # the blades are single sheets: drawn from both sides
        fh.write('kids 0\n')


def plate(name, corners, thick=0.035):
    """A thin plate from four corners (upper surface), for a spoiler."""
    c = np.array(corners)
    v = np.vstack([c, c + [0, 0, thick]])
    f = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]
    return Obj(name, trimesh.Trimesh(v, f, process=False), DARK)


def build():
    global KZ
    parts = glb.load()
    objs, anims = [], []
    # NASA's model is too tall for its length: scaled to the published 44.4 ft it stands 16.15 ft, against NASA's own
    # 15.2 ft (Northrop Grumman's sheet says 14.6; the side-view drawing 14.3). Everything is squashed in height to
    # 15.2 ft, about the ground. Two things keep their shape: the turbine's disc, and the wheels (a gear part is
    # squashed only above WHEEL_TOP, so the legs get shorter and the wheels stay round). The fan is made round again
    # where it is gathered, below.
    tall = max(to_aircraft(p['vertices'])[:, 2].max() for p in parts)
    KZ = HEIGHT / tall
    leg_top = max(to_aircraft(p['vertices'])[:, 2].max() for p in parts[1:2])        # the top of the tallest strut
    k_leg = (leg_top * KZ - WHEEL_TOP) / (leg_top - WHEEL_TOP)
    bodies = []
    turbine = []
    for i, p in enumerate(parts):
        v, f = to_aircraft(p['vertices']), p['faces'][:, ::-1]                                    # the mirror in y turns the faces over
        if i == 0:
            # The disc of vanes in the nozzle (the turbine's last stage, seen from behind) is made of some 230 small
            # pieces that only touch the skin. Taken out before the vertices are merged, or they fuse with it.
            loose = trimesh.Trimesh(v, f, process=False).split(only_watertight=False)
            turbine = [b for b in loose if in_nozzle(b)]
            rest = trimesh.util.concatenate([b for b in loose if not in_nozzle(b) and not nozzle_pipes(b)])
            v, f = rest.vertices, rest.faces
        v = np.array(v, float)
        if i == 0:
            v[:, 2] *= KZ
        else:
            up = v[:, 2] > WHEEL_TOP
            v[up, 2] = WHEEL_TOP + (v[up, 2] - WHEEL_TOP) * k_leg
        m = trimesh.Trimesh(v, f, process=True)
        for b in m.split(only_watertight=False):
            bodies.append((i, b))
    merged = max((b for i, b in bodies if i == 0), key=lambda b: len(b.faces))
    # The airframe is drawn with the vertices of touching pieces merged, so that the nacelle, the pylon and the
    # fuselage shade as one skin where they flow into each other; the .ac file's crease angle (40 deg) keeps real
    # edges sharp. (Unmerged, every one of NASA's pieces showed its outline.)
    airframe = trimesh.Trimesh(stretch_wing(merged.vertices), merged.faces, process=False)
    core = airframe
    # The wing bends: outboard of BEND[0] it is cut into segments along the span, each hinged to the one inboard of it
    # about a chordwise line at the wing's own height there, and turned by the flight model's tip deflection
    # (flex/tip-deflection-ft: about -1.6 ft standing with full tanks, +4.3 ft in flight at 1 g) so that the segments'
    # ends lie on the beam model's bent shape (fdm/data/flex.json). The ailerons and the spoilers are cut at the same
    # places and go with their segments.
    flex = json.load(open(os.path.join(HERE, 'data', 'flex.json')))['shape']
    fy, fd = np.array([0.0] + list(flex['y']) + [HALF]), np.array([0.0] + list(flex['deflection_over_tip']) + [1.0])
    ya, yb = AILERON['inner'] * HALF, AILERON['outer'] * HALF
    cuts = sorted(set(list(BEND) + [ya, yb]))                      # the hinges' stations; the aileron's ends are among them
    ends = cuts + [HALF + 1.0]
    defl = lambda y: float(np.interp(min(y, HALF), fy, fd))
    slopes = [(defl(min(ends[k + 1], HALF)) - defl(ends[k])) / (min(ends[k + 1], HALF) - ends[k]) for k in range(len(cuts))]
    kinks = [math.degrees(slopes[k] - (slopes[k - 1] if k else 0.0)) for k in range(len(cuts))]      # deg per ft of tip deflection at each hinge
    for side, sn in ((1, 'right'), (-1, 'left')):
        la, ta, za = chord_at(airframe, side * (ya + 0.4))
        lb, tb, zb = chord_at(airframe, side * (yb - 0.4))
        h = 1 - AILERON['chord']
        h0, h1 = np.array([la + h * (ta - la), side * ya, za]), np.array([lb + h * (tb - lb), side * yb, zb])
        along = (h1 - h0) / np.linalg.norm(h1 - h0)
        aft = np.cross(along, (0, 0, 1.0)) * side                    # horizontal, pointing aft of the hinge line
        aft /= np.linalg.norm(aft)
        if aft[0] < 0:
            aft = -aft
        hinges = []                                                  # each bending hinge of this wing: an animation's fields
        for k, yk in enumerate(cuts):
            zk = chord_at(airframe, side * (yk + 0.2))[2]
            hinges.append(dict(prop=J + 'flex/tip-deflection-ft', factor=side * kinks[k], down=1.0, a=np.array([20.0, side * yk, zk]), b=np.array([21.0, side * yk, zk])))
        bent = lambda name, k: [dict(hk, obj=name) for hk in hinges[:k + 1]]         # the hinges a part in segment k hangs on, the innermost first
        for k, yk in enumerate(cuts):
            seg = keep(keep(airframe, (0, side, 0), (0, side * yk, 0)), (0, -side, 0), (0, side * ends[k + 1], 0))
            if seg is None:
                continue
            if ya - 1e-6 <= yk < yb - 1e-6:
                name = 'aileron-%s-%d' % (sn, k)
                objs.append(Obj(name, keep(seg, aft, h0), GREY))
                anims.extend(bent(name, k))
                anims.append(dict(obj=name, prop=J + 'ctl/aileron-deg', factor=1.0 if side > 0 else -1.0, a=h0, b=h1, down=side))
                seg = keep(seg, -aft, h0)
            name = 'wing-%s-%d' % (sn, k)
            objs.append(Obj(name, seg))
            anims.extend(bent(name, k))
        core = keep(core, (0, -side, 0), (0, side * cuts[0], 0))
        # spoiler plates sitting on the upper skin, one to each segment they lie over
        s0, s1 = SPOILER['inner'] * HALF, SPOILER['outer'] * HALF
        stations = [s0] + [c for c in cuts if s0 < c < s1] + [s1]
        for n in range(len(stations) - 1):
            cs = []
            for y, fr in ((stations[n], SPOILER['front']), (stations[n + 1], SPOILER['front']), (stations[n + 1], SPOILER['back']), (stations[n], SPOILER['back'])):
                le, te, _ = chord_at(airframe, side * y)
                x = le + fr * (te - le)
                sec = np.asarray(airframe.section(plane_origin=[0, side * y, 0], plane_normal=[0, 1, 0]).vertices)
                top = sec[(np.abs(sec[:, 0] - x) < 0.12 * (te - le)) & (sec[:, 2] < G['wing']['z'] + 1.5)]
                cs.append((x, side * y, top[:, 2].max() + 0.01))
            name = 'spoiler-%s-%d' % (sn, n)
            objs.append(plate(name, cs))
            k = max([i for i, c in enumerate(cuts) if c <= stations[n] + 1e-6], default=-1)
            anims.extend(bent(name, k))
            anims.append(dict(obj=name, prop=J + 'ctl/spoiler-norm', factor=SPOILER['travel_deg'], a=np.array(cs[0]), b=np.array(cs[1]), down=-side))
        # the wing tip's lamps: the navigation light (red on the left, green on the right) and a white strobe behind
        # it, on the tip's own segment so that they ride the bending wing
        tipv = airframe.vertices[airframe.vertices[:, 1] * side > HALF - 0.4]
        at = np.array([np.percentile(tipv[:, 0], 30), side * (HALF + 0.05), tipv[:, 2].mean()])
        for lamp, dx, mat, switch in (('nav', 0.0, GREEN_LIGHT if side > 0 else RED_LIGHT, 'nav'), ('strobe', 0.9, WHITE_LIGHT, 'strobe')):
            name = 'light-%s-%s' % (lamp, sn)
            objs.append(Obj(name, trimesh.creation.icosphere(subdivisions=1, radius=0.13).apply_translation(at + [dx, 0, 0]), mat))
            anims.extend(bent(name, len(cuts) - 1))
            anims.append(dict(obj=name, select=L + switch, a=np.zeros(3), b=np.ones(3)))
    # the V-tail's ruddervators, cut out of what is left
    t = G['vtail']
    d = math.radians(t['dihedral_deg'])
    v = core.vertices
    for side, sn in ((1, 'right'), (-1, 'left')):
        span_dir = np.array([0.0, side * math.cos(d), math.sin(d)])
        normal = np.array([0.0, -side * math.sin(d), math.cos(d)])
        panel = (v[:, 0] > 0.80 * G['fuselage']['length']) & (v[:, 1] * side > 2.3) & (v[:, 2] > 7.0 * KZ)
        pv = v[panel]
        s = pv @ span_dir
        s0, s1 = np.percentile(s, 4), s.max()
        root_pt = pv[np.argmin(np.abs(s - s0))]
        # hinge points near the root and the tip of the panel
        pts = []
        for sv in (s0 + 0.08 * (s1 - s0), s1 - 0.08 * (s1 - s0)):
            sec = np.asarray(core.section(plane_origin=span_dir * sv, plane_normal=span_dir).vertices)
            sec = sec[(sec[:, 0] > 0.80 * G['fuselage']['length']) & (np.abs((sec - pv.mean(axis=0)) @ normal) < 0.7)]
            le, te = sec[:, 0].min(), sec[:, 0].max()
            mid = sec.mean(axis=0)
            pts.append(np.array([le + (1 - RUDDERVATOR['chord']) * (te - le), mid[1], mid[2]]))
        h0, h1 = pts
        along = (h1 - h0) / np.linalg.norm(h1 - h0)
        aft = np.cross(normal, along)
        aft /= np.linalg.norm(aft)
        if aft[0] < 0:
            aft = -aft
        mid_plane = pv.mean(axis=0)
        slab = keep(keep(core, normal, mid_plane - 0.7 * normal), -normal, mid_plane + 0.7 * normal)     # the panel's own slab: not the nacelle beside it
        slab = keep(keep(slab, span_dir, h0 - 0.5 * span_dir), (1, 0, 0), (0.80 * G['fuselage']['length'], 0, 0))
        rv = keep(slab, aft, h0)
        if rv is None:
            continue
        # take the same piece out of the core: what is ahead of the hinge, or outside the slab
        ahead = keep(core, -aft, h0)
        behind = keep(core, aft, h0)
        rest = [ahead]
        for nrm, org in ((-normal, mid_plane - 0.7 * normal), (normal, mid_plane + 0.7 * normal), (-span_dir, h0 - 0.5 * span_dir), ((-1, 0, 0), (0.80 * G['fuselage']['length'], 0, 0))):
            piece = keep(behind, nrm, org)
            if piece is not None:
                rest.append(piece)
            behind = keep(behind, -np.asarray(nrm, float), org)
            if behind is None:
                break
        core = trimesh.util.concatenate([r for r in rest if r is not None])
        v = core.vertices
        objs.append(Obj('ruddervator-%s' % sn, rv, GREY))
        anims.append(dict(obj='ruddervator-%s' % sn, expr=(J + 'ctl/pitch-deg', J + 'ctl/yaw-deg', 1.0 if side < 0 else -1.0), a=h0, b=h1, down=side))
    # The nose gear's doors: cut out of the belly's own skin, so that closed they ARE the fuselage. Two of them, either
    # side of the centreline, each hinged along its outer edge and swinging down to hang open. (NASA's model has two
    # flat plates there instead, taller than half the bay's width: closed, they stood out of the curved belly, and
    # swung shut they passed through each other.) A dark well behind them, for the leg to fold into.
    x0, x1, hw = NOSE_BAY
    nose_doors = {}
    for sd, nm in ((1.0, 'right'), (-1.0, 'left')):
        door, core = cut_out(core, [((1, 0, 0), (x0, 0, 0)), ((-1, 0, 0), (x1, 0, 0)), ((0, sd, 0), (0, 0, 0)), ((0, -sd, 0), (0, sd * hw, 0)), ((0, 0, -1), (0, 0, 4.3 * KZ))])
        nose_doors[nm] = door
    # NASA's two Global Hawks are white with one thin dark blue stripe along each side of the fuselage from the nose
    # to the tail, about where the wing's underside meets it (NASA's photograph of 871 and 872 on the Dryden ramp, "in
    # their blue-and-white paint scheme"). It is cut out of the skin as a band between two heights. No insignia and
    # no lettering are drawn (NASA's are not to be used).
    sz0, sz1, sx0, sx1 = STRIPE
    stripe, core = cut_out(core, [((0, 0, 1), (0, 0, sz0)), ((0, 0, -1), (0, 0, sz1)), ((1, 0, 0), (sx0, 0, 0)), ((-1, 0, 0), (sx1, 0, 0))])
    objs.insert(0, Obj('airframe', core))
    if stripe is not None:
        objs.append(Obj('stripe', stripe, BLUE))
    # the white tail light at the fuselage's end, and red beacons on top of the nacelle and under the belly
    fv = core.vertices[np.abs(core.vertices[:, 1]) < 0.6]
    tail = fv[np.argmax(fv[:, 0])]
    top = fv[(fv[:, 0] > 29.0) & (fv[:, 0] < 31.0)]
    under = fv[(fv[:, 0] > 13.0) & (fv[:, 0] < 15.0)]
    for name, at, mat, switch in (('light-tail', tail + [0.05, 0, 0], WHITE_LIGHT, 'nav'), ('light-beacon-top', [30.0, 0.0, top[:, 2].max() + 0.05], RED_LIGHT, 'beacon'),
                                  ('light-beacon-under', [14.0, 0.0, under[:, 2].min() - 0.05], RED_LIGHT, 'beacon')):
        objs.append(Obj(name, trimesh.creation.icosphere(subdivisions=1, radius=0.13).apply_translation(np.asarray(at, float)), mat))
        anims.append(dict(obj=name, select=L + switch, a=np.zeros(3), b=np.ones(3)))
    zb = max(d.vertices[:, 2].max() for d in nose_doors.values())          # above the doors' highest edge: the belly is curved, and a well that began lower stood out of it at the sides
    wv = np.array([(x, y, z) for z in (zb + 0.05, zb + 2.5) for x, y in ((x0, -hw), (x1, -hw), (x1, hw), (x0, hw))]) * [1, 0.97, 1]
    wf = [(4, 5, 6), (4, 6, 7)] + [t for k in range(4) for t in ((k, (k + 1) % 4, 4 + (k + 1) % 4), (k, 4 + (k + 1) % 4, 4 + k))]
    objs.append(Obj('nose-gear-well', trimesh.Trimesh(wv, np.array(wf), process=False), DARK))
    # everything else: small fixed things, and the gear in three legs
    legs = {'gear-nose': [], 'gear-left': [], 'gear-right': []}
    fixed = []
    for i, b in bodies:
        if b is merged:
            continue
        c = b.bounds.mean(axis=0)
        if i == 0 and c[2] > 6.0 * KZ:
            fixed.append(b)                                         # aerials and the like on top
        elif c[0] < 16.0:
            legs['gear-nose'].append((i, b))
        elif c[1] < 0:
            legs['gear-left'].append((i, b))
        else:
            legs['gear-right'].append((i, b))
    # the fan, seen down the intake: NASA's model has it, as a spinner and a ring of blades in many small pieces.
    # They are gathered into one object that turns about the ring's own centre
    def in_fan(b):
        lo, hi = b.bounds
        return lo[0] > 26.0 and hi[0] < 27.8 and abs(lo[1]) < 2.3 and abs(hi[1]) < 2.3 and lo[2] > 7.5 * KZ and hi[2] < 11.3 * KZ
    fan = [b for b in fixed if in_fan(b)]
    if fan:
        fixed = [b for b in fixed if not in_fan(b)]
        # NASA's engine sits nose-up in the nacelle: the blade ring is tilted 15 deg from the fuselage's axis, and
        # the spinner in front of it is not on the ring's centre line. Each turns about its own axis: the ring (with
        # its loose blades) about its own normal through its centre, the spinner about a parallel line through its
        # own centre. (Turned about the fuselage's axis they wobbled.)
        ring = max(fan, key=lambda b: np.ptp(b.bounds[:, 1]))
        rc = ring.vertices.mean(axis=0)
        # squashed in height with the rest, the fan would be an oval and wobble as it turns: it is drawn in by the
        # same amount fore-and-aft and sideways about the ring's centre, so it is round again (6 % smaller)
        def round_again(b):
            v = b.vertices.copy()
            v[:, :2] = rc[:2] + (v[:, :2] - rc[:2]) * KZ
            return trimesh.Trimesh(v, b.faces, process=False)
        fan = [round_again(b) for b in fan]
        ring = max(fan, key=lambda b: np.ptp(b.bounds[:, 1]))
        ring_is = ring
        normal = np.linalg.svd(ring.vertices - rc)[2][2]
        normal = normal * np.sign(normal[0])
        hubs = [b for b in fan if len(b.faces) > 100 and b is not ring]
        blades = [b for b in fan if b not in hubs]
        # NASA's blade ring is not a circle: it is an oval, 2.08 ft to the sides and 1.73 ft up and down, to fill its
        # oval intake. An oval turning shows its tips going in and out. (At NASA's size the tips were buried in the
        # intake's wall and it was not seen; drawn in 6 % it was.) The blades are narrowed sideways to a circle of
        # the oval's lesser radius, and a dark oval plate behind them fills the intake to its wall.
        up = np.cross(normal, [0.0, 1.0, 0.0])
        up /= np.linalg.norm(up)
        bv = np.vstack([b.vertices for b in blades]) - rc
        r_up, r_side = np.abs(bv @ up).max(), np.abs(bv[:, 1]).max()
        def narrowed(b):
            v = b.vertices.copy()
            v[:, 1] = rc[1] + (v[:, 1] - rc[1]) * r_up / r_side
            return trimesh.Trimesh(v, b.faces, process=False)
        blades = [narrowed(b) for b in blades]
        back = rc + normal * 0.22
        ring_pts = [back + up * (1.05 * r_up * math.sin(t)) + np.array([0.0, 1.0, 0.0]) * (1.05 * r_side / KZ * math.cos(t)) for t in np.linspace(0, 2 * math.pi, 37)[:-1]]
        objs.append(Obj('fan-backing', trimesh.Trimesh(np.vstack([back] + ring_pts), np.array([(0, 1 + k, 1 + (k + 1) % 36) for k in range(36)]), process=False), DARK))
        for name, group in (('fan', blades), ('fan-spinner', hubs)):
            if not group:
                continue
            mesh = trimesh.util.concatenate(group)
            c = rc if name == 'fan' else mesh.vertices.mean(axis=0)
            objs.append(Obj(name, mesh, DARK))
            anims.append(dict(obj=name, spin=J + 'engine/fan-rpm', a=c, b=c + normal))
    if turbine:
        # The low-pressure turbine is on the fan's shaft: it turns at the fan's speed, about the duct's axis.
        # Where NASA's model has the disc, it does not fit the nacelle's own duct: the duct is a little oval and
        # lower, and its mouth is cut on the slant, so the disc's top stood out through the lip and its sides stood
        # clear of the wall. It is moved forward to DISC_X, well inside, and made the size of the duct there: centred
        # in the duct's section, as wide as the duct's narrower way less a finger's clearance.
        disc = trimesh.util.concatenate(turbine)
        sec = airframe.section(plane_origin=[DISC_X, 0, 0], plane_normal=[1, 0, 0])
        loop = next(np.array(e) for e in sec.discrete if abs(np.array(e)[:, 1].mean()) < 0.5 and 8.5 * KZ < np.array(e)[:, 2].mean() < 10.5 * KZ and np.ptp(np.array(e)[:, 1]) < 4.5)
        lo, hi = loop.min(axis=0), loop.max(axis=0)
        c = np.array([DISC_X, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2])
        radius = 0.97 * min(hi[1] - lo[1], hi[2] - lo[2]) / 2
        old = np.array([sum(NOZZLE['x']) / 2, NOZZLE['y'], NOZZLE['z']])
        was = np.hypot(disc.vertices[:, 1] - old[1], disc.vertices[:, 2] - old[2]).max()
        v = disc.vertices - old
        v[:, 1:] *= radius / was
        disc = trimesh.Trimesh(v + c, disc.faces, process=False)
        objs.append(Obj('turbine', disc, DARK))
        # The inside of a real nozzle is dark (soot, shadow): seen from behind the aircraft it is a plain dark round
        # hole. A dark lining is laid just inside the duct's wall from the disc back to the mouth: rings cut from the
        # skin's own duct, drawn in by 2 %.
        rings = []
        for x in np.linspace(DISC_X - 0.3, 39.9, 10):
            sec = airframe.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
            loops = [np.array(e) for e in sec.discrete if abs(np.array(e)[:, 1].mean()) < 0.5 and 8.5 * KZ < np.array(e)[:, 2].mean() < 10.5 * KZ and np.ptp(np.array(e)[:, 1]) < 4.5]
            if not loops:
                continue
            lp = loops[0]
            cc = (lp.min(axis=0) + lp.max(axis=0)) / 2
            ang = np.arctan2(lp[:, 2] - cc[2], lp[:, 1] - cc[1])
            rad = np.hypot(lp[:, 1] - cc[1], lp[:, 2] - cc[2])
            order = np.argsort(ang)
            want = np.linspace(-math.pi, math.pi, 49)[:-1]
            rr = np.interp(want, ang[order], rad[order], period=2 * math.pi) * 0.98
            rings.append(np.c_[np.full(48, x), cc[1] + rr * np.cos(want), cc[2] + rr * np.sin(want)])
        if len(rings) > 1:
            lv = np.vstack(rings)
            lf = []
            for i in range(len(rings) - 1):
                for k in range(48):
                    a0, a1, b0, b1 = i * 48 + k, i * 48 + (k + 1) % 48, (i + 1) * 48 + k, (i + 1) * 48 + (k + 1) % 48
                    lf += [(a0, a1, b1), (a0, b1, b0)]
            objs.append(Obj('nozzle-lining', trimesh.Trimesh(lv, np.array(lf), process=False), DARK))
        anims.append(dict(obj='turbine', spin=J + 'engine/fan-rpm', a=c, b=c + [1.0, 0.0, 0.0]))
    G_ = np.linspace(0.0, 1.0, 21)                      # gear-pos-norm: 0 up, 1 down
    DOORS = 0.25                                        # the doors move over this first part of the travel, the legs over the rest
    leg_frac = np.clip((G_ - DOORS) / (1 - DOORS), 0.0, 1.0)        # 0 folded, 1 down
    door_frac = np.clip(G_ / DOORS, 0.0, 1.0)                       # 0 closed, 1 open

    def table(deg):
        return [(float(g), float(d)) for g, d in zip(G_, deg)]

    def add(name, mesh, mat, rotations, hide_up=0):          # nothing is hidden: what folds away has to fit where it goes
        """An object and its rotations. Where there are two, FlightGear applies the LAST one listed nearest the object
        and the first one outermost (in the F-16's model a wheel's spin comes after its leg's retraction). So a part
        carried by the leg lists the leg's rotation first and its own after it."""
        objs.append(Obj(name, mesh, mat))
        for tab, a, b in rotations:
            anims.append(dict(obj=name, table=tab, a=np.asarray(a, float), b=np.asarray(b, float)))
        if hide_up:
            anims.append(dict(obj=name, hide_up=hide_up, a=np.zeros(3), b=np.ones(3)))

    for name, pieces in legs.items():
        # NASA's parts: 1 struts, axles and hubs; 2 tyres; 3 the mains' side braces; 4 door plates; 5 the nose wheel's hubs
        tyres = [b for i, b in pieces if i == 2]
        plates = [b for i, b in pieces if i == 4]
        metal = [b for i, b in pieces if i in (1, 5)]
        braces = [b for i, b in pieces if i == 3]
        fixed += [b for i, b in pieces if i == 0]                                                 # a plate on the belly by the nose gear: part of the skin
        struts = [b for i, b in pieces if i == 1]
        xaxis = np.array([1.0, 0.0, 0.0])
        if 'nose' in name:
            # NASA's nose leg has wheels but no strut: it turns about a point up in the bay, forward and up into the
            # well. NASA's two flat door plates are not used (see the doors cut from the belly, above)
            allt = np.vstack([b.vertices for b in tyres])
            pivot = np.array([allt[:, 0].mean(), 0.0, 4.3 * KZ])
            leg = (table(96.0 * (1 - leg_frac)), pivot, pivot + [0.0, 1.0, 0.0])        # a little past level, so the wheel clears the belly's skin ahead of the bay
            for suffix, group, mat in (('', metal, GREY), ('-tyres', tyres, TYRE)):
                if group:
                    add(name + suffix, trimesh.util.concatenate(group), mat, [leg])
            for nm, door in nose_doors.items():
                sd = 1.0 if nm == 'right' else -1.0
                edge = door.vertices[np.abs(np.abs(door.vertices[:, 1]) - NOSE_BAY[2]) < 0.03]
                h0, h1 = edge[np.argmin(edge[:, 0])], edge[np.argmax(edge[:, 0])]
                # open, each hangs straight down from its hinge on the bay's outer edge
                add('%s-door-%s' % (name, nm), door, WHITE, [(table(90.0 * sd * door_frac), h0, h1)], hide_up=0)
            continue
        side = 1.0 if 'right' in name else -1.0
        # The main legs are moved MAIN_OUT further from the fuselage than NASA's model has them. Where it has them, a
        # leg folded inboard put its tyres 0.45 ft into the fuselage's side. (The model's gear track was never a
        # measured figure: it is the model's own, at the scale that gives the right length.) The brace is lengthened
        # to reach.
        def moved(b, k=1.0):
            v = b.vertices.copy()
            v[:, 1] += side * MAIN_OUT * k
            return trimesh.Trimesh(v, b.faces, process=False)
        metal, tyres, struts = [moved(b) for b in metal], [moved(b) for b in tyres], [moved(b) for b in struts]
        if braces:
            br0 = trimesh.util.concatenate(braces)
            yin, yout = np.abs(br0.vertices[:, 1]).min(), np.abs(br0.vertices[:, 1]).max()
            v = br0.vertices.copy()
            v[:, 1] = side * (yin + (np.abs(v[:, 1]) - yin) * (yout + MAIN_OUT - yin) / (yout - yin))
            braces = [trimesh.Trimesh(v, br0.faces, process=False)]
        strut = max(struts, key=lambda b: np.ptp(b.bounds[:, 2]))                                 # the tallest piece: the leg itself
        c = strut.bounds.mean(axis=0)
        pivot = np.array([c[0], c[1], strut.bounds[1][2]])
        # the leg swings inboard and up about its own top, to lie in the fairing under the wing root
        theta = -88.0 * side * (1 - leg_frac)
        leg = (table(theta), pivot, pivot + xaxis)
        # NASA's door plate, which hangs beside each main leg, is not used: the fairing has its own doors, and the
        # plate, taken up with the leg, came out through the fairing's underside
        for suffix, group, mat in (('', metal, GREY), ('-tyres', tyres, TYRE)):
            if group:
                add(name + suffix, trimesh.util.concatenate(group), mat, [leg])
        # the fairing, and its two doors: fore and aft halves of the opening, hinged on its fore and aft edges
        shell, bay = gear_fairing(side)
        objs.append(Obj(name + '-fairing', shell, WHITE))
        mid = sum(BAY_X) / 2
        for half, xe, sgn in (('fore', BAY_X[0], 1.0), ('aft', BAY_X[1], -1.0)):
            part = keep(bay, (-sgn, 0, 0), (mid, 0, 0))
            edge = part.vertices[np.abs(part.vertices[:, 0] - (part.vertices[:, 0].min() if sgn > 0 else part.vertices[:, 0].max())) < 0.05]
            h0, h1 = edge[np.argmin(np.abs(edge[:, 1]))], edge[np.argmax(np.abs(edge[:, 1]))]
            # the fore door swings forward and down about a spanwise hinge, the aft one aft and down
            add('%s-bay-door-%s' % (name, half), part, WHITE, [(table(80.0 * sgn * side * door_frac), h0, h1)], hide_up=0)
        if braces:
            # The side brace runs from the fuselage to the leg. It is cut in two, and the two parts fold like a knee
            # as the leg comes up: the inner part turns about its end on the fuselage, the outer part about its end
            # on the leg (and goes round with the leg). The knee's place at each stage is where two circles meet: one
            # about the fuselage end, one about the leg end. The cut is at KNEE of the length from the fuselage, not
            # the middle: with a short inner part the knee swings in and up INTO the fuselage, and the folded brace
            # lies inside the fuselage and the fairing. (Cut in the middle, the knee stood 2 ft up through the wing.)
            br = trimesh.util.concatenate(braces)
            v = br.vertices
            inner_end = v[np.argmin(np.abs(v[:, 1]))]
            outer_end = v[np.argmax(np.abs(v[:, 1]))]
            F = np.array([inner_end[1], inner_end[2]]) * [side, 1]          # worked in the right-hand side's (y, z)
            A0 = np.array([outer_end[1], outer_end[2]]) * [side, 1]
            P = np.array([pivot[1] * side, pivot[2]])
            K0 = F + (A0 - F) * KNEE
            l1, l2 = np.linalg.norm(K0 - F), np.linalg.norm(A0 - K0)
            ang = lambda d: math.degrees(math.atan2(d[1], d[0]))
            alpha, beta = [], []
            for fr in leg_frac:
                th = math.radians(-88.0 * (1 - fr))
                R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
                A = P + R @ (A0 - P)
                d = float(np.clip(np.linalg.norm(A - F), abs(l1 - l2) + 1e-6, l1 + l2 - 1e-6))
                u = (A - F) / max(np.linalg.norm(A - F), 1e-9)
                along_fa = (l1 ** 2 - l2 ** 2 + d ** 2) / (2 * d)                # may be negative: the knee passes inboard of the fuselage end
                h = math.sqrt(max(l1 ** 2 - along_fa ** 2, 0.0))
                perp = np.array([-u[1], u[0]])
                K = F + u * along_fa + perp * h if (perp * h)[1] > 0 else F + u * along_fa - perp * h      # the knee goes up
                alpha.append(ang(K - F) - ang(K0 - F))
                beta.append(ang(K - A) - ang(K0 - A0) - math.degrees(th))
            unwrap = lambda a: np.degrees(np.unwrap(np.radians(a[::-1])))[::-1]                   # no jumps of 360 deg; zero with the gear down
            alpha, beta = unwrap(np.array(alpha)), unwrap(np.array(beta))
            mid3 = inner_end + (outer_end - inner_end) * KNEE
            along = (outer_end - inner_end) / np.linalg.norm(outer_end - inner_end)
            add(name + '-brace-inner', keep(br, -along, mid3), GREY, [(table(alpha * side), inner_end, inner_end + xaxis)])
            add(name + '-brace-outer', keep(br, along, mid3), GREY, [leg, (table(beta * side), outer_end, outer_end + xaxis)])
    if fixed:
        objs.append(Obj('details', trimesh.util.concatenate(fixed), WHITE))        # aerials and the like: the skin's colour
    return objs, anims, airframe


def write(objs, anims):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'GlobalHawk.ac'), 'w') as fh:
        fh.write('AC3Db\n')
        for rgb, name, spec in (((0.94, 0.94, 0.95), 'white', 0.25), ((0.80, 0.82, 0.84), 'grey', 0.25), ((0.20, 0.21, 0.23), 'dark', 0.1), ((0.05, 0.05, 0.05), 'tyre', 0.02), ((1.0, 0.05, 0.05), 'red lamp', 1.0), ((0.05, 1.0, 0.15), 'green lamp', 1.0), ((1.0, 1.0, 1.0), 'white lamp', 1.0), ((0.05, 0.16, 0.42), 'blue', 0.25)):
            emis = rgb if 'lamp' in name else (0, 0, 0)
            fh.write('MATERIAL "%s" rgb %g %g %g  amb %g %g %g  emis %g %g %g  spec %g %g %g  shi 30  trans 0\n' % ((name,) + rgb + rgb + emis + (spec, spec, spec)))
        fh.write('OBJECT world\nkids %d\n' % len(objs))
        for o in objs:
            o.write(fh)
    x = ['<?xml version="1.0"?>',
         '<!-- Generated by fdm/mkmodel.py from NASA\'s 3-D model of the Global Hawk (NASA 3D Resources), scaled to the published',
         '     length and with the wing stretched to the published span and area. Shape courtesy of NASA; no endorsement implied. -->',
         '<PropertyList>', ' <path>GlobalHawk.ac</path>']
    hidden = []
    for a in anims:
        p0, p1 = a['a'] * FT, a['b'] * FT
        axis = '  <axis><x1-m>%.4f</x1-m><y1-m>%.4f</y1-m><z1-m>%.4f</z1-m><x2-m>%.4f</x2-m><y2-m>%.4f</y2-m><z2-m>%.4f</z2-m></axis></animation>' % (
            p0[0], p0[1], p0[2], p1[0], p1[1], p1[2])
        if a.get('hide_up'):
            hidden.append((a['obj'], a['hide_up']))
            continue
        if a.get('select'):
            x.append(' <animation><type>select</type><object-name>%s</object-name><condition><property>%s</property></condition></animation>' % (a['obj'], a['select']))
            continue
        if a.get('spin'):
            # drawn slowed (see SHOWN); the property itself keeps the real speed
            x.append(' <animation><type>spin</type><object-name>%s</object-name><property>%s</property><factor>%g</factor>' % (a['obj'], a['spin'], SHOWN[a['obj']]))
            x.append(axis)
            continue
        x.append(' <animation><type>rotate</type><object-name>%s</object-name>' % a['obj'])
        if 'table' in a:
            # gear-pos-norm is 1 with the gear down and 0 with it up
            x.append('  <property>%sgear/gear-pos-norm</property><interpolation>%s</interpolation>' % (
                J, ''.join('<entry><ind>%.2f</ind><dep>%.2f</dep></entry>' % e for e in a['table'])))
        elif 'expr' in a:
            pitch, yaw, sign = a['expr']
            x.append('  <expression><product><value>%g</value><sum><property>%s</property><product><value>%g</value><property>%s</property></product></sum></product></expression>' % (a['down'], pitch, sign, yaw))
        else:
            x.append('  <property>%s</property><factor>%g</factor>' % (a['prop'], a['factor'] * a['down']))
        x.append(axis)
    for limit in sorted(set(h[1] for h in hidden)):
        # not drawn with the gear up: the legs lie inside the closed fairings (the nose leg inside the belly)
        x.append(' <animation><type>select</type>' + ''.join('<object-name>%s</object-name>' % n for n, l in hidden if l == limit))
        x.append('  <condition><greater-than><property>%sgear/gear-pos-norm</property><value>%g</value></greater-than></condition></animation>' % (J, limit))
    x.append('</PropertyList>')
    open(os.path.join(OUT, 'GlobalHawk.xml'), 'w').write('\n'.join(x) + '\n')


def test(objs, anims, airframe):
    v = np.vstack([o.mesh.vertices for o in objs])
    span, length, height = np.ptp(v[:, 1]), np.ptp(v[:, 0]), v[:, 2].max()
    # the wing's area from its outline in plan: chords at stations along the half span
    ys = np.linspace(SIDE + 0.5, HALF - 0.3, 60)
    ch = [chord_at(airframe, y) for y in ys]
    area = 2 * np.trapezoid([c[1] - c[0] for c in ch], ys)
    fus = airframe.vertices[(np.abs(airframe.vertices[:, 1]) < SIDE) & (airframe.vertices[:, 0] < 15)]
    rows = [('span', span, G['wing']['span'], 0.01), ('length', length, G['fuselage']['length'], 0.01),
            ('wing area outboard of the fuselage side', area, None, 0), ('  (the reference area, which counts the part inside the fuselage)', G['wing']['area_reference'], None, 0), ('fuselage width ahead of the wing', np.ptp(fus[:, 1]), None, 0),
            ('height (the tail tips)', height, None, 0), ('lowest point (the tyres)', v[:, 2].min(), 0.0, 0.01)]
    ok = True
    for name, got, want, tol in rows:
        if want is None:
            print('  %-42s %7.2f' % (name, got))
            continue
        good = abs(got - want) <= max(tol * abs(want), 0.15)
        ok &= good
        print('  %-42s %7.2f, published %7.2f  %s' % (name, got, want, 'pass' if good else 'MISS'))
    names = {o.name for o in objs}
    need = ['aileron-left-4', 'aileron-right-4', 'ruddervator-left', 'ruddervator-right', 'spoiler-left-0', 'spoiler-right-0', 'wing-left-0', 'wing-right-8', 'gear-nose-tyres', 'gear-left', 'gear-right', 'gear-left-tyres',
            'gear-left-bay-door-fore', 'gear-right-bay-door-aft', 'gear-left-brace-inner', 'gear-right-brace-outer', 'gear-nose-door-left', 'gear-nose-door-right']
    missing = [n for n in need if n not in names]
    ok &= not missing and all(a['obj'] in names for a in anims)
    for n in need[:4]:
        m = next(o.mesh for o in objs if o.name == n)
        print('  %-42s %5d faces, %.1f sq ft in plan' % (n, len(m.faces), m.area / 2))
    print('  %d objects, %d vertices, %d faces; moving parts missing: %s' % (len(objs), len(v), sum(len(o.mesh.faces) for o in objs), missing or 'none'))
    return ok


if __name__ == '__main__':
    objs, anims, airframe = build()
    write(objs, anims)
    print('wrote GlobalHawk/Models/GlobalHawk.ac and GlobalHawk.xml')
    raise SystemExit(0 if test(objs, anims, airframe) else 1)
