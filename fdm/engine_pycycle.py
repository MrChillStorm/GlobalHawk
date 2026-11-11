#!/usr/bin/env python3
"""A second model of the AE 3007, in NASA's pyCycle, to check fdm/engine.py where no data reaches.

pyCycle is a tool here, set up by fdm/mkpycycle.sh in tools/pycycle/ (not in the repository). The cycle below is
laid out as pyCycle's own example of a two-spool high-bypass turbofan (example_cycles/high_bypass_turbofan.py in
its repository), without that example's booster, which the AE 3007 doesn't have: a booster left in with no
pressure rise runs off its map and spoils the solution. The component maps are pyCycle's generic ones. Differences from fdm/engine.py that matter: real component maps (so
efficiencies and the bypass ratio move off design), turbine cooling flows, and gas properties from pyCycle's
tables for air and Jet-A (its chemical-equilibrium method doesn't run under NumPy 2 without more patching).

  design point   the ICAO takeoff row of the AE 3007A2 (sea level, static: 42.23 kN, pressure ratio 20.2, bypass
                 ratio 4.79), fan pressure ratio as fdm/engine.py; turbine entry temperature a round 3,000 R
  not modelled   customer bleed and power offtake (a bare engine, like the ICAO test)

    qrun python3 fdm/engine_pycycle.py          about ten minutes; prints the comparison, writes fdm/out/engine_pycycle.json
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, '..', 'tools', 'pycycle')
if not os.path.isdir(os.path.join(TOOL, 'lib', 'pycycle')):
    sys.exit('pyCycle is not set up: run fdm/mkpycycle.sh first')
sys.path.insert(0, os.path.join(TOOL, 'lib'))
sys.path.insert(0, HERE)

os.environ.setdefault('OPENMDAO_REPORTS', '0')      # no report folders
os.environ.setdefault('OPENMDAO_WORKDIR', os.path.join(HERE, 'out'))   # its scratch folder goes with our outputs
import openmdao.api as om                        # noqa: E402
import pycycle.api as pyc                        # noqa: E402
import engine as E                               # noqa: E402  our cycle model

LBF = E.LBF
FAN_PR = 1.758
# Turbine entry temperature at the design point. At the 1,380 K of fdm/engine.py this cycle has no solution: its
# component efficiencies are lower and a quarter of the core flow goes to turbine cooling. 3,000 R (1,667 K) is a
# round value at which it solves; nothing is tuned to it.
DESIGN_T4_R = 3000.0
A2 = E.ICAO['AE3007A2']
# The off-design point starts in flight (the solver doesn't start well at rest) and is walked to each condition.
START = (10000.0, 0.4, 5000.0)                   # ft, Mach, lbf
OD_AIR_GUESS = 200.0                             # lbm/s there, to start the solver


class Cycle(pyc.Cycle):
    """Fan, splitter, high-pressure compressor, burner, two turbines, two nozzles, two shafts."""

    def initialize(self):
        self.options.declare('throttle_mode', default='T4', values=['T4', 'percent_thrust'])
        super().initialize()

    def setup(self):
        design = self.options['design']
        self.options['thermo_method'] = 'TABULAR'           # the chemical-equilibrium method fails under NumPy 2
        self.options['thermo_data'] = pyc.AIR_JETA_TAB_SPEC
        add = self.add_subsystem
        add('fc', pyc.FlightConditions())
        add('inlet', pyc.Inlet())
        add('fan', pyc.Compressor(map_data=pyc.FanMap, bleed_names=[], map_extrap=True), promotes_inputs=[('Nmech', 'LP_Nmech')])
        add('splitter', pyc.Splitter())
        add('duct4', pyc.Duct())
        add('hpc', pyc.Compressor(map_data=pyc.HPCMap, bleed_names=['cool1', 'cool2', 'cust'], map_extrap=True),
            promotes_inputs=[('Nmech', 'HP_Nmech')])
        add('bld3', pyc.BleedOut(bleed_names=['cool3', 'cool4']))
        add('burner', pyc.Combustor(fuel_type='FAR'))
        add('hpt', pyc.Turbine(map_data=pyc.HPTMap, bleed_names=['cool3', 'cool4'], map_extrap=True),
            promotes_inputs=[('Nmech', 'HP_Nmech')])
        add('duct11', pyc.Duct())
        add('lpt', pyc.Turbine(map_data=pyc.LPTMap, bleed_names=['cool1', 'cool2'], map_extrap=True),
            promotes_inputs=[('Nmech', 'LP_Nmech')])
        add('duct13', pyc.Duct())
        add('core_nozz', pyc.Nozzle(nozzType='CV', lossCoef='Cv'))
        add('byp_bld', pyc.BleedOut(bleed_names=['bypBld']))
        add('duct15', pyc.Duct())
        add('byp_nozz', pyc.Nozzle(nozzType='CV', lossCoef='Cv'))
        add('lp_shaft', pyc.Shaft(num_ports=2), promotes_inputs=[('Nmech', 'LP_Nmech')])
        add('hp_shaft', pyc.Shaft(num_ports=2), promotes_inputs=[('Nmech', 'HP_Nmech')])
        add('perf', pyc.Performance(num_nozzles=2, num_burners=1))
        for a, b in (('inlet.Fl_O:tot:P', 'perf.Pt2'), ('hpc.Fl_O:tot:P', 'perf.Pt3'), ('burner.Wfuel', 'perf.Wfuel_0'),
                     ('inlet.F_ram', 'perf.ram_drag'), ('core_nozz.Fg', 'perf.Fg_0'), ('byp_nozz.Fg', 'perf.Fg_1'),
                     ('fan.trq', 'lp_shaft.trq_0'), ('lpt.trq', 'lp_shaft.trq_1'), ('hpc.trq', 'hp_shaft.trq_0'),
                     ('hpt.trq', 'hp_shaft.trq_1'), ('fc.Fl_O:stat:P', 'core_nozz.Ps_exhaust'),
                     ('fc.Fl_O:stat:P', 'byp_nozz.Ps_exhaust')):
            self.connect(a, b)
        bal = add('balance', om.BalanceComp())
        if design:
            # air flow for the thrust, fuel for the turbine entry temperature, turbine pressure ratios for the shafts
            bal.add_balance('W', units='lbm/s', eq_units='lbf')
            self.connect('balance.W', 'fc.W')
            self.connect('perf.Fn', 'balance.lhs:W')
            self.promotes('balance', inputs=[('rhs:W', 'Fn_DES')])
            bal.add_balance('FAR', eq_units='degR', lower=1e-4, val=.017)
            self.connect('balance.FAR', 'burner.Fl_I:FAR')
            self.connect('burner.Fl_O:tot:T', 'balance.lhs:FAR')
            self.promotes('balance', inputs=[('rhs:FAR', 'T4_MAX')])
            for t, sh in (('lpt', 'lp_shaft'), ('hpt', 'hp_shaft')):
                bal.add_balance(t + '_PR', val=1.5, lower=1.001, upper=8, eq_units='hp', use_mult=True, mult_val=-1)
                self.connect('balance.%s_PR' % t, t + '.PR')
                self.connect(sh + '.pwr_in_real', 'balance.lhs:%s_PR' % t)
                self.connect(sh + '.pwr_out_real', 'balance.rhs:%s_PR' % t)
        else:
            # fuel for the thrust (or the temperature), air flow and bypass ratio for the nozzle areas, speeds for the shafts
            if self.options['throttle_mode'] == 'T4':
                bal.add_balance('FAR', val=0.017, lower=1e-4, eq_units='degR')
                self.connect('burner.Fl_O:tot:T', 'balance.lhs:FAR')
                self.promotes('balance', inputs=[('rhs:FAR', 'T4_MAX')])
            else:
                bal.add_balance('FAR', val=0.017, lower=1e-4, eq_units='lbf', use_mult=True)
                self.connect('perf.Fn', 'balance.rhs:FAR')
                self.promotes('balance', inputs=[('mult:FAR', 'PC'), ('lhs:FAR', 'Fn_max')])
            self.connect('balance.FAR', 'burner.Fl_I:FAR')
            bal.add_balance('W', units='lbm/s', lower=5., upper=1000., eq_units='inch**2')
            self.connect('balance.W', 'fc.W')
            self.connect('core_nozz.Throat:stat:area', 'balance.lhs:W')
            bal.add_balance('BPR', lower=2., upper=10., eq_units='inch**2')
            self.connect('balance.BPR', 'splitter.BPR')
            self.connect('byp_nozz.Throat:stat:area', 'balance.lhs:BPR')
            for n, sh, prom in (('lp_Nmech', 'lp_shaft', 'LP_Nmech'), ('hp_Nmech', 'hp_shaft', 'HP_Nmech')):
                bal.add_balance(n, val=1.5, units='rpm', lower=500., eq_units='hp', use_mult=True, mult_val=-1)
                self.connect('balance.' + n, prom)
                self.connect(sh + '.pwr_in_real', 'balance.lhs:' + n)
                self.connect(sh + '.pwr_out_real', 'balance.rhs:' + n)
        for a, b in (('fc.Fl_O', 'inlet.Fl_I'), ('inlet.Fl_O', 'fan.Fl_I'), ('fan.Fl_O', 'splitter.Fl_I'),
                     ('splitter.Fl_O1', 'duct4.Fl_I'), ('duct4.Fl_O', 'hpc.Fl_I'), ('hpc.Fl_O', 'bld3.Fl_I'),
                     ('bld3.Fl_O', 'burner.Fl_I'), ('burner.Fl_O', 'hpt.Fl_I'), ('hpt.Fl_O', 'duct11.Fl_I'),
                     ('duct11.Fl_O', 'lpt.Fl_I'), ('lpt.Fl_O', 'duct13.Fl_I'), ('duct13.Fl_O', 'core_nozz.Fl_I'),
                     ('splitter.Fl_O2', 'byp_bld.Fl_I'), ('byp_bld.Fl_O', 'duct15.Fl_I'), ('duct15.Fl_O', 'byp_nozz.Fl_I')):
            self.pyc_connect_flow(a, b)
        for a, b in (('hpc.cool1', 'lpt.cool1'), ('hpc.cool2', 'lpt.cool2'), ('bld3.cool3', 'hpt.cool3'), ('bld3.cool4', 'hpt.cool4')):
            self.pyc_connect_flow(a, b, connect_stat=False)
        newton = self.nonlinear_solver = om.NewtonSolver()
        newton.options.update(dict(atol=1e-8, rtol=1e-99, iprint=-1, maxiter=50, solve_subsystems=True, max_sub_solves=1000,
                                   reraise_child_analysiserror=False))
        ls = newton.linesearch = om.ArmijoGoldsteinLS()
        ls.options['maxiter'] = 3
        ls.options['rho'] = 0.75
        self.linear_solver = om.DirectSolver()
        super().setup()


class Engine(pyc.MPCycle):
    """The cycle at its design point and at one off-design point throttled to a thrust."""

    def setup(self):
        self.pyc_add_pnt('DESIGN', Cycle())
        for name, mn in (('inlet', 0.60), ('fan', 0.4578), ('splitter', None), ('duct4', 0.3121),
                         ('hpc', 0.2442), ('bld3', 0.3000), ('burner', 0.1025), ('hpt', 0.3650),
                         ('duct11', 0.3063), ('lpt', 0.4127), ('duct13', 0.4463), ('byp_bld', 0.4489), ('duct15', 0.4589)):
            if mn is not None:
                self.set_input_defaults('DESIGN.%s.MN' % name, mn)
        self.set_input_defaults('DESIGN.splitter.BPR', A2['bpr'])
        self.set_input_defaults('DESIGN.splitter.MN1', 0.3104)
        self.set_input_defaults('DESIGN.splitter.MN2', 0.4518)
        self.set_input_defaults('DESIGN.LP_Nmech', 8700.0, units='rpm')      # nominal: only ratios of speed are used
        self.set_input_defaults('DESIGN.HP_Nmech', 16000.0, units='rpm')
        # losses and turbine cooling as in pyCycle's example; no customer bleed, no power offtake
        for name, val in (('inlet.ram_recovery', 0.9990), ('duct4.dPqP', 0.0048),
                          ('burner.dPqP', 0.0540), ('duct11.dPqP', 0.0051), ('duct13.dPqP', 0.0107),
                          ('duct15.dPqP', 0.0149), ('core_nozz.Cv', 0.9933), ('byp_bld.bypBld:frac_W', 0.005),
                          ('byp_nozz.Cv', 0.9939), ('hpc.cool1:frac_W', 0.050708), ('hpc.cool1:frac_P', 0.5),
                          ('hpc.cool1:frac_work', 0.5), ('hpc.cool2:frac_W', 0.020274), ('hpc.cool2:frac_P', 0.55),
                          ('hpc.cool2:frac_work', 0.5), ('bld3.cool3:frac_W', 0.067214), ('bld3.cool4:frac_W', 0.101256),
                          ('hpc.cust:frac_P', 0.5), ('hpc.cust:frac_work', 0.5), ('hpc.cust:frac_W', 0.0),
                          ('hpt.cool3:frac_P', 1.0), ('hpt.cool4:frac_P', 0.0), ('lpt.cool1:frac_P', 1.0),
                          ('lpt.cool2:frac_P', 0.0)):
            self.pyc_add_cycle_param(name, val)
        self.pyc_add_cycle_param('hp_shaft.HPX', 0.0, units='hp')
        self.pyc_add_pnt('OD', Cycle(design=False, throttle_mode='percent_thrust'))
        self.set_input_defaults('OD.fc.MN', START[1])
        self.set_input_defaults('OD.fc.alt', START[0], units='ft')
        self.set_input_defaults('OD.fc.dTs', 0.0, units='degR')
        self.set_input_defaults('OD.PC', 1.0)
        self.set_input_defaults('OD.Fn_max', START[2], units='lbf')
        self.pyc_use_default_des_od_conns()
        self.pyc_connect_des_od('core_nozz.Throat:stat:area', 'balance.rhs:W')
        self.pyc_connect_des_od('byp_nozz.Throat:stat:area', 'balance.rhs:BPR')
        super().setup()


class Model:
    def __init__(self, T4_R=2500.0, quiet=True):
        self.prob = p = om.Problem()
        p.model = Engine()
        p.setup()
        p.set_val('DESIGN.fan.PR', FAN_PR)
        p.set_val('DESIGN.fan.eff', 0.8948)
        p.set_val('DESIGN.hpc.PR', A2['opr'] / FAN_PR)
        p.set_val('DESIGN.hpc.eff', 0.8707)
        p.set_val('DESIGN.hpt.eff', 0.8888)
        p.set_val('DESIGN.lpt.eff', 0.8996)
        p.set_val('DESIGN.fc.alt', 0.0, units='ft')
        p.set_val('DESIGN.fc.MN', 0.001)
        p.set_val('DESIGN.T4_MAX', T4_R, units='degR')
        p.set_val('DESIGN.Fn_DES', A2['thrust'] / LBF, units='lbf')
        p['DESIGN.balance.FAR'] = 0.02
        p['DESIGN.balance.W'] = 280.0
        p['DESIGN.balance.lpt_PR'] = 4.0
        p['DESIGN.balance.hpt_PR'] = 3.0
        p['DESIGN.fc.balance.Pt'] = 14.7
        p['DESIGN.fc.balance.Tt'] = 518.67
        p['OD.balance.FAR'] = 0.02
        p['OD.balance.W'] = OD_AIR_GUESS
        p['OD.balance.BPR'] = A2['bpr']
        p['OD.balance.lp_Nmech'] = 8700.0
        p['OD.balance.hp_Nmech'] = 16000.0
        p['OD.hpt.PR'] = 3.0
        p['OD.lpt.PR'] = 4.0
        p['OD.fan.map.RlineMap'] = 2.0
        p['OD.hpc.map.RlineMap'] = 2.0
        p.set_solver_print(level=-1)
        self.state = START
        try:
            p.run_model()
        finally:
            self.design = self.read('DESIGN')
            if not quiet:
                print('design', {k: round(v, 4) for k, v in self.design.items()})

    def read(self, pt='OD'):
        p = self.prob
        g = lambda name, units=None: float(np.ravel(p.get_val('%s.%s' % (pt, name), units=units))[0])
        out = dict(thrust=g('perf.Fn', 'lbf'), fuel=g('burner.Wfuel', 'lbm/h'), opr=g('perf.OPR'), bpr=g('splitter.BPR'),
                   Tt4=g('burner.Fl_O:tot:T', 'degK'), air=g('inlet.Fl_O:stat:W', 'lbm/s'), fan_pr=g('fan.PR'),
                   Tt2=g('fan.Fl_I:tot:T', 'degK'))
        n = g('LP_Nmech', 'rpm') if pt == 'DESIGN' else g('balance.lp_Nmech', 'rpm')
        out['fan_corrected_speed'] = n / np.sqrt(out['Tt2'] / 288.15)
        out['tsfc'] = out['fuel'] / out['thrust']
        return out

    def at(self, alt, mach, thrust, steps=None):
        """Throttle the off-design point to a thrust (lbf) at a flight condition.

        The solver only follows small changes, so the point is walked there: altitude in steps of at most
        2,500 ft, Mach along with it, thrust in equal ratios (it falls with air pressure). A step that doesn't
        converge stops the run: a wrong number here would look like a result.
        """
        p = self.prob
        a0, m0, f0 = self.state
        mach = max(mach, 0.001)
        if steps is None:
            steps = max(int(np.ceil(abs(alt - a0) / 2500.0)), int(np.ceil(abs(mach - m0) / 0.1)),
                        int(np.ceil(abs(np.log(thrust / f0)) / 0.12)), 1)
        for k in range(1, steps + 1):
            w = k / steps
            target = f0 * (thrust / f0) ** w
            p.set_val('OD.fc.alt', a0 + w * (alt - a0), units='ft')
            p.set_val('OD.fc.MN', m0 + w * (mach - m0))
            p.set_val('OD.Fn_max', target, units='lbf')
            p.run_model()
            out = self.read()
            if not (np.isfinite(out['thrust']) and abs(out['thrust'] / target - 1) < 2e-3 and 1.0 < out['opr'] < 60.0):
                raise RuntimeError('pyCycle did not converge at %.0f ft, Mach %.3f, %.0f lbf (got %.3g lbf)' % (
                    a0 + w * (alt - a0), m0 + w * (mach - m0), target, out['thrust']))
            self.state = (a0 + w * (alt - a0), m0 + w * (mach - m0), target)
        out['ok'] = True
        return out


def fan_limit_thrust(m, alt, mach, speed, guess):
    """The thrust (lbf) at which the fan's corrected speed is the given one: secant steps on thrust."""
    f0, o0 = guess, m.at(alt, mach, guess)
    f1 = guess * (speed / o0['fan_corrected_speed']) ** 3
    o1 = m.at(alt, mach, f1)
    for _ in range(8):
        if abs(o1['fan_corrected_speed'] / speed - 1) < 2e-4:
            break
        slope = (o1['fan_corrected_speed'] - o0['fan_corrected_speed']) / (f1 - f0)
        f0, o0 = f1, o1
        f1 = f1 + (speed - o1['fan_corrected_speed']) / slope
        o1 = m.at(alt, mach, f1)
    return o1


def main():
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        e = E.validation()[0]                     # our model, with its limit and fits
        m = Model(T4_R=DESIGN_T4_R)
    d = m.design
    rows = []
    add = lambda tag, name, val, ref, lim, kind: rows.append((tag, name, val, ref, lim, kind))
    print('pyCycle design point: thrust %.0f lbf, air flow %.1f lbm/s (ours %.1f), turbine entry %.0f K (ours %.0f), '
          'bypass ratio %.2f, pressure ratio %.2f' % (d['thrust'], d['air'], e.ref['mdot'] / 0.45359237, d['Tt4'],
                                                     e.ref['Tt4'], d['bpr'], d['opr']))
    add('X0', 'A2 takeoff (design point): fuel flow, lb/h', d['fuel'], A2['ff'][0] / E.LBH, 5.0, 'predicted')
    o = m.at(0, 0.0, 0.85 * A2['thrust'] / LBF)
    add('X0b', 'A2 fuel flow at ICAO 85 % thrust, lb/h', o['fuel'], A2['ff'][1] / E.LBH, 5.0, 'predicted')
    c1 = E.ICAO['AE3007C1']
    o = m.at(0, 0.0, c1['thrust'] / LBF)
    add('X1a', 'C1 takeoff as a rating: fuel flow, lb/h', o['fuel'], c1['ff'][0] / E.LBH, 5.0, 'predicted')
    add('X1b', 'C1 takeoff as a rating: pressure ratio', o['opr'], c1['opr'], 5.0, 'predicted')
    add('X1c', 'C1 takeoff as a rating: bypass ratio', o['bpr'], c1['bpr'], 5.0, 'predicted')
    lo, hi = E.GHAZI[0], E.GHAZI[-1]
    olo = m.at(lo['alt'], lo['mach'], lo['fn'])
    add('X2a', 'TSFC at 1,500 ft, M 0.234, lb/h/lbf', olo['tsfc'], lo['wf'] / lo['fn'], 8.0, 'predicted')
    ohi = m.at(hi['alt'], hi['mach'], hi['fn'])
    add('X2b', 'TSFC at 45,000 ft, M 0.564, lb/h/lbf', ohi['tsfc'], hi['wf'] / hi['fn'], 8.0, 'predicted')
    th = lambda g: (E.isa(g['alt'])[0] * (1 + 0.2 * g['mach'] ** 2)) / 288.15
    n1 = (hi['n1'] / np.sqrt(th(hi))) / (lo['n1'] / np.sqrt(th(lo)))
    add('X3', 'fan corrected speed, 45,000 ft over 1,500 ft', ohi['fan_corrected_speed'] / olo['fan_corrected_speed'], n1, 5.0, 'predicted')
    limit = ohi['fan_corrected_speed']
    print('pyCycle at Ghazi\'s 45,000 ft point: pressure ratio %.1f, bypass ratio %.2f, turbine entry %.0f K, fan speed '
          '%.3f of design (the limit, a fit as in our model: %.3f)' % (ohi['opr'], ohi['bpr'], ohi['Tt4'],
                                                                     limit / d['fan_corrected_speed'], e.fan_speed_max))
    table = []
    for alt in (50000, 55000, 60000, 65000):
        ours = e.at_fan_speed(alt, 0.6, e.fan_speed_max)
        f_ours, ts_ours = ours['thrust'] / LBF, ours['fuel_cycle'] / E.LBH / (ours['thrust'] / LBF)
        o = fan_limit_thrust(m, alt, 0.6, limit, f_ours)
        add('X4', 'maximum thrust at %d ft, M 0.6, lbf (ours)' % alt, o['thrust'], f_ours, 5.0, 'model against model')
        add('X4', 'bare TSFC at %d ft, M 0.6 (ours)' % alt, o['tsfc'], ts_ours, 5.0, 'model against model')
        if alt == 60000:
            add('X5', 'pressure ratio at the limit, 60,000 ft', o['opr'], 23.0, 10.0, 'predicted')
        table.append(dict(alt=alt, mach=0.6, pycycle=dict(thrust=o['thrust'], tsfc=o['tsfc'], opr=o['opr'], bpr=o['bpr'], Tt4=o['Tt4'],
                                                          converged=bool(o['ok'])),
                          ours=dict(thrust=f_ours, tsfc=ts_ours, opr=ours['opr'], bpr=ours['bpr'], Tt4=ours['Tt4'])))
        print('  %d ft: pyCycle %.0f lbf, TSFC %.3f, OPR %.1f, BPR %.2f, Tt4 %.0f K | ours %.0f lbf, TSFC %.3f, OPR %.1f, '
              'BPR %.2f, Tt4 %.0f K' % (alt, o['thrust'], o['tsfc'], o['opr'], o['bpr'], o['Tt4'], f_ours, ts_ours,
                                        ours['opr'], ours['bpr'], ours['Tt4']), flush=True)
    E.report(rows)
    os.makedirs(os.path.join(HERE, 'out'), exist_ok=True)
    json.dump(dict(design=d, limit_fan_speed=limit / d['fan_corrected_speed'], ghazi_45000=ohi, ghazi_1500=olo, table=table,
                   checks=[dict(tag=r[0], name=r[1], model=r[2], source=r[3], limit=r[4], kind=r[5]) for r in rows]),
              open(os.path.join(HERE, 'out', 'engine_pycycle.json'), 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
