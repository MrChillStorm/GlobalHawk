#!/usr/bin/env python3
"""A wall-resolved mesh of the LRN 1015 for SU2: python3 fdm/cfd/mesh_lrn1015.py OUT.su2 [first_cell]

Chord 1, the section as fdm/data/lrn1015.dat but with a trailing edge 0.0008 thick (a sharp edge does not take a boundary-layer
mesh), a far field 60 chords out, quadrilateral layers in the boundary layer (first cell 1e-5 by default: y+ about 1 at Reynolds 2
million, growth 1.18, 45 layers) and triangles outside. Physical groups: airfoil, farfield.
"""
import math
import os
import sys

import gmsh
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TE_HALF = 0.0004


def build(out, first=1e-5, layers=45, ratio=1.18, far=60.0, ds_surface=0.004):
    xy = np.loadtxt(os.path.join(HERE, '..', 'data', 'lrn1015.dat'))
    le = int(np.argmin(xy[:, 0]))
    up, lo = xy[:le + 1].copy(), xy[le:].copy()
    up[0] = (1.0, TE_HALF)
    lo[-1] = (1.0, -TE_HALF)
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 0)
    g = gmsh.model.geo
    pu = [g.addPoint(x, y, 0, ds_surface) for x, y in up]
    pl = [g.addPoint(x, y, 0, ds_surface) for x, y in lo[1:]]
    cu = g.addSpline(pu)                                   # trailing edge (upper) to the leading edge
    cl = g.addSpline([pu[-1]] + pl)                        # leading edge to the trailing edge (lower)
    cte = g.addLine(pl[-1], pu[0])
    centre = g.addPoint(0.5, 0, 0)
    ring = [g.addPoint(0.5 + far * math.cos(a), far * math.sin(a), 0, 6.0) for a in (0, math.pi / 2, math.pi, 1.5 * math.pi)]
    arcs = [g.addCircleArc(ring[i], centre, ring[(i + 1) % 4]) for i in range(4)]
    outer = g.addCurveLoop(arcs)
    inner = g.addCurveLoop([cu, cl, cte])
    surf = g.addPlaneSurface([outer, inner])
    g.synchronize()
    gmsh.model.addPhysicalGroup(1, [cu, cl, cte], 1, 'airfoil')
    gmsh.model.addPhysicalGroup(1, arcs, 2, 'farfield')
    gmsh.model.addPhysicalGroup(2, [surf], 3, 'fluid')
    f = gmsh.model.mesh.field
    bl = f.add('BoundaryLayer')
    f.setNumbers(bl, 'CurvesList', [cu, cl, cte])
    f.setNumber(bl, 'Quads', 1)
    f.setNumber(bl, 'hwall_n', first)
    f.setNumber(bl, 'ratio', ratio)
    f.setNumber(bl, 'thickness', first * (ratio ** layers - 1) / (ratio - 1))
    f.setNumber(bl, 'IntersectMetrics', 0)
    f.setNumbers(bl, 'PointsList', [pu[0], pl[-1]])          # fans at the two corners of the trailing edge
    f.setAsBoundaryLayer(bl)
    d = f.add('Distance')
    f.setNumbers(d, 'CurvesList', [cu, cl, cte])
    f.setNumber(d, 'Sampling', 200)
    th = f.add('Threshold')
    f.setNumber(th, 'InField', d)
    f.setNumber(th, 'SizeMin', ds_surface)
    f.setNumber(th, 'SizeMax', 6.0)
    f.setNumber(th, 'DistMin', 0.05)
    f.setNumber(th, 'DistMax', far)
    bg = f.add('Min')
    f.setNumbers(bg, 'FieldsList', [th])
    f.setAsBackgroundMesh(bg)
    gmsh.option.setNumber('Mesh.Algorithm', 6)
    gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary', 0)
    gmsh.option.setNumber('Mesh.MeshSizeFromPoints', 0)
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 0)
    gmsh.model.mesh.generate(2)
    gmsh.model.mesh.optimize('Laplace2D', False, 2)
    gmsh.write(out)
    n_el = len(gmsh.model.mesh.getElements(2)[1][0]) if gmsh.model.mesh.getElements(2)[1] else 0
    types = gmsh.model.mesh.getElements(2)[0]
    counts = {int(t): len(e) for t, e in zip(types, gmsh.model.mesh.getElements(2)[1])}
    q = gmsh.model.mesh.getElementQualities(gmsh.model.mesh.getElements(2)[1][0], 'minSICN') if len(types) else []
    gmsh.finalize()
    return counts, float(np.min(q)) if len(q) else None


if __name__ == '__main__':
    out = sys.argv[1]
    first = float(sys.argv[2]) if len(sys.argv) > 2 else 1e-5
    print(build(out, first))
