"""The mission manager, standing in for the one that will run in FlightGear's Nasal: it hands the flight laws their
next leg, target and mode a few times a second and does nothing else (docs/FLIGHT-LAWS.md, section 5). Plain Python,
for the JSBSim checks. It only writes ap/* properties and the gear command.

A plan is a list of items:
    dict(kind='taxi', points=[(lat, lon), ...], speed=15, turn_speed=8)       ends stopped at the last point if stop=True
    dict(kind='takeoff', start=(lat, lon), end=(lat, lon), elev=2300)
    dict(kind='route', points=[(lat, lon, alt_ft), ...])
    dict(kind='land', fix=(lat, lon), aim=(lat, lon), elev=2300)
"""
import math

import numpy as np

FT_PER_DEG = 364567.2
KT = 1.6878099
RATE = 12                      # frames between the manager's looks: 10 a second


class Field:
    """A flat patch of earth: feet north and east of an origin to latitude and longitude and back."""

    def __init__(self, lat, lon, elev):
        self.lat, self.lon, self.elev = lat, lon, elev

    def ll(self, n, e):
        return self.lat + n / FT_PER_DEG, self.lon + e / (FT_PER_DEG * math.cos(math.radians(self.lat)))

    def ne(self, lat, lon):
        return (lat - self.lat) * FT_PER_DEG, (lon - self.lon) * FT_PER_DEG * math.cos(math.radians(self.lat))


def course(a, b):
    dn = (b[0] - a[0]) * FT_PER_DEG
    de = (b[1] - a[1]) * FT_PER_DEG * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(de, dn)) % 360.0, math.hypot(dn, de)


def turn(c0, c1):
    return (c1 - c0 + 180.0) % 360.0 - 180.0


class Manager:
    def __init__(self, f, plan):
        self.f, self.plan = f, list(plan)
        self.i, self.k, self.frame, self.done = 0, 0, 0, False
        self.events = []
        self.begin()

    def note(self, text):
        self.events.append((self.f['simulation/sim-time-sec'], text))

    def leg(self, a, b):
        f = self.f
        f['ap/leg-lat0-deg'], f['ap/leg-lon0-deg'], f['ap/leg-lat1-deg'], f['ap/leg-lon1-deg'] = a[0], a[1], b[0], b[1]

    def here(self):
        return (self.f['position/lat-geod-deg'], self.f['position/long-gc-deg'])

    def begin(self):
        """Set the laws up for the item that starts now."""
        f = self.f
        if self.i >= len(self.plan):
            self.done = True
            return
        it = self.plan[self.i]
        self.k = 0
        kind = it['kind']
        self.note('begin ' + kind)
        if kind == 'taxi':
            given = it['points'](self) if callable(it['points']) else it['points']
            pts = [self.here()] + list(given)
            it['_pts'] = pts
            self.leg(pts[0], pts[1])
            f['ap/land-mode'] = 0
            f['ap/thrust-mode'], f['ap/ground-steer'], f['ap/pitch-mode'], f['ap/roll-mode'] = 4, 1, 0, 0
            f['ap/spoiler-mode'], f['ap/spoiler-cmd'] = 1, 0.0
            f['ap/taxi-speed-kt'] = it.get('speed', 15.0)
            f['gear/gear-cmd-norm'] = 1
        elif kind == 'takeoff':
            self.leg(it['start'], it['end'])
            f['ap/taxi-speed-kt'] = 0.0
            f['ap/thrust-mode'], f['ap/ground-steer'], f['ap/pitch-mode'], f['ap/roll-mode'] = 1, 1, 3, 2
            f['ap/spoiler-mode'], f['ap/spoiler-cmd'] = 1, 0.0
        elif kind == 'route':
            pts = [self.here() + (f['position/h-sl-ft'],)] + list(it['points'])
            it['_pts'] = pts
            self.leg(pts[0], pts[1])
            f['ap/roll-mode'], f['ap/ground-steer'] = 2, 0
            self.vertical(pts[1][2])
        elif kind == 'land':
            # level towards the runway in the landing configuration until the glide path comes down to the aircraft
            self.leg(it['fix'], it['aim'])
            f['ap/rwy-elev-ft'] = it['elev']
            f['ap/roll-mode'], f['ap/ground-steer'] = 2, 1
            f['ap/alt-cmd-ft'] = f['position/h-sl-ft']
            f['ap/pitch-mode'], f['ap/thrust-mode'] = 2, 3
            f['ap/speed-schedule'] = 0
            f['ap/speed-cmd-kcas'] = f['ap/approach-keas']
            f['ap/spoiler-mode'], f['ap/spoiler-cmd'] = 1, 0.667
            f['gear/gear-cmd-norm'] = 1
            it['_on_path'] = False

    def vertical(self, alt):
        """Climb, descend or hold towards a height."""
        f = self.f
        h = f['position/h-sl-ft']
        f['ap/alt-cmd-ft'] = alt
        f['ap/speed-schedule'] = 1
        if abs(alt - h) <= 150.0:
            mode = 'level'
            f['ap/pitch-mode'], f['ap/thrust-mode'], f['ap/spoiler-cmd'] = 2, 3, 0.0
        elif alt > h:
            mode = 'climb'
            f['ap/pitch-mode'], f['ap/thrust-mode'], f['ap/spoiler-cmd'] = 1, 1, 0.0
        else:
            mode = 'descent'
            f['ap/pitch-mode'], f['ap/thrust-mode'], f['ap/spoiler-cmd'] = 1, 2, 0.5
        f['ap/spoiler-mode'] = 1
        if getattr(self, 'vmode', None) != mode:
            self.vmode = mode
            self.note(mode + ' to %.0f ft' % alt)

    def step(self):
        """Call every frame; acts ten times a second."""
        self.frame += 1
        if self.done or self.frame % RATE:
            return
        f = self.f
        it = self.plan[self.i]
        kind = it['kind']
        togo = f['ap/leg-togo-ft']
        if kind == 'taxi':
            pts = it['_pts']
            last = self.k == len(pts) - 2
            if not last:
                c0, _ = course(pts[self.k], pts[self.k + 1])
                c1, _ = course(pts[self.k + 1], pts[self.k + 2])
                bend = abs(turn(c0, c1))
                # slow for the corner, then take the next leg a little before it
                fast, slow = it.get('speed', 15.0), it.get('turn_speed', 8.0)
                f['ap/taxi-speed-kt'] = fast if bend <= 20.0 else float(np.clip(slow + (fast - slow) * (togo - 100.0) / 250.0, slow, fast))
                if togo < 40.0:
                    self.k += 1
                    self.leg(pts[self.k], pts[self.k + 1])
            else:
                stop = it.get('stop', True)
                if stop:
                    # come down to a walk, then stop on the point
                    f['ap/taxi-speed-kt'] = 0.0 if togo < 12.0 else min(it.get('speed', 15.0), max(3.0, 0.12 * togo))
                    if togo < 12.0 and f['ap/ground-speed-kt'] < 0.3:
                        self.next()
                elif togo < 40.0:
                    self.next()
        elif kind == 'takeoff':
            if f['aero/wheel-height-ft'] > 100.0:
                f['gear/gear-cmd-norm'] = 0
                f['ap/speed-schedule'], f['ap/pitch-mode'], f['ap/ground-steer'] = 1, 1, 0
                self.note('airborne, climb')
                self.next()
        elif kind == 'route':
            pts = it['_pts']
            self.vertical(pts[self.k + 1][2])
            last = self.k == len(pts) - 2
            lead = 0.0
            if not last:
                c0, _ = course(pts[self.k], pts[self.k + 1])
                c1, _ = course(pts[self.k + 1], pts[self.k + 2])
                bank = math.radians(max(f['ap/bank-limit-deg'] - 2.0, 5.0))
                radius = f['velocities/vg-fps'] ** 2 / (32.174 * math.tan(bank))
                lead = radius * math.tan(math.radians(abs(turn(c0, c1))) / 2.0) + 5.0 * f['velocities/vg-fps']
            if togo < max(lead, 500.0):
                if last:
                    self.next()
                else:
                    self.k += 1
                    self.leg(pts[self.k], pts[self.k + 1])
                    self.note('leg %d' % (self.k + 1))
        elif kind == 'land':
            if not it['_on_path']:
                f['ap/speed-cmd-kcas'] = f['ap/approach-keas']
                if f['ap/glide-error-ft'] > -10.0:
                    it['_on_path'] = True
                    f['ap/pitch-mode'] = 1
                    f['ap/land-mode'] = 1
                    self.note('glide path')
            elif f['ap/rollout'] == 1 and f['ap/ground-speed-kt'] < 15.0:
                self.note('rollout over')
                self.next()

    def next(self):
        self.i += 1
        self.begin()
