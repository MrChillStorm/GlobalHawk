#!/usr/bin/env python3
"""The flight laws as a JSBSim system: GlobalHawk/Systems/laws.xml, written by fdm/genghawk.py through laws_file().

The real laws aren't public; these are ours, built to behave as the public sources say the aircraft does. The
design, its sources and its checks are in docs/FLIGHT-LAWS.md (local) and summarised in fdm/data/README.md.
Part A: the basic laws (pitch attitude, bank, yaw damping), the autopilot modes on top of them (speed by elevator,
altitude hold, heading), thrust modes, protections and actuators.

Properties: ap/engaged, ap/pitch-mode (0 attitude, 1 speed by elevator, 2 altitude), ap/roll-mode (0 bank,
1 heading), ap/thrust-mode (0 as commanded, 1 maximum, 2 idle, 3 speed by thrust), and the targets ap/theta-cmd-deg,
ap/speed-cmd-kcas, ap/speed-schedule, ap/speed-offset-kcas, ap/alt-cmd-ft, ap/bank-cmd-deg, ap/heading-cmd-deg,
ap/throttle-cmd. ap/gain-scale multiplies every loop gain (for the gain-margin checks).
"""

# gains at a dynamic pressure of 50 psf (docs/FLIGHT-LAWS.md, section 3)
G = dict(K_theta=1.4, K_q=0.6, K_theta_i=0.4, K_phi=0.5, K_phi_i=0.0, K_p=0.6, K_r=0.5, K_beta=1.5, K_beta_i=0.15, K_ari=0.0,
         K_alpha=3.0, K_slow=0.4,
         K_v=0.5, K_v_i=0.03, K_h=0.012, K_h_i=0.0012, K_hd=0.06, K_psi=1.2, K_thr=0.04, K_thr_i=0.004)
SURFACE = dict(lag=20.0, rate=40.0, limit=20.0)          # actuators: 0.05 s lag, 40 deg/s, 20 deg. Estimates
SCHEDULE = [(0.0, 0.0), (22000.0, 0.345), (55000.0, 0.60), (80000.0, 0.60)]     # pressure altitude, Mach above FL220
SCHEDULE_KCAS = 150.0
ALPHA_LIMIT = [(0.0, 7.0), (0.3, 6.0), (0.5, 5.0), (0.6, 3.5), (0.65, 2.5)]       # Mach, deg in body axes
BANK_LIMIT = [(0.0, 25.0), (30000.0, 25.0), (50000.0, 15.0), (80000.0, 15.0)]     # pressure altitude, deg
ALTITUDE_LIMIT = 65000.0
BANK_MARGIN = 2.0


def _table(pts, prop, ind='          '):
    rows = '\n'.join('%s    %g %g' % (ind, x, y) for x, y in pts)
    return '%s<table><independentVar lookup="row">%s</independentVar><tableData>\n%s\n%s</tableData></table>' % (ind, prop, rows, ind)


def _fn(name, expr, desc='', clip=None, out=None):
    s = '    <fcs_function name="%s">\n' % name
    if desc:
        s += '      <description>%s</description>\n' % desc
    s += '      <function>\n%s\n      </function>\n' % expr
    if clip:
        s += '      <clipto><min>%s</min><max>%s</max></clipto>\n' % clip
    if out:
        s += '      <output>%s</output>\n' % out
    return s + '    </fcs_function>'


def _p(name):
    return '<property>%s</property>' % name


def _v(x):
    return '<value>%g</value>' % x


def _op(op, *terms):
    return '        <%s>%s</%s>' % (op, ''.join(terms), op)


def _latch(name, follow, desc):
    """A property that follows another while the laws are off and holds it from the frame they come on."""
    return '''    <switch name="ap/latch-%s">
      <description>%s</description>
      <default value="ap/%s"/>
      <test value="%s">ap/engaged == 0</test>
      <output>ap/%s</output>
    </switch>''' % (name, desc, name, follow, name)


def _trigger(name, *conds):
    """An integrator's trigger: 0 lets it run, -1 holds it at zero. It runs only while every condition holds."""
    return '''    <switch name="ap/trig-%s">
      <default value="-1"/>
      <test logic="AND" value="0">
        %s
      </test>
    </switch>''' % (name, '\n        '.join(('ap/engaged == 1',) + conds))


def _pid(name, inp, kp, ki, trig, clip=None):
    s = '''    <pid name="%s">
      <input>%s</input>
      <kp>%s</kp>
      <ki>%s</ki>
      <kd>0</kd>
      <trigger>ap/trig-%s</trigger>
''' % (name, inp, kp, ki, trig)
    if clip:
        s += '      <clipto><min>%s</min><max>%s</max></clipto>\n' % clip
    return s + '    </pid>'


def _gain(name, value):
    """A gain property: its value at 50 psf times the dynamic-pressure schedule and the test scale."""
    return _fn('ap/k-%s' % name, _op('product', _v(value), _p('ap/gain-q'), _p('ap/gain-scale')))


def _actuator(name, inp, lag, rate, lo, hi):
    return '''    <actuator name="%s">
      <input>%s</input>
      <lag>%g</lag>
      <rate_limit>%g</rate_limit>
      <clipto><min>%g</min><max>%g</max></clipto>
    </actuator>''' % (name, inp, lag, rate, lo, hi)


def _final(name, law, manual, desc, out=None):
    """The surface: the law through its actuator when engaged, the manual value otherwise; no actuator in trims."""
    return '''    <switch name="ap/sel-%s">
      <default value="%s"/>
      <test value="%s">ap/engaged == 1</test>
    </switch>
%s
    <switch name="%s">
      <description>%s</description>
      <default value="ap/act-%s"/>
      <test value="ap/sel-%s">ctl/instant == 1</test>%s
    </switch>''' % (name, manual, law, _actuator('ap/act-%s' % name, 'ap/sel-%s' % name, SURFACE['lag'], SURFACE['rate'], -SURFACE['limit'], SURFACE['limit']),
                    'ctl/%s' % name, desc, name, name, ('\n      <output>%s</output>' % out) if out else '')


def laws_file():
    props = ''.join('  <property value="%g">ap/%s</property>\n' % (v, k) for k, v in (
        ('engaged', 0), ('pitch-mode', 0), ('roll-mode', 0), ('thrust-mode', 0), ('theta-cmd-deg', 0), ('speed-cmd-kcas', 150),
        ('speed-schedule', 1), ('speed-offset-kcas', 0), ('alt-cmd-ft', 0), ('bank-cmd-deg', 0), ('heading-cmd-deg', 0),
        ('throttle-cmd', 0.5), ('gain-scale', 1), ('bias-pitch-deg', 0), ('bias-yaw-deg', 0), ('bias-throttle', 0),
        ('theta-latched-deg', 0), ('theta-delta-deg', 0)))
    ch = []
    # ---- schedules
    ch.append(_fn('ap/gain-q', _op('quotient', _v(50), '<max>%s%s</max>' % (_p('aero/qbar-psf'), _v(1))),
                  'gain schedule: control power goes with dynamic pressure', clip=('0.4', '2.5')))
    for n in ('theta', 'q', 'theta_i', 'phi', 'phi_i', 'p', 'r', 'beta', 'beta_i'):
        ch.append(_gain(n.replace('_', '-'), G['K_' + n]))
    ch.append(_fn('ap/schedule-mach', _table(SCHEDULE, 'engine/pressure-altitude-ft'), 'the scheduled Mach number above FL220'))
    ch.append(_fn('ap/schedule-kcas', '''        <ifthen>
          <lt>%s%s</lt>
          %s
          <product>%s<quotient>%s<max>%s%s</max></quotient></product>
        </ifthen>''' % (_p('engine/pressure-altitude-ft'), _v(SCHEDULE[1][0]), _v(SCHEDULE_KCAS), _p('velocities/vc-kts'),
                        _p('ap/schedule-mach'), _p('velocities/mach'), _v(0.05)),
                  'the scheduled speed as calibrated airspeed at this height: %g KCAS low down, the scheduled Mach above' % SCHEDULE_KCAS))
    ch.append('''    <switch name="ap/speed-target-kcas">
      <description>the commanded speed: the schedule less the operator's offset, or a commanded speed</description>
      <default value="ap/speed-cmd-kcas"/>
      <test value="ap/schedule-less-offset">ap/speed-schedule == 1</test>
    </switch>''')
    ch.insert(len(ch) - 1, _fn('ap/schedule-less-offset', _op('difference', _p('ap/schedule-kcas'), _p('ap/speed-offset-kcas'))))
    ch.append(_fn('ap/alpha-limit-deg', _table(ALPHA_LIMIT, 'velocities/mach'), 'angle-of-attack limit: the lift break less a margin'))
    ch.append(_fn('ap/bank-limit-deg', _table(BANK_LIMIT, 'engine/pressure-altitude-ft'), 'bank limit'))
    # ---- latches
    ch.append(_latch('bias-pitch-deg', 'ctl/manual-pitch-deg', 'ruddervator angle at engagement'))
    ch.append(_latch('bias-yaw-deg', 'ctl/manual-yaw-deg', 'yaw command at engagement'))
    ch.append(_latch('bias-throttle', 'fcs/throttle-cmd-norm', 'throttle at engagement'))
    ch.append(_latch('theta-latched-deg', 'attitude/theta-deg', 'pitch attitude at engagement'))
    # ---- autopilot: the pitch attitude command
    ch.append(_fn('ap/speed-error-kt', _op('difference', _p('velocities/vc-kts'), _p('ap/speed-target-kcas')), 'fast is positive'))
    ch.append(_trigger('speed', 'ap/pitch-mode == 1'))
    ch.append(_pid('ap/theta-speed-deg', 'ap/speed-error-kt', G['K_v'], G['K_v_i'], 'speed', clip=('-20', '20')))
    ch.append(_fn('ap/alt-error-ft', _op('difference', _p('ap/alt-cmd-ft'), _p('position/h-sl-ft')), clip=('-1500', '1500')))
    ch.append(_trigger('alt', 'ap/pitch-mode == 2'))
    ch.append(_pid('ap/theta-alt-pi-deg', 'ap/alt-error-ft', G['K_h'], G['K_h_i'], 'alt', clip=('-12', '12')))
    ch.append(_fn('ap/theta-alt-deg', _op('difference', _p('ap/theta-alt-pi-deg'), '<product>%s%s</product>' % (_v(G['K_hd']), _p('velocities/h-dot-fps')))))
    ch.append('''    <switch name="ap/theta-mode-deg">
      <description>pitch attitude asked for by the mode, from the attitude latched at engagement</description>
      <default value="ap/theta-cmd-less-latched"/>
      <test value="ap/theta-speed-deg">ap/pitch-mode == 1</test>
      <test value="ap/theta-alt-deg">ap/pitch-mode == 2</test>
    </switch>''')
    ch.insert(len(ch) - 1, _fn('ap/theta-cmd-less-latched', _op('difference', _p('ap/theta-cmd-deg'), _p('ap/theta-latched-deg'))))
    # ---- the pitch command governor: the command is a state that moves towards what the mode asks at 2 deg/s at
    # most, and is pulled down, whatever the mode asks, while the angle of attack is over its limit or the speed is
    # under its floor. Being a rate, it has nothing to wind up and nothing to release with a jump.
    ch.append(_fn('ap/alpha-margin-deg', _op('difference', _p('ap/alpha-limit-deg'), _p('aero/alpha-deg')), 'room under the angle-of-attack limit'))
    ch.append(_fn('ap/speed-margin-kt', '        <difference>%s<difference>%s%s</difference></difference>' % (
        _p('velocities/vc-kts'), _p('ap/speed-target-kcas'), _v(15)), 'room above the lowest speed allowed: 15 kt under the commanded speed'))
    ch.append(_fn('ap/protect-fast-deg', '        <product>%s<max>%s<difference>%s%s</difference></max></product>' % (
        _v(200.0), _v(0), _p('velocities/mach'), _v(0.63)), 'nose up above Mach 0.63'))
    ch.append(_fn('ap/theta-rate-deg_sec', '''        <max>
          %s
          <min>
            <min>%s<max>%s<product>%s<difference><sum>%s%s</sum>%s</difference></product></max></min>
            <product>%s%s</product>
            <product>%s%s</product>
          </min>
        </max>''' % (_v(-6), _v(2), _v(-2), _v(2.0), _p('ap/theta-mode-deg'), _p('ap/protect-fast-deg'), _p('ap/theta-delta-deg'),
                     _v(G['K_alpha']), _p('ap/alpha-margin-deg'), _v(G['K_slow']), _p('ap/speed-margin-kt')),
                  'how fast the pitch command moves: towards the mode\'s, or down for angle of attack or speed, whichever is lowest'))
    ch.append(_trigger('governor'))
    ch.append('''    <pid name="ap/theta-governor">
      <description>the pitch command, as a change from the attitude latched at engagement</description>
      <input>ap/theta-rate-deg_sec</input>
      <kp>0</kp><ki>1</ki><kd>0</kd>
      <trigger>ap/trig-governor</trigger>
      <clipto><min>-16</min><max>18</max></clipto>
      <output>ap/theta-delta-deg</output>
    </pid>''')
    ch.append(_fn('ap/protect-alpha-deg', '        <product>%s<min>%s%s</min></product>' % (_v(2.0), _v(0), _p('ap/alpha-margin-deg')),
                  'a direct push down in proportion to the angle of attack over its limit, ahead of the governor'))
    # ---- basic law: pitch
    ch.append(_fn('ap/theta-error-deg', '        <difference>%s<sum>%s%s%s</sum></difference>' % (
        _p('attitude/theta-deg'), _p('ap/theta-latched-deg'), _p('ap/theta-delta-deg'), _p('ap/protect-alpha-deg')), 'nose high is positive'))
    ch.append(_trigger('pitch'))
    ch.append(_pid('ap/pitch-pi-deg', 'ap/theta-error-deg', 'ap/k-theta', 'ap/k-theta-i', 'pitch', clip=('-25', '25')))
    ch.append(_fn('ap/pitch-law-deg', '        <sum>%s%s<product>%s%s%s</product></sum>' % (
        _p('ap/bias-pitch-deg'), _p('ap/pitch-pi-deg'), _p('ap/k-q'), _v(57.29578), _p('velocities/q-rad_sec')),
        'ruddervators together, trailing edge down positive', clip=('-20', '20')))
    # ---- basic law: roll
    ch.append(_fn('ap/heading-error-deg', '''        <difference>
          <mod><sum><difference>%s%s</difference>%s</sum>%s</mod>
          %s
        </difference>''' % (_p('ap/heading-cmd-deg'), _p('attitude/psi-deg'), _v(540), _v(360), _v(180)), 'right of the nose is positive'))
    ch.append(_fn('ap/bank-heading-deg', _op('product', _v(G['K_psi']), _p('ap/heading-error-deg'), '<quotient>%s%s</quotient>' % (_p('velocities/vt-fps'), _v(600)))))
    ch.append('''    <switch name="ap/bank-mode-deg">
      <default value="ap/bank-cmd-deg"/>
      <test value="ap/bank-heading-deg">ap/roll-mode == 1</test>
    </switch>''')
    ch.append(_fn('ap/bank-command-limit-deg', _op('difference', _p('ap/bank-limit-deg'), _v(BANK_MARGIN)),
                  'the bank command stops %g deg inside the limit: in a steady turn the bank settles above its command (a '
                  'proportional law; an integral was tried and overshot)' % BANK_MARGIN))
    ch.append(_fn('ap/bank-clipped-deg', '''        <max>
          <product>%s%s</product>
          <min>%s%s</min>
        </max>''' % (_v(-1), _p('ap/bank-command-limit-deg'), _p('ap/bank-command-limit-deg'), _p('ap/bank-mode-deg')), 'inside the bank limit'))
    ch.append('''    <switch name="ap/bank-gated-deg">
      <default value="0"/>
      <test value="ap/bank-clipped-deg">ap/engaged == 1</test>
    </switch>''')
    ch.append('''    <actuator name="ap/bank-target-deg">
      <description>the bank command moves at 5 deg/s at most</description>
      <input>ap/bank-gated-deg</input>
      <rate_limit>5</rate_limit>
    </actuator>''')
    ch.append(_fn('ap/bank-error-deg', _op('difference', _p('ap/bank-target-deg'), _p('attitude/phi-deg'))))
    # the integral trims the ailerons in a steady turn; it runs only close to the target, so it can't wind up
    # while the bank command is still ramping
    ch.append(_trigger('roll', 'ap/bank-error-deg lt 3', 'ap/bank-error-deg gt -3'))
    ch.append(_pid('ap/roll-pi-deg', 'ap/bank-error-deg', 'ap/k-phi', 'ap/k-phi-i', 'roll', clip=('-20', '20')))
    ch.append(_fn('ap/roll-law-deg', '''        <difference>
          %s
          <product>%s%s%s</product>
        </difference>''' % (_p('ap/roll-pi-deg'), _p('ap/k-p'), _v(57.29578), _p('velocities/p-rad_sec')),
                  'roll command, right wing down positive', clip=('-20', '20')))
    # ---- basic law: yaw
    ch.append('''    <washout_filter name="ap/yaw-rate-washed">
      <input>velocities/r-rad_sec</input>
      <c1>0.3333</c1>
    </washout_filter>''')
    ch.append(_trigger('beta'))
    ch.append(_pid('ap/yaw-beta-deg', 'aero/beta-deg', 'ap/k-beta', 'ap/k-beta-i', 'beta', clip=('-12', '12')))
    ch.append(_fn('ap/yaw-law-deg', '''        <sum>
          %s
          <product>%s%s%s%s</product>
          %s
          <product>%s%s</product>
        </sum>''' % (_p('ap/bias-yaw-deg'), _v(-1), _p('ap/k-r'), _v(57.29578), _p('ap/yaw-rate-washed'), _p('ap/yaw-beta-deg'),
                     _v(-G['K_ari']), _p('ap/roll-law-deg')),
                  'ruddervators against each other, nose right positive: damper, sideslip to zero (interconnect with the ailerons: gain 0 for now)', clip=('-20', '20')))
    # ---- thrust
    ch.append(_fn('ap/thrust-error-kt', _op('difference', _p('ap/speed-target-kcas'), _p('velocities/vc-kts')), 'slow is positive'))
    ch.append(_trigger('thrust', 'ap/thrust-mode == 3'))
    ch.append(_pid('ap/thrust-pi', 'ap/thrust-error-kt', G['K_thr'], G['K_thr_i'], 'thrust', clip=('-1', '1')))
    ch.append(_fn('ap/thrust-speed', _op('sum', _p('ap/bias-throttle'), _p('ap/thrust-pi')), clip=('0', '1')))
    ch.append('''    <switch name="ap/thrust-law">
      <default value="ap/throttle-cmd"/>
      <test value="1">ap/thrust-mode == 1</test>
      <test value="0">ap/thrust-mode == 2</test>
      <test value="ap/thrust-speed">ap/thrust-mode == 3</test>
    </switch>
    <switch name="ctl/throttle-norm">
      <description>what the engine takes: the laws' throttle when engaged, the throttle command otherwise</description>
      <default value="fcs/throttle-cmd-norm"/>
      <test value="ap/thrust-law">ap/engaged == 1</test>
    </switch>''')
    # ---- surfaces
    ch.append(_final('pitch-deg', 'ap/pitch-law-deg', 'ctl/manual-pitch-deg', 'both ruddervators, trailing edge down positive: nose down'))
    ch.append(_final('roll-cmd-deg', 'ap/roll-law-deg', 'ctl/manual-roll-deg', 'roll command, right wing down positive'))
    ch.append(_final('yaw-deg', 'ap/yaw-law-deg', 'ctl/manual-yaw-deg', 'ruddervators against each other, nose right positive'))
    ch.append(_fn('ctl/aileron-deg', _op('product', _v(-1), _p('ctl/roll-cmd-deg')),
                  'ailerons as the aerodynamic tables take them: right trailing edge down positive, which rolls left'))
    return '''<?xml version="1.0"?>
<!-- Generated by fdm/genghawk.py (fdm/laws.py). The flight laws: our own design, the real ones are not public.
     ap/engaged = 0 leaves the surfaces on the direct commands. -->
<system name="laws">
%s  <channel name="flight laws">
%s
  </channel>
</system>
''' % (props, '\n'.join(ch))
