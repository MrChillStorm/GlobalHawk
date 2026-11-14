#!/usr/bin/env python3
"""The aircraft's insignia: a round badge painted on each side of the nacelle, drawn here into GlobalHawk/Models/insignia.png.

    python3 fdm/mkinsignia.py [preview.png]

FlightGear's own, in the manner of the FlightGear X-57's pilot's patch (its fdm/mkpatch.py, which this follows): the black and yellow
checkerboard round it tells whose it is, so the middle carries no logo. In the middle: the earth as a lit globe from straight above, with its
graticule, a bright rim of air, lights on its night side and a gold track round it with its waypoints; the Global Hawk over it from above, to
scale (fdm/data/geometry.json: the wing's taper and sweep, the fuselage, the nacelle on its back, the V-tail's panels as they show from above)
with its shadow on the earth below. Stars round the globe. Lettering in DejaVu Sans Bold, as matplotlib ships it. No agency's name, logo or
insignia. The badge is transparent outside its round edge: it lies over the skin, of whatever livery's colour.
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


def globe(cx, cy, rg, tilt=24.0, spin=-28.0):
    """the earth from straight above, as a lit globe with its graticule and a thin bright rim of air; returns (colour image, alpha) in the full canvas, and the unit-sphere coordinates"""
    y, x = np.mgrid[0:N, 0:N] + 0.5
    nx, ny = (x - cx) / rg, (y - cy) / rg
    rr = np.hypot(nx, ny)
    inside = rr < 1.0
    nz = np.sqrt(np.clip(1 - rr ** 2, 0, 1))
    # the sphere's own axes: tilted toward the viewer and turned, so that the poles are off to one side and the lines curve
    t, p = math.radians(tilt), math.radians(spin)
    px = nx
    py = ny * math.cos(t) - nz * math.sin(t)
    pz = ny * math.sin(t) + nz * math.cos(t)
    qx = px * math.cos(p) + pz * math.sin(p)
    qz = -px * math.sin(p) + pz * math.cos(p)
    lat = np.degrees(np.arcsin(np.clip(-py, -1, 1)))
    lon = np.degrees(np.arctan2(qx, qz))
    # land: a few slow waves over the sphere, thresholded
    rng = np.random.default_rng(60000)
    f = np.zeros_like(lat)
    for _ in range(9):
        k = rng.normal(size=3); k /= np.linalg.norm(k); k *= rng.uniform(1.6, 3.4)
        f += rng.uniform(0.6, 1.0) * np.sin(k[0] * qx + k[1] * -py + k[2] * qz + rng.uniform(0, 6.28))
    land = f > 99.0                                  # no continents: a drawn globe with only its lines
    # light from the upper left; the night side keeps a little of the sea's blue
    L = np.array([-0.55, -0.55, 0.63]); L /= np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    sea = np.array((8, 30, 78))[None, None, :] * (1 - lam[..., None]) + np.array((30, 104, 178))[None, None, :] * lam[..., None]
    soil = np.array((10, 44, 52))[None, None, :] * (1 - lam[..., None]) + np.array((46, 138, 118))[None, None, :] * lam[..., None]
    col = np.where(land[..., None], soil, sea)
    # the graticule: every 15 degrees, the equator and the Greenwich-like meridian a little brighter
    def lines(v, step, w):
        d = np.abs(((v + step / 2) % step) - step / 2)
        return np.exp(-(d / w) ** 2)
    wlat = 0.55 / np.maximum(nz, 0.18)
    grid = np.maximum(lines(lat, 15.0, 0.30 * wlat / 0.55), lines(lon, 15.0, 0.30 * wlat / 0.55))
    col = col * (1 - 0.55 * grid[..., None]) + np.array((150, 225, 255))[None, None, :] * 0.55 * grid[..., None] * (0.35 + 0.65 * lam[..., None] + 0.2)
    # the limb: the air seen edge-on brightens it
    limb = (1 - nz) ** 2.2
    col = col * (1 - limb[..., None] * 0.85) + np.array((130, 215, 255))[None, None, :] * limb[..., None] * 0.85
    glint = np.exp(-(((nx + 0.42) ** 2 + (ny + 0.46) ** 2) / 0.05)) * 0.5 * (nz > 0)
    col = col + np.array((200, 235, 255))[None, None, :] * glint[..., None]
    rgba = np.zeros((N, N, 4), np.uint8)
    rgba[..., :3] = np.clip(col, 0, 255).astype(np.uint8)
    rgba[..., 3] = (inside * 255).astype(np.uint8)
    return Image.fromarray(rgba, 'RGBA'), (nx, ny, nz, lat, lon, f, lam)


def sky():
    """the view from 60,000 ft: a deep glow behind, stars, the earth below as a globe with its graticule, its air a halo, a track round it and the aircraft's shadow"""
    y, x = np.mgrid[0:N, 0:N] + 0.5
    r = np.hypot(x - C, y - C)
    t = np.clip(r / R_TXT_I, 0, 1)[..., None]
    img = np.zeros((N, N, 4), np.uint8)
    img[..., :3] = (np.array((24, 64, 118)) * (1 - t) ** 1.4 + np.array(SPACE) * (1 - (1 - t) ** 1.4)).astype(np.uint8)
    img[..., 3] = 255
    out = Image.fromarray(img, 'RGBA')
    rng = np.random.default_rng(872)
    d = ImageDraw.Draw(out)
    for _ in range(90):
        a, rad = rng.uniform(0, 2 * math.pi), R_TXT_I * math.sqrt(rng.uniform(0.28, 1.0))
        sx, sy = C + rad * math.cos(a), C + rad * math.sin(a)
        k = rng.uniform(2.0, 5.5)
        d.ellipse((sx - k, sy - k, sx + k, sy + k), fill=(235, 240, 255, int(rng.uniform(110, 230))))
    RG = 628.0
    gx, gy = C, C + 8
    # the air round the globe
    halo = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((gx - RG - 4, gy - RG - 4, gx + RG + 4, gy + RG + 4), outline=(150, 222, 255, 255), width=22)
    out.alpha_composite(halo.filter(ImageFilter.GaussianBlur(30)))
    out.alpha_composite(halo.filter(ImageFilter.GaussianBlur(9)))
    g, (nx, ny, nz, lat, lon, fld, lam) = globe(gx, gy, RG)
    out.alpha_composite(g)
    # the night side: lights where people are (the same slow waves as the land would have been, thresholded), dots a few pixels across
    r2 = np.random.default_rng(1)
    # a finer field than the globe's, so that the lights make many small clusters (towns and cities) over the night side, and sparse stray lights between them
    fine = np.zeros_like(lat)
    for _ in range(22):
        k = r2.normal(size=3); k /= np.linalg.norm(k); k *= r2.uniform(3.0, 8.5)
        qx_, qy_, qz_ = nx, ny, nz
        fine += r2.uniform(0.5, 1.0) * np.sin(k[0] * qx_ + k[1] * qy_ + k[2] * qz_ + r2.uniform(0, 6.28))
    night = np.clip((0.42 - lam) / 0.30, 0, 1)
    dots = (fine > 2.1) & (r2.random((N, N)) < 0.022 * night) & (nz > 0.06)
    dots |= (r2.random((N, N)) < 0.0008 * night) & (nz > 0.06)
    lit = Image.fromarray((dots * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(5))
    glow_l = lit.filter(ImageFilter.GaussianBlur(9))
    warm = Image.new('RGBA', (N, N), (255, 214, 120, 0))
    warm.putalpha(Image.fromarray(np.minimum(np.asarray(glow_l).astype(int) * 3, 255).astype(np.uint8), 'L'))
    out.alpha_composite(warm)
    core = Image.new('RGBA', (N, N), (255, 240, 190, 0))
    core.putalpha(lit)
    out.alpha_composite(core)
    # a track: a great circle round the globe in gold, dashed, with a dot at each waypoint
    ov = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    inc = math.radians(58.0)
    pts = []
    for k in range(0, 721):
        a = math.radians(k * 0.5)
        v = np.array([math.cos(a), math.sin(a) * math.cos(inc), math.sin(a) * math.sin(inc)])      # on the sphere's own axes: lon/lat -> screen
        t_, p_ = math.radians(24.0), math.radians(-28.0)
        qx, qy, qz = v[0], v[1], v[2]
        # undo the sphere's turn and tilt to get the screen position
        sx_ = qx * math.cos(p_) - qz * math.sin(p_)
        sz_ = qx * math.sin(p_) + qz * math.cos(p_)
        sy_ = -qy
        py_ = sy_ * math.cos(t_) + sz_ * math.sin(t_)
        pz_ = -sy_ * math.sin(t_) + sz_ * math.cos(t_)
        pts.append((gx + RG * sx_, gy + RG * py_, pz_))
    for k in range(len(pts) - 1):
        (x0, y0, z0), (x1, y1, z1) = pts[k], pts[k + 1]
        if z0 > 0.02 and z1 > 0.02 and (k // 5) % 2 == 0:
            od.line([(x0, y0), (x1, y1)], fill=(255, 214, 80, 255), width=12)
    for k in range(60, 700, 130):
        x0, y0, z0 = pts[k]
        if z0 > 0.1:
            od.ellipse((x0 - 19, y0 - 19, x0 + 19, y0 + 19), fill=(255, 238, 150, 255), outline=(255, 190, 40, 255), width=6)
    out.alpha_composite(ov.filter(ImageFilter.GaussianBlur(1.2)))
    glow = ov.filter(ImageFilter.GaussianBlur(14))
    out.alpha_composite(glow)
    return out


def shadow(img, s=11.0, nose_y=C - 372, off=(46, 52)):
    """the aircraft's shadow on the earth below: drawn as the silhouette, blurred, dark, offset to the lower right"""
    sh = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    aircraft(sh, s, nose_y, flat=(2, 8, 24, 255))
    sh = sh.filter(ImageFilter.GaussianBlur(16))
    a = np.asarray(sh).copy()
    a[..., 3] = (a[..., 3] * 0.55).astype(np.uint8)
    sh = Image.fromarray(a, 'RGBA')
    moved = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    moved.alpha_composite(sh, (off[0], off[1]))
    img.alpha_composite(moved)


def aircraft(img, s=10.6, nose_y=C - 520, flat=None):
    """the Global Hawk from above, nose up, feet to pixels at s"""
    w, t, fu, na = GEO['wing'], GEO['vtail'], GEO['fuselage'], GEO['nacelle']
    P = lambda x, y: (C + y * s, nose_y + x * s)
    d = ImageDraw.Draw(img)
    ow = 6
    FILL = (lambda c: flat if flat else c)
    half = w['span'] / 2
    le = lambda y: w['le_centreline_x'] + abs(y) * math.tan(math.radians(w['sweep_le_deg']))
    ch = lambda y: w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * abs(y) / half
    # the V-tail's panels as they show from above
    for sy in (-1, 1):
        y0, y1 = t['root_y'], t['root_y'] + t['panel_span'] * math.cos(math.radians(t['dihedral_deg']))
        d.polygon([P(t['root_le_x'], sy * y0), P(t['tip_le_x'], sy * y1), P(t['tip_le_x'] + t['tip_chord'], sy * y1), P(t['root_le_x'] + t['root_chord'], sy * y0)],
                  fill=(flat or WHITE), outline=(flat or OUTLINE), width=ow)
    # the wing
    ys = np.linspace(-half, half, 3)
    d.polygon([P(le(y), y) for y in ys] + [P(le(y) + ch(y), y) for y in ys[::-1]], fill=(flat or WHITE), outline=(flat or OUTLINE), width=ow)
    # the fuselage: its width taken as its depth's share of the greatest (the side view has no widths)
    prof = fu['profile']
    xs = np.array([p['x'] for p in prof])
    dep = np.array([p['z_top'] - p['z_bottom'] for p in prof])
    hw = np.clip(fu['max_width'] / 2 * np.sqrt(np.clip(dep / fu['max_depth'], 0, 1)), 0, None)
    d.polygon([P(x, -y) for x, y in zip(xs, hw)] + [P(x, y) for x, y in zip(xs[::-1], hw[::-1])], fill=(flat or WHITE), outline=(flat or OUTLINE), width=ow)
    # the nacelle on its back, and the intake's dark mouth
    a, b = P(na['inlet_x'], 0), P(na['exhaust_x'], 0)
    r = na['diameter'] / 2 * s
    d.rounded_rectangle((a[0] - r, a[1], b[0] + r, b[1]), radius=r * 0.8, fill=(flat or (228, 232, 238)), outline=(flat or OUTLINE), width=ow)
    d.ellipse((a[0] - r * 0.72, a[1] - r * 0.1, a[0] + r * 0.72, a[1] + r * 0.9), fill=(flat or (40, 46, 58)))
    # the stripe's colours across the nose, as the livery's
    n0 = P(3.0, 0)
    if not flat:
        d.line([(n0[0] - 16, n0[1]), (n0[0] + 16, n0[1])], fill=FG_BLUE, width=10)
    return P(fu['length'], 0)[1]


def main(preview=None):
    img = ring_layers()
    inner = sky()
    shadow(inner)
    aircraft(inner, s=11.0, nose_y=C - 372)
    r, _ = polar()
    inner.putalpha(Image.fromarray(((r <= R_TXT_I - 8) * 255).astype(np.uint8), 'L'))
    img.alpha_composite(inner)
    edge = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(edge).ellipse((C - R_TXT_I, C - R_TXT_I, C + R_TXT_I, C + R_TXT_I), outline=GOLD + (255,), width=9)
    img.alpha_composite(edge)
    arc_text(img, 'GLOBAL HAWK', (R_TXT_O + R_TXT_I) / 2 - 2, 108, WHITE, top=True)
    arc_text(img, 'FLIGHTGEAR', (R_TXT_O + R_TXT_I) / 2 + 2, 100, FG_YELLOW, top=False)
    # the texture: the badge alone, transparent outside its round edge (the model draws it over the skin whatever the livery's colour); under the transparent pixels the rim's colour, so that
    # the texture's mip levels and the edge's smoothing do not bring in a halo of black or white
    arr = np.asarray(img).copy()
    arr[arr[..., 3] == 0, :3] = NAVY
    tex = Image.fromarray(arr, 'RGBA').resize((TEX, TEX), Image.LANCZOS)
    tex.save(OUT, optimize=True)
    print('wrote', os.path.relpath(OUT, os.path.join(HERE, '..')), tex.size, tex.mode)
    if preview:
        bg = Image.new('RGBA', (N, N), PAINT + (255,))
        bg.alpha_composite(img)
        bg.convert('RGB').resize((2 * TEX, 2 * TEX), Image.LANCZOS).save(preview)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
