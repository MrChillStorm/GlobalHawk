#!/bin/sh
# Every check of the model, the laws and the station, each into its own log:
#
#     qrun fdm/check_all.sh [LOGDIR]          the checks that need no FlightGear (LOGDIR: fdm/report/results)
#     fdm/check_all.sh LOGDIR fg              those that fly in FlightGear (not through the queue; an unlocked screen)
#
# The report's tables are made from these logs (fdm/report/mktables.py). A check that fails to run leaves its error
# in its log and the run goes on.
cd "$(dirname "$0")/.." || exit 1
LOG=${1:-fdm/report/results}
PY=/opt/homebrew/bin/python3
mkdir -p "$LOG"
run() {
    name=$1; shift
    # ONLY="mission engine" fdm/check_all.sh: just those
    if [ -n "${ONLY:-}" ]; then case " $ONLY " in *" $name "*) ;; *) return;; esac; fi
    echo "== $name" >&2
    start=$(date +%s)
    "$@" > "$LOG/$name.txt" 2>&1
    echo "exit $? after $(( $(date +%s) - start )) s" >> "$LOG/$name.txt"
    tail -n 3 "$LOG/$name.txt" | grep -a "checks,\|exit " >&2
}
if [ "${2:-}" = "fg" ]; then
    for c in phase9a phase9b phase9c phase9d; do run ${c}_checks sh -c "$PY -u fdm/${c}_checks.py 2>&1 | grep -a -v '^\[sentry\]'"; done
else
    run engine $PY fdm/engine.py
    run mission $PY fdm/mission.py
    run engine_pycycle $PY fdm/engine_pycycle.py          # needs tools/pycycle (fdm/mkpycycle.sh)
    run attrex_lift $PY fdm/attrex_lift.py                # needs the ATTREX records in refs/
    for c in phase1 phase3 phase5 phase6 phase7a phase7b phase7c phase7d phase8a phase8b phase8c phase8d phase8e; do run ${c}_checks $PY fdm/${c}_checks.py; done
    run gcs_tests sh -c "cd GlobalHawk/gcs && npm test"
fi
git rev-parse --short HEAD > "$LOG/commit.txt" 2>/dev/null
date "+%Y-%m-%d %H:%M" >> "$LOG/commit.txt"
