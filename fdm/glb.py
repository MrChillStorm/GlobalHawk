"""Read NASA's 3-D model of the Global Hawk (a Draco-compressed .glb) into plain arrays.

    parts = load()      list of dicts: name, material, vertices (n,3) in the file's units and axes, faces (m,3)

Needs trimesh and DracoPy. The model itself (NASA 3D Resources) is not in the repository.
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
GLB = os.path.join(HERE, '..', 'refs', 'model3d', 'NASA-3D-Global-Hawk.glb')


def load(path=GLB):
    import trimesh
    scene = trimesh.load(path)
    parts = []
    for node in scene.graph.nodes_geometry:
        T, gname = scene.graph[node]
        m = scene.geometry[gname]
        mat = getattr(getattr(m.visual, 'material', None), 'name', None)
        parts.append(dict(name=gname, material=mat, vertices=trimesh.transform_points(m.vertices, T),
                          faces=np.asarray(m.faces)))
    return parts


if __name__ == '__main__':
    import trimesh
    allv = []
    for p in load():
        v = p['vertices']
        allv.append(v)
        m = trimesh.Trimesh(v, p['faces'], process=False)
        bodies = m.split(only_watertight=False)
        print('%-14s %6d faces %4d pieces  x %8.3f..%8.3f  y %8.3f..%8.3f  z %8.3f..%8.3f  %s' % (
            p['name'], len(p['faces']), len(bodies), v[:, 0].min(), v[:, 0].max(), v[:, 1].min(), v[:, 1].max(),
            v[:, 2].min(), v[:, 2].max(), p['material']))
    v = np.vstack(allv)
    print('all: extents', (v.max(0) - v.min(0)).round(4), 'min', v.min(0).round(4), 'max', v.max(0).round(4))
