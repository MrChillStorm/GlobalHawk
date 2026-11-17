#!/usr/bin/env python3
"""The one geometry of the earth every piece of the aircraft, the station and the tests uses: WGS84, the ellipsoid GPS, FlightGear and JSBSim fly on.

Positions are [lat, lon] in degrees (geodetic latitude, longitude). A local frame is the tangent plane at an origin point: north and east in feet, the frame
GPS receivers and every flight-management system work in. Its pieces:

    enu(o, p)           -> (north_ft, east_ft) of the point p in the tangent plane at o (through the points' ECEF coordinates: exact, no scale factors, no cosines of a latitude)
    from_enu(o, n, e)   -> [lat, lon] of the surface point whose tangent-plane coordinates about o are (n, e) ft (the inverse of enu, to well under a thousandth of a foot)
    course(a, b)        -> (deg true, ft): the bearing from a to b at a, and the distance in the tangent plane at a
    along(p, deg, ft)   -> the point ft along the course deg from p

A straight line in the tangent plane at its start is the normal section of the ellipsoid towards its end, which is the geodesic to a few micrometres over a 5 nmi final, so a runway's
centreline (a geodesic through the threshold at the runway's heading) is a straight line here, and the aircraft's cross-track against it is the distance to the line. The earlier model
(364,567.2 ft for a degree of latitude and the same times cos(lat) for a degree of longitude, everywhere) tilted the final by 0.05 deg at 60 deg N (N/M is 1.0016 there, 1.0067 at the
equator), and read the aircraft's track in a frame that is not the plane's.

The fdm/laws.py channels, the mission manager in Python and in Nasal, the head-up display and the station's geo.js carry the same formulas (docs/PLAN.md, "One earth").
"""
import math

A_M = 6378137.0                      # WGS84 semi-major axis, m
F_INV = 298.257223563                # WGS84 flattening: 1 / F_INV
E2 = (1.0 / F_INV) * (2.0 - 1.0 / F_INV)   # first eccentricity squared, 0.00669437999014
FT_PER_M = 1.0 / 0.3048
D2R = math.pi / 180.0


def ecef(lat, lon):
    """the point on the ellipsoid's surface, metres from the earth's centre (x to 0 N 0 E, y to 0 N 90 E, z to the pole)"""
    p, l = lat * D2R, lon * D2R
    sp = math.sin(p)
    n = A_M / math.sqrt(1.0 - E2 * sp * sp)
    return n * math.cos(p) * math.cos(l), n * math.cos(p) * math.sin(l), n * (1.0 - E2) * sp


def enu(o, p):
    """(north, east) ft of p in the tangent plane at o"""
    x0, y0, z0 = ecef(o[0], o[1])
    x, y, z = ecef(p[0], p[1])
    dx, dy, dz = x - x0, y - y0, z - z0
    sp, cp, sl, cl = math.sin(o[0] * D2R), math.cos(o[0] * D2R), math.sin(o[1] * D2R), math.cos(o[1] * D2R)
    e = -sl * dx + cl * dy
    n = -sp * cl * dx - sp * sl * dy + cp * dz
    return n * FT_PER_M, e * FT_PER_M


def ft_per_deg(lat):
    """feet in a degree of latitude and in a degree of longitude at the latitude (the meridian and the parallel's radii of the ellipsoid)"""
    s = math.sin(lat * D2R)
    w = math.sqrt(1.0 - E2 * s * s)
    m = A_M * (1.0 - E2) / (w * w * w)
    nn = A_M / w
    return m * D2R * FT_PER_M, nn * math.cos(lat * D2R) * D2R * FT_PER_M


def from_enu(o, n, e):
    """[lat, lon] of the surface point at (n, e) ft in the tangent plane at o: Newton steps on enu() from the local scale (each takes the error down about thirty times at 100 nmi, a few hundred times at 5 nmi; it stops at 1e-5 ft)"""
    kn, ke = ft_per_deg(o[0])
    lat, lon = o[0] + n / kn, o[1] + e / ke
    for _ in range(12):
        cn, ce = enu(o, (lat, lon))
        if abs(n - cn) < 1e-5 and abs(e - ce) < 1e-5:
            break
        kn, ke = ft_per_deg(lat)
        lat += (n - cn) / kn
        lon += (e - ce) / ke
    return [lat, lon]


def course(a, b):
    """(deg true, ft) from a to b: the bearing at a and the distance in the tangent plane at a"""
    n, e = enu(a, b)
    return (math.degrees(math.atan2(e, n)) + 360.0) % 360.0, math.hypot(n, e)


def along(p, deg, ft):
    """the point ft along the course deg from p"""
    c = deg * D2R
    return from_enu(p, ft * math.cos(c), ft * math.sin(c))


def distance(a, b):
    return course(a, b)[1]
