"""The highest this model of the aircraft flies, tanks run dry: offline, through the laws and the mission manager.

    python3 scenario_record.py              flies it (about 35 h of flight, 15 minutes at full speed) and prints the record

The aircraft takes off at full tanks (26,750 lb, the model's 15,300 lb of fuel) and cruise-climbs at maximum thrust on the schedule's Mach number (0.6 above FL550), the height
command out of reach (90,000 ft), so that it goes on rising as the fuel burns away: the lighter it is, the higher its ceiling. The racetrack is short (150 nmi sides) so that
the aircraft is always within glide range of the field. When the tanks are empty (under 2 lb) the engine is failed, the way the fuel running out would stop it, and the
aircraft's own engine-out logic glides it to the field and lands it: the flight ends with the rollout. The laws' and the manager's 65,000 ft limits (the aircraft's published
maximum, NASA 2008) are lifted for this run only.

What the number means: the engine data (fdm/data/engine.json) go to 70,000 ft and Mach 0.7, the aerodynamic data are sampled at 60,000 ft for Mach 0.6, and the laws' tables
(throttle, turn performance) to 65,000 ft, held at their last value above it. Above 65,000 ft this is the model extrapolated, not the aircraft measured.
"""
import json
import math
import wgs84 as WG                 # the one earth model: WGS84's tangent plane (fdm/wgs84.py)
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np                  # noqa: E402
import harness as H                 # noqa: E402
import missionmgr as MM             # noqa: E402
import scenario65 as SC             # noqa: E402

LIMIT_FT = 90000.0                  # the height command and the limits of this run
FULL_WEIGHT = 26749.0
LOOPS = 45                          # about 2.1 h each at Mach 0.6: more than the fuel lasts
FUEL_OUT_LB = 2.0
HOURS_MAX = 60.0


def main():
    MM.MAX_ALT = LIMIT_FT
    VAR = {'laws.ALTITUDE_LIMIT': LIMIT_FT}
    H.load = lambda *a, **k: H.load_variant(VAR)            # a temp tree: the shipped laws.xml is not touched
    import gcs_server as G
    SC.SIDE_NM, SC.WIDTH_NM, SC.START_NM = 150.0, 30.0, 20.0
    plan = SC.plan65(ceiling=LIMIT_FT, loops=LOOPS)
    plan['id'] = 'record'
    plan['field'].update(stand=plan['items'][0]['start'], stand_heading=SC.HEADING)
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
        json.dump(plan, fh)
    sim = G.Sim(fh.name, weight=FULL_WEIGHT)
    f, ob = sim.f, sim.ob
    for n, (name, args) in enumerate((('plan', plan), ('start', {}))):
        sim.set('/gcs/up/cmd', json.dumps(dict(seq=n + 1, station='C', name=name, args=args)))
    for _ in range(int(2 * H.HZ)):
        sim.step()
    print('plan:', ob.down.get('/gcs/down/ack'), flush=True)
    names = ['simulation/sim-time-sec', 'position/h-sl-ft', 'velocities/mach', 'velocities/vc-kts', 'velocities/h-dot-fps', 'aero/alpha-deg', 'ap/alpha-limit-deg', 'ctl/throttle-norm',
             'fuel/total-lbs', 'inertia/weight-lbs', 'ap/pitch-mode', 'ap/thrust-mode', 'ap/vmode', 'position/lat-geod-deg', 'position/long-gc-deg', 'accelerations/Nz', 'engine/failed',
             'ap/leg-xt-ft', 'ap/on-mains', 'engine/thrust-lbf', 'engine/fuel-flow-pph', 'attitude/phi-deg']
    rows, t0, out_at, done = [], f['simulation/sim-time-sec'], None, None
    for i in range(int(HOURS_MAX * 3600 * H.HZ)):
        if i % H.HZ == 0:
            sim.set('/gcs/up/heartbeat', i)
        sim.step()
        if not sim.ok:
            print('the model stopped', flush=True)
            break
        if out_at is None and f['fuel/total-lbs'] < FUEL_OUT_LB and f['ap/on-mains'] == 0:
            f['engine/failed'] = 1                                     # the tanks are dry
            out_at = f['simulation/sim-time-sec'] - t0
            print('%.2f h: the tanks are empty at %.0f ft, %.0f lb, Mach %.3f: the engine is out' % (out_at / 3600, f['position/h-sl-ft'], f['inertia/weight-lbs'], f['velocities/mach']), flush=True)
        if i % int(H.HZ) == 0:
            rows.append([f[n] for n in names])
            r = rows[-1]
            if len(rows) % 3600 == 1:
                print('%5.1f h  %6.0f ft  M %.3f  %6.0f lb  fuel %6.0f lb  climb %+5.1f ft/min  alpha margin %.2f deg  mode %d/%d/%d' % (
                    (r[0] - t0) / 3600, r[1], r[2], r[9], r[8], r[4] * 60, r[6] - r[5], r[10], r[11], r[12]), flush=True)
        if any('rollout over' in e[1] for e in ob.mgr.events) and done is None:
            done = i
        if done is not None and i > done + 5 * H.HZ:
            break
    a = np.array(rows)
    out = os.environ.get('OUT', os.path.join(HERE, '..', 'record_altitude.npz'))
    np.savez(out, a=a, names=np.array(names), t0=t0)
    col = lambda n: a[:, names.index(n)]
    t = col('simulation/sim-time-sec') - t0
    alt = col('position/h-sl-ft')
    k = int(np.argmax(alt))
    print()
    print('RECORD: %.0f ft at %.2f h (weight %.0f lb, fuel %.0f lb, Mach %.3f, alpha margin %.2f deg, climb rate %+.1f ft/min)' % (
        alt[k], t[k] / 3600, col('inertia/weight-lbs')[k], col('fuel/total-lbs')[k], col('velocities/mach')[k], col('ap/alpha-limit-deg')[k] - col('aero/alpha-deg')[k], col('velocities/h-dot-fps')[k] * 60))
    print('flight time to the engine out: %s; the whole flight %.2f h' % ('%.2f h' % (out_at / 3600) if out_at is not None else 'the tanks never ran dry', t[-1] / 3600))
    for h in range(6, int(t[-1] / 3600) + 1, 6):
        j = int(np.argmin(abs(t - h * 3600)))
        print('  %2d h: %6.0f ft, %6.0f lb' % (h, alt[j], col('inertia/weight-lbs')[j]))
    if done is not None and out_at is not None:
        iout = int(np.argmax(col('engine/failed') > 0))
        after = np.nonzero((col('ap/on-mains') > 0) & (np.arange(len(t)) > iout))[0]
        if len(after):
            td = int(after[0])
            far = WG.distance((col('position/lat-geod-deg')[td], col('position/long-gc-deg')[td]), (col('position/lat-geod-deg')[iout], col('position/long-gc-deg')[iout])) / 6076.1
            print('landing: the engine out at %.0f ft, %.0f nmi from the field; touchdown %.0f min later, %.1f ft off the line, the rollout at most %.1f ft off it' % (
                alt[iout], far, (t[td] - t[iout]) / 60, col('ap/leg-xt-ft')[td], float(np.nanmax(np.abs(col('ap/leg-xt-ft')[after])))))
    else:
        print('no landing: the flight ended without a rollout (altitude now %.0f ft)' % alt[-1])


if __name__ == '__main__':
    main()
