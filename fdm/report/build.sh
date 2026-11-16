#!/bin/sh
# Rebuild the report from the check logs in results/ (a run of fdm/check_all.sh; fdm/report/mkresults.py for the time histories)
# and copy the PDF to the repository root.
set -e
cd "$(dirname "$0")"
/opt/homebrew/bin/python3 mktables.py
/opt/homebrew/bin/python3 mkgust.py
/opt/homebrew/bin/python3 figures.py
tectonic -X compile ghawk_report.tex
cp ghawk_report.pdf ../../GlobalHawk-JSBSim-model-report.pdf
