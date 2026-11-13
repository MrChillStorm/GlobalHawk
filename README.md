# Global Hawk for FlightGear, with a ground control station

A JSBSim flight model of NASA's Global Hawk N872NA, the high-altitude, long-endurance unmanned aircraft (a Northrop
Grumman RQ-4A) that NASA flew on science missions, and a ground control station to fly it from. It is modelled from
public data and is not made or endorsed by NASA or Northrop Grumman.

**Status: in development; it flies.** The flight model is built from published numbers and NASA's ATTREX flight
data and checked against the measured climb, cruise-climb, takeoffs and landings. Its own flight laws fly a whole
mission hands off, from taxi and takeoff to landing, with contingencies for a failed navigator, a lost link and a
dead engine. In FlightGear it has a 3-D model with a bending wing, a head-up display over the nose camera, a
belly camera that locks on targets, its own sounds, and a ground control station in the browser that flies it.

- [Model report](GlobalHawk-JSBSim-model-report.pdf): how the flight model is built, what it was checked against, every
  check that passes and every one that misses. Built by `fdm/report/build.sh` from the logs of `fdm/check_all.sh`.
- [Operator's manual](GlobalHawk-operators-manual.pdf): the station, the aircraft in FlightGear, limits, procedures,
  what the aircraft does when things fail, performance tables. Built by `manual/build.sh`; its tables of controls
  and alerts and its figures come from the aircraft's own sources.
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
- [fdm/genghawk.py](fdm/genghawk.py): writes the JSBSim model in [GlobalHawk/](GlobalHawk) from the data files
  ([fdm/aerotables.py](fdm/aerotables.py) samples the aerodynamic tables). [fdm/harness.py](fdm/harness.py) loads, trims
  and flies it; `fdm/phase3_checks.py` checks it.
- [fdm/mission.py](fdm/mission.py): a whole flight in the JSBSim model, against the measured climb, cruise-climb and
  endurance; it also fits the calibration. [fdm/attrex_lift.py](fdm/attrex_lift.py): the lift curve and the turns from
  the ATTREX flights.
- `fdm/phase5_checks.py`: standing, taxi, takeoff and landing against the measured ones.
- [fdm/flex.py](fdm/flex.py): the wing's bending, a beam model on stated assumptions (no data of the real wing is
  public); it gives the tip deflection for the animation and the roll due to sideslip of the bent wing.
- [fdm/laws.py](fdm/laws.py): the flight laws (our own design; the real ones aren't public), generated into
  `GlobalHawk/Systems/laws.xml`; `fdm/phase7a_checks.py` checks them.
- [fdm/missionmgr.py](fdm/missionmgr.py): a stand-in for the mission manager; `fdm/phase7b_checks.py` flies the two
  recorded landings and one whole mission with it.
  `fdm/phase7c_checks.py`: a failed navigator, a lost link and a landing without the engine.
  `fdm/phase7d_checks.py`: flying it by hand, protected and direct.
- [GlobalHawk/gcs/](GlobalHawk/gcs/README.md): the ground control station, a browser page (first part: the command
  link, a map, commands with preview and acknowledgement). [fdm/gcs_server.py](fdm/gcs_server.py) stands in for
  FlightGear with the flight model behind FlightGear's own web protocol; [fdm/onboard.py](fdm/onboard.py) is the
  aircraft's end of the link; `fdm/phase8a_checks.py` flies a scenario through it. `fdm/phase8b_checks.py` checks the alerts the aircraft raises. [fdm/gcs_perf.py](fdm/gcs_perf.py) samples
  the model into the table the station forecasts with; `fdm/phase8c_checks.py` holds the forecast against flights of the model.
  `fdm/phase8d_checks.py`: several stations, handing over control, and flying by hand through the link.
  `fdm/phase8e_checks.py`: traffic, and the demo's stand-in aircraft against the model. The station also runs
  with nothing behind it: `GlobalHawk/gcs/index.html?demo=1`.

- [GlobalHawk/GlobalHawk-set.xml](GlobalHawk/GlobalHawk-set.xml): the FlightGear aircraft. Its 3-D model is made by
  [fdm/mkmodel.py](fdm/mkmodel.py) from NASA's 3-D model of the Global Hawk: scaled to the published length, span and
  height, the ailerons, ruddervators and spoilers cut out, the fan and turbine turning, and the gear folding into
  fairings behind doors. [fdm/viewmodel.py](fdm/viewmodel.py) draws it posed, for checking without FlightGear;
  `fdm/phase9a_checks.py` starts FlightGear with it. The fairings, the doors and the way the gear folds are our own
  guesses: no drawing of them is public.
- [GlobalHawk/Nasal/](GlobalHawk/Nasal/): what runs inside FlightGear. `onboard.nas` and `missionmgr.nas` are the
  aircraft's end of the link and the mission manager, the same logic as `fdm/onboard.py` and `fdm/missionmgr.py`
  line for line (change both together); `json.nas` reads and writes the link's JSON. With them the ground station
  flies FlightGear itself: start FlightGear with `--httpd=5400` and open the station on that address.
  `fdm/phase9b_checks.py` flies it in FlightGear through the station's protocol.
- [GlobalHawk/Huds/hud.nas](GlobalHawk/Huds/hud.nas): the head-up display over the nose camera's picture, in place
  of FlightGear's standard one: one green, the horizon and flight path marker lying on the world outside, the
  flight laws' targets and limits, what the aircraft is doing and what the crew must know. `h` switches it.
  `fdm/phase9c_checks.py` checks it in FlightGear from screenshots.
- [GlobalHawk/Nasal/camera.nas](GlobalHawk/Nasal/camera.nas): the belly camera (the view "Belly Camera", for the
  sensor operator): it locks on a point on the ground or on any model FlightGear has (a ship, a vehicle, an
  aircraft) and follows it, and is slewed by buttons or the stick. In the "Global Hawk" menu.
  `fdm/phase9d_checks.py` flies it. [GlobalHawk/Sounds/](GlobalHawk/Sounds/): the engine's sound, made by PyWopWop's
  turbofan model with the fan's speeds and blade count measured from recordings of Global Hawks, and with it the
  wind on the nose, the tyres, the gear in the airflow, the touchdowns and the airframe: every loop and one-shot is
  made by [fdm/mksounds.py](fdm/mksounds.py) from [PyWopWop](https://github.com/MrChillStorm/PyWopWop) (about 270 MB).
  The inside sounds are what a microphone in the nose bay would hear, and play in the two cameras' views.
  The belly camera keeps the horizon level in its picture as the aircraft banks, and the ground station has a
  Camera panel for it (lock on a point by clicking the map).
- Starting in the air: [fdm/trimtable.py](fdm/trimtable.py) writes the flight model's level trims by height, speed
  and weight, and the aircraft starts from them once FlightGear's wind has settled, so it begins in steady flight.
  (`Nasal/defaults.nas`, written by `fdm/genghawk.py`, keeps a ground station that connects early from leaving the
  flight model's switches unset.)
  Where the height asked for can't be flown with full tanks (above about 50,000 ft) it starts with less fuel and
  says so. High up it also widens FlightGear's terrain range so the ground runs towards the horizon
  ("Ground to the horizon at height" in the Global Hawk menu switches that off; expect more scenery downloads).
- Lamps ([fdm/ghlights.py](fdm/ghlights.py)), the livery and its badge ([fdm/mkinsignia.py](fdm/mkinsignia.py)) and
  the materials for FlightGear's HDR renderer are made with the 3-D model. The livery is FlightGear's own, not the
  real aircraft's.

## Credits

The 3-D model is derived from NASA's Global Hawk model on NASA 3D Resources (credit: NASA). NASA's material is
generally not copyrighted and may be used with that credit; its use here does not mean NASA endorses this project,
and NASA's insignia are not used. The flight records are NASA's ATTREX data (NASA ESPO archive).

## Licence

GNU General Public License, version 2. See [COPYING](COPYING).
