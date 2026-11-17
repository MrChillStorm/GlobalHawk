"""A flight from a parking spot: taxi out, a box, taxi back to the spot. The taxi routes come from FlightGear's own ground network of the airport
(Airports/E/F/H/EFHK.groundnet.xml in its scenery: parking spots, taxi nodes and the arcs between them), so that the aircraft taxis on the airport's taxiways.

    python3 groundplan.py EFHK 22L 121 [out.json]      print the taxi routes (and write the plan, as the station would send it)

The plan is [taxi out, takeoff, route (the box), land, taxi in]. The box, the landing and the lost-link route are the station's local flight (js/geo.js localPlan: takeoff
from the runway's start, a box, landing on the same runway); only the takeoff's start moves, to a line-up point on the centreline a little way down the runway, where the
taxi out ends, stopped, in line. The taxi in leaves the runway by the exit named below: the rollout ends about 4,000 to 5,000 ft down the runway and the exit is beyond that.
A parking spot that faces its taxiway is chosen (a gate faces the terminal: it would need a push back, which the aircraft does not have).
"""
import heapq
import json
import math
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import wgs84 as WG             # the one earth model: WGS84's tangent plane (fdm/wgs84.py)
TERRASYNC = os.path.expanduser('~/Library/Application Support/FlightGear/TerraSync_WS3/Airports')
# per airport and runway: the threshold and heading (the airport's threshold.xml), the node where a taxiway meets the runway's start (the taxi out follows the taxiway to it and turns
# onto the centreline), how far down the runway the aircraft lines up, the node on the centreline the taxi in begins at (beyond where the rollout ends) and the exit it takes
RUNWAYS = {
    ('EFHK', '22L'): dict(thr=(60.33065824, 24.97904158), hdg=227.51, entry=487, lineup_ft=450.0, rollout_node=282, exit_node=609, length_ft=10461.0),
}
FILLET_ENTRY_FT = 150.0          # the radius of the turn from the taxiway onto the centreline
TAXI_KT, TURN_KT = 15.0, 8.0


def _dm(s):
    m = re.match(r'([NSEW])(\d+) ([\d.]+)', s)
    v = int(m.group(2)) + float(m.group(3)) / 60.0
    return -v if m.group(1) in 'SW' else v


class Net:
    """The ground network: parking spots, taxi nodes, arcs (the arcs are two-way here: the groundnet lists both directions)."""

    def __init__(self, icao):
        path = os.path.join(TERRASYNC, icao[0], icao[1], icao[2], icao + '.groundnet.xml')
        root = ET.parse(path).getroot()
        self.park = {}
        for p in root.iter('Parking'):
            self.park[p.get('name')] = dict(index=int(p.get('index')), type=p.get('type'), name=p.get('name'), lat=_dm(p.get('lat')), lon=_dm(p.get('lon')),
                                            heading=float(p.get('heading')) % 360.0, radius=float(p.get('radius') or 0))
        self.node = {}
        for n in root.iter('node'):
            self.node[int(n.get('index'))] = (_dm(n.get('lat')), _dm(n.get('lon')))
        self.adj = {}
        for a in root.iter('arc'):
            u, v = int(a.get('begin')), int(a.get('end'))
            if a.get('isPushBackRoute') == '1':
                continue
            self.adj.setdefault(u, set()).add(v)
            self.adj.setdefault(v, set()).add(u)

    def dist(self, p, q):
        return WG.distance(p, q)

    def nearest(self, p, among=None):
        return min((self.dist(p, self.node[i]), i) for i in (among or self.node))[1]

    def route(self, a, b, forbid=()):
        best, prev, q = {a: 0.0}, {}, [(0.0, a)]
        while q:
            d, x = heapq.heappop(q)
            if x == b:
                break
            if d > best.get(x, 1e18):
                continue
            for v in self.adj.get(x, ()):
                if v in forbid and v != b:
                    continue
                nd = d + self.dist(self.node[x], self.node[v])
                if nd < best.get(v, 1e18):
                    best[v], prev[v] = nd, x
                    heapq.heappush(q, (nd, v))
        if b not in best:
            raise ValueError('no taxi route from node %d to node %d' % (a, b))
        path = [b]
        while path[-1] != a:
            path.append(prev[path[-1]])
        return path[::-1]


class Frame:
    """Feet along a runway's heading from its threshold and to the right of it, and back to latitude and longitude."""

    def __init__(self, thr, hdg):
        self.thr, self.h = thr, math.radians(hdg)

    def to(self, p):
        n, e = WG.enu(self.thr, p)
        return n * math.cos(self.h) + e * math.sin(self.h), -n * math.sin(self.h) + e * math.cos(self.h)

    def ll(self, a, l):
        n, e = a * math.cos(self.h) - l * math.sin(self.h), a * math.sin(self.h) + l * math.cos(self.h)
        return tuple(WG.from_enu(self.thr, n, e))


def pt(p):
    return [round(p[0], 6), round(p[1], 6)]


def taxi_out(net, fr, rw, spot):
    """The points from the parking spot to the end of the line-up: the taxiway's nodes to the entry, the turn onto the centreline, and down it to the line-up point."""
    start = net.nearest((spot['lat'], spot['lon']), [i for i in net.node if i not in net.park])
    nodes = net.route(start, rw['entry'])
    pts = [net.node[i] for i in nodes]
    # the taxiway meets the runway square-on at the entry's end: the turn onto the centreline is an arc tangent to the taxiway's last straight and to the centreline
    a0, l0 = fr.to(net.node[rw['entry']])
    a1, l1 = fr.to(net.node[nodes[-2]]) if len(nodes) > 1 else (a0, l0 - 500.0)
    assert abs(a1 - a0) < 60.0, 'the last leg of the taxiway to the entry is not square to the runway'
    R = FILLET_ENTRY_FT
    pts = pts[:-1]                                    # the entry itself is where the arc begins, 150 ft from the centreline: stands on that straight
    pts.append(fr.ll(a0, -R))
    for t in (30.0, 60.0):
        r = math.radians(t)
        pts.append(fr.ll(a0 + R * (1 - math.cos(r)), -R + R * math.sin(r)))
    pts.append(fr.ll(a0 + R, 0.0))
    pts.append(fr.ll(rw['lineup_ft'], 0.0))
    return pts


def taxi_in(net, fr, rw, spot):
    """From the centreline beyond the rollout, off by the exit, round to the parking spot."""
    end_node = net.nearest((spot['lat'], spot['lon']), [i for i in net.node if i not in net.park])
    nodes = net.route(rw['exit_node'], end_node, forbid={i for i in net.node if abs(fr.to(net.node[i])[1]) < 12 and i != rw['exit_node']})
    return [net.node[rw['rollout_node']]] + [net.node[i] for i in nodes] + [(spot['lat'], spot['lon'])]


def length_ft(net, pts):
    return sum(net.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))


def build(icao, rwy, parking, box_plan):
    """The plan: box_plan is the station's local flight from the runway's start (geo.localPlan): its route, land, lost-link and sites are kept."""
    net = Net(icao)
    rw = RUNWAYS[(icao, rwy)]
    fr = Frame(rw['thr'], rw['hdg'])
    spot = net.park[parking]
    out_pts, in_pts = taxi_out(net, fr, rw, spot), taxi_in(net, fr, rw, spot)
    route = [it for it in box_plan['items'] if it['kind'] == 'route'][0]
    land = [it for it in box_plan['items'] if it['kind'] == 'land'][0]
    plan = dict(box_plan)
    plan['id'] = 'taxi-box-taxi'
    plan['note'] = 'From parking spot %s: taxi to runway %s, take off, a box, land on the same runway, taxi back to the spot.' % (parking, rwy)
    plan['items'] = [
        dict(kind='taxi', points=[pt(p) for p in out_pts], speed=TAXI_KT, turn_speed=TURN_KT, stop=True),
        dict(kind='takeoff', start=pt(fr.ll(rw['lineup_ft'], 0.0)), end=pt(fr.ll(9000.0 + rw['lineup_ft'], 0.0))),
        route,
        land,
        dict(kind='taxi', points=[pt(p) for p in in_pts], speed=TAXI_KT, turn_speed=TURN_KT, stop=True),
    ]
    return plan, dict(out=out_pts, into=in_pts, spot=spot, frame=fr, net=net, rw=rw)


if __name__ == '__main__':
    icao, rwy, parking = sys.argv[1], sys.argv[2], sys.argv[3]
    net = Net(icao)
    rw = RUNWAYS[(icao, rwy)]
    fr = Frame(rw['thr'], rw['hdg'])
    spot = net.park[parking]
    o, i = taxi_out(net, fr, rw, spot), taxi_in(net, fr, rw, spot)
    print('spot %s (%s, radius %.0f m, faces %.0f deg) at %.5f %.5f' % (parking, spot['type'], spot['radius'], spot['heading'], spot['lat'], spot['lon']))
    print('taxi out: %d points, %.0f ft' % (len(o), length_ft(net, [(spot['lat'], spot['lon'])] + o)))
    for p in o:
        print('   %.6f %.6f   along %6.0f ft, %5.0f ft right' % (p[0], p[1], *fr.to(p)))
    print('taxi in: %d points, %.0f ft' % (len(i), length_ft(net, i)))
    for p in i:
        print('   %.6f %.6f   along %6.0f ft, %5.0f ft right' % (p[0], p[1], *fr.to(p)))
