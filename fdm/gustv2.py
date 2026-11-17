#!/usr/bin/env python3
"""All the gust flights again, on the laws as they stand after 2026-11-17 (docs/PLAN.md, "The gust flights, version 2"): the WGS84 geometry everywhere and the landing's lateral loops shortened low (8 s and 2 s below
300 ft). The laws are frozen for it: any later change to them makes a version 3.

    python3 fdm/gustv2.py cases              writes fdm/out/gust_v2/<set>.cases
    python3 fdm/gustv2.py run STAGE          queues the flights (`qrun`, two at a time): STAGE core | rules
    python3 fdm/gustv2.py count              the flights of each stage
    python3 fdm/gustfactorial.py --set test|crazy|rules --dir fdm/out/gust_v2 --out fdm/report/results/gust_factorial_v2.json     the tables

The sets are the version 1 sets' (fdm/gustsweep.py: test_d, test_t, rules_t, crazy_t, crazy_m) with one change: the turbulence is JSBSim's own MIL-F-8785C turbulence as FlightGear runs it, at the field's height
(`GB_ELEV=171`, `tu=W20:severity`), with the rotation of the gusts across the wings and not the bench's own Dryden (`lo=`, which has none: docs/PLAN.md, "Why the bench did not reproduce FlightGear's offset").
Fresh seeds: 501 to 548 for the turbulence (version 1: 101 to 148 and 201 to 248). The discrete gusts are the same 216 cases. The arms are the version 1 arms.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gustsweep  # noqa: E402

OUT = os.path.join(HERE, 'out', 'gust_v2')
SEV = 5                      # FlightGear's gusts 0.85: magnitude 0.7225 squared times 7 (below 1,000 ft only the wind at 20 ft counts)

SETS = {
    'test_d': gustsweep.SWEEPS['test_d'],
    'test_t': ['w=20800 tu=%d:%d seed=%d' % (w20, SEV, seed) for w20 in (20, 30, 40, 50) for seed in range(501, 549)]
              + ['w=20800 hw=%d xw=%d tu=%d:%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, SEV, seed) for w20 in (30, 40, 50) for seed in range(501, 549)],
    'rules_t': ['w=20800 tu=%d:%d seed=%d' % (w20, SEV, seed) for w20 in (20, 30, 40, 50) for seed in range(601, 649)]
               + ['w=20800 hw=%d xw=%d tu=%d:%d seed=%d' % (round(w20 * 0.7), round(w20 * 0.7), w20, SEV, seed) for w20 in (30, 40, 50) for seed in range(601, 649)],
    'crazy_t': ['w=26750 hw=4 xw=28 tu=28:6 seed=%d' % seed for seed in range(501, 549)] + ['w=26750 hw=5 xw=36 tu=36:6 shr=2.36 seed=%d' % seed for seed in range(501, 549)],
    'crazy_m': ['w=26750 mgr=1 sec=1800 hw=4 xw=28 tu=28:6 seed=%d' % seed for seed in range(501, 525)] + ['w=26750 mgr=1 sec=1800 hw=5 xw=36 tu=36:6 shr=2.36 seed=%d' % seed for seed in range(501, 525)],
}

# the arms: name -> the bench's flags (fdm/gustbench.py)
ARMS = {
    'neither': [], 'speed': ['--auto'], 'stab': ['--gs'], 'both': ['--gs', '--auto'],
    'fixed': ['--add', '10'], 'fixedboth': ['--gs', '--add', '10'],
    'boeing': ['--rule', 'boeing'], 'boeingstab': ['--gs', '--rule', 'boeing'],
    'airbus': ['--rule', 'airbus'], 'airbusstab': ['--gs', '--rule', 'airbus'],
    'airbusfull': ['--rule', 'airbusfull'], 'airbusfullstab': ['--gs', '--rule', 'airbusfull'],
}
STAGES = {
    'core': [('test_d', ('neither', 'speed', 'stab', 'both', 'fixed', 'fixedboth')), ('test_t', ('neither', 'speed', 'stab', 'both')),
             ('crazy_t', ('neither', 'speed', 'stab', 'both')), ('crazy_m', ('neither', 'stab', 'both'))],
    'rules': [('crazy_t', ('boeing', 'boeingstab', 'airbus', 'airbusstab', 'airbusfull', 'airbusfullstab')),
              ('rules_t', tuple(ARMS))],
    # 2026-11-17: the Boeing arm's gust increment read lo= only and was zero on these tu= cases (fixed in gustbench.rule_add); only the Boeing arms are flown again
    'boeingfix': [('crazy_t', ('boeing', 'boeingstab')), ('rules_t', ('boeing', 'boeingstab'))],
}


def write_cases():
    os.makedirs(OUT, exist_ok=True)
    for name, cases in SETS.items():
        with open(os.path.join(OUT, name + '.cases'), 'w') as fh:
            fh.write('\n'.join(cases) + '\n')
        print('%-8s %4d cases' % (name, len(cases)))


def run(stage):
    write_cases()
    procs = []
    for name, arms in STAGES[stage]:
        for arm in arms:
            of = os.path.join(OUT, '%s.%s.jsonl' % (name, arm))
            if os.path.exists(of):
                os.remove(of)
            cmd = ['qrun', 'env', 'GB_ELEV=171', sys.executable, os.path.join(HERE, 'gustbench.py')] + ARMS[arm] + ['--from', os.path.join(OUT, name + '.cases'), '--out', of]
            procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(of.replace('.jsonl', '.log'), 'w'), cwd=os.path.dirname(HERE)))
    for p in procs:
        p.wait()


def main():
    a = sys.argv[1:]
    if not a or a[0] == 'cases':
        write_cases()
    elif a[0] == 'count':
        for st, items in STAGES.items():
            print(st, sum(len(SETS[n]) * len(arms) for n, arms in items), 'flights')
    elif a[0] == 'run':
        run(a[1])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
