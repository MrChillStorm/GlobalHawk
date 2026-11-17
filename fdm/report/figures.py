#!/usr/bin/env python3
"""The report's figures, from the data files, the check logs in results/ and histories.json (mkresults.py)."""
import json
import os
import re
import sys

import matplotlib
matplotlib.use('pdf')
import matplotlib.pyplot as plt     # noqa: E402
import numpy as np                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, 'results')
F = os.path.join(HERE, 'fig')
D = os.path.join(HERE, '..', 'data')
plt.rcParams.update({'font.family': 'serif', 'font.size': 8, 'axes.grid': True, 'grid.linewidth': 0.3, 'axes.linewidth': 0.5, 'lines.linewidth': 1.0,
                     'lines.markersize': 3.5, 'legend.fontsize': 7, 'legend.frameon': False, 'xtick.major.width': 0.4, 'ytick.major.width': 0.4})
BLUE, RED, GREY, GREEN, ORANGE = '#1f4e8c', '#b03030', '#777777', '#2a7a3a', '#c7791a'
NM = 6076.1
H = json.load(open(os.path.join(R, 'histories.json')))
data = lambda n: json.load(open(os.path.join(D, n + '.json')))


def save(fig, name):
    fig.savefig(os.path.join(F, name + '.pdf'), bbox_inches='tight', pad_inches=0.02)
    plt.close(fig)


def checks(name):
    """the rows of a check log: (tag, check, model, reference, pass)"""
    out = []
    for line in open(os.path.join(R, name + '.txt'), errors='replace'):
        m = re.match(r'\s*([A-Z]{1,2}\d+[a-z]?)\s+(.+?)\s{2,}(-?[\d.eE+]+)\s+(-?[\d.eE+]+)\s+.*?\s(pass|MISS)', line)
        if m:
            out.append((m.group(1), m.group(2).strip(), float(m.group(3)), float(m.group(4)), m.group(5) == 'pass'))
    return out


def geometry():
    """plan and side view, from geometry.json: what the flight model is built on"""
    g = data('geometry')
    w, fu, n, v, gr = g['wing'], g['fuselage'], g['nacelle'], g['vtail'], g['gear']
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.0, 3.9), gridspec_kw=dict(height_ratios=[1.45, 1.0], hspace=0.12))
    half = w['span'] / 2
    le = lambda y: w['le_centreline_x'] + abs(y) * np.tan(np.radians(w['sweep_le_deg']))
    ch = lambda y: w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * abs(y) / half
    for s in (-1, 1):
        ys = np.linspace(fu['max_width'] / 2, half, 30)
        a1.plot(s * ys, [le(y) for y in ys], color=BLUE, lw=0.8)
        a1.plot(s * ys, [le(y) + ch(y) for y in ys], color=BLUE, lw=0.8)
        a1.plot([s * half, s * half], [le(half), le(half) + ch(half)], color=BLUE, lw=0.8)
        # the ailerons (55 to 95 % of the semi-span, 25 % chord: estimates)
        ya = np.array([0.55, 0.95]) * half
        a1.fill(s * np.r_[ya, ya[::-1]], np.r_[[le(y) + 0.75 * ch(y) for y in ya], [le(y) + ch(y) for y in ya[::-1]]], color='#f2dcd9', ec=RED, lw=0.4)
        # the V-tail's panels, seen from above
        yt = v['root_y'] + v['panel_span'] * np.cos(np.radians(v['dihedral_deg']))
        a1.fill(s * np.array([v['root_y'], yt, yt, v['root_y']]), [v['root_le_x'], v['tip_le_x'], v['tip_le_x'] + v['tip_chord'], v['root_le_x'] + v['root_chord']],
                color='#d9e6f2', ec=BLUE, lw=0.5)
        a1.plot(s * gr['main_track'] / 2, gr['main_x'], 's', color=GREY, ms=3)
    x = np.array([p['x'] for p in fu['profile']])
    d = np.array([p['z_top'] - p['z_bottom'] for p in fu['profile']])
    wd = fu['max_width'] * np.minimum(1.0, d / (0.75 * d.max()))
    a1.fill(np.r_[wd / 2, -wd[::-1] / 2], np.r_[x, x[::-1]], color='#eeeeee', ec='0.3', lw=0.6)
    a1.fill([-n['diameter'] / 2, n['diameter'] / 2, n['diameter'] / 2, -n['diameter'] / 2], [n['inlet_x'], n['inlet_x'], n['exhaust_x'], n['exhaust_x']], color='#dddddd', ec='0.3', lw=0.5)
    a1.plot(0, gr['nose_x'], 's', color=GREY, ms=3)
    a1.plot(0, w['mac_quarter_x'] - 0.25 * w['mac'] + 0.22 * w['mac'], '+', color=RED, ms=7)
    a1.set_aspect('equal')
    a1.invert_yaxis()
    a1.set_ylabel('x, ft aft of the nose')
    a1.tick_params(labelbottom=False)
    a1.grid(False)
    a2.fill(np.r_[x, x[::-1]], np.r_[[p['z_top'] for p in fu['profile']], [p['z_bottom'] for p in fu['profile']][::-1]], color='#eeeeee', ec='0.3', lw=0.6)
    a2.fill([n['inlet_x'], n['exhaust_x'], n['exhaust_x'], n['inlet_x']], [n['top_z'] - n['diameter'], n['top_z'] - n['diameter'], n['top_z'], n['top_z']], color='#dddddd', ec='0.3', lw=0.5)
    a2.fill([v['root_le_x'], v['tip_le_x'], v['tip_le_x'] + v['tip_chord'], v['root_le_x'] + v['root_chord']], [v['root_z'], v['tip_z'], v['tip_z'], v['root_z']], color='#d9e6f2', ec=BLUE, lw=0.5)
    a2.plot([w['le_centreline_x'], w['le_centreline_x'] + w['root_chord_centreline']], [w['z'], w['z']], color=BLUE, lw=1.6)
    for xx, zz, dd in ((gr['main_x'], gr['main_axle_z'], gr['main_wheel_diameter']), (gr['nose_x'], gr['nose_axle_z'], gr['nose_wheel_diameter'])):
        a2.add_patch(plt.Circle((xx, zz), dd / 2, fc='0.4', ec='0.2', lw=0.4))
    a2.axhline(0, color='0.3', lw=0.5)
    a2.annotate('', (n['exhaust_x'] + 3.5, n['thrust_line_z']), (n['exhaust_x'], n['thrust_line_z']), arrowprops=dict(arrowstyle='<-', color=RED, lw=0.8))
    a2.set_aspect('equal')
    a2.set_xlim(-3, 48)
    a2.set_xlabel('x, ft')
    a2.set_ylabel('z, ft')
    a2.grid(False)
    save(fig, 'geometry')


def engine():
    e = H['engine']
    alt, mach = np.array(e['altitude_ft']), np.array(e['mach'])
    T = np.array(e['max_thrust_lbf'])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 2.5), gridspec_kw=dict(width_ratios=[1.0, 1.15], wspace=0.28))
    for m, col in ((0.0, GREY), (0.3, GREEN), (0.6, BLUE)):
        j = int(np.argmin(np.abs(mach - m)))
        a1.semilogy(alt / 1000, T[:, j], color=col, label='Mach %.1f' % mach[j])
        for kind, mk in (('rating', 's'), ('temperature', 'o'), ('fan speed', '^')):
            k = [i for i in range(len(alt)) if e['limit'][i][j].startswith(kind[:4])]
            a1.semilogy(alt[k] / 1000, T[k, j], mk, color=col, ms=3, mfc='white', mew=0.7)
    for kind, mk in (('flat rating', 's'), ('turbine temperature', 'o'), ('fan speed', '^')):
        a1.plot([], [], mk, color='0.3', mfc='white', mew=0.7, label='limit: ' + kind)
    a1.set_xlabel('pressure altitude, 1000 ft')
    a1.set_ylabel('maximum thrust, lbf')
    a1.legend(loc='lower left')
    rows = [('engine', c) for c in checks('engine')] + [('pyCycle', c) for c in checks('engine_pycycle') if c[0] != 'X4']
    y = 0
    labels = []
    for which, (tag, name, val, ref, ok) in rows:
        err = 100 * (val / ref - 1)
        a2.plot(err, y, 'o' if which == 'engine' else 'D', color=BLUE if ok else RED, ms=4, mfc=(BLUE if ok else RED) if which == 'engine' else 'white')
        labels.append(tag)
        y -= 1
    a2.set_yticks(range(0, y, -1))
    a2.set_yticklabels(labels, fontsize=6)
    a2.axvline(0, color='0.3', lw=0.5)
    a2.plot([], [], 'o', color=BLUE, label='cycle model: pass')
    a2.plot([], [], 'o', color=RED, label='miss')
    a2.plot([], [], 'D', color=BLUE, mfc='white', label='pyCycle')
    a2.set_xlabel('model against the source, %')
    a2.set_xlim(-18, 34)
    a2.legend(loc='center right')
    save(fig, 'engine')


def section():
    sys.path.insert(0, os.path.join(HERE, '..'))
    import strips as S
    tun = data('lrn1015_tunnel')
    fig, ax = plt.subplots(2, 3, figsize=(7.0, 3.6), sharey='row', gridspec_kw=dict(hspace=0.08, wspace=0.06))
    for k, c in enumerate(tun['cases']):
        cl, cd, cm = S.Section(S.section_tables()['wing'], c['mach'])(S.ALPHAS, np.full(len(S.ALPHAS), c['reynolds']))
        top = int(np.argmax(cl))
        lo = int(np.argmin(np.abs(S.ALPHAS + 6)))
        ax[0, k].plot([p[1] for p in c['cd']], [1e4 * p[0] for p in c['cd']], 'o', color=RED, mfc='white', mew=0.6, label='tunnel')
        ax[0, k].plot(cl[lo:top + 1], 1e4 * cd[lo:top + 1], color=BLUE, label='section data')
        ax[1, k].plot([p[1] for p in c['cm']], [p[0] for p in c['cm']], 'o', color=RED, mfc='white', mew=0.6)
        ax[1, k].plot(cl[lo:top + 1], cm[lo:top + 1], color=BLUE)
        ax[0, k].axvspan(0.4, 1.0, color='0.93', lw=0)
        ax[1, k].axvspan(0.4, 1.0, color='0.93', lw=0)
        ax[0, k].set_title('Mach %.1f, Reynolds %.0f million' % (c['mach'], c['reynolds'] / 1e6), fontsize=8)
        ax[0, k].set_ylim(0, 300)
        ax[0, k].set_xlim(-0.2, 1.5)
        ax[1, k].set_xlim(-0.2, 1.5)
        ax[1, k].set_ylim(-0.18, 0.0)
        ax[0, k].tick_params(labelbottom=False)
        ax[1, k].set_xlabel('lift coefficient')
    ax[0, 0].set_ylabel('profile drag, counts')
    ax[1, 0].set_ylabel('moment about c/4')
    ax[0, 0].legend(loc='upper left')
    save(fig, 'section')


def calibration():
    m = H['mission']
    fig, ax = plt.subplots(1, 3, figsize=(7.0, 2.45), gridspec_kw=dict(wspace=0.42))
    a = ax[0]
    t, alt = np.array(m['climb']['t']), np.array(m['climb']['alt'])
    t10 = float(np.interp(10000, alt, t))
    a.plot((t - t10) / 60, alt / 1000, color=BLUE, label='model, quasi-steady')
    cl = H['climb_laws']
    a.plot(np.array(cl['t']) / 60, np.array(cl['alt']) / 1000, color=GREEN, ls='--', label='flown by the laws')
    for k in (0, 1):
        a.plot([0] + [v[k] / 60 for v in m['pastor_climb'].values()], [10] + [float(h) / 1000 for h in m['pastor_climb']], 'o', color=RED, mfc='white', mew=0.7,
               label='measured, two flights' if k == 0 else None)
    a.set_xlim(0, 85)
    a.set_ylim(8, 58)
    a.set_xlabel('minutes from 10,000 ft')
    a.set_ylabel('height, 1000 ft')
    a.legend(loc='lower right')
    a = ax[1]
    a.plot(np.array(m['t']) / 3600, np.array(m['alt']) / 1000, color=BLUE, label='model')
    for k in (0, 1):
        a.plot([p[0][k] / 60 for p in m['pastor_cruise']], [p[1][k] / 1000 for p in m['pastor_cruise']], 'o', color=RED, mfc='white', mew=0.7,
               label='measured' if k == 0 else None)
    a.axhline(65, color=GREY, lw=0.6, ls=':')
    a.set_xlim(0, 36)
    a.set_ylim(50, 72)
    a.set_xlabel('hours after takeoff')
    a.set_ylabel('height, 1000 ft')
    a.legend(loc='lower right')
    a = ax[2]
    L = data('attrex_lift')
    fit = [x for x in L['lift_fits'] if x['mach_lo'] > 0.55][0]
    model = [c for c in checks('phase4_checks') if c[0] == 'A1' and '0.59' in c[1]][0]
    cols = [BLUE, GREEN, ORANGE]
    for n, fl in enumerate(fit['flights']):
        pts = [p for p in L['points'] if p['flight'] == fl and fit['mach_lo'] <= p['mach'] <= fit['mach_hi']]
        a0, c0 = np.mean([p['aoa'] for p in pts]), np.mean([p['cl'] for p in pts])
        a.plot([p['aoa'] - a0 for p in pts], [p['cl'] - c0 for p in pts], '.', color=cols[n % 3], ms=3.5, label='%s-%s-%s' % (fl[:4], fl[4:6], fl[6:]))
    x = np.array([-0.8, 0.8])
    a.plot(x, fit['slope_per_deg'] * x, color=RED, lw=0.8, label='flights: %.3f per deg' % fit['slope_per_deg'])
    a.plot(x, model[2] * x, color='k', lw=0.8, ls='--', label='model, trimmed: %.3f' % model[2])
    a.set_xlabel('angle of attack less the flight\'s mean, deg')
    a.set_ylabel('lift coefficient less its mean')
    a.set_ylim(-0.11, 0.16)
    a.legend(loc='upper left', fontsize=5.5, ncol=1, handlelength=1.5, labelspacing=0.2)
    save(fig, 'calibration')


def landing():
    g = H['landing']
    d = -np.array(g['togo'])
    on = np.array(g['mains']) > 0
    i = int(np.argmax(on))
    fig, ax = plt.subplots(1, 4, figsize=(7.0, 1.95), gridspec_kw=dict(wspace=0.5))
    k = (d > -9000) & (np.arange(len(d)) <= i + 2)
    ax[0].plot(d[k] / 1000, np.array(g['wh'])[k], color=BLUE)
    ax[0].plot(d[k] / 1000, np.maximum(0, -d[k] * np.tan(np.radians(4.45))), color=GREY, lw=0.6, ls='--')
    ax[0].set_ylabel('wheel height, ft')
    ax[1].plot(d[k] / 1000, np.array(g['keas'])[k], color=BLUE)
    ax[1].plot([-8, d[i] / 1000], [133, 130], 'o', color=RED, mfc='white', mew=0.7)
    ax[1].set_ylabel('KEAS')
    ax[2].plot(d[k] / 1000, np.array(g['theta'])[k], color=BLUE, label='pitch')
    ax[2].plot(d[k] / 1000, 10 * np.array(g['spoiler'])[k], color=GREEN, lw=0.7, label='spoilers x 10')
    ax[2].plot([-8, d[i] / 1000], [0.05, 2.4], 'o', color=RED, mfc='white', mew=0.7)
    ax[2].set_ylabel('deg')
    ax[2].legend(loc='center left', fontsize=6)
    r = np.arange(len(d)) >= i
    ax[3].plot((d[r] - d[i]) / 1000, np.array(g['vg'])[r], color=BLUE, label='model')
    v0 = 120 * 1.6878
    s = (v0 ** 2 - (np.linspace(120, 50, 10) * 1.6878) ** 2) / (2 * 0.235 * 32.174)
    s0 = float(np.interp(120, np.array(g['vg'])[r][::-1], (d[r] - d[i])[::-1]))
    ax[3].plot((s0 + s) / 1000, np.linspace(120, 50, 10), color=RED, lw=0.8, ls='--', label='measured: 0.235 g')
    ax[3].set_ylabel('ground speed, kt')
    ax[3].set_xlabel('1000 ft past touchdown', fontsize=7)
    ax[3].legend(loc='lower left', fontsize=6)
    for a in ax[:3]:
        a.set_xlabel('1000 ft past the aim', fontsize=7)
    save(fig, 'landing')


def laws():
    fig, ax = plt.subplots(1, 3, figsize=(7.0, 2.1), gridspec_kw=dict(wspace=0.38))
    for (name, s), col in zip(H['steps'].items(), (BLUE, GREEN, ORANGE)):
        ax[0].plot(s['pitch']['t'], s['pitch']['y'], color=col, label=name)
        ax[1].plot(s['bank']['t'], s['bank']['y'], color=col, label='%s, to %.1f deg' % (name, s['bank']['to']))
        ax[2].plot(s['heading']['t'], np.array(s['heading']['psi']) / s['heading']['turn'], color=col, label='%s: bank %.0f deg' % (name, np.abs(s['heading']['phi']).max()))
    for a, yl in zip(ax, ('pitch attitude, of a 2 deg step', 'bank, of the step', 'heading, of the change')):
        a.axhline(1, color='0.3', lw=0.5)
        a.set_xlabel('s')
        a.set_ylabel(yl)
        a.legend(loc='lower right', fontsize=6)
    ax[2].set_xlim(0, 300)
    save(fig, 'laws')


def flight():
    g = H['flight']
    lat, lon = np.array(g['lat']), np.array(g['lon'])
    north = (lat - lat[0]) * 60.0
    east = (lon - lon[0]) * 60.0 * np.cos(np.radians(lat[0]))
    item = np.array(g['item'])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 2.5), gridspec_kw=dict(width_ratios=[1.0, 1.5], wspace=0.25))
    names = ['taxi', 'takeoff', 'route', 'landing', 'taxi']
    cols = [GREY, RED, BLUE, GREEN, GREY]
    for k in range(5):
        m = item == k
        if m.any():
            a1.plot(east[m], north[m], color=cols[k], lw=1.2 if k in (2, 3) else 2.0, label=names[k] if k < 4 else None)
    a1.set_aspect('equal')
    a1.set_xlabel('nmi east of the stand')
    a1.set_ylabel('nmi north')
    a1.legend(loc='lower right', fontsize=6)
    t = np.array(g['t']) / 60
    a2.plot(t, np.array(g['alt']) / 1000, color=BLUE, label='height, 1000 ft')
    a2.set_xlabel('minutes')
    a2.set_ylabel('height, 1000 ft')
    b = a2.twinx()
    b.plot(t, g['kcas'], color=ORANGE, lw=0.8, label='KCAS')
    b.plot(t, np.abs(g['phi']), color=GREEN, lw=0.6, label='bank, deg')
    b.set_ylabel('KCAS; bank, deg')
    b.grid(False)
    h1, l1 = a2.get_legend_handles_labels()
    h2, l2 = b.get_legend_handles_labels()
    a2.legend(h1 + h2, l1 + l2, loc='upper right', fontsize=6)
    save(fig, 'flight')


def record():
    """The highest the model flies, tanks run dry (results/record.json, mkrecord.py from fdm/scenario_record.py)."""
    g = json.load(open(os.path.join(R, 'record.json')))
    t, alt, w = np.array(g['t_h']), np.array(g['alt_ft']) / 1000.0, np.array(g['weight_lb']) / 1000.0
    r = g['record']
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(3.4, 3.3), sharex=True, gridspec_kw=dict(height_ratios=[2.2, 1.0], hspace=0.08))
    a1.plot(t, alt, color=BLUE, label='height')
    a1.axhline(65.0, color=GREY, lw=0.6, ls='--')
    a1.text(1.0, 66.0, 'NASA\'s maximum, 65,000 ft', color=GREY, fontsize=6, va='bottom')
    a1.plot(r['t_h'], r['alt_ft'] / 1000.0, 'o', color=RED, ms=4)
    a1.annotate('%s ft at %.1f h, tanks empty' % (format(r['alt_ft'], ','), r['t_h']), xy=(r['t_h'], r['alt_ft'] / 1000.0), xytext=(r['t_h'] - 1.5, 74.0), fontsize=6.5, color=RED, ha='right', va='center',
                arrowprops=dict(arrowstyle='-', color=RED, lw=0.5))
    a1.axvline(g['engine_out_h'], color=RED, lw=0.5, ls=':')
    a1.set_ylabel('height, 1000 ft')
    a1.set_ylim(0, 78)
    b = a1.twinx()
    b.plot(t, w, color=GREEN, lw=0.8)
    b.set_ylabel('weight, 1000 lb', color=GREEN)
    b.set_ylim(10, 28)
    b.grid(False)
    a1.text(g['engine_out_h'] - 0.4, 26, 'engine out,\nglide, landing', color=RED, fontsize=6, ha='right', va='center')
    a2.plot(g['margin_t_h'], g['margin_median_deg'], color=BLUE, lw=0.9, label='median')
    a2.plot(g['margin_t_h'], g['margin_min_deg'], color=BLUE, lw=0.6, ls='--', label='least')
    a2.legend(loc='upper right', fontsize=6)
    a2.axhline(0, color=GREY, lw=0.6)
    a2.set_ylabel('angle-of-attack\nmargin, deg')
    a2.set_ylim(-0.1, 1.0)
    a2.set_xlabel('hours after take-off')
    a2.set_xlim(0, 41)
    save(fig, 'record')


def failures():
    fig, ax = plt.subplots(1, 3, figsize=(7.0, 2.3), gridspec_kw=dict(wspace=0.34))
    n = H['navigator']
    ax[0].plot(n['t'], n['wrong'], color=RED, lw=0.8, label='the failed navigator')
    ax[0].plot(n['t'], n['voted'], color=GREEN, label='what the laws take')
    ax[0].plot(n['t'], n['phi'], color=BLUE, ls='--', label='the aircraft\'s bank')
    if n['flagged'] is not None:
        ax[0].axvline(n['flagged'], color=GREY, lw=0.6, ls=':')
    ax[0].set_xlim(0, 25)
    ax[0].set_xlabel('s')
    ax[0].set_ylabel('roll, deg')
    ax[0].legend(loc='center right', fontsize=6)
    e = H['engine_out']
    ax[1].plot(e['east'], e['north'], color=BLUE)
    ax[1].plot(e['east'][0], e['north'][0], 'o', color=RED)
    c = np.radians(e['course'])
    ax[1].plot([-6 * np.sin(c), 2 * np.sin(c)], [-6 * np.cos(c), 2 * np.cos(c)], color='0.2', lw=2.0)
    ax[1].set_aspect('equal')
    ax[1].set_xlabel('nmi east of the aiming point')
    ax[1].set_ylabel('nmi north')
    t = np.array(e['t']) / 60
    ax[2].plot(t, np.array(e['alt']) / 1000, color=BLUE, label='height, 1000 ft')
    ax[2].plot(t, 10 * np.array(e['spoiler']), color=GREEN, lw=0.7, label='spoilers x 10')
    ax[2].axhline(e['elev'] / 1000, color='0.3', lw=0.5)
    ax[2].set_xlabel('minutes; the engine stops at 0.2')
    ax[2].legend(loc='upper right', fontsize=6)
    save(fig, 'failures')


def station():
    s = open(os.path.join(HERE, '..', '..', 'GlobalHawk', 'gcs', 'js', 'perfdata.js')).read()
    L = json.loads(re.search(r'const data = (\{.*\});', s).group(1))['landing']
    fig, a = plt.subplots(figsize=(3.3, 2.2))
    w = np.array(L['weight_lb']) / 1000
    for k, (e, col) in enumerate(zip(L['elev_ft'], (BLUE, GREEN))):
        a.plot(w, np.array(L['slow_ft'][k]) / 1000, 'o-', color=col, label='rollout ends, field at %.0f ft' % e)
        a.plot(w, np.array(L['touchdown_ft'][k]) / 1000, 'o--', color=col, mfc='white', lw=0.7, label='touchdown' if k == 0 else None)
    m = re.search(r'at (\d+) lb; under 15 kt (\d+) ft past the aiming point \(the flight model alone at that weight: (\d+) ft', open(os.path.join(R, 'phase9b_checks.txt'), errors='replace').read())
    if m:
        a.plot(float(m.group(1)) / 1000, float(m.group(2)) / 1000, '*', color=RED, ms=8, label='landed in FlightGear')
    a.set_xlabel('landing weight, 1000 lb')
    a.set_ylabel('1000 ft past the aiming point')
    a.set_ylim(0, 7.5)
    a.legend(loc='upper left', fontsize=6)
    save(fig, 'landing_roll')

def drift():
    """the flare's drift: where the first wheel lands against the line, by crosswind and weight, with and without the aim offset (results/flare_drift.json: mkstudy.py)"""
    D = json.load(open(os.path.join(R, 'flare_drift.json')))
    rows, fit = D['rows'], D['fit']
    fig, a = plt.subplots(figsize=(3.3, 2.5))
    cols = {12450: (ORANGE, 'o', '12\u2009450 lb'), 19100: (GREEN, 's', '19\u2009100 lb'), 26750: (BLUE, '^', '26\u2009750 lb')}
    xs = np.linspace(0, 40, 2)
    for w, (c, m, lab) in cols.items():
        a.plot(xs, fit['k'] * w / 1000.0 * xs, color=c, lw=0.7, alpha=0.8)
        for aim in (False, True):
            r = [q for q in rows if round(q['weight']) == w and q['aim'] == aim]
            a.plot([q['xw'] for q in r], [-q['x_td'] for q in r], m, color=c, mfc='white' if aim else c, mew=0.8, label=lab if not aim else None)
    a.axhline(0, color='0.3', lw=0.5)
    a.plot([], [], 'o', color=GREY, label='without the offset')
    a.plot([], [], 'o', color=GREY, mfc='white', mew=0.8, label='with the offset')
    a.set_xlabel('crosswind at the wheels, kt')
    a.set_ylabel('first wheel downwind of the line, ft')
    a.set_xlim(0, 40)
    a.legend(loc='upper left', fontsize=6)
    save(fig, 'drift')


def wingtips():
    """the wing tips in the landing's last seconds, the old landing law against the present one, on the confirmation set: rigid and with the wing's bending (results/lat_roll_loop.json)"""
    p = os.path.join(R, 'lat_roll_loop.json')
    if not os.path.exists(p):
        return
    e = json.load(open(p))['final']
    fig, ax = plt.subplots(1, 3, figsize=(7.0, 2.0), gridspec_kw=dict(wspace=0.38))
    for a, key, xl in ((ax[0], 'rigid', 'lowest tip height, rigid wing, ft'), (ax[1], 'flex', 'lowest tip height, bent wing, ft'), (ax[2], 'bank', 'bank at the first wheel, deg')):
        for lk, col, lab in (('law2', RED, 'old landing law'), ('law3', BLUE, 'present law')):
            v = np.sort(np.array(e[lk]['lists'][key]))
            a.plot(v, 100.0 * np.arange(1, len(v) + 1) / len(v), color=col, label=lab, drawstyle='steps-post')
        a.set_xlabel(xl, fontsize=7)
    ax[0].set_ylabel('share of flights below, %')
    ax[0].axvline(0, color='0.3', lw=0.6)
    ax[1].axvline(0, color='0.3', lw=0.6)
    ax[0].text(0.02, 0.97, 'the ground', transform=ax[0].transAxes, fontsize=6, va='top', color='0.3')
    ax[2].axvline(5.5, color='0.3', lw=0.6, ls='--')
    ax[2].text(5.4, 5, 'rigid tip\ncontact', fontsize=6, ha='right', color='0.3')
    ax[1].legend(loc='upper left', fontsize=6)
    save(fig, 'wingtips')


if __name__ == '__main__':
    os.makedirs(F, exist_ok=True)
    for fn in (geometry, engine, section, calibration, landing, laws, flight, record, failures, station, drift, wingtips):
        fn()
        print(fn.__name__, flush=True)
