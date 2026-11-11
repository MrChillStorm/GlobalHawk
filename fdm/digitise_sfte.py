#!/usr/bin/env python3
"""Lift-curve slopes of the RQ-4 Block 20 measured in flight, read from figure 3 of Eaton and Woolf, "Flight Test
Validation of the RQ-4 Block 20 Global Hawk Aerodynamic and Propulsive Models", SFTE 2009 (U.S. Air Force Flight
Test Center, approved for public release, AFFTC-PA-09254).

The figure's axes have no numbers, only their scales: one grid square is 2 deg of angle of attack and 0.2 of lift
coefficient, and the curves for seven Mach numbers are drawn side by side. So absolute lift can't be read, but the
slope of each cloud of flight-test points can. The coloured symbols (climb and cruise points) are taken pixel by
pixel, sorted into the clouds by where a line of typical slope through them meets a reference height, and a line
is fitted to each cloud. The Mach 0.625 cloud has too few points.

    python3 fdm/digitise_sfte.py        prints the slopes; writes fdm/data/sfte_block20_lift_slopes.json

The paper is not in the repository. The Block 20 is the RQ-4B, with a longer wing than the aircraft modelled here.
"""
import json
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, '..', 'refs', 'other', 'SFTE-2009-Eaton-Woolf-RQ-4-Block20-flight-test-validation-aero-propulsion.pdf')
OUT = os.path.join(HERE, 'data', 'sfte_block20_lift_slopes.json')
CELL = 66.65                      # pixels in one grid square of the embedded figure (800 x 598)
MACHS = (0.27, 0.4, 0.5, 0.55, 0.575, 0.6)


def figure3():
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(['pdfimages', '-png', '-f', '7', '-l', '7', PDF, os.path.join(d, 'f')], check=True)
        return np.asarray(Image.open(os.path.join(d, sorted(os.listdir(d))[0])).convert('RGB')).astype(int)


def slopes():
    a = figure3()
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = ((g > 120) & (r < 90) & (b < 90)) | ((b > 150) & (r < 90) & (g < 90))      # green climb, blue cruise symbols
    m[:215, :210] = False                                                        # the legend
    y, x = np.nonzero(m)
    x0 = x + (y - 300) / 1.3                                                     # where each point's line crosses y = 300
    h, e = np.histogram(x0, bins=np.arange(0, 900, 6))
    peaks = [e[i] + 3 for i in range(1, len(h) - 1) if h[i] >= h[i - 1] and h[i] >= h[i + 1] and h[i] > 60]
    centres = []
    for c in peaks:
        if not centres or c - centres[-1] >= 45:
            centres.append(c)
    out = []
    for mach, c in zip(MACHS, centres):
        k = np.abs(x0 - c) < 40
        alpha, cl = x[k] / CELL * 2.0, -y[k] / CELL * 0.2
        w, v = np.linalg.eigh(np.cov(alpha, cl))                                 # total least squares: both axes carry scatter
        out.append(dict(mach=mach, slope_per_deg=round(float(v[1, 1] / v[0, 1]), 4), cl_range=round(float(np.ptp(cl)), 2),
                        pixels=int(k.sum())))
    return out


if __name__ == '__main__':
    s = slopes()
    for r in s:
        print('Mach %.3f: lift-curve slope %.4f per deg over a lift-coefficient range of %.2f (%d pixels of symbols)' % (
            r['mach'], r['slope_per_deg'], r['cl_range'], r['pixels']))
    json.dump(dict(source='Eaton and Woolf, SFTE 2009, figure 3: RQ-4 Block 20, untrimmed, standardised to a rigid airframe and '
                          '25 % MAC; slopes of the flight-test point clouds, read from a figure whose axes carry scales only',
                   slopes=s), open(OUT, 'w'), indent=1)
