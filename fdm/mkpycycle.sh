#!/bin/sh
# Sets up NASA's pyCycle (OpenMDAO) as a local tool in tools/pycycle/, which git ignores: nothing of pyCycle's
# goes into this repository. fdm/engine_pycycle.py, the second engine model, runs from it.
#
# Why a copy: pyCycle 4.4.0 fails under NumPy 2 in two places, where it writes a one-element array into a single
# array element. The copy gets those two lines patched; the installed package is left alone.
#
#   fdm/mkpycycle.sh [python]        default python: /opt/homebrew/bin/python3
#
# Only the tabulated gas properties are made to run this way; the chemical-equilibrium ones need more patches.
set -e
PY=${1:-/opt/homebrew/bin/python3}
HERE=$(cd "$(dirname "$0")" && pwd)
T="$HERE/../tools/pycycle"
SRC=$("$PY" -c "import pycycle, os; print(os.path.dirname(pycycle.__file__))")
mkdir -p "$T/lib"
rm -rf "$T/lib/pycycle"
cp -R "$SRC" "$T/lib/pycycle"
find "$T/lib" -name __pycache__ -prune -exec rm -rf {} +
"$PY" -I - "$T/lib/pycycle" <<'PYEOF'
import sys
root = sys.argv[1]
def patch(path, old, new):
    s = open(path).read()
    if new in s:
        return
    if old not in s:
        sys.exit('%s: the line to patch has changed; look at it by hand' % path)
    open(path, 'w').write(s.replace(old, new))
patch(root + '/thermo/tabular/thermo_add.py',
      "W_other_out[self.idx_compo] += W_other_mix\n",
      "W_other_out[self.idx_compo] += np.ravel(W_other_mix)[0]  # patched for NumPy 2\n")
patch(root + '/thermo/cea/props_rhs.py',
      "outputs['rhs_P'][num_element] = inputs['n_moles']",
      "outputs['rhs_P'][num_element] = np.ravel(inputs['n_moles'])[0]  # patched for NumPy 2")
print('patched copy of pyCycle in', root)
PYEOF
