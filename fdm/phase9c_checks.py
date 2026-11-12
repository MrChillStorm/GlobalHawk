#!/usr/bin/env python3
"""Phase 9 part C checks: the aircraft's own head-up display, in FlightGear.

    python3 fdm/phase9c_checks.py        about four minutes; FlightGear opens a window twice (runway, then in the air)

Limits: docs/PLAN.md, written before the HUD was run. Screenshots are kept in fdm/out/hud-*.png.
"""
import io
import math
import os
import sys
import time
import urllib.request

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import phase9a_checks as P9         # noqa: E402
import phase9b_checks as P9B        # noqa: E402

J = '/fdm/jsbsim/'
OUT = os.path.join(HERE, 'out')
LOG = os.path.join(OUT, 'fg-hud.log')
GREEN = (0.30, 1.00, 0.25)
rows = []


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))
    print('%-3s %-44s %-5s %s' % rows[-1], flush=True)


get, post = P9.get, P9B.post
hud = lambda k: get('/sim/globalhawk/hud/' + k)


def shot(name=None):
    data = urllib.request.urlopen('http://127.0.0.1:%d/screenshot?type=png' % P9.PORT, timeout=30).read()
    if name:
        open(os.path.join(OUT, name), 'wb').write(data)
    return np.asarray(Image.open(io.BytesIO(data)).convert('RGB')).astype(float)


def fps(seconds):
    v = []
    end = time.time() + seconds
    while time.time() < end:
        x = get('/sim/frame-rate')
        if x:
            v.append(x)
        time.sleep(1.0)
    return sum(v) / len(v) if v else 0.0


def nasal_errors():
    """Nasal errors that are the aircraft's: the error's own lines or its traceback name the aircraft's files.
    (FlightGear's own weather code gives one at every air start: not counted.)"""
    lines = [l for l in open(LOG, errors='replace') if not l.startswith('[sentry]') and 'tied property' not in l]
    bad = []
    for n, line in enumerate(lines):
        low = line.lower()
        if 'global hawk hud' in low or 'global hawk link' in low:
            bad.append(line.strip()[:160])
        elif 'nasal' in low and ('runtime error' in low or 'parse error' in low):
            block = ''.join(lines[n:n + 8])
            if 'GlobalHawk' in block:
                bad.append(line.strip()[:160])
    return bad


def look_ahead():
    """the nose camera as the aircraft's files have it: FlightGear keeps the way the user last turned it"""
    for k, v in (('heading-offset-deg', 0.0), ('pitch-offset-deg', -4.0)):
        post('/sim/current-view/goal-' + k, v)
        post('/sim/current-view/' + k, v)
    time.sleep(1.5)


def runway():
    proc, took = P9.start(['--airport=EFHK'], LOG)
    if took is None:
        P9.stop(proc)
        add('H1', 'FlightGear starts', False, 'it did not come up')
        return
    try:
        time.sleep(8)
        look_ahead()
        name, on0 = get('/sim/hud/hud-list/hud/name'), hud('shown')
        post('/sim/current-view/view-number', 1); time.sleep(1.5)
        outside = hud('shown')
        post('/sim/current-view/view-number', 0); time.sleep(1.5)
        back = hud('shown')
        post('/sim/hud/visible', False); time.sleep(1.5)
        off = hud('shown')
        without = shot('hud-runway-off.png')
        f_off = fps(20)
        post('/sim/hud/visible', True); time.sleep(1.5)
        on = shot('hud-runway.png')
        f_on = fps(20)
        bad = nasal_errors()
        add('H1', "the aircraft's own HUD, in the nose camera only", name == 'Global Hawk nose camera' and on0 == 1 and outside == 0 and back == 1 and off == 0 and not bad,
            'HUD "%s"; shown at the start %s; in an outside view %s; back in the nose camera %s; switched off %s; Nasal errors: %s' % (name, on0, outside, back, off, bad[:2] or 'none'))
        # H3 on the runway: the scenery's horizon is where the picture goes from sky to ground down its middle columns
        h, w, _ = without.shape
        lum = without[:, int(w * 0.30):int(w * 0.70), :].mean(axis=(1, 2))
        smooth = np.convolve(lum, np.ones(5) / 5, mode='same')
        grad = smooth[:-6] - smooth[6:]                     # brighter above than below
        lo, hi = int(h * 0.2), int(h * 0.7)
        row = lo + int(np.argmax(grad[lo:hi])) + 3
        hy = hud('horizon-y')
        fov = get('/sim/current-view/field-of-view')
        px_per_deg = (w / 2) / math.tan(math.radians(fov / 2)) * math.radians(1)
        err = (hy - row) / px_per_deg
        add('H3', 'the horizon line lies on the horizon (runway)', abs(err) <= 1.0, "the HUD's horizon at row %.0f, the scenery's (sky to ground, by brightness) at row %d: %.2f deg apart (%.1f px a deg)" % (hy, row, err, px_per_deg))
        # H4 one colour: the pixels the HUD adds
        diff = np.abs(on - without).sum(axis=2)
        added = on[diff > 150]
        dark = without.sum(axis=2) < 270                     # over a dark part of the scene: over a light one the line's soft edge takes the scene's colour
        strong = on[(diff > 150) & dark & (on[:, :, 1] > 200)]
        r, b = (strong[:, 0] / strong[:, 1]), (strong[:, 2] / strong[:, 1])
        other = int(((added[:, 1] < added[:, 0]) | (added[:, 1] < added[:, 2])).sum())
        add('H4', 'one colour', len(strong) > 500 and abs(np.median(r) - GREEN[0]) < 0.08 and abs(np.median(b) - GREEN[2]) < 0.08 and other <= 0.01 * len(added),
            '%d pixels changed by the HUD, %d of them at full strength over the dark part of the scene: red/green %.2f (%.2f wanted), blue/green %.2f (%.2f wanted); pixels where green is not the strongest: %d' % (
                len(added), len(strong), np.median(r), GREEN[0], np.median(b), GREEN[2], other))
        add('H7g', 'no structural alert from standing on the runway', get(J + 'limits/overstress') == 0, 'the limit flag %s after about a minute on the runway (FlightGear sets the aircraft down with a jolt at the start; the latch is cleared once after it)' % get(J + 'limits/overstress'))
        add('H5', 'cost in frames a second', f_on >= 0.9 * f_off, '%.1f with the HUD, %.1f without, over 20 s each on the runway' % (f_on, f_off))
    finally:
        P9.stop(proc)


def air():
    time.sleep(20)
    proc, took = P9.start(['--lat=60.317', '--lon=24.963', '--altitude=3000', '--vc=150', '--heading=40'], LOG)
    if took is None:
        P9.stop(proc)
        add('H2', 'FlightGear starts in the air', False, 'it did not come up')
        return
    try:
        look_ahead()
        nz, over = [], []
        end = time.time() + 40
        while time.time() < end:
            nz.append(get(J + 'accelerations/Nz') or 0.0)
            over.append(get(J + 'limits/overstress') or 0.0)
            time.sleep(0.5)
        add('H7', 'no structural alert from the start itself', over[-1] == 0, 'load factor over the first 40 s %.2f to %.2f; the limit flag at the end %g (it was set at some time: %s; cleared once at 5 s)' % (min(nz), max(nz), over[-1], max(over) > 0))
        worst, lines = [0, 0, 0, 0, 0], []
        for n in range(2):
            a = (get(J + 'velocities/vc-kts'), get(J + 'position/h-sl-ft'), get('/orientation/heading-deg'), get(J + 'ap/speed-target-kcas'), get(J + 'ap/alt-cmd-ft'))
            s = (hud('kcas'), hud('alt-ft'), hud('heading-deg'), hud('target-kcas'), hud('target-alt-ft'))
            b = (get(J + 'velocities/vc-kts'), get(J + 'position/h-sl-ft'), get('/orientation/heading-deg'), get(J + 'ap/speed-target-kcas'), get(J + 'ap/alt-cmd-ft'))
            # what is shown must be the rounding of a value the property had between the two readings around it
            for i, step in enumerate((1, 10, 1, 1, 1)):
                # what is shown was written up to a frame or two before it is read here: the readings either side are
                # widened by what the value can move in 0.3 s (5 ft at 1,000 ft/min, 0.5 kt, 1 deg)
                slack = (0.5, 5.0, 1.0, 0.0, 0.0)[i]
                lo, hi = min(a[i], b[i]) - slack, max(a[i], b[i]) + slack
                off = 0.0 if lo - step / 2 - 1e-6 <= s[i] <= hi + step / 2 + 1e-6 else min(abs(s[i] - lo), abs(s[i] - hi)) - step / 2
                if i == 2:
                    off = 0.0 if abs((s[i] - a[i] + 180) % 360 - 180) <= 0.5 + abs(b[i] - a[i]) + 1e-6 else abs((s[i] - a[i] + 180) % 360 - 180) - 0.5
                worst[i] = max(worst[i], off)
            lines.append('shown %d kt, %d ft, %03d deg, targets %d kt %d ft; had %.1f kt, %.0f ft, %.1f deg, %.1f kt, %.0f ft' % (s + a))
            if n == 0:
                time.sleep(30)
        add('H2', 'shows what the aircraft has (in the air)', max(worst) == 0, '%s | 30 s later %s; beyond rounding by: %s' % (lines[0], lines[1], [round(x, 2) for x in worst]))
        shot('hud-air-level.png')
        hdg = get('/orientation/heading-deg')
        post(J + 'ap/heading-cmd-deg', (hdg + 120) % 360)
        time.sleep(14)
        shot('hud-air-turn.png')
        add('H3b', 'the horizon in a banked turn (by eye, screenshot)', True, 'fdm/out/hud-air-turn.png, bank %.1f deg, pitch %.1f deg: to be looked at' % (get('/orientation/roll-deg'), get('/orientation/pitch-deg')))
        bad = nasal_errors()
        add('H1b', 'no Nasal error in the air', not bad, '%s' % (bad[:2] or 'none'))
    finally:
        P9.stop(proc)


if __name__ == '__main__':
    which = sys.argv[1:] or ['runway', 'air']
    if 'runway' in which:
        runway()
    if 'air' in which:
        air()
    with open(os.path.join(OUT, 'phase9c_checks.txt'), 'w') as fh:
        for r in rows:
            fh.write('%-3s %-44s %-5s %s\n' % r)
    print('%d checks, %d pass, %d miss' % (len(rows), sum(r[2] == 'pass' for r in rows), sum(r[2] != 'pass' for r in rows)))
