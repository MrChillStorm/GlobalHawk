#!/usr/bin/env python3
"""The aircraft's insignia: a round badge painted on each side of the nacelle, drawn here into GlobalHawk/Models/insignia.png.

    python3 fdm/mkinsignia.py [preview.png]

FlightGear's own, in the manner of the FlightGear X-57's pilot's patch (its fdm/mkpatch.py, which this follows): the black and yellow
checkerboard round it, and FlightGear's logo, the checker strip and the blue F of fgdata's Docs/img/FlightGear_logo.svg (GPL, as
fgdata), under the tail. The aircraft is the Global Hawk from above, to scale, from fdm/data/geometry.json: the wing's taper and
sweep, the fuselage, the nacelle on its back and the V-tail's panels as they show from above. Behind it the edge of the earth as it is
seen from where the aircraft flies, and a few stars. Lettering in DejaVu Sans Bold, as matplotlib ships it. No agency's name, logo or
insignia. The badge's surround is the paint's white, so it needs no transparency on the skin.
"""
import json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import matplotlib

HERE = os.path.dirname(os.path.abspath(__file__))
GEO = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
OUT = os.path.join(HERE, '..', 'GlobalHawk', 'Models', 'insignia.png')
TEX = 512
FONT = os.path.join(matplotlib.get_data_path(), 'fonts', 'ttf', 'DejaVuSans-Bold.ttf')
PAINT = (240, 240, 242)       # the skin's white (fdm/mkmodel.py's first material)

N = 2048                      # drawn at four times the texture's size
C = N / 2
FG_YELLOW, FG_BLUE, BLACK = (251, 252, 70), (66, 126, 191), (17, 17, 17)
GOLD = (201, 162, 39)
NAVY, SPACE, HIGH = (13, 31, 60), (6, 12, 30), (20, 48, 100)
WHITE, OUTLINE = (242, 244, 247), (120, 132, 146)

R_OUT, R_CHK_O, R_CHK_I, R_TXT_O, R_TXT_I = 1000, 975, 875, 862, 705


def polar():
    y, x = np.mgrid[0:N, 0:N] + 0.5
    return np.hypot(x - C, y - C), np.arctan2(x - C, -(y - C)) % (2 * math.pi)       # angle from the top, clockwise


def ring_layers():
    r, th = polar()
    img = np.zeros((N, N, 4), np.uint8)
    img[(r <= R_OUT) & (r > R_CHK_O)] = NAVY + (255,)                                # a painted rim
    band = (r <= R_CHK_O) & (r > R_CHK_I)                                            # FlightGear's checkerboard, two rows round the ring
    h = (R_CHK_O - R_CHK_I) / 2
    n = int(round(2 * math.pi * (R_CHK_O + R_CHK_I) / 2 / h / 2)) * 2
    yellow = ((np.floor((R_CHK_O - r) / h).astype(int) + np.floor(th / (2 * math.pi) * n).astype(int)) % 2) == 0
    img[band & yellow] = FG_YELLOW + (255,)
    img[band & ~yellow] = BLACK + (255,)
    img[(r <= R_CHK_I) & (r > R_TXT_O)] = GOLD + (255,)
    img[(r <= R_TXT_O) & (r > R_TXT_I)] = NAVY + (255,)
    return Image.fromarray(img, 'RGBA')


def arc_text(img, text, radius, size, fill, top=True, track=0.06):
    """letters round the circle, their feet to the centre on top and their heads to it below, reading left to right"""
    font = ImageFont.truetype(FONT, size)
    widths = [font.getlength(ch) * (1 + track) for ch in text]
    a = -sum(widths) / radius / 2
    for ch, w in zip(text, widths):
        mid = a + w / 2 / radius
        a += w / radius
        if ch == ' ':
            continue
        box = font.getbbox(ch)
        tile = Image.new('RGBA', (int(box[2] + 40), int(size * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((20, size * 0.2), ch, font=font, fill=fill + (255,))
        if top:
            x, y, rot = C + radius * math.sin(mid), C - radius * math.cos(mid), -math.degrees(mid)
        else:
            x, y, rot = C + radius * math.sin(mid), C + radius * math.cos(mid), math.degrees(mid)
        tile = tile.rotate(rot, resample=Image.BICUBIC, expand=True)
        img.alpha_composite(tile, (int(x - tile.width / 2), int(y - tile.height / 2)))


def sky():
    """the view from 60,000 ft: near-black above, the earth's curved edge low in the picture with its thin blue air, stars"""
    r, _ = polar()
    y, x = np.mgrid[0:N, 0:N] + 0.5
    img = np.zeros((N, N, 4), np.uint8)
    t = np.clip((y - (C - R_TXT_I)) / (2 * R_TXT_I), 0, 1)[..., None]
    img[..., :3] = (np.array(SPACE) * (1 - t) + np.array(HIGH) * t).astype(np.uint8)
    img[..., 3] = 255
    out = Image.fromarray(img, 'RGBA')
    rng = np.random.default_rng(872)
    d = ImageDraw.Draw(out)
    for _ in range(70):
        sx, sy = C + rng.uniform(-R_TXT_I, R_TXT_I), C + rng.uniform(-R_TXT_I, 120)
        k = rng.uniform(2.0, 5.5)
        d.ellipse((sx - k, sy - k, sx + k, sy + k), fill=(235, 240, 255, int(rng.uniform(110, 230))))
    # the earth: a great circle whose top is below the middle; its air a glow along the edge
    R_E, top = 2600.0, C + 300
    ce = top + R_E
    dist = np.hypot(x - C, y - ce)
    earth = dist <= R_E
    a = np.asarray(out).copy()
    shade = np.clip((R_E - dist) / 500.0, 0, 1)[..., None]
    a[earth, :3] = (np.array((70, 150, 215)) * (1 - shade) + np.array((16, 60, 120)) * shade)[earth].astype(np.uint8)
    out = Image.fromarray(a, 'RGBA')
    glow = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((C - R_E - 14, ce - R_E - 14, C + R_E + 14, ce + R_E + 14), outline=(150, 215, 255, 255), width=30)
    out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(22)))
    return out


def aircraft(img, s=10.6, nose_y=C - 520):
    """the Global Hawk from above, nose up, feet to pixels at s"""
    w, t, fu, na = GEO['wing'], GEO['vtail'], GEO['fuselage'], GEO['nacelle']
    P = lambda x, y: (C + y * s, nose_y + x * s)
    d = ImageDraw.Draw(img)
    ow = 6
    half = w['span'] / 2
    le = lambda y: w['le_centreline_x'] + abs(y) * math.tan(math.radians(w['sweep_le_deg']))
    ch = lambda y: w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * abs(y) / half
    # the V-tail's panels as they show from above
    for sy in (-1, 1):
        y0, y1 = t['root_y'], t['root_y'] + t['panel_span'] * math.cos(math.radians(t['dihedral_deg']))
        d.polygon([P(t['root_le_x'], sy * y0), P(t['tip_le_x'], sy * y1), P(t['tip_le_x'] + t['tip_chord'], sy * y1), P(t['root_le_x'] + t['root_chord'], sy * y0)],
                  fill=WHITE, outline=OUTLINE, width=ow)
    # the wing
    ys = np.linspace(-half, half, 3)
    d.polygon([P(le(y), y) for y in ys] + [P(le(y) + ch(y), y) for y in ys[::-1]], fill=WHITE, outline=OUTLINE, width=ow)
    # the fuselage: its width taken as its depth's share of the greatest (the side view has no widths)
    prof = fu['profile']
    xs = np.array([p['x'] for p in prof])
    dep = np.array([p['z_top'] - p['z_bottom'] for p in prof])
    hw = np.clip(fu['max_width'] / 2 * np.sqrt(np.clip(dep / fu['max_depth'], 0, 1)), 0, None)
    d.polygon([P(x, -y) for x, y in zip(xs, hw)] + [P(x, y) for x, y in zip(xs[::-1], hw[::-1])], fill=WHITE, outline=OUTLINE, width=ow)
    # the nacelle on its back, and the intake's dark mouth
    a, b = P(na['inlet_x'], 0), P(na['exhaust_x'], 0)
    r = na['diameter'] / 2 * s
    d.rounded_rectangle((a[0] - r, a[1], b[0] + r, b[1]), radius=r * 0.8, fill=(228, 232, 238), outline=OUTLINE, width=ow)
    d.ellipse((a[0] - r * 0.72, a[1] - r * 0.1, a[0] + r * 0.72, a[1] + r * 0.9), fill=(40, 46, 58))
    # the stripe's colours across the nose, as the livery's
    n0 = P(3.0, 0)
    d.line([(n0[0] - 16, n0[1]), (n0[0] + 16, n0[1])], fill=FG_BLUE, width=10)
    return P(fu['length'], 0)[1]


def fg_logo(img, cx, cy, size):
    """fgdata's FlightGear logo, its 200-unit drawing: the black and yellow checker strip and the blue F, on a white tile"""
    k = size / 200.0
    tile = Image.new('RGBA', (int(size + 24), int(size + 24)), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    o = 12
    d.rounded_rectangle((0, 0, tile.width - 1, tile.height - 1), radius=26, fill=GOLD + (255,))
    d.rounded_rectangle((o - 2, o - 2, o + size + 2, o + size + 2), radius=18, fill=(255, 255, 255, 255))
    Q = lambda x, y: (o + x * k, o + y * k)
    d.rectangle((*Q(0, 0), *Q(75, 200)), fill=BLACK)
    for col in range(3):
        for row in range(8):
            if (row + col) % 2 == 0:
                d.rectangle((*Q(25 * col, 25 * row), *Q(25 * col + 25, 25 * row + 25)), fill=FG_YELLOW)
    for a, b in (((94.418, 27.531), (129.606, 172.47)), ((94.418, 27.531), (188.54, 54.56)), ((129.6, 82.53), (184.51, 109.47))):
        d.rounded_rectangle((*Q(*a), *Q(*b)), radius=3 * k, fill=FG_BLUE)
    mask = Image.new('L', tile.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile.width - 1, tile.height - 1), radius=26, fill=255)
    tile.putalpha(Image.fromarray(np.minimum(np.asarray(tile)[..., 3], np.asarray(mask))))
    img.alpha_composite(tile, (int(cx - tile.width / 2), int(cy - tile.height / 2)))


def main(preview=None):
    img = ring_layers()
    inner = sky()
    tail = aircraft(inner)
    fg_logo(inner, C, tail + 105, 150)
    r, _ = polar()
    inner.putalpha(Image.fromarray(((r <= R_TXT_I - 8) * 255).astype(np.uint8), 'L'))
    img.alpha_composite(inner)
    edge = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(edge).ellipse((C - R_TXT_I, C - R_TXT_I, C + R_TXT_I, C + R_TXT_I), outline=GOLD + (255,), width=9)
    img.alpha_composite(edge)
    arc_text(img, 'GLOBAL HAWK', (R_TXT_O + R_TXT_I) / 2 - 2, 108, WHITE, top=True)
    arc_text(img, 'FLIGHTGEAR', (R_TXT_O + R_TXT_I) / 2 + 2, 100, FG_YELLOW, top=False)
    bg = Image.new('RGBA', (N, N), PAINT + (255,))
    bg.alpha_composite(img)
    out = bg.convert('RGB').resize((TEX, TEX), Image.LANCZOS)
    out.save(OUT, optimize=True)
    print('wrote', os.path.relpath(OUT, os.path.join(HERE, '..')), out.size)
    if preview:
        bg.convert('RGB').resize((2 * TEX, 2 * TEX), Image.LANCZOS).save(preview)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
