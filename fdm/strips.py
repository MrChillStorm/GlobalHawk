#!/usr/bin/env python3
"""The built-up aerodynamic model: the aircraft as strips, each with its own section data. This is what ships.

  wing      strips along the whole span on a lifting line: each strip's lift comes from the LRN 1015's section
            table at its own angle of attack, Reynolds number and the flight Mach number; the trailing vortices of
            all strips give each one its downwash (so induced drag and the spanwise loading come out, and a
            stalled or aileron-deflected strip changes its neighbours)
  V-tail    strips on the two panels, in the wing's downwash and sidewash (Biot-Savart from the same vortices),
            with a symmetric section and the ruddervators as a flap
  bodies    fuselage and nacelle: skin friction with a form factor, and the slender-body (Munk) moments in pitch
            and yaw. No body lift.

Not in it: the wing's bending in flight (the real wing takes up dihedral under load), spoilers, gear, ground
effect, anything past the stall beyond what the section tables hold.

Section data: NeuralFoil through AeroSandbox, with AeroSandbox's compressibility correction. Checked against NASA's
tunnel test of the LRN 1015 in fdm/data/README.md.

    python3 fdm/strips.py            the cruise condition against the reference model; writes fdm/data/aero_compare.json

Axes: x aft from the nose, y right, z up, feet (geometry.json). Forces come back as coefficients on the published
wing area: CL up, CD along the flight path, CY right, and moments Cl (right wing down), Cm (nose up), Cn (nose
right) about the centre of gravity given.
"""
import json
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E                               # noqa: E402  standard atmosphere

G = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
TABLES = os.path.join(HERE, 'data', 'section_tables.json')
FT = 0.3048
ALPHAS = np.arange(-12.0, 20.01, 0.5)
REYNOLDS = [3e5, 6e5, 1e6, 2e6, 4e6, 8e6, 2e7]
MACHS = [0.1, 0.3, 0.45, 0.55, 0.6, 0.65, 0.7]
# Estimates, from photographs and usual practice; none is published
AILERON = dict(inner=0.55, outer=0.95, chord=0.25)
RUDDERVATOR = dict(chord=0.30)
FLAP_VISCOUS = 0.85            # of thin-airfoil flap effectiveness
TAIL_TC = 0.10
EXCRESCENCE = 1.15             # on body drag: antennas, radomes, gaps, the inlet lip
NACELLE_EXPOSED = 0.6          # of the nacelle's surface: the rest is buried in the fuselage (from the side view)
# deg, wing root chord to the axes the aircraft's inertial unit calls level. A fit: it puts the model's trimmed lift
# curve on the ATTREX flights' (fdm/attrex_lift.py), which need 2.1 deg at Mach 0.6 and 1.2 deg at Mach 0.52
WING_INCIDENCE = 2.0
# deg, each V-tail panel's chord to the same axes, leading edge down negative. A choice: it leaves the ruddervators
# near neutral in cruise, as a designer would; the real setting isn't known
TAIL_INCIDENCE = -3.0
# The wing section's pitching moment grows with Mach number as beta^-K, beta = sqrt(1 - M^2), not as NeuralFoil's
# Prandtl-Glauert 1/beta (K = 1) with its own transonic growth on top. A fit, of one parameter, to the one measurement of
# the section: the tunnel's moment (TM 102840) grows 15.5 % from Mach 0.2 to Mach 0.6, the tables' 28 %, XFOIL's
# (Karman-Tsien) 19 %. K is found by fdm/section_study.py, which also reports what it does to S1-S3 and to the speed mode:
# the tables' Mach growth of the moment is what made the bare airframe's speed mode unstable at the cruise.
CM_MACH_K = 0.65
# The wing section's drag at Mach numbers above 0.45 gets the CFD's rise with Mach number, at equal lift, where NeuralFoil's is far smaller
# (fdm/cfd/wave_drag.py writes data/cfd_wave_drag.json; docs/PLAN.md "Wave drag from the CFD"). Not a fit to flight data. False leaves NeuralFoil's drag as it came.
CD_WAVE = True
WAVE_FILE = os.path.join(HERE, 'data', 'cfd_wave_drag.json')
# The wing section's lift at Mach 0.6 above 3.5 deg: the tunnel's maximum height with the CFD's shape past it, a named fit (fdm/cfd/stall_fit.py writes
# data/cfd_stall_m06.json; docs/PLAN.md "Stall at Mach 0.6 fitted to the tunnel"). False leaves NeuralFoil's stall as it came.
STALL_FIT = True
STALL_FILE = os.path.join(HERE, 'data', 'cfd_stall_m06.json')


def section_tables():
    """cl, cd, cm of the wing and tail sections over angle of attack, Reynolds number and Mach. Cached on disk."""
    if os.path.exists(TABLES):
        out = json.load(open(TABLES))
        # the wing's moment: NeuralFoil's, taken from beta^-1 to beta^-K of Mach number (CM_MACH_K above)
        beta = np.sqrt(1 - np.array(out['mach']) ** 2)
        out['wing']['cm'] = (np.array(out['wing']['cm']) * (beta ** (1 - CM_MACH_K))[:, None, None]).tolist()
        if CD_WAVE and os.path.exists(WAVE_FILE):
            w = json.load(open(WAVE_FILE))
            grid_m = [w['reference_mach']] + list(w['mach'])
            grid_d = [np.zeros(len(w['cl']))] + [np.array(d) for d in w['d']]
            cl, cd = np.array(out['wing']['cl']), np.array(out['wing']['cd'])
            for j, m in enumerate(out['mach']):
                if m <= w['reference_mach'] + 1e-9:
                    continue
                # the correction at this table Mach number: between the correction's own Mach numbers, held beyond the last
                k = int(np.clip(np.searchsorted(grid_m, m) - 1, 0, len(grid_m) - 2))
                f = float(np.clip((m - grid_m[k]) / (grid_m[k + 1] - grid_m[k]), 0, 1))
                dm = (1 - f) * grid_d[k] + f * grid_d[k + 1]
                cd[j] = cd[j] + np.interp(np.abs(cl[j]), w['cl'], dm)
            out['wing']['cd'] = cd.tolist()
        if STALL_FIT and os.path.exists(STALL_FILE):
            st = json.load(open(STALL_FILE))
            assert np.allclose(st['alpha'], out['alpha']), 'the stall file is for another angle grid'
            j = list(out['mach']).index(st['mach'])
            cl = np.array(out['wing']['cl'])
            wgt = np.array(st['weight'])[None, :]
            cl[j] = (1 - wgt) * cl[j] + wgt * np.array(st['target'])
            out['wing']['cl'] = cl.tolist()
        return out
    import aerosandbox as asb
    out = dict(alpha=ALPHAS.tolist(), reynolds=REYNOLDS, mach=MACHS,
               source='NeuralFoil (xxlarge) through AeroSandbox %s, n_crit 9, free transition' % asb.__version__)
    xy = np.loadtxt(os.path.join(HERE, 'data', 'lrn1015.dat'))
    for name, af in (('wing', asb.Airfoil(name='lrn1015', coordinates=xy)), ('tail', asb.Airfoil('naca00%02d' % round(100 * TAIL_TC)))):
        t = dict(cl=[], cd=[], cm=[])
        for m in MACHS:
            rows = dict(cl=[], cd=[], cm=[])
            for re in REYNOLDS:
                r = af.get_aero_from_neuralfoil(alpha=ALPHAS, Re=re, mach=m, n_crit=9, model_size='xxlarge')
                for k, kk in (('cl', 'CL'), ('cd', 'CD'), ('cm', 'CM')):
                    rows[k].append(np.round(np.array(r[kk]), 5).tolist())
            for k in rows:
                t[k].append(rows[k])
        out[name] = t
    json.dump(out, open(TABLES, 'w'))
    return out


class Section:
    """A section table at one Mach number: cl, cd, cm at arrays of angle of attack (deg) and Reynolds number."""

    def __init__(self, t, mach):
        m = np.array(MACHS)
        j = int(np.clip(np.searchsorted(m, mach) - 1, 0, len(m) - 2))
        w = float(np.clip((mach - m[j]) / (m[j + 1] - m[j]), 0, 1))
        self.tab = {k: (1 - w) * np.array(t[k][j]) + w * np.array(t[k][j + 1]) for k in ('cl', 'cd', 'cm')}
        self.lre = np.log(np.array(REYNOLDS))

    def __call__(self, alpha, re):
        alpha = np.clip(np.asarray(alpha, float), ALPHAS[0], ALPHAS[-1])
        x = np.clip(np.log(np.asarray(re, float)), self.lre[0], self.lre[-1])
        i = np.clip(np.searchsorted(self.lre, x) - 1, 0, len(self.lre) - 2)
        w = (x - self.lre[i]) / (self.lre[i + 1] - self.lre[i])
        fa = (alpha - ALPHAS[0]) / 0.5
        ia = np.clip(np.floor(fa).astype(int), 0, len(ALPHAS) - 2)
        wa = fa - ia
        out = []
        for k in ('cl', 'cd', 'cm'):
            t = self.tab[k]
            lo = t[i, ia] * (1 - wa) + t[i, ia + 1] * wa
            hi = t[i + 1, ia] * (1 - wa) + t[i + 1, ia + 1] * wa
            out.append(lo * (1 - w) + hi * w)
        return out


def flap_tau(cf):
    """Thin-airfoil effectiveness of a plain flap of chord fraction cf: change of zero-lift angle per unit deflection."""
    th = np.arccos(2 * cf - 1)
    return (1 - (th - np.sin(th)) / np.pi) * FLAP_VISCOUS


def body_volume(profile, width):
    x = np.array([p['x'] for p in profile])
    d = np.array([p['z_top'] - p['z_bottom'] for p in profile])
    w = width * np.minimum(1.0, d / (0.75 * d.max()))
    return float(np.trapezoid(np.pi / 4 * w * d, x)), float(np.trapezoid(np.pi * (w + d) / 2, x)), float(np.trapezoid(d, x)), d.max()


class Aircraft:
    def __init__(self, n=40, n_tail=8):
        w, t = G['wing'], G['vtail']
        half = w['span'] / 2
        th = np.linspace(0, np.pi, 2 * n + 1)
        edges = -half * np.cos(th)                           # cosine spacing over the whole span
        y = 0.5 * (edges[1:] + edges[:-1])
        st_y = np.array([s['y'] for s in w['stations']])
        ay = np.abs(y)
        ctrap = w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * ay / half
        cst = np.interp(ay, st_y, [s['chord'] for s in w['stations']])
        self.c = np.where(ay < w['fillet_ends_y'], np.maximum(cst, ctrap), ctrap)
        self.twist = np.interp(ay, st_y, [s['twist_deg'] for s in w['stations']])
        self.y, self.dy, self.ya, self.yb = y, np.diff(edges), edges[:-1], edges[1:]
        self.sweep = np.radians(w['sweep_quarter_deg'])
        # quarter-chord line of the trapezoid; the fillet adds chord behind it
        self.x = w['le_centreline_x'] + 0.25 * w['root_chord_centreline'] + ay * np.tan(self.sweep)
        self.z = np.full_like(y, w['z'])
        self.dzdy = np.zeros_like(y)                          # slope of the bent wing, dz/dy: none when rigid
        self.ail = np.where((ay >= AILERON['inner'] * half) & (ay <= AILERON['outer'] * half), np.sign(y), 0.0)
        self.S, self.b, self.cbar = w['area_reference'], w['span'], w['mac']
        self.wing_area_strips = float(np.sum(self.c * self.dy))
        # V-tail strips
        dih = np.radians(t['dihedral_deg'])
        s = (np.arange(n_tail) + 0.5) / n_tail
        self.tail = []
        for side in (1, -1):
            c = t['root_chord'] + (t['tip_chord'] - t['root_chord']) * s
            xq = t['root_le_x'] + (t['tip_le_x'] - t['root_le_x']) * s + 0.25 * c
            self.tail.append(dict(side=side, c=c, ds=np.full(n_tail, t['panel_span'] / n_tail), x=xq,
                                  y=side * (t['root_y'] + s * t['panel_span'] * np.cos(dih)),
                                  z=t['root_z'] + s * t['panel_span'] * np.sin(dih),
                                  n=np.array([0.0, -side * np.sin(dih), np.cos(dih)])))     # normal: up and inward
        ar = (2 * t['panel_span']) ** 2 / t['area_total']
        self.tail_ar = ar
        # bodies
        f, nac = G['fuselage'], G['nacelle']
        self.fus = dict(zip(('volume', 'wetted', 'side_area', 'depth'), body_volume(f['profile'], f['max_width'])))
        self.fus.update(length=f['length'], width=f['max_width'], x_mid=0.45 * f['length'])
        self.nac = dict(length=nac['length'], diameter=nac['diameter'], wetted=np.pi * nac['diameter'] * nac['length'] * NACELLE_EXPOSED,
                        volume=np.pi / 4 * nac['diameter'] ** 2 * nac['length'] * 0.8, x_mid=nac['inlet_x'] + 0.5 * nac['length'],
                        z=nac['thrust_line_z'])
        self.tables = section_tables()

    def bend(self, y, deflection, slope):
        """Give the wing a bent shape: deflection (ft, up) and slope along the half span, mirrored to both sides.
        None puts it back flat. The strips' heights change, and a tilted strip feels sideslip as angle of attack."""
        if y is None:
            self.z = np.full_like(self.y, G['wing']['z'])
            self.dzdy = np.zeros_like(self.y)
            return
        ay = np.abs(self.y)
        self.z = G['wing']['z'] + np.interp(ay, y, deflection, left=0.0)
        self.dzdy = np.sign(self.y) * np.interp(ay, y, slope, left=0.0)

    def cg_at(self, percent_mac):
        return np.array([G['wing']['mac_le_x'] + percent_mac / 100.0 * G['wing']['mac'], 0.0, 5.3])

    def image_downwash(self, agl):
        """Downwash at each wing strip per unit circulation of each strip's mirror image below the ground
        (negative: the images push the air up). The ground is taken as level with the aircraft's x axis."""
        pts = np.stack([self.x, self.y, self.z], -1)
        Dg = np.zeros((len(self.y), len(self.y)))
        for j in range(len(self.y)):
            g = np.zeros(len(self.y))
            g[j] = -1.0
            Dg[:, j] = -self.induced(g, pts, mirror=agl, only=j)[:, 2]
        return Dg

    def induced(self, gamma, pts, mirror=None, only=None):
        """Velocity (ft/s per unit, in body axes) induced at points by the wing's horseshoe vortices: straight bound
        segments along y at each strip's quarter chord, trailing legs straight aft to infinity. mirror: the same
        vortices reflected in the ground, the wheels being that many feet above it (z is measured from the wheels)."""
        v = np.zeros_like(pts)
        zs = self.z if mirror is None else -self.z - 2.0 * mirror
        for j, (a, b, x, z, g) in enumerate(zip(self.ya, self.yb, self.x, zs, gamma)):
            if only is not None and j != only:
                continue
            A, B = np.array([x, a, z]), np.array([x, b, z])
            v += g * (_segment(pts, A, B) + _semi(pts, B, +1.0) - _semi(pts, A, +1.0))
        return v

    def solve(self, alt_ft, mach, alpha, beta=0.0, p=0.0, q=0.0, r=0.0, aileron=0.0, pitch=0.0, yaw=0.0, cg=None, agl=None):
        """Coefficients at a flight condition. Angles and deflections in degrees, rates in rad/s.
        aileron: right trailing edge down; pitch: both ruddervators trailing edge down; yaw: against each other.
        agl: height of the wheels above the ground, ft, for ground effect: the wing's vortices get mirror images
        below the ground, which hold back the downwash at the wing and at the tail."""
        T, P = E.isa(alt_ft)
        rho = P / (287.05287 * T) / 515.378818              # slug/ft3
        a = np.sqrt(1.4 * 287.05287 * T) / FT
        V = mach * a
        mu = 1.458e-6 * T ** 1.5 / (T + 110.4) / 47.880259   # slug/ft/s
        cg = self.cg_at(27.0) if cg is None else np.asarray(cg, float)
        al, be = np.radians(alpha), np.radians(beta)
        # air velocity relative to the aircraft, in geometry axes (x aft, y right, z up)
        vinf = V * np.array([np.cos(al) * np.cos(be), -np.sin(be), np.sin(al) * np.cos(be)])
        omega = np.array([-p, q, -r])                         # body rates (roll right, pitch up, yaw right) in these axes

        def local(x, y, z):
            rr = np.stack([x - cg[0], y - cg[1], z - cg[2]], -1)
            return vinf - np.cross(omega, rr)                 # the air's velocity seen by a point turning with the aircraft

        sec_w, sec_t = Section(self.tables['wing'], mach), Section(self.tables['tail'], mach)
        # --- wing lifting line
        vl = local(self.x, self.y, self.z)
        sgn = np.sign(self.y)
        un = vl[:, 0] * np.cos(self.sweep) + sgn * vl[:, 1] * np.sin(self.sweep)     # normal to the quarter-chord line
        # the air's speed normal to each strip: on a wing bent upward, sideslip adds to it on the windward side
        cosg = 1.0 / np.sqrt(1.0 + self.dzdy ** 2)
        wn = (vl[:, 2] - vl[:, 1] * self.dzdy) * cosg
        vn = np.sqrt(un ** 2 + wn ** 2)
        ageo = np.degrees(np.arctan2(wn, un)) + self.twist + WING_INCIDENCE + np.degrees(flap_tau(AILERON['chord'])) * \
            np.radians(aileron) * self.ail
        re = rho * vn * self.c / mu
        # downwash matrix: w at strip i per unit circulation of strip j (trailing legs only, the classical lifting line)
        yi = self.y[:, None]
        D = (1.0 / (yi - self.ya[None, :]) - 1.0 / (yi - self.yb[None, :])) / (4 * np.pi)
        if agl is not None:
            D = D + self.image_downwash(agl)
        # Newton's method on the circulation: residual gamma - V c cl(alpha_eff(gamma)) / 2, with each section's
        # own lift slope in the Jacobian
        gamma = np.zeros_like(self.y)
        for it in range(200):
            wi = D @ gamma                                    # downward
            aeff = ageo - np.degrees(wi / vn)
            cl, cd, cm = sec_w(aeff, re)
            slope = (sec_w(aeff + 0.25, re)[0] - sec_w(aeff - 0.25, re)[0]) / np.radians(0.5)
            res = gamma - 0.5 * vn * self.c * cl
            if np.max(np.abs(res)) < 1e-7 * V * self.cbar:
                break
            # Past a section's stall its slope is negative and plain Newton runs away. The Jacobian keeps a
            # floor on the slope, and no strip's angle of attack may move more than 2 deg in one step.
            J = np.eye(len(gamma)) + (0.5 * self.c * np.maximum(slope, 2.0))[:, None] * D
            step = np.linalg.solve(J, res)
            dalpha = np.max(np.abs(np.degrees((D @ step) / vn)))
            gamma -= step * min(0.8, 2.0 / max(dalpha, 1e-9))
        ai = wi / vn
        qs = 0.5 * rho * vn ** 2 * self.c * self.dy
        # lift is normal to the effective flow (tilted back by the induced angle), drag along it
        th = np.arctan2(wn, un) - ai                          # direction of the effective flow above the x axis
        fx = qs * (-cl * np.sin(th) + cd * np.cos(th))
        fn = qs * (cl * np.cos(th) + cd * np.sin(th))         # normal to the strip, which leans inward when bent
        F = np.stack([fx, -fn * self.dzdy * cosg, fn * cosg], -1)
        M = np.cross(np.stack([self.x - cg[0], self.y - cg[1], self.z - cg[2]], -1), F)
        M[:, 1] += qs * self.c * cm                            # section moments: nose up is about +y in these axes
        Ftot, Mtot = F.sum(0), M.sum(0)
        parts = dict(wing=(F.sum(0), M.sum(0)))
        # --- V-tail
        k3d = self.tail_ar / (self.tail_ar + 2 * (self.tail_ar + 4) / (self.tail_ar + 2))    # Helmbold-like finite-span factor
        tau = np.degrees(flap_tau(RUDDERVATOR['chord']))
        Ft, Mt = np.zeros(3), np.zeros(3)
        for pan in self.tail:
            pts = np.stack([pan['x'], pan['y'], pan['z']], -1)
            vt = local(pan['x'], pan['y'], pan['z']) + self.induced(gamma, pts)
            if agl is not None:
                vt = vt + self.induced(-gamma, pts, mirror=agl)
            chordwise = vt[:, 0]
            normal = vt @ pan['n']
            vmag = np.sqrt(chordwise ** 2 + normal ** 2)
            d = pitch + pan['side'] * yaw
            an = (np.degrees(np.arctan2(normal, chordwise)) + TAIL_INCIDENCE + tau * np.radians(d)) * k3d
            clt, cdt, cmt = sec_t(an, rho * vmag * pan['c'] / mu)
            qt = 0.5 * rho * vmag ** 2 * pan['c'] * pan['ds']
            tht = np.arctan2(normal, chordwise)
            f = (qt * (clt * np.cos(tht) + cdt * np.sin(tht)))[:, None] * pan['n'][None, :] + \
                (qt * (-clt * np.sin(tht) + cdt * np.cos(tht)))[:, None] * np.array([1.0, 0, 0])[None, :]
            Ft += f.sum(0)
            Mt += np.cross(pts - cg, f).sum(0)
        Ftot, Mtot = Ftot + Ft, Mtot + Mt
        parts['tail'] = (Ft, Mt)
        # --- bodies: drag along the flight path at the body's middle, Munk moments
        qinf = 0.5 * rho * V ** 2
        Fb, Mb = np.zeros(3), np.zeros(3)
        for body in (self.fus, self.nac):
            L = body['length']
            rel = rho * V * L / mu
            cf = 0.455 / np.log10(rel) ** 2.58 / (1 + 0.144 * mach ** 2) ** 0.65
            fine = L / (body.get('depth', body.get('diameter')))
            cd_area = cf * (1 + 60 / fine ** 3 + fine / 400) * body['wetted'] * EXCRESCENCE
            fb = qinf * cd_area * vinf / V
            Fb += fb
            Mb += np.cross(np.array([body['x_mid'], 0, body.get('z', 5.3)]) - cg, fb)
        k = 0.93                                              # apparent-mass factor k2 - k1 for a fineness ratio of 8
        Mb[1] += qinf * 2 * k * self.fus['volume'] * al       # nose up with angle of attack
        # in yaw the body is deeper than wide, so it carries more apparent mass sideways; nose away from the wind
        Mb[2] += qinf * 2 * k * self.fus['volume'] * (self.fus['depth'] / self.fus['width']) * be
        Ftot, Mtot = Ftot + Fb, Mtot + Mb
        parts['bodies'] = (Fb, Mb)
        return self._coefficients(Ftot, Mtot, qinf, al, be, parts, dict(cl=cl, aeff=aeff, ai=np.degrees(ai), re=re,
                                                                      gamma=gamma, iterations=it))

    def _coefficients(self, F, M, qinf, al, be, parts, strips):
        S, b, c = self.S, self.b, self.cbar

        def coef(F, M):
            # wind axes: drag along the air's direction, lift normal to it in the plane of symmetry
            d = np.array([np.cos(al) * np.cos(be), -np.sin(be), np.sin(al) * np.cos(be)])
            lz = np.array([-np.sin(al), 0.0, np.cos(al)])
            return dict(CL=float(F @ lz) / (qinf * S), CD=float(F @ d) / (qinf * S), CY=float(F[1]) / (qinf * S),
                        Cl=float(-M[0]) / (qinf * S * b), Cm=float(M[1]) / (qinf * S * c), Cn=float(-M[2]) / (qinf * S * b))
        out = coef(F, M)
        out['parts'] = {k: coef(*v) for k, v in parts.items()}
        out['strips'] = strips
        return out


def _segment(p, A, B):
    """Velocity at points p from a unit-strength straight vortex from A to B."""
    r1, r2 = p - A, p - B
    cr = np.cross(r1, r2)
    n1, n2 = np.linalg.norm(r1, axis=-1), np.linalg.norm(r2, axis=-1)
    den = (cr * cr).sum(-1)
    k = np.where(den > 1e-9, ((B - A) @ (r1 / n1[:, None] - r2 / n2[:, None]).T) / np.maximum(den, 1e-9), 0.0)
    return cr * k[:, None] / (4 * np.pi)


def _semi(p, A, sign):
    """Velocity at points p from a unit-strength vortex from A straight aft (+x) to infinity."""
    r = p - A
    h2 = r[:, 1] ** 2 + r[:, 2] ** 2
    n = np.linalg.norm(r, axis=-1)
    k = np.where(h2 > 1e-9, (1 + r[:, 0] / n) / np.maximum(h2, 1e-9), 0.0) / (4 * np.pi)
    # direction: x cross r, for a vortex running towards +x
    return sign * np.stack([np.zeros_like(k), -r[:, 2] * k, r[:, 1] * k], -1)


def derivatives(f, alt, mach, alpha, cg=None):
    """Stability and control derivatives of a model f(alt, mach, alpha, **kw) -> coefficients, by differences."""
    kw = {} if cg is None else dict(cg=cg)
    b = f(alt, mach, alpha, **kw)
    d = dict(base=b)
    a1, a2 = f(alt, mach, alpha - 1.5, **kw), f(alt, mach, alpha + 1.5, **kw)   # a wide step: section tables have small kinks
    d['CLalpha'] = (a2['CL'] - a1['CL']) / 3.0
    d['Cmalpha'] = (a2['Cm'] - a1['Cm']) / 3.0
    d['dCm_dCL'] = d['Cmalpha'] / d['CLalpha']
    s2 = f(alt, mach, alpha, beta=2.0, **kw)
    for k, name in (('CY', 'CYbeta'), ('Cl', 'Clbeta'), ('Cn', 'Cnbeta')):
        d[name] = (s2[k] - b[k]) / 2.0
    for ctl, pairs in (('aileron', (('Cl', 'Cl_aileron'), ('Cn', 'Cn_aileron'))), ('pitch', (('Cm', 'Cm_pitch'), ('CL', 'CL_pitch'))),
                       ('yaw', (('Cn', 'Cn_yaw'), ('Cl', 'Cl_yaw'), ('CY', 'CY_yaw')))):
        c2 = f(alt, mach, alpha, **dict(kw, **{ctl: 5.0}))
        for k, name in pairs:
            d[name] = (c2[k] - b[k]) / 5.0
    return d


def compare(alt=60000.0, mach=0.6, alpha=2.5):
    """Our strips against the reference at one condition: AeroSandbox's build-up (bodies and controls in it) and,
    where it has something to say, its vortex lattice (wing and tail only, no bodies, no control surfaces)."""
    import aero_ref as R
    ac = Aircraft()
    cg = ac.cg_at(27.0)
    ours = lambda alt, mach, alpha, **kw: ac.solve(alt, mach, alpha, **kw)
    bld = lambda alt, mach, alpha, cg=None, **kw: R.buildup(alt, mach, alpha, **kw)
    vlm = lambda alt, mach, alpha, cg=None, **kw: R.vlm(alt, mach, alpha, **kw)
    out = dict(condition=dict(altitude_ft=alt, mach=mach, alpha=alpha, cg_percent_mac=27.0), rows=[])
    do, db, dv = derivatives(ours, alt, mach, alpha, cg=cg), derivatives(bld, alt, mach, alpha), derivatives(vlm, alt, mach, alpha)
    rows = out['rows']
    add = lambda name, a, b, c=None, unit='': rows.append(dict(name=name, strips=float(a), buildup=float(b),
                                                                 lattice=None if c is None else float(c), unit=unit))
    add('CL at %.1f deg' % alpha, do['base']['CL'], db['base']['CL'])
    add('CLalpha', do['CLalpha'], db['CLalpha'], dv['CLalpha'], 'per deg')
    add('neutral point', 27.0 - 100 * do['dCm_dCL'], 27.0 - 100 * db['dCm_dCL'], unit='% MAC')
    add('neutral point without bodies', 27.0 - 100 * (do['Cmalpha'] - _body_cma(ac, alt, mach)) / do['CLalpha'], float('nan'),
        27.0 - 100 * dv['dCm_dCL'], '% MAC')
    add('Cm at %.1f deg, CG 27 %%' % alpha, do['base']['Cm'], db['base']['Cm'])
    for k in ('CYbeta', 'Clbeta', 'Cnbeta'):
        add(k, do[k], db[k], dv[k], 'per deg')
    for k in ('Cl_aileron', 'Cn_aileron', 'Cm_pitch', 'CL_pitch', 'Cn_yaw', 'Cl_yaw', 'CY_yaw'):
        add(k, do[k], db[k], unit='per deg')
    # rates, per unit of the usual nondimensional rate (p b / 2V, q c / 2V, r b / 2V)
    T = E.isa(alt)[0]
    V = mach * np.sqrt(1.4 * 287.05287 * T) / FT
    for rate, key, name, ref_len in (('p', 'Cl', 'Clp', ac.b), ('q', 'Cm', 'Cmq', ac.cbar), ('r', 'Cn', 'Cnr', ac.b), ('p', 'Cn', 'Cnp', ac.b),
                                     ('r', 'Cl', 'Clr', ac.b)):
        hat = 0.02 if rate != 'q' else 0.002
        w = hat * 2 * V / ref_len
        a = (ours(alt, mach, alpha, cg=cg, **{rate: w})[key] - do['base'][key]) / hat
        b = (bld(alt, mach, alpha, **{rate: w})[key] - db['base'][key]) / hat
        c = (vlm(alt, mach, alpha, **{rate: w})[key] - dv['base'][key]) / hat
        add(name, a, b, c, 'per unit rate')
    polar = []
    for al in (-2, -1, 0, 1, 2, 3, 4, 5, 6):
        o, rb = ours(alt, mach, float(al), cg=cg), R.buildup(alt, mach, float(al))
        polar.append(dict(alpha=al, strips=dict(CL=o['CL'], CD=o['CD'], Cm=o['Cm'], parts={k: v['CD'] for k, v in o['parts'].items()}),
                          reference=rb))
    out['polar'] = polar
    # trimmed: ruddervators to zero pitching moment at the reference centre of gravity, ours only
    trim = []
    for cl_target in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        al, de = 2.0, 0.0
        for _ in range(12):
            o = ours(alt, mach, al, cg=cg, pitch=de)
            al += (cl_target - o['CL']) / do['CLalpha']
            de -= o['Cm'] / do['Cm_pitch']
        o = ours(alt, mach, al, cg=cg, pitch=de)
        trim.append(dict(CL=o['CL'], CD=o['CD'], alpha=al, ruddervator=de, Cm=o['Cm']))
    out['trim'] = trim
    return out


def _body_cma(ac, alt, mach):
    a = ac.solve(alt, mach, 2.0)['parts']['bodies']['Cm']
    b = ac.solve(alt, mach, 3.0)['parts']['bodies']['Cm']
    return b - a


if __name__ == '__main__':
    out = compare()
    c = out['condition']
    print('Mach %.2f, %.0f ft, alpha %.1f deg, CG at 27 %% MAC' % (c['mach'], c['altitude_ft'], c['alpha']))
    print('  %-30s %11s %11s %11s' % ('', 'strips', 'build-up', 'lattice'))
    for r in out['rows']:
        print('  %-30s %11.5f %11.5f %11s  %s' % (r['name'], r['strips'], r['buildup'],
                                                 '' if r['lattice'] is None else '%.5f' % r['lattice'], r['unit']))
    print('  alpha   CL ours  ref    CD ours    ref     L/D ours  ref    Cm ours    ref    (ours: wing, tail, bodies CD)')
    for p in out['polar']:
        o, rf = p['strips'], p['reference']
        print('  %5.1f  %6.3f %6.3f  %8.5f %8.5f  %6.1f %6.1f  %7.4f %7.4f   %s' % (
            p['alpha'], o['CL'], rf['CL'], o['CD'], rf['CD'], o['CL'] / o['CD'], rf['CL'] / rf['CD'], o['Cm'], rf['Cm'],
            ' '.join('%.5f' % o['parts'][k] for k in ('wing', 'tail', 'bodies'))))
    print('  trimmed with the ruddervators (ours):')
    for t in out['trim']:
        print('    CL %.3f  CD %.5f  L/D %.1f  alpha %.2f deg  ruddervators %+.2f deg' % (t['CL'], t['CD'], t['CL'] / t['CD'], t['alpha'], t['ruddervator']))
    json.dump(out, open(os.path.join(HERE, 'data', 'aero_compare.json'), 'w'), indent=1, default=float)
