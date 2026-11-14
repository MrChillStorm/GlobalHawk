#!/usr/bin/env python3
"""The Finnish livery's markings (docs/PLAN.md, "A Finnish livery"): the cockade and the serial, drawn into GlobalHawk/Models/cockade.png and serial.png.

    python3 fdm/mkmarkings.py

The Finnish Air Force's cockade: a white disc in the middle, a blue ring round it and a white ring outside that, **a third of the radius each** (the centre r 1/3, the blue ring 1/3 to 2/3, the
outer white ring 2/3 to 1): the construction of Wikimedia Commons' "Roundel of the Finnish Air Force" (SVG, circles of radius 300, 200 and 100 on a 600 disc; its blue #002F6C, matched to the
flag's; Fry1989, after drareg.nl), which is a drawing, not a service specification: none was found. The blue here is lifted from #002F6C to a royal blue, which reads as blue on the grey in daylight
(the photograph of HN-451 shows the ring's darkest pixels about (6, 39, 92), in the shade). The serial (cut tight to its ink; the model puts the cockade as far from its last digit as the 0 is from the 1: the gap measured on the lettering), small and black beside the cockade as on the Hornets, follows the Finnish scheme (two letters from the type's name, a hyphen, a number: HN-4xx for the Hornets, HW-3xx for the Hawks, DK-2xx
for the Drakens, JF-5xx for the F-35s): GH-601 for a Global Hawk, the next hundred after the F-35's. The aircraft is a made-up Finnish one, and so is its number. Both pictures are
transparent round the marking, so that the model draws them over the skin (fdm/mkmodel.py). Lettering in DejaVu Sans Bold, as matplotlib ships it.
"""
import os

import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'GlobalHawk', 'Models')
FONT = os.path.join(matplotlib.get_data_path(), 'fonts', 'ttf', 'DejaVuSans-Bold.ttf')
FIN_BLUE, WHITE, INK = (10, 66, 146), (246, 247, 250), (12, 13, 14)
SERIAL = 'GH-601'
SS = 4                                      # drawn at four times the size


def cockade(size=512):
    n = size * SS
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = n / 2
    for r, col in ((1.0, WHITE), (2 / 3, FIN_BLUE), (1 / 3, WHITE)):
        d.ellipse((c - r * c, c - r * c, c + r * c, c + r * c), fill=col + (255,))
    arr = np.asarray(img).copy()
    arr[arr[..., 3] == 0, :3] = WHITE                            # under the transparent pixels the outer ring's colour: no halo in the edge's smoothing
    return Image.fromarray(arr, 'RGBA').resize((size, size), Image.LANCZOS)


def _render(text=SERIAL):
    """the lettering on a transparent canvas at four times the size, and its ink's bounding box (left, top, right, bottom) and the gaps between its glyphs' ink (the columns with no ink between two
    runs of ink), all in the canvas's pixels"""
    font = ImageFont.truetype(FONT, 1000)
    d0 = ImageDraw.Draw(Image.new('L', (1, 1)))
    box = d0.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0] + 40, box[3] - box[1] + 40
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((20 - box[0], 20 - box[1]), text, font=font, fill=INK + (255,))
    a = np.asarray(img)[..., 3] > 0
    cols = np.where(a.any(axis=0))[0]
    rows = np.where(a.any(axis=1))[0]
    ink = a.any(axis=0)
    runs, start = [], None
    for x in range(len(ink)):
        if ink[x] and start is None:
            start = x
        if not ink[x] and start is not None:
            runs.append((start, x - 1)); start = None
    if start is not None:
        runs.append((start, len(ink) - 1))
    gaps = [runs[k + 1][0] - runs[k][1] - 1 for k in range(len(runs) - 1)]
    return img, (cols[0], rows[0], cols[-1] + 1, rows[-1] + 1), gaps


def serial_metrics(text=SERIAL):
    """what the model needs to lay the serial out: the picture's width over its height (it is cut tight to the ink: the picture's edge is the first and the last glyph's), and the gap between
    the last two glyphs' ink (the 0 and the 1 of GH-601), as a fraction of the picture's height. The cockade stands that far from the 1."""
    img, box, gaps = _render(text)
    ink_w, ink_h = box[2] - box[0], box[3] - box[1]
    return ink_w / ink_h, gaps[-1] / ink_h


def serial(text=SERIAL, height=256):
    """the lettering, black on transparent, cut to its ink: no margin, so that the picture's edges are the lettering's"""
    img, box, gaps = _render(text)
    img = img.crop(box)
    arr = np.asarray(img).copy()
    arr[arr[..., 3] == 0, :3] = INK
    img = Image.fromarray(arr, 'RGBA')
    return img.resize((max(1, round(img.width * height / img.height)), height), Image.LANCZOS)


if __name__ == '__main__':
    c, s = cockade(), serial()
    c.save(os.path.join(OUT, 'cockade.png'), optimize=True)
    s.save(os.path.join(OUT, 'serial.png'), optimize=True)
    a, g = serial_metrics()
    print('wrote GlobalHawk/Models/cockade.png', c.size, 'and serial.png', s.size, '; width/height %.3f, the 0 to 1 gap %.4f of the height' % (a, g))
