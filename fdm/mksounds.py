#!/usr/bin/env python3
"""The aircraft's sounds: every bank made by PyWopWop and put together into GlobalHawk/Sounds.

    ~/git/PyWopWop/.venv/bin/python fdm/mksounds.py        a few minutes; needs PyWopWop (github.com/MrChillStorm/PyWopWop)
    ~/git/PyWopWop/.venv/bin/python fdm/mksounds.py merge  the banks already made, put together again

Banks: the engine (PyWopWop's turbofan: by fan speed, at three altitudes, inside and outside from three directions),
the wind on the nose bay's wall (by equivalent airspeed; its level and pitch follow the altitude), the tyres rolling
(by each wheel's speed), the gear in the airflow (by airspeed, while it is out) and each wheel's touchdown (its squeal
and its strut's thump, by the sink rate and slip the flight model holds for it: Systems/touchdown.xml). All inside loops share one gain
and all outside loops another, so their loudness against each other is the physics'.

The "inside" is the two cameras' views (the nose bay). FlightGear's own inside/outside switch is not used: the
cameras are not internal views (see Nasal/globalhawk.nas); every bank's section is put on the aircraft's property.
"""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PWW = os.path.expanduser(os.environ.get('PYWOPWOP', '~/git/PyWopWop'))
sys.path.insert(0, PWW)
from pywopwop import gear, turbofan, tyre, wind            # noqa: E402
from pywopwop.wind import _e, _ramp_e, _v                  # noqa: E402

OUT = os.path.join(HERE, '..', 'GlobalHawk', 'Sounds')
WORK = os.path.join(PWW, 'out', 'globalhawk')
INSIDE = '/sim/sound/pywopwop/inside'
G = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))['gear']
FT = 0.3048
WEIGHT_LB = 20000.0                  # for the tyres' load: between the landing and the take-off weights
NOSE_SHARE = 0.174                   # of the weight on the nose leg (fdm/data/mass.json)

# The wheels, in the aircraft's frame the jet's preset has (x forward from the nose's tip, y left, z up from the ground).
# Sizes: the main tyres are the Learjet 45's (22x5.75-12), the nose's the CF-5's (18x6.5-8), which the Global Hawk's
# legs were taken from (Janes, as the flight model's notes have it); two side by side on every leg.
SPRING = dict(nose=11636.0, main=22096.0)                  # lb/ft, the flight model's
TYRES = [
    dict(name='nose', gear=0, position=(-G['nose_x'] * FT, 0.0, 0.0), width_m=0.165, diameter_m=0.457, count=1,      # one wheel on the nose leg
         static_compression_ft=NOSE_SHARE * WEIGHT_LB / SPRING['nose']),
    dict(name='left_main', gear=1, position=(-G['main_x'] * FT, G['main_track'] / 2 * FT, 0.0), width_m=0.146, diameter_m=0.559, count=2,
         static_compression_ft=(1 - NOSE_SHARE) / 2 * WEIGHT_LB / SPRING['main']),
    dict(name='right_main', gear=2, position=(-G['main_x'] * FT, -G['main_track'] / 2 * FT, 0.0), width_m=0.146, diameter_m=0.559, count=2,
         static_compression_ft=(1 - NOSE_SHARE) / 2 * WEIGHT_LB / SPRING['main']),
]
# the legs in the airflow: each wheel pair as one wheel of its size, the strut's length the leg's (3-D model: 1.2 m)
LEGS = [dict(position=(t['position'][0], t['position'][1], t['diameter_m'] / 2), wheel_m=t['diameter_m'], strut_m=0.09, strut_length_m=1.2 if 'main' in t['name'] else 0.8)
        for t in TYRES]
# For the touchdown: the tyres as PyWopWop's touchdown model takes them (the flight model's WHEELS, fdm/genghawk.py, have
# the same sizes and weights; estimated), their squeal the P2006T's recorded one moved to their sizes, as the MV-22B's
import genghawk as GH                 # noqa: E402
LBFT, LBFTS = 14.5939, 14.5939        # N/m per lb/ft, N s/m per lb/ft/s
for _name, _w in (('22x5.75-12', GH.WHEELS['main']), ('18x6.5-8', GH.WHEELS['nose'])):
    tyre.TYRE_TYPES[_name] = dict(diameter_m=_w['diameter_m'], width_m=_w['width_m'], rolling_radius_m=_w['rolling_radius_m'], tyre_kg=_w['tyre_kg'],
                                  wheel_kg=_w['wheel_kg'], unsprung_kg=3.0 * (_w['tyre_kg'] + _w['wheel_kg']), tyre_stiffness=600e3)
    tyre.SQUEAL[_name] = tyre._scaled_squeal('6.00-6', _w['diameter_m'])
GROUPS = [
    dict(name='main', tyre_type='22x5.75-12', damping=2754.0 * LBFTS, spring=SPRING['main'] * LBFT, static_load_n=(1 - NOSE_SHARE) / 2 * WEIGHT_LB * 4.4482,
         tyres=2, wheels=[dict(gear=1, position=TYRES[1]['position']), dict(gear=2, position=TYRES[2]['position'])]),
    dict(name='nose', tyre_type='18x6.5-8', damping=1297.0 * LBFTS, spring=SPRING['nose'] * LBFT, static_load_n=NOSE_SHARE * WEIGHT_LB * 4.4482,
         tyres=1, wheels=[dict(gear=0, position=TYRES[0]['position'])]),
]
SLIPS_KT = (40.0, 60.0, 80.0, 100.0, 120.0, 140.0)          # the model lands at 100 to 140 kt over the ground
AIRFRAME = 'p2006t'                  # whose structure's transfer the tyres' roll takes inside, scaled by mass (PyWopWop's STRUCTURES)
AIRFRAME_KG = WEIGHT_LB * 0.4536
WIND_KT = (30.0, 60.0, 100.0, 150.0, 200.0, 250.0)
GEAR_KT = (50.0, 80.0, 110.0, 140.0, 170.0, 200.0)


AIRFRAME_KT = (90.0, 110.0, 130.0, 150.0, 170.0, 190.0)      # equivalent airspeed: the aircraft flies in this range at every height


def airframe_glider():
    """the aircraft as PyWopWop's glider model takes one (its datum: X aft from the nose, Y right, Z up from the wing):
    the wing from fdm/data/geometry.json on the LRN 1015, the two V-tail panels laid flat as a tailplane of their true
    size (their sound does not care which way they lean), no fin to speak of, the spoilers as its airbrakes"""
    from pywopwop.glider import Glider
    import math
    g = json.load(open(os.path.join(HERE, 'data', 'geometry.json')))
    w, t, fu = g['wing'], g['vtail'], g['fuselage']
    half = w['span'] / 2 * FT
    hw = fu['max_width'] / 2 * FT
    ys = [0.0, hw] + [hw + (half - hw) * k / 10.0 for k in range(1, 11)]
    chord = [(w['root_chord_centreline'] + (w['tip_chord'] - w['root_chord_centreline']) * y / half) * FT for y in ys]
    x_le = [w['le_centreline_x'] * FT + y * math.tan(math.radians(w['sweep_le_deg'])) for y in ys]
    edges = [hw + (half - hw) * k / 12.0 for k in range(13)]
    prof = fu['profile']
    fx = [p['x'] * FT for p in prof]
    top = [(p['z_top'] - w['z']) * FT for p in prof]
    bot = [(p['z_bottom'] - w['z']) * FT for p in prof]
    width = [min(fu['max_width'] * FT, 0.75 * (a - b)) for a, b in zip(top, bot)]
    return Glider(
        name='RQ-4A Global Hawk (airframe)', mass_kg=AIRFRAME_KG, wing_area=w['area_reference'] * FT * FT, span=w['span'] * FT, dihedral_deg=0.0,
        fuselage_half_width=hw, cg_x=g['wing']['mac_quarter_x'] * FT,
        wing=dict(y=ys, chord=chord, x_le=x_le, strip_edges=edges, root_section='lrn1015', tip_section='lrn1015', kink_y=half,
                  incidence_y=[0.0, half], incidence_deg=[3.0, 3.0 + w['twist_root_to_tip_deg']], te_thickness=0.002),
        ailerons=dict(y=[0.55 * half, 0.95 * half], chord_fraction=0.25, up_deg=20.0, down_deg=20.0),
        airbrakes=dict(y=[0.18 * half, 0.50 * half], height=0.14, x_c=0.69),
        tailplane=dict(span=2 * t['panel_span'] * FT, area=t['area_total'] * FT * FT, root_chord=t['root_chord'] * FT, tip_chord=t['tip_chord'] * FT,
                       x_le_root=t['root_le_x'] * FT, x_le_tip=t['tip_le_x'] * FT, z=(t['quarter_z'] - w['z']) * FT, incidence_deg=0.0,
                       section='naca0010', elevator_chord_fraction=0.30, elevator_up_deg=20.0, elevator_down_deg=20.0),
        fin=dict(area=0.01, z_bottom=0.20, z_top=0.26, x_le_bottom=12.0, x_le_top=12.0, x_te=12.05, section='naca0010',
                 rudder_chord_fraction=0.3, rudder_deg=20.0),
        fuselage=dict(x=fx, top_z=top, bottom_z=bot, width=width, section_exponent=2.3, nose_x=0.0, transition_x=0.3, canopy_x=[0.5, 1.5],
                      canopy_half_angle_deg=10.0, canopy_surface_mass=4.0, canopy_thickness=0.004, canopy_youngs=2e10),
        cockpit=dict(front=[1.2, 0.0, 0.0], rear=[1.2, 0.0, 0.0]), wheels=[])


def airframe_bank(out_dir, gain_db, distance=50.0, fs=48000.0, duration=15.0, progress=print):
    """the airframe's own sound outside, to the side: loops at sea level by airspeed, clean, and what the spoilers
    add fully out as a layer of its own"""
    import numpy as np
    from pywopwop.glider import GliderCondition, render_glider
    from pywopwop.model import Observer
    from pywopwop.synth import write_wav
    g = airframe_glider()
    os.makedirs(out_dir, exist_ok=True)
    o = Observer('side', 90.0, 0.0, distance)
    k = 10 ** (gain_db / 20.0)
    files = []
    for i, v in enumerate(AIRFRAME_KT):
        r = render_glider(g, GliderCondition(airspeed_kt=v, brakes=1.0), o, fs, duration, seed=31 + i)
        lv = r.levels()
        for layer in ('airframe', 'brakes'):
            x = r.signals.get('layer/' + layer)
            if x is None:
                continue
            fn = 'airframe_%s_%gkt_side.wav' % (layer, v)
            if np.abs(x).max() * k > 10 ** (-0.1 / 20.0):
                raise ValueError('%s would peak at %+.1f dBFS at this gain' % (fn, 20 * np.log10(np.abs(x).max() * k)))
            write_wav(os.path.join(out_dir, fn), x, fs, 16, k, seed=int(v))
            files.append(dict(file=fn, layer=layer, airspeed_kt=v, oaspl_db=round(lv['layer/' + layer]['oaspl'], 2), dba=round(lv['layer/' + layer]['dba'], 2)))
        progress('  airframe %3.0f kt: clean %.1f dBA, spoilers add %.1f dBA' % (v, lv['layer/airframe']['dba'], lv.get('layer/brakes', {}).get('dba', float('nan'))))
    m = dict(aircraft=g.name, generator='pywopwop glider (the airframe)', exterior_distance_m=distance, gain_db=dict(exterior=gain_db), files=files)
    json.dump(m, open(os.path.join(out_dir, 'manifest.json'), 'w'), indent=1)
    return m


def airframe_xml(manifest, sound_dir='Sounds/pywopwop'):
    """the airframe's loops outside: cross-faded by equivalent airspeed; at altitude louder by the density ratio to the
    -1/4 (see the plan); the spoilers' layer with how far they are out"""
    eas = '<property>/velocities/equivalent-kt</property>'
    sigma = _e('div', '<property>/environment/density-slugft3</property>', _v(0.00237689))
    alt = _e('pow', _e('max', sigma, _v(0.02)), _v(-0.25))
    out = []
    for layer in ('airframe', 'brakes'):
        files = sorted([f for f in manifest['files'] if f['layer'] == layer], key=lambda f: f['airspeed_kt'])
        pts = [f['airspeed_kt'] for f in files]
        for i, f in enumerate(files):
            lo, hi = (pts[i - 1] if i else 0.5 * pts[0]), (pts[i + 1] if i + 1 < len(pts) else None)
            w = [_ramp_e(eas, lo, pts[i])] + ([_ramp_e(eas, hi, pts[i])] if hi else [])
            cond = [f'<not><property>{INSIDE}</property></not>', f'<greater-than>{eas}<value>{lo:g}</value></greater-than>']
            if hi:
                cond.append(f'<less-than>{eas}<value>{hi:g}</value></less-than>')
            extra = []
            if layer == 'brakes':
                cond.append('<greater-than><property>/fdm/jsbsim/ctl/spoiler-norm</property><value>0.02</value></greater-than>')
                extra = ['<property>/fdm/jsbsim/ctl/spoiler-norm</property>']
            vol = _e('product', alt, _e('sqrt', _e('product', *w) if len(w) > 1 else w[0]), *extra)
            out.append(f"\t\t<airframe>\n\t\t\t<name>pww-airframe-{layer}-{pts[i]:g}</name>\n\t\t\t<mode>looped</mode>\n\t\t\t<path>{sound_dir}/{f['file']}</path>\n"
                       f"\t\t\t<condition><and>{''.join(cond)}</and></condition>\n\t\t\t<volume><expression>{vol}</expression></volume>\n"
                       f"\t\t\t<reference-dist>{manifest['exterior_distance_m']:g}</reference-dist>\n\t\t\t<max-dist>3000</max-dist>\n\t\t</airframe>\n")
    return '<PropertyList>\n\t<fx>\n' + ''.join(out) + '\t</fx>\n</PropertyList>\n'


def gear_xml(manifest, sound_dir='Sounds/pywopwop'):
    """the gear's loops: cross-faded by true airspeed, with the air's density and how far the gear is out"""
    tas = '<property>/fdm/jsbsim/velocities/vtrue-kts</property>'
    pos = '<property>/fdm/jsbsim/gear/gear-pos-norm</property>'
    sigma = _e('div', '<property>/environment/density-slugft3</property>', _v(0.00237689))
    out = []
    for view in ('cockpit', 'side'):
        files = sorted([f for f in manifest['files'] if f['view'] == view], key=lambda f: f['airspeed_kt'])
        pts = [f['airspeed_kt'] for f in files]
        for i, f in enumerate(files):
            lo, hi = (pts[i - 1] if i else 0.2 * pts[0]), (pts[i + 1] if i + 1 < len(pts) else None)
            w = [_ramp_e(tas, lo, pts[i])] + ([_ramp_e(tas, hi, pts[i])] if hi else [])
            cond = [f'<property>{INSIDE}</property>' if view == 'cockpit' else f'<not><property>{INSIDE}</property></not>',
                    f'<greater-than>{pos}<value>0.01</value></greater-than>', f'<greater-than>{tas}<value>{lo:g}</value></greater-than>']
            if hi:
                cond.append(f'<less-than>{tas}<value>{hi:g}</value></less-than>')
            vol = _e('product', sigma, _e('sqrt', _e('product', *w) if len(w) > 1 else w[0]), pos)
            out.append(f"\t\t<gearair>\n\t\t\t<name>pww-gear-{pts[i]:g}-{view}</name>\n\t\t\t<mode>looped</mode>\n\t\t\t<path>{sound_dir}/{f['file']}</path>\n"
                       f"\t\t\t<condition><and>{''.join(cond)}</and></condition>\n\t\t\t<volume><expression>{vol}</expression></volume>\n"
                       + ('' if view == 'cockpit' else f"\t\t\t<reference-dist>{manifest['exterior_distance_m']:g}</reference-dist>\n\t\t\t<max-dist>3000</max-dist>\n")
                       + '\t\t</gearair>\n')
    return '<PropertyList>\n\t<fx>\n' + ''.join(out) + '\t</fx>\n</PropertyList>\n'


def body(xml):
    """a bank's section without its wrapping, its inside/outside switch put on the aircraft's property"""
    m = re.search(r'<fx>\n(.*)\t</fx>', xml, re.S)
    s = m.group(1)
    return s.replace('<property>sim/current-view/internal</property>', f'<property>{INSIDE}</property>')


def build():
    """every bank, into the work folder; returns the manifests the merge needs"""
    jet = turbofan.load_jet('globalhawk')
    shutil.rmtree(WORK, ignore_errors=True)          # nothing left over from an earlier build
    quiet = lambda *a: None
    peak = dict(inside=-1.0, outside=-1.0)
    while True:
        # the engine sets the two gains; if another bank would clip at them, everything is made again quieter
        print('engine, loudest loops at %.0f dBFS inside, %.0f outside' % (peak['inside'], peak['outside']), flush=True)
        eng = turbofan.make_jet_bank('globalhawk', os.path.join(WORK, 'engine'), peak_dbfs=peak, progress=quiet)
        gains = dict(cockpit=eng['gain_db']['inside'], exterior=eng['gain_db']['outside'])
        try:
            wnd = wind.make_wind_bank(jet, os.path.join(WORK, 'wind'), speeds=WIND_KT, gain_db=gains['cockpit'], progress=quiet)
            tyr = tyre.make_tyre_bank(jet, os.path.join(WORK, 'tyres'), TYRES, gains, AIRFRAME, airframe_kg=AIRFRAME_KG, progress=quiet)
            gr = gear.make_gear_bank(jet, os.path.join(WORK, 'gear'), LEGS, gains, speeds=GEAR_KT, progress=quiet)
            af = airframe_bank(os.path.join(WORK, 'airframe'), gains['exterior'], progress=print)
            td = tyre.make_touchdown_bank(jet, os.path.join(WORK, 'touchdown'), GROUPS, gains, AIRFRAME, slips=SLIPS_KT, airframe_kg=AIRFRAME_KG, progress=quiet)
            break
        except ValueError as e:
            m = re.search(r'peak at \+?(-?[\d.]+) dBFS', str(e))
            over = float(m.group(1)) if m else 3.0
            # which set it was: the inside loops' files are named cockpit, or it is the wind (inside only)
            which = 'outside' if ('_side' in str(e) and 'cockpit' not in str(e)) else 'inside'
            print('  too loud for the %s gain (%s): again %.0f dB quieter' % (which, e, over + 1.5), flush=True)
            peak[which] -= over + 1.5
    return dict(gains=gains, wind=wnd, tyres=tyr, gear=gr, touchdown=td, airframe=af)


def start_layer(engine_xml):
    """The start, before the fan turns fast enough for its loops (they begin at 660 rpm): the high-pressure rotor
    comes up first, and its whine is the idle core loop played from the flight model's engine/core-spool, fading
    as the fan's loops come in. No recording of a Global Hawk's start was found: the lead of the core over the
    fan is the flight model's assumption, and no starter or igniter is heard."""
    out = []
    for where in ('inside', 'outside'):
        m = re.search(r'\t\t<engine>\n\t\t\t<name>(pww-jet-core-0-[\d.]+-%s)</name>.*?\t\t</engine>\n' % where, engine_xml, re.S)
        e = m.group(0).replace(m.group(1), 'start-core-' + where)
        view = '<property>%s</property>' % INSIDE if where == 'inside' else '<not><property>%s</property></not>' % INSIDE
        fan, core = '<property>/fdm/jsbsim/engine/fan-rpm</property>', '<property>/fdm/jsbsim/engine/core-spool</property>'
        lo, hi = (float(x) for x in re.findall(r'<value>([\d.]+)</value>', re.search(r'<condition>.*?</condition>', e).group(0))[:2])
        e = re.sub(r'<condition>.*?</condition>', '<condition><and>%s<greater-than>%s<value>0.03</value></greater-than><less-than>%s<value>%g</value></less-than></and></condition>'
                   % (view, core, fan, 0.5 * (lo + hi)), e)
        e = re.sub(r'<volume>.*?</volume>', '<volume><expression><product><value>0.7</value><sqrt><product><clip>%s<clipMin>0</clipMin><clipMax>1</clipMax></clip>'
                   '<clip><difference><value>1</value><div><difference>%s<value>%g</value></difference><value>%g</value></div></difference><clipMin>0</clipMin><clipMax>1</clipMax></clip>'
                   '</product></sqrt></product></expression></volume>\n\t\t\t<pitch><property>/fdm/jsbsim/engine/core-spool</property><factor>0.65</factor><offset>0.35</offset></pitch>'
                   % (core, fan, lo, 0.5 * (hi - lo)), e)
        out.append(e)
    return ''.join(out)


def main():
    if 'merge' in sys.argv[1:]:
        # the banks as they stand in the work folder, put together again (a change to this file's own sounds)
        load = lambda name, mf='manifest.json': json.load(open(os.path.join(WORK, name, mf)))
        eng = load('engine')
        made = dict(gains=dict(cockpit=eng['gain_db']['inside'], exterior=eng['gain_db']['outside']), wind=load('wind'), tyres=load('tyres'), gear=load('gear'),
                    touchdown=load('touchdown', 'touchdown.json'), airframe=load('airframe'))
    else:
        made = build()
    gains, wnd, tyr, gr, td, af = (made[k] for k in ('gains', 'wind', 'tyres', 'gear', 'touchdown', 'airframe'))
    shutil.rmtree(os.path.join(OUT, 'pywopwop'), ignore_errors=True)
    os.makedirs(os.path.join(OUT, 'pywopwop'))
    n = 0
    for name in ('engine', 'wind', 'tyres', 'gear', 'touchdown', 'airframe'):
        d = os.path.join(WORK, name)
        for f in os.listdir(d):
            if f.endswith('.wav'):
                shutil.copy(os.path.join(d, f), os.path.join(OUT, 'pywopwop', f))
                n += 1
        mf = 'touchdown.json' if name == 'touchdown' else 'manifest.json'
        shutil.copy(os.path.join(d, mf), os.path.join(OUT, 'pywopwop', name + '-manifest.json'))
    engine = body(open(os.path.join(WORK, 'engine', 'pywopwop-jet.xml')).read())
    parts = [engine, start_layer(engine), body(open(os.path.join(WORK, 'wind', 'pywopwop-wind.xml')).read()),
             body(open(os.path.join(WORK, 'tyres', 'pywopwop-tyres.xml')).read()), body(gear_xml(gr)),
             body(open(os.path.join(WORK, 'touchdown', 'pywopwop-touchdown.xml')).read()), body(airframe_xml(af))]
    with open(os.path.join(OUT, 'globalhawk-sound.xml'), 'w') as fh:
        fh.write('<?xml version="1.0"?>\n<!-- Made by fdm/mksounds.py from PyWopWop\'s banks: the engine, the wind, the tyres, the gear in the airflow, the touchdowns, the airframe.\n'
                 '     Inside loops play in the two cameras\' views (' + INSIDE + '), outside loops in the others. -->\n<PropertyList>\n\t<fx>\n'
                 + ''.join(parts) + '\t</fx>\n</PropertyList>\n')
    import xml.etree.ElementTree as ET
    fx = ET.parse(os.path.join(OUT, 'globalhawk-sound.xml')).getroot().find('fx')
    missing = [s.find('path').text for s in fx if not os.path.exists(os.path.join(OUT, '..', s.find('path').text))]
    left = sum('current-view/internal' in ET.tostring(s, encoding='unicode') for s in fx)
    print('%d files, %d sounds; gains inside %.1f dB, outside %.1f dB; files missing: %d; sounds still on FlightGear\'s internal switch: %d' % (
        n, len(fx), gains['cockpit'], gains['exterior'], len(missing), left))
    for name, m in (('wind', wnd), ('tyres', tyr), ('gear', gr), ('touchdown', td), ('airframe', af)):
        lv = [f.get('dba', f.get('dba_exposure', 0.0)) for f in m['files']]
        print('  %-6s %3d loops, %.0f to %.0f dBA' % (name, len(lv), min(lv), max(lv)))


if __name__ == '__main__':
    main()
