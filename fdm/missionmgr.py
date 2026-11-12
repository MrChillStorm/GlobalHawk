"""The mission manager, standing in for the one that will run in FlightGear's Nasal: it hands the flight laws their
next leg, target and mode a few times a second and does nothing else (docs/FLIGHT-LAWS.md, section 5). Plain Python,
for the JSBSim checks. It only writes ap/* properties and the gear command.

A plan is a list of items:
    dict(kind='taxi', points=[(lat, lon), ...], speed=15, turn_speed=8)       ends stopped at the last point if stop=True
    dict(kind='takeoff', start=(lat, lon), end=(lat, lon), elev=2300)
    dict(kind='route', points=[(lat, lon, alt_ft), ...])
    dict(kind='land', fix=(lat, lon), aim=(lat, lon), elev=2300)
    dict(kind='hold', centre=(lat, lon), alt=20000)                           a circle; never ends by itself
A route may carry start=(lat, lon): its first leg then begins there, not where the aircraft is (resuming a plan).

Contingencies (docs/FLIGHT-LAWS.md, section 6):
    lost_link=[items]       what the aircraft flies instead of the rest of the plan once ap/link-lost is set
    sites=[dict(aim=(lat, lon), course=deg, elev=ft, name=...)]     runways for a landing without the engine
"""
import math

import numpy as np

FT_PER_DEG = 364567.2
KT = 1.6878099
RATE = 12                      # frames between the manager's looks: 10 a second
NM = 6076.1
GLIDE_TAN = 0.07782            # the approach path, 4.45 deg (fdm/laws.py)
GLIDE_CL = 0.8                 # the lift coefficient of the glide without the engine
GLIDE_RATIO = 20.0             # what the planner counts on: the model's 26 less a margin for wind and turns
ENTRY_HEIGHT = 2500.0          # ft above the runway on the glide path: where the entry point is
TURN_COST = 300.0              # ft per 90 deg of turn
IN_HAND = 1000.0               # ft kept over at the entry point when choosing a site
CIRCLE_BANK = 15.0             # deg
FINAL_SURPLUS = 300.0          # ft above the glide path the circle aims to leave for the final
WING_AREA = 540.0
K_PSI = 1.2                    # the heading law's gain (fdm/laws.py), deg of bank per deg at 600 ft/s
MAX_ALT = 65000.0              # ft: the aircraft's maximum (NASA 2008)
HOLD_BANK = 11.5               # deg: a hold's circle is flown well inside the bank limit, so it can be caught without overshoot


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
    def __init__(self, f, plan, lost_link=None, sites=()):
        self.f, self.plan = f, list(plan)
        self.lost_link, self.sites = lost_link, list(sites)
        self.contingency, self.alert = None, None
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
            first = tuple(it['start']) if it.get('start') else self.here()
            pts = [first + (f['position/h-sl-ft'],)] + list(it['points'])
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
        elif kind == 'hold':
            f['ap/land-mode'] = 0
            f['ap/roll-mode'], f['ap/ground-steer'] = 1, 0
            it['side'] = 1.0
            self.vertical(it['alt'])
        elif kind == 'engine_out':
            self.choose_site(it)
            f['ap/land-mode'] = 0
            f['ap/roll-mode'], f['ap/ground-steer'] = 2, 0
            f['ap/pitch-mode'], f['ap/thrust-mode'], f['ap/speed-schedule'] = 1, 2, 0
            f['ap/spoiler-mode'], f['ap/spoiler-cmd'] = 1, 0.0
            f['gear/gear-cmd-norm'] = 0
            f['ap/speed-cmd-kcas'] = self.glide_kcas()
            self.leg(self.here(), it['entry'])
            it['task'] = 'glide'
            self.note('glide to %s' % it['site'].get('name', 'the runway'))

    # ---- without the engine (section 6.3)
    def glide_kcas(self):
        """The calibrated airspeed for the glide's lift coefficient at this weight and height."""
        f = self.f
        q = f['inertia/weight-lbs'] / (GLIDE_CL * WING_AREA)
        p = f['atmosphere/P-psf']
        mach = math.sqrt(q / (0.7 * p))
        qc = p * ((1 + 0.2 * mach * mach) ** 3.5 - 1)
        return 661.4786 * math.sqrt(5 * ((qc / 2116.2166 + 1) ** (2 / 7.0) - 1))

    def entry(self, site):
        """The entry point: on the extended centreline where the glide path is ENTRY_HEIGHT above the runway."""
        d = ENTRY_HEIGHT / GLIDE_TAN
        c = math.radians(site['course'])
        return (site['aim'][0] - d * math.cos(c) / FT_PER_DEG, site['aim'][1] - d * math.sin(c) / (FT_PER_DEG * math.cos(math.radians(site['aim'][0]))))

    def reach(self, site):
        """Height left over at a site's entry point, by the planner's book: what there is less what is needed."""
        f = self.f
        brg, dist = course(self.here(), self.entry(site))
        trk = math.degrees(math.atan2(f['velocities/v-east-fps'], f['velocities/v-north-fps']))
        need = dist / GLIDE_RATIO + TURN_COST * abs(turn(trk, brg)) / 90.0 + site['elev'] + ENTRY_HEIGHT + IN_HAND
        return f['position/h-sl-ft'] - need

    def choose_site(self, it):
        ranked = sorted(self.sites, key=self.reach, reverse=True)
        best = ranked[0]
        it['site'], it['entry'], it['expected'] = best, self.entry(best), self.reach(best) + IN_HAND
        if self.reach(best) < 0:
            # nothing in reach: towards the nearest all the same, and say so. A landing off a runway is not built.
            best = min(self.sites, key=lambda s: course(self.here(), self.entry(s))[1])
            it['site'], it['entry'], it['expected'] = best, self.entry(best), self.reach(best) + IN_HAND
            self.alert = 'no runway in reach'
            self.note('ALERT: no runway in reach')
        self.note('site %s: %.0f ft expected in hand at the entry point (%s)' % (
            best.get('name', '?'), it['expected'], ', '.join('%s %+.0f' % (s.get('name', '?'), self.reach(s) + IN_HAND) for s in ranked)))

    def engine_out(self, it):
        f = self.f
        site, ent = it['site'], it['entry']
        if it['task'] == 'glide':
            f['ap/speed-cmd-kcas'] = self.glide_kcas()
        elif it['task'] == 'circle':
            f['ap/speed-cmd-kcas'] = f['ap/approach-keas']
        vg = max(f['velocities/vg-fps'], 100.0)
        radius = vg * vg / (32.174 * math.tan(math.radians(CIRCLE_BANK)))
        brg, dist = course(self.here(), ent)
        above = f['position/h-sl-ft'] - site['elev'] - ENTRY_HEIGHT
        if it['task'] == 'glide':
            it['surplus'] = above - dist / GLIDE_RATIO
            if dist < radius:
                # circle on the side the aircraft is on, so that the circle touches the centreline at the entry point
                side = 1.0 if turn(site['course'], course(ent, self.here())[0]) >= 0 else -1.0
                it['side'], it['task'], it['arrived'] = side, 'circle', above
                f['ap/roll-mode'] = 1
                f['ap/speed-cmd-kcas'] = f['ap/approach-keas']       # with spoilers out the glide speed is too near the limit
                self.note('circle %s over the entry point, %.0f ft above the glide path there (planner expected %.0f)' % (
                    'right' if side > 0 else 'left', above, it['expected']))
        if it['task'] == 'circle':
            side = it['side']
            c = math.radians(site['course'] + 90.0 * side)
            centre = (ent[0] + radius * math.cos(c) / FT_PER_DEG, ent[1] + radius * math.sin(c) / (FT_PER_DEG * math.cos(math.radians(ent[0]))))
            out, d = course(centre, self.here())                    # bearing from the centre to the aircraft
            tangent = out + 90.0 * side
            f['ap/heading-cmd-deg'] = (tangent + side * float(np.clip(60.0 * (d - radius) / radius, -45.0, 80.0))) % 360.0
            # the way round to the entry point, which is where the circle touches the centreline
            at_entry = (site['course'] - 90.0 * side) % 360.0       # bearing from the centre to the entry point
            arc = ((at_entry - out) * side) % 360.0
            if arc > 340.0:
                arc -= 360.0                                        # just past it
            surplus = above - math.radians(arc) * radius / GLIDE_RATIO
            it['surplus'] = surplus
            f['ap/spoiler-cmd'] = float(np.clip((surplus - FINAL_SURPLUS) / 1000.0, 0.0, 1.0))
            trk = math.degrees(math.atan2(f['velocities/v-east-fps'], f['velocities/v-north-fps']))
            aligned = abs(turn(trk, site['course'])) < 20.0 and abs(arc) < 30.0
            if (aligned and surplus < 2.0 * FINAL_SURPLUS) or surplus < -500.0:
                it['task'], it['final'] = 'final', surplus
                self.leg(ent, site['aim'])
                f['ap/rwy-elev-ft'] = site['elev']
                f['ap/roll-mode'], f['ap/ground-steer'] = 2, 1
                f['ap/land-mode'] = 1
                f['gear/gear-cmd-norm'] = 1
                self.note('final, %.0f ft above the glide path' % surplus)
        elif it['task'] == 'final':
            if f['ap/rollout'] == 1 and f['ap/ground-speed-kt'] < 15.0:
                self.note('rollout over')
                f['ap/taxi-speed-kt'] = 0.0
                f['ap/thrust-mode'] = 4
                self.next()

    def circle(self, centre, radius, side, out_max=45.0, lead=False):
        """The heading that flies a circle about a centre: the tangent, turned in or out for the distance off it.
        Returns the bearing from the centre and the distance from it."""
        f = self.f
        out, d = course(centre, self.here())
        ahead = 0.0
        if lead:
            # the heading law banks in proportion to the heading error, so a steady turn needs the command ahead
            # of the nose by the error that gives the circle's bank (without it the hold sat 0.7 nmi outside)
            bank = math.degrees(math.atan(f['velocities/vg-fps'] ** 2 / (32.174 * radius)))
            ahead = bank / (K_PSI * max(f['velocities/vt-fps'], 100.0) / 600.0)
        f['ap/heading-cmd-deg'] = (out + 90.0 * side + side * (ahead + float(np.clip(60.0 * (d - radius) / radius, -out_max, 80.0)))) % 360.0
        return out, d

    def hold_radius(self):
        vg = max(self.f['velocities/vg-fps'], 100.0)
        return vg * vg / (32.174 * math.tan(math.radians(HOLD_BANK)))

    def contingencies(self):
        """Leave the plan when the link is lost or the engine stops. Only in the air, and only once each."""
        f = self.f
        kind = self.plan[self.i]['kind']
        if f['engine/failed'] == 1 and self.contingency != 'engine' and kind in ('route', 'land', 'hold') and self.sites and f['ap/rollout'] == 0:
            self.contingency = 'engine'
            self.note('ENGINE FAILED')
            self.plan = self.plan[:self.i + 1] + [dict(kind='engine_out')]
            self.next()
        elif f['ap/link-lost'] == 1 and self.contingency is None and kind in ('route', 'hold') and self.lost_link:
            self.contingency = 'link'
            self.note('LINK LOST: the contingency route')
            self.plan = self.plan[:self.i + 1] + [dict(d) for d in self.lost_link]
            self.next()

    def vertical(self, alt):
        """Climb, descend or hold towards a height."""
        f = self.f
        h = f['position/h-sl-ft']
        alt = min(alt, MAX_ALT)
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
        self.contingencies()
        if self.done:
            return
        it = self.plan[self.i]
        kind = it['kind']
        togo = f['ap/leg-togo-ft']
        if kind == 'engine_out':
            self.engine_out(it)
            return
        if kind == 'hold':
            it['radius'] = it.get('radius') or self.hold_radius()      # fixed once the hold begins: the station draws it
            self.circle(it['centre'], it['radius'], it['side'], out_max=30.0, lead=True)
            self.vertical(it['alt'])
            return
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
            self.vertical(it.get('alt_override', pts[self.k + 1][2]))
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
                    it.pop('alt_override', None)
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
