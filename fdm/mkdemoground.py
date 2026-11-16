#!/usr/bin/env python3
"""The made-up airport XDM1 ("Demo Field" of the station's demo): a ground network and runway ends in FlightGear's own file formats.

    python3 mkdemoground.py        writes
        GlobalHawk/gcs/tests/fixtures/scenery/Airports/X/D/M/XDM1.groundnet.xml and XDM1.threshold.xml    what FlightGear's scenery holds for a real airport
        GlobalHawk/gcs/js/demoground.js                                                                    the same, as the `airport` command sends it (fdm/airportdata.py)

It stands in for the scenery where there is none: the demo aircraft in the page (js/demo.js), the node tests (tests/ground.test.js) and fdm/gcs_server.py
(--scenery GlobalHawk/gcs/tests/fixtures/scenery) all use it. The shape is the one that matters at EFHK, made simple: runway 04/22 (course 40 deg, 12,000 ft)
from the demo plan's threshold, a taxiway A beside it 300 ft to the right, the entry B square to the runway near its start and ending on the centreline
(as ZA does at EFHK's 22L, and not joined to the runway's own arcs), three exits C, D, E from the runway to A, and three stands at the west end, the demo plan's
among them; the third too small for the aircraft. Nothing here is a real place.
"""
import math
import os

import airportdata as AD

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN = os.path.join(HERE, '..', 'GlobalHawk', 'gcs', 'tests', 'fixtures', 'scenery')
JS = os.path.join(HERE, '..', 'GlobalHawk', 'gcs', 'js', 'demoground.js')
THR = (34.9, -117.88)               # the threshold of 04, as the demo plan's takeoff begins
HDG = 40.0
LEN = 12000.0
FT = 364567.2


def ll(a, l, thr=THR, hdg=HDG):
    """Feet along the runway's course from its threshold and to the right of it, as latitude and longitude."""
    h = math.radians(hdg)
    n, e = a * math.cos(h) - l * math.sin(h), a * math.sin(h) + l * math.cos(h)
    return thr[0] + n / FT, thr[1] + e / (FT * math.cos(math.radians(thr[0])))


def dm(v, pos, neg):
    hemi = pos if v >= 0 else neg
    v = abs(v)
    d = int(v)
    return '%s%d %.8f' % (hemi, d, (v - d) * 60.0)


# index in the file, (along, right) in feet. The indices are not the positions in the file on purpose: the airport message uses positions.
NODES = {
    30: (-400, 300),        # A, west end
    31: (20, 300),          # A at the entry B
    32: (4100, 300),        # A at exit E
    33: (6350, 300),        # A at exit C
    34: (9650, 300),        # A at exit D
    35: (12400, 300),       # A, east end
    36: (20, 60),           # B, square to the runway
    37: (170, 0),           # B, on the centreline (not joined to the runway's arcs)
    40: (300, 0),           # the runway's arcs begin
    41: (4000, 0),          # junction E
    42: (6000, 0),          # junction C
    43: (9500, 0),          # junction D
    44: (12000, 0),         # the far end
    50: (4100, 200),        # E
    51: (6180, 39),         # C
    52: (9650, 200),        # D
}
ARCS = [
    (30, 31, 'A'), (31, 32, 'A'), (32, 33, 'A'), (33, 34, 'A'), (34, 35, 'A'),
    (31, 36, 'B'), (36, 37, 'B'),
    (40, 41, '04/22'), (41, 42, '04/22'), (42, 43, '04/22'), (43, 44, '04/22'),
    (41, 50, 'E'), (50, 32, 'E'),
    (42, 51, 'C'), (51, 33, 'C'),
    (43, 52, 'D'), (52, 34, 'D'),
]
# name, type, (along, right), heading, radius m. The first is the demo plan's stand (Missions/demo-local.json), facing the taxiway.
SPOTS = [
    ('S1', 'ramp_mil_cargo', (-400, 400), -50, 30),
    ('S2', 'ramp_mil_cargo', (-400, 560), -50, 30),
    ('S3', 'tie_down', (-400, 720), -50, 15),
]
ONRWY = {40, 41, 42, 43, 44}


def build():
    nd = []
    for i, (a, l) in sorted(NODES.items()):
        la, lo = ll(a, l)
        nd.append('\t\t<node index="%d" lat="%s" lon="%s" isOnRunway="%d" holdPointType="none"/>' % (i, dm(la, 'N', 'S'), dm(lo, 'E', 'W'), 1 if i in ONRWY else 0))
    ar = []
    for a, b, n in ARCS:
        for u, v in ((a, b), (b, a)):
            ar.append('\t\t<arc begin="%d" end="%d" isPushBackRoute="0" name="%s"/>' % (u, v, n))
    pk = []
    for k, (n, t, (a, l), h, r) in enumerate(SPOTS):
        la, lo = ll(a, l)
        pk.append('\t\t<Parking index="%d" type="%s" name="%s" lat="%s" lon="%s" heading="%d" radius="%d"/>' % (k, t, n, dm(la, 'N', 'S'), dm(lo, 'E', 'W'), h, r))
    groundnet = '<?xml version="1.0" encoding="UTF-8"?>\n<groundnet>\n\t<version>1</version>\n\t<parkingList>\n%s\n\t</parkingList>\n\t<TaxiNodes>\n%s\n\t</TaxiNodes>\n\t<TaxiWaySegments>\n%s\n\t</TaxiWaySegments>\n</groundnet>\n' % (
        '\n'.join(pk), '\n'.join(nd), '\n'.join(ar))
    far = ll(LEN, 0)
    thr = '<?xml version="1.0" encoding="UTF-8"?>\n<PropertyList>\n\t<runway>\n'
    for rwy, p, h in (('04', THR, HDG), ('22', far, HDG + 180.0)):
        thr += '\t\t<threshold>\n\t\t\t<lat>%.8f</lat>\n\t\t\t<lon>%.8f</lon>\n\t\t\t<rwy>%s</rwy>\n\t\t\t<hdg-deg>%.2f</hdg-deg>\n\t\t\t<displ-m>0.0</displ-m>\n\t\t\t<stopw-m>0.0</stopw-m>\n\t\t</threshold>\n' % (p[0], p[1], rwy, h)
    thr += '\t</runway>\n</PropertyList>\n'
    return groundnet, thr


def main():
    d = os.path.join(SCEN, 'Airports', 'X', 'D', 'M')
    os.makedirs(d, exist_ok=True)
    g, t = build()
    open(os.path.join(d, 'XDM1.groundnet.xml'), 'w').write(g)
    open(os.path.join(d, 'XDM1.threshold.xml'), 'w').write(t)
    msg = AD.load('XDM1', [SCEN])
    open(JS, 'w').write('/**\n * The made-up airport XDM1 (the demo field): its ground network and runway ends as the aircraft\'s `airport` command sends them (fdm/airportdata.py).\n'
                        ' * Generated by fdm/mkdemoground.py from tests/fixtures/scenery; do not edit.\n */\n(function (root) {\n  \'use strict\';\n  const data = %s;\n'
                        '  if (typeof module !== \'undefined\' && module.exports) module.exports = data;\n  else (root.GCS = root.GCS || {}).demoground = data;\n})(typeof window !== \'undefined\' ? window : globalThis);\n' % AD.dumps(msg))
    print('XDM1: %d stands, %d nodes, %d arcs, %d runway ends; %d bytes' % (len(msg['parking']), len(msg['nodes']), len(msg['arcs']), len(msg['runways']), len(AD.dumps(msg))))


if __name__ == '__main__':
    main()
