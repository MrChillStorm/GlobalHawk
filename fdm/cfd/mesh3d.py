#!/usr/bin/env python3
"""A coarse unstructured mesh of the whole aircraft for an Euler run in SU2: python3 fdm/cfd/mesh3d.py OUT.su2 [scale]

Wing (the strip model's stations, LRN 1015 sections, twist and the wing's 2 deg of incidence), fuselage (the drawing's profile as ellipses), the two V-tail
panels (NACA 0010 sections, the tail's incidence), fused into one solid; no nacelle, gear or control-surface gaps. Metres, x aft from the nose, y to the right,
z up. Physical groups: wing, fuselage, vtail, farfield (a sphere of 6 spans). `scale` multiplies every size (2 for a coarser mesh).
"""
import math
import os
import sys
import time

import gmsh
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import aero_ref as R  # noqa: E402

FT = 0.3048
G = R.G


def airfoil_xy():
    xy = np.loadtxt(os.path.join(HERE, '..', 'data', 'lrn1015.dat'))
    le = int(np.argmin(xy[:, 0]))
    return xy[:le + 1], xy[le:]


def naca00(tc, n=40):
    x = np.linspace(0, 1, n)
    t = 5 * tc * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
    up = np.column_stack([x[::-1], t[::-1]])
    lo = np.column_stack([x, -t])
    return up, lo


def section_wire(up, lo, le, chord, twist_deg, pivot=0.25, mirror_y=False):
    """A closed wire (two splines meeting at the leading and trailing edge) in the plane y = le[1]; le = (x, y, z) in metres."""
    th = math.radians(twist_deg)
    def place(xy):
        dx, dz = (xy[:, 0] - pivot) * chord, xy[:, 1] * chord
        x = le[0] + pivot * chord + dx * math.cos(th) + dz * math.sin(th)
        z = le[2] - dx * math.sin(th) + dz * math.cos(th)
        return np.column_stack([x, np.full(len(x), le[1]), z])
    pu, pl = place(up), place(lo)
    occ = gmsh.model.occ
    p_up = [occ.addPoint(*p) for p in pu]
    p_lo = [p_up[-1]] + [occ.addPoint(*p) for p in pl[1:-1]] + [p_up[0]]
    c1 = occ.addSpline(p_up)
    c2 = occ.addSpline(p_lo)
    return occ.addWire([c1, c2])


def build(out, scale=1.0, far_spans=6.0):
    T0 = time.time()
    w, t, f = G['wing'], G['vtail'], G['fuselage']
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 0)
    occ = gmsh.model.occ
    up, lo = airfoil_xy()
    half = w['span'] / 2
    ail_in, ail_out = R.AIL['inner'] * half, R.AIL['outer'] * half
    ys = sorted(set([0.0] + [s['y'] for s in w['stations'] if s['y'] < 56.0] + [ail_in, ail_out, half]))
    st_y = np.array([s['y'] for s in w['stations']])
    tan_le = math.tan(math.radians(w['sweep_le_deg']))
    secs = []
    for y in ys:
        ctrap = w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * y / half
        chord = float(np.interp(y, st_y, [s['chord'] for s in w['stations']])) if y >= st_y[0] else w['stations'][0]['chord']
        chord = max(chord, ctrap) if y < w['fillet_ends_y'] else ctrap
        twist = float(np.interp(y, st_y, [s['twist_deg'] for s in w['stations']])) + R.WING_INCIDENCE
        secs.append((y, chord, twist))
    wires = []
    for sign in (-1, 1):
        for y, chord, twist in (secs[::-1] if sign < 0 else secs):
            if sign < 0 and y == 0.0:
                continue
            le = ((w['le_centreline_x'] + y * tan_le) * FT, sign * y * FT, w['z'] * FT)
            wires.append(section_wire(up, lo, le, chord * FT, twist))
    # the wing from the left tip to the right tip: the centre section was added once (from the right half's list)
    wing = occ.addThruSections(wires, makeSolid=True, makeRuled=True)
    # the fuselage: ellipses at the profile's stations
    prof = f['profile']
    depth = np.array([p['z_top'] - p['z_bottom'] for p in prof])
    rings, xs = [], []
    for p, d in zip(prof, depth):
        wd = max(f['max_width'] * min(1.0, d / (0.75 * depth.max())), 0.05)
        h = max(d, 0.05)
        xc, zc = p['x'] * FT, (p['z_top'] + p['z_bottom']) / 2 * FT
        if xs and xc <= xs[-1] + 1e-6:
            continue
        xs.append(xc)
        rings.append((xc, zc, wd / 2 * FT, h / 2 * FT))
    wires_f = []
    for xc, zc, a, b in rings:
        r1, r2 = (a, b) if a >= b else (b, a)
        xa = [0, 1, 0] if a >= b else [0, 0, 1]
        e = occ.addEllipse(xc, 0, zc, r1, r2, zAxis=[1, 0, 0], xAxis=xa)
        wires_f.append(occ.addWire([e]))
    fus = occ.addThruSections(wires_f, makeSolid=True, makeRuled=False)
    # the V-tail
    tup, tlo = naca00(R.TAIL_TC)
    dih = math.radians(t['dihedral_deg'])
    tails = []
    for side in (1, -1):
        root = (t['root_le_x'] * FT, side * t['root_y'] * FT, t['root_z'] * FT)
        tip = (t['tip_le_x'] * FT, side * (t['root_y'] + t['panel_span'] * math.cos(dih)) * FT, t['tip_z'] * FT)
        w1 = section_wire(tup, tlo, root, t['root_chord'] * FT, R.TAIL_INCIDENCE)
        w2 = section_wire(tup, tlo, tip, t['tip_chord'] * FT, R.TAIL_INCIDENCE)
        tails.append(occ.addThruSections([w1, w2], makeSolid=True, makeRuled=True))
    body, _ = occ.fuse([(3, wing[0][1])], [(3, fus[0][1])] + [(3, tl[0][1]) for tl in tails])
    occ.synchronize()
    # farfield
    far = far_spans * w['span'] * FT
    sph = occ.addSphere(0.5 * w['mac_le_x'] * FT + 20, 0, 0, far)
    flow, _ = occ.cut([(3, sph)], body, removeTool=False)
    occ.synchronize()
    surfs = gmsh.model.getBoundary(flow, oriented=False)
    groups = dict(wing=[], fuselage=[], vtail=[], farfield=[])
    for dim, tag in surfs:
        box = gmsh.model.getBoundingBox(dim, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = box
        if (xmax - xmin) > 0.8 * far:
            groups['farfield'].append(tag)
        elif xmin > (t['root_le_x'] - 0.5) * FT and zmin > (t['root_z'] - 1.0) * FT and (ymax - ymin) > 0.2 and abs(ymin) > 0.2 * 0 and zmax > t['root_z'] * FT + 0.3:
            groups['vtail'].append(tag)
        elif (ymax - ymin) > 2.2 * f['max_width'] * FT / 2 + 1.0 or (xmax - xmin) > 0 and (ymax - ymin) > 3.0:
            groups['wing'].append(tag)
        else:
            groups['fuselage'].append(tag)
    print({k: len(v) for k, v in groups.items()})
    for i, (k, v) in enumerate(groups.items(), 1):
        if v:
            gmsh.model.addPhysicalGroup(2, v, i, k)
    gmsh.model.addPhysicalGroup(3, [t for _, t in flow], 10, 'fluid')
    # sizes
    s = scale
    fld = gmsh.model.mesh.field
    d = fld.add('Distance')
    fld.setNumbers(d, 'SurfacesList', groups['wing'] + groups['fuselage'] + groups['vtail'])
    fld.setNumber(d, 'Sampling', 50)
    th = fld.add('Threshold')
    fld.setNumber(th, 'InField', d)
    fld.setNumber(th, 'SizeMin', 0.10 * s)
    fld.setNumber(th, 'SizeMax', 30.0)
    fld.setNumber(th, 'DistMin', 0.3)
    fld.setNumber(th, 'DistMax', far)
    fld.setAsBackgroundMesh(th)
    gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary', 0)
    gmsh.option.setNumber('Mesh.MeshSizeFromPoints', 0)
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 0)
    gmsh.option.setNumber('Mesh.Algorithm', 6)
    gmsh.option.setNumber('Mesh.Algorithm3D', 1)
    print('geometry ready %.0f s' % (time.time() - T0), flush=True)
    gmsh.model.mesh.generate(2)
    print('surface mesh %.0f s, %d nodes' % (time.time() - T0, len(gmsh.model.mesh.getNodes()[0])), flush=True)
    gmsh.model.mesh.generate(3)
    print('volume mesh %.0f s' % (time.time() - T0), flush=True)
    gmsh.write(out)
    n_tet = sum(len(e) for t_, e in zip(*gmsh.model.mesh.getElements(3)[:2]))
    gmsh.finalize()
    return n_tet


if __name__ == '__main__':
    print('tetrahedra:', build(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 1.0))
