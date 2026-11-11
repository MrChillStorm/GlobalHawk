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
BANK_COMMAND = 0.86            # of the bank limit: 21.5 deg low down (Pastor: 21), 13 deg at height (ATTREX: 15)
# part B (docs/FLIGHT-LAWS.md section 5)
FT_PER_DEG = 364567.2            # feet in a degree of latitude
GLIDE_TAN = 0.07782              # tan of 4.45 deg: the measured approaches
APPROACH_CL = 0.645              # the measured approaches
SPOILER_BASE = 0.667             # 30 of 45 deg
FLARE_HEIGHT = 70.0              # ft of wheel height
FLARE_PITCH = 2.4                # deg: the measured touchdowns
FLARE_SINK = 2.3                 # ft/s wanted at the ground (0.7 m/s)
ROTATE_KIAS, ROTATE_PITCH = 130.0, 7.0
DECEL_G = 0.235                  # the measured rollout
WING_AREA = 540.0


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
        ('theta-latched-deg', 0), ('theta-delta-deg', 0), ('land-mode', 0), ('ground-steer', 0), ('taxi-speed-kt', 0),
        ('spoiler-mode', 0), ('spoiler-cmd', 0), ('rwy-elev-ft', 0), ('leg-lat0-deg', 0), ('leg-lon0-deg', 0), ('leg-lat1-deg', 0.01),
        ('leg-lon1-deg', 0), ('rollout', 0), ('spoiler-base', 0.667)))
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
      <test value="ap/approach-keas">ap/land-mode == 1</test>
      <test value="ap/schedule-less-offset">ap/speed-schedule == 1</test>
    </switch>''')
    ch.insert(len(ch) - 1, _fn('ap/schedule-less-offset', _op('difference', _p('ap/schedule-kcas'), _p('ap/speed-offset-kcas'))))
    ch.append(_fn('ap/alpha-limit-deg', _table(ALPHA_LIMIT, 'velocities/mach'), 'angle-of-attack limit: the lift break less a margin'))
    ch.append(_fn('ap/bank-limit-deg', _table(BANK_LIMIT, 'engine/pressure-altitude-ft'), 'bank limit'))
    # ---- part B: the leg, on a flat earth about its start
    lat, lon = 'position/lat-geod-deg', 'position/long-gc-deg'
    coslat = '<cos><toradians>%s</toradians></cos>' % _p('ap/leg-lat0-deg')
    ch.append(_fn('ap/leg-dn-ft', _op('product', _v(FT_PER_DEG), '<difference>%s%s</difference>' % (_p('ap/leg-lat1-deg'), _p('ap/leg-lat0-deg')))))
    ch.append(_fn('ap/leg-de-ft', _op('product', _v(FT_PER_DEG), coslat, '<difference>%s%s</difference>' % (_p('ap/leg-lon1-deg'), _p('ap/leg-lon0-deg')))))
    ch.append(_fn('ap/leg-length-ft', '        <max>%s<pow><sum><product>%s%s</product><product>%s%s</product></sum>%s</pow></max>' % (
        _v(1), _p('ap/leg-dn-ft'), _p('ap/leg-dn-ft'), _p('ap/leg-de-ft'), _p('ap/leg-de-ft'), _v(0.5))))
    ch.append(_fn('ap/leg-course-deg', '        <todegrees><atan2>%s%s</atan2></todegrees>' % (_p('ap/leg-de-ft'), _p('ap/leg-dn-ft')), 'the leg\'s course, east of north'))
    ch.append(_fn('ap/pos-n-ft', _op('product', _v(FT_PER_DEG), '<difference>%s%s</difference>' % (_p(lat), _p('ap/leg-lat0-deg')))))
    ch.append(_fn('ap/pos-e-ft', _op('product', _v(FT_PER_DEG), coslat, '<difference>%s%s</difference>' % (_p(lon), _p('ap/leg-lon0-deg')))))
    ch.append(_fn('ap/leg-togo-ft', '        <difference>%s<quotient><sum><product>%s%s</product><product>%s%s</product></sum>%s</quotient></difference>' % (
        _p('ap/leg-length-ft'), _p('ap/pos-n-ft'), _p('ap/leg-dn-ft'), _p('ap/pos-e-ft'), _p('ap/leg-de-ft'), _p('ap/leg-length-ft')), 'distance to the end of the leg'))
    ch.append(_fn('ap/leg-xt-ft', '        <quotient><difference><product>%s%s</product><product>%s%s</product></difference>%s</quotient>' % (
        _p('ap/pos-e-ft'), _p('ap/leg-dn-ft'), _p('ap/pos-n-ft'), _p('ap/leg-de-ft'), _p('ap/leg-length-ft')), 'cross-track error, right of the leg positive'))
    ch.append(_fn('ap/ground-speed-kt', _op('product', _v(1 / 1.6878099), _p('velocities/vg-fps'))))
    ch.append(_fn('ap/ground-track-deg', '        <todegrees><atan2>%s%s</atan2></todegrees>' % (_p('velocities/v-east-fps'), _p('velocities/v-north-fps'))))

    def intercept(name, per_second, least):
        """the wanted course: the leg's, turned towards the leg by atan(cross-track / lookahead), 45 deg at most"""
        return _fn(name, '''        <difference>
          %s
          <max>%s<min>%s<todegrees><atan><quotient>%s<max>%s<product>%s%s</product></max></quotient></atan></todegrees></min></max>
        </difference>''' % (_p('ap/leg-course-deg'), _v(-45), _v(45), _p('ap/leg-xt-ft'), _v(least), _v(per_second), _p('velocities/vg-fps')))

    def wrapped(name, a, b, desc=''):
        return _fn(name, '''        <difference>
          <mod><sum><difference>%s%s</difference>%s</sum>%s</mod>
          %s
        </difference>''' % (_p(a), _p(b), _v(540), _v(360), _v(180)), desc)
    ch.append(intercept('ap/track-cmd-deg', 15.0, 3000.0))
    ch.append(wrapped('ap/track-error-deg', 'ap/track-cmd-deg', 'ap/ground-track-deg', 'wanted course less ground track'))
    ch.append(intercept('ap/ground-course-cmd-deg', 4.0, 60.0))
    ch.append(wrapped('ap/ground-error-deg', 'ap/ground-course-cmd-deg', 'attitude/psi-deg', 'wanted course less heading, on the ground'))
    # ---- part B: landing phases
    ch.append(_fn('ap/on-mains', _op('sum', _p('gear/unit[1]/WOW'), _p('gear/unit[2]/WOW'))))
    ch.append('''    <switch name="ap/latch-rollout">
      <description>on the runway: set by weight on a main wheel while landing, cleared when landing is switched off</description>
      <default value="ap/rollout"/>
      <test value="0">ap/land-mode == 0</test>
      <test logic="AND" value="1">
        ap/land-mode == 1
        ap/on-mains gt 0
      </test>
      <output>ap/rollout</output>
    </switch>
    <switch name="ap/flare">
      <default value="0"/>
      <test logic="AND" value="1">
        ap/land-mode == 1
        ap/rollout == 0
        aero/wheel-height-ft lt %g
      </test>
    </switch>''' % FLARE_HEIGHT)
    ch.append(_fn('ap/approach-keas', '        <quotient><pow><quotient>%s%s</quotient>%s</pow>%s</quotient>' % (
        _p('inertia/weight-lbs'), _v(APPROACH_CL * WING_AREA * 0.5 * 0.0023769), _v(0.5), _v(1.6878099)),
        'the speed for a lift coefficient of %g at this weight' % APPROACH_CL))
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
      <test value="ap/theta-flare-deg">ap/flare == 1</test>
      <test value="ap/theta-takeoff-deg">ap/pitch-mode == 3</test>
      <test value="ap/theta-speed-deg">ap/pitch-mode == 1</test>
      <test value="ap/theta-alt-deg">ap/pitch-mode == 2</test>
    </switch>''')
    ch.insert(len(ch) - 1, _fn('ap/theta-cmd-less-latched', _op('difference', _p('ap/theta-cmd-deg'), _p('ap/theta-latched-deg'))))
    ch.insert(len(ch) - 1, _fn('ap/theta-flare-deg', _op('difference', _v(FLARE_PITCH), _p('ap/theta-latched-deg')), 'the flare\'s pitch attitude'))
    ch.insert(len(ch) - 1, _fn('ap/theta-takeoff-deg', '''        <ifthen>
          <or><ge>%s%s</ge><gt>%s%s</gt></or>
          <difference>%s%s</difference>
          %s
        </ifthen>''' % (_p('velocities/vc-kts'), _v(ROTATE_KIAS), _p('aero/wheel-height-ft'), _v(3), _v(ROTATE_PITCH), _p('ap/theta-latched-deg'), _v(0)),
                                 'takeoff: the attitude on the ground until %g KIAS, then %g deg' % (ROTATE_KIAS, ROTATE_PITCH)))
    # ---- the pitch command governor: the command is a state that moves towards what the mode asks at 2 deg/s at
    # most, and is pulled down, whatever the mode asks, while the angle of attack is over its limit or the speed is
    # under its floor. Being a rate, it has nothing to wind up and nothing to release with a jump.
    ch.append(_fn('ap/alpha-margin-deg', _op('difference', _p('ap/alpha-limit-deg'), _p('aero/alpha-deg')), 'room under the angle-of-attack limit'))
    ch.append(_fn('ap/speed-margin-kt', '''        <ifthen>
          <gt>%s%s</gt>
          %s
          <difference>%s<difference>%s%s</difference></difference>
        </ifthen>''' % (_p('ap/on-mains'), _v(0), _v(50), _p('velocities/vc-kts'), _p('ap/speed-target-kcas'), _v(15)),
                  'room above the lowest speed allowed: 15 kt under the commanded speed. Not on the ground: a takeoff starts from rest'))
    ch.append(_fn('ap/protect-fast-deg', '        <product>%s<max>%s<difference>%s%s</difference></max></product>' % (
        _v(200.0), _v(0), _p('velocities/mach'), _v(0.63)), 'nose up above Mach 0.63'))
    ch.append(_fn('ap/theta-rate-deg_sec', '''        <max>
          <max>%s<product>%s<difference>%s%s</difference></product></max>
          <min>
            <product>%s<difference>%s%s</difference></product>
            <min>%s<max>%s<product>%s<difference><sum>%s%s</sum>%s</difference></product></max></min>
            <product>%s%s</product>
            <product>%s%s</product>
          </min>
        </max>''' % (_v(-6), _v(10), _v(-16), _p('ap/theta-delta-deg'), _v(10), _v(18), _p('ap/theta-delta-deg'),
                     _v(3), _v(-3), _v(2.0), _p('ap/theta-mode-deg'), _p('ap/protect-fast-deg'), _p('ap/theta-delta-deg'),
                     _v(G['K_alpha']), _p('ap/alpha-margin-deg'), _v(G['K_slow']), _p('ap/speed-margin-kt')),
                  'how fast the pitch command moves: towards the mode\'s, or down for angle of attack or speed, whichever is lowest; and never past -16 or +18 deg (the integrator behind it has no limit of its own)'))
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
    # the pitch integral runs in the air, and on the ground only from 5 kt under the rotation speed: left running
    # through a taxi it winds up against the nose wheel and then holds the nose down at rotation (it did: the first
    # mission left the ground at 249 kt)
    ch.append('''    <switch name="ap/trig-pitch">
      <default value="-1"/>
      <test logic="AND" value="0">
        ap/engaged == 1
        ap/on-mains == 0
      </test>
      <test logic="AND" value="0">
        ap/engaged == 1
        velocities/vc-kts ge %g
        ap/rollout == 0
      </test>
    </switch>''' % (ROTATE_KIAS - 5.0))
    ch.append(_pid('ap/pitch-pi-deg', 'ap/theta-error-deg', 'ap/k-theta', 'ap/k-theta-i', 'pitch', clip=('-25', '25')))
    ch.append(_fn('ap/pitch-law-deg', '        <sum>%s%s<product>%s%s%s</product></sum>' % (
        _p('ap/bias-pitch-deg'), _p('ap/pitch-pi-deg'), _p('ap/k-q'), _v(57.29578), _p('velocities/q-rad_sec')),
        'ruddervators together, trailing edge down positive', clip=('-20', '20')))
    ch.append('''    <switch name="ap/pitch-out-deg">
      <description>on the runway after landing: 3 deg nose-down</description>
      <default value="ap/pitch-law-deg"/>
      <test value="3">ap/rollout == 1</test>
    </switch>''')
    # ---- basic law: roll
    ch.append(_fn('ap/heading-error-deg', '''        <difference>
          <mod><sum><difference>%s%s</difference>%s</sum>%s</mod>
          %s
        </difference>''' % (_p('ap/heading-cmd-deg'), _p('attitude/psi-deg'), _v(540), _v(360), _v(180)), 'right of the nose is positive'))
    ch.append(_fn('ap/bank-heading-deg', _op('product', _v(G['K_psi']), _p('ap/heading-error-deg'), '<quotient>%s%s</quotient>' % (_p('velocities/vt-fps'), _v(600)))))
    ch.append(_fn('ap/bank-track-deg', _op('product', _v(G['K_psi']), _p('ap/track-error-deg'), '<quotient>%s%s</quotient>' % (_p('velocities/vt-fps'), _v(600)))))
    ch.append('''    <switch name="ap/bank-mode-deg">
      <default value="ap/bank-cmd-deg"/>
      <test value="0">ap/on-mains gt 0</test>
      <test value="ap/bank-heading-deg">ap/roll-mode == 1</test>
      <test value="ap/bank-track-deg">ap/roll-mode == 2</test>
    </switch>''')
    ch.append(_fn('ap/bank-command-limit-deg', _op('product', _p('ap/bank-limit-deg'), _v(BANK_COMMAND)),
                  'the bank command stops at %g of the limit: turning, the bank overshoots its command and then settles '
                  'above it (a proportional law; an integral was tried and overshot)' % BANK_COMMAND))
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
    ch.append(_fn('ap/beta-gated-deg', '        <product>%s<max>%s<min>%s<quotient><difference>%s%s</difference>%s</quotient></min></max></product>' % (
        _p('aero/beta-deg'), _v(0), _v(1), _p('velocities/vc-kts'), _v(40), _v(20)), 'sideslip, faded out below 60 kt: it means nothing at a walk'))
    ch.append(_pid('ap/yaw-beta-deg', 'ap/beta-gated-deg', 'ap/k-beta', 'ap/k-beta-i', 'beta', clip=('-12', '12')))
    ch.append(_fn('ap/yaw-ground-deg', _op('product', _p('ap/ground-steer'), '<min>%s%s</min>' % (_v(1), _p('ap/on-mains')), _v(0.5), _p('ap/ground-error-deg')),
                  'on the ground the ruddervators help the nose wheel', clip=('-10', '10')))
    ch.append(_fn('ap/yaw-law-deg', '''        <sum>
          %s
          <product>%s%s%s%s</product>
          %s
          <product>%s%s</product>
          %s
        </sum>''' % (_p('ap/bias-yaw-deg'), _v(-1), _p('ap/k-r'), _v(57.29578), _p('ap/yaw-rate-washed'), _p('ap/yaw-beta-deg'),
                     _v(-G['K_ari']), _p('ap/roll-law-deg'), _p('ap/yaw-ground-deg')),
                  'ruddervators against each other, nose right positive: damper, sideslip to zero (interconnect with the ailerons: gain 0 for now)', clip=('-20', '20')))
    # ---- thrust
    ch.append(_fn('ap/thrust-error-kt', _op('difference', _p('ap/speed-target-kcas'), _p('velocities/vc-kts')), 'slow is positive'))
    ch.append(_trigger('thrust', 'ap/thrust-mode == 3'))
    ch.append(_pid('ap/thrust-pi', 'ap/thrust-error-kt', G['K_thr'], G['K_thr_i'], 'thrust', clip=('-1', '1')))
    ch.append(_fn('ap/thrust-speed', _op('sum', _p('ap/bias-throttle'), _p('ap/thrust-pi')), clip=('0', '1')))
    ch.append(_fn('ap/taxi-error-kt', _op('difference', _p('ap/taxi-speed-kt'), _p('ap/ground-speed-kt'))))
    ch.append(_trigger('taxi', 'ap/thrust-mode == 4', 'ap/taxi-speed-kt gt 0.5'))
    ch.append(_pid('ap/taxi-throttle', 'ap/taxi-error-kt', 0.03, 0.003, 'taxi', clip=('0', '0.4')))
    ch.append('''    <switch name="ap/thrust-law">
      <default value="ap/throttle-cmd"/>
      <test value="0">ap/land-mode == 1</test>
      <test value="ap/taxi-throttle">ap/thrust-mode == 4</test>
      <test value="1">ap/thrust-mode == 1</test>
      <test value="0">ap/thrust-mode == 2</test>
      <test value="ap/thrust-speed">ap/thrust-mode == 3</test>
    </switch>
    <switch name="ctl/throttle-norm">
      <description>what the engine takes: the laws' throttle when engaged, the throttle command otherwise</description>
      <default value="fcs/throttle-cmd-norm"/>
      <test value="ap/thrust-law">ap/engaged == 1</test>
    </switch>''')
    # ---- part B: the glide path on spoilers
    ch.append(_fn('ap/glide-height-ft', '        <sum>%s%s<product>%s<max>%s%s</max></product></sum>' % (
        _p('ap/rwy-elev-ft'), _v(5.3), _v(GLIDE_TAN), _v(0), _p('ap/leg-togo-ft')), 'height of the glide path here: the leg ends at the aiming point'))
    ch.append(_fn('ap/glide-error-ft', _op('difference', _p('position/h-sl-ft'), _p('ap/glide-height-ft')), 'high is positive', clip=('-300', '300')))
    ch.append(_fn('ap/glide-sink-error-fps', '        <sum>%s<product>%s%s</product></sum>' % (_p('velocities/h-dot-fps'), _v(GLIDE_TAN), _p('velocities/vg-fps')),
                  'sinking less than the path asks is positive'))
    ch.append(_trigger('glide', 'ap/land-mode == 1', 'ap/flare == 0', 'ap/rollout == 0'))
    ch.append(_pid('ap/glide-i', 'ap/glide-error-ft', 0.0, 0.0004, 'glide', clip=('-0.25', '0.25')))
    ch.append(_fn('ap/spoiler-glide', '        <sum>%s<product>%s%s</product><product>%s%s</product>%s</sum>' % (
        _v(SPOILER_BASE), _v(0.004), _p('ap/glide-error-ft'), _v(0.02), _p('ap/glide-sink-error-fps'), _p('ap/glide-i')),
        'spoilers hold the glide path: more when high or sinking too little', clip=('0.10', '1')))
    ch.append('''    <switch name="ap/latch-spoiler-base">
      <description>the spoiler setting at the start of the flare</description>
      <default value="ap/spoiler-base"/>
      <test value="ap/spoiler-glide">ap/flare == 0</test>
      <output>ap/spoiler-base</output>
    </switch>''')
    ch.append(_fn('ap/flare-sink-wanted-fps', '        <max>%s<product>%s%s<quotient>%s%s</quotient></product></max>' % (
        _v(FLARE_SINK), _v(GLIDE_TAN), _p('velocities/vg-fps'), _p('aero/wheel-height-ft'), _v(FLARE_HEIGHT)),
        'the sink wanted in the flare: the approach\'s, falling with height to %.1f ft/s at the ground' % FLARE_SINK))
    ch.append(_fn('ap/spoiler-flare', '        <sum>%s<product>%s<sum>%s%s</sum></product></sum>' % (
        _p('ap/spoiler-base'), _v(0.25), _p('velocities/h-dot-fps'), _p('ap/flare-sink-wanted-fps')),
        'in the flare the spoilers work on sink rate alone: they come in as far as the sink needs', clip=('0.10', '1')))
    ch.append('''    <switch name="ap/spoiler-law">
      <default value="ctl/manual-spoiler-norm"/>
      <test value="1">ap/rollout == 1</test>
      <test value="ap/spoiler-flare">ap/flare == 1</test>
      <test value="ap/spoiler-glide">ap/land-mode == 1</test>
      <test value="ap/spoiler-cmd">ap/spoiler-mode == 1</test>
    </switch>
    <switch name="ap/sel-spoiler">
      <default value="ctl/manual-spoiler-norm"/>
      <test value="ap/spoiler-law">ap/engaged == 1</test>
    </switch>
    <actuator name="ap/act-spoiler">
      <input>ap/sel-spoiler</input>
      <lag>10</lag>
      <rate_limit>0.667</rate_limit>
      <clipto><min>0</min><max>1</max></clipto>
    </actuator>
    <switch name="ctl/spoiler-norm">
      <description>spoilers, 0 to 1 (1 is 45 deg)</description>
      <default value="ap/act-spoiler"/>
      <test value="ap/sel-spoiler">ctl/instant == 1</test>
    </switch>''')
    # ---- part B: brakes and nose-wheel steering
    ch.append(_fn('ap/decel-error-g', '        <sum>%s<quotient>%s%s</quotient></sum>' % (_v(DECEL_G), _p('accelerations/udot-ft_sec2'), _v(32.174)), 'wanted deceleration less the present one'))
    ch.append(_trigger('decel', 'ap/rollout == 1', 'gear/unit[0]/WOW == 1', 'ap/ground-speed-kt gt 15'))
    ch.append(_pid('ap/brake-decel', 'ap/decel-error-g', 0.0, 0.8, 'decel', clip=('0', '1')))
    ch.append(_fn('ap/brake-taxi', '''        <ifthen>
          <and><lt>%s%s</lt><lt>%s%s</lt></and>
          %s
          <product>%s<difference><difference>%s%s</difference>%s</difference></product>
        </ifthen>''' % (_p('ap/taxi-speed-kt'), _v(0.5), _p('ap/ground-speed-kt'), _v(1.5), _v(1), _v(0.6), _p('ap/ground-speed-kt'), _p('ap/taxi-speed-kt'), _v(0.2)),
                  'taxi: brakes when over the speed, held on when stopped', clip=('0', '1')))
    ch.append('''    <switch name="ap/brake-law">
      <default value="0"/>
      <test value="ap/brake-decel">ap/rollout == 1</test>
      <test value="ap/brake-taxi">ap/thrust-mode == 4</test>
    </switch>''')
    for side in ('left', 'right'):
        ch.append(_fn('ap/brake-%s' % side, '        <ifthen><eq>%s%s</eq>%s%s</ifthen>' % (_p('ap/engaged'), _v(1), _p('ap/brake-law'), _p('fcs/%s-brake-cmd-norm' % side)),
                      out='fcs/%s-brake-cmd-norm' % side))
    ch.append(_fn('ap/steer-limit', '        <quotient>%s<max>%s%s</max></quotient>' % (_v(12), _v(1), _p('velocities/vg-fps')),
                  'nose-wheel travel allowed, falling with speed', clip=('0.08', '0.6')))
    ch.append(_fn('ap/steer-law', '''        <max>
          <product>%s%s</product>
          <min>%s<difference><product>%s%s</product><product>%s%s</product></difference></min>
        </max>''' % (_v(-1), _p('ap/steer-limit'), _p('ap/steer-limit'), _v(0.02), _p('ap/ground-error-deg'), _v(0.8), _p('velocities/r-rad_sec'))))
    ch.append(_fn('ap/steer-out-deg', '''        <product>
          %s
          <ifthen><and><eq>%s%s</eq><eq>%s%s</eq></and>%s%s</ifthen>
        </product>''' % (_v(60), _p('ap/engaged'), _v(1), _p('ap/ground-steer'), _v(1), _p('ap/steer-law'), _p('fcs/steer-cmd-norm')),
                  'the nose wheel: the law\'s when steering on the ground, the direct command otherwise', out='fcs/steer-pos-deg'))
    # ---- surfaces
    ch.append(_final('pitch-deg', 'ap/pitch-out-deg', 'ctl/manual-pitch-deg', 'both ruddervators, trailing edge down positive: nose down'))
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
