#!/usr/bin/env python3
"""Gusts on the landing: a bench for finding out what the aircraft does, with no limits in it (docs/PLAN.md, "Gusts: find out first").

    python3 fdm/gustbench.py [--gs] [--rule boeing|airbus] [--add KT] [--set laws.NAME=VALUE ...] [--out FILE] [--from FILE] [--trace FILE.csv] CASE [CASE ...]     --from: a file with a case a line (fdm/gustsweep.py writes them);
                                                                                             --trace: the flight's log, 20 times a second, as CSV (the landing task alone, the last case)

A CASE is words, joined by spaces inside one argument (quote it):

    w=20800          weight, lb (default 20,800)
    course=DEG       the runway's true course (the bench's 40; EFHK 22L is 227.5: a westward course at a high latitude parts from the leg's flat-earth course the other way from an eastward one)
    wide=1           the final's wide cross-track integral (ap/final-wide; fdm/laws.py FINAL_*_WIDE)
    off=FT           the aircraft starts this many ft to the right of the final's line (negative: to the left)
    lat=DEG          the field's latitude (default 35; FlightGear's EFHK is at 60.3: the leg's flat-earth geometry and the velocity's course part with latitude)
    rx=F  ra=F       the replay's crosswind and headwind multiplied by these (rx=-1 mirrors it: a wind from the other side; 0.5 halves it)
    replay=NAME      the wind a recorded flight met on its final (fdm/gustreplay.py, fdm/out/gust/replay_NAME.json): the headwind, the wind to the left and the updraught against the height over the runway,
                     the turbulence as it was (a frozen field); replaces hw= and xw= (not the gusts or lo=)
    ff=1             the final's wind feed-forward (ap/final-ff)
    imb=X            tank 1's fuel raised and tank 0's lowered by this share (0.1: ten per cent): a rolling moment the roll law holds the wings level against (phase 7b's M11; flight 34's drift)
    shr=K            the steady wind grows with height over the runway, linearly from the surface wind at 0 ft to K times it at 500 ft (SHH= another height) and above: the FlightGear scenario's boundary-layer
                     shear (a wind of 36 kt at the surface and 85 kt at 500 ft is shr=2.36)
    hw=10  xw=15     steady wind: a headwind of 10 kt (negative: a tailwind), a crosswind of 15 kt from the right (negative: from the left); brought up over 30 s
    g=AXIS:KT@H[:RISE[:HOLD]]
                     a discrete 1-cosine gust, in the runway's axes: AXIS a (along: positive is more headwind), x (across: positive from the right),
                     v (vertical: positive an updraft); KT its size; H the height over the runway (ft) it begins at, the first time the aircraft is under it;
                     RISE s (default 2) up, HOLD s (default 2) at its size, RISE s down. As many g= as you like (a sequence: several heights).
    lo=W20           a low-level turbulence of the bench's own: MIL-F-8785C's low-altitude Dryden (sigma_w = 0.1 W20, the scales and the sigmas with the height over the runway), W20 the wind at 20 ft in kt
                     (15 is light, 30 moderate, 45 severe). JSBSim's own (tu=) does not do this in this harness: it is the same at every height and for every W20 (docs/PLAN.md, "Gusts: find out first")
    tua=SEV          JSBSim's own turbulence of this severity ABOVE 1,500 ft over the runway only, off below (the bench's lo= Dryden is the turbulence below): FlightGear's GUSTS 0.85 is severity 5, strong aloft (a
                     downdraught of 30 to 35 kt at 2,100 ft in the recorded flights) and 0.1 times the wind at 20 ft near the ground
    tu=W20:SEV       JSBSim's own MIL-F-8785C turbulence (W20 does nothing here; the severity sets one strength at every height)
    seed=N           the turbulence's random sequence (the bench's own for lo=, JSBSim's simulation/randomseed for tu=)
    add=KT           the approach speed raised by this many kt (ap/approach-add-kt; the landing's speed in gusty wind)
    gsmini=1         the ground-speed minimum (ap/gsmini-on; the A320 family's: the approach speed is raised by how far the live headwind is over the tower's, ap/tower-hw-kt = the case's hw, at least 10 kt)
    rule=boeing|airbus|airbusfull   the addition an airliner's rule gives for this case's weather, as a pilot would work it from the reported wind: boeing = half the steady headwind component plus the gust increment
                     (twice the along sigma of the turbulence at 30 ft), 5 to 20 kt; airbus = a third of the steady headwind component, 5 to 15 kt (docs/PLAN.md, "Protocol addendum: the airliners' rules")
    auto=1           the aircraft picks the approach speed's addition itself (ap/approach-add-auto; fdm/laws.py GS_AUTO_*) in place of add=
    gs=1             the gust system on (ap/gust-sys: fdm/laws.py GS_*); gs=0, the default, the aircraft as it was
    mgr=1            the landing flown by the mission manager (the stabilised-approach gate, the missed approach) from 5 nmi out, instead of the landing task alone
    sec=260          the flight's length

It prints one line a case and, with --out, appends the case's record (JSON, one line) to the file. What it measures is the aircraft's, not a verdict: the landing task's own contracts
(fdm/landlimit.py: final.gate, flare.touchdown, rollout.line, control.margin) are listed as the ones that would break, to see where, not to pass or fail anything.
"""
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H             # noqa: E402
import landlimit as LL          # noqa: E402
import phase11_checks as P      # noqa: E402
import phase7b_checks as B      # noqa: E402

FPS = 1.68781                    # ft/s in a knot
NM = B.NM
COURSE = B.COURSE
ELEV = float(os.environ.get('GB_ELEV', LL.ELEV))          # GB_ELEV=171: the field at FlightGear's EFHK height (JSBSim's own turbulence counts the height above sea level)
LL.ELEV = ELEV
EXTRA = (('alim', 'ap/alpha-limit-deg'), ('over', 'limits/overstress'), ('flap', 'ap/ld-captured'))
EXTRA2 = (('gson', 'ap/gs-on'), ('gsthr', 'ap/gs-throttle'), ('gsfl', 'ap/gs-flare-extra-deg'), ('thrust', 'engine/thrust-lbf'), ('gsalert', 'ap/gust-alert'), ('addu', 'ap/approach-add-used'), ('gsig', 'ap/gust-sigma-kt'), ('gxw', 'ap/gs-xw-kt'), ('gnow', 'ap/gs-add-now'), ('ggm', 'ap/gs-gsmini-add'), ('ghw', 'ap/gs-hw-live-kt'), ('pt', 'atmosphere/p-turb-rad_sec'), ('qt', 'atmosphere/q-turb-rad_sec'), ('rt', 'atmosphere/r-turb-rad_sec'))


def _unit(deg):
    return np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg))])


class Weather:
    """A steady wind (brought up over `ramp` seconds) and discrete gusts, in the runway's axes, written into JSBSim's wind every frame. JSBSim's initial conditions set the wind back to
    nothing, so a weather is installed after the aircraft is engaged: it wraps the model's run(). Positive: `a` a headwind, `x` a wind from the right of the runway's course, `v` an updraft."""

    def __init__(self, hw=0.0, xw=0.0, gusts=(), tu=None, seed=None, ramp=30.0, lo=None, shr=1.0, shh=500.0, tua=None, replay=None, rx=1.0, ra=1.0):
        self.hw, self.xw, self.ramp = hw, xw, ramp
        self.rp = None
        self.rx, self.ra = rx, ra
        if replay:
            import json as _json
            d = _json.load(open(os.path.join(HERE, 'out', 'gust', 'replay_%s.json' % replay)))
            self.rp = tuple(np.array(d[k]) for k in ('agl', 'a', 'x', 'v'))
        self.tua = tua
        self.shr, self.shh = shr, shh
        self.lo = lo
        self.rng = np.random.default_rng(seed or 0)
        self.dry = np.zeros(5)                              # the Dryden filters' states: u, v1, v2, w1, w2
        self.gusts = [dict(g, t0=None) for g in gusts]
        self.tu, self.seed = tu, seed
        self.t0 = None
        self.now = dict(a=0.0, x=0.0, v=0.0)               # what the gusts add now, kt
        self.u, self.r = _unit(COURSE), _unit(COURSE + 90.0)

    @staticmethod
    def shape(g, s):
        """the 1-cosine gust's size (0 to 1) s seconds after it began"""
        rise, hold = g['rise'], g['hold']
        if s <= 0 or s >= 2 * rise + hold:
            return 0.0
        if s < rise:
            return 0.5 * (1 - math.cos(math.pi * s / rise))
        if s <= rise + hold:
            return 1.0
        return 0.5 * (1 + math.cos(math.pi * (s - rise - hold) / rise))

    def dryden(self, agl, vt):
        """one frame of MIL-F-8785C's low-altitude Dryden turbulence (below 1,000 ft: sigma_w = 0.1 W20, sigma_u = sigma_v = sigma_w / (0.177 + 0.000823 h)^0.4, L_w = h,
        L_u = L_v = h / (0.177 + 0.000823 h)^1.2; height held between 10 and 1,000 ft); returns (along, across, vertical) in kt. The filters: u a first-order lag, v and w the second-order
        (1 + sqrt(3) tau s) / (1 + tau s)^2 as sqrt(3) x1 - (sqrt(3) - 1) x2, each x a lag of the one before; white noise of the strength that gives the filter's output unit variance, times sigma."""
        dt = 1.0 / H.HZ
        h = min(1000.0, max(10.0, agl))
        sw = 0.1 * self.lo * 1.68781                          # ft/s: W20 is in kt (a first version took it as ft/s and divided by 1.688 again at the end: the turbulence was 59 % of its label, 2026-11-16)
        su = sw / (0.177 + 0.000823 * h) ** 0.4
        lu = h / (0.177 + 0.000823 * h) ** 1.2
        lw = h
        n = self.rng.standard_normal(3) / math.sqrt(dt)
        v = max(vt, 100.0)
        tu, tw = max(lu / v, 0.15), max(lw / v, 0.15)
        d = self.dry
        d[0] += dt / tu * (math.sqrt(2 * tu) * n[0] - d[0])
        for i, (tau, k) in ((1, (tu, 1)), (3, (tw, 2))):
            d[i] += dt / tau * (math.sqrt(tau) * n[k] - d[i])
            d[i + 1] += dt / tau * (d[i] - d[i + 1])
        r3 = math.sqrt(3.0)
        along = su * d[0]
        across = su * (r3 * d[1] - (r3 - 1) * d[2])
        vert = sw * (r3 * d[3] - (r3 - 1) * d[4])
        return along / 1.68781, across / 1.68781, vert / 1.68781

    def apply(self, f, t):
        agl = f['position/h-sl-ft'] - ELEV - 5.3
        k = min(1.0, max(0.0, t / self.ramp))
        add = dict(a=0.0, x=0.0, v=0.0)
        if self.lo:
            add['a'], add['x'], add['v'] = self.dryden(agl, f['velocities/vt-fps'])
        for g in self.gusts:
            if g['t0'] is None and agl <= g['h']:
                g['t0'] = t
            if g['t0'] is not None:
                add[g['axis']] += g['kt'] * self.shape(g, t - g['t0'])
        self.now = add
        if self.tua:
            f['atmosphere/turb-type'] = 3 if agl > 1500.0 else 0                       # JSBSim's severity turbulence only aloft
        prof = 1.0 + (self.shr - 1.0) * min(1.0, max(0.0, agl / self.shh))          # the steady wind's growth with height (shr 1: none)
        a, x, v = k * prof * self.hw + add['a'], k * prof * self.xw + add['x'], add['v']
        if self.rp is not None:
            h = min(max(agl, 1.0), float(self.rp[0][-1]))
            a, x, v = a + k * self.ra * float(np.interp(h, self.rp[0], self.rp[1])), x + k * self.rx * float(np.interp(h, self.rp[0], self.rp[2])), v + k * float(np.interp(h, self.rp[0], self.rp[3]))
        n, e = -(a * self.u + x * self.r) * FPS
        f['atmosphere/wind-north-fps'] = n
        f['atmosphere/wind-east-fps'] = e
        f['atmosphere/wind-down-fps'] = -v * FPS

    def start(self, f):
        P.calm(f)
        if self.seed:
            f['simulation/randomseed'] = self.seed
        if self.tu:
            P.turbulence(f, True, self.tu[0], self.tu[1])
        if self.tua:
            P.turbulence(f, True, 15.0, self.tua)

    def install(self, f):
        """wrap f.run(): the weather is put on frame by frame from the first call; uninstall() takes it off"""
        self.start(f)
        orig = f.run

        def run():
            now = f['simulation/sim-time-sec']
            if self.t0 is None:
                self.t0 = now
            self.apply(f, now - self.t0)
            return orig()
        f.run = run
        self._f = f
        return f

    def uninstall(self):
        try:
            del self._f.run
        except AttributeError:
            pass
        P.calm(self._f)


GS_ALL = 0                       # --gs: the gust system on in every case
ADD_ALL = 0.0                    # --add KT: the approach speed raised by this many kt in every case
AUTO_ALL = 0                     # --auto: the aircraft picks the addition itself in every case
RULE_ALL = None                  # --rule boeing|airbus: the airliner rule's addition in every case
SET_ALL = {}                     # --set laws.NAME=VALUE: a number of the laws changed for every case (harness.load_variant), to try a design number without touching the file


def rule_add(c, kind):
    """the addition of an airliner's rule for the case's weather (from the reported wind: the steady wind's headwind component and the turbulence's gust increment), kt"""
    hw = max(0.0, c['hw'])
    w20 = c['lo'] or (c['tu'][0] if c['tu'] else 0.0)      # the wind at 20 ft: lo= (the bench's Dryden) or tu= (JSBSim's turbulence; version 2's sets: until 2026-11-17 this read lo= only, so the Boeing arm had no gust increment)
    gust = 2.0 * 0.1 * w20 / (0.177 + 0.000823 * 30.0) ** 0.4          # twice the along sigma at 30 ft (MIL-F-8785C): the gust over the mean
    if kind == 'boeing':
        return min(20.0, max(5.0, 0.5 * hw + gust))
    if kind in ('airbus', 'airbusfull'):
        return min(15.0, max(5.0, hw / 3.0))
    raise SystemExit('gustbench: the rule is boeing or airbus, not "%s"' % kind)


def parse(text):
    """a case's words -> a dict"""
    global COURSE
    COURSE = B.COURSE
    for word in text.split():
        if word.startswith('course='):
            COURSE = float(word.partition('=')[2])
    c = dict(w=20800.0, hw=0.0, xw=0.0, gusts=[], tu=None, lo=None, seed=None, mgr=False, gs=GS_ALL, add=ADD_ALL, auto=AUTO_ALL, gsmini=0, shr=1.0, shh=500.0, tua=None, imb=0.0, wide=0, off=0.0, lat=35.0, replay=None, ff=0, ri=0, aim=0, rx=1.0, ra=1.0, sec=260.0, name=text.strip())
    for word in text.split():
        k, _, v = word.partition('=')
        if k == 'w':
            c['w'] = float(v)
        elif k in ('hw', 'xw'):
            c[k] = float(v)
        elif k == 'g':
            axis, _, rest = v.partition(':')
            kt, _, rest = rest.partition('@')
            parts = rest.split(':')
            c['gusts'].append(dict(axis=axis, kt=float(kt), h=float(parts[0]), rise=float(parts[1]) if len(parts) > 1 else 2.0, hold=float(parts[2]) if len(parts) > 2 else 2.0))
        elif k == 'tu':
            w20, _, sev = v.partition(':')
            c['tu'] = (float(w20), float(sev or 3))
        elif k == 'lo':
            c['lo'] = float(v)
        elif k == 'seed':
            c['seed'] = int(v)
        elif k == 'mgr':
            c['mgr'] = bool(int(v))
        elif k == 'gs':
            c['gs'] = int(v)
        elif k == 'add':
            c['add'] = float(v)
        elif k == 'auto':
            c['auto'] = int(v)
        elif k == 'rule':
            c['rule'] = v
        elif k == 'gsmini':
            c['gsmini'] = int(v)
        elif k == 'tua':
            c['tua'] = float(v)
        elif k == 'imb':
            c['imb'] = float(v)
        elif k == 'wide':
            c['wide'] = int(v)
        elif k == 'off':
            c['off'] = float(v)
        elif k == 'lat':
            c['lat'] = float(v)
        elif k == 'course':
            pass
        elif k == 'replay':
            c['replay'] = v
        elif k == 'rx':
            c['rx'] = float(v)
        elif k == 'ra':
            c['ra'] = float(v)
        elif k == 'ff':
            c['ff'] = int(v)
        elif k == 'ri':
            c['ri'] = int(v)
        elif k == 'aim':
            c['aim'] = int(v)
        elif k == 'shr':
            c['shr'] = float(v)
        elif k == 'shh':
            c['shh'] = float(v)
        elif k == 'sec':
            c['sec'] = float(v)
        else:
            raise SystemExit('gustbench: what is "%s"?' % word)
    if c.get('rule') or RULE_ALL:
        c['rule'] = c.get('rule') or RULE_ALL
        c['add'] = rule_add(c, c['rule'])
        if c['rule'] == 'airbusfull':
            c['gsmini'] = 1
    for g in c['gusts']:
        if g['axis'] not in ('a', 'x', 'v'):
            raise SystemExit('gustbench: the gust axis is a, x or v, not "%s"' % g['axis'])
    return c


def weather_of(c):
    return Weather(c['hw'], c['xw'], c['gusts'], c['tu'], c['seed'], lo=c['lo'], shr=c['shr'], shh=c['shh'], tua=c['tua'], replay=c['replay'], rx=c['rx'], ra=c['ra'])


def run_task(c):
    """the landing task alone, from 5 nmi out on the glide (landlimit.py's setup), the weather on"""
    weight = c['w']
    f = H.load_variant(SET_ALL)
    P.calm(f)
    fld = B.MM.Field(c['lat'], -117.0, ELEV)
    u = B.unit(COURSE)
    aim, far = fld.ll(0, 0), fld.ll(*(-8 * NM * u))
    d0 = 5 * NM
    start = fld.ll(*(-d0 * u + c['off'] * B.unit(COURSE + 90.0)))
    keas = math.sqrt(weight / (0.645 * 540 * 0.5 * 0.0023769)) / H.KT
    t = H.trim(f, alt=ELEV + 5.3 + d0 * 0.07782, kcas=keas, weight=weight, gamma=-4.45, gear=1.0, spoiler=2 / 3, lat=start[0], lon=start[1], psi=COURSE, terrain=ELEV)
    H.engage(f, t, pitch_mode=1, roll_mode=3, ground_steer=1, land_mode=1, rwy_elev_ft=ELEV, leg_lat0_deg=far[0], leg_lon0_deg=far[1], leg_lat1_deg=aim[0], leg_lon1_deg=aim[1])
    if c['imb']:
        f['propulsion/tank[1]/contents-lbs'] = f['propulsion/tank[1]/contents-lbs'] * (1 + c['imb'])
        f['propulsion/tank[0]/contents-lbs'] = f['propulsion/tank[0]/contents-lbs'] * (1 - c['imb'])
    wx = weather_of(c)
    wx.install(f)
    f['ap/gust-sys'] = c['gs']
    f['ap/approach-add-kt'] = c['add']
    f['ap/approach-add-auto'] = c['auto']
    f['ap/gsmini-on'] = c['gsmini']
    f['ap/tower-hw-kt'] = max(0.0, c['hw'])
    f['ap/final-wide'] = c['wide']
    f['ap/final-ff'] = c['ff']
    f['ap/final-ri'] = c['ri']
    f['ap/final-aim'] = c['aim']
    log = {k: [] for k, _ in H.AP_LOG + EXTRA + EXTRA2}
    log.update(ga=[], gx=[], gv=[])
    ext = dict(ail=0.0, rud=0.0)
    t0 = f['simulation/sim-time-sec']
    for i in range(int(c['sec'] * H.HZ)):
        if not f.run():
            break
        ext['ail'] = max(ext['ail'], abs(f['ctl/roll-cmd-deg']) / LL.TRAVEL_DEG)
        ext['rud'] = max(ext['rud'], abs(f['ctl/yaw-deg']) / LL.TRAVEL_DEG)
        if i % 6 == 0:
            for k, p in H.AP_LOG + EXTRA + EXTRA2:
                log[k].append(f[p])
            log['ga'].append(wx.now['a'])
            log['gx'].append(wx.now['x'])
            log['gv'].append(wx.now['v'])
        if f['ap/on-mains'] > 0 and f['ap/rollout'] == 1 and f['ap/ground-speed-kt'] < 16 and i > 0:
            break
    wx.uninstall()
    out = {k: np.array(v) for k, v in log.items()}
    out['t'] = out['t'] - t0
    out['_ext'] = ext
    return out


def measure(log, c):
    """what happened: the numbers, with the landing task's contracts listed beside them (not as a verdict)"""
    agl = log['alt'] - ELEV - 5.3
    down = np.nonzero(log['mains'] > 0)[0]
    r = dict(name=c['name'], finite=bool(np.all(np.isfinite(log['alt']))), down=bool(len(down)))
    r['peak_kt'] = dict(a=round(float(np.abs(log['ga']).max()), 1), x=round(float(np.abs(log['gx']).max()), 1), v=round(float(np.abs(log['gv']).max()), 1))
    r['overstress'] = float(log['over'].max())
    if not len(down):
        r['broke'] = ['never down']
        i = len(log['t']) - 1
    else:
        i = int(down[0])
        j = LL.judge(log)
        r['broke'] = j['broke']
        r['detail'] = j['detail']
        r['sink_ms'] = round(-float(log['hdot'][max(0, i - 1)]) * 0.3048, 2)
        r['pitch_td'] = round(float(log['theta'][i]), 1)
        r['bank_td'] = round(float(abs(log['phi'][i])), 1)
        r['xt_td_ft'] = round(float(log['xt'][i]), 1)
        r['nose_off_deg'] = round(float(abs((log['psi'][i] - COURSE + 540) % 360 - 180)), 1)
        r['past_ft'] = round(float(-log['togo'][i]), 0)
        r['keas_td'] = round(float(log['keas'][i]), 1)
        r['speed_err_td'] = round(float(log['kcas'][i] - log['target'][i]), 1)
        r['rollout_xt_ft'] = round(float(np.abs(log['xt'][i:]).max()), 1)
        r['end_kt'] = round(float(log['vg'][-1]), 1)
        r['roll_ft'] = round(float(log['togo'][i] - log['togo'][-1]), 0)
        r['total_ft'] = round(float(-log['togo'][-1]), 0)             # the aiming point to the end of the rollout (16 kt)
        r['bank_ground'] = round(float(np.abs(log['phi'][i:]).max()), 1)
        fl = np.nonzero(log['flare'] > 0)[0]
        r['flare_agl_ft'] = round(float(agl[fl[0]]), 0) if len(fl) else None
    low = (agl < 500) & (np.arange(len(agl)) <= i)
    if low.any():
        r['below500'] = dict(xt_ft=round(float(np.abs(log['xt'][low]).max()), 1), glide_ft=(round(float(log['glide'][low].min()), 1), round(float(log['glide'][low].max()), 1)),
                             speed_err_kt=(round(float((log['kcas'] - log['target'])[low].min()), 1), round(float((log['kcas'] - log['target'])[low].max()), 1)),
                             bank=round(float(np.abs(log['phi'][low]).max()), 1), alpha_margin=round(float((log['alim'] - log['alpha'])[low].min()), 2),
                             nz=(round(float(log['nz'][low].min()), 2), round(float(log['nz'][low].max()), 2)), sideslip=round(float(np.abs(log['beta'][low]).max()), 1),
                             spoiler=(round(float(log['spoiler'][low].min()), 2), round(float(log['spoiler'][low].max()), 2)), throttle=(round(float(log['throttle'][low].min()), 2), round(float(log['throttle'][low].max()), 2)),
                             wheel_h_min=round(float(log['wh'][low].min()), 1))
    for h in (1000, 500, 150):
        k = np.nonzero((agl <= h) & (np.arange(len(agl)) <= i))[0]
        if len(k):
            r['at%d' % h] = dict(xt=round(float(log['xt'][k[0]]), 0), glide=round(float(log['glide'][k[0]]), 0), speed_err=round(float(log['kcas'][k[0]] - log['target'][k[0]]), 1))
    r['gust_alert_s'] = round(float(np.sum(log['gsalert'][: i + 1] > 0)) * float(np.median(np.diff(log['t']))), 1) if len(log['t']) > 1 else 0.0
    k1000 = np.nonzero(agl <= 1000)[0]
    if len(k1000):
        r['at1000_picker'] = dict(sigma_kt=round(float(log['gsig'][k1000[0]]), 2), w20e=round(10 * float(log['gsig'][k1000[0]]), 1), cross_kt=round(float(log['gxw'][k1000[0]]), 1), add_kt=round(float(log['addu'][k1000[0]]), 1))
    r['add_kt'] = round(float(c['add']), 1)
    r['gsmini_add_max'] = round(float(np.max(log['ggm'])), 1)
    r['controls'] = dict(aileron=round(log['_ext']['ail'], 2), ruddervators=round(log['_ext']['rud'], 2))
    return r


def run_mgr(c):
    """the same approach flown by the manager (the stabilised-approach gate and the missed approach): B.gate_case with the weather installed"""
    wx = weather_of(c)
    def setup(f):
        wx.install(f)
        f['ap/gust-sys'] = c['gs']
        f['ap/approach-add-kt'] = c['add']
        f['ap/approach-add-auto'] = c['auto']
        f['ap/gsmini-on'] = c['gsmini']
        f['ap/tower-hw-kt'] = max(0.0, c['hw'])
    res = B.gate_case(c['w'], 0.0, False, seconds=c['sec'], setup=setup, seed=None, elev=ELEV)
    r = dict(name=c['name'], mgr=True, missed=[dict(h=round(m['h']), why=m['why'].split(';')[0], low=round(m['low']), down=m['down'], gear_up=m['gear_up']) for m in res['misses']],
             abandoned=res['abandoned'], touchdown=None)
    if res['td']:
        r['touchdown'] = dict(past=round(res['td']['past']), sink=round(res['td']['sink'], 2), xt=round(res['td']['xt'], 1), after_misses=res['td']['n_before'])
    r['events'] = [e[1] for e in res['events']][-8:]
    return r


def line(r):
    if r.get('mgr'):
        td = r['touchdown']
        return '%-60s missed %d (%s)%s  %s' % (r['name'], len(r['missed']), ', '.join('%s at %d ft' % (m['why'].replace('MISSED APPROACH: ', ''), m['h']) for m in r['missed']) or '-', ' ABANDONED' if r['abandoned'] else '',
                                              'down %d ft past, %.2f m/s, %.1f ft off' % (td['past'], td['sink'], td['xt']) if td else 'not down')
    if not r['down']:
        return '%-60s NEVER DOWN%s' % (r['name'], '' if r['finite'] else ' (not finite)')
    b = r['below500']
    return '%-60s sink %.2f m/s, %.1f ft off, nose %.1f, bank %.1f/%.1f, %+.0f ft past, speed %+.1f kt; <500ft: xt %.0f, glide %.0f..%.0f, speed %.1f..%.1f, alpha margin %.2f, nz %.2f..%.2f; roll %.0f ft; rud %.2f ail %.2f; %s' % (
        r['name'], r['sink_ms'], r['xt_td_ft'], r['nose_off_deg'], r['bank_td'], r['bank_ground'], r['past_ft'], r['speed_err_td'], b['xt_ft'], b['glide_ft'][0], b['glide_ft'][1],
        b['speed_err_kt'][0], b['speed_err_kt'][1], b['alpha_margin'], b['nz'][0], b['nz'][1], r['rollout_xt_ft'], r['controls']['ruddervators'], r['controls']['aileron'],
        ','.join(r['broke']) or 'holds all four') + ('; GUST ALERT %.0f s' % r['gust_alert_s'] if r.get('gust_alert_s') else '')


def write_trace(log, path):
    keys = [k for k in log if not k.startswith('_')]
    with open(path, 'w') as fh:
        fh.write(','.join(keys) + '\n')
        for i in range(len(log['t'])):
            fh.write(','.join('%.4g' % log[k][i] for k in keys) + '\n')


def fly(text, trace=None):
    c = parse(text)
    t = time.time()
    if c['mgr']:
        r = run_mgr(c)
    else:
        log = run_task(c)
        if trace:
            write_trace(log, trace)
        r = measure(log, c)
    r['seconds'] = round(time.time() - t, 1)
    return r


def main():
    args = sys.argv[1:]
    out, trace = None, None
    global GS_ALL
    global ADD_ALL, AUTO_ALL, RULE_ALL
    while args and args[0] in ('--out', '--from', '--trace', '--gs', '--set', '--add', '--auto', '--rule'):
        if args[0] == '--rule':
            RULE_ALL = args[1]
            args = args[2:]
            continue
        if args[0] == '--auto':
            AUTO_ALL = 1
            args = args[1:]
            continue
        if args[0] == '--add':
            ADD_ALL = float(args[1])
            args = args[2:]
            continue
        if args[0] == '--gs':
            GS_ALL = 1
            args = args[1:]
            continue
        if args[0] == '--set':
            k, _, v = args[1].partition('=')
            SET_ALL[k] = float(v)
            args = args[2:]
            continue
        if args[0] == '--out':
            out = args[1]
        elif args[0] == '--trace':
            trace = args[1]
        else:
            args = args + [x.strip() for x in open(args[1]) if x.strip() and not x.startswith('#')]
        args = args[2:]
    for text in args:
        r = fly(text, trace)
        print(line(r), flush=True)
        if out:
            with open(out, 'a') as fh:
                fh.write(json.dumps(r) + '\n')


if __name__ == '__main__':
    main()
