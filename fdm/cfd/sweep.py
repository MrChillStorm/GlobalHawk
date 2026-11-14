#!/usr/bin/env python3
"""An angle-of-attack sweep of one Mach and Reynolds number, each case warm-started from the one before:

    python3 fdm/cfd/sweep.py MACH REYNOLDS ALPHA1 ALPHA2 ...      (run each Mach and Reynolds number as one queue job: qrun)
    python3 fdm/cfd/sweep.py 0.6 1.5e6 from=M0.60_Re1.5_a0.0 n2 n3   the first case starts from that one's solution; 'n2' is -2 deg
    python3 fdm/cfd/sweep.py --collect                           every result.json under tools/su2-runs into fdm/data/cfd_lrn1015.json
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_case as R  # noqa: E402

OUT = os.path.join(HERE, '..', 'data', 'cfd_lrn1015.json')


def collect():
    rows = []
    for p in sorted(glob.glob(os.path.join(R.RUNS, '*', 'result.json'))):
        rows.append(json.load(open(p)))
    rows.sort(key=lambda r: (r['mach'], r['re'], r['alpha']))
    json.dump(dict(source='SU2 8.6.0, RANS, Spalart-Allmaras, fully turbulent, adiabatic wall; fdm/cfd/run_case.py; moment nose-up positive about the quarter chord',
                   cases=rows), open(OUT, 'w'), indent=1)
    print('wrote', os.path.relpath(OUT), len(rows), 'cases')


if __name__ == '__main__':
    if '--collect' in sys.argv:
        collect()
        sys.exit()
    mach, re = float(sys.argv[1]), float(sys.argv[2])
    prev = None
    rest = []
    for x in sys.argv[3:]:
        if x.startswith('from='):                      # warm start the first case from another one's restart file (a name under tools/su2-runs/)
            prev = x[5:]
        else:
            rest.append(-float(x[1:]) if x.startswith('n') else float(x))        # 'n2' is -2 degrees (a leading '-' would look like an option to the queue)
    for a in rest:
        r = R.run(mach, re, a, restart_from=prev, iters=4000)
        print(r, flush=True)
        prev = R.name(mach, re, a)
