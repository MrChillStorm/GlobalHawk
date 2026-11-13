"""JSBSim harness for the Global Hawk: load a build, set a flight state, trim, fly, find the modes.

    f = load()                       the model that ships (GlobalHawk/); load('ref') the reference build
    t = trim(f, alt=60000, mach=0.6, weight=15000)
    m = modes(f, t)
    log = fly(f, t, 120)
"""
import math
import os
import subprocess
import sys

import jsbsim
import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
# Frames per second of simulated time. 120 is what FlightGear runs JSBSim at; GH_HZ=240 (or 480, 960) in the environment
# runs every check at that rate instead, to see whether a result is the model's or the step's (fdm/rate_study.py)
HZ = float(os.environ.get('GH_HZ', 120.0))
KT = 1.6878099
ACC = ('accelerations/udot-ft_sec2', 'accelerations/vdot-ft_sec2', 'accelerations/wdot-ft_sec2',
       'accelerations/pdot-rad_sec2', 'accelerations/qdot-rad_sec2', 'accelerations/rdot-rad_sec2')
INTEG = ('simulation/integrator/rate/rotational', 'simulation/integrator/rate/translational',
         'simulation/integrator/position/rotational', 'simulation/integrator/position/translational')
N_TANKS = 6
EMPTY = 11450.0                      # lb without fuel


class Sim(jsbsim.FGFDMExec):
    build = None
    capacity = None


def load(build='ships', rebuild=True, dt=1 / HZ):
    if build == 'ships':
        parent = os.path.join(HERE, '..')
        args = []
    else:
        parent = os.path.join(HERE, 'root-' + build)
        args = [os.path.join(parent, 'GlobalHawk'), '--' + build]
    if rebuild:
        subprocess.run([sys.executable, os.path.join(HERE, 'genghawk.py')] + args, check=True, stdout=subprocess.DEVNULL)
    f = Sim(None)
    f.set_debug_level(0)
    f.set_aircraft_path(os.path.abspath(parent))
    f.set_systems_path('Systems')
    f.set_dt(dt)
    if not f.load_model('GlobalHawk'):
        raise RuntimeError('JSBSim could not load the %s build' % build)
    f.build = build
    f.capacity = [f['propulsion/tank[%d]/contents-lbs' % i] for i in range(N_TANKS)]
    return f


def load_variant(overrides, dt=1 / HZ):
    """The model generated in this process with module constants changed, in a temporary tree: for trying a design
    number (overrides = {'laws.FLARE_SINK': 1.5}) without touching the files. Constants other modules copied by value
    when they were imported are not reached; the ones the generators read at call time are."""
    import importlib
    import shutil
    import tempfile
    import genghawk
    saved = {}
    for key, val in overrides.items():
        mod, name = key.split('.')
        m = importlib.import_module(mod)
        saved[key] = (m, name, getattr(m, name))
        setattr(m, name, val)
    tmp = tempfile.mkdtemp(prefix='ghvariant')
    try:
        genghawk.write(os.path.join(tmp, 'GlobalHawk'))
    finally:
        for m, name, old in saved.values():
            setattr(m, name, old)
    f = Sim(None)
    f.set_debug_level(0)
    f.set_aircraft_path(os.path.abspath(tmp))
    f.set_systems_path('Systems')
    f.set_dt(dt)
    if not f.load_model('GlobalHawk'):
        raise RuntimeError('JSBSim could not load the variant')
    f.build = 'variant'
    f.capacity = [f['propulsion/tank[%d]/contents-lbs' % i] for i in range(N_TANKS)]
    shutil.rmtree(tmp, ignore_errors=True)
    return f


def freeze(f, on=True):
    """Stop (or restart) the integration of the motion, so accelerations can be read at a fixed state."""
    for k, v in zip(INTEG, (0, 0, 0, 0) if on else (1, 3, 1, 4)):
        f[k] = v
    f['fuel/freeze'] = 1 if on else 0


def set_weight(f, weight):
    """Fill every tank to the same fraction for a gross weight."""
    frac = (weight - EMPTY) / sum(f.capacity)
    if not -1e-6 <= frac <= 1 + 1e-6:
        raise ValueError('weight %.0f lb is outside %.0f to %.0f' % (weight, EMPTY, EMPTY + sum(f.capacity)))
    for i, c in enumerate(f.capacity):
        f['propulsion/tank[%d]/contents-lbs' % i] = c * frac


def state(f, cond, alpha, pitch_cmd, throttle, x=None):
    """Put the aircraft at a condition (alt, mach or kcas, weight; gamma in deg, gear 0-1, spoiler 0-1 optional)
    and return the six accelerations. x overrides the motion:
    [u, v, w, p, q, r, phi, theta] in ft/s, rad/s and rad."""
    set_weight(f, cond['weight'])
    f['ic/terrain-elevation-ft'] = cond.get('terrain', 0.0)
    f['ic/h-sl-ft'] = cond['alt']
    f['ic/psi-true-deg'] = cond.get('psi', 0.0)
    f['ic/lat-geod-deg'] = cond.get('lat', 35.0)
    f['ic/long-gc-deg'] = cond.get('lon', 0.0)
    if 'mach' in cond:
        f['ic/mach'] = cond['mach']
    else:
        f['ic/vc-kts'] = cond['kcas']
    f['ic/beta-deg'] = 0
    f['ic/phi-deg'] = 0
    f['ic/alpha-deg'] = alpha
    f['ic/theta-deg'] = alpha + cond.get('gamma', 0.0)
    for k in ('ic/p-rad_sec', 'ic/q-rad_sec', 'ic/r-rad_sec'):
        f[k] = 0
    if x is not None:
        for k, v in zip(('ic/u-fps', 'ic/v-fps', 'ic/w-fps', 'ic/p-rad_sec', 'ic/q-rad_sec', 'ic/r-rad_sec', 'ic/phi-rad', 'ic/theta-rad'), x):
            f[k] = v
    f['ap/engaged'] = 0                                   # the laws off: a state is set on the direct commands
    f['ap/land-mode'] = 0                                 # and any landing over: its rollout latch clears on the next frame
    f['ap/manual'] = 0
    for k in ('elevator', 'aileron', 'rudder'):
        f['fcs/%s-cmd-norm' % k] = 0.0
    f['limits/overstress'] = f['limits/failed'] = 0
    f['ap/ground-steer'] = 0
    f['ap/spoiler-mode'] = 0
    f['fcs/elevator-cmd-norm'] = pitch_cmd
    f['fcs/aileron-cmd-norm'] = 0
    f['fcs/rudder-cmd-norm'] = 0
    f['fcs/throttle-cmd-norm'] = throttle
    f['gear/gear-cmd-norm'] = cond.get('gear', 0.0)
    f['fcs/speedbrake-cmd-norm'] = cond.get('spoiler', 0.0)
    f['ctl/instant'] = 1
    f['engine/running'] = 1
    freeze(f, True)
    f.run_ic()
    f.run()
    return np.array([f[k] for k in ACC])


def trim(f, **cond):
    """Level (or climbing, gamma in deg) trim: angle of attack, ruddervators and throttle for no acceleration.
    With throttle given, the flight path angle is found instead."""
    fixed = cond.pop('throttle', None)
    cond.setdefault('gamma', 0.0)

    def res(v):
        if fixed is None:
            a = state(f, cond, v[0], v[1], v[2])
        else:
            c = dict(cond, gamma=v[2] * 10.0)
            a = state(f, c, v[0], v[1], fixed)
        return [a[0], a[2], a[4] * 50.0]
    best = None
    for start in ([3.0, -0.2, 0.5], [1.5, -0.1, 0.3], [5.0, -0.3, 0.8]):
        s = least_squares(res, start, bounds=([-4, -1, 0 if fixed is None else -3], [11, 1, 1 if fixed is None else 3]), xtol=1e-12, ftol=1e-12)
        if best is None or s.cost < best.cost:
            best = s
        if best.cost < 1e-10:
            break
    v = best.x
    if fixed is not None:
        cond['gamma'] = v[2] * 10.0
    acc = state(f, cond, v[0], v[1], fixed if fixed is not None else v[2])
    t = dict(cond=cond, alpha=float(v[0]), pitch_cmd=float(v[1]), throttle=float(fixed if fixed is not None else v[2]),
             residual=float(np.abs(acc).max()), ok=bool(best.cost < 1e-8))
    for k, p in (('pitch_deg', 'ctl/pitch-deg'), ('thrust', 'engine/thrust-lbf'), ('thrust_max', 'engine/max-thrust-lbf'),
                 ('fuel_flow', 'engine/fuel-flow-pph'), ('mach', 'velocities/mach'), ('kcas', 'velocities/vc-kts'),
                 ('ktas', 'velocities/vtrue-kts'), ('qbar', 'aero/qbar-psf'), ('weight', 'inertia/weight-lbs'),
                 ('lift', 'forces/fwz-aero-lbs'), ('drag', 'forces/fwx-aero-lbs'), ('cg_x_in', 'inertia/cg-x-in')):
        t[k] = float(f[p])
    S = f['metrics/Sw-sqft']
    t['CL'], t['CD'] = t['lift'] / (t['qbar'] * S), t['drag'] / (t['qbar'] * S)
    t['x'] = [f['velocities/u-fps'], f['velocities/v-fps'], f['velocities/w-fps'], 0.0, 0.0, 0.0, 0.0, math.radians(v[0] + cond['gamma'])]
    return t


def modes(f, t):
    """Eigenvalues of the bare airframe about a trim, controls fixed: the longitudinal and the lateral sets."""
    x0 = np.array(t['x'])
    steps = np.array([1.0, 1.0, 1.0, 0.01, 0.01, 0.01, 0.01, 0.01])

    def xdot(x):
        a = state(f, t['cond'], t['alpha'], t['pitch_cmd'], t['throttle'], x=x)
        u, v, w, p, q, r, phi, th = x
        return np.array([a[0], a[1], a[2], a[3], a[4], a[5], p + math.tan(th) * (q * math.sin(phi) + r * math.cos(phi)),
                         q * math.cos(phi) - r * math.sin(phi)])
    A = np.zeros((8, 8))
    for j in range(8):
        d = np.zeros(8)
        d[j] = steps[j]
        A[:, j] = (xdot(x0 + d) - xdot(x0 - d)) / (2 * steps[j])
    lon, lat = [0, 2, 4, 7], [1, 3, 5, 6]
    out = {}
    for name, idx in (('longitudinal', lon), ('lateral', lat)):
        ev = np.linalg.eigvals(A[np.ix_(idx, idx)])
        out[name] = sorted([complex(e) for e in ev if e.imag >= 0], key=lambda e: -abs(e))
    return out


def describe(ev):
    if abs(ev.imag) < 1e-9:
        return 'real %+.4f /s (%s %.1f s)' % (ev.real, 'time constant' if ev.real < 0 else 'doubles in',
                                              -1 / ev.real if ev.real < 0 else math.log(2) / ev.real) if abs(ev.real) > 1e-9 else 'zero'
    wn = abs(ev)
    return 'period %.1f s, damping %.3f' % (2 * math.pi / ev.imag, -ev.real / wn)


def fly(f, t, seconds, hold=True, lag=False):
    """Fly on from a trim. hold: a plain attitude hold (pitch attitude by ruddervators, wings level by ailerons),
    done here in Python at the model's rate, only to show that the model flies. Returns a log."""
    state(f, t['cond'], t['alpha'], t['pitch_cmd'], t['throttle'])
    if lag:
        # with the motion still frozen, let the slow things reach where the trim has them: the gear, the engine's spool
        f['ctl/instant'] = 0
        for _ in range(int(12 * HZ)):
            f.run()
        state(f, t['cond'], t['alpha'], t['pitch_cmd'], t['throttle'])      # the position drifts while frozen: see engage()
    freeze(f, False)
    f['ctl/instant'] = 0 if lag else 1
    th0 = f['attitude/theta-rad']
    n = int(seconds * HZ)
    log = dict(t=[], alt=[], kcas=[], theta=[], phi=[], fuel=[], cg=[], flow=[])
    for i in range(n):
        if hold:
            f['fcs/elevator-cmd-norm'] = t['pitch_cmd'] + 4.0 * (f['attitude/theta-rad'] - th0) + 1.5 * f['velocities/q-rad_sec']
            f['fcs/aileron-cmd-norm'] = -1.0 * f['attitude/phi-rad'] - 0.5 * f['velocities/p-rad_sec']
        if not f.run():
            break
        if i % 12 == 0:
            for k, p in (('t', 'simulation/sim-time-sec'), ('alt', 'position/h-sl-ft'), ('kcas', 'velocities/vc-kts'),
                         ('theta', 'attitude/theta-deg'), ('phi', 'attitude/phi-deg'), ('fuel', 'fuel/total-lbs'),
                         ('cg', 'inertia/cg-x-in'), ('flow', 'engine/fuel-flow-pph')):
                log[k].append(f[p])
    return {k: np.array(v) for k, v in log.items()}


# ---- on the ground. The pilot below is plain Python run at the model's rate, standing in for the flight laws.
def on_ground(f, weight, elevation=2300.0, heading=0.0, lat=35.0, lon=0.0):
    """Stand the aircraft on its wheels at rest and let it settle for 5 s."""
    set_weight(f, weight)
    f['ic/terrain-elevation-ft'] = elevation
    f['ic/h-agl-ft'] = 5.5
    f['ap/engaged'] = 0
    f['ic/psi-true-deg'] = heading
    f['ic/lat-geod-deg'] = lat
    f['ic/long-gc-deg'] = lon
    # at rest: only the speed and the attitude are set. Setting the body velocities or the flow angles to zero
    # here leaves JSBSim's initial condition pointing backwards for the next flight state set in this session
    f['ic/vc-kts'] = 0
    for k in ('ic/p-rad_sec', 'ic/q-rad_sec', 'ic/r-rad_sec', 'ic/phi-deg', 'ic/theta-deg'):
        f[k] = 0
    for k in ('fcs/elevator-cmd-norm', 'fcs/aileron-cmd-norm', 'fcs/rudder-cmd-norm', 'fcs/throttle-cmd-norm', 'fcs/steer-cmd-norm',
              'fcs/speedbrake-cmd-norm'):
        f[k] = 0
    f['gear/gear-cmd-norm'] = 1
    f['fcs/left-brake-cmd-norm'] = f['fcs/right-brake-cmd-norm'] = 1
    f['ctl/instant'] = 0
    f['engine/running'] = 1
    freeze(f, False)
    f.run_ic()
    for _ in range(int(5 * HZ)):
        f.run()


def brakes(f, level):
    f['fcs/left-brake-cmd-norm'] = f['fcs/right-brake-cmd-norm'] = float(np.clip(level, 0, 1))


def snapshot(f, log):
    for k, p in (('t', 'simulation/sim-time-sec'), ('agl', 'position/h-agl-ft'), ('alt', 'position/h-sl-ft'), ('kcas', 'velocities/vc-kts'),
                 ('keas', 'velocities/ve-kts'), ('gs', 'velocities/vg-fps'), ('theta', 'attitude/theta-deg'), ('phi', 'attitude/phi-deg'),
                 ('psi', 'attitude/psi-deg'), ('alpha', 'aero/alpha-deg'), ('vs', 'velocities/h-dot-fps'), ('x', 'position/distance-from-start-mag-mt'),
                 ('wow', 'gear/unit[1]/WOW'), ('nose', 'forces/fbz-gear-lbs'), ('thrust', 'engine/thrust-lbf')):
        log.setdefault(k, []).append(f[p])


def heading_error(f, target):
    return (f['attitude/psi-deg'] - target + 180.0) % 360.0 - 180.0


def takeoff(f, weight=25600.0, elevation=2300.0, rotate_kias=130.0, pitch_deg=6.0, climb_keas=150.0, seconds=150.0):
    """From rest: full throttle, hold the heading with the nose wheel, raise the nose at the rotation speed, then
    hold the climb speed with pitch attitude. Returns a log of arrays."""
    on_ground(f, weight, elevation)
    brakes(f, 0)
    f['fcs/throttle-cmd-norm'] = 1.0
    log, t0, airborne = {}, f['simulation/sim-time-sec'], False
    for i in range(int(seconds * HZ)):
        v = f['velocities/vc-kts']
        e = heading_error(f, 0.0)
        r = f['velocities/r-rad_sec']
        if f['gear/unit[1]/WOW'] or f['gear/unit[2]/WOW']:
            f['fcs/steer-cmd-norm'] = float(np.clip(-0.012 * e - 0.8 * r, -0.1, 0.1))
            f['fcs/rudder-cmd-norm'] = float(np.clip(-0.2 * e - 1.0 * r, -1, 1))
        else:
            airborne = True
            f['fcs/steer-cmd-norm'] = 0
            f['fcs/rudder-cmd-norm'] = float(np.clip(-1.0 * r, -0.3, 0.3))
        if v < rotate_kias and not airborne:
            target = None
        elif not airborne or f['position/h-agl-ft'] < 40:
            target = pitch_deg
        else:
            target = float(np.clip(11.0 + 0.6 * (f['velocities/ve-kts'] - climb_keas), 3.0, 16.0))
            f['gear/gear-cmd-norm'] = 0
        if target is None:
            f['fcs/elevator-cmd-norm'] = 0.0
        else:
            gain = 0.30 if not airborne else 0.08            # on the ground the nose is heavy: the tail has to work hard
            damp = 4.0 if not airborne else 1.5              # and once it comes up it comes up fast (the surfaces have actuators now)
            f['fcs/elevator-cmd-norm'] = float(np.clip(-gain * (target - f['attitude/theta-deg']) + damp * f['velocities/q-rad_sec'], -1, 1))
        f['fcs/aileron-cmd-norm'] = float(np.clip(-1.5 * f['attitude/phi-rad'] - 0.5 * f['velocities/p-rad_sec'], -1, 1))
        if not f.run():
            break
        if i % 12 == 0:
            snapshot(f, log)
    out = {k: np.array(v) for k, v in log.items()}
    out['t'] = out['t'] - t0
    return out


def landing(f, approach, weight=20800.0, elevation=2300.0, start_agl=600.0, flare_agl=110.0, flare_pitch=2.4, decel_g=0.235, seconds=200.0):
    """From a trimmed approach (a trim from trim(), with gear and spoilers) down to a stop: hold the approach's pitch
    attitude, flare to a pitch attitude, idle, then full spoilers, nose down, and brakes held to a deceleration."""
    c = dict(approach['cond'], alt=elevation + start_agl + 5.3)
    state(f, c, approach['alpha'], approach['pitch_cmd'], approach['throttle'])
    f['ic/terrain-elevation-ft'] = elevation
    f.run_ic()
    freeze(f, False)
    f['ctl/instant'] = 0
    brakes(f, 0)
    th0, hdg = approach['alpha'] + c['gamma'], f['attitude/psi-deg']
    sink0 = approach['ktas'] * KT * np.sin(np.radians(-c['gamma'])) * 0.3048       # m/s on the approach
    log, t0, down, brake, td = {}, f['simulation/sim-time-sec'], False, 0.0, None
    for i in range(int(seconds * HZ)):
        agl = f['aero/wheel-height-ft']
        wow = f['gear/unit[1]/WOW'] or f['gear/unit[2]/WOW']
        if wow and not down:
            down, td = True, dict(t=f['simulation/sim-time-sec'] - t0, keas=f['velocities/ve-kts'], sink=-f['velocities/h-dot-fps'] * 0.3048,
                                  theta=f['attitude/theta-deg'], x=f['position/distance-from-start-mag-mt'])
        if not down:
            if agl > flare_agl:
                f['fcs/elevator-cmd-norm'] = float(np.clip(approach['pitch_cmd'] - 0.10 * (th0 - f['attitude/theta-deg']) +
                                                           1.5 * f['velocities/q-rad_sec'], -1, 1))
            else:
                # the flare: the sink rate is led down in proportion to the height left, to 0.6 m/s at the ground;
                # pitch attitude follows the sink error, up to the flare attitude and a little over
                f['fcs/throttle-cmd-norm'] = 0.0
                # the spoilers close as the ground comes up: at the measured touchdown attitude (2.4 deg) the model
                # can't hold its sink with them open, so the real flare is taken to be flown this way. A guess
                f['fcs/speedbrake-cmd-norm'] = c.get('spoiler', 0.0) * float(np.clip(agl / flare_agl, 0, 1))
                sink = -f['velocities/h-dot-fps'] * 0.3048
                want = max(0.6, sink0 * agl / flare_agl)
                target = float(np.clip(th0 + 1.2 * (sink - want), th0, flare_pitch + 2.0))
                f['fcs/elevator-cmd-norm'] = float(np.clip(approach['pitch_cmd'] - 0.25 * (target - f['attitude/theta-deg']) +
                                                           2.0 * f['velocities/q-rad_sec'], -1, 1))
            f['fcs/rudder-cmd-norm'] = float(np.clip(-1.0 * f['velocities/r-rad_sec'], -0.3, 0.3))
        else:
            f['fcs/throttle-cmd-norm'] = 0.0
            f['fcs/speedbrake-cmd-norm'] = 1.0
            f['fcs/elevator-cmd-norm'] = 0.1
            e, r = heading_error(f, hdg), f['velocities/r-rad_sec']
            f['fcs/steer-cmd-norm'] = float(np.clip(-0.012 * e - 0.8 * r, -0.1, 0.1))
            f['fcs/rudder-cmd-norm'] = float(np.clip(-0.2 * e - 1.0 * r, -1, 1))
            # brakes: an integrator on the deceleration error, once the nose wheel is down
            if f['gear/unit[0]/WOW']:
                dec = -f['accelerations/udot-ft_sec2'] / 32.174
                brake = float(np.clip(brake + 0.8 * (decel_g - dec) / HZ, 0, 1))
                brakes(f, brake)
            if f['velocities/vg-fps'] < 1.0:
                brakes(f, 1)
                snapshot(f, log)
                break
        f['fcs/aileron-cmd-norm'] = float(np.clip(-1.5 * f['attitude/phi-rad'] - 0.5 * f['velocities/p-rad_sec'], -1, 1))
        if not f.run():
            break
        if i % 12 == 0:
            snapshot(f, log)
    out = {k: np.array(v) for k, v in log.items()}
    out['t'] = out['t'] - t0
    out['touchdown'] = td
    return out


# ---- the flight laws (Systems/laws.xml)
AP_LOG = (('t', 'simulation/sim-time-sec'), ('alt', 'position/h-sl-ft'), ('kcas', 'velocities/vc-kts'), ('mach', 'velocities/mach'),
          ('theta', 'attitude/theta-deg'), ('phi', 'attitude/phi-deg'), ('psi', 'attitude/psi-deg'), ('beta', 'aero/beta-deg'),
          ('alpha', 'aero/alpha-deg'), ('pitch', 'ctl/pitch-deg'), ('roll', 'ctl/roll-cmd-deg'), ('yaw', 'ctl/yaw-deg'),
          ('throttle', 'ctl/throttle-norm'), ('target', 'ap/speed-target-kcas'), ('weight', 'inertia/weight-lbs'), ('nz', 'accelerations/Nz'),
          ('spoiler', 'ctl/spoiler-norm'), ('xt', 'ap/leg-xt-ft'), ('glide', 'ap/glide-error-ft'), ('wh', 'aero/wheel-height-ft'),
          ('mains', 'ap/on-mains'), ('vg', 'ap/ground-speed-kt'), ('udot', 'accelerations/udot-ft_sec2'), ('hdot', 'velocities/h-dot-fps'),
          ('keas', 'velocities/ve-kts'), ('togo', 'ap/leg-togo-ft'), ('rollout', 'ap/rollout'), ('flare', 'ap/flare'),
          ('lat', 'position/lat-geod-deg'), ('lon', 'position/long-gc-deg'), ('brake', 'fcs/left-brake-cmd-norm'), ('nosew', 'gear/unit[0]/WOW'))


def engage(f, t, x=None, **ap):
    """Start from a trim with everything slow settled, then switch the laws on. ap: properties under ap/ with
    underscores for dashes (pitch_mode=2, alt_cmd_ft=...). x: a disturbed starting motion, as in state()."""
    state(f, t['cond'], t['alpha'], t['pitch_cmd'], t['throttle'])
    f['ap/engaged'] = 0
    f['ctl/instant'] = 0
    for _ in range(int(12 * HZ)):
        f.run()
    # set the state again: with the motion frozen the position still drifts west with the earth's rotation
    # (0.05 deg of longitude in those 12 s). The lags that have settled keep their values through this.
    state(f, t['cond'], t['alpha'], t['pitch_cmd'], t['throttle'], x=x)
    f['ctl/instant'] = 0
    f.run()
    freeze(f, False)
    f['ap/theta-cmd-deg'] = f['attitude/theta-deg']
    f['ap/alt-cmd-ft'] = f['position/h-sl-ft']
    f['ap/heading-cmd-deg'] = f['attitude/psi-deg']
    f['ap/bank-cmd-deg'] = 0.0
    for k in ('pitch-mode', 'roll-mode', 'thrust-mode'):
        f['ap/' + k] = 0
    f['ap/throttle-cmd'] = t['throttle']
    f['ap/speed-schedule'] = 0
    f['ap/speed-cmd-kcas'] = f['velocities/vc-kts']
    f['ap/gain-scale'] = 1.0
    for k, v in ap.items():
        f['ap/' + k.replace('_', '-')] = v
    f['ap/engaged'] = 1
    # The trim left the surfaces' commands in the stick properties (the ruddervator's, at the cruise 0.087 of full
    # travel). The bias latch has them from the frames before this one; a pilot's stick lies at neutral, and left
    # as it was the protected law (dead band 0.05) reads it as a push on the stick (found when a cruise trim,
    # after the moment's Mach growth was changed, needed more than the dead band's worth).
    for k in ('fcs/elevator-cmd-norm', 'fcs/aileron-cmd-norm', 'fcs/rudder-cmd-norm'):
        f[k] = 0.0


def run(f, seconds, every=12, hook=None):
    """Run on, logging. hook(f, time since the start of this run) is called every frame."""
    log = {k: [] for k, _ in AP_LOG}
    t0 = f['simulation/sim-time-sec']
    for i in range(int(seconds * HZ)):
        if hook:
            hook(f, f['simulation/sim-time-sec'] - t0)
        if not f.run():
            break
        if i % every == 0:
            for k, p in AP_LOG:
                log[k].append(f[p])
    out = {k: np.array(v) for k, v in log.items()}
    out['t'] = out['t'] - t0
    return out
