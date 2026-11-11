# NASA Global Hawk for FlightGear, with a ground control station

A JSBSim flight model of NASA's Global Hawk N872NA, the high-altitude, long-endurance unmanned aircraft (a Northrop
Grumman RQ-4A) that NASA flew on science missions, and a ground control station to fly it from. It is modelled from
public data and is not made or endorsed by NASA or Northrop Grumman.

**Status: in development. Nothing flies yet.** So far: the published numbers with their sources, and a reader for
NASA's flight data from the ATTREX campaigns.

- [fdm/data/README.md](fdm/data/README.md): every published number the model is built from, its source, and the
  choices made where sources disagree.
- [fdm/attrex.py](fdm/attrex.py): reads the ATTREX flight records (NASA ESPO archive) and summarises each flight.

## Licence

GNU General Public License, version 2. See [COPYING](COPYING).
