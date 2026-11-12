#!/usr/bin/env python3
"""Generate the JSBSim model of the Global Hawk: GlobalHawk.xml and Systems/*.xml.

    python3 fdm/genghawk.py                  the model that ships, into GlobalHawk/
    python3 fdm/genghawk.py DIR --ref        the reference build (AeroSandbox's tables), into DIR

Everything comes from fdm/data: geometry.json, mass.json, engine.json and aero_tables.json (aerotables.py).

  aerodynamics   coefficient tables over angle of attack and Mach number, about the reference point
  engine         not JSBSim's turbine: system channels. Maximum and idle thrust and fuel flow from the cycle model's
                 tables over pressure altitude, Mach number and the temperature's offset from standard; a lag for the
                 spool; thrust applied as an external force on the nacelle's axis
  fuel           six tanks; the fuel-management channel draws from all of them in proportion to their contents,
                 which keeps the centre of gravity where the tank layout puts it. The engine stops when they are dry
  controls       surface angles straight from the commands for now: the flight laws come later
  gear           three contact points with estimated springs, enough to stand on

Properties of ours live under ctl/ (surfaces), engine/ and fuel/.
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import laws                                      # noqa: E402

D = os.path.join(HERE, 'data')
G = json.load(open(os.path.join(D, 'geometry.json')))
M = json.load(open(os.path.join(D, 'mass.json')))
ENG = json.load(open(os.path.join(D, 'engine.json')))
FLEX = json.load(open(os.path.join(D, 'flex.json')))
_cal = os.path.join(D, 'calibration.json')
# what the calibration against flight data adds: fdm/data/README.md, "Calibration"
CAL = json.load(open(_cal)) if os.path.exists(_cal) else dict(drag_increment=0.0, fuel_factor=1.0)
GEAR_DRAG = 0.0065                # gear down: a drag area of 3.5 ft2 on the wing area. An estimate
SPOILER_MAX_DEG = 45.0            # the real aero model's largest spoiler angle (Eaton and Woolf)
SPOILER_APPROACH_DEG = 30.0       # the setting the approach is taken to be flown at: an assumption
IN = 12.0
SURFACE_LIMIT_DEG = 20.0          # ailerons and ruddervators: an estimate
SPOOL_SECONDS = 2.0               # thrust lag: a class estimate, no data
# past the stall the tables go on as a flat plate, plainly: the autopilot stays far from it
FLAT = dict(alpha=[-90.0, -30.0, -15.0], CL=[0.0, -0.95, -0.55], CD=[1.3, 0.55, 0.20], Cm=[0.3, 0.15, 0.05])
FLAT_HI = dict(alpha=[20.0, 30.0, 90.0], CL=[0.75, 0.95, 0.0], CD=[0.35, 0.60, 1.3], Cm=[-0.15, -0.20, -0.35])


def table2(rows, cols, data, row_prop, col_prop, indent='          '):
    """A JSBSim table: data[row][col]."""
    s = ['<table>', '  <independentVar lookup="row">%s</independentVar>' % row_prop,
         '  <independentVar lookup="column">%s</independentVar>' % col_prop, '  <tableData>',
         '          ' + ' '.join('%10.4g' % c for c in cols)]
    for r, line in zip(rows, data):
        s.append('  %8.4g ' % r + ' '.join('%10.6g' % v for v in line))
    s += ['  </tableData>', '</table>']
    return '\n'.join(indent + x for x in s)


def table1(xs, ys, prop, indent='          '):
    s = ['<table>', '  <independentVar lookup="row">%s</independentVar>' % prop, '  <tableData>']
    s += ['    %10.6g %12.6g' % (x, y) for x, y in zip(xs, ys)]
    s += ['  </tableData>', '</table>']
    return '\n'.join(indent + x for x in s)


def table3(rows, cols, tabs, data, row_prop, col_prop, tab_prop, indent='          '):
    """data[tab][row][col]."""
    s = ['<table>', '  <independentVar lookup="row">%s</independentVar>' % row_prop,
         '  <independentVar lookup="column">%s</independentVar>' % col_prop,
         '  <independentVar lookup="table">%s</independentVar>' % tab_prop]
    for tb, block in zip(tabs, data):
        s.append('  <tableData breakPoint="%g">' % tb)
        s.append('          ' + ' '.join('%10.4g' % c for c in cols))
        for r, line in zip(rows, block):
            s.append('  %8.4g ' % r + ' '.join('%10.6g' % v for v in line))
        s.append('  </tableData>')
    s.append('</table>')
    return '\n'.join(indent + x for x in s)


def by_alpha(t, name, full=False):
    """Table data [alpha][mach] from the sampled [mach][alpha]; full adds the flat-plate rows at both ends."""
    a = np.array(t[name]).T
    if not full:
        return t['alpha_d'], a.tolist()
    lo = np.repeat(np.array(FLAT[name])[:, None], a.shape[1], 1)
    hi = np.repeat(np.array(FLAT_HI[name])[:, None], a.shape[1], 1)
    return FLAT['alpha'] + t['alpha'] + FLAT_HI['alpha'], np.vstack([lo, a, hi]).tolist()


def fn(name, body, desc=''):
    return '      <function name="%s">\n%s%s\n      </function>' % (
        name, ('        <description>%s</description>\n' % desc) if desc else '', body)


def product(*terms, indent='        '):
    return indent + '<product>\n' + '\n'.join(terms) + '\n' + indent + '</product>'


def prop(p, indent='          '):
    return indent + '<property>%s</property>' % p


def aerodynamics(t):
    A, MACH = 'aero/alpha-deg', 'velocities/mach'
    qs = [prop('aero/qbar-psf'), prop('metrics/Sw-sqft')]
    qsb = qs + [prop('metrics/bw-ft')]
    qsc = qs + [prop('metrics/cbarw-ft')]

    def tab(name, full=False):
        rows, data = by_alpha(t, name, full)
        return table2(rows, t['mach'], data, A, MACH)

    def term(axis_name, desc, scale, name, *factors, full=False):
        return fn('aero/%s' % axis_name, product(*(scale + [tab(name, full)] + [prop(f) for f in factors])), desc)
    dcd = table2(t['pitch_d'], t['mach'], np.array(t['dCD_de']).T.tolist(), 'ctl/pitch-deg', MACH)
    ge = lambda n: table2(t['ge_alpha'], t['ge_agl'], t[n], A, 'aero/wheel-height-ft')
    spoil = lambda cal: product(*(qs + [prop(cal), prop('ctl/spoiler-norm')]))
    axes = [
        ('LIFT', [term('lift-basic', 'lift against angle of attack and Mach', qs, 'CL', full=True),
                  term('lift-pitch-rate', 'lift due to pitch rate', qs, 'CLq', 'aero/ci2vel', 'velocities/q-aero-rad_sec'),
                  term('lift-ruddervators', 'lift due to the ruddervators together', qs, 'CL_de', 'ctl/pitch-deg'),
                  fn('aero/lift-ground-effect', product(*(qs + [ge('dCL_ge')])), 'lift gained near the ground'),
                  fn('aero/lift-spoilers', spoil('cal/spoiler-lift'), 'lift dumped by the spoilers (cal/spoiler-lift is negative)')]),
        ('DRAG', [term('drag-basic', 'drag against angle of attack and Mach, controls neutral', qs, 'CD', full=True),
                  fn('aero/drag-ruddervators', product(*(qs + [dcd])), 'drag change with the ruddervators together (trim drag)'),
                  fn('aero/drag-calibration', product(*(qs + [prop('cal/drag-increment')])),
                     'a constant drag coefficient added by the calibration against measured climb and cruise-climb'),
                  fn('aero/drag-ground-effect', product(*(qs + [ge('dCD_ge')])), 'induced drag lost near the ground'),
                  fn('aero/drag-gear', product(*(qs + [prop('ctl/gear-norm'), '          <value>%g</value>' % GEAR_DRAG])), 'gear down'),
                  fn('aero/drag-spoilers', spoil('cal/spoiler-drag'), 'drag of the spoilers')]),
        ('SIDE', [term('side-sideslip', 'side force due to sideslip', qs, 'CYb', 'aero/beta-deg'),
                  term('side-ruddervators', 'side force due to the ruddervators against each other', qs, 'CY_dr', 'ctl/yaw-deg')]),
        ('ROLL', [term('roll-sideslip', 'roll due to sideslip', qsb, 'Clb', 'aero/beta-deg'),
                  term('roll-damping', 'roll due to roll rate', qsb, 'Clp', 'aero/bi2vel', 'velocities/p-aero-rad_sec'),
                  term('roll-yaw-rate', 'roll due to yaw rate', qsb, 'Clr', 'aero/bi2vel', 'velocities/r-aero-rad_sec'),
                  term('roll-ailerons', 'roll due to the ailerons (ctl/aileron-deg: right trailing edge down)', qsb, 'Cl_da', 'ctl/aileron-deg'),
                  term('roll-ruddervators', 'roll due to the ruddervators against each other', qsb, 'Cl_dr', 'ctl/yaw-deg'),
                  fn('aero/roll-sideslip-bending', product(*(qsb + [table1([r['mach'] for r in FLEX['roll_due_to_sideslip']], [r['per_ft_per_deg'] for r in FLEX['roll_due_to_sideslip']], MACH), prop('flex/tip-deflection-ft'), prop('aero/beta-deg'), prop('flex/enable')])),
                     'roll due to sideslip from the dihedral of the bent wing, in proportion to its tip deflection')]),
        ('PITCH', [term('pitch-basic', 'pitching moment against angle of attack and Mach', qsc, 'Cm', full=True),
                   term('pitch-damping', 'pitch due to pitch rate', qsc, 'Cmq', 'aero/ci2vel', 'velocities/q-aero-rad_sec'),
                   term('pitch-ruddervators', 'pitch due to the ruddervators together', qsc, 'Cm_de', 'ctl/pitch-deg'),
                   fn('aero/pitch-ground-effect', product(*(qsc + [ge('dCm_ge')])), 'pitching moment near the ground')]),
        ('YAW', [term('yaw-sideslip', 'yaw due to sideslip', qsb, 'Cnb', 'aero/beta-deg'),
                 term('yaw-roll-rate', 'yaw due to roll rate', qsb, 'Cnp', 'aero/bi2vel', 'velocities/p-aero-rad_sec'),
                 term('yaw-damping', 'yaw due to yaw rate', qsb, 'Cnr', 'aero/bi2vel', 'velocities/r-aero-rad_sec'),
                 term('yaw-ailerons', 'yaw due to the ailerons', qsb, 'Cn_da', 'ctl/aileron-deg'),
                 term('yaw-ruddervators', 'yaw due to the ruddervators against each other', qsb, 'Cn_dr', 'ctl/yaw-deg')]),
    ]
    out = ['  <aerodynamics>']
    for axis, fns in axes:
        out.append('    <axis name="%s">' % axis)
        out += fns
        out.append('    </axis>')
    out.append('  </aerodynamics>')
    return '\n'.join(out)


def loc(tag, x, y, z, indent='      '):
    return '%s<%s unit="IN"><x>%.2f</x><y>%.2f</y><z>%.2f</z></%s>' % (indent, tag, x * IN, y * IN, z * IN, tag)


def main_file(t, name):
    w, gear, nac = G['wing'], G['gear'], G['nacelle']
    e, pay = M['empty'], M['payload']
    ref = t['reference_point_ft']
    tanks = '\n'.join('''    <tank type="FUEL">   <!-- %s -->
%s
      <capacity unit="LBS">%.1f</capacity>
      <contents unit="LBS">%.1f</contents>
      <density unit="LBS/GAL">6.7</density>
    </tank>''' % (tk['name'], loc('location', tk['x'], tk['y'], tk['z']), tk['capacity'], tk['capacity']) for tk in M['tanks'])
    w_main = 0.826 * 26750 / 2
    w_nose = 0.174 * 26750

    def contact(nm, x, y, load, defl, steer, group):
        k = load / defl
        c = 2 * 0.5 * np.sqrt(k * load / 32.174)
        return '''    <contact type="BOGEY" name="%s">
%s
      <static_friction>0.8</static_friction><dynamic_friction>0.5</dynamic_friction><rolling_friction>0.015</rolling_friction>
      <spring_coeff unit="LBS/FT">%.0f</spring_coeff>
      <damping_coeff unit="LBS/FT/SEC">%.0f</damping_coeff>
      <max_steer unit="DEG">%g</max_steer>
      <brake_group>%s</brake_group>
      <retractable>1</retractable>
    </contact>''' % (nm, loc('location', x, y, -defl), k, c, steer, group)
    def structure():
        pts = [('left wing tip', w['mac_le_x'] + 6.0, -w['span'] / 2, w['z']), ('right wing tip', w['mac_le_x'] + 6.0, w['span'] / 2, w['z']),
               ('nose', 1.0, 0, 3.0), ('tail', G['fuselage']['length'] - 0.5, 0, 5.3), ('belly', 15.0, 0, 1.7)]
        return ''.join('''\n    <contact type="STRUCTURE" name="%s">\n%s\n      <static_friction>0.6</static_friction><dynamic_friction>0.5</dynamic_friction>\n      <spring_coeff unit="LBS/FT">20000</spring_coeff>\n      <damping_coeff unit="LBS/FT/SEC">3000</damping_coeff>\n    </contact>''' % (nm, loc('location', x, y, z)) for nm, x, y, z in pts)
    return '''<?xml version="1.0"?>
<!-- Generated by fdm/genghawk.py (%s). Do not edit: change the generator or its data.
     NASA Global Hawk (RQ-4A), modelled from public data. Not made or endorsed by NASA or Northrop Grumman. -->
<fdm_config name="GlobalHawk" version="2.0" release="ALPHA">
  <fileheader>
    <author>fdm/genghawk.py</author>
    <description>NASA Global Hawk N872NA (RQ-4A), from public data; sources and choices in fdm/data/README.md</description>
  </fileheader>
  <metrics>
    <wingarea unit="FT2">%.1f</wingarea>
    <wingspan unit="FT">%.2f</wingspan>
    <chord unit="FT">%.3f</chord>
%s
%s
%s
  </metrics>
  <mass_balance>
    <ixx unit="SLUG*FT2">%.0f</ixx>
    <iyy unit="SLUG*FT2">%.0f</iyy>
    <izz unit="SLUG*FT2">%.0f</izz>
    <emptywt unit="LBS">%.1f</emptywt>
%s
    <pointmass name="payload">
      <weight unit="LBS">%.1f</weight>
%s
    </pointmass>
  </mass_balance>
  <ground_reactions>
%s
%s
%s
  </ground_reactions>
  <propulsion>
%s
  </propulsion>
  <external_reactions>
    <force name="thrust" frame="BODY">
%s
      <direction><x>1</x><y>0</y><z>0</z></direction>
    </force>
  </external_reactions>
  <system file="controls"/>
  <system file="laws"/>
  <system file="engine"/>
  <system file="fuel"/>
  <system file="flex"/>
  <system file="touchdown"/>
  <flight_control name="fcs"/>
%s
</fdm_config>
''' % (name, w['area_reference'], w['span'], w['mac'], loc('location name="AERORP"', *ref, indent='    ').replace('</location name="AERORP">', '</location>'),
       loc('location name="EYEPOINT"', 3.0, 0, 6.0, indent='    ').replace('</location name="EYEPOINT">', '</location>'),
       loc('location name="VRP"', 0, 0, 0, indent='    ').replace('</location name="VRP">', '</location>'),
       e['ixx'] + pay['ixx'], e['iyy'] + pay['iyy'], e['izz'] + pay['izz'], e['weight'],   # the payload's own inertia rides with the airframe's
       loc('location name="CG"', e['x'], 0, e['z'], indent='    ').replace('</location name="CG">', '</location>'),
       pay['weight'], loc('location', pay['x'], 0, pay['z']),
       contact('nose', gear['nose_x'], 0, w_nose, 0.4, 60, 'NONE'),
       contact('left main', gear['main_x'], -gear['main_track'] / 2, w_main, 0.5, 0, 'LEFT'),
       contact('right main', gear['main_x'], gear['main_track'] / 2, w_main, 0.5, 0, 'RIGHT') + structure(),
       tanks, loc('location', nac['inlet_x'] + 0.5 * nac['length'], 0, nac['thrust_line_z']), aerodynamics(t))


def controls_file():
    def surf(nm, cmd, desc):
        return '''    <fcs_function name="ctl/manual-%s">
      <description>%s</description>
      <function><product><value>%g</value><property>%s</property></product></function>
      <clipto><min>-%g</min><max>%g</max></clipto>
    </fcs_function>''' % (nm, desc, SURFACE_LIMIT_DEG, cmd, SURFACE_LIMIT_DEG, SURFACE_LIMIT_DEG)
    ail = '''    <fcs_function name="ctl/manual-spoiler-norm">
      <description>spoilers, 0 to 1 (1 is %g deg), from the speedbrake command; the approach is taken to be flown at %g deg</description>
      <function><property>fcs/speedbrake-cmd-norm</property></function>
      <clipto><min>0</min><max>1</max></clipto>
    </fcs_function>
    <fcs_function name="aero/wheel-height-ft">
      <description>height of the wheels above the ground, for ground effect</description>
      <function><difference><property>position/h-agl-ft</property><value>%.2f</value></difference></function>
      <clipto><min>0</min><max>1000</max></clipto>
    </fcs_function>
    <kinematic name="gear/position">
      <description>gear travel: %g s (an estimate)</description>
      <input>gear/gear-cmd-norm</input>
      <traverse><setting><position>0</position><time>0</time></setting><setting><position>1</position><time>%g</time></setting></traverse>
      <output>gear/gear-pos-norm</output>
    </kinematic>
    <switch name="ctl/gear-norm">
      <description>gear position as the drag sees it: the command itself when ctl/instant is set (trims)</description>
      <default value="gear/gear-pos-norm"/>
      <test value="gear/gear-cmd-norm">ctl/instant == 1</test>
    </switch>
    <fcs_function name="ctl/steer-deg">
      <description>nose-wheel steering, %g deg at full command</description>
      <function><product><value>%g</value><property>fcs/steer-cmd-norm</property></product></function>
      <output>fcs/steer-pos-deg</output>
    </fcs_function>''' % (SPOILER_MAX_DEG, SPOILER_APPROACH_DEG, 5.3, 8.0, 8.0, 60.0, 60.0)
    return '''<?xml version="1.0"?>
<!-- Generated by fdm/genghawk.py. The direct commands (ctl/manual-*): what the surfaces follow when the flight laws
     (Systems/laws.xml) are off. Spoilers, gear and steering are direct for now. -->
<system name="controls">
  <property value="0">ctl/instant</property>
  <property value="0">fcs/throttle-cmd-norm</property>   <!-- the model has no JSBSim engine, so nothing else makes this one -->
  <property value="%g">cal/spoiler-lift</property>
  <property value="%g">cal/spoiler-drag</property>
  <channel name="surfaces">
%s
%s
%s
%s
  </channel>
</system>
''' % (CAL.get('spoiler_lift', 0.0), CAL.get('spoiler_drag', 0.0),
       surf('pitch-deg', 'fcs/elevator-cmd-norm', 'both ruddervators, trailing edge down positive: nose down'),
       surf('roll-deg', 'fcs/aileron-cmd-norm', 'roll command, right wing down positive'),
       surf('yaw-deg', 'fcs/rudder-cmd-norm', 'ruddervators against each other, nose right positive'), ail)


def engine_file():
    T = ENG['tables']
    alts, machs, dts, fr = T['altitude_ft'], T['mach'], T['delta_T_K'], T['thrust_fraction']
    HP, MACH = 'engine/pressure-altitude-ft', 'velocities/mach'
    import engine as E
    isa = [E.isa(a)[0] * 1.8 for a in alts]
    isa_p = [E.isa(a)[1] / 47.880259 for a in alts]
    fuel = [[[T['fuel_lbh'][i][j][k] for j in range(len(machs))] for i in range(len(alts))] for k in range(len(fr))]
    return '''<?xml version="1.0"?>
<!-- Generated by fdm/genghawk.py from fdm/data/engine.json: the AE 3007H as tables from the cycle model. -->
<system name="engine">
  <property value="1">engine/running</property>
  <property value="1">engine/master</property>
  <property value="0">engine/failed</property>
  <property value="%g">cal/fuel-factor</property>
  <property value="%g">cal/drag-increment</property>
  <channel name="engine">
    <fcs_function name="engine/pressure-altitude-ft">
      <description>pressure altitude from the static pressure, standard atmosphere</description>
      <function>
%s
      </function>
    </fcs_function>
    <fcs_function name="engine/isa-T-R">
      <function>
%s
      </function>
    </fcs_function>
    <fcs_function name="engine/delta-T-K">
      <description>air temperature above standard at this pressure altitude</description>
      <function><quotient><difference><property>atmosphere/T-R</property><property>engine/isa-T-R</property></difference><value>1.8</value></quotient></function>
    </fcs_function>
    <fcs_function name="engine/max-thrust-lbf">
      <description>maximum thrust: the lowest of fan speed, turbine temperature and the flat rating</description>
      <function>
%s
      </function>
    </fcs_function>
    <fcs_function name="engine/max-thrust-standard-lbf">
      <function>
%s
      </function>
    </fcs_function>
    <fcs_function name="engine/idle-thrust-lbf">
      <function>
%s
      </function>
    </fcs_function>
    <fcs_function name="engine/thrust-cmd-lbf">
      <description>idle to maximum with the throttle; nothing when the engine is stopped</description>
      <function>
        <product>
          <property>engine/running</property>
          <difference><value>1</value><property>engine/failed</property></difference>
          <sum>
            <property>engine/idle-thrust-lbf</property>
            <product>
              <property>ctl/throttle-norm</property>
              <difference><property>engine/max-thrust-lbf</property><property>engine/idle-thrust-lbf</property></difference>
            </product>
          </sum>
        </product>
      </function>
    </fcs_function>
    <lag_filter name="engine/thrust-lagged-lbf">
      <input>engine/thrust-cmd-lbf</input>
      <c1>%.4f</c1>
    </lag_filter>
    <switch name="engine/thrust-lbf">
      <description>the spool lag, or none when ctl/instant is set (trims)</description>
      <default value="engine/thrust-lagged-lbf"/>
      <test value="engine/thrust-cmd-lbf">ctl/instant == 1</test>
      <output>external_reactions/thrust/magnitude</output>
    </switch>
    <fcs_function name="engine/thrust-fraction">
      <description>thrust over the standard-day maximum here</description>
      <function><quotient><property>engine/thrust-lbf</property><max><property>engine/max-thrust-standard-lbf</property><value>1</value></max></quotient></function>
    </fcs_function>
    <fcs_function name="engine/fuel-flow-pph">
      <description>fuel flow: the standard-day table, scaled with the square root of the temperature ratio</description>
      <function>
        <product>
          <property>engine/running</property>
          <difference><value>1</value><property>engine/failed</property></difference>
          <property>cal/fuel-factor</property>
          <pow><quotient><property>atmosphere/T-R</property><property>engine/isa-T-R</property></quotient><value>0.5</value></pow>
%s
        </product>
      </function>
    </fcs_function>
    <fcs_function name="engine/spool-target">
      <description>1 while the engine runs</description>
      <function><product><property>engine/running</property><difference><value>1</value><property>engine/failed</property></difference></product></function>
    </fcs_function>
    <lag_filter name="engine/spool">
      <description>the rotors coming up to idle on a start and running down after a shutdown, for the fan's speed (and so the sound): about 20 s to most of the way. An assumed time, and no start sequence is modelled</description>
      <input>engine/spool-target</input>
      <c1>0.12</c1>
    </lag_filter>
    <lag_filter name="engine/core-spool">
      <description>the high-pressure rotor, which the starter turns and which leads the fan up on a start: most of the way in about 9 s. For the start's sound only; the time is assumed</description>
      <input>engine/spool-target</input>
      <c1>0.35</c1>
    </lag_filter>
    <fcs_function name="engine/fan-rpm">
      <description>the fan's speed, for the sound and the 3-D model's fan, not used by the flight model. Running: 8,290 rpm times the square root of the thrust's share of the maximum, measured from recordings: 8,290 rpm at take-off (a Global Hawk's take-off pass: the fan's 24th order and its buzz-saw's spacing, less the Doppler shift) and 2,230 to 2,270 rpm at ground idle (two taxiing Global Hawks: the blade passing tone at 891 Hz), which the idle thrust's 7 %% gives as 2,190. It comes up and runs down with engine/spool. Stopped in flight it windmills, 9 rpm per knot (assumed)</description>
      <function>
        <ifthen>
          <gt><product><property>engine/running</property><difference><value>1</value><property>engine/failed</property></difference></product><value>0.5</value></gt>
          <max>
            <product><value>9</value><property>velocities/vc-kts</property></product>
            <product><property>engine/spool</property><value>8290</value><pow><max><value>0</value><min><value>1.1</value><property>engine/thrust-fraction</property></min></max><value>0.5</value></pow></product>
          </max>
          <max>
            <product><value>9</value><property>velocities/vc-kts</property></product>
            <product><property>engine/spool</property><value>2190</value></product>
          </max>
        </ifthen>
      </function>
    </fcs_function>
  </channel>
</system>
''' % (CAL['fuel_factor'], CAL['drag_increment'], table1(isa_p[::-1], alts[::-1], 'atmosphere/P-psf'), table1(alts, isa, HP),
       table3(alts, machs, dts, T['max_thrust_lbf'], HP, MACH, 'engine/delta-T-K'),
       table2(alts, machs, T['max_thrust_lbf'][dts.index(0.0)], HP, MACH),
       table2(alts, machs, T['idle_thrust_lbf'], HP, MACH), 1.0 / SPOOL_SECONDS,
       table3(alts, machs, fr, fuel, HP, MACH, 'engine/thrust-fraction'))


# The wheels, for the touchdown's sound (fdm/mksounds.py has the same): two tyres on every leg; the mains the Learjet
# 45's size (22x5.75-12), the nose's the CF-5's (18x6.5-8). Weights estimated (no data sheet at hand): the moment of
# inertia as PyWopWop's tyre model takes it, the tyre's mass at 0.8 of its radius, the wheel's and brake's at 0.35.
WHEELS = dict(main=dict(diameter_m=0.559, width_m=0.146, rolling_radius_m=0.26, tyre_kg=8.5, wheel_kg=7.5, drag_nm=3.0),
              nose=dict(diameter_m=0.457, width_m=0.165, rolling_radius_m=0.21, tyre_kg=6.0, wheel_kg=3.5, drag_nm=2.0))
BRAKE_NM = 1500.0                 # a main wheel's brake at full command, N m: stops a spinning wheel in the air at once (assumed)


def wheel_inertia(w):
    R = w['diameter_m'] / 2
    return w['tyre_kg'] * (0.8 * R) ** 2 + w['wheel_kg'] * (0.35 * R) ** 2


def touchdown_file(g=None):
    """Each leg's wheels' spin and what its touchdown sounds read, as the X-57's and the MV-22B's models have them: the
    rim's speed (spun up on the ground by the sliding grip, 0.5, times the strut's force shared by the leg's two tyres,
    until it rolls at the ground speed; in the air run down by the bearings' drag and stopped by a main's brake), and
    the wheel's own sink rate and slip as its weight comes on, held until it lifts off."""
    g = g or G['gear']
    track_in = g['main_track'] * 12.0
    out = []
    for n, (kind, x_in, y_in, spring, damp, brake) in enumerate((('nose', g['nose_x'] * 12.0, 0.0, 11636.0, 1297.0, None),
                                                                 ('main', g['main_x'] * 12.0, -track_in / 2, 22096.0, 2754.0, 'left'),
                                                                 ('main', g['main_x'] * 12.0, track_in / 2, 22096.0, 2754.0, 'right'))):
        w = WHEELS[kind]
        I, r = wheel_inertia(w), w['rolling_radius_m']
        up = 0.5 * 4.4482216 * r * r / (2 * I) / 0.514444          # kt/s of rim speed a lbf of the leg's load gives (two tyres)
        k = r / I / 0.514444                                        # kt/s a N m of torque takes away
        u = 'gear/unit[%d]/' % n
        torque = '<value>%g</value>' % w['drag_nm'] if brake is None else \
            '<sum><value>%g</value><product><property>fcs/%s-brake-cmd-norm</property><value>%g</value></product></sum>' % (w['drag_nm'], brake, BRAKE_NM)
        out.append("""    <fcs_function name="%(u)ssink-now-fps">
      <description>the wheel's own speed downwards: the aircraft's, with its roll and pitch about the centre of gravity</description>
      <function><sum>
        <property>velocities/v-down-fps</property>
        <product><property>velocities/p-rad_sec</property><quotient><difference><value>%(y)g</value><property>inertia/cg-y-in</property></difference><value>12</value></quotient></product>
        <product><value>-1</value><property>velocities/q-rad_sec</property><quotient><difference><property>inertia/cg-x-in</property><value>%(x)g</value></difference><value>12</value></quotient></product>
      </sum></function>
    </fcs_function>
    <fcs_function name="%(u)sslip-now-kt">
      <description>the ground speed less the rim's</description>
      <function><max><value>0</value><difference><product><property>velocities/vg-fps</property><value>0.592484</value></product><property>%(u)sspin-kt</property></difference></max></function>
    </fcs_function>
    <fcs_function name="%(u)sspin-kt">
      <description>the rim's speed, kt: spun up by the runway, rolling, running down in the air</description>
      <function><ifthen>
        <gt><property>%(u)sWOW</property><value>0.5</value></gt>
        <min>
          <product><property>velocities/vg-fps</property><value>0.592484</value></product>
          <sum><property>%(u)sspin-kt</property><product><value>%(up).6g</value><max><value>0</value><sum><product><value>%(spring)g</value><property>%(u)scompression-ft</property></product><product><value>%(damp)g</value><property>%(u)scompression-velocity-fps</property></product></sum></max><property>simulation/channel-dt</property></product></sum>
        </min>
        <max><value>0</value><difference><property>%(u)sspin-kt</property><product><value>%(k).6g</value>%(torque)s<property>simulation/channel-dt</property></product></difference></max>
      </ifthen></function>
    </fcs_function>
    <fcs_function name="%(u)stouchdown-sink-fps">
      <description>as the weight came on, held until it lifts off</description>
      <function><ifthen><gt><property>%(u)sWOW</property><value>0.5</value></gt><property>%(u)stouchdown-sink-fps</property><property>%(u)ssink-now-fps</property></ifthen></function>
    </fcs_function>
    <fcs_function name="%(u)stouchdown-slip-kt">
      <description>likewise</description>
      <function><ifthen><gt><property>%(u)sWOW</property><value>0.5</value></gt><property>%(u)stouchdown-slip-kt</property><property>%(u)sslip-now-kt</property></ifthen></function>
    </fcs_function>
""" % dict(u=u, x=x_in, y=y_in, up=up, k=k, spring=spring, damp=damp, torque=torque))
    props = ''.join('  <property value="0">gear/unit[%d]/%s</property>\n' % (n, q) for n in range(3) for q in ('spin-kt', 'touchdown-sink-fps', 'touchdown-slip-kt'))
    return """<?xml version="1.0"?>
<!-- Generated by fdm/genghawk.py: each leg's wheels' spin and its touchdown's sink rate and slip, for the sounds. -->
<system name="touchdown">
%s  <channel name="touchdown">
%s  </channel>
</system>
""" % (props, ''.join(out))


def fuel_file():
    n = len(M['tanks'])
    total = '\n'.join('          <property>propulsion/tank[%d]/contents-lbs</property>' % i for i in range(n))
    tanks = '\n'.join('''    <fcs_function name="fuel/tank-%d-lbs">
      <description>%s: its share of this frame's fuel, in proportion to what it holds</description>
      <function>
        <max>
          <value>0</value>
          <difference>
            <property>propulsion/tank[%d]/contents-lbs</property>
            <product>
              <property>fuel/burn-lbs</property>
              <quotient><property>propulsion/tank[%d]/contents-lbs</property><max><property>fuel/total-lbs</property><value>0.001</value></max></quotient>
            </product>
          </difference>
        </max>
      </function>
      <output>propulsion/tank[%d]/contents-lbs</output>
    </fcs_function>''' % (i, tk['name'], i, i, i) for i, tk in enumerate(M['tanks']))
    return '''<?xml version="1.0"?>
<!-- Generated by fdm/genghawk.py. The real aircraft's fuel system isn't public: this layout and its management are ours.
     Every tank gives up fuel in proportion to its contents, so the fuel's centre stays where it is: at the
     centre-of-gravity target, by the tank sizes in fdm/data/mass.json. -->
<system name="fuel">
  <property value="0">fuel/freeze</property>
  <channel name="fuel management">
    <fcs_function name="fuel/total-lbs">
      <function>
        <sum>
%s
        </sum>
      </function>
    </fcs_function>
    <fcs_function name="fuel/burn-lbs">
      <description>fuel used this frame</description>
      <function>
        <product>
          <difference><value>1</value><property>fuel/freeze</property></difference>
          <property>engine/fuel-flow-pph</property>
          <property>simulation/dt</property>
          <value>%.9f</value>
        </product>
      </function>
    </fcs_function>
%s
    <switch name="fuel/engine-fed">
      <description>the engine runs while its master switch is on (engine/master: the aircraft's Autostart and Shutdown) and the tanks are not dry</description>
      <default value="engine/master"/>
      <test value="0">fuel/total-lbs lt 1</test>
      <output>engine/running</output>
    </switch>
  </channel>
</system>
''' % (total, 1 / 3600.0, tanks)


def flex_file():
    c, fr = FLEX['tip_deflection'], FLEX['frequency_hz']
    k = (fr['empty'] / fr['full']) ** 2 - 1.0
    return '''<?xml version="1.0"?>
<!-- Generated by fdm/genghawk.py from fdm/data/flex.json. The wing's first bending mode, from a beam model built on
     assumptions (fdm/flex.py): no stiffness or frequency of the real wing is public. flex/enable = 0 keeps the tip
     deflection for show and takes its effect on roll due to sideslip away. -->
<system name="flex">
  <property value="1">flex/enable</property>
  <channel name="wing bending">
    <fcs_function name="flex/wing-fuel-lbs">
      <function><sum><property>propulsion/tank[0]/contents-lbs</property><property>propulsion/tank[1]/contents-lbs</property><property>propulsion/tank[2]/contents-lbs</property><property>propulsion/tank[3]/contents-lbs</property></sum></function>
    </fcs_function>
    <fcs_function name="flex/tip-static-ft">
      <description>where the tips would settle: up with the lift, down with the load factor times the wing's own weight and fuel</description>
      <function>
        <sum>
          <product><value>%.6e</value><property>forces/fwz-aero-lbs</property></product>
          <product>
            <property>accelerations/Nz</property>
            <sum><value>%.6f</value><product><value>%.6e</value><property>flex/wing-fuel-lbs</property></product></sum>
          </product>
        </sum>
      </function>
    </fcs_function>
    <fcs_function name="flex/omega-rad_sec">
      <description>first bending frequency: %.2f Hz with empty wing tanks, %.2f Hz full</description>
      <function>
        <quotient>
          <value>%.5f</value>
          <pow><sum><value>1</value><product><value>%.6e</value><property>flex/wing-fuel-lbs</property></product></sum><value>0.5</value></pow>
        </quotient>
      </function>
    </fcs_function>
    <fcs_function name="flex/c5"><function><product><value>%.4f</value><property>flex/omega-rad_sec</property></product></function></fcs_function>
    <fcs_function name="flex/c6"><function><product><property>flex/omega-rad_sec</property><property>flex/omega-rad_sec</property></product></function></fcs_function>
    <second_order_filter name="flex/tip-dynamic-ft">
      <input>flex/tip-static-ft</input>
      <c1>0</c1><c2>0</c2><c3>flex/c6</c3>
      <c4>1</c4><c5>flex/c5</c5><c6>flex/c6</c6>
    </second_order_filter>
    <switch name="flex/tip-deflection-ft">
      <description>tip deflection, up positive: the mode, or its settled value when ctl/instant is set (trims)</description>
      <default value="flex/tip-dynamic-ft"/>
      <test value="flex/tip-static-ft">ctl/instant == 1</test>
    </switch>
  </channel>
</system>
''' % (c['per_lb_lift'], c['per_lb_structure'] * FLEX['wing_structure_lb'], c['per_lb_wing_fuel'], fr['empty'], fr['full'],
       2 * np.pi * fr['empty'], k / FLEX['wing_fuel_lb'], 2 * FLEX['damping'])


def write(out_dir, ref=False):
    t = json.load(open(os.path.join(D, 'aero_tables_ref.json' if ref else 'aero_tables.json')))
    os.makedirs(os.path.join(out_dir, 'Systems'), exist_ok=True)
    name = 'reference build: %s' % t['model'] if ref else 'the strip model'
    files = {'GlobalHawk.xml': main_file(t, name), 'Systems/controls.xml': controls_file(), 'Systems/engine.xml': engine_file(),
             'Systems/fuel.xml': fuel_file(), 'Systems/flex.xml': flex_file(), 'Systems/touchdown.xml': touchdown_file(), 'Systems/laws.xml': laws.laws_file()}
    for f, text in files.items():
        open(os.path.join(out_dir, f), 'w').write(text)
    if os.path.isdir(os.path.join(out_dir, 'Nasal')):
        # The model's properties that start at something other than zero, for FlightGear. A ground station that is
        # connected before the flight model has loaded makes the properties it listens to, empty; JSBSim then keeps
        # them as they are and they never get their value (found: the four navigators' switches, so no navigator,
        # no attitude for the laws and a pitch swing that grew). Nasal/globalhawk.nas gives the empty ones theirs.
        rows = []
        for text in files.values():
            rows += ['    "%s": %s,' % (name.strip(), value) for value, name in re.findall(r'<property value="([^"]+)">([^<]+)</property>', text) if float(value) != 0.0]
        open(os.path.join(out_dir, 'Nasal', 'defaults.nas'), 'w').write(
            '# Written by fdm/genghawk.py: do not edit. The flight model\'s properties that start at a value other than zero.\n'
            '# Nasal/globalhawk.nas sets those that FlightGear has without a value when the flight model has loaded.\n'
            'var DEFAULTS = {\n' + '\n'.join(rows) + '\n};\n')
    return out_dir


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    ref = '--ref' in sys.argv
    out = args[0] if args else os.path.join(HERE, '..', 'GlobalHawk')
    write(out, ref)
    print('wrote', os.path.relpath(out))
