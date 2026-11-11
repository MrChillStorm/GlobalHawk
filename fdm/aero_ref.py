#!/usr/bin/env python3
"""The reference aerodynamic model: the whole aircraft in AeroSandbox.

No wind-tunnel or CFD data of the Global Hawk is public, so this takes their place as the thing our own strip model
(fdm/strips.py) is compared with. Lift, moments, stability and control derivatives come from AeroSandbox's vortex
lattice; drag from its AeroBuildup (section drag from NeuralFoil with a compressibility correction, bodies by
skin friction and form factor). Geometry is fdm/data/geometry.json.

    python3 fdm/aero_ref.py          the cruise condition; writes fdm/data/aero_ref.json

Axes here are AeroSandbox's geometry axes: x aft, y right, z up, metres, origin at the nose tip on the ground line.
"""
import json
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E                               # noqa: E402  for the standard atmosphere

FT = 0.3048
G = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
OUT = os.path.join(HERE, 'data', 'aero_ref.json')
AIL = dict(inner=0.55, outer=0.95, chord=0.25)      # ailerons: span fractions and chord fraction. Estimates from photographs
RUDV = dict(chord=0.30)                              # ruddervators: chord fraction, full span of each panel. Estimate
TAIL_TC = 0.10


def lrn1015():
    import aerosandbox as asb
    xy = np.array([[float(v) for v in line.split()] for line in LRN1015.strip().splitlines()])
    return asb.Airfoil(name='lrn1015', coordinates=xy)


def airplane(aileron=0.0, pitch=0.0, yaw=0.0, cg_x=None):
    """The aircraft. Control deflections in degrees: aileron (right trailing edge down), ruddervators together
    (pitch, trailing edge down) and against each other (yaw)."""
    import aerosandbox as asb
    w, t, f, n = G['wing'], G['vtail'], G['fuselage'], G['nacelle']
    af = lrn1015()
    tan_le = np.tan(np.radians(w['sweep_le_deg']))
    half = w['span'] / 2
    ys = sorted(set([0.0] + [s['y'] for s in w['stations'] if s['y'] < 56.0] + [AIL['inner'] * half, AIL['outer'] * half, half]))
    st_y = np.array([s['y'] for s in w['stations']])
    xsecs = []
    for y in ys:
        ctrap = w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * y / half
        chord = float(np.interp(y, st_y, [s['chord'] for s in w['stations']])) if y >= st_y[0] else w['stations'][0]['chord']
        chord = max(chord, ctrap) if y < w['fillet_ends_y'] else ctrap
        twist = float(np.interp(y, st_y, [s['twist_deg'] for s in w['stations']]))
        in_ail = AIL['inner'] * half - 1e-6 <= y < AIL['outer'] * half - 1e-6
        cs = [asb.ControlSurface(name='aileron', symmetric=False, deflection=aileron, hinge_point=1 - AIL['chord'])] if in_ail else []
        xsecs.append(asb.WingXSec(xyz_le=[(w['le_centreline_x'] + y * tan_le) * FT, y * FT, w['z'] * FT], chord=chord * FT,
                                  twist=twist + WING_INCIDENCE, airfoil=af, control_surfaces=cs))
    wing = asb.Wing(name='wing', symmetric=True, xsecs=xsecs)
    tail_af = asb.Airfoil('naca00%02d' % round(100 * TAIL_TC))
    dih = np.radians(t['dihedral_deg'])
    panels = []
    for side in (1, -1):
        d = pitch + side * yaw
        cs = [asb.ControlSurface(name='ruddervator', symmetric=True, deflection=d, hinge_point=1 - RUDV['chord'])]
        root = [t['root_le_x'] * FT, side * t['root_y'] * FT, t['root_z'] * FT]
        tip = [t['tip_le_x'] * FT, side * (t['root_y'] + t['panel_span'] * np.cos(dih)) * FT, t['tip_z'] * FT]
        panels.append(asb.Wing(name='vtail_%s' % ('right' if side > 0 else 'left'), symmetric=False, xsecs=[
            asb.WingXSec(xyz_le=root, chord=t['root_chord'] * FT, airfoil=tail_af, control_surfaces=cs),
            asb.WingXSec(xyz_le=tip, chord=t['tip_chord'] * FT, airfoil=tail_af)]))
    prof = f['profile']
    depth = np.array([p['z_top'] - p['z_bottom'] for p in prof])
    fus = asb.Fuselage(name='fuselage', xsecs=[
        asb.FuselageXSec(xyz_c=[p['x'] * FT, 0, (p['z_top'] + p['z_bottom']) / 2 * FT],
                         width=max(f['max_width'] * min(1.0, d / (0.75 * depth.max())), 0.05) * FT, height=max(d, 0.05) * FT)
        for p, d in zip(prof, depth)])
    r = n['diameter'] / 2
    nac = asb.Fuselage(name='nacelle', xsecs=[
        asb.FuselageXSec(xyz_c=[x * FT, 0, n['thrust_line_z'] * FT], radius=rr * FT)
        for x, rr in ((n['inlet_x'], 0.7 * r), (n['inlet_x'] + 2.0, r), (n['exhaust_x'] - 4.0, r), (n['exhaust_x'], 0.6 * r))])
    cg = cg_x if cg_x is not None else w['mac_le_x'] + 0.27 * w['mac']
    return asb.Airplane(name='Global Hawk', xyz_ref=[cg * FT, 0, 5.3 * FT], wings=[wing] + panels, fuselages=[fus, nac],
                        s_ref=w['area_reference'] * FT ** 2, c_ref=w['mac'] * FT, b_ref=w['span'] * FT)


def op_point(alt_ft, mach, alpha, beta=0.0, p=0.0, q=0.0, r=0.0):
    import aerosandbox as asb
    T, P = E.isa(alt_ft)
    atm = asb.Atmosphere(altitude=0)
    a = np.sqrt(1.4 * 287.05287 * T)
    o = asb.OperatingPoint(atmosphere=asb.Atmosphere(altitude=alt_ft * FT), velocity=mach * a, alpha=alpha, beta=beta, p=p, q=q, r=r)
    return o


def vlm(alt_ft, mach, alpha, beta=0.0, p=0.0, q=0.0, r=0.0, **controls):
    """Vortex lattice: coefficients about the reference point, with the Prandtl-Glauert factor on the loads."""
    import aerosandbox as asb
    ap = airplane(**controls)
    s = asb.VortexLatticeMethod(airplane=ap, op_point=op_point(alt_ft, mach, alpha, beta, p, q, r), spanwise_resolution=1,
                                chordwise_resolution=6, align_trailing_vortices_with_wind=False)
    res = s.run()
    k = 1 / np.sqrt(1 - mach ** 2)                         # the lattice is incompressible
    return {c: float(res[c]) * (k if c != 'CD' else k * k) for c in ('CL', 'CD', 'CY', 'Cl', 'Cm', 'Cn')}


def buildup(alt_ft, mach, alpha, beta=0.0, p=0.0, q=0.0, r=0.0, **controls):
    """AeroBuildup: all six coefficients about the reference point, bodies and control surfaces included."""
    import aerosandbox as asb
    res = asb.AeroBuildup(airplane=airplane(**controls), op_point=op_point(alt_ft, mach, alpha, beta, p, q, r)).run()
    return {c: float(np.ravel(res[c])[0]) for c in ('CL', 'CD', 'CY', 'Cl', 'Cm', 'Cn')}


WING_INCIDENCE = 0.0          # deg, of the root chord to the fuselage datum. Not known: set from flight data later
LRN1015 = open(os.path.join(HERE, 'data', 'lrn1015.dat')).read() if os.path.exists(os.path.join(HERE, 'data', 'lrn1015.dat')) else ''

if __name__ == '__main__':
    alt, mach = 60000.0, 0.6
    a0, a1 = vlm(alt, mach, 0.0), vlm(alt, mach, 4.0)
    cla = (a1['CL'] - a0['CL']) / 4
    cma = (a1['Cm'] - a0['Cm']) / 4
    print('VLM  CL(0) %.4f  CLalpha %.4f/deg  Cm(0) %.4f  Cmalpha %.5f/deg  neutral point %.1f %% MAC (reference at 27 %%)' % (
        a0['CL'], cla, a0['Cm'], cma, 27 - 100 * cma / cla))
    for al in (-2, 0, 2, 4, 6):
        b = buildup(alt, mach, al)
        print('buildup alpha %4.1f  CL %.4f  CD %.5f  L/D %.1f  Cm %.4f' % (al, b['CL'], b['CD'], b['CL'] / b['CD'], b['Cm']))
