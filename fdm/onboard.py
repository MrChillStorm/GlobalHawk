"""The aircraft's end of the command link (docs: GlobalHawk/gcs/README.md): it takes the station's heartbeat and
commands, checks plans, answers every command, and says what the aircraft is doing. It owns the mission manager.

Python for the JSBSim checks and the simulator server; in FlightGear the same logic runs in Nasal (Phase 9).
Nothing here flies the aircraft: commands change the plan the manager works through.
"""
import json
import math
import os

import airportdata as AD
import missionmgr as MM

NAVS = ('kna', 'knb', 'lna', 'lnb')
KINDS = ('taxi', 'takeoff', 'route', 'land', 'hold')
MAX_LEG_NM = 3000.0
MIN_FINAL_NM = 8.0
REPOSITION_MAX_KT = 2.0            # the aircraft moves to a new place on the ground only when it stands (docs/GCS.md, `reposition`)
MAX_DESCENT_DEG = 6.0               # a route leg goes down no more steeply than this on average: the glide path is 4.45 deg, the flown descent 2.5 to 3.5 (docs/PLAN.md, "The aircraft refuses what it cannot fly")
MAX_HOLDS = 16                     # holds a taxi item may carry (docs/PLAN.md, "Hold points and clearances")
HOLD_KINDS = ('runway', 'takeoff', 'junction', 'point')
HOLD_ID_MAX, HOLD_NAME_MAX = 24, 80
MIN_GRADIENT_LEG_NM = 2.0          # shorter legs are not judged on their slope: the turns at their ends take most of them
FPS_PER_KT = 1.6878099


def crosswind_limit_kt(weight):
    """The steady crosswind the landing holds its contracts in at a weight, kt (fdm/landlimit.py writes data/landing_limits.json): linear between the weights flown, held at the
    ends; None when none was measured. The station's plan check reads the same table (js/flightmath.js crosswindLimitKt)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'landing_limits.json')
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    xs, ys = d['weight_lb'], d['crosswind_kt']
    if any(y is None for y in ys):
        return None
    if weight <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if weight <= xs[i]:
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (weight - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[-1]


FUEL_LOW_LB = 1500.0               # assumed: about an hour and a half at cruise
AOA_NEAR_DEG, AOA_SEC = 0.15, 3.0              # the near-limit advisory: raised with the angle of attack within 0.15 deg of its limit for 3 s (the approach is flown 0.2 to 0.3 deg under it at light weights: the advisory is for closer than that) ...
AOA_NEAR_OFF_DEG, AOA_CLEAR_SEC = 0.25, 2.0      # ... and cleared when it has been more than 0.25 deg under it for 2 s (hysteresis: with one threshold the caution came and went every few seconds)
AOA_EXCEED_SEC, AOA_HOLD_SEC = 0.5, 3.0          # the exceeded caution: the angle over its limit for 0.5 s; once raised it stands at least 3 s (a 2 s excursion at the glide capture used to raise nothing)
OFFER_SEC = 120.0                  # a handover offer lapses after this
FREE = ('control.take', 'control.accept', 'airport')      # commands a station that does not hold control may send ('airport' only reads the scenery)
LINK_TIMEOUT_MIN, LINK_TIMEOUT_MAX = 10.0, 300.0   # s, assumed: under 10 a satellite delay and a missed heartbeat could trigger it


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _point(p, n, what):
    if not (isinstance(p, (list, tuple)) and len(p) == n and all(_num(v) for v in p)):
        return '%s: a point needs %d numbers' % (what, n)
    if not -90.0 <= p[0] <= 90.0:
        return '%s: latitude %g is not on the earth' % (what, p[0])
    if not -180.0 <= p[1] <= 180.0:
        return '%s: longitude %g is not on the earth' % (what, p[1])
    if n == 3 and not 0.0 <= p[2] <= MM.MAX_ALT:
        return '%s: height %g ft is outside 0 to %.0f ft' % (what, p[2], MM.MAX_ALT)
    return None


def _text(x, n):
    return isinstance(x, str) and 1 <= len(x) <= n


def holds_fault(holds, npts, w, ids):
    """None if a taxi item's holds are good, or the first fault as text. ids: the ids met so far in this list of items (an id is used once)."""
    if not isinstance(holds, list) or len(holds) > MAX_HOLDS:
        return '%s (taxi): holds is not a list of at most %d' % (w, MAX_HOLDS)
    used = set()
    for n, h in enumerate(holds):
        x = '%s (taxi) hold %d' % (w, n + 1)
        if not isinstance(h, dict):
            return '%s: not a hold' % x
        i = h.get('i')
        if not _num(i) or i != math.floor(i) or not 0 <= i < npts:
            return '%s: i is not a whole number from 0 to %d' % (x, npts - 1)
        if i in used:
            return '%s: point %d is a hold already' % (x, i + 1)
        used.add(i)
        if not _text(h.get('id'), HOLD_ID_MAX):
            return '%s: id is not text of 1 to %d characters' % (x, HOLD_ID_MAX)
        if h['id'] in ids:
            return '%s: id %s is used twice in the plan' % (x, h['id'])
        ids.add(h['id'])
        if not _text(h.get('name'), HOLD_NAME_MAX):
            return '%s: name is not text of 1 to %d characters' % (x, HOLD_NAME_MAX)
        if h.get('kind') not in HOLD_KINDS:
            return '%s: kind %s is not runway, takeoff, junction or point' % (x, json.dumps(h.get('kind'), separators=(',', ':')))
        if h['kind'] == 'takeoff' and i != npts - 1:
            return '%s: a takeoff hold belongs at the last point (point %d)' % (x, npts)
    return None


def check_items(items, what):
    """None if a list of plan items can be flown, or the first fault as text."""
    if not isinstance(items, list) or not items:
        return '%s: no items' % what
    for n, it in enumerate(items):
        if not isinstance(it, dict) or it.get('kind') not in KINDS:
            return '%s item %d: unknown kind %s' % (what, n + 1, json.dumps(it.get('kind') if isinstance(it, dict) else it, separators=(',', ':')))
    ids = set()
    for n, it in enumerate(items):
        w = '%s item %d' % (what, n + 1)
        kind = it['kind']
        if kind in ('taxi', 'route'):
            pts = it.get('points')
            if not isinstance(pts, list) or not pts:
                return '%s (%s): no points' % (w, kind)
            for m, p in enumerate(pts):
                bad = _point(p, 3 if kind == 'route' else 2, '%s (%s) point %d' % (w, kind, m + 1))
                if bad:
                    return bad
            for a, b in zip(pts[:-1], pts[1:]):
                if MM.course(a, b)[1] / MM.NM > MAX_LEG_NM:
                    return '%s (%s): a leg longer than %.0f nmi' % (w, kind, MAX_LEG_NM)
            if kind == 'taxi' and it.get('holds') is not None:
                bad = holds_fault(it['holds'], len(pts), w, ids)
                if bad:
                    return bad
            if kind == 'route':
                for m, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
                    ft, drop = MM.course(a, b)[1], a[2] - b[2]
                    if drop > 0 and ft / MM.NM >= MIN_GRADIENT_LEG_NM and math.degrees(math.atan2(drop, ft)) > MAX_DESCENT_DEG:
                        return '%s (route): point %d to point %d goes down %.0f ft in %.1f nmi, %.1f deg: the aircraft does not come down more steeply than %g deg' % (
                            w, m + 1, m + 2, drop, ft / MM.NM, math.degrees(math.atan2(drop, ft)), MAX_DESCENT_DEG)
        elif kind == 'takeoff':
            bad = _point(it.get('start'), 2, w + ' (takeoff) start') or _point(it.get('end'), 2, w + ' (takeoff) end')
            if bad:
                return bad
            if n + 1 >= len(items) or items[n + 1]['kind'] != 'route':
                return '%s: a takeoff must be followed by a route' % w
        elif kind == 'land':
            bad = _point(it.get('fix'), 2, w + ' (land) fix') or _point(it.get('aim'), 2, w + ' (land) aim')
            if bad:
                return bad
            d = MM.course(it['fix'], it['aim'])[1] / MM.NM
            if d < MIN_FINAL_NM:
                return '%s (land): the fix is %.1f nmi from the aiming point, less than %.0f' % (w, d, MIN_FINAL_NM)
        elif kind == 'hold':
            bad = _point(list(it.get('centre', ())) + [it.get('alt')], 3, w + ' (hold)')
            if bad:
                return bad
    return None


def check_plan(plan):
    """None if the plan is good, or the first fault as text."""
    if not isinstance(plan, dict):
        return 'not a plan'
    fld = plan.get('field')
    if not (isinstance(fld, dict) and _num(fld.get('elev_ft')) and _point([fld.get('lat'), fld.get('lon')], 2, 'field') is None):
        return 'field: needs lat, lon and elev_ft'
    bad = check_items(plan.get('items'), 'plan')
    if bad:
        return bad
    if plan.get('lost_link') is not None:
        bad = check_items(plan['lost_link'], 'lost-link route')
        if bad:
            return bad
        if plan['lost_link'][0]['kind'] != 'route' or plan['lost_link'][-1]['kind'] != 'land':
            return 'lost-link route: it must begin with a route and end in a land'
    for n, s in enumerate(plan.get('sites') or []):
        if not (isinstance(s, dict) and _point(s.get('aim'), 2, 'site %d' % (n + 1)) is None and _num(s.get('course')) and _num(s.get('elev_ft'))):
            return 'site %d: needs aim, course and elev_ft' % (n + 1)
    return None


def items_for_manager(items, elev):
    """Plan items as the manager takes them: tuples, and the field's elevation where a takeoff or landing needs one."""
    out = []
    for it in items:
        d = dict(it)
        for k in ('start', 'end', 'fix', 'aim', 'centre'):
            if k in d:
                d[k] = tuple(d[k])
        if 'points' in d:
            d['points'] = [tuple(p) for p in d['points']]
        if d['kind'] in ('takeoff', 'land'):
            d.setdefault('elev', d.pop('elev_ft', elev))
        out.append(d)
    return out


class Onboard:
    def __init__(self, f, scenery=None):
        self.f = f
        self.scenery = scenery                  # where the ground networks are (airportdata.scenery_dirs() when None)
        self.plan, self.mgr = None, None
        self.started, self.off, self.saved = False, None, None
        self.answered = {}                       # station -> the last seq answered
        self.beat = None
        self.events = []
        self.down = {'/gcs/down/ack': '', '/gcs/down/status': '', '/gcs/down/plan': '', '/gcs/down/airport': ''}
        self.frame = 0
        self.aoa = dict(over_since=None, over_on=None, near_since=None, near_on=False, clear_since=None)      # the angle-of-attack alerts' state
        self.stations = {}                       # name -> when last heard (sim seconds)
        self.holder, self.offer = None, None     # who has control; a handover offered: (to, when)
        self.status()

    # ---- uplink
    def uplink(self, path, value):
        t = self.f['simulation/sim-time-sec']
        if path == '/gcs/up/heartbeat':
            if value == self.beat:
                return
            self.beat = value
            name = value.rsplit(':', 1)[0] if isinstance(value, str) and ':' in value else None
            if name is None:
                self.alive()                     # a bare counter: keeps the link alive for whoever holds control, takes none
            else:
                self.heard(name)
        elif path == '/gcs/up/stick':
            try:
                m = json.loads(value)
                name = str(m['station'])
                v = [float(m[k]) for k in ('p', 'r', 'y', 't', 's')]
            except (ValueError, KeyError, TypeError):
                return
            self.heard(name)
            if name == self.holder and self.f['ap/manual'] > 0:
                f = self.f
                clip = lambda x, lo: max(lo, min(1.0, x))
                f['fcs/elevator-cmd-norm'], f['fcs/aileron-cmd-norm'], f['fcs/rudder-cmd-norm'] = clip(v[0], -1.0), clip(v[1], -1.0), clip(v[2], -1.0)
                f['fcs/throttle-cmd-norm'], f['fcs/speedbrake-cmd-norm'] = clip(v[3], 0.0), clip(v[4], 0.0)
        elif path == '/gcs/up/cmd':
            try:
                cmd = json.loads(value)
                seq, name, station = int(cmd['seq']), str(cmd['name']), str(cmd.get('station', ''))
            except (ValueError, KeyError, TypeError):
                return                           # not a command: nothing to answer
            if seq <= self.answered.get(station, float('-inf')):
                return                           # this or a later one was answered already: an old command is never done again
            self.answered[station] = seq
            self.heard(station)
            self.sender = station
            if station != self.holder and name not in FREE:
                reason = '%s has control' % self.holder
            else:
                try:
                    reason = getattr(self, 'cmd_' + name.replace('.', '_'), self.cmd_unknown)(cmd.get('args') or {})
                except (KeyError, TypeError, ValueError) as e:
                    reason = 'bad arguments (%s)' % e
            self.down['/gcs/down/ack'] = json.dumps(dict(seq=seq, station=station, name=name, status='rejected' if reason else 'accepted',
                                                         reason=reason or '', t=round(self.f['simulation/sim-time-sec'], 2)))
            self.note('%s %s%s' % (name, 'REJECTED: ' + reason if reason else 'accepted', ''))
            self.status()

    def alive(self):
        """An uplink from the station that holds control: the link is alive."""
        self.f['ap/link-last-sec'] = self.f['simulation/sim-time-sec']
        self.f['ap/link-monitor'] = 1

    def heard(self, name):
        """A station was heard. The first one gets control; the holder's uplinks keep the link alive."""
        self.stations[name] = self.f['simulation/sim-time-sec']
        if self.holder is None:
            self.holder = name
            self.note('%s has control' % name)
        if name == self.holder:
            self.alive()

    def note(self, text):
        self.events.append((self.f['simulation/sim-time-sec'], text))

    # ---- commands: each returns None when done, or why not
    def cmd_unknown(self, a):
        return 'unknown command'

    def airborne(self):
        return self.started and self.mgr and not self.mgr.done and self.mgr.plan[self.mgr.i]['kind'] in ('route', 'hold', 'go_around')

    def cmd_plan(self, a):
        bad = check_plan(a)
        if bad:
            return bad
        if self.started and not (self.airborne() and a['items'][0]['kind'] == 'route'):
            return 'a plan is being flown: a new one must begin with a route and be sent while enroute'
        self.plan = a
        elev = a['field']['elev_ft']
        sites = [dict(name=s.get('name', '?'), aim=tuple(s['aim']), course=s['course'], elev=s['elev_ft']) for s in a.get('sites') or []]
        lost = items_for_manager(a['lost_link'], elev) if a.get('lost_link') else None
        if self.started:
            m = self.mgr
            m.plan = m.plan[:m.i + 1] + items_for_manager(a['items'], elev)
            m.lost_link, m.sites = lost, sites
            self.off = self.saved = None
            m.next()
        else:
            self._new = (items_for_manager(a['items'], elev), lost, sites)
        self.down['/gcs/down/plan'] = json.dumps(a)
        return None

    def cmd_start(self, a):
        if self.plan is None:
            return 'no plan'
        if self.started:
            return 'the plan has already begun'
        if not self.f['engine/running']:
            return 'the engine is not running'
        items, lost, sites = self._new
        f = self.f
        f['ap/speed-schedule'] = 1
        f['ap/theta-cmd-deg'] = f['attitude/theta-deg']
        f['fcs/left-brake-cmd-norm'] = f['fcs/right-brake-cmd-norm'] = 0
        self.mgr = MM.Manager(f, items, lost_link=lost, sites=sites)
        f['ap/engaged'] = 1
        self.started = True
        return None

    def cmd_clear(self, a):
        """Clear the hold the aircraft is waiting at (docs/PLAN.md, "Hold points and clearances"): by id, so that a clearance meant for one is never taken for another."""
        m = self.mgr if self.started else None
        if m is None:
            return 'the plan has not begun'
        if m.waiting is None:
            return 'the aircraft is not waiting at a hold'
        w = m.waiting
        id_ = a.get('id')
        if not isinstance(id_, str) or not id_:
            return 'clear: a hold is cleared by its id'
        if id_ != w['id']:
            return 'the aircraft is waiting at %s (%s), not %s' % (w['id'], w['name'], id_)
        m.clear()
        return None

    def cmd_airport(self, a):
        """The ground network and runway ends of an airport, from the scenery, on /gcs/down/airport (airportdata.py)."""
        try:
            msg = AD.load(a.get('icao') if isinstance(a, dict) else None, self.scenery)
        except ValueError as e:
            return str(e)
        self.down['/gcs/down/airport'] = AD.dumps(msg)
        return None

    def cmd_reposition(self, a):
        """Put the aircraft, stopped on the ground, at a place with a heading (a parking spot the station chose). Not once the plan has begun, not in the air, not while it moves."""
        bad = _point([a.get('lat'), a.get('lon')], 2, 'reposition')
        if bad:
            return bad
        if not _num(a.get('heading')):
            return 'reposition: the heading is not a number'
        if self.started:
            return 'the plan has begun'
        f = self.f
        if f['ap/on-mains'] == 0:
            return 'only on the ground'
        if f['ap/ground-speed-kt'] > REPOSITION_MAX_KT:
            return 'only when the aircraft stands (%.0f kt)' % f['ap/ground-speed-kt']
        import harness as H                     # the JSBSim stand-in for FlightGear's reposition
        H.on_ground(f, f['inertia/weight-lbs'], elevation=f['position/terrain-elevation-asl-ft'], heading=float(a['heading']) % 360.0, lat=float(a['lat']), lon=float(a['lon']))
        f['limits/reset'] = 1                   # the structure's latches, as FlightGear's start-over leaves them (see the Nasal end): cleared
        f.run()
        f['limits/reset'] = 0
        return None

    def remember(self):
        """Before leaving the plan: where to come back to. The leg being flown, from its own start, and the rest."""
        m = self.mgr
        it = m.plan[m.i]
        if self.saved is None and it['kind'] == 'route' and not self.off:
            pts = it['_pts']
            rest = dict(kind='route', start=pts[m.k][:2], points=list(it['points'][m.k:]))
            self.saved = [rest] + [dict(d) for d in m.plan[m.i + 1:]]

    def leave(self, items, what):
        """Leave the plan for other items."""
        m = self.mgr
        self.remember()
        m.plan = m.plan[:m.i + 1] + items
        self.off = what
        m.next()

    def cmd_goto(self, a):
        if not self.airborne():
            return 'only while enroute'
        bad = _point([a['lat'], a['lon'], a['alt_ft']], 3, 'goto')
        if bad:
            return bad
        p = (float(a['lat']), float(a['lon']), float(a['alt_ft']))
        self.leave([dict(kind='route', points=[p]), dict(kind='hold', centre=p[:2], alt=p[2])], 'goto')
        return None

    def cmd_hold(self, a):
        if not self.airborne():
            return 'only while enroute'
        f = self.f
        m = self.mgr
        # the circle starts where the aircraft is: its centre one radius to the right
        r = m.hold_radius()
        c = math.radians(f['attitude/psi-deg'] + 90.0)
        here = m.here()
        centre = (here[0] + r * math.cos(c) / MM.FT_PER_DEG, here[1] + r * math.sin(c) / (MM.FT_PER_DEG * math.cos(math.radians(here[0]))))
        self.leave([dict(kind='hold', centre=centre, alt=float(f['ap/alt-cmd-ft']), radius=r)], 'hold')
        return None

    def cmd_altitude(self, a):
        if not self.airborne():
            return 'only while enroute'
        alt = a['alt_ft']
        if not (_num(alt) and 0.0 <= alt <= MM.MAX_ALT):
            return 'height %s ft is outside 0 to %.0f ft' % (alt, MM.MAX_ALT)
        it = self.mgr.plan[self.mgr.i]
        if it['kind'] == 'hold':
            it['alt'] = float(alt)
        else:
            it['alt_override'] = float(alt)
        return None

    def cmd_resume(self, a):
        m = self.mgr
        if not self.started or self.saved is None:
            return 'not off the plan'
        if m.contingency == 'engine':
            return 'the engine has failed'
        if m.contingency == 'link':
            m.contingency = None
            self.f['ap/link-monitor'] = 0        # clears the lost-link latch; the next heartbeat starts the watch again
            self.f['ap/link-lost'] = 0           # and at once: a heartbeat may switch the watch back on before the latch has run
        m.plan = m.plan[:m.i + 1] + self.saved
        self.saved, self.off = None, None
        m.next()
        return None

    def cmd_home(self, a):
        if not self.airborne():
            return 'only while enroute'
        if not self.mgr.lost_link:
            return 'the plan has no contingency route'
        self.leave([dict(d) for d in self.mgr.lost_link], 'home')
        return None

    def cmd_control_offer(self, a):
        to = str(a['to'])
        t = self.f['simulation/sim-time-sec']
        if to == self.holder:
            return 'that is this station'
        if to not in self.stations or t - self.stations[to] > 10.0:
            return 'station %s is not being heard' % to
        self.offer = (to, t)
        return None

    def cmd_control_cancel(self, a):
        if self.offer is None:
            return 'no handover is offered'
        self.offer = None
        return None

    def cmd_control_accept(self, a):
        if self.offer is None or self.offer[0] != self.sender:
            return 'control has not been offered to %s' % self.sender
        old, self.holder, self.offer = self.holder, self.sender, None
        self.alive()
        self.note('control passed from %s to %s' % (old, self.holder))
        return None

    def cmd_control_take(self, a):
        if self.holder == self.sender:
            return 'this station already has control'
        if self.holder is not None and not self.f['ap/link-lost']:
            return '%s has control and is being heard' % self.holder
        old, self.holder, self.offer = self.holder, self.sender, None
        self.alive()
        self.note('%s took control%s' % (self.holder, ' (%s was lost)' % old if old else ''))
        return None

    def cmd_manual(self, a):
        mode = a['mode']
        if mode not in (0, 1, 2):
            return 'mode must be 0 (automatic), 1 (protected) or 2 (direct)'
        f = self.f
        if mode == 0:
            if f['ap/manual'] == 0:
                return 'already automatic'
            self.automatic()
            return None
        if not self.airborne():
            return 'only while enroute'
        if f['ap/manual'] == 0:
            # the levers start where the laws have them; the manager holds here, off the plan, until told otherwise
            f['fcs/throttle-cmd-norm'], f['fcs/speedbrake-cmd-norm'] = f['ctl/throttle-norm'], f['ctl/spoiler-norm']
            for k in ('elevator', 'aileron', 'rudder'):
                f['fcs/%s-cmd-norm' % k] = 0.0
        f['ap/land-mode'] = 0
        f['ap/manual'] = mode
        self.remember()
        self.off = 'manual'
        return None

    def automatic(self):
        """Back from flying by hand: the laws take over and the aircraft holds where it is."""
        f = self.f
        f['ap/manual'] = 0
        for k in ('elevator', 'aileron', 'rudder'):
            f['fcs/%s-cmd-norm' % k] = 0.0
        self.off = None
        f['ap/alt-cmd-ft'] = round(f['position/h-sl-ft'] / 100.0) * 100.0
        if self.airborne():
            self.cmd_hold({})

    def cmd_linktimeout(self, a):
        sec = a.get('sec')
        if not _num(sec):
            return 'the time-out needs a number of seconds'
        if not LINK_TIMEOUT_MIN <= sec <= LINK_TIMEOUT_MAX:
            return 'the time-out is %g to %g s' % (LINK_TIMEOUT_MIN, LINK_TIMEOUT_MAX)
        self.f['ap/link-timeout-sec'] = float(sec)
        return None

    def cmd_nav(self, a):
        if a.get('name') not in NAVS:
            return 'unknown navigator'
        self.f['nav/%s-on' % a['name']] = 1 if a.get('on') else 0
        return None

    # ---- every frame
    def step(self):
        self.frame += 1
        if self.started:
            m = self.mgr
            if self.f['ap/manual'] > 0 and self.f['ap/link-lost']:
                self.note('link lost while flown by hand: automatic')
                self.automatic()
            if self.offer and self.f['simulation/sim-time-sec'] - self.offer[1] > OFFER_SEC:
                self.offer = None
            before = m.contingency
            if before is None and (self.f['ap/link-lost'] or self.f['engine/failed']) and not m.done:
                self.remember()                  # the manager is about to leave the plan by itself
            m.step()
            if m.contingency != before and m.contingency:
                # the manager left the plan by itself: remember the way back, as for a command
                self.off = m.contingency
        if self.frame % 60 == 0:
            self.status()

    def status(self):
        f = self.f
        m = self.mgr if self.started else None
        s = dict(t=round(f['simulation/sim-time-sec'], 1), plan=self.plan.get('id') if self.plan else None, started=self.started,
                 item=None, kind=None, doing='no plan' if self.plan is None else 'waiting for start', next='', off_plan=self.off,
                 contingency=None, alerts=[], hold=None, wait=None, leg=None, link_lost=bool(f['ap/link-lost']),
                 link_age=round(f['ap/link-age-sec'], 1) if f['ap/link-monitor'] else None, link_timeout=f['ap/link-timeout-sec'])
        if m:
            it = m.plan[min(m.i, len(m.plan) - 1)]
            kind = 'done' if m.done else it['kind']
            s.update(item=m.i, kind=kind, contingency=m.contingency)
            s['doing'], s['next'] = self.describe(m, it, kind)
            if kind in ('hold', 'go_around'):
                s['hold'] = dict(lat=it['centre'][0], lon=it['centre'][1], radius_ft=round(it.get('radius') or m.hold_radius()), alt_ft=it['alt'])
            if kind not in ('done', 'hold', 'go_around'):
                s['leg'] = [[f['ap/leg-lat0-deg'], f['ap/leg-lon0-deg']], [f['ap/leg-lat1-deg'], f['ap/leg-lon1-deg']]]
            if kind == 'engine_out':
                s['site'] = it.get('site', {}).get('name')
                s['surplus_ft'] = round(it.get('surplus', 0.0))
        if m and getattr(m, 'waiting', None):
            w = m.waiting
            s['wait'] = dict(id=w['id'], name=w['name'], kind=w['kind'], since=round(w['since'], 1))
        s['alerts'] = self.alerts(m)
        now = f['simulation/sim-time-sec']
        s['control'] = dict(holder=self.holder, offer_to=self.offer[0] if self.offer else None,
                            stations=[dict(name=n, age=round(now - t, 1)) for n, t in sorted(self.stations.items())])
        s['manual'] = int(f['ap/manual'])
        s['target'] = dict(alt_ft=round(f['ap/alt-cmd-ft']), kcas=round(f['ap/speed-target-kcas'], 1))
        s['events'] = [[round(t, 1), e] for t, e in ((m.events if m else []) + self.events)]
        s['events'] = sorted(s['events'])[-6:]
        self.down['/gcs/down/status'] = json.dumps(s)
        return s

    def aoa_step(self, margin, active, t):
        """The angle-of-attack alerts for one look: (exceeded, near). margin: the limit less the angle, deg. Exceeded: the angle over the limit for AOA_EXCEED_SEC, then standing at least AOA_HOLD_SEC and
        until it is back under. Near: within AOA_NEAR_DEG of the limit (or over) for AOA_SEC, then standing until more than AOA_NEAR_OFF_DEG under it for AOA_CLEAR_SEC (the margin hovers at the
        threshold on final: with one threshold and no hold the caution came and went every few seconds while the indicator read a steady 0.3 deg under the limit)."""
        a = self.aoa
        if not active:
            a.update(over_since=None, over_on=None, near_since=None, near_on=False, clear_since=None)
            return False, False
        if margin < 0:
            a['over_since'] = t if a['over_since'] is None else a['over_since']
            if a['over_on'] is None and t - a['over_since'] >= AOA_EXCEED_SEC:
                a['over_on'] = t
        else:
            a['over_since'] = None
            if a['over_on'] is not None and t - a['over_on'] >= AOA_HOLD_SEC:
                a['over_on'] = None
        if not a['near_on']:
            if margin < AOA_NEAR_DEG:
                a['near_since'] = t if a['near_since'] is None else a['near_since']
                if t - a['near_since'] >= AOA_SEC:
                    a['near_on'], a['clear_since'] = True, None
            else:
                a['near_since'] = None
        else:
            if margin > AOA_NEAR_OFF_DEG:
                a['clear_since'] = t if a['clear_since'] is None else a['clear_since']
                if t - a['clear_since'] >= AOA_CLEAR_SEC:
                    a.update(near_on=False, near_since=None, clear_since=None)
            else:
                a['clear_since'] = None
        return a['over_on'] is not None, a['near_on']

    def alerts(self, m):
        """What the crew must know, as the aircraft sees it. Only what the model computes."""
        f = self.f
        out = []

        def add(i, level, text, action=''):
            out.append(dict(id=i, level=level, text=text, action=action))
        if f['engine/failed']:
            it = m.plan[min(m.i, len(m.plan) - 1)] if m else {}
            site = it.get('site', {}).get('name') if it.get('kind') == 'engine_out' else None
            add('engine', 'warning', 'ENGINE FAILED', ('Gliding to %s by itself. Clear the runway. ' % site if site else '') + 'No restart is modelled')
        if m and m.alert:
            add('no-site', 'warning', 'NO RUNWAY IN REACH', 'Gliding towards the nearest')
        if m and not m.done and m.plan[min(m.i, len(m.plan) - 1)]['kind'] == 'go_around':
            ga = m.plan[min(m.i, len(m.plan) - 1)]
            add('go-around', 'warning', 'LANDING NOT COMMITTED', 'The aircraft was %.0f ft %s at the landing fix. It is circling over the fix to lose height and will land when it can. Check the plan' % (ga['above'], ga['reason']))
        if m and not m.done:
            cur = m.plan[min(m.i, len(m.plan) - 1)]
            if cur['kind'] == 'route' and cur.get('ga') and not cur['ga'].get('abandoned'):
                add('missed-approach', 'warning', 'MISSED APPROACH', 'The approach was not stable (%s). The aircraft is climbing out and flying a circuit for another approach, attempt %d. Check the weather and the aircraft' % (cur['ga']['why'], cur['ga']['attempt']))
            elif (cur['kind'] == 'route' and cur.get('ga')) or (cur['kind'] == 'hold' and cur.get('abandoned')):
                why = cur['ga']['why'] if cur['kind'] == 'route' else cur['abandoned']
                add('landing-abandoned', 'warning', 'LANDING ABANDONED', 'The approach was not stable again (%s). The aircraft is climbing out to hold over the landing fix and will not try again by itself. Decide: another approach, another runway or the engine-out site' % why)
        if m and not m.done and f['ap/engaged'] == 1 and f['ap/land-mode'] == 1 and f['ap/on-mains'] == 0:
            it = m.plan[min(m.i, len(m.plan) - 1)]
            lim = crosswind_limit_kt(f['inertia/weight-lbs'])
            if it['kind'] == 'land' and lim is not None:
                c = math.radians(MM.course(it['fix'], it['aim'])[0])
                xw = abs(-f['ap/wind-north-filt-fps'] * math.sin(c) + f['ap/wind-east-filt-fps'] * math.cos(c)) / FPS_PER_KT
                if xw > lim:
                    add('crosswind', 'caution', 'CROSSWIND OVER LIMIT', 'The wind across the final is %.0f kt; the landing holds its limits to %.0f kt at %.0f lb. Go around or divert if it is not to be accepted' % (xw, lim, f['inertia/weight-lbs']))
        if m and getattr(m, 'waiting', None):
            add('hold', 'advisory', 'WAITING FOR CLEARANCE: ' + m.waiting['name'], 'Check that the way is clear, then clear it')
        if f['limits/overstress']:
            add('structure', 'warning', 'STRUCTURAL LIMIT PASSED', 'Land')
        if f['ap/link-lost']:
            add('link', 'caution', 'LINK WAS LOST', 'The aircraft left its plan when the link was lost. Resume when ready')
        if f['nav/miscompare']:
            add('nav-disagree', 'caution', 'NAVIGATORS DISAGREE', 'The aircraft is using the one that matches its turn rate. Land')
        if f['nav/count'] < 2 and f['simulation/sim-time-sec'] > 1.0:
            add('nav-one', 'caution', 'ONE NAVIGATOR LEFT' if f['nav/count'] == 1 else 'NO NAVIGATOR', 'No cross-check of attitude is left. Switch one on')
        if f['fuel/total-lbs'] < FUEL_LOW_LB and f['simulation/sim-time-sec'] > 1.0:
            add('fuel-low', 'caution', 'FUEL LOW', 'Return home')
        exceeded, near = self.aoa_step(f['ap/alpha-limit-deg'] - f['aero/alpha-deg'], f['ap/engaged'] == 1 and f['ap/on-mains'] == 0, f['simulation/sim-time-sec'])
        if exceeded:
            add('aoa', 'caution', 'ANGLE OF ATTACK LIMIT EXCEEDED', 'The aircraft is bringing it back')
        elif near:
            add('aoa-near', 'advisory', 'NEAR THE ANGLE OF ATTACK LIMIT', 'The aircraft is holding it under the limit')
        if f['ap/gust-alert'] == 1:
            add('gust', 'caution', 'GUSTS OR WIND SHEAR ON THE FINAL', 'The gust system is correcting' if f['ap/gust-sys'] == 1 else 'The gust system is off: the landing may be hard')
        if f['ap/manual'] > 0:
            add('manual', 'advisory', 'FLOWN BY HAND: ' + ('PROTECTED' if f['ap/manual'] == 1 else 'DIRECT, NO PROTECTIONS'))
        if self.off in ('goto', 'hold', 'home'):
            add('off-plan', 'advisory', 'OFF THE PLAN: ' + self.off.upper())
        return out

    def describe(self, m, it, kind):
        f = self.f
        rest = [d['kind'] for d in m.plan[m.i + 1:]]
        after = {'taxi': 'taxi', 'takeoff': 'takeoff', 'route': 'route', 'land': 'landing', 'hold': 'hold', 'go_around': 'go-around', 'engine_out': ''}
        nxt = 'then ' + after[rest[0]] if rest else 'end of plan'
        if kind == 'done':
            return 'plan complete', ''
        if f['ap/manual'] > 0:
            return 'FLOWN BY HAND (%s)' % ('protected' if f['ap/manual'] == 1 else 'direct'), 'automatic when commanded, or if the link is lost'
        if kind == 'taxi':
            if getattr(m, 'waiting', None):
                return 'HOLD: waiting for clearance: %s' % m.waiting['name'], 'on the station\'s clearance'
            return ('stopped' if f['ap/ground-speed-kt'] < 0.3 else 'taxi, %.0f kt' % f['ap/ground-speed-kt']), nxt
        if kind == 'takeoff':
            return 'takeoff', nxt
        if kind == 'route':
            n = len(it['_pts']) - 1
            v = getattr(m, 'vmode', 'level')
            head = {'climb': 'climb to', 'descent': 'descend to', 'level': 'level at'}[v]
            return '%s%s %.0f ft, leg %d of %d, %.0f nmi to go' % (('LANDING ABANDONED: ' if it['ga'].get('abandoned') else 'MISSED APPROACH: ') if it.get('ga') else '', head, f['ap/alt-cmd-ft'], m.k + 1, n, f['ap/leg-togo-ft'] / MM.NM), \
                ('then leg %d' % (m.k + 2) if m.k + 1 < n else nxt)
        if kind == 'hold':
            if it.get('abandoned'):
                return 'LANDING ABANDONED: hold at %.0f ft' % it['alt'], 'until commanded'
            return 'hold at %.0f ft' % it['alt'], 'until commanded'
        if kind == 'go_around':
            return 'GO-AROUND: circling over the fix to %.0f ft, %.0f ft above the glide path when it began' % (it['alt'], it['above']), 'then landing'
        if kind == 'land':
            if f['ap/rollout']:
                return 'rollout', nxt
            return ('approach, glide path' if it.get('_on_path') else 'level to the glide path, %.0f nmi out' % (f['ap/leg-togo-ft'] / MM.NM)), 'then landing'
        if kind == 'engine_out':
            task = it.get('task', 'glide')
            return {'glide': 'ENGINE OUT: glide to %s' % it['site'].get('name', 'the runway'), 'circle': 'ENGINE OUT: circle to lose height',
                    'final': 'ENGINE OUT: final'}[task], {'glide': 'then circle', 'circle': 'then final', 'final': 'then landing'}[task]
        return kind, nxt
