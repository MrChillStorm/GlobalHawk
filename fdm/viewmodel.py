#!/usr/bin/env python3
"""Pictures of the 3-D model without FlightGear: a small z-buffer renderer, so that the model can be looked at (and
its moving parts turned) while it is being built.

    python3 fdm/viewmodel.py out.png            four views, gear down
    from viewmodel import render                render(objs, anims, az, el, centre, size_ft, gear=1.0) -> image array

Orthographic, flat-shaded with a little of each vertex's smooth normal mixed in, lit from above and ahead of the
camera. It shows shapes, joins, gaps and where parts are; it does not show FlightGear's own shading.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
COLOURS = {0: (0.93, 0.93, 0.95), 1: (0.66, 0.70, 0.76), 2: (0.28, 0.29, 0.33), 3: (0.07, 0.07, 0.07)}


def rotation(axis, angle_deg, origin, pts):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = math.radians(angle_deg)
    p = pts - origin
    return origin + p * math.cos(t) + np.cross(a, p) * math.sin(t) + np.outer(p @ a, a) * (1 - math.cos(t))


def posed(objs, anims, gear=1.0, aileron=0.0, pitch=0.0, spoiler=0.0):
    """Vertices of every object with its animations applied as FlightGear would: the last one listed nearest the
    object, the first outermost, each about its axis as it lies in the model at rest. gear: 1 down, 0 up."""
    out = []
    for o in objs:
        mine = [a for a in anims if a['obj'] == o.name]
        if any(a.get('hide_up') and gear <= a['hide_up'] for a in mine):
            continue
        v = o.mesh.vertices.copy()
        for a in reversed(mine):
            if a.get('hide_up') or a.get('spin'):
                continue
            if 'table' in a:
                deg = float(np.interp(gear, [e[0] for e in a['table']], [e[1] for e in a['table']]))
            elif 'expr' in a:
                deg = a['down'] * pitch
            elif 'aileron' in a['prop']:
                deg = a['factor'] * a['down'] * aileron
            else:
                deg = a['factor'] * a['down'] * spoiler
            v = rotation(a['b'] - a['a'], deg, a['a'], v)
        out.append((o, v))
    return out


def render(objs, anims, az, el, centre, size_ft, px=900, **pose):
    """az: where the camera stands, deg round from the nose (0 ahead, 90 to the right, 180 behind); el: deg above."""
    a, e = math.radians(az), math.radians(el)
    to_cam = np.array([-math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)])     # x is aft: ahead is -x
    right = np.cross((0, 0, 1.0), to_cam)
    right /= np.linalg.norm(right)
    up = np.cross(to_cam, right)
    light = to_cam + 0.6 * up + 0.3 * right
    light /= np.linalg.norm(light)
    img = np.ones((px, px, 3)) * np.array([0.42, 0.55, 0.72])
    zbuf = np.full((px, px), -1e9)
    s = px / size_ft
    for o, v in posed(objs, anims, **pose):
        p = v - np.asarray(centre, float)
        sx, sy, sz = (p @ right) * s + px / 2, px / 2 - (p @ up) * s, p @ to_cam
        tri = o.mesh.faces
        n = np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]])
        n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
        shade = 0.35 + 0.65 * np.abs(n @ light)
        col = np.array(COLOURS[o.mat])
        for k, (i0, i1, i2) in enumerate(tri):
            x = np.array([sx[i0], sx[i1], sx[i2]])
            y = np.array([sy[i0], sy[i1], sy[i2]])
            x0, x1, y0, y1 = int(max(x.min(), 0)), int(min(x.max() + 1, px - 1)), int(max(y.min(), 0)), int(min(y.max() + 1, px - 1))
            if x0 > x1 or y0 > y1:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
            if abs(d) < 1e-9:
                continue
            w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / d
            w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / d
            w2 = 1 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            z = w0 * sz[i0] + w1 * sz[i1] + w2 * sz[i2]
            zb = zbuf[y0:y1 + 1, x0:x1 + 1]
            hit = inside & (z > zb)
            zb[hit] = z[hit]
            img[y0:y1 + 1, x0:x1 + 1][hit] = col * shade[k]
    return img


def sheet(path, views, objs, anims, cols=2, px=700):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = (len(views) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 6.5, rows * 6.5), dpi=110, squeeze=False)
    for ax in axes.ravel():
        ax.axis('off')
    for ax, (title, kw) in zip(axes.ravel(), views):
        ax.imshow(render(objs, anims, px=px, **kw))
        ax.set_title(title, fontsize=11)
    plt.tight_layout()
    plt.savefig(path)


if __name__ == '__main__':
    import mkmodel as M
    objs, anims, _ = M.build()
    sheet(sys.argv[1], [('front quarter', dict(az=40, el=18, centre=(22, 0, 6), size_ft=125)), ('rear quarter', dict(az=215, el=15, centre=(26, 0, 6), size_ft=70)),
                        ('from above', dict(az=0.1, el=89, centre=(24, 0, 5), size_ft=125)), ('from the side', dict(az=90, el=2, centre=(22, 0, 7), size_ft=52))], objs, anims)
    print('wrote', sys.argv[1])
