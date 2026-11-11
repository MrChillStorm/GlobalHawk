# NASA Global Hawk for FlightGear, with a ground control station

A JSBSim flight model of NASA's Global Hawk N872NA, the high-altitude, long-endurance unmanned aircraft (a Northrop
Grumman RQ-4A) that NASA flew on science missions, and a ground control station to fly it from. It is modelled from
public data and is not made or endorsed by NASA or Northrop Grumman.

**Status: in development. Nothing flies yet.** So far: the published numbers with their sources, a reader for
NASA's flight data from the ATTREX campaigns, the geometry and mass, the engine model,
and the aerodynamic model (not yet in JSBSim).

- [fdm/data/README.md](fdm/data/README.md): every published number the model is built from, its source, and the
  choices made where sources disagree.
- [fdm/attrex.py](fdm/attrex.py): reads the ATTREX flight records (NASA ESPO archive) and summarises each flight.
- [fdm/geometry.py](fdm/geometry.py): geometry and mass from the published numbers, NASA's side-view drawing and
  NASA's 3-D model, written to `fdm/data/geometry.json` and `mass.json`; `fdm/phase1_checks.py` prints the checks.
- [fdm/engine.py](fdm/engine.py): the engine, a turbofan cycle model of the AE 3007 family fitted to the ICAO
  databank and checked against the Citation X's engine; writes `fdm/data/engine.json`.
- [fdm/engine_pycycle.py](fdm/engine_pycycle.py): the same engine in NASA's pyCycle, as a second opinion. pyCycle is
  not in this repository: [fdm/mkpycycle.sh](fdm/mkpycycle.sh) sets it up in `tools/`, which git ignores.
- [fdm/strips.py](fdm/strips.py): the aerodynamic model, strips with section data on a lifting line; compared with
  [fdm/aero_ref.py](fdm/aero_ref.py), the same aircraft in AeroSandbox. [fdm/digitise_lrn1015.py](fdm/digitise_lrn1015.py)
  reads NASA's tunnel test of the wing section, which the section data is checked against.

## Licence

GNU General Public License, version 2. See [COPYING](COPYING).
