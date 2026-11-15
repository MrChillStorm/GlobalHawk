"""The mission manager, standing in for the one that will run in FlightGear's Nasal: it hands the flight laws their
next leg, target and mode a few times a second and does nothing else (docs/FLIGHT-LAWS.md, section 5). Plain Python,
for the JSBSim checks. It only writes ap/* properties and the gear command.

A plan is a list of items:
    dict(kind='taxi', points=[(lat, lon), ...], speed=15, turn_speed=8)       ends stopped at the last point if stop=True
    dict(kind='takeoff', start=(lat, lon), end=(lat, lon), elev=2300)
    dict(kind='route', points=[(lat, lon, alt_ft), ...])
    dict(kind='land', fix=(lat, lon), aim=(lat, lon), elev=2300)
    dict(kind='hold', centre=(lat, lon), alt=20000)                           a circle; never ends by itself
    (made by the manager, not given:) dict(kind='go_around', ...)            the landing's entry contract broken: a circle over the fix down to the final's height, then the landing
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
CAPTURE_SPEED_KT = 10.0        # the glide is taken over only within this many kt of the approach speed: 30 kt over it the speed-by-elevator law pitched up 15 deg and the aircraft zoomed through the path
GLIDE_CL = 0.8                 # the lift coefficient of the glide without the engine
GLIDE_RATIO = 20.0             # what the planner counts on: the model's 26 less a margin for wind and turns
ENTRY_HEIGHT = 2500.0          # ft above the runway on the glide path: where the entry point is
TURN_COST = 300.0              # ft per 90 deg of turn
IN_HAND = 1000.0               # ft kept over at the entry point when choosing a site
CIRCLE_BANK = 15.0             # deg
FINAL_SURPLUS = 300.0          # ft above the glide path the circle aims to leave for the final
WING_AREA = 540.0
K_PSI = 1.2                    # the heading law's gain (fdm/laws.py), deg of bank per deg at 600 ft/s
LANDING_LEVEL = 1                # the level-off before a landing is flown in the landing configuration: the spoilers end at LANDING_SPOILER and the gear goes down as it begins (retracted to nothing and put out again at the landing's start they dipped it 21 ft)
LANDING_SPOILER = 0.667        # the spoilers' command in the landing configuration, before the glide path is taken (the laws' spoiler base)
LEVEL_BEGIN_FT = 400.0         # the landing keeps the level's height command while the aircraft is within this of it
MAX_ALT = 65000.0              # ft: the aircraft's maximum (NASA 2008)
HOLD_BANK = 11.5               # deg: a hold's circle is flown well inside the bank limit, so it can be caught without overshoot
# the landing task's entry contract and the go-around task it hands over to when the contract is broken (docs/PLAN.md, "The aircraft refuses what it cannot fly")
ENTRY_CAPTURE_FT = ((12000.0, 500.0), (20000.0, 1500.0), (26000.0, 2000.0))   # (weight lb, ft above the path at 10 nmi the capture still takes over by 1.5 nmi out): flown, above.py
ENTRY_MARGIN = 0.8             # of that
ENTRY_TOGO_MIN_NM = 1.5        # to go at which no height above the path is taken; the limit grows from there with the way to go ...
ENTRY_SPAN_NM = 8.5            # ... as the 10 nmi it was measured at (1.5 to 10 nmi) ...
ENTRY_TOGO_MAX_NM = 12.0       # ... and no further (not measured beyond)
LAND_FIX_GAP_FT = 2634.0       # the height under the glide path the final is begun from: the capture gap flown (2,484 ft, fdm/capability.py) and the planner's 150 ft
GO_AROUND_MIN_AGL = 1000.0     # ft over the ground: the go-around's circle comes down to this at the least
GO_AROUND_ALT_ABOVE = 100.0    # ft: the go-around hands back to the landing no higher than this over the height it came down to (the capture gap has 150 ft of margin) ...
GO_AROUND_ALT_BELOW = 300.0    # ... and no lower than this under it ...
GO_AROUND_FIX_FT = 2500.0      # ... within this of the fix ...
GO_AROUND_TRACK_DEG = 20.0     # ... on a track within this of the final's course


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
    go_arounds = 0                  # how many go-arounds any manager has begun: the checks that should land at once count on it being 0 (a go-around hides nothing)

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

    def after(self, i):
        """The point the leg that ends item i's last waypoint is followed by: a landing's aiming point, else none."""
        nxt = self.plan[i + 1] if i + 1 < len(self.plan) else None
        return tuple(nxt['aim']) if nxt is not None and nxt['kind'] == 'land' else None

    def set_next(self, p):
        f = self.f
        if p is None:
            f['ap/next-valid'] = 0
        else:
            f['ap/next-lat-deg'], f['ap/next-lon-deg'], f['ap/next-valid'] = p[0], p[1], 1

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
        vm, lv = int(round(f['ap/vmode'])), f['ap/v-level-alt']          # what the vertical task was doing, before this item takes it over
        f['ap/vt-on'], f['ap/sp-ext'], f['ap/vt-sp-end'] = 0, -1, 0
        f['ap/tk-done'], f['ap/ld-captured'] = 0, 0                 # the laws' latches start clear: the item may follow one of its own kind in the same call, and they would never see the task off
        f['ap/tk-on'], f['ap/tx-on'], f['ap/ld-on'], f['ap/ci-on'] = 0, 0, 0, 0          # the laws' takeoff, taxi, landing and circle tasks: each item turns on its own
        f['ap/next-valid'] = 0
        f['ap/turn-ack'] = f['ap/turn-done']
        if kind == 'taxi':
            given = it['points'](self) if callable(it['points']) else it['points']
            pts = [self.here()] + list(given)
            it['_pts'] = pts
            self.leg(pts[0], pts[1])
            f['ap/land-mode'] = 0
            f['ap/thrust-mode'], f['ap/ground-steer'], f['ap/pitch-mode'], f['ap/roll-mode'] = 4, 1, 0, 0
            f['ap/spoiler-mode'], f['ap/spoiler-cmd'] = 1, 0.0
            f['ap/taxi-speed-kt'] = it.get('speed', 15.0)
            f['ap/tx-fast'], f['ap/tx-slow'], f['ap/tx-stop'] = it.get('speed', 15.0), it.get('turn_speed', 8.0), 1 if it.get('stop', True) else 0
            self.taxi_leg(it)
            f['ap/tx-on'] = 1
            f['gear/gear-cmd-norm'] = 1
        elif kind == 'takeoff':
            self.leg(it['start'], it['end'])
            f['ap/taxi-speed-kt'] = 0.0
            f['ap/thrust-mode'], f['ap/ground-steer'], f['ap/pitch-mode'], f['ap/roll-mode'] = 1, 1, 3, 2
            f['ap/spoiler-mode'], f['ap/spoiler-cmd'] = 1, 0.0
            f['ap/tk-on'] = 1
        elif kind == 'route':
            first = tuple(it['start']) if it.get('start') else self.here()
            pts = [first + (f['position/h-sl-ft'],)] + list(it['points'])
            it['_pts'] = pts
            self.leg(pts[0], pts[1])
            f['ap/roll-mode'], f['ap/ground-steer'] = 2, 0
            self.vertical(pts[1][2])
        elif kind == 'land':
            above = self.above_path(it)
            if above > self.entry_limit(course(self.here(), it['aim'])[1]):
                self.go_around(it, above)               # the entry contract is broken: nothing of the landing is set up
                return
            # level towards the runway in the landing configuration until the glide path comes down to the aircraft
            self.leg(it['fix'], it['aim'])
            f['ap/rwy-elev-ft'] = it['elev']
            f['ap/roll-mode'], f['ap/ground-steer'] = 3, 1           # the landing task's own lateral law
            # the height asked for stays the level's if its capture is going on (the aircraft was still coming down to it: a command of the height it has this moment is a step in
            # what the altitude mode asks), else it is the height it has; the spoilers go out as a ramp (it was a step of 0.12 to 0.67: a load factor of 1.31 and the speed 11 kt down)
            h = f['position/h-sl-ft']
            f['ap/alt-cmd-ft'] = lv if (vm == 3 and abs(lv - h) <= LEVEL_BEGIN_FT) else h
            f['ap/pitch-mode'], f['ap/thrust-mode'] = 2, 3
            f['ap/speed-schedule'] = 0
            f['ap/speed-cmd-kcas'] = f['ap/approach-keas']
            f['ap/sp-ext'] = LANDING_SPOILER          # the laws move the spoilers there at their slew rate, from where they are
            f['gear/gear-cmd-norm'] = 1
            it['_on_path'] = False
            f['ap/ld-on'] = 1
        elif kind in ('hold', 'go_around'):
            f['ap/land-mode'] = 0
            f['ap/roll-mode'], f['ap/ground-steer'] = 1, 0
            it['side'] = 1.0
            it['radius'] = it.get('radius') or self.hold_radius()      # fixed once the hold begins: the station draws it
            f['ap/ci-lat'], f['ap/ci-lon'], f['ap/ci-radius-ft'], f['ap/ci-side'] = it['centre'][0], it['centre'][1], it['radius'], it['side']
            f['ap/ci-out-max'], f['ap/ci-lead'], f['ap/ci-on'] = 30.0, 1, 1          # the laws fly the circle: the heading command about the centre
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

    def taxi_leg(self, it):
        """Tell the laws what the taxi leg is: the last one, or ends in a bend of so many degrees (they work out the speed from the way to go)."""
        f, pts = self.f, it['_pts']
        last = self.k == len(pts) - 2
        f['ap/tx-last'] = 1 if last else 0
        if not last:
            f['ap/tx-bend-deg'] = abs(turn(course(pts[self.k], pts[self.k + 1])[0], course(pts[self.k + 1], pts[self.k + 2])[0]))

    def hold_radius(self):
        vg = max(self.f['velocities/vg-fps'], 100.0)
        return vg * vg / (32.174 * math.tan(math.radians(HOLD_BANK)))

    def above_path(self, land):
        """Feet above the glide path to the aiming point (negative under it): the landing task's entry contract is judged on this."""
        h = self.f['position/h-sl-ft'] - land['elev']
        return h - (5.3 + GLIDE_TAN * course(self.here(), land['aim'])[1])

    def entry_limit(self, togo_ft):
        """How far above the path the landing may be begun, ft: what the capture was flown to take over at 10 nmi at this weight, with the margin, by the way to go."""
        w = self.f['inertia/weight-lbs']
        cap10 = float(np.interp(w, [x[0] for x in ENTRY_CAPTURE_FT], [x[1] for x in ENTRY_CAPTURE_FT]))
        return ENTRY_MARGIN * cap10 * max(0.0, min(togo_ft / NM, ENTRY_TOGO_MAX_NM) - ENTRY_TOGO_MIN_NM) / ENTRY_SPAN_NM

    def go_around(self, land, above):
        """The landing task's entry contract is broken (too high to take the path over): the go-around task takes the aircraft: a right-hand
        circle tangent to the final's line at the fix, down to the height the final is begun from, then back to the landing."""
        fix, aim = land['fix'], land['aim']
        fc, d = course(fix, aim)
        r = self.hold_radius()
        centre = (fix[0] + r * math.cos(math.radians(fc + 90.0)) / FT_PER_DEG,
                  fix[1] + r * math.sin(math.radians(fc + 90.0)) / (FT_PER_DEG * math.cos(math.radians(fix[0]))))
        alt = land['elev'] + max(GO_AROUND_MIN_AGL, math.floor((5.3 + GLIDE_TAN * d - LAND_FIX_GAP_FT) / 100.0) * 100.0)
        Manager.go_arounds += 1
        self.note('LANDING NOT COMMITTED: %.0f ft above the glide path; go-around, circling over the fix to %.0f ft' % (above, alt))
        self.plan.insert(self.i, dict(kind='go_around', reason='above the glide path', above=above, centre=centre, radius=r, alt=alt, final=fc,
                                      fix=tuple(fix), side=1.0))
        self.begin()

    def go_around_over(self, it):
        """The go-around's contract with the landing: at the height it came down to, at the fix, on the final's course."""
        f = self.f
        _, d = course(it['fix'], self.here())
        return (-GO_AROUND_ALT_BELOW <= f['position/h-sl-ft'] - it['alt'] <= GO_AROUND_ALT_ABOVE and d <= GO_AROUND_FIX_FT
                and abs(turn(f['ap/ground-track-deg'], it['final'])) <= GO_AROUND_TRACK_DEG)

    def contingencies(self):
        """Leave the plan when the link is lost or the engine stops. Only in the air, and only once each."""
        f = self.f
        kind = self.plan[self.i]['kind']
        if f['engine/failed'] == 1 and self.contingency != 'engine' and kind in ('route', 'land', 'hold', 'go_around') and self.sites and f['ap/rollout'] == 0:
            self.contingency = 'engine'
            self.note('ENGINE FAILED')
            self.plan = self.plan[:self.i + 1] + [dict(kind='engine_out')]
            self.next()
        elif f['ap/link-lost'] == 1 and self.contingency is None and kind in ('route', 'hold', 'go_around') and self.lost_link:
            self.contingency = 'link'
            self.note('LINK LOST: the contingency route')
            self.plan = self.plan[:self.i + 1] + [dict(d) for d in self.lost_link]
            self.next()

    def vertical(self, alt, path=False):
        """Ask the laws for a climb, a descent or a hold towards a height (fdm/laws.py, _mission_vertical: the gate, the mode, the spoilers are theirs); path: the height is the one
        at the end of the leg, and a descent steers its slope with the spoilers to get there. What is read back is the mode, for the status and the notes."""
        f = self.f
        f['ap/vt-on'], f['ap/vt-ft'], f['ap/vt-path'] = 1, alt, 1 if path else 0
        mode = {1: 'climb', 2: 'descent', 3: 'level'}.get(int(round(f['ap/vmode'])))
        if mode and getattr(self, 'vmode', None) != mode:
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
        if kind == 'go_around':
            self.vertical(it['alt'])
            if self.go_around_over(it):
                self.note('go-around over: back on the final')
                self.next()                                     # the landing's contract is judged again as it begins
            return
        if kind == 'hold':
            self.vertical(it['alt'])
            return
        if kind == 'taxi':
            pts = it['_pts']
            if f['ap/tx-leg'] == 1:                         # the laws: the next leg is to be taken
                self.k += 1
                self.leg(pts[self.k], pts[self.k + 1])
                self.taxi_leg(it)
            elif f['ap/tx-done'] == 1:                      # the laws: the item is over
                self.next()
        elif kind == 'takeoff':
            if f['ap/tk-done'] == 1:                            # the laws took it up: schedule, pitch mode, nose wheel (and the gear in the model: in FlightGear its command is the lever's, which is the supervisor's to move)
                f['gear/gear-cmd-norm'] = 0
                self.note('airborne, climb')
                self.next()
        elif kind == 'route':
            # the turn onto the next leg is the aircraft's (fdm/laws.py, ap/turn-*): the manager gives it the next waypoint and moves on when
            # the laws say the turn is done. Past the last waypoint of a route that a landing follows the next point is the aiming point
            pts = it['_pts']
            self.vertical(it.get('alt_override', pts[self.k + 1][2]), path=True)
            last = self.k == len(pts) - 2
            if last and LANDING_LEVEL and self.i + 1 < len(self.plan) and self.plan[self.i + 1]['kind'] == 'land':
                # a landing follows: the level-off of the descent ends in the landing configuration (the laws take the spoilers there as they level), and the gear goes down as the level begins
                f['ap/vt-sp-end'] = LANDING_SPOILER
                if int(round(f['ap/vmode'])) == 3 and int(round(f['ap/v-level-from'])) == 2 and f['gear/gear-cmd-norm'] < 0.5:
                    f['gear/gear-cmd-norm'] = 1
                    self.note('gear down for the landing')
            nxt = pts[self.k + 2] if not last else self.after(self.i)
            self.set_next(nxt)
            if f['ap/turn-done'] > f['ap/turn-ack']:
                f['ap/turn-ack'] = f['ap/turn-done']
                if last:
                    self.next()
                else:
                    self.k += 1
                    it.pop('alt_override', None)
                    self.leg(pts[self.k], pts[self.k + 1])
                    self.note('leg %d' % (self.k + 1))
            elif last and nxt is None and togo < 500.0:
                self.next()
        elif kind == 'land':
            if not it['_on_path']:
                if f['ap/ld-captured'] == 1:                    # the laws took the glide over: the pitch mode, the land mode, the spoilers
                    it['_on_path'] = True
                    self.note('glide path')
            elif f['ap/ld-done'] == 1:
                self.note('rollout over')
                self.next()

    def next(self):
        self.i += 1
        self.begin()
