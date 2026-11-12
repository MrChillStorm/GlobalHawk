#!/usr/bin/env python3
"""Phase 9 part C checks: the belly camera's lock and slew, in FlightGear in the air.

    python3 fdm/phase9d_checks.py        about five minutes; FlightGear opens a window. Leave it alone while it runs.

Limits: docs/PLAN.md, written before the lock was run.
"""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import missionmgr as MM             # noqa: E402
import phase9a_checks as P9         # noqa: E402
import phase9b_checks as P9B        # noqa: E402
import phase9c_checks as P9C        # noqa: E402

J = '/fdm/jsbsim/'
CAM = '/sim/globalhawk/camera/'
LOG = os.path.join(HERE, 'out', 'fg-camera.log')
rows = []
get, post = P9.get, P9B.post


def add(tag, name, ok, detail):
    rows.append((tag, name, 'pass' if ok else 'MISS', detail))
    print('%-3s %-44s %-5s %s' % rows[-1], flush=True)


def here():
    return (get('/position/latitude-deg'), get('/position/longitude-deg'), get('/position/altitude-ft'))


def direction(target):
    """the bearing and the elevation (deg) from the aircraft to (lat, lon, alt ft), as the camera's Nasal works them out"""
    lat, lon, alt = here()
    brg, dist = MM.course((lat, lon), target[:2])
    dh = target[2] - alt - (dist * 0.3048) ** 2 / (2 * 6371000.0) / 0.3048
    return brg, math.degrees(math.atan2(dh, dist))


def error(target):
    """deg between where the camera looks (the overlay's own azimuth and depression) and the direction to the target"""
    az, dep = P9C.hud('sensor-azimuth-deg'), P9C.hud('sensor-depression-deg')
    brg, el = direction(target)
    dh = ((az - brg + 180) % 360 - 180) * math.cos(math.radians(el))
    return math.hypot(dh, -dep - el)


def belly():
    for n in range(0, 14):
        post('/sim/current-view/view-number', n)
        time.sleep(0.7)
        if get('/sim/current-view/name') == 'Belly Camera':
            return n
    return None


def nasal(script):
    """run a line of Nasal in FlightGear (its web server's command interface, as its own web pages use it)"""
    import json
    import urllib.request
    body = json.dumps(dict(name='', children=[dict(name='script', index=0, value=script)])).encode()
    urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d/run.cgi?value=nasal' % P9.PORT, method='POST', data=body), timeout=5).read()


def ship(index, lat, lon, name):
    """a made-up model in FlightGear's list: what any AI or multiplayer model is to the camera, a node with a place"""
    base = '/ai/models/ship[%d]/' % index
    nasal('var n = props.globals.getNode("/ai/models/ship[%d]", 1); n.getNode("valid", 1).setBoolValue(1); n.getNode("name", 1).setValue("%s"); '
          'n.getNode("position/latitude-deg", 1).setDoubleValue(%.7f); n.getNode("position/longitude-deg", 1).setDoubleValue(%.7f); '
          'n.getNode("position/altitude-ft", 1).setDoubleValue(0);' % (index, name, lat, lon))
    return base


def main():
    proc, took = P9.start(['--lat=60.317', '--lon=24.963', '--altitude=3000', '--vc=150', '--heading=40'], LOG)
    if took is None:
        P9.stop(proc)
        add('K1', 'FlightGear starts in the air', False, 'it did not come up')
        return
    try:
        time.sleep(25)
        view = belly()
        lat, lon, alt = here()
        ground = get('/position/ground-elev-ft') or 100.0
        hdg = get('/orientation/heading-deg')

        # ---- K1 a point 3 nmi ahead and to the right, through a turn
        c, s = math.cos(math.radians(hdg + 50)), math.sin(math.radians(hdg + 50))
        target = (lat + 3 * MM.NM * c / MM.FT_PER_DEG, lon + 3 * MM.NM * s / (MM.FT_PER_DEG * math.cos(math.radians(lat))), ground)
        post(CAM + 'command', 'point %.6f %.6f %.1f' % target)
        time.sleep(2)
        errs, hd = [], []
        post(J + 'ap/heading-cmd-deg', (hdg + 150) % 360)
        end = time.time() + 90
        while time.time() < end:
            errs.append(error(target))
            hd.append(get('/orientation/heading-deg'))
            time.sleep(0.5)
        turned = abs((hd[-1] - hd[0] + 180) % 360 - 180)
        add('K1', 'locked on a point through a turn', view is not None and get(CAM + 'lock') == 'point' and max(errs) <= 0.3 and turned >= 90,
            'belly camera is view %s; lock "%s" on %s; 90 s, heading turned %.0f deg, bank to %.0f; the camera within %.2f deg of the point (mean %.2f, 95th percentile %.2f)' % (
                view, get(CAM + 'lock'), get(CAM + 'name'), turned, abs(get('/orientation/roll-deg')), max(errs), sum(errs) / len(errs), sorted(errs)[int(0.95 * len(errs))]))

        # ---- K3 first half: the nose camera is not moved by the lock
        post('/sim/current-view/view-number', 0)
        time.sleep(2)
        nose = (get('/sim/current-view/heading-offset-deg'), get('/sim/current-view/pitch-offset-deg'))
        post('/sim/current-view/view-number', view)
        time.sleep(1.5)

        # ---- K2 a ship at 20 kt, and a second one further from the cross
        lat, lon, alt = here()
        hdg = get('/orientation/heading-deg')
        c, s = math.cos(math.radians(hdg + 40)), math.sin(math.radians(hdg + 40))
        s_lat, s_lon = lat + 2.5 * MM.NM * c / MM.FT_PER_DEG, lon + 2.5 * MM.NM * s / (MM.FT_PER_DEG * math.cos(math.radians(lat)))
        base = ship(7, s_lat, s_lon, 'Made-up ship')
        ship(8, s_lat + 0.012, s_lon + 0.03, 'Other ship')
        post(CAM + 'command', 'point %.6f %.6f 0' % (s_lat, s_lon))          # look at it first
        time.sleep(2)
        post(CAM + 'command', 'nearest')
        time.sleep(1.5)
        took_name, mode = get(CAM + 'name'), get(CAM + 'lock')
        said = get(CAM + 'said')
        errs = []
        t0 = time.time()
        while time.time() - t0 < 60:
            moved = 20 * 1.6878 * (time.time() - t0)                           # ft northwards
            cur = (s_lat + moved / MM.FT_PER_DEG, s_lon, 0.0)
            post(base + 'position/latitude-deg', cur[0])
            time.sleep(0.25)
            errs.append(error(cur))
            time.sleep(0.25)
        add('K2', 'locked on a moving object', mode == 'object' and took_name == 'Made-up ship' and max(errs) <= 0.3,
            'lock "%s" on "%s" (it said: %s); the ship moved %.0f ft in 60 s; the camera within %.2f deg of it (mean %.2f, 95th percentile %.2f)' % (mode, took_name, said, moved, max(errs), sum(errs) / len(errs), sorted(errs)[int(0.95 * len(errs))]))

        # ---- K3 the rest: unlock leaves it where it is, and free
        post(CAM + 'command', 'unlock')
        time.sleep(1)
        o1 = (get('/sim/current-view/heading-offset-deg'), get('/sim/current-view/pitch-offset-deg'))
        time.sleep(4)
        o2 = (get('/sim/current-view/heading-offset-deg'), get('/sim/current-view/pitch-offset-deg'))
        add('K3', 'the nearest is taken; unlock frees; the nose is left', took_name == 'Made-up ship' and get(CAM + 'lock') == '' and o1 == o2 and nose == (0.0, -4.0),
            'of two ships the one under the cross was taken: %s; after unlock the lock is "%s" and the view offsets stay (%s, then %s); the nose camera while locked: %s' % (
                took_name == 'Made-up ship', get(CAM + 'lock'), o1, o2, nose))

        # ---- K4 slewing: free, at two fields of view; then locked on a point
        post('/sim/current-view/goal-pitch-offset-deg', -40.0); post('/sim/current-view/pitch-offset-deg', -40.0)
        rates = []
        for fov in (40.0, 10.0):
            post('/sim/current-view/field-of-view', fov)
            time.sleep(1)
            a0 = P9C.hud('sensor-azimuth-deg')
            post(CAM + 'slew-right', 1.0)
            time.sleep(2.0)
            post(CAM + 'slew-right', 0.0)
            time.sleep(0.6)
            a1 = P9C.hud('sensor-azimuth-deg')
            turn = get('/orientation/heading-deg')
            rates.append(((a1 - a0 + 180) % 360 - 180) / 2.0)
        post('/sim/current-view/field-of-view', 40.0)
        post(CAM + 'command', 'cross')
        time.sleep(1.5)
        p0 = (get(CAM + 'target-lat'), get(CAM + 'target-lon'))
        post(CAM + 'slew-up', 1.0)
        time.sleep(0.6)
        post(CAM + 'slew-up', 0.0)
        time.sleep(1.0)
        p1 = (get(CAM + 'target-lat'), get(CAM + 'target-lon'))
        still = get(CAM + 'lock')
        shift = MM.course(p0, p1)[1]
        time.sleep(3)
        e = error((p1[0], p1[1], get(CAM + 'target-alt-ft')))
        add('K4', 'slewing', rates[0] > 3 * rates[1] > 0 and still == 'point' and shift > 300 and e <= 0.3,
            'free, slew held 2 s: %.1f deg/s at 40 deg of view, %.1f at 10 deg (the aircraft was turning too); locked on the cross, slewed up 0.6 s: the point moved %.0f ft and the lock is "%s", the camera %.2f deg from it afterwards' % (
                rates[0], rates[1], shift, still, e))
        bad = P9C.nasal_errors.__wrapped__() if hasattr(P9C.nasal_errors, '__wrapped__') else [l.strip()[:160] for l in open(LOG, errors='replace') if 'Global Hawk camera' in l or ('GlobalHawk' in l and 'rror' in l)]
        add('K0', 'no Nasal error of the camera', not bad, '%s' % (bad[:3] or 'none'))
    finally:
        P9.stop(proc)
    with open(os.path.join(HERE, 'out', 'phase9d_checks.txt'), 'w') as fh:
        for r in rows:
            fh.write('%-3s %-44s %-5s %s\n' % r)
    print('%d checks, %d pass, %d miss' % (len(rows), sum(r[2] == 'pass' for r in rows), sum(r[2] != 'pass' for r in rows)))


if __name__ == '__main__':
    main()
