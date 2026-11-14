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
- the gear's pieces are grouped into three legs that fold away inside the airframe (nothing is hidden: the mains fold about an axis in the wing root, the plate beside each leg goes with its
  strut, and doors cut from the skin close over them). How the real gear folds is not in our sources: the mains swing inboard (their braces run inboard), the nose leg forward. Assumed.
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
# The materials for FlightGear's HDR pipeline, physically based: (base colour in linear light or None for a picture's own,
# metallic, roughness), and the objects each is on by the start of their names. The .ac file's own materials stay for
# the older pipelines. Values are the usual ones for each stuff; none is measured from the aircraft.
EFFECTS = {
    'paint': ((0.86, 0.86, 0.88), 0.0, 0.35, ('airframe', 'wing-', 'aileron-', 'ruddervator-', 'spoiler-', 'details', 'gear-plate-left', 'gear-plate-right', 'gear-main-door-left', 'gear-main-door-right', 'gear-nose-door')),          # gloss white polyurethane
    'blue': ((0.055, 0.21, 0.52), 0.0, 0.35, ('stripe',)),                                                             # FlightGear's blue, as paint
    'yellow': ((0.96, 0.97, 0.06), 0.0, 0.35, ('stripe-pin',)),
    'marking': (None, 0.0, 0.60, ('cockade-', 'serial-')),                                                             # the Finnish livery's cockade and serial: their pictures
    'badge': (None, 0.0, 0.40, ('insignia-',)),                                                                         # the painted badge: its picture
    'steel': ((0.77, 0.78, 0.80), 1.0, 0.30, ('gear-nose', 'gear-left', 'gear-right')),                                 # the legs, axles, hubs and braces: bare machined alloy steel
    'rubber': ((0.02, 0.02, 0.02), 0.0, 0.85, ('gear-nose-tyres', 'gear-left-tyres', 'gear-right-tyres')),
    'titanium': ((0.54, 0.50, 0.47), 1.0, 0.35, ('fan',)),                                                              # the fan's blades
    'spinner': ((0.05, 0.05, 0.06), 0.0, 0.40, ('fan-spinner',)),                                                       # dark painted
    'black': ((0.01, 0.01, 0.01), 0.0, 1.0, ('fan-backing',)),
    'hot': ((0.20, 0.18, 0.17), 1.0, 0.60, ('turbine',)),                                                               # heat-stained nickel alloy
    'liner': ((0.035, 0.033, 0.032), 0.0, 0.90, ('nozzle-lining',)),                                                    # the nozzle's lining, heat-blackened and matte (as bare metal it glared white in the sun)
    'primer': ((0.10, 0.11, 0.09), 0.0, 0.90, ('nose-gear-well', 'main-gear-well')),
}


# The liveries (docs/PLAN.md, "Liveries"): FlightGear's livery selector (aircraft.livery, as in the UH-60 and the Bo 105) copies one of these files' properties into sim/model/livery, and a pbr animation on
# every object painted with the 'paint', 'blue' or 'yellow' effect reads that paint's base colour (linear light) and roughness from there: the airframe's own paint, the livery stripe and its pin. The
# first livery, the white one the aircraft has always had, is the default: its colours are EFFECTS'. The second is the dark grey of the military aircraft, low gloss, the stripe and its pin the colour of
# the skin (the stripe is cut out of the skin, so it cannot be hidden without a slit; the badge stays).
LIVERIES = (
    dict(file='default', name='White', index=1, paint=(EFFECTS['paint'][0], EFFECTS['paint'][2]), stripe=(EFFECTS['blue'][0], EFFECTS['blue'][2]), pin=(EFFECTS['yellow'][0], EFFECTS['yellow'][2]), fan=(EFFECTS['titanium'][0], EFFECTS['titanium'][2]), spinner=(EFFECTS['spinner'][0], EFFECTS['spinner'][2]), markings=False),
    dict(file='military', name='Dark grey (military)', index=2, paint=((0.058, 0.064, 0.072), 0.90), stripe=((0.058, 0.064, 0.072), 0.90), pin=((0.058, 0.064, 0.072), 0.90), fan=(EFFECTS['titanium'][0], EFFECTS['titanium'][2]), spinner=(EFFECTS['spinner'][0], EFFECTS['spinner'][2]), markings=False),
    # the Finnish Air Force's grey (the Hornets'; linear light: sRGB about 108, 116, 124), matte, with the cockade and the serial GH-601 (a made-up aircraft and number: fdm/mkmarkings.py); the fan's blades a muted
    # steel blue instead of the bare titanium that shines white in the sun, and the spinner (the disc in the middle) a matte dark steel blue instead of the dark paint that glints beige
    dict(file='finnish', name='Finnish Air Force (GH-601)', index=3, paint=((0.153, 0.177, 0.205), 0.85), stripe=((0.153, 0.177, 0.205), 0.85), pin=((0.153, 0.177, 0.205), 0.85), fan=((0.12, 0.16, 0.22), 0.80), spinner=((0.08, 0.11, 0.16), 0.90), markings=True),
)
LIVERY_PBR = {'paint': 'paint', 'blue': 'stripe', 'yellow': 'pin', 'titanium': 'fan', 'spinner': 'spinner'}       # effect -> the livery's property group (sim/model/livery/<group>/red, green, blue, roughness)


def effect_of(name):
    """the material an object wears: the longest of the name beginnings that fits"""
    best = None
    for eff, (_, _, _, starts) in EFFECTS.items():
        for st in starts:
            if name.startswith(st) and (best is None or len(st) > best[1]):
                best = (eff, len(st))
    return best[0] if best else None


LAMP_AT = {}                                      # where the lamps are, ft (filled by build; fdm/ghlights.py makes them)
BLUE, YELLOW = 4, 5                              # the stripe: FlightGear's blue, and its yellow under it
INSIGNIA = dict(x=31.0, z=9.0, size=2.3, out=1.75)   # ft: the badge on each side of the nacelle: its centre, its width, and how far from the centreline the skin it is painted on begins
#                                        # the stripe
STRIPE = (4.05, 4.30, 1.0, 40.0)                 # ft: the blue stripe's lower and upper edge and its fore and aft ends
STRIPE_Y = ((1.0, 19.5, 2.95), (19.5, 27.5, 2.76), (27.5, 40.0, 2.95))   # ft: the stripe is on the fuselage's sides only: fore and aft ends of a stretch and how far out from the centreline it may reach. The wing root's lower skin lies at
                                                  # the stripe's height (4.0 to 4.3 ft) and, cut by height alone, was painted blue and yellow out to 9 ft (the user: "what's with the colors here?"): where the wing root joins,
                                                  # from 19.5 to 27.5 ft, the limit is the fuselage wall (2.5 to 2.75 ft there)
MARKINGS = dict(front=6.7, z=5.4, out=1.9,                                  # ft: the Finnish livery's serial and cockade, level with the nose gear's doors' front edge (6.7 ft), the cockade as the serial's next character
                cockade=dict(w=0.85, h=0.85),                                 # 0.85 ft across
                serial=dict(h=0.48))                                          # GH-601 (fdm/mkmarkings.py), its ink 0.48 ft high and, cut tight, as wide as its proportions make it; the cockade stands as far from the 1 as the 0 does
WING_MARK = dict(y=45.5, chord=0.38, d=0.85)      # ft: the Finnish livery's cockade on each wing's lower skin, placed as on the Hornet in the user's photograph, and on the upper skin at the same spot (the user's instruction) (docs/PLAN.md, "Roundels on the Finnish livery's wings"):
                                                  # 77 % of the way from the fuselage to the tip (45.5 ft out, in the hinged segment between the 44 and 50 ft hinges), its centre 38 % of the chord back from the leading edge,
                                                  # the size of the fuselage cockade (0.85 ft)
MAIN_DOOR = (24.0, 26.7, 0.5, 3.0, 4.45, 80.0)     # ft: the main gear's inner door, cut from the fuselage's lower skin each side: fore and aft ends, the hinge (near the centre of the belly) and the
                                              # outer edge (where the wing root's lower skin begins), and the height below which the skin is taken (the belly and the lower side wall up to the wing root)
LEG_SHOWN = 0                                 # nothing is hidden with the gear up: every part folds away to a place inside the fuselage or the wing root, where the skin covers it (the legs once
                                              # vanished when the gear came up to 0.24: they were hidden before the doors shut)
PLATE_IN = 0.12                               # the gear position by which the side plate has straightened against the strut (it starts at 0.25, when the struts are in; the doors, closing over 0.25 to 0, are then about half shut)
LEG_FOLD_DEG = 88.0                          # deg: how far the main legs turn about the fold axis, gear down to gear up (the plate beside each leg is carried by it)
STRUT_ACROSS = 0.55                         # ft: the main strut's width across the aircraft (NASA's mesh: 0.89; the user: "the struts themselves are too thick"). A first value, not from a source:
                                             # no A-model photograph of it has been named (docs/PLAN.md). Its fore-and-aft width, 0.45, is as it was
STRUT_LIFT = 0.10                           # ft: the folded struts and wheels are raised this much over the last of their fold (gear position STRUT_LIFT_FROM down to 0.25), and
STRUT_THIN = 0.55                            # made this fraction as wide across the aircraft: while they are inside the wing root and unseen. Folded, the strut spans z 3.9 to 4.8 ft (0.9 thick) and the
STRUT_LIFT_FROM = 0.35                       # wing root's skins are at 4.0 to 4.3 and 4.75 to 4.95: unthinned its bottom stood through the side plate (at 4.3), and lifted 0.12 its tip stood through the top skin
PLATE_END_X = 26.1                           # ft: the wing root's trailing edge at the plate: NASA's plate reaches 0.6 ft past it, a slab behind the wing when folded, so it is set forward by that
BRACE_TUCK_FROM = 0.40                       # the folded brace, a 0.5 ft stub, points at the leg's end of it until this gear position, then swings (by 0.25) to point BRACE_TUCK_DEG: up and inboard from its
BRACE_TUCK_DEG = 130.0                       # end on the fuselage, which is only 0.2 ft inside the wall, so that the stub lies inside the fuselage (pointing at the leg's end it stood out below the wing root)
PIVOT_Z = 4.9                                 # ft: the height of the axis the main legs fold about, and PIVOT_IN how far inboard of the leg it is: the leg lies along the axis' height less 0.5 ft when
PIVOT_IN = 0.25                               # (0.5 before 2026-11-14: the folded dual wheels' inner edges then lay at 0.7 ft from the centreline and crossed the doors, which hang open there; 0.25 clears them) folded, 4.4 ft, inside the wing root (lower skin 4.0 to 4.3, upper 4.75 to 4.95), and its axle ends 1.0 ft from the centreline, so that the
                                              # dual wheels (0.9 ft either side) lie inside the fuselage (2.5 ft); folded about the strut's own top (4.0 ft) they hung out below the skin and past the side
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
NOSE_OD, NOSE_WIDTH, NOSE_RIM = 18.0 / 12, 6.5 / 12, 8.0 / 12      # ft: the F-5's nose wheel, 18 x 6.5-8 (outer diameter, section width, rim)


def f5_nose_wheel(tyres, hubs, struts):
    """The nose wheel at the F-5's size. Meshes in feet, x aft, y right (the axle's direction), z up. Returns (tyres, metal).
    NASA's hub piece holds the rim (within 0.55 ft of the axle) and a thin arm well above the wheel: only the rim is scaled (to the 8 in
    rim), the arm just moves up with the wheel."""
    cat = trimesh.util.concatenate(tyres)
    lo, hi = cat.bounds
    c = (lo + hi) / 2
    d_now, w_now = hi[2] - lo[2], hi[1] - lo[1]
    k_r, k_w = NOSE_OD / d_now, NOSE_WIDTH / w_now
    lift = lo[2] - (c[2] - NOSE_OD / 2)                                   # puts the new lowest point back where the old one was
    R_SPLIT = 0.55                                                        # ft from the axle: inside, the rim; outside, the arm
    r_all = [np.hypot(b.vertices[:, 0] - c[0], b.vertices[:, 2] - c[2]) for b in hubs]
    rim_r = max([r[r < R_SPLIT].max() for r in r_all if (r < R_SPLIT).any()] or [d_now / 2])
    k_h = (NOSE_RIM / 2) / rim_r

    def scaled(b, kr, kw):
        v = b.vertices.copy()
        v[:, 0] = c[0] + (v[:, 0] - c[0]) * kr
        v[:, 2] = c[2] + (v[:, 2] - c[2]) * kr + lift
        v[:, 1] = c[1] + (v[:, 1] - c[1]) * kw
        return trimesh.Trimesh(v, b.faces, process=False)

    def rim_scaled(b):
        v = b.vertices.copy()
        inner = np.hypot(v[:, 0] - c[0], v[:, 2] - c[2]) < R_SPLIT
        v[inner, 0] = c[0] + (v[inner, 0] - c[0]) * k_h
        v[inner, 2] = c[2] + (v[inner, 2] - c[2]) * k_h
        v[inner, 1] = c[1] + (v[inner, 1] - c[1]) * k_w
        v[:, 2] += lift
        return trimesh.Trimesh(v, b.faces, process=False)

    def lifted(b):
        v = b.vertices.copy()
        v[:, 2] += lift
        return trimesh.Trimesh(v, b.faces, process=False)
    new_t = [scaled(b, k_r, k_w) for b in tyres]
    new_h = [rim_scaled(b) for b in hubs]
    new_s = [lifted(b) for b in struts]
    nb = trimesh.util.concatenate(new_t).bounds
    print('  nose wheel: %.1f in across, %.1f in wide (was %.1f x %.1f); rim %.1f in (was %.1f); lowest point %.3f ft (was %.3f)' % (
        (nb[1][2] - nb[0][2]) * 12, (nb[1][1] - nb[0][1]) * 12, d_now * 12, w_now * 12, NOSE_RIM * 12, 2 * rim_r * 12, nb[0][2], lo[2]), flush=True)
    return new_t, new_h + new_s


def shift_main_leg(pieces):
    """The main leg moved aft to the side drawing's main axle (the flight model's main_x): NASA's mesh, scaled by length, has the legs 2.2 ft too far forward
    (23.1 ft against 25.29; the photograph of N872 from the side agrees with the drawing). The tyres, struts, braces and door plate move together."""
    tyres = [b for i, b in pieces if i == 2]
    if not tyres:
        return pieces
    x_now = float(np.mean([b.bounds.mean(axis=0)[0] for b in tyres]))
    dx = G['gear']['main_x'] - x_now
    out = []
    for i, b in pieces:
        if i in (1, 2, 3, 4, 5):
            v = b.vertices.copy()
            v[:, 0] += dx
            out.append((i, trimesh.Trimesh(v, b.faces, process=False)))
        else:
            out.append((i, b))
    print('  main leg moved aft %.2f ft: wheels now at x %.2f ft (the flight model: %.2f)' % (dx, x_now + dx, G['gear']['main_x']), flush=True)
    return out


def fit_ramps(G, target, n=2):
    """FlightGear's scale animation takes a property, a factor, an offset and limits: no table. A curve of the gear position is made of n of them in a row (their factors multiply):
    each is clamp(a * G + b, m, 1), a ramp from m up to 1. Returns [(m, a, b)] fitted to the target by least worst error."""
    from scipy.optimize import differential_evolution
    G, target = np.asarray(G, float), np.asarray(target, float)

    def model(p):
        out = np.ones_like(G)
        for i in range(n):
            m, g0, w = p[3 * i:3 * i + 3]
            out = out * np.clip(m + (1 - m) * (G - g0) / w, m, 1.0)
        return out
    r = differential_evolution(lambda p: np.max(np.abs(model(p) - target)), [(0.1, 1.0), (0.0, 0.9), (0.1, 1.0)] * n, seed=1, maxiter=400, tol=1e-8, polish=True)
    ramps = []
    for i in range(n):
        m, g0, w = r.x[3 * i:3 * i + 3]
        a = (1 - m) / w
        ramps.append((float(m), float(a), float(m - a * g0)))
    return ramps, float(r.fun)


MAIN_OD, MAIN_WIDTH, MAIN_RIM, MAIN_SPACING = 22.0 / 12, 5.75 / 12, 12.0 / 12, 1.05   # ft: the main tyre, 22 x 5.75-12 (the flight model's and the sounds'), and the dual pair's centre-to-centre spacing (the head-on photograph)


def resize_main_wheels(pieces):
    """One main leg's pieces (index, mesh) with its two tyres made 22 x 5.75-12 and set 1.05 ft apart, the hubs made the 12 in rim, the
    wheels lifted so the lowest point stays, the leg's lower part stretched to meet them. Meshes in feet, x aft, y right, z up.
    NASA's tyres are 16.5 in across and about 4 in wide, 0.61 ft apart. Index 2 is the tyres, 1 the struts, axles and hubs."""
    tyres = [b for i, b in pieces if i == 2]
    if len(tyres) != 2:
        return pieces
    cs = [b.bounds.mean(axis=0) for b in tyres]
    y_leg = 0.5 * (cs[0][1] + cs[1][1])
    d_old = float(np.mean([b.bounds[1][2] - b.bounds[0][2] for b in tyres]))
    w_old = float(np.mean([b.bounds[1][1] - b.bounds[0][1] for b in tyres]))
    k_r, k_w = MAIN_OD / d_old, MAIN_WIDTH / w_old
    lift = (MAIN_OD - d_old) / 2                                        # the tyres' lowest point stays where it was
    axle_old = float(np.mean([c[2] for c in cs]))
    sp_old = abs(cs[0][1] - cs[1][1])
    u_c, u_cn = sp_old / 2, MAIN_SPACING / 2
    u_in, u_out = u_c - w_old / 2, u_c + w_old / 2
    u_inn, u_outn = u_cn - MAIN_WIDTH / 2, u_cn + MAIN_WIDTH / 2
    a = 0.06                                                            # within this of the leg's own centre line nothing moves sideways

    def h(u):                                                           # the sideways map: monotone, piecewise linear
        u = np.asarray(u, float)
        return np.where(u <= a, u, np.where(u < u_in, a + (u - a) * (u_inn - a) / (u_in - a),
                                            np.where(u <= u_out, u_inn + (u - u_in) * k_w, u_outn + (u - u_out))))
    R_SPLIT = 0.55                                                      # ft from an axle: inside, the rim; outside, the leg
    margin = 0.1
    rim_r = 0.0
    for i, b in pieces:
        if i != 1:
            continue
        v = b.vertices
        u = np.abs(v[:, 1] - y_leg)
        for c in cs:
            r = np.hypot(v[:, 0] - c[0], v[:, 2] - c[2])
            k = (r < R_SPLIT) & (u > u_in - margin) & (u < u_out + margin)
            if k.any():
                rim_r = max(rim_r, float(r[k].max()))
    k_h = (MAIN_RIM / 2) / rim_r if rim_r > 0 else k_r

    def transform(b, is_tyre):
        v = b.vertices.copy()
        sgn = np.sign(v[:, 1] - y_leg)
        u = np.abs(v[:, 1] - y_leg)
        z_old = v[:, 2].copy()
        new_z = z_old.copy()
        new_x = v[:, 0].copy()
        if is_tyre:
            c = b.bounds.mean(axis=0)
            new_x = c[0] + (v[:, 0] - c[0]) * k_r
            new_z = c[2] + (z_old - c[2]) * k_r + lift
        else:
            # the leg: below the axle lifted, up to WHEEL_TOP stretched, above it as it was; near an axle the rim, scaled about it
            new_z = np.where(z_old <= axle_old, z_old + lift, np.where(z_old < WHEEL_TOP, z_old + lift * (WHEEL_TOP - z_old) / (WHEEL_TOP - axle_old), z_old))
            for c in cs:
                r = np.hypot(v[:, 0] - c[0], z_old - c[2])
                rim = (r < R_SPLIT) & (u > u_in - margin) & (u < u_out + margin) & (np.sign(v[:, 1] - y_leg) == np.sign(c[1] - y_leg))
                new_x = np.where(rim, c[0] + (v[:, 0] - c[0]) * k_h, new_x)
                new_z = np.where(rim, c[2] + (z_old - c[2]) * k_h + lift, new_z)
        v[:, 0], v[:, 2] = new_x, new_z
        v[:, 1] = y_leg + sgn * h(u)
        return trimesh.Trimesh(v, b.faces, process=False)
    out = [(i, transform(b, i == 2) if i in (1, 2) else b) for i, b in pieces]
    nt = trimesh.util.concatenate([b for i, b in out if i == 2]).bounds
    print('  main wheels: %.1f in across, %.2f in wide each, %.2f ft apart (was %.1f x %.1f, %.2f); rim %.1f in (was %.1f); lowest point %.3f ft' % (
        (nt[1][2] - nt[0][2]) * 12, MAIN_WIDTH * 12, MAIN_SPACING, d_old * 12, w_old * 12, sp_old, MAIN_RIM * 12, 2 * rim_r * 12, nt[0][2]), flush=True)
    return out


TAIL_X = 0.74 * G['fuselage']['length']                                  # ft: aft of this is the tail, not the wing (stretch_wing's own limit)
BEND = (10.0, 16.0, 22.0, 28.0, 38.0, 44.0, 50.0)                 # ft from the centreline: where the bending wing is hinged (and at the aileron's ends)
PODS = 8.0                                                         # ft: outboard of the gear fairings at the wing root; the wing's stretch begins here
ROOT_FILLET_Y = 2.55                                               # ft: from here out the root's trailing-edge fillet is drawn in: the fuselage wall is at 2.4 to 2.5 there, the fillet from 2.6 (it was 2.9, which left
                                                                   # the fillet's inner 20 vertices, up to 1.9 ft aft of the trailing edge, at NASA's size: a lobe of the bigger wing on the fuselage's side)
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
    root = (np.abs(v[:, 1]) > ROOT_FILLET_Y) & (np.abs(v[:, 1]) < PODS) & (v[:, 0] > ROOT_TE_X) & (v[:, 0] < 29.0) & (v[:, 2] > 3.6 * KZ) & (v[:, 2] < 5.6 * KZ)
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


def wing_decal(skin, name, xc, yc, d, zm, up):
    """A picture lying on the wing's upper (up=1) or lower (up=-1) skin: the square (d ft across, centred at xc, yc) of that skin, the half above or below the height zm, is copied 0.02 ft off the skin along
    its own normals and carries the cockade, which is transparent round the marking; the skin under it stays. Returns the decal and the skin."""
    piece, rest = cut_out(skin, [((1, 0, 0), (xc - d / 2, 0, 0)), ((-1, 0, 0), (xc + d / 2, 0, 0)), ((0, 1, 0), (0, yc - d / 2, 0)), ((0, -1, 0), (0, yc + d / 2, 0)), ((0, 0, up), (0, 0, zm))])
    if piece is None:
        return None, skin
    piece = piece.copy()
    piece.merge_vertices()                      # the slicing leaves every triangle its own vertices: lifted along their own normals, neighbours parted in hairline cracks. Shared vertices lift together.
    v = piece.vertices
    uv = np.c_[(v[:, 0] - (xc - d / 2)) / d, (v[:, 1] - (yc - d / 2)) / d]      # the cockade is a disc: it has no up or down
    nrm = np.asarray(piece.vertex_normals).copy()
    if (nrm[:, 2] * up).mean() < 0:
        nrm = -nrm
    return Obj(name, trimesh.Trimesh(v + 0.02 * nrm, piece.faces, process=False), WHITE, 'cockade.png', np.clip(uv, 0.0, 1.0)), trimesh.util.concatenate([rest, piece])


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


class Obj:
    def __init__(self, name, mesh, mat=WHITE, texture=None, uv=None):
        self.name, self.mesh, self.mat = name, mesh, mat
        self.texture, self.uv = texture, uv                 # a picture on it, and each vertex's place in the picture

    def write(self, fh):
        v, f = self.mesh.vertices, self.mesh.faces
        fh.write('OBJECT poly\nname "%s"\n%screase 40.0\nnumvert %d\n' % (self.name, 'texture "%s"\n' % self.texture if self.texture else '', len(v)))
        uv = self.uv if self.uv is not None else np.zeros((len(v), 2))
        for x, y, z in v:
            fh.write('%.4f %.4f %.4f\n' % (x * FT, z * FT, -y * FT))
        fh.write('numsurf %d\n' % len(f))
        for a, b, c in f:
            fh.write('SURF 0x%s\nmat %d\nrefs 3\n%d %.4f %.4f\n%d %.4f %.4f\n%d %.4f %.4f\n' % ('30', self.mat, a, uv[a][0], uv[a][1], b, uv[b][0], uv[b][1], c, uv[c][0], uv[c][1]))   # smooth, and drawn from both sides: NASA's pieces don't all face the same way, and one-sided some vanish   # the blades are single sheets: drawn from both sides
        fh.write('kids 0\n')


def plate(name, corners, thick=0.035, flip=False):
    """A thin plate from four corners (upper surface), for a spoiler. The faces are wound for the right wing; flip=True turns them for the left, whose corners come the other way round
    (without it every face of the left spoilers pointed inward and they were lit from inside: dark, as if without their paint)."""
    c = np.array(corners)
    v = np.vstack([c, c + [0, 0, thick]])
    f = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]
    if flip:
        f = [(a, c_, b) for a, b, c_ in f]
    return Obj(name, trimesh.Trimesh(v, f, process=False), WHITE)             # painted as the wing: stowed, it is the wing's skin


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
    # NASA's mesh also has a few small pieces of the wing's underside outboard (four thin faces, 0.8 ft by 2.2 ft, in the left wing at 38 to 40 ft from the centreline): separate from the big mesh, they were
    # drawn with the fixed details, unmoved by the wing's stretch (first version: they hung in the air below the leading edge) and, after that was put right, unmoved by the wing's BENDING, which
    # lifts the tip 4 ft in flight (the user: "the small item is still hovering"; "is that some part that doesn't animate with the wing bend?"). They are part of the airframe, before it is cut into the
    # wing's segments, so they are stretched and bent with the wing.
    wing_bits = [b for i, b in bodies if i == 0 and b is not merged and abs(b.bounds.mean(axis=0)[1]) > PODS and b.bounds.mean(axis=0)[2] < 6.0 * KZ and b.bounds.mean(axis=0)[0] > 16.0]
    wing_bit_ids = set(id(b) for b in wing_bits)
    print('  %d small pieces of the wing joined to the airframe, to be stretched and bent with it' % len(wing_bits), flush=True)
    airframe = trimesh.Trimesh(stretch_wing(np.vstack([merged.vertices] + [b.vertices for b in wing_bits])),
                               np.vstack([merged.faces] + [b.faces + len(merged.vertices) + sum(len(x.vertices) for x in wing_bits[:k]) for k, b in enumerate(wing_bits)]), process=False)
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
            seg = keep(keep(keep(airframe, (0, side, 0), (0, side * yk, 0)), (0, -side, 0), (0, side * ends[k + 1], 0)), (-1, 0, 0), (TAIL_X, 0, 0))      # the wing only: not the V-tail's tip, which reaches out past BEND[0]
            if seg is None:
                continue
            if ya - 1e-6 <= yk < yb - 1e-6:
                name = 'aileron-%s-%d' % (sn, k)
                objs.append(Obj(name, keep(seg, aft, h0), GREY))
                anims.extend(bent(name, k))
                anims.append(dict(obj=name, prop=J + 'ctl/aileron-deg', factor=1.0 if side > 0 else -1.0, a=h0, b=h1, down=side))
                seg = keep(seg, -aft, h0)
            name = 'wing-%s-%d' % (sn, k)
            wdec = []
            if cuts[k] <= WING_MARK['y'] < ends[k + 1]:
                # the Finnish livery's cockades on this segment's upper and lower skin (shown only with that livery); they hang on the segment's hinges and bend with it
                le, te, _ = chord_at(airframe, side * WING_MARK['y'])
                xc, yc, dm = le + WING_MARK['chord'] * (te - le), side * WING_MARK['y'], WING_MARK['d']
                sec = np.asarray(airframe.section(plane_origin=[0, yc, 0], plane_normal=[0, 1, 0]).vertices)
                sec = sec[(np.abs(sec[:, 0] - xc) < dm / 2) & (sec[:, 0] < TAIL_X)]
                zm = (sec[:, 2].max() + sec[:, 2].min()) / 2                  # the height between the two skins there
                for up, un in ((1, 'up'), (-1, 'down')):
                    dec, seg = wing_decal(seg, 'cockade-wing-%s-%s' % (sn, un), xc, yc, dm, zm, up)
                    if dec is not None:
                        wdec.append(dec)
            objs.append(Obj(name, seg))
            anims.extend(bent(name, k))
            for dec in wdec:
                objs.append(dec)
                anims.extend(bent(dec.name, k))
        # what is left outboard of the first hinge at the tail's height is the V-tail panel's tip (it reaches 10.2 ft from the centreline, the first hinge is at 10.0): it stays with the airframe.
        # Cut off with the wing's first segment, it bent with the wing and showed as a hollow, sliced tip on the right panel (the user: "why did you slice the tail?").
        tail_tip = keep(keep(core, (0, side, 0), (0, side * cuts[0], 0)), (1, 0, 0), (TAIL_X, 0, 0))
        core = keep(core, (0, -side, 0), (0, side * cuts[0], 0))
        if tail_tip is not None:
            core = trimesh.util.concatenate([core, tail_tip])
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
            objs.append(plate(name, cs, flip=side < 0))
            k = max([i for i, c in enumerate(cuts) if c <= stations[n] + 1e-6], default=-1)
            anims.extend(bent(name, k))
            anims.append(dict(obj=name, prop=J + 'ctl/spoiler-norm', factor=SPOILER['travel_deg'], a=np.array(cs[0]), b=np.array(cs[1]), down=-side))
        # the wing tip's lamps (fdm/ghlights.py: the navigation light and a strobe behind it) hang on the tip's own
        # segment, so that they ride the bending wing
        tipv = airframe.vertices[airframe.vertices[:, 1] * side > HALF - 0.4]
        LAMP_AT['tip-' + sn] = np.array([np.percentile(tipv[:, 0], 30), side * (HALF + 0.05), tipv[:, 2].mean()])
        for lamp in (('nav-green', 'strobe-right') if side > 0 else ('nav-red', 'strobe-left')):
            anims.extend(bent('light-' + lamp, len(cuts) - 1))
    # the V-tail's ruddervators, cut out of what is left
    # The panels are cut along their own plane: NASA's model has them at 47.9 deg (right) and 50.0 (left), not at the flight
    # model's 50.0 (fdm/geometry.py, VTAIL_DIHEDRAL), so the angle is read from the model's own vertices, a side at a time.
    v = core.vertices
    for side, sn in ((1, 'right'), (-1, 'left')):
        panel = (v[:, 0] > 0.80 * G['fuselage']['length']) & (v[:, 1] * side > 2.3) & (v[:, 2] > 7.0 * KZ)
        pv = v[panel]
        n_plane = np.linalg.svd(pv - pv.mean(axis=0), full_matrices=False)[2][2]
        d = math.atan(abs(n_plane[1] / n_plane[2]))
        span_dir = np.array([0.0, side * math.cos(d), math.sin(d)])
        normal = np.array([0.0, -side * math.sin(d), math.cos(d)])
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
    # The main gear's inner doors, cut from the fuselage's lower skin the same way: the belly from near the centre out to the fuselage side, up the lower side wall to the wing root
    # and the wing root's first strip of lower skin. Each is hinged along its inner edge, near the centre of the belly, and hangs open (swung down) while the gear is down; when the
    # gear is up it closes over the folded leg and the side plate to lock them in, its free edge moving outward and up: from the inside out (the user).
    mx0, mx1, my0, my1, mzc, mopen = MAIN_DOOR
    main_doors = {}
    for sd, nm in ((1.0, 'right'), (-1.0, 'left')):
        door, core = cut_out(core, [((1, 0, 0), (mx0, 0, 0)), ((-1, 0, 0), (mx1, 0, 0)), ((0, sd, 0), (0, sd * my0, 0)), ((0, -sd, 0), (0, sd * my1, 0)), ((0, 0, -1), (0, 0, mzc))])
        main_doors[nm] = door
        print('  main door %s: %d faces, x %.2f..%.2f, y %.2f..%.2f, z %.2f..%.2f ft' % (nm, len(door.faces), door.bounds[0][0], door.bounds[1][0], door.bounds[0][1], door.bounds[1][1],
                                                                                         door.bounds[0][2], door.bounds[1][2]), flush=True)
    # The livery is FlightGear's own, on the pattern NASA's two aircraft wear (white, with one thin stripe along each
    # side of the fuselage from the nose to the tail, about where the wing's underside meets it, and a round badge on
    # each side of the nacelle): the stripe in FlightGear's blue with its yellow under it, cut out of the skin as
    # bands between heights, and the badge FlightGear's (fdm/mkinsignia.py), painted on a piece of the nacelle's own
    # skin. No agency's insignia or lettering.
    sz0, sz1, sx0, sx1 = STRIPE
    stripe_parts, pin_parts = [], []
    for xa, xb, ylim in STRIPE_Y:
        ends = [((1, 0, 0), (max(sx0, xa), 0, 0)), ((-1, 0, 0), (min(sx1, xb), 0, 0)), ((0, -1, 0), (0, ylim, 0)), ((0, 1, 0), (0, -ylim, 0))]
        part, core = cut_out(core, [((0, 0, 1), (0, 0, sz0)), ((0, 0, -1), (0, 0, sz1))] + ends)
        stripe_parts.append(part)
        part, core = cut_out(core, [((0, 0, 1), (0, 0, sz0 - 0.09)), ((0, 0, -1), (0, 0, sz0))] + ends)
        pin_parts.append(part)
    stripe_parts, pin_parts = [x for x in stripe_parts if x is not None], [x for x in pin_parts if x is not None]
    stripe = trimesh.util.concatenate(stripe_parts) if stripe_parts else None
    pin = trimesh.util.concatenate(pin_parts) if pin_parts else None
    def decal(core, name, texture, x, z, w, h, side, out):
        """A picture lying on the skin: the square (w ft along the aircraft, h ft high, centred at x, z) of the skin on one side is copied 0.02 ft off the skin along its own normals and carries the
        picture, which is transparent round the marking; the skin under it stays. Returns the decal and the skin."""
        piece, rest = cut_out(core, [((1, 0, 0), (x - w / 2, 0, 0)), ((-1, 0, 0), (x + w / 2, 0, 0)), ((0, 0, 1), (0, 0, z - h / 2)), ((0, 0, -1), (0, 0, z + h / 2)), ((0, side, 0), (0, side * out, 0))])
        if piece is None:
            return None, core
        v = piece.vertices
        u = (v[:, 0] - (x - w / 2)) / w
        # seen from outside, the nose is to the left on the left side and to the right on the right side, and writing reads left to right from either
        uv = np.c_[u if side < 0 else 1.0 - u, (v[:, 2] - (z - h / 2)) / h]
        nrm = np.asarray(piece.vertex_normals).copy()
        if (nrm[:, 1] * side).mean() < 0:
            nrm = -nrm
        return Obj(name, trimesh.Trimesh(v + 0.02 * nrm, piece.faces, process=False), WHITE, texture, np.clip(uv, 0.0, 1.0)), trimesh.util.concatenate([rest, piece])
    badges = []
    q = INSIGNIA
    for side, sn in ((1, 'right'), (-1, 'left')):
        dec, core = decal(core, 'insignia-' + sn, 'insignia.png', q['x'], q['z'], q['size'], q['size'], side, q['out'])
        if dec is not None:
            badges.append(dec)
        # the Finnish livery's markings (shown only with it: sim/model/livery/markings): the serial and the cockade as its next character, on the forward fuselage's upright wall, the group's front edge level
        # with the nose gear's doors' front edge. Writing reads left to right from either side: on the right side (the nose to the viewer's right) the serial is aft and the cockade forward of it, on the left side
        # (the nose to the left) the serial forward and the cockade aft.
        mk = MARKINGS
        import mkmarkings
        aspect, gap_ratio = mkmarkings.serial_metrics()
        sh = mk['serial']['h']
        sw, gap = sh * aspect, sh * gap_ratio                    # the serial's width (the picture is cut tight to its ink) and the gap between its 0 and its 1
        cw = mk['cockade']['w']
        if side > 0:
            parts = (('cockade-', 'cockade.png', mk['front'] + cw / 2, mk['cockade']), ('serial-', 'serial.png', mk['front'] + cw + gap + sw / 2, dict(w=sw, h=sh)))
        else:
            parts = (('serial-', 'serial.png', mk['front'] + sw / 2, dict(w=sw, h=sh)), ('cockade-', 'cockade.png', mk['front'] + sw + gap + cw / 2, mk['cockade']))
        for nm, tex, xc, m in parts:
            dec, core = decal(core, nm + sn, tex, xc, mk['z'], m['w'], m['h'], side, mk['out'])
            if dec is not None:
                badges.append(dec)
    objs.insert(0, Obj('airframe', core))
    if stripe is not None:
        objs.append(Obj('stripe', stripe, BLUE))
    if pin is not None:
        objs.append(Obj('stripe-pin', pin, YELLOW))
    objs.extend(badges)
    # where the other lamps go: the white light at the fuselage's end, red beacons on top of the nacelle and under the belly
    fv = core.vertices[np.abs(core.vertices[:, 1]) < 0.6]
    top = fv[(fv[:, 0] > 29.0) & (fv[:, 0] < 31.0)]
    under = fv[(fv[:, 0] > 13.0) & (fv[:, 0] < 15.0)]
    LAMP_AT.update(tail=fv[np.argmax(fv[:, 0])] + [0.05, 0, 0], top=np.array([30.0, 0.0, top[:, 2].max() + 0.05]), under=np.array([14.0, 0.0, under[:, 2].min() - 0.05]))
    zb = max(d.vertices[:, 2].max() for d in nose_doors.values())          # above the doors' highest edge: the belly is curved, and a well that began lower stood out of it at the sides
    wv = np.array([(x, y, z) for z in (zb + 0.05, zb + 2.5) for x, y in ((x0, -hw), (x1, -hw), (x1, hw), (x0, hw))]) * [1, 0.97, 1]
    wf = [(4, 5, 6), (4, 6, 7)] + [t for k in range(4) for t in ((k, (k + 1) % 4, 4 + (k + 1) % 4), (k, 4 + (k + 1) % 4, 4 + k))]
    objs.append(Obj('nose-gear-well', trimesh.Trimesh(wv, np.array(wf), process=False), DARK))
    # behind each main door: a dark liner, the door's own skin copied 0.3 ft up and drawn in 15 % toward the centre, so it follows the skin from inside and shows (dark) when the door is open;
    # dark boxes there stood out of the fuselage's rounded lower sides
    for nm, door in main_doors.items():
        objs.append(Obj('main-gear-well-' + nm, trimesh.Trimesh(door.vertices * [1.0, 0.85, 1.0] + [0.0, 0.0, 0.3], door.faces, process=False), DARK))
    # everything else: small fixed things, and the gear in three legs
    legs = {'gear-nose': [], 'gear-left': [], 'gear-right': []}
    fixed = []
    for i, b in bodies:
        if b is merged or id(b) in wing_bit_ids:
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

    def add(name, mesh, mat, rotations, hide_up=0, scale=None, lift=None):          # nothing is hidden: what folds away has to fit where it goes
        """An object and its rotations. Where there are two, FlightGear applies the LAST one listed nearest the object
        and the first one outermost (in the F-16's model a wheel's spin comes after its leg's retraction). So a part
        carried by the leg lists the leg's rotation first and its own after it."""
        objs.append(Obj(name, mesh, mat))
        if lift is not None:                                   # a table of gear position and metres (up): listed first, so outermost, after the turns
            anims.append(dict(obj=name, lift=lift, a=np.zeros(3), b=np.zeros(3)))
        for tab, a, b in rotations:
            anims.append(dict(obj=name, table=tab, a=np.asarray(a, float), b=np.asarray(b, float)))
        if scale is not None:                                  # (ramps (m, a, b) of the gear position whose product is the factor along the model's y axis, the point it is scaled about): listed last, so nearest the object
            anims.append(dict(obj=name, scale=scale[0], a=np.asarray(scale[1], float), b=np.asarray(scale[1], float)))
        if hide_up:
            anims.append(dict(obj=name, hide_up=hide_up, a=np.zeros(3), b=np.ones(3)))

    for name, pieces in legs.items():
        if 'nose' not in name:
            pieces = shift_main_leg(resize_main_wheels(pieces))
        # NASA's parts: 1 struts, axles and hubs; 2 tyres; 3 the mains' side braces; 4 door plates; 5 the nose wheel's hubs
        tyres = [b for i, b in pieces if i == 2]
        plates = [b for i, b in pieces if i == 4]
        if plates and 'nose' not in name:
            for k, b in enumerate(plates):
                lo_, hi_ = b.bounds
                print('  %s door plate %d: x %.2f..%.2f, y %.2f..%.2f, z %.2f..%.2f ft, %d verts' % (name, k, lo_[0], hi_[0], lo_[1], hi_[1], lo_[2], hi_[2], len(b.vertices)), flush=True)
        metal = [b for i, b in pieces if i in (1, 5)]
        braces = [b for i, b in pieces if i == 3]
        fixed += [b for i, b in pieces if i == 0]                                                 # a plate on the belly by the nose gear: part of the skin
        struts = [b for i, b in pieces if i == 1]
        xaxis = np.array([1.0, 0.0, 0.0])
        if 'nose' in name:
            # The nose wheel is made the F-5's size, 18 x 6.5-8 (the size the flight model and the sounds already use; docs/PLAN.md,
            # "Nose wheel"): NASA's mesh has it 16.5 in across and 4.3 in wide. Tyre and hub are scaled about the axle, in the wheel's own
            # plane and across it, and the whole wheel is lifted so its lowest point stays where it was; the hub to the 8 in rim.
            tyres, metal = f5_nose_wheel(tyres, [b for i, b in pieces if i == 5], [b for i, b in pieces if i == 1])
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

        def slim(b):                                                       # the upright strut (the wide piece high up) made STRUT_ACROSS wide about its own centre line; nothing else moves
            lo_, hi_ = b.bounds
            if hi_[1] - lo_[1] > 0.8 and hi_[2] > 3.5:
                w = b.vertices.copy()
                yc = 0.5 * (lo_[1] + hi_[1])
                w[:, 1] = yc + (w[:, 1] - yc) * STRUT_ACROSS / (hi_[1] - lo_[1])
                print('  %s strut: %.2f ft across made %.2f' % (name, hi_[1] - lo_[1], STRUT_ACROSS), flush=True)
                return trimesh.Trimesh(w, b.faces, process=False)
            return b
        metal = [slim(b) for b in metal]                                   # only the drawn strut: `struts`, which the fold's pivot is taken from, is left as it was
        if braces:
            br0 = trimesh.util.concatenate(braces)
            yin, yout = np.abs(br0.vertices[:, 1]).min(), np.abs(br0.vertices[:, 1]).max()
            v = br0.vertices.copy()
            v[:, 1] = side * (yin + (np.abs(v[:, 1]) - yin) * (yout + MAIN_OUT - yin) / (yout - yin))
            braces = [trimesh.Trimesh(v, br0.faces, process=False)]
        strut = max(struts, key=lambda b: np.ptp(b.bounds[:, 2]))                                 # the tallest piece: the leg itself
        c = strut.bounds.mean(axis=0)
        print('  %s: the strut top is at z %.2f ft; the leg folds about y %.2f z %.2f' % (name, strut.bounds[1][2], c[1] - side * PIVOT_IN, PIVOT_Z), flush=True)
        pivot = np.array([c[0], c[1] - side * PIVOT_IN, PIVOT_Z])
        # the leg swings inboard and up about its own top, to lie inside the fuselage and the wing root (hidden then: LEG_SHOWN)
        theta = -LEG_FOLD_DEG * side * (1 - leg_frac)
        leg = (table(theta), pivot, pivot + xaxis)
        lift = table(STRUT_LIFT * np.clip((STRUT_LIFT_FROM - G_) / (STRUT_LIFT_FROM - 0.25), 0.0, 1.0))
        for suffix, group, mat in (('', metal, GREY), ('-tyres', tyres, TYRE)):
            if group:
                thin = ([(STRUT_THIN, (1 - STRUT_THIN) / (STRUT_LIFT_FROM - 0.25), STRUT_THIN - (1 - STRUT_THIN) / (STRUT_LIFT_FROM - 0.25) * 0.25)], c) if suffix == '' else None
                add(name + suffix, trimesh.util.concatenate(group), mat, [leg], hide_up=LEG_SHOWN, lift=lift, scale=thin)
        # the side plate: NASA's, where NASA has it beside the leg (moved with the leg), and attached to the strut: it goes wherever the leg goes. Its own motion is only a tuck against the
        # strut as the leg folds (it hangs tilted 19.5 deg out; folded it lies flat beside the leg, inside the wing root, under the doors)
        if plates:
            pv0 = trimesh.util.concatenate([moved(b) for b in plates])
            pv = trimesh.Trimesh(pv0.vertices + [PLATE_END_X - pv0.vertices[:, 0].max(), 0.0, 0.0], pv0.faces, process=False)
            # The plate is attached to the strut and moves exactly as the leg does, at the leg's speed, all the way to gear position 0.25, when the struts are completely in (the user: "move the
            # side plates like they were attached to the struts"; "the issue was in the speed of the animation between components": a tuck of its own, added to the leg's turn, made it go in
            # faster than the wheels). Only then does it move more (the user: "the plates need to move more once the struts are completely in"): it straightens against the strut, from 0.25 to
            # PLATE_IN, so that it lies flat in the wing root before the doors come over it. Folded rigidly it ends 21 deg below horizontal, 37 % of it outside the skin (folded_in.py).
            v = pv.vertices
            a_, b_ = np.linalg.lstsq(np.c_[np.ones(len(v)), v[:, 2]], v[:, 1], rcond=None)[0]       # the plate's mid line, y against height
            zt, zb = v[:, 2].max(), v[:, 2].min()
            yt, yb = a_ + b_ * zt, a_ + b_ * zb
            tilt = math.degrees(math.atan2(side * (yb - yt), zt - zb))                              # how far it hangs out of the vertical, outward positive
            h0 = np.array([v[:, 0].min(), yt, zt])
            tuck = np.clip((0.25 - G_) / (0.25 - PLATE_IN), 0.0, 1.0)
            tuck = tuck * tuck * (3.0 - 2.0 * tuck)                                                  # eased
            print('  side plate (%s): hinge on the strut at y %.2f z %.2f, hanging %.1f deg out; with the leg to gear 0.25, then straightens %.1f deg by gear %.2f' % (
                'right' if side > 0 else 'left', yt, zt, tilt, tilt, PLATE_IN), flush=True)
            add(name.replace('gear-', 'gear-plate-'), pv, WHITE, [leg, (table(-side * tilt * tuck), h0, h0 + xaxis)])
        # the inner doors, cut from the skin above: added once, with the right leg. Each is hinged along its inner edge and swings down to hang open, free edge inboard-down;
        # closing, the free edge swings outward and up
        if name == 'gear-right':
            for nm, door in main_doors.items():
                sd = 1.0 if nm == 'right' else -1.0
                dv = door.vertices
                inner = dv[np.abs(dv[:, 1]) < np.abs(dv[:, 1]).min() + 0.06]                  # the hinge edge, near the centre of the belly
                h0, h1 = inner[np.argmin(inner[:, 0])], inner[np.argmax(inner[:, 0])]
                add('gear-main-door-%s' % nm, door, WHITE, [(table(-mopen * sd * door_frac), h0, h1)])
        if braces:
            # The side brace runs from the fuselage to the leg, and is TELESCOPIC (the user): it shortens as the leg folds, and does not fold. It is one bar, made straight along the model's
            # y axis about its fuselage end F, turned about F to point at the leg's end of it A as the leg moves, and scaled along its length to the distance from F to A: from 3.5 ft with
            # the gear down to 0.6 ft folded. (Jointed like a knee it stood out through the belly, or up through the wing.)
            br = trimesh.util.concatenate(braces)
            v = br.vertices
            inner_end = v[np.argmin(np.abs(v[:, 1]))]
            outer_end = v[np.argmax(np.abs(v[:, 1]))]
            F = np.array([inner_end[1] * side, inner_end[2]])               # worked in the right-hand side's (y, z)
            A0 = np.array([outer_end[1] * side, outer_end[2]])
            P = np.array([pivot[1] * side, pivot[2]])
            d0 = float(np.linalg.norm(A0 - F))
            phi0 = math.atan2(A0[1] - F[1], A0[0] - F[0])
            rel = np.c_[v[:, 1] * side - F[0], v[:, 2] - F[1]]               # the mesh turned about F so that the bar lies along +y
            c0, s0 = math.cos(-phi0), math.sin(-phi0)
            flat = v.copy()
            flat[:, 1] = side * (F[0] + c0 * rel[:, 0] - s0 * rel[:, 1])
            flat[:, 2] = F[1] + s0 * rel[:, 0] + c0 * rel[:, 1]
            phis, scales = [], []
            for fr in leg_frac:
                th = math.radians(-LEG_FOLD_DEG * (1 - fr))
                R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
                dv = P + R @ (A0 - P) - F                                   # from F to where the leg's end of the brace is now
                phis.append(math.degrees(math.atan2(dv[1], dv[0])))
                scales.append(float(np.linalg.norm(dv)) / d0)
            phis = np.degrees(np.unwrap(np.radians(phis)))
            tuck = np.clip((BRACE_TUCK_FROM - G_) / (BRACE_TUCK_FROM - 0.25), 0.0, 1.0)
            tuck = tuck * tuck * (3.0 - 2.0 * tuck)
            phis = phis * (1.0 - tuck) + BRACE_TUCK_DEG * tuck
            print('  brace %s: %.2f ft from the fuselage end to the leg end, shortening to %.2f ft (x%.2f), turning from %.1f to %.1f deg' % (name, d0, d0 * min(scales), min(scales), phis[-1], phis[0]), flush=True)
            F3 = np.array([inner_end[0], inner_end[1], inner_end[2]])
            ramps, err = fit_ramps(G_, scales)
            print('    its length by the gear position: two ramps in a row, worst error %.3f ft' % (err * d0), flush=True)
            add(name + '-brace', trimesh.Trimesh(flat, br.faces, process=False), GREY, [(table(phis * side), F3, F3 + xaxis)], scale=(ramps, F3))
    if fixed:
        objs.append(Obj('details', trimesh.util.concatenate(fixed), WHITE))        # aerials and the like: the skin's colour
    return objs, anims, airframe


def write(objs, anims):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'GlobalHawk.ac'), 'w') as fh:
        fh.write('AC3Db\n')
        for rgb, name, spec in (((0.94, 0.94, 0.95), 'white', 0.25), ((0.80, 0.82, 0.84), 'grey', 0.25), ((0.20, 0.21, 0.23), 'dark', 0.1), ((0.05, 0.05, 0.05), 'tyre', 0.02), ((0.26, 0.49, 0.75), 'blue', 0.25), ((0.98, 0.99, 0.27), 'yellow', 0.25)):
            fh.write('MATERIAL "%s" rgb %g %g %g  amb %g %g %g  emis 0 0 0  spec %g %g %g  shi 30  trans 0\n' % ((name,) + rgb + rgb + (spec, spec, spec)))
        fh.write('OBJECT world\nkids %d\n' % len(objs))
        for o in objs:
            o.write(fh)
    x = ['<?xml version="1.0"?>',
         '<!-- Generated by fdm/mkmodel.py from NASA\'s 3-D model of the Global Hawk (NASA 3D Resources), scaled to the published',
         '     length and with the wing stretched to the published span and area. Shape courtesy of NASA; no endorsement implied. -->',
         '<PropertyList>', ' <path>GlobalHawk.ac</path>']
    # the livery of an aircraft seen over multiplayer follows the file its owner has picked (aircraft.livery_update does nothing outside a multiplayer model)
    x.append(' <nasal><load>var livery_update = aircraft.livery_update.new("Aircraft/GlobalHawk/Models/Liveries", 10);</load><unload>livery_update.stop();</unload></nasal>')
    # the lamps: models of their own (fdm/ghlights.py), at the places build found
    import ghlights
    m = lambda k: tuple(float(c) * FT for c in LAMP_AT[k])
    ghlights.lights(m('tip-left'), m('tip-right'), m('tail'), m('top'), m('under'))
    ghlights.install(os.path.join(OUT, '..'))
    x.append(' ' + ghlights.models().replace('\n', '\n ').rstrip())
    # the HDR materials: an effect file each, and which objects wear it
    eff_dir = os.path.join(OUT, 'Effects')
    os.makedirs(eff_dir, exist_ok=True)
    wear = {}
    for o in objs:
        e = effect_of(o.name)
        if e is None:
            raise ValueError('no material for ' + o.name)
        wear.setdefault(e, []).append(o.name)
    for e, names in wear.items():
        base, metal, rough, _ = EFFECTS[e]
        open(os.path.join(eff_dir, 'gh-%s.eff' % e), 'w').write(
            '<?xml version="1.0"?>\n<PropertyList><name>gh-%s</name><inherits-from>%s</inherits-from><parameters>%s'
            '<metallic-factor type="float">%g</metallic-factor><roughness-factor type="float">%g</roughness-factor></parameters></PropertyList>\n'
            % (e, 'Effects/model-pbr-transparent' if e in ('badge', 'marking') else 'Effects/model-pbr', '<base-color-factor type="vec4d">%g %g %g 1</base-color-factor>' % base if base else '', metal, rough))
        if e in LIVERY_PBR:
            # the livery's paint: the animation first, then the effect (as in the Bo 105): base colour and roughness from sim/model/livery/<group>
            x.append(' <animation><type>pbr</type>%s<property-base>sim/model/livery/%s</property-base>'
                     '<base-color-factor><red>red</red><green>green</green><blue>blue</blue><alpha>1</alpha></base-color-factor><roughness-factor>roughness</roughness-factor></animation>' % (
                         ''.join('<object-name>%s</object-name>' % n for n in names), LIVERY_PBR[e]))
        x.append(' <effect><inherits-from>Aircraft/GlobalHawk/Models/Effects/gh-%s</inherits-from>%s</effect>' % (e, ''.join('<object-name>%s</object-name>' % n for n in names)))
    hidden = []
    for a in anims:
        p0, p1 = a['a'] * FT, a['b'] * FT
        axis = '  <axis><x1-m>%.4f</x1-m><y1-m>%.4f</y1-m><z1-m>%.4f</z1-m><x2-m>%.4f</x2-m><y2-m>%.4f</y2-m><z2-m>%.4f</z2-m></axis></animation>' % (
            p0[0], p0[1], p0[2], p1[0], p1[1], p1[2])
        if a.get('hide_up'):
            hidden.append((a['obj'], a['hide_up']))
            continue
        if a.get('lift'):
            x.append(' <animation><type>translate</type><object-name>%s</object-name>' % a['obj'])
            x.append('  <property>%sgear/gear-pos-norm</property><interpolation>%s</interpolation>' % (
                J, ''.join('<entry><ind>%.2f</ind><dep>%.4f</dep></entry>' % (e[0], e[1] * FT) for e in a['lift'])))
            x.append('  <axis><x>0</x><y>0</y><z>1</z></axis></animation>')
            continue
        if a.get('scale'):
            # telescopic: scaled along the model's y axis only, about the point given; the factor is a ramp of the gear position, and where there are several they multiply
            for m, fa, fb in a['scale']:
                x.append(' <animation><type>scale</type><object-name>%s</object-name>' % a['obj'])
                x.append('  <property>%sgear/gear-pos-norm</property>' % J)
                x.append('  <x-offset>1</x-offset><x-factor>0</x-factor><y-offset>%.5f</y-offset><y-factor>%.5f</y-factor><y-min>%.5f</y-min><y-max>1</y-max><z-offset>1</z-offset><z-factor>0</z-factor>' % (fb, fa, m))
                x.append('  <center><x-m>%.4f</x-m><y-m>%.4f</y-m><z-m>%.4f</z-m></center></animation>' % (p0[0], p0[1], p0[2]))
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
        # (nothing is hidden any more: LEG_SHOWN is 0, so this loop finds no parts; the folded gear lies inside the airframe)
        x.append(' <animation><type>select</type>' + ''.join('<object-name>%s</object-name>' % n for n, l in hidden if l == limit))
        x.append('  <condition><greater-than><property>%sgear/gear-pos-norm</property><value>%g</value></greater-than></condition></animation>' % (J, limit))
    marks = [o.name for o in objs if o.name.startswith(('cockade-', 'serial-'))]
    if marks:
        x.append(' <animation><type>select</type>' + ''.join('<object-name>%s</object-name>' % n for n in marks) + '<condition><property>sim/model/livery/markings</property></condition></animation>')
    x.append('</PropertyList>')
    open(os.path.join(OUT, 'GlobalHawk.xml'), 'w').write('\n'.join(x) + '\n')
    liv_dir = os.path.join(OUT, 'Liveries')
    os.makedirs(liv_dir, exist_ok=True)
    for lv in LIVERIES:
        groups = ''.join('    <%s>\n     <red type="float">%g</red>\n     <green type="float">%g</green>\n     <blue type="float">%g</blue>\n     <roughness type="float">%g</roughness>\n    </%s>\n' % (
            grp, lv[grp][0][0], lv[grp][0][1], lv[grp][0][2], lv[grp][1], grp) for grp in ('paint', 'stripe', 'pin', 'fan', 'spinner'))
        open(os.path.join(liv_dir, lv['file'] + '.xml'), 'w').write(
            '<?xml version="1.0"?>\n<!-- A livery of the Global Hawk, written by fdm/mkmodel.py (LIVERIES): FlightGear\'s livery selector copies these properties into sim/model/livery. Each group: base colour in linear light and roughness. -->\n'
            '<PropertyList>\n <sim>\n  <model>\n   <livery>\n    <name type="string">%s</name>\n    <index type="int">%d</index>\n%s   </livery>\n  </model>\n </sim>\n</PropertyList>\n' % (lv['name'], lv['index'], groups + '    <markings type="bool">%s</markings>\n' % ('true' if lv['markings'] else 'false')))


SIDE_WALL = 2.5                                                    # ft: the fuselage wall at the wing root (the wing's span fractions are counted from here, as in docs/PLAN.md)


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
            'gear-plate-left', 'gear-plate-right', 'gear-main-door-left', 'gear-main-door-right', 'gear-left-brace', 'gear-right-brace', 'gear-nose-door-left', 'gear-nose-door-right']
    missing = [n for n in need if n not in names]
    ok &= not missing and all(a['obj'] in names or a['obj'].startswith('light-') for a in anims)
    for n in need[:4]:
        m = next(o.mesh for o in objs if o.name == n)
        print('  %-42s %5d faces, %.1f sq ft in plan' % (n, len(m.faces), m.area / 2))
    print('  %d objects, %d vertices, %d faces; moving parts missing: %s' % (len(objs), len(v), sum(len(o.mesh.faces) for o in objs), missing or 'none'))
    # the default livery's numbers in the set file are the white livery's (the aircraft starts with them, before any file is chosen), and every object painted with the 'paint' effect is on the pbr animation
    import xml.etree.ElementTree as ET
    lv = ET.parse(os.path.join(HERE, '..', 'GlobalHawk', 'GlobalHawk-set.xml')).getroot().find('sim/model/livery')
    d = LIVERIES[0]
    same = lv.findtext('name') == d['name']
    same &= (lv.findtext('markings') == 'true') == d['markings']
    for grp in ('paint', 'stripe', 'pin', 'fan', 'spinner'):
        got = [float(lv.findtext('%s/%s' % (grp, k))) for k in ('red', 'green', 'blue', 'roughness')]
        same &= all(abs(a - b) < 1e-9 for a, b in zip(got, list(d[grp][0]) + [d[grp][1]]))
    painted = [o.name for o in objs if effect_of(o.name) in LIVERY_PBR]
    xml_text = open(os.path.join(OUT, 'GlobalHawk.xml')).read()
    pbr = ''.join(xml_text.split('<type>pbr</type>')[1:])
    on_pbr = all('<object-name>%s</object-name>' % n in pbr for n in painted)
    print('  livery: the set file\'s defaults are the white livery\'s: %s; the %d painted objects are all on the pbr animation: %s' % (same, len(painted), on_pbr))
    ok &= same and on_pbr
    # the Finnish livery's wing cockades (docs/PLAN.md, "Roundels on the Finnish livery's wings"), limits (a) to (e)
    from scipy.spatial import cKDTree
    wc = sorted(n for n in names if n.startswith('cockade-wing-'))
    cuts_t = sorted(set(list(BEND) + [AILERON['inner'] * HALF, AILERON['outer'] * HALF]))
    k_t = max(i for i, c in enumerate(cuts_t) if c <= WING_MARK['y'])
    lo, hi = cuts_t[k_t], (cuts_t + [HALF + 1.0])[k_t + 1]
    good = len(wc) == 4 and len(objs) == 72
    print('  wing cockades (a): %d of 4 (%s), %d objects (72)  %s' % (len(wc), ', '.join(wc), len(objs), 'pass' if good else 'MISS'))
    ok &= good
    marked = next(x for x in xml_text.split('<animation>') if 'sim/model/livery/markings' in x)
    eff_marking = open(os.path.join(OUT, 'Effects', 'gh-marking.eff')).read() and xml_text.split('gh-marking</inherits-from>')[1].split('</effect>')[0]
    for n in wc:
        o = next(o for o in objs if o.name == n)
        sn = 'right' if '-right-' in n else 'left'
        y = np.abs(o.mesh.vertices[:, 1])
        seg = next(q.mesh for q in objs if q.name == 'wing-%s-%d' % (sn, k_t))
        ail = next(q.mesh for q in objs if q.name == 'aileron-%s-%d' % (sn, k_t))
        pts, fi = seg.sample(400000, return_index=True)
        _, near = cKDTree(pts).query(o.mesh.vertices)
        fn = seg.face_normals[fi[near]]
        dist = np.abs(((o.mesh.vertices - seg.triangles[fi[near]][:, 0]) * fn).sum(axis=1))
        clear = ail.vertices[:, 0].min() - o.mesh.vertices[:, 0].max()
        good_b, good_c = lo - 1e-6 <= y.min() and y.max() <= hi + 1e-6, clear >= 0.05
        le_t, te_t, _ = chord_at(airframe, y.mean() * (1 if sn == 'right' else -1))
        vx, vy = o.mesh.vertices[:, 0], np.abs(o.mesh.vertices[:, 1])
        diam, at_chord, at_span = max(vx.max() - vx.min(), vy.max() - vy.min()), ((vx.max() + vx.min()) / 2 - le_t) / (te_t - le_t), ((vy.max() + vy.min()) / 2 - SIDE_WALL) / (HALF - SIDE_WALL)
        good_g, good_h = abs(diam - MARKINGS['cockade']['w']) < 0.02, 0.36 <= at_chord <= 0.40 and 0.76 <= at_span <= 0.79
        print('  %-34s across %.2f ft, the fuselage cockade\'s %.2f (g) %s; centre %.1f %% of the way out, %.1f %% of the chord back (h) %s' % (
            n, diam, MARKINGS['cockade']['w'], 'pass' if good_g else 'MISS', 100 * at_span, 100 * at_chord, 'pass' if good_h else 'MISS'))
        ok &= good_g and good_h
        e_sorted = np.sort(o.mesh.edges, axis=1)
        uniq, cnt = np.unique(e_sorted, axis=0, return_counts=True)
        mid = o.mesh.vertices[uniq[cnt == 1]].mean(axis=1)
        wx, wy, wd = (vx.max() + vx.min()) / 2, (vy.max() + vy.min()) / 2, MARKINGS['cockade']['w']
        rim = np.minimum(np.abs(np.abs(mid[:, 0] - wx) - wd / 2), np.abs(np.abs(np.abs(mid[:, 1]) - wy) - wd / 2))
        inner = int((rim > 0.03).sum())
        print('  %-34s %d open edges, %d of them not on the window\'s rim: cracks (i) %s' % (n, len(mid), inner, 'pass' if inner == 0 else 'MISS'))
        ok &= inner == 0
        good_d, good_e = 0.015 <= dist.min() and dist.max() <= 0.025, ('<object-name>%s</object-name>' % n in marked) and ('<object-name>%s</object-name>' % n in eff_marking)
        print('  %-34s %3d faces, y %.2f..%.2f of %.0f..%.0f (b) %s; clear of the aileron by %.2f ft (c) %s; %.4f..%.4f ft off the skin (d) %s; in the markings group and effect (e) %s' % (
            n, len(o.mesh.faces), y.min(), y.max(), lo, hi, 'pass' if good_b else 'MISS', clear, 'pass' if good_c else 'MISS', dist.min(), dist.max(), 'pass' if good_d else 'MISS', 'pass' if good_e else 'MISS'))
        ok &= good_b and good_c and good_d and good_e
    for sn in ('right', 'left'):
        up_o, dn_o = (next(q.mesh for q in objs if q.name == 'cockade-wing-%s-%s' % (sn, w)) for w in ('up', 'down'))
        sp = [np.abs(q.mesh.vertices[:, 1]).max() for q in objs if q.name.startswith('spoiler-%s-' % sn)]
        near = np.abs(up_o.vertices[:, 1]).min()
        c_up, c_dn = (up_o.vertices[:, :2].min(axis=0) + up_o.vertices[:, :2].max(axis=0)) / 2, (dn_o.vertices[:, :2].min(axis=0) + dn_o.vertices[:, :2].max(axis=0)) / 2
        good_k, good_l = near - max(sp) >= 10.0, bool(np.abs(c_up - c_dn).max() <= 0.01)
        print('  wing cockades, %-5s: the upper one %.1f ft clear of the spoiler plates (k) %s; upper and lower centres %.4f ft apart in plan (l) %s' % (
            sn, near - max(sp), 'pass' if good_k else 'MISS', np.abs(c_up - c_dn).max(), 'pass' if good_l else 'MISS'))
        ok &= good_k and good_l
    return ok


if __name__ == '__main__':
    objs, anims, airframe = build()
    write(objs, anims)
    print('wrote GlobalHawk/Models/GlobalHawk.ac and GlobalHawk.xml')
    raise SystemExit(0 if test(objs, anims, airframe) else 1)
