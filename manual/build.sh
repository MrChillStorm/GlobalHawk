#!/bin/sh
# Rebuild the operator's manual: its tables and numbers from the aircraft's sources (mkmanual.py stops the build on a
# control, an alert or a guideline that is not accounted for), its pictures' callouts, then the PDF to the repository root.
set -e
cd "$(dirname "$0")"
/opt/homebrew/bin/python3 mkmanual.py
/opt/homebrew/bin/python3 figures.py
tectonic -X compile ghawk_manual.tex
cp ghawk_manual.pdf ../GlobalHawk-operators-manual.pdf
