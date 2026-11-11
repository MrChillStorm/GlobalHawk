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
HZ = 120.0
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
    """Put the aircraft at a condition and return the six accelerations. x overrides the motion:
    [u, v, w, p, q, r, phi, theta] in ft/s, rad/s and rad."""
    set_weight(f, cond['weight'])
    f['ic/h-sl-ft'] = cond['alt']
    f['ic/psi-true-deg'] = 0
    f['ic/lat-geod-deg'] = 35.0
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
    f['fcs/elevator-cmd-norm'] = pitch_cmd
    f['fcs/aileron-cmd-norm'] = 0
    f['fcs/rudder-cmd-norm'] = 0
    f['fcs/throttle-cmd-norm'] = throttle
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
