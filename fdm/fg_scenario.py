"""Fly a whole scenario in FlightGear, recorded: python3 fg_scenario.py AIRPORT RUNWAY OUT.csv [KEEP]

SCENARIO=box (default)  takeoff, a box at the height the station's planner picks, landing on the same runway (js/geo.js localPlan)
SCENARIO=taxibox        from a parking spot (PARKING=121: a name in the airport's ground network): taxi to the runway, take off, the box, land, taxi back to the spot (groundplan.py)
SCENARIO=ceiling        the whole fuel load (14,500 lb), a cruise-climb of about 22 h to 65,000 ft, a long descent, landing (scenario65.py): 27 h of flight, so a high SPEEDUP
FUEL_LB=1000            the fuel at the start, lb (the same share in every tank; the ceiling scenario's default is its whole load, the box's is the aircraft's own)
FUEL_IMBALANCE_LB=40    of that, this many lb moved from tank 0 to tank 1 (needs FUEL_LB): a rolling moment the roll law holds the wings level against, so the final drifts off the line and the stabilised-approach
                        gate has something to catch (flight 34's fuel, made on purpose)
SPEEDUP_LAND=0          the sim's speed from the landing start on (0, the default: SPEEDUP all the way through the landing; 1 is real time, to read the alerts, which last seconds)
GUSTS=0.85              gusts from the landing's start: FlightGear's turbulence magnitude (0 to 1; it goes to JSBSim as the MIL-F-8785C severity, magnitude squared times 7: 0.85 is 5, which broke the stabilised-approach gate in 11 of 12 headless landings;
                        0.9 is 6); GUSTS_EASE=0.3 (default) the magnitude once GUSTS_EASE_AFTER=90 s (of flight) have passed since the first MISSED APPROACH, so that the second approach can land;
                        GUSTS_EASE=-1: it stays (a landing abandoned ends the run). Needs a METAR for the steady wind (METARWIND=31028KT: a gust group in the METAR only raises the steady wind (28G45 gave 37 kt))
SHEAR_KT=75             a wind shear on the final: from the status SHEAR_AT ('descend to', the last leg's descent; 'level at' is the top of the climb) on, the wind at 500 ft over the field is raised to this many kt (SHEAR_DIR=310 deg; the surface wind stays the METAR's):
                        FlightGear's boundary layers carry the wind aloft (entry 1, 500 ft) and move it only 0.25 kt a second, so it is set 3 minutes before the glide; the gusts GUSTS give are the milspec
                        model's, which at low altitude are 0.1 times the wind at 20 ft whatever the severity (1.7 kt at 28 kt): too small to trouble the aircraft (the first gusty flight landed). On a missed
                        approach it eases (GUSTS_EASE_AFTER) back to SHEAR_EASE=36.4 kt from 315
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
import groundplan
PARKING = os.environ.get('PARKING', '121')
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
    hudalert='/sim/globalhawk/hud/alert', mach=J + 'velocities/mach', fuel=J + 'fuel/total-lbs', beta=J + 'aero/beta-deg', wn=J + 'atmosphere/total-wind-north-fps', we=J + 'atmosphere/total-wind-east-fps', tel=J + 'position/terrain-elevation-asl-ft',
    nae=J + 'moments/n-aero-lbsft', nto=J + 'moments/n-total-lbsft', sa0=J + 'gear/unit[0]/steering-angle-deg', sf1=J + 'gear/unit[1]/wheel-side-force',
    sf2=J + 'gear/unit[2]/wheel-side-force', sf0=J + 'gear/unit[0]/wheel-side-force', cmp0=J + 'gear/unit[0]/compression-ft', ay=J + 'accelerations/Ny',
    turb=J + 'atmosphere/turbulence/milspec/severity', fgturb='/environment/turbulence/magnitude-norm', gust='/environment/gust-front-speed-kt')


async def main():
    if P9.get('/sim/globalhawk/started') is not None and not os.environ.get('ATTACH'):
        print('a FlightGear already answers on port 5477: not starting a second one', flush=True)
        return
    if P9.get('/sim/globalhawk/started') is not None and os.environ.get('ATTACH'):
        proc, took = None, 1                                  # one already up on the runway: use it
    else:
        # a parking spot by its coordinates and heading: FlightGear's --parkpos needs its AI traffic (the user aircraft's flight plan), which is off here, and falls back to the best runway
        spot0 = groundplan.Net(airport).park[PARKING] if SCENARIO == 'taxibox' else None
        where = ['--lat=%.8f' % spot0['lat'], '--lon=%.8f' % spot0['lon'], '--heading=%.1f' % spot0['heading']] if spot0 else ['--airport=' + airport, '--runway=' + runway]
        proc, took = P9.start(where + (['--metar=XXXX 012345Z %s 19SM SKC 15/M99 Q1013 NOSIG' % os.environ['METARWIND']] if os.environ.get('METARWIND') else []), log)
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
        if SCENARIO == 'taxibox':
            spot = groundplan.Net(airport).park[PARKING]
            off = math.hypot((here[0] - spot['lat']) * 364567.2, (here[1] - spot['lon']) * 364567.2 * math.cos(math.radians(here[0])))
            print('FlightGear put the aircraft %.0f ft from parking spot %s, heading %.0f (the spot faces %.0f)' % (off, PARKING, hdg, spot['heading']), flush=True)
            if off > 80.0:
                print('it is not at the spot: stopping', flush=True)
                return
        print('on the %s at %.5f %.5f heading %.1f, elevation %d ft, wind from %s at %s kt' % ('parking spot' if SCENARIO == 'taxibox' else 'runway',
            here[0], here[1], hdg, elev, B.get('/environment/wind-from-heading-deg'), B.get('/environment/wind-speed-kt')), flush=True)
        import subprocess
        if SCENARIO == 'ceiling' or os.environ.get('FUEL_LB'):
            fuel_lb = float(os.environ.get('FUEL_LB', scenario65.FUEL_LB))
            # The same share in every tank, down to the fuel asked for. The targets are worked out once, from the tanks as they are at the start (full), and posted again on every attempt: a first
            # version took the shares from the tanks as they stood after a partly taken first attempt, and the second attempt kept their unevenness (flight 34: 1,000 lb in the right tanks and
            # the left ones off by hundreds: a rolling moment the cross-track law held 140 to 200 ft off the line against, from the take-off to the grass). Checked: the total, each tank
            # against its target, and the left tank against the right (tanks 0 and 1, 2 and 3).
            base = [B.get('/consumables/fuel/tank[%d]/level-lbs' % i) for i in range(6)]       # FlightGear's own tanks: it copies them into the flight model every frame (setting the flight model's is undone)
            targets = [b * fuel_lb / sum(base) for b in base]
            shift = min(float(os.environ.get('FUEL_IMBALANCE_LB', '0')), targets[0])
            targets[0] -= shift
            targets[1] += shift                                                                  # on purpose, if asked: the check below then expects the pair to be this far apart
            for attempt in range(8):
                for i in range(6):
                    B.post('/consumables/fuel/tank[%d]/level-lbs' % i, targets[i])
                await asyncio.sleep(2.5)
                held = [B.get(J + 'propulsion/tank[%d]/contents-lbs' % i) for i in range(6)]
                got = B.get(J + 'fuel/total-lbs')
                even = (all(abs(held[i] - targets[i]) <= 0.02 * targets[i] + 5 for i in range(6)) and abs((held[0] - held[1]) - (targets[0] - targets[1])) <= 2.0 and abs(held[2] - held[3]) <= 2.0)
                if abs(got - fuel_lb) <= 0.02 * fuel_lb + 20 and even:
                    break
                print('fuel %.0f lb, asked for %.0f, tanks %s: again' % (got, fuel_lb, ' '.join('%.0f' % h for h in held)), flush=True)
            else:
                print('the fuel is not what was asked for: stopping', flush=True)
                return
            print('tanks %s lb (the left against the right: %.1f and %.1f lb apart)' % (' '.join('%.0f' % h for h in held), abs(held[0] - held[1]), abs(held[2] - held[3])), flush=True)
        wt, fl = B.get(J + 'inertia/weight-lbs'), B.get(J + 'fuel/total-lbs')
        print('weight %.0f lb, fuel %.0f lb' % (wt, fl), flush=True)
        if SCENARIO == 'ceiling':
            plan = scenario65.plan65(tuple(here), hdg, elev)
        elif SCENARIO == 'taxibox':
            rw = groundplan.RUNWAYS[(airport, runway)]
            js = ("const geo = require('./js/geo.js'), pc = require('./js/plancheck.js'), P = require('./js/predict.js'), perf = require('./js/perfdata.js'); "
                  "const h = pc.localBoxFt([%.7f, %.7f], %.3f, %d, P.make(perf), { alt_ft: %d, weight_lb: %.0f, fuel_lb: %.0f }); "
                  "console.log(JSON.stringify(geo.localPlan([%.7f, %.7f], %.3f, %d, h)))") % (rw['thr'][0], rw['thr'][1], rw['hdg'], elev, elev + 100, wt, fl, rw['thr'][0], rw['thr'][1], rw['hdg'], elev)
            box = json.loads(subprocess.run(['node', '-e', js], capture_output=True, text=True, cwd=os.path.join(HERE, '..', 'GlobalHawk', 'gcs'), check=True).stdout)
            plan, info = groundplan.build(airport, runway, PARKING, box)
            print('taxi out %.0f ft, taxi in %.0f ft' % (groundplan.length_ft(info['net'], [(info['spot']['lat'], info['spot']['lon'])] + info['out']), groundplan.length_ft(info['net'], info['into'])), flush=True)
        else:
            js = ("const geo = require('./js/geo.js'), pc = require('./js/plancheck.js'), P = require('./js/predict.js'), perf = require('./js/perfdata.js'); "
                  "const h = pc.localBoxFt([%.7f, %.7f], %.3f, %d, P.make(perf), { alt_ft: %d, weight_lb: %.0f, fuel_lb: %.0f }); "
                  "console.log(JSON.stringify(geo.localPlan([%.7f, %.7f], %.3f, %d, h)))") % (here[0], here[1], hdg, elev, elev + 100, wt, fl, here[0], here[1], hdg, elev)
            plan = json.loads(subprocess.run(['node', '-e', js], capture_output=True, text=True, cwd=os.path.join(HERE, '..', 'GlobalHawk', 'gcs'), check=True).stdout)
        json.dump(plan, open(os.path.splitext(out)[0] + '-plan.json', 'w'))
        rt = [it for it in plan['items'] if it['kind'] == 'route'][0]
        print('%s: the route climbs to %d ft, the fix is at %d ft' % (plan['id'], max(p[2] for p in rt['points']), rt['points'][-1][2]), flush=True)
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
        gusts, gusts_on, t_miss, eased = float(os.environ.get('GUSTS', '0')), False, None, False
        shear, shear_on = float(os.environ.get('SHEAR_KT', '0')), False
        ease, ease_after = float(os.environ.get('GUSTS_EASE', '0.3')), float(os.environ.get('GUSTS_EASE_AFTER', '90'))
        slowed = float(os.environ.get('SPEEDUP_LAND', '0')) <= 0          # SPEEDUP_LAND: the sim's speed from the landing start on (default 0: no change; 1: real time, so that what the HUD shows can be read)
        while time.monotonic() - t0 < float(os.environ.get('DURATION', '1500')):
            v = {k: c.values.get(p) for k, p in KEYS.items()}
            if isinstance(v['t'], (int, float)):
                if v['t'] - last_beat >= 1.0:
                    c.heartbeat()
                    last_beat = v['t']
                rows.append(v)
                st = v.get('status') or ''
                if '\"doing\":\"plan complete' in st or ('rollout over' in st and SCENARIO != 'taxibox') or 'LANDING ABANDONED' in st:
                    t_lift = t_lift or v['t']
                    t_end = t_end or v['t']
                try:
                    js_ = json.loads(st) if st else {}
                    v['status'] = (js_.get('doing') or '').replace(',', ';') if st else ''
                    v['alerts'] = ';'.join(a.get('id', '') for a in (js_.get('alerts') or []))          # the alert ids the aircraft is raising
                except ValueError:
                    v['status'], v['alerts'] = '', ''
                rows[-1] = v
                if shear > 0 and not shear_on and v['status'].startswith(os.environ.get('SHEAR_AT', 'descend to')):
                    B.post('/environment/config/enabled', True)
                    B.post('/environment/config/boundary/entry[1]/wind-speed-kt', shear)
                    B.post('/environment/config/boundary/entry[1]/wind-from-heading-deg', float(os.environ.get('SHEAR_DIR', '310')))
                    shear_on = True
                    print('the shear begins at %.0f s of flight (%s): the wind at 500 ft goes to %.0f kt from %s (FlightGear moves it 0.05 to 0.25 kt a second)' % (v['t'], v['status'][:30], shear, os.environ.get('SHEAR_DIR', '310')), flush=True)
                if gusts > 0 and not gusts_on and (v['status'].startswith('level to the glide') or v['status'].startswith('approach')):
                    # FlightGear's environment feeds JSBSim's turbulence (its severity is FlightGear's magnitude squared times 7, the surface wind speed its 20 ft wind): with the interpolator on,
                    # the preset's override sets the magnitude (JSBSim's own turbulence properties are written over every frame)
                    B.post('/environment/config/enabled', True)
                    B.post('/environment/config/presets/turbulence-magnitude-norm', gusts)
                    B.post('/environment/config/presets/turbulence-magnitude-norm-override', True)
                    gusts_on = True
                    print('the landing start at %.0f s of flight: gusts on, magnitude %.2f' % (v['t'], gusts), flush=True)
                if gusts_on and t_miss is None and v['status'].startswith('MISSED APPROACH'):
                    t_miss = v['t']
                    print('MISSED APPROACH at %.0f s of flight (%s)' % (v['t'], v['status'][:90]), flush=True)
                if gusts_on and t_miss is not None and not eased and ease >= 0 and v['t'] > t_miss + ease_after:
                    B.post('/environment/config/presets/turbulence-magnitude-norm', ease)
                    eased = True
                    if shear_on:
                        B.post('/environment/config/boundary/entry[1]/wind-speed-kt', float(os.environ.get('SHEAR_EASE', '36.4')))
                        B.post('/environment/config/boundary/entry[1]/wind-from-heading-deg', 315.0)
                    print('%.0f s after the missed approach: the gusts ease to %.2f' % (v['t'] - t_miss, ease), flush=True)
                if not slowed and (v['status'].startswith('level to the glide') or v['status'].startswith('approach')):
                    B.post('/sim/speed-up', float(os.environ['SPEEDUP_LAND']))
                    slowed = True
                    print('the landing start at %.0f s of flight: the sim runs at %sx from here' % (v['t'], os.environ['SPEEDUP_LAND']), flush=True)
                if t_end is not None and v['t'] > t_end + 8:
                    break
            await asyncio.sleep(0.1)
        with open(out, 'w') as fh:
            fh.write(','.join(list(KEYS) + ['alerts']) + '\n')
            seen = None
            for v in rows:
                if v['t'] != seen:
                    fh.write(','.join(['' if v[k] is None else str(v[k]) for k in KEYS] + [v.get('alerts', '')]) + '\n')
                    seen = v['t']
        print('wrote %d rows to %s' % (len(rows), out), flush=True)
    finally:
        if not keep:
            P9.stop(proc)

asyncio.run(main())
