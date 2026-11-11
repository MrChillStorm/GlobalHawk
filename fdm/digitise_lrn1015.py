#!/usr/bin/env python3
"""Digitise the measured points of the LRN 1015 from NASA TM 102840 (Hicks and Cliff, 1991), figure 24.

Each case in the figure is a row of three plots with the same lift axis: lift against angle of attack, the drag
polar and the pitching moment about the quarter chord. The measurements are the filled circles. The page is
rendered from the PDF (pdftoppm), the three frames are found from their long straight edges, and the circles are
what is left of the dark pixels when thin lines are eroded away. Circles that touch come out as one point.

    python3 fdm/digitise_lrn1015.py          writes fdm/data/lrn1015_tunnel.json, draws fdm/out/lrn1015_digitised.png

The report is not in the repository (NASA NTRS 19910007688).
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, '..', 'refs', 'other', 'NTRS-19910007688-TM102840-LRN1015-CFD-codes-and-tunnel-data.pdf')
OUT = os.path.join(HERE, 'data', 'lrn1015_tunnel.json')
DPI = 300
# page of the PDF, row on the page (0 top, 1 bottom), Mach, Reynolds number, moment at the right edge of its frame.
# Only the cases whose axes were read off the page by eye: the frames' edges are the ends of the axes there, lift
# from -0.4 to 1.6, angle of attack from -10 to 20 deg, drag from 0 to 0.12. The Mach 0.5 pages and the other
# Mach 0.2 case use other scales and are left out.
CASES = [(45, 1, 0.20, 1.0e6, -0.12), (50, 0, 0.60, 1.0e6, -0.16), (50, 1, 0.60, 2.0e6, -0.16)]
CL_AXIS = (-0.4, 1.6)


def page(n):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(['pdftoppm', '-f', str(n), '-l', str(n), '-r', str(DPI), '-gray', '-png', PDF, os.path.join(d, 'p')], check=True)
        f = [x for x in os.listdir(d) if x.endswith('.png')][0]
        return np.asarray(Image.open(os.path.join(d, f)).convert('L'))


def runs(mask, least):
    """Start and end of each run of True at least `least` long."""
    out, start = [], None
    for i, v in enumerate(list(mask) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= least:
                out.append((start, i - 1))
            start = None
    return out


def frames(dark):
    """The plot frames on a page: a list of rows, each a list of three (x0, x1, y0, y1)."""
    h, w = dark.shape
    # The scan is slightly skewed, so an edge wanders over a few rows: look through a window 7 pixels deep.
    # Rows dark over 30 % of the width are the top or bottom edges of three frames side by side; a frame is
    # 29 % of the page high, which tells a frame from the gap between two rows of frames.
    wide = ndimage.maximum_filter1d(dark, 7, axis=0)
    edges = [(a + b) // 2 for a, b in runs(wide.sum(1) > 0.30 * w, 3)]
    pairs = [(a, b) for i, a in enumerate(edges) for b in edges[i + 1:] if 0.27 * h < b - a < 0.31 * h]
    out = []
    for y0, y1 in pairs:
        band = ndimage.maximum_filter1d(dark[y0 + 8:y1 - 8], 7, axis=1)
        cols = [(a + b) // 2 for a, b in runs(band.sum(0) > 0.6 * band.shape[0], 4)]
        boxes = [(cols[i], cols[i + 1]) for i in range(len(cols) - 1) if cols[i + 1] - cols[i] > 0.1 * w]
        if len(boxes) == 3:
            out.append([(x0, x1, y0, y1) for x0, x1 in boxes])
    return out


def dots(dark, box):
    x0, x1, y0, y1 = box
    sub = dark[y0 + 8:y1 - 7, x0 + 8:x1 - 7]
    r = max(int(round(DPI / 100.0)), 2)                    # erode by a disc wider than any line, narrower than a circle
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    core = ndimage.binary_erosion(sub, structure=(xx * xx + yy * yy) <= r * r)
    lab, n = ndimage.label(core)
    pts = ndimage.center_of_mass(core, lab, range(1, n + 1))
    return [(x0 + 8 + c, y0 + 8 + rr) for rr, c in pts]


def digitise():
    cases, drawn = [], []
    cache = {}
    for pg, row, mach, re, cm_edge in CASES:
        xaxes = [(-10.0, 20.0), (0.0, 0.12), (0.0, cm_edge)]
        if pg not in cache:
            img = page(pg)
            cache[pg] = (img, img < 110)
        img, dark = cache[pg]
        fr = frames(dark)
        if len(fr) <= row:
            sys.exit('page %d: found %d rows of frames, wanted row %d' % (pg, len(fr), row))
        case = dict(mach=mach, reynolds=re, page=pg, row=row)
        for name, box, xa in zip(('alpha', 'cd', 'cm'), fr[row], xaxes):
            x0, x1, y0, y1 = box
            pts = []
            for px, py in dots(dark, box):
                x = xa[0] + (px - x0) / (x1 - x0) * (xa[1] - xa[0])
                cl = CL_AXIS[1] + (py - y0) / (y1 - y0) * (CL_AXIS[0] - CL_AXIS[1])
                pts.append((round(float(x), 5 if name != 'alpha' else 3), round(float(cl), 4)))
            pts.sort(key=lambda p: p[1])
            case[name] = pts
            drawn.append((pg, box, pts))
        cases.append(case)
    json.dump(dict(source='NASA TM 102840 (NTRS 19910007688), figure 24: LRN 1015, Ames 2- by 2-Foot Transonic Wind Tunnel, '
                          'free transition; digitised from the scanned figure',
                   note='each list holds (x, cl) pairs; angles of attack are the report\'s corrected ones, which it says '
                        'are uncertain by up to 3 deg of wall correction; touching symbols are read as one point',
                   cases=cases), open(OUT, 'w'), indent=1)
    return cases, cache, drawn


if __name__ == '__main__':
    cases, cache, drawn = digitise()
    for c in cases:
        cl = [p[1] for p in c['alpha']]
        cd = [p[0] for p in c['cd']]
        print('M %.2f Re %.1fe6: %2d lift points (cl %.2f to %.2f, alpha %.1f to %.1f), %2d drag (cd min %.4f), %2d moment' % (
            c['mach'], c['reynolds'] / 1e6, len(cl), min(cl), max(cl), min(p[0] for p in c['alpha']),
            max(p[0] for p in c['alpha']), len(cd), min(cd), len(c['cm'])))
    # a picture to check the reading by eye: the page with the points found marked
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    pg = 50
    fig, ax = plt.subplots(figsize=(11, 14))
    ax.imshow(cache[pg][0], cmap='gray')
    for p, box, pts in drawn:
        if p != pg:
            continue
        x0, x1, y0, y1 = box
        ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], 'b', lw=0.6)
    for p, row, mach, re, _ in CASES:
        if p != pg:
            continue
        fr = frames(cache[pg][1])[row]
        for box in fr:
            d = dots(cache[pg][1], box)
            ax.plot([q[0] for q in d], [q[1] for q in d], 'r+', ms=9, mew=1.0)
    ax.axis('off')
    os.makedirs(os.path.join(HERE, 'out'), exist_ok=True)
    plt.savefig(os.path.join(HERE, 'out', 'lrn1015_digitised.png'), dpi=80, bbox_inches='tight')
