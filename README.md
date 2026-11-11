# NASA Global Hawk for FlightGear, with a ground control station

A JSBSim flight model of NASA's Global Hawk N872NA, the high-altitude, long-endurance unmanned aircraft (a Northrop
Grumman RQ-4A) that NASA flew on science missions, and a ground control station to fly it from. It is modelled from
public data and is not made or endorsed by NASA or Northrop Grumman.

**Status: in development. Nothing flies yet.** So far: the published numbers with their sources, a reader for
NASA's flight data from the ATTREX campaigns, and the geometry and mass the flight model will be built on.

- [fdm/data/README.md](fdm/data/README.md): every published number the model is built from, its source, and the
  choices made where sources disagree.
- [fdm/attrex.py](fdm/attrex.py): reads the ATTREX flight records (NASA ESPO archive) and summarises each flight.
- [fdm/geometry.py](fdm/geometry.py): geometry and mass from the published numbers, NASA's side-view drawing and
  NASA's 3-D model, written to `fdm/data/geometry.json` and `mass.json`; `fdm/phase1_checks.py` prints the checks.

## Licence

GNU General Public License, version 2. See [COPYING](COPYING).
