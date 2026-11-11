#!/usr/bin/env python3
"""Geometry and mass of NASA's Global Hawk (RQ-4A) from public sources: writes fdm/data/geometry.json and mass.json.

Three sources, none of them complete (fdm/data/README.md, "Geometry", says what each is trusted for):

  published numbers   span 116.2 ft, length 44.4 ft, wing area 540 ft2, the weights
  NASA's side view    a line drawing of the fuselage with its payload bays, from NASA's Global Hawk briefings:
                      fuselage outline, nacelle, fin, gear and wing root positions along the length and in height
  NASA's 3-D model    an artist's model (NASA 3D Resources), not to scale as a whole: used for shapes seen from above
                      and from the front, which the side view can't give (planform taper and sweep, twist, tail
                      dihedral, gear track, fuselage width)

    python3 fdm/geometry.py            measure, write the JSON files, print the summary
    python3 fdm/geometry.py --plot     also draw fdm/out/geometry.png

Frame of the output: feet; x aft from the nose tip, y to the right, z up from the ground with the aircraft
standing on its wheels as drawn.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_GEOM = os.path.join(HERE, 'data', 'geometry.json')
OUT_MASS = os.path.join(HERE, 'data', 'mass.json')

# ---- published (fdm/data/README.md has the sources)
SPAN = 116.2            # ft
LENGTH = 44.4           # ft
HEIGHT = 15.2           # ft, NASA; Northrop Grumman's sheet says 14.6
HEIGHT_NG = 14.6
AREA = 540.0            # ft2, Jane's 1999
W_GROSS = 26750.0       # lb
W_EMPTY = 9100.0        # lb, with fluids
W_FUEL = 15300.0        # lb
W_ENGINE = 1644.0       # lb, Rolls-Royce
FUEL_DENSITY = 50.1     # lb/ft3, JP-8 at 6.7 lb/gal
TC = 0.152              # LRN 1015
ZERO_FUEL_CG = 0.25     # of the mean aerodynamic chord: a choice, see mass_model()

# ---- NASA's side view, digitised by hand in pixels (x to the right = forward, y down). The drawing is
# 1024 x 344; the nose tip is at x = 1010, the tail end at x = 4, the ground under the nose wheel at y = 336.
PX_NOSE, PX_TAIL, PX_GROUND, PX_TOP = 1010.0, 4.0, 336.0, 11.0
SV = dict(
    # fuselage upper and lower outline (x, y): nose to tail
    top=[(1010, 215), (992, 177), (960, 154), (928, 138), (896, 126), (864, 116), (832, 113), (800, 115), (768, 121),
         (736, 128), (704, 137), (672, 146), (640, 154), (608, 161), (576, 166), (544, 170), (512, 170), (470, 172),
         (400, 180), (330, 205), (210, 204), (120, 192), (4, 207)],
    bottom=[(1010, 215), (992, 260), (960, 272), (896, 272), (864, 273), (832, 277), (800, 281), (768, 286), (736, 292),
            (704, 296), (672, 298), (608, 297), (576, 293), (544, 285), (512, 277), (480, 272), (416, 268), (384, 269),
            (352, 264), (320, 260), (288, 259), (192, 261), (160, 258), (128, 253), (96, 246), (64, 237), (32, 225),
            (4, 209)],
    radome=[(290, 259), (256, 283), (224, 275), (200, 261)],     # the bulge under the aft fuselage
    wing_root_le=(572, 243), wing_root_te=(400, 222),            # ends of the wing root as drawn; heights are rough
    symbol=(462, 213),             # a centre-of-gravity style symbol on the wing root; see the README
    main_axle=(437, 312), main_wheel_radius=21.0,
    nose_axle=(771, 318), nose_wheel_radius=18.0,
    inlet_lip=(500, 158), nacelle_top=88.0, exhaust_x=105.0, exhaust_top=98.0, exhaust_bottom=192.0,
    fin_tip_y=12.0, fin_tip_x=(37, 93), fin_root_y=215.0, fin_root_x=(8, 118),
)
FT_PER_PX = LENGTH / (PX_NOSE - PX_TAIL)


def sv_point(p):
    """A side-view pixel as (x aft of the nose, z above the ground) in feet."""
    return ((PX_NOSE - p[0]) * FT_PER_PX, (PX_GROUND - p[1]) * FT_PER_PX)


# ---- NASA's 3-D model: its axes are x to the right, y up, z forward, in arbitrary units
def mesh_measure():
    """What is taken from the mesh, in mesh units. Returns None when the model or its readers aren't there."""
    try:
        import trimesh
        import glb
        parts = glb.load()
    except Exception as e:                                  # the model is not in the repository
        print('3-D model not read (%s): keeping the mesh numbers already in geometry.json' % e)
        return None
    allv = np.vstack([p['vertices'] for p in parts])
    lo, hi = allv.min(0), allv.max(0)
    body = trimesh.Trimesh(parts[0]['vertices'], parts[0]['faces'], process=False)
    out = dict(extent_span=float(hi[0] - lo[0]), extent_length=float(hi[2] - lo[2]), extent_height=float(hi[1] - lo[1]),
               nose_z=float(hi[2]), ground_y=float(lo[1]), half_span=float((hi[0] - lo[0]) / 2))

    # wing sections at span stations, both sides averaged
    def wing_section(x):
        s = body.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
        pts = np.vstack([s.vertices[e.points] for e in s.entities])
        pts = pts[pts[:, 2] > -50]                         # not the tail
        le, te = pts[pts[:, 2].argmax()], pts[pts[:, 2].argmin()]
        chord = le[2] - te[2]
        zb = np.linspace(te[2], le[2], 40)
        th = 0.0
        for a, b in zip(zb[:-1], zb[1:]):
            k = (pts[:, 2] >= a) & (pts[:, 2] <= b)
            if k.sum() > 1:
                th = max(th, float(np.ptp(pts[k, 1])))
        return np.array([le[2], te[2], np.degrees(np.arctan2(le[1] - te[1], chord)), th / chord,
                         le[1] - 0.25 * (le[1] - te[1])])
    stations = [14, 16, 18, 20, 25, 30, 35, 40, 50, 75, 100, 125, 150, 175, 190, 200, 205, 207]
    rows = []
    for x in stations:
        a, b = wing_section(x), wing_section(-x)
        rows.append([x] + list((a + b) / 2))
    out['wing'] = [dict(x=r[0], le_z=r[1], te_z=r[2], incidence=r[3], tc=r[4], quarter_y=r[5]) for r in rows]

    # V-tail: the two panels' tips and roots seen from the front
    tail = parts[0]['vertices']
    tail = tail[(tail[:, 2] < -45) & (tail[:, 1] > 36)]
    right = tail[tail[:, 0] > 0]
    tip = right[right[:, 1] > right[:, 1].max() - 1.0]
    ys = np.linspace(60, right[:, 1].max() - 2, 8)          # above the nacelle, where only the panel is left
    xc = []
    for y in ys:
        k = (abs(right[:, 1] - y) < 1.5) & (right[:, 0] > 14)
        xc.append((right[k, 0].min() + right[k, 0].max()) / 2)
    slope = np.polyfit(np.array(xc), ys, 1)[0]
    out['tail_dihedral_deg'] = float(np.degrees(np.arctan(slope)))
    out['tail_tip_x'] = float(tip[:, 0].mean())
    out['tail_tip_y'] = float(tip[:, 1].mean())

    # gear: wheel centres (tyres are the third part), fuselage width
    tyres = trimesh.Trimesh(parts[2]['vertices'], parts[2]['faces'], process=False).split(only_watertight=False)
    cs = np.array([t.bounds.mean(0) for t in tyres])
    mains = cs[abs(cs[:, 0]) > 10]
    nose = cs[abs(cs[:, 0]) < 10]
    out['main_track_half'] = float(abs(mains[:, 0]).mean())
    out['main_wheel_spacing'] = float(np.ptp(abs(mains[:, 0])))
    out['main_z'] = float(mains[:, 2].mean())
    out['nose_z_gear'] = float(nose[:, 2].mean())
    out['tyre_diameter'] = float(np.mean([t.extents[1] for t in tyres]))
    shells = body.split(only_watertight=False)
    fus = max(shells, key=lambda b: len(b.faces))
    out['fuselage_width'] = float(fus.extents[0])
    out['parts'] = [dict(name=p['name'], faces=int(len(p['faces'])), material=p['material']) for p in parts]
    out['separate_control_surfaces'] = False              # the wing and tail are single shells: see the README
    return out


def build(mesh):
    """The geometry in feet from the three sources."""
    g = {}
    k_len = LENGTH / mesh['extent_length']                  # mesh units to feet for everything on the fuselage
    k_span = SPAN / mesh['extent_span']                     # and along the wing's span
    w = mesh['wing']
    x = np.array([r['x'] for r in w])
    le = np.array([r['le_z'] for r in w])
    te = np.array([r['te_z'] for r in w])
    # the straight-tapered part: fit lines to the leading and trailing edges outboard of the root fillet
    outer = (x >= 40) & (x <= 200)
    le_fit = np.polyfit(x[outer], le[outer], 1)
    te_fit = np.polyfit(x[outer], te[outer], 1)
    half = mesh['half_span']
    c_centre = np.polyval(le_fit, 0) - np.polyval(te_fit, 0)
    c_tip = np.polyval(le_fit, half) - np.polyval(te_fit, half)
    area_trap_mesh = (c_centre + c_tip) * half              # both sides, mesh units squared
    # chords: scaled so the trapezoid has the published area. A fit to one published number.
    k_chord = AREA / (area_trap_mesh * k_span)
    taper = c_tip / c_centre
    cr, ct = c_centre * k_chord, c_tip * k_chord
    b = SPAN
    mac = 2.0 / 3.0 * cr * (1 + taper + taper ** 2) / (1 + taper)
    y_mac = b / 6.0 * (1 + 2 * taper) / (1 + taper)
    sweep_le = np.degrees(np.arctan(-le_fit[0] * k_chord / k_span))
    sweep_te = np.degrees(np.arctan(-te_fit[0] * k_chord / k_span))
    sweep_c4 = np.degrees(np.arctan((-le_fit[0] + 0.25 * (le_fit[0] - te_fit[0])) * k_chord / k_span))
    # the fillet: the real chord inboard of the break, as extra chord over the trapezoid, mostly at the trailing edge
    stations = []
    for r in w:
        ctrap = np.polyval(le_fit, r['x']) - np.polyval(te_fit, r['x'])
        stations.append(dict(y=round(r['x'] * k_span, 3), chord=round((r['le_z'] - r['te_z']) * k_chord, 3),
                             chord_trapezoid=round(ctrap * k_chord, 3),
                             le_ahead_of_trapezoid=round((r['le_z'] - np.polyval(le_fit, r['x'])) * k_chord, 3),
                             twist_deg=round(r['incidence'] - w[0]['incidence'], 2), mesh_tc=round(r['tc'], 3)))
    ys = np.array([s['y'] for s in stations])
    cs = np.array([s['chord'] for s in stations])
    y_all = np.concatenate([[0.0], ys, [b / 2]])
    c_all = np.concatenate([[cs[0]], cs, [ct]])
    area_gross = 2 * np.trapezoid(c_all, y_all)

    # along the length: the wing is placed by the leading edge of its root as NASA's side view draws it (the
    # fillet is all at the trailing edge, so the root's leading edge is the trapezoid's)
    root_le, root_te = sv_point(SV['wing_root_le']), sv_point(SV['wing_root_te'])
    x0 = root_le[0] + k_chord * w[0]['le_z']                # x_ft = x0 - k_chord * z_mesh on the wing
    le_centre_x = x0 - k_chord * np.polyval(le_fit, 0)
    mac_le_x = le_centre_x + y_mac * np.tan(np.radians(sweep_le))
    wing_z = (root_le[1] + root_te[1]) / 2
    g['wing'] = dict(span=b, area_reference=AREA, aspect_ratio=round(b * b / AREA, 2), root_chord_centreline=round(cr, 3),
                     tip_chord=round(ct, 3), taper=round(taper, 3), mac=round(mac, 3), y_mac=round(y_mac, 3),
                     sweep_le_deg=round(sweep_le, 2), sweep_quarter_deg=round(sweep_c4, 2),
                     sweep_te_deg=round(sweep_te, 2), dihedral_deg=0.0,
                     twist_root_to_tip_deg=round(stations[-3]['twist_deg'], 2),
                     area_with_fillet=round(area_gross, 1), le_centreline_x=round(le_centre_x, 3),
                     mac_le_x=round(mac_le_x, 3), mac_quarter_x=round(mac_le_x + 0.25 * mac, 3), z=round(wing_z, 3),
                     fillet_ends_y=round(40 * k_span, 2), section='LRN 1015', tc=TC, stations=stations,
                     chord_scale_ft_per_unit=round(k_chord, 5), span_scale_ft_per_unit=round(k_span, 5))

    # fuselage from the side view; width from the mesh
    top = [sv_point(p) for p in SV['top']]
    bot = [sv_point(p) for p in SV['bottom']]
    xs = np.linspace(0, LENGTH, 45)
    zt = np.interp(xs, [p[0] for p in top], [p[1] for p in top])
    zb = np.interp(xs, [p[0] for p in bot], [p[1] for p in bot])
    width = mesh['fuselage_width'] * k_len
    g['fuselage'] = dict(length=LENGTH, max_width=round(width, 3), max_depth=round(float((zt - zb).max()), 3),
                         side_area=round(float(np.trapezoid(zt - zb, xs)), 1),
                         profile=[dict(x=round(float(a), 3), z_top=round(float(t), 3), z_bottom=round(float(c), 3))
                                  for a, t, c in zip(xs, zt, zb)])
    ex_top, ex_bot = sv_point((SV['exhaust_x'], SV['exhaust_top'])), sv_point((SV['exhaust_x'], SV['exhaust_bottom']))
    inlet = sv_point(SV['inlet_lip'])
    g['nacelle'] = dict(inlet_x=round(inlet[0], 3), exhaust_x=round(ex_top[0], 3),
                        length=round(ex_top[0] - inlet[0], 3), diameter=round(ex_top[1] - ex_bot[1], 3),
                        thrust_line_z=round((ex_top[1] + ex_bot[1]) / 2, 3), top_z=round(sv_point((0, SV['nacelle_top']))[1], 3))

    # V-tail: height and chords from the side view, dihedral from the mesh
    dih = mesh['tail_dihedral_deg']
    tip_a, tip_f = sv_point((SV['fin_tip_x'][0], SV['fin_tip_y'])), sv_point((SV['fin_tip_x'][1], SV['fin_tip_y']))
    root_a, root_f = sv_point((SV['fin_root_x'][0], SV['fin_root_y'])), sv_point((SV['fin_root_x'][1], SV['fin_root_y']))
    hv = tip_f[1] - root_f[1]
    panel = hv / np.sin(np.radians(dih))
    c_r, c_t = root_a[0] - root_f[0], tip_a[0] - tip_f[0]
    area_panel = (c_r + c_t) / 2 * panel
    c_mean = (c_r + c_t) / 2
    x_c4_root, x_c4_tip = root_f[0] + 0.25 * c_r, tip_f[0] + 0.25 * c_t
    frac = (1 + 2 * c_t / c_r) / (3 * (1 + c_t / c_r))
    g['vtail'] = dict(dihedral_deg=round(dih, 1), panel_span=round(panel, 3), root_chord=round(c_r, 3),
                      tip_chord=round(c_t, 3), area_each=round(area_panel, 1), area_total=round(2 * area_panel, 1),
                      area_projected_horizontal=round(2 * area_panel * np.cos(np.radians(dih)) ** 2, 1),
                      area_projected_vertical=round(2 * area_panel * np.sin(np.radians(dih)) ** 2, 1),
                      root_z=round(root_f[1], 3), tip_z=round(tip_f[1], 3), root_y=round(mesh['fuselage_width'] * k_len / 4, 3),
                      root_le_x=round(root_f[0], 3), tip_le_x=round(tip_f[0], 3), mean_chord=round(c_mean, 3),
                      quarter_x=round(x_c4_root + frac * (x_c4_tip - x_c4_root), 3),
                      quarter_z=round(root_f[1] + frac * hv, 3), section='symmetric, 10 % thick (assumed)')
    g['vtail']['arm_from_wing_quarter'] = round(g['vtail']['quarter_x'] - g['wing']['mac_quarter_x'], 3)
    g['vtail']['horizontal_volume'] = round(g['vtail']['area_projected_horizontal'] * g['vtail']['arm_from_wing_quarter']
                                            / (AREA * mac), 3)
    g['vtail']['vertical_volume'] = round(g['vtail']['area_projected_vertical'] * g['vtail']['arm_from_wing_quarter']
                                          / (AREA * b), 4)

    # gear: along the length and in height from the side view, track from the mesh
    main, nose = sv_point(SV['main_axle']), sv_point(SV['nose_axle'])
    g['gear'] = dict(main_x=round(main[0], 3), nose_x=round(nose[0], 3), wheelbase=round(main[0] - nose[0], 3),
                     main_track=round(2 * mesh['main_track_half'] * k_len, 3),
                     main_wheel_spacing=round(mesh['main_wheel_spacing'] * k_len, 3),
                     main_wheel_diameter=round(2 * SV['main_wheel_radius'] * FT_PER_PX, 3),
                     nose_wheel_diameter=round(2 * SV['nose_wheel_radius'] * FT_PER_PX, 3),
                     main_axle_z=round(main[1], 3), nose_axle_z=round(nose[1], 3), wheels='two per main leg, two on the nose leg')
    g['side_view'] = dict(symbol_x=round(sv_point(SV['symbol'])[0], 3), symbol_z=round(sv_point(SV['symbol'])[1], 3),
                          symbol_percent_mac=round(100 * (sv_point(SV['symbol'])[0] - mac_le_x) / mac, 1),
                          height=round((PX_GROUND - PX_TOP) * FT_PER_PX, 3),
                          root_chord_as_drawn=round(root_te[0] - root_le[0], 3), ft_per_px=round(FT_PER_PX, 5))
    g['mesh'] = mesh
    g['mesh_scale'] = dict(by_span_ft_per_unit=round(k_span, 5), by_length_ft_per_unit=round(k_len, 5),
                           length_if_scaled_by_span=round(mesh['extent_length'] * k_span, 2),
                           height_if_scaled_by_span=round(mesh['extent_height'] * k_span, 2),
                           span_if_scaled_by_length=round(mesh['extent_span'] * k_len, 2),
                           height_if_scaled_by_length=round(mesh['extent_height'] * k_len, 2),
                           wing_area_if_scaled_by_span=round(area_trap_mesh * k_span ** 2, 1),
                           wing_area_if_chords_by_length=round(area_trap_mesh * k_span * k_len, 1))
    return g


# ---- mass: a build-up of estimates that adds up to the published weights
def wing_tank_volume(g):
    """Volume of the wing box between 15 and 60 % chord, out to 90 % of the semi-span, both sides, ft3.

    The section's area between two chord fractions is taken as 0.85 * t/c * c2 * (width): the LRN 1015 is close to
    its full thickness over that stretch.
    """
    w = g['wing']
    y = np.linspace(g['fuselage']['max_width'] / 2, 0.9 * w['span'] / 2, 200)
    c = w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * y / (w['span'] / 2)
    return float(2 * np.trapezoid(0.85 * TC * c * c * 0.45, y)), y, c


def mass_model(g):
    w, f, n, t, gear = g['wing'], g['fuselage'], g['nacelle'], g['vtail'], g['gear']
    vol, y, c = wing_tank_volume(g)
    wing_fuel = min(vol * FUEL_DENSITY * 0.95, W_FUEL)     # 5 % for structure and ullage
    fus_fuel = W_FUEL - wing_fuel
    half = w['span'] / 2
    zc = w['z']
    xw = w['mac_le_x'] + 0.42 * w['mac']                   # wing structure and wing fuel act near 42 % chord
    items = []

    def add(name, weight, x, yy, z, ixx=0.0, iyy=0.0, izz=0.0, kind='empty'):
        items.append(dict(name=name, weight=round(weight, 1), x=round(x, 3), y=round(yy, 3), z=round(z, 3),
                          ixx=round(ixx, 1), iyy=round(iyy, 1), izz=round(izz, 1), kind=kind))

    def slug(lb):
        return lb / 32.174

    # the wing's and its fuel's own inertia: mass spread along the span in proportion to chord squared
    def span_inertia(weight, y0, y1):
        yy = np.linspace(y0, y1, 200)
        cc = w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * yy / half
        m = cc * cc
        m = m / np.trapezoid(m, yy) * slug(weight) / 2      # per side
        return float(2 * np.trapezoid(m * yy * yy, yy))

    empty_split = dict(wing=0.24, fuselage=0.22, vtail=0.03, nacelle=0.05, gear=0.055)   # of the empty weight: estimates
    ww = empty_split['wing'] * W_EMPTY
    ixx = span_inertia(ww, 0, half)
    add('wing structure', ww, xw, 0, zc, ixx, slug(ww) * w['mac'] ** 2 / 12, ixx)
    wf = empty_split['fuselage'] * W_EMPTY
    add('fuselage structure', wf, 0.47 * LENGTH, 0, 5.0, slug(wf) * (f['max_width'] / 2) ** 2 / 2,
        slug(wf) * LENGTH ** 2 / 12, slug(wf) * LENGTH ** 2 / 12)
    wt = empty_split['vtail'] * W_EMPTY
    it = slug(wt) * t['panel_span'] ** 2 / 12
    add('V-tail', wt, t['quarter_x'] + 0.15 * t['mean_chord'], 0, t['quarter_z'], it * 2, it, it)
    add('engine', W_ENGINE, n['inlet_x'] + 0.55 * n['length'], 0, n['thrust_line_z'], slug(W_ENGINE) * 1.6 ** 2 / 2,
        slug(W_ENGINE) * 9.6 ** 2 / 12, slug(W_ENGINE) * 9.6 ** 2 / 12)
    wn = empty_split['nacelle'] * W_EMPTY
    add('nacelle and engine installation', wn, n['inlet_x'] + 0.5 * n['length'], 0, n['thrust_line_z'], 0,
        slug(wn) * n['length'] ** 2 / 12, slug(wn) * n['length'] ** 2 / 12)
    wg = empty_split['gear'] * W_EMPTY
    add('main gear', 0.8 * wg, gear['main_x'], 0, 2.2, slug(0.8 * wg) * (gear['main_track'] / 2) ** 2, 0,
        slug(0.8 * wg) * (gear['main_track'] / 2) ** 2)
    add('nose gear', 0.2 * wg, gear['nose_x'], 0, 2.2)
    rest = W_EMPTY - sum(i['weight'] for i in items)
    payload = W_GROSS - W_EMPTY - W_FUEL
    x_payload = 0.35 * LENGTH                               # the bays are in the nose, under the belly and in the tail
    # Where the systems sit isn't known. They are put where the aircraft without fuel balances at ZERO_FUEL_CG of
    # the mean chord: a choice, as the designers will have balanced it, to be looked at again with the neutral point.
    target = w['mac_le_x'] + ZERO_FUEL_CG * w['mac']
    moment = sum(i['weight'] * i['x'] for i in items) + payload * x_payload
    x_rest = (target * (W_EMPTY + payload) - moment) / rest
    add('systems, avionics, antennas (the rest of the empty weight)', rest, x_rest, 0, 5.5, 0,
        slug(rest) * (0.6 * LENGTH) ** 2 / 12, slug(rest) * (0.6 * LENGTH) ** 2 / 12)
    add('payload and its fittings', payload, x_payload, 0, 5.5, 0, slug(payload) * (0.5 * LENGTH) ** 2 / 12,
        slug(payload) * (0.5 * LENGTH) ** 2 / 12, kind='payload')
    y0, y1 = f['max_width'] / 2, 0.9 * half
    ixf = span_inertia(wing_fuel, y0, y1)
    add('wing fuel', wing_fuel, xw, 0, zc, ixf, 0, ixf, kind='fuel')
    add('fuselage fuel', fus_fuel, w['mac_le_x'] + 0.25 * w['mac'], 0, 5.0, 0, slug(fus_fuel) * 12.0 ** 2 / 12,
        slug(fus_fuel) * 12.0 ** 2 / 12, kind='fuel')

    def totals(fuel_fraction):
        tot = np.zeros(4)
        sel = []
        for i in items:
            k = fuel_fraction if i['kind'] == 'fuel' else 1.0
            sel.append((i, k))
            tot += k * i['weight'] * np.array([1, i['x'], i['y'], i['z']])
        wsum = tot[0]
        cg = tot[1:] / wsum
        I = np.zeros(3)
        for i, k in sel:
            m = slug(k * i['weight'])
            d = np.array([i['x'], i['y'], i['z']]) - cg
            I += k * np.array([i['ixx'], i['iyy'], i['izz']])
            I += m * np.array([d[1] ** 2 + d[2] ** 2, d[0] ** 2 + d[2] ** 2, d[0] ** 2 + d[1] ** 2])
        return dict(fuel_fraction=fuel_fraction, weight=round(float(wsum), 1), cg_x=round(float(cg[0]), 3),
                    cg_z=round(float(cg[2]), 3), cg_percent_mac=round(float(100 * (cg[0] - w['mac_le_x']) / w['mac']), 1),
                    ixx=round(float(I[0]), 0), iyy=round(float(I[1]), 0), izz=round(float(I[2]), 0),
                    nose_gear_load_percent=round(float(100 * (gear['main_x'] - cg[0]) / gear['wheelbase']), 1))
    return dict(published=dict(gross=W_GROSS, empty=W_EMPTY, fuel=W_FUEL, engine=W_ENGINE),
                derived=dict(payload_and_fittings=payload, wing_tank_volume_ft3=round(vol, 1),
                             wing_fuel=round(wing_fuel, 0), fuselage_fuel=round(fus_fuel, 0)),
                empty_weight_split=empty_split, items=items,
                states=[totals(1.0), totals(0.5), totals(0.1), totals(0.0)],
                note='Every weight but the four published ones, every position and every inertia is an estimate. '
                     'Fuel is burned from both tank groups in proportion in these states.')


def plot(g, m, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(13, 13))
    w = g['wing']
    for s in (1, -1):
        y = [0] + [st['y'] for st in w['stations']] + [w['span'] / 2]
        tan = np.tan(np.radians(w['sweep_le_deg']))
        le = [w['le_centreline_x'] + yy * tan for yy in y]
        lead = [le[0] - w['stations'][0]['le_ahead_of_trapezoid']] + \
               [l - st['le_ahead_of_trapezoid'] for l, st in zip(le[1:-1], w['stations'])] + [le[-1]]
        ch = [w['stations'][0]['chord']] + [st['chord'] for st in w['stations']] + [w['tip_chord']]
        ax[0].plot(np.array(y) * s, lead, 'k')
        ax[0].plot(np.array(y) * s, np.array(lead) + np.array(ch), 'k')
    f = g['fuselage']
    half = f['max_width'] / 2
    ax[0].plot([-half, -half, half, half], [3, LENGTH - 3, LENGTH - 3, 3], 'b', lw=0.8)
    ax[0].plot([0], [w['mac_quarter_x']], 'r+', ms=12)
    for st in m['states']:
        ax[0].plot([0], [st['cg_x']], 'go', ms=4)
    ax[0].plot([g['gear']['main_track'] / 2, -g['gear']['main_track'] / 2, 0],
               [g['gear']['main_x'], g['gear']['main_x'], g['gear']['nose_x']], 'ms')
    ax[0].invert_yaxis()
    ax[0].set_aspect('equal')
    ax[0].set_title('planform (ft): wing as built, fuselage box, gear, MAC quarter chord (+), centre of gravity states')
    x = [p['x'] for p in f['profile']]
    ax[1].plot(x, [p['z_top'] for p in f['profile']], 'k')
    ax[1].plot(x, [p['z_bottom'] for p in f['profile']], 'k')
    n, t = g['nacelle'], g['vtail']
    ax[1].plot([n['inlet_x'], n['exhaust_x']], [n['thrust_line_z']] * 2, 'r--')
    ax[1].plot([t['root_le_x'], t['tip_le_x'], t['tip_le_x'] + t['tip_chord'], t['root_le_x'] + t['root_chord']],
               [t['root_z'], t['tip_z'], t['tip_z'], t['root_z']], 'k')
    ax[1].plot([g['gear']['main_x'], g['gear']['nose_x']], [g['gear']['main_axle_z'], g['gear']['nose_axle_z']], 'mo')
    ax[1].plot([w['mac_le_x'], w['mac_le_x'] + w['mac']], [w['z']] * 2, 'b', lw=3)
    for st in m['states']:
        ax[1].plot([st['cg_x']], [st['cg_z']], 'go', ms=4)
    ax[1].axhline(0, color='gray')
    ax[1].set_aspect('equal')
    ax[1].set_title('side (ft): fuselage outline, thrust line, fin, axles, MAC, centre of gravity states')
    plt.tight_layout()
    plt.savefig(path, dpi=100)


def main():
    mesh = mesh_measure()
    if mesh is None:
        mesh = json.load(open(OUT_GEOM))['mesh']
    g = build(mesh)
    m = mass_model(g)
    json.dump(g, open(OUT_GEOM, 'w'), indent=1)
    json.dump(m, open(OUT_MASS, 'w'), indent=1)
    w, t, gear = g['wing'], g['vtail'], g['gear']
    print('wing: centreline chord %.2f ft, tip %.2f, taper %.3f, MAC %.2f at y %.2f; sweep LE %.1f, c/4 %.1f deg; '
          'twist %.1f deg; area with fillet %.0f ft2' % (w['root_chord_centreline'], w['tip_chord'], w['taper'], w['mac'],
                                                       w['y_mac'], w['sweep_le_deg'], w['sweep_quarter_deg'],
                                                       w['twist_root_to_tip_deg'], w['area_with_fillet']))
    print('      MAC leading edge at x %.2f ft, quarter chord %.2f; wing height %.2f' % (w['mac_le_x'], w['mac_quarter_x'], w['z']))
    print('V-tail: dihedral %.1f deg, panel %.2f ft, chords %.2f/%.2f, area %.1f ft2 each; volumes %.3f, %.4f' % (
        t['dihedral_deg'], t['panel_span'], t['root_chord'], t['tip_chord'], t['area_each'], t['horizontal_volume'],
        t['vertical_volume']))
    print('gear: main x %.2f, nose x %.2f, wheelbase %.2f, track %.2f ft' % (gear['main_x'], gear['nose_x'],
                                                                         gear['wheelbase'], gear['main_track']))
    print('fuselage: width %.2f, depth %.2f; nacelle %.1f ft long, thrust line z %.2f' % (
        g['fuselage']['max_width'], g['fuselage']['max_depth'], g['nacelle']['length'], g['nacelle']['thrust_line_z']))
    d = m['derived']
    print('fuel: wing box %.0f ft3 holds %.0f lb; fuselage tanks %.0f lb' % (d['wing_tank_volume_ft3'], d['wing_fuel'],
                                                                            d['fuselage_fuel']))
    for s in m['states']:
        print('  fuel %3.0f %%: %6.0f lb, CG x %.2f ft (%.1f %% MAC), z %.2f; Ixx %.0f Iyy %.0f Izz %.0f slug ft2; '
              'nose gear %.1f %%' % (100 * s['fuel_fraction'], s['weight'], s['cg_x'], s['cg_percent_mac'], s['cg_z'],
                                     s['ixx'], s['iyy'], s['izz'], s['nose_gear_load_percent']))
    if '--plot' in sys.argv:
        os.makedirs(os.path.join(HERE, 'out'), exist_ok=True)
        plot(g, m, os.path.join(HERE, 'out', 'geometry.png'))


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    main()
