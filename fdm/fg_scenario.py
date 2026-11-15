"""Fly a whole scenario in FlightGear, recorded: python3 fg_scenario.py AIRPORT RUNWAY OUT.csv [KEEP]

SCENARIO=box (default)  takeoff, a box at the height the station's planner picks, landing on the same runway (js/geo.js localPlan)
SCENARIO=ceiling        the whole fuel load (14,500 lb), a cruise-climb of about 22 h to 65,000 ft, a long descent, landing (scenario65.py): 27 h of flight, so a high SPEEDUP
METARWIND=31020KT       the wind at the field, from 310 at 20 kt (the METAR holds it); SPEEDUP=4 the sim's speed; DURATION the longest wait, s of real time
FlightGear starts on the runway, the plan is sent as a station would, heartbeats go, and the telemetry is written as CSV when the flight ends. One FlightGear at a time:
it refuses to start while one answers on port 5477. The screen must be unlocked.
"""
import asyncio, json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import phase9b_checks as B
import phase9a_checks as P9

airport, runway, out = sys.argv[1], sys.argv[2], sys.argv[3]
SCENARIO = os.environ.get('SCENARIO', 'box')
import scenario65
keep = len(sys.argv) > 4
log = os.path.join(os.path.dirname(out), 'fg-efhk.log')
B.LOG = log
J = '/fdm/jsbsim/'
KEYS = dict(
    alpha=J + 'aero/alpha-deg', alim=J + 'ap/alpha-limit-deg', tphase=J + 'ap/turn-phase', tlead=J + 'ap/turn-lead-ft', tdelta=J + 'ap/turn-delta-deg', capcap=J + 'ap/bank-alpha-cap-deg',
    gerrft=J + 'ap/glide-error-ft', serr=J + 'ap/glide-sink-error-fps', spoil=J + 'ctl/spoiler-norm', gi=J + 'ap/glide-i', pm=J + 'ap/pitch-mode', lm=J + 'ap/land-mode',
    togo=J + 'ap/leg-togo-ft', alt=J + 'position/h-sl-ft', hdot=J + 'velocities/h-dot-fps', keas=J + 'velocities/ve-kts', target=J + 'ap/speed-target-kcas', status='/gcs/down/status', flare=J + 'ap/flare', rollout=J + 'ap/rollout',
    t=J + 'simulation/sim-time-sec', xt=J + 'ap/leg-xt-ft', gerr=J + 'ap/ground-error-deg', gcmd=J + 'ap/ground-course-cmd-deg',
    legc=J + 'ap/leg-course-deg', psi=J + 'attitude/psi-deg', steer=J + 'fcs/steer-pos-deg', slaw=J + 'ap/steer-law', slim=J + 'ap/steer-limit',
    yawg=J + 'ap/yaw-ground-deg', rud=J + 'fcs/rudder-cmd-norm', r=J + 'velocities/r-rad_sec', vg=J + 'velocities/vg-fps',
    kcas=J + 'velocities/vc-kts', wh=J + 'aero/wheel-height-ft', phi=J + 'attitude/phi-deg', theta=J + 'attitude/theta-deg',
    thr=J + 'fcs/throttle-cmd-norm', thrust=J + 'engine/thrust-lbf', mains=J + 'ap/on-mains',
    wdir='/environment/wind-from-heading-deg', wspd='/environment/wind-speed-kt', lat='/position/latitude-deg', lon='/position/longitude-deg',
    hdg='/orientation/heading-deg', gtrk=J + 'ap/ground-track-deg', nz=J + 'accelerations/Nz', tm=J + 'ap/thrust-mode', thrn=J + 'ctl/throttle-norm', vscmd=J + 'ap/alt-vs-cmd-fps', altcmd=J + 'ap/alt-cmd-ft', spl=J + 'ap/spoiler-cmd', pred=J + 'ap/turn-bank-cmd-deg', xtnew=J + 'ap/turn-xt-new-ft',
    mach=J + 'velocities/mach', fuel=J + 'fuel/total-lbs', beta=J + 'aero/beta-deg', wn=J + 'atmosphere/total-wind-north-fps', we=J + 'atmosphere/total-wind-east-fps', tel=J + 'position/terrain-elevation-asl-ft',
    nae=J + 'moments/n-aero-lbsft', nto=J + 'moments/n-total-lbsft', sa0=J + 'gear/unit[0]/steering-angle-deg', sf1=J + 'gear/unit[1]/wheel-side-force',
    sf2=J + 'gear/unit[2]/wheel-side-force', sf0=J + 'gear/unit[0]/wheel-side-force', cmp0=J + 'gear/unit[0]/compression-ft', ay=J + 'accelerations/Ny',
    turb=J + 'atmosphere/turbulence/magnitude-norm', fgturb='/environment/turbulence/magnitude-norm', gust='/environment/gust-front-speed-kt')


async def main():
    if P9.get('/sim/globalhawk/started') is not None and not os.environ.get('ATTACH'):
        print('a FlightGear already answers on port 5477: not starting a second one', flush=True)
        return
    if P9.get('/sim/globalhawk/started') is not None and os.environ.get('ATTACH'):
        proc, took = None, 1                                  # one already up on the runway: use it
    else:
        proc, took = P9.start(['--airport=' + airport, '--runway=' + runway] + (['--metar=XXXX 012345Z %s 19SM SKC 15/M99 Q1013 NOSIG' % os.environ['METARWIND']] if os.environ.get('METARWIND') else []), log)
    print('FlightGear', 'up in %.0f s' % took if took else 'FAILED', flush=True)
    if not took:
        return
    try:
        c = B.Station()
        await c.connect()
        c.listen_to('/gcs/down/ack', '/gcs/down/status', *KEYS.values())
        await asyncio.sleep(1.0)       # the first station to speak holds control: do not let a station on the same port get there first
        here = [B.get('/position/latitude-deg'), B.get('/position/longitude-deg')]
        hdg = B.get('/orientation/heading-deg')
        elev = round(B.get('/position/altitude-ft') - B.get('/position/altitude-agl-ft'))
        print('on the runway at %.5f %.5f heading %.1f, elevation %d ft, wind from %s at %s kt' % (
            here[0], here[1], hdg, elev, B.get('/environment/wind-from-heading-deg'), B.get('/environment/wind-speed-kt')), flush=True)
        import subprocess
        if SCENARIO == 'ceiling':
            fuel_lb = float(os.environ.get('FUEL_LB', scenario65.FUEL_LB))
            tot = B.get(J + 'fuel/total-lbs')
            for i in range(6):                                    # the same share in every tank, down to the fuel asked for
                c = B.get(J + 'propulsion/tank[%d]/contents-lbs' % i)
                B.post(J + 'propulsion/tank[%d]/contents-lbs' % i, c * fuel_lb / tot)
            await asyncio.sleep(1.0)
        wt, fl = B.get(J + 'inertia/weight-lbs'), B.get(J + 'fuel/total-lbs')
        print('weight %.0f lb, fuel %.0f lb' % (wt, fl), flush=True)
        if SCENARIO == 'ceiling':
            plan = scenario65.plan65(tuple(here), hdg, elev)
        else:
            js = ("const geo = require('./js/geo.js'), pc = require('./js/plancheck.js'), P = require('./js/predict.js'), perf = require('./js/perfdata.js'); "
                  "const h = pc.localBoxFt([%.7f, %.7f], %.3f, %d, P.make(perf), { alt_ft: %d, weight_lb: %.0f, fuel_lb: %.0f }); "
                  "console.log(JSON.stringify(geo.localPlan([%.7f, %.7f], %.3f, %d, h)))") % (here[0], here[1], hdg, elev, elev + 100, wt, fl, here[0], here[1], hdg, elev)
            plan = json.loads(subprocess.run(['node', '-e', js], capture_output=True, text=True, cwd=os.path.join(HERE, '..', 'GlobalHawk', 'gcs'), check=True).stdout)
        json.dump(plan, open(os.path.splitext(out)[0] + '-plan.json', 'w'))
        print('%s: the route climbs to %d ft, the fix is at %d ft' % (plan['id'], max(p[2] for p in plan['items'][1]['points']), plan['items'][1]['points'][-1][2]), flush=True)
        print('wind now: from %.0f at %.1f kt (METAR holds it)' % (B.get('/environment/wind-from-heading-deg'), B.get('/environment/wind-speed-kt')), flush=True)
        if os.environ.get('METARWIND') and abs(B.get('/environment/wind-speed-kt') - float(os.environ['METARWIND'][3:5])) > 2:
            print('the wind is not what was set: stopping', flush=True)
            return
        a = await c.say('plan', plan)
        print('plan:', a and a.get('status'), a and a.get('reason'), flush=True)
        if not a or a.get('status') != 'accepted':
            print('the plan was not accepted: stopping', flush=True)
            return
        B.post('/sim/speed-up', float(os.environ.get('SPEEDUP', '4')))
        a = await c.say('start')
        print('start:', a and a.get('status'), a and a.get('reason'), flush=True)
        rows, t_lift, t0, t_end = [], None, time.monotonic(), None
        last_beat = 0
        while time.monotonic() - t0 < float(os.environ.get('DURATION', '1500')):
            v = {k: c.values.get(p) for k, p in KEYS.items()}
            if isinstance(v['t'], (int, float)):
                if v['t'] - last_beat >= 1.0:
                    c.heartbeat()
                    last_beat = v['t']
                rows.append(v)
                st = v.get('status') or ''
                if '\"doing\":\"plan complete' in st or 'rollout over' in st:
                    t_lift = t_lift or v['t']
                    t_end = t_end or v['t']
                try:
                    v['status'] = (json.loads(st).get('doing') or '').replace(',', ';') if st else ''
                except ValueError:
                    v['status'] = ''
                rows[-1] = v
                if t_end is not None and v['t'] > t_end + 8:
                    break
            await asyncio.sleep(0.1)
        with open(out, 'w') as fh:
            fh.write(','.join(KEYS) + '\n')
            seen = None
            for v in rows:
                if v['t'] != seen:
                    fh.write(','.join('' if v[k] is None else str(v[k]) for k in KEYS) + '\n')
                    seen = v['t']
        print('wrote %d rows to %s' % (len(rows), out), flush=True)
    finally:
        if not keep:
            P9.stop(proc)

asyncio.run(main())
