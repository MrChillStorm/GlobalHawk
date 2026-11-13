"""The aircraft's end of the command link (docs: GlobalHawk/gcs/README.md): it takes the station's heartbeat and
commands, checks plans, answers every command, and says what the aircraft is doing. It owns the mission manager.

Python for the JSBSim checks and the simulator server; in FlightGear the same logic runs in Nasal (Phase 9).
Nothing here flies the aircraft: commands change the plan the manager works through.
"""
import json
import math

import missionmgr as MM

NAVS = ('kna', 'knb', 'lna', 'lnb')
KINDS = ('taxi', 'takeoff', 'route', 'land', 'hold')
MAX_LEG_NM = 3000.0
MIN_FINAL_NM = 8.0
FUEL_LOW_LB = 1500.0               # assumed: about an hour and a half at cruise
AOA_NEAR_DEG, AOA_SEC = 0.3, 3.0
OFFER_SEC = 120.0                  # a handover offer lapses after this
FREE = ('control.take', 'control.accept')      # commands a station that does not hold control may send
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


def check_items(items, what):
    """None if a list of plan items can be flown, or the first fault as text."""
    if not isinstance(items, list) or not items:
        return '%s: no items' % what
    for n, it in enumerate(items):
        if not isinstance(it, dict) or it.get('kind') not in KINDS:
            return '%s item %d: unknown kind %s' % (what, n + 1, json.dumps(it.get('kind') if isinstance(it, dict) else it, separators=(',', ':')))
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
    def __init__(self, f):
        self.f = f
        self.plan, self.mgr = None, None
        self.started, self.off, self.saved = False, None, None
        self.answered = {}                       # station -> the last seq answered
        self.beat = None
        self.events = []
        self.down = {'/gcs/down/ack': '', '/gcs/down/status': '', '/gcs/down/plan': ''}
        self.frame = 0
        self.aoa_since = None
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
        return self.started and self.mgr and not self.mgr.done and self.mgr.plan[self.mgr.i]['kind'] in ('route', 'hold')

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
                 contingency=None, alerts=[], hold=None, leg=None, link_lost=bool(f['ap/link-lost']),
                 link_age=round(f['ap/link-age-sec'], 1) if f['ap/link-monitor'] else None, link_timeout=f['ap/link-timeout-sec'])
        if m:
            it = m.plan[min(m.i, len(m.plan) - 1)]
            kind = 'done' if m.done else it['kind']
            s.update(item=m.i, kind=kind, contingency=m.contingency)
            s['doing'], s['next'] = self.describe(m, it, kind)
            if kind == 'hold':
                s['hold'] = dict(lat=it['centre'][0], lon=it['centre'][1], radius_ft=round(it.get('radius') or m.hold_radius()), alt_ft=it['alt'])
            if kind not in ('done', 'hold'):
                s['leg'] = [[f['ap/leg-lat0-deg'], f['ap/leg-lon0-deg']], [f['ap/leg-lat1-deg'], f['ap/leg-lon1-deg']]]
            if kind == 'engine_out':
                s['site'] = it.get('site', {}).get('name')
                s['surplus_ft'] = round(it.get('surplus', 0.0))
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
        near = f['ap/engaged'] == 1 and f['ap/on-mains'] == 0 and f['ap/alpha-limit-deg'] - f['aero/alpha-deg'] < AOA_NEAR_DEG
        t = f['simulation/sim-time-sec']
        self.aoa_since = (self.aoa_since if self.aoa_since is not None else t) if near else None
        if near and t - self.aoa_since >= AOA_SEC:
            add('aoa', 'caution', 'ANGLE OF ATTACK LIMIT', 'The aircraft is holding it')
        if f['ap/manual'] > 0:
            add('manual', 'advisory', 'FLOWN BY HAND: ' + ('PROTECTED' if f['ap/manual'] == 1 else 'DIRECT, NO PROTECTIONS'))
        if self.off in ('goto', 'hold', 'home'):
            add('off-plan', 'advisory', 'OFF THE PLAN: ' + self.off.upper())
        return out

    def describe(self, m, it, kind):
        f = self.f
        rest = [d['kind'] for d in m.plan[m.i + 1:]]
        after = {'taxi': 'taxi', 'takeoff': 'takeoff', 'route': 'route', 'land': 'landing', 'hold': 'hold', 'engine_out': ''}
        nxt = 'then ' + after[rest[0]] if rest else 'end of plan'
        if kind == 'done':
            return 'plan complete', ''
        if f['ap/manual'] > 0:
            return 'FLOWN BY HAND (%s)' % ('protected' if f['ap/manual'] == 1 else 'direct'), 'automatic when commanded, or if the link is lost'
        if kind == 'taxi':
            return ('stopped' if f['ap/ground-speed-kt'] < 0.3 else 'taxi, %.0f kt' % f['ap/ground-speed-kt']), nxt
        if kind == 'takeoff':
            return 'takeoff', nxt
        if kind == 'route':
            n = len(it['_pts']) - 1
            v = getattr(m, 'vmode', 'level')
            head = {'climb': 'climb to', 'descent': 'descend to', 'level': 'level at'}[v]
            return '%s %.0f ft, leg %d of %d, %.0f nmi to go' % (head, f['ap/alt-cmd-ft'], m.k + 1, n, f['ap/leg-togo-ft'] / MM.NM), \
                ('then leg %d' % (m.k + 2) if m.k + 1 < n else nxt)
        if kind == 'hold':
            return 'hold at %.0f ft' % it['alt'], 'until commanded'
        if kind == 'land':
            if f['ap/rollout']:
                return 'rollout', nxt
            return ('approach, glide path' if it.get('_on_path') else 'level to the glide path, %.0f nmi out' % (f['ap/leg-togo-ft'] / MM.NM)), 'then landing'
        if kind == 'engine_out':
            task = it.get('task', 'glide')
            return {'glide': 'ENGINE OUT: glide to %s' % it['site'].get('name', 'the runway'), 'circle': 'ENGINE OUT: circle to lose height',
                    'final': 'ENGINE OUT: final'}[task], {'glide': 'then circle', 'circle': 'then final', 'final': 'then landing'}[task]
        return kind, nxt
