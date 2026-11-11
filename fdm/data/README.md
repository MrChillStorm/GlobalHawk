# Data: every published number, its source, and the choices made

The model is of NASA's Global Hawk N872NA, an RQ-4A (Block 10 geometry). Nothing here comes from the manufacturer's
data or a flight manual: none is public. Each number is followed by its source in brackets; where sources disagree
they are shown side by side and the choice is stated. "Measured" means taken from flight data, "published" from a
document, "derived" worked out here from those.

The source documents themselves are not in this repository. Each is public; the list at the end says where.

## Dimensions

| Item | Value | Source |
|---|---|---|
| Wingspan | 116.2 ft (35.42 m) | 116 ft [NASA overviews 2009-2017]; 116 ft 2.5 in [Designation-Systems]; 35.42 m [Jane's 1999, quoted in the UTHM thesis] |
| Length | 44.4 ft (13.53 m) | 44 ft [NASA overviews]; 44 ft 4.75 in [Designation-Systems]; 13.52 m [Jane's 1999] |
| Height | 15.2 ft (4.64 m) | 15 ft [NASA fact sheet FS-098]; 15 ft 2.5 in [Designation-Systems]; 4.60 m (15.1 ft) [Jane's 1999]; 14.6 ft [Northrop Grumman's sheet, from the build plan, not re-read] |
| Wing area | 540 ft² (50.2 m²) | Jane's 1999, quoted in the UTHM thesis. The only published figure found |
| Aspect ratio | 25.0 | derived from the span and area above; Jane's gives 25.09 |
| Wing section | LRN 1015: design lift coefficient 1.0, 15.2 % thick | NASA TM 102840; coordinates from the UIUC database, 79 points, measured here at 15.2 % thick at 40 % chord |

The RQ-4B is a different aircraft (span 130.9 ft, length 47.6 ft, height 15.3 ft, 32,250 lb [USAF fact sheet]) and none
of its numbers are used.

Wing sweep, taper, dihedral, twist, the V-tail's size and angle, the control-surface outlines and the gear positions
are not published anywhere we found. Where they come from is the next section.

## Geometry: what was built, and from what

`fdm/geometry.py` writes `geometry.json` (feet; x aft from the nose tip, y right, z up from the ground with the
aircraft on its wheels) and `mass.json`. `fdm/phase1_checks.py` prints the checks below.

**NASA's 3-D model is not to scale.** It is an artist's model (NASA 3D Resources, 37,000 triangles, Draco-compressed;
`fdm/glb.py` reads it). Scaled to the published span its fuselage is 57.1 ft long, 29 % over; scaled to the published
length its span is 90.3 ft, 22 % under. Its fuselage and wing root agree with NASA's side-view drawing, so it is the
wing that was drawn short. No single scale brings it inside the limits set beforehand (span and length 1 %,
height 3 %), so the model is used only for shapes, and each dimension is anchored on a published number or on
NASA's drawing:

| What | Source | Scale |
|---|---|---|
| Positions along the length and heights: fuselage outline, nacelle, fin, wing root, axles | NASA's side-view drawing of the payload bays (a slide in NASA's Global Hawk briefings), digitised by hand to about 2 pixels, 0.1 ft | published length, 44.4 ft |
| Wing span stations | 3-D model | published span, 116.2 ft |
| Wing chords | 3-D model's planform: taper, sweep and the root fillet | **a fit:** scaled so the straight-tapered wing, carried to the centreline, has the published 540 ft² |
| Widths: fuselage, gear track; V-tail dihedral | 3-D model | published length |

| Wing | Value | |
|---|---|---|
| Span, reference area, aspect ratio | 116.2 ft, 540 ft², 25.0 | published |
| Centreline and tip chords, taper ratio | 6.83 ft, 2.47 ft, 0.361 | model's shape, fitted to the area |
| Mean aerodynamic chord | 4.99 ft at y = 24.5 ft; leading edge at x = 21.63 ft | derived |
| Sweep: leading edge, quarter chord, trailing edge | 7.2, 6.2 and 3 deg | model's shape with the scales above |
| Root fillet | the trailing edge runs aft inboard of y = 11 ft; chord 8.85 ft at the fuselage side; area with it 577 ft² | model |
| Dihedral | 0 on the ground | model. In flight the wing bends upward: not modelled here |
| Twist | 4 deg nose-down from the fuselage side to the tip, 2.5 deg of it inboard of y = 14 ft | model, an estimate: an artist's wing |
| Section | LRN 1015, 15.2 % | published. The model's wing is 10-15 % thick and is not used for the section |
| Control surfaces | not separate in the model: the wing and tail are single shells. Outlines from photographs, later | |

| V-tail, fuselage, engine, gear | Value | |
|---|---|---|
| V-tail | two panels at 47 deg from the horizontal, each 12.2 ft long, chords 4.86 and 2.47 ft, 44.8 ft² | height and chords from the drawing, angle from the model |
| V-tail projected areas | 41.6 ft² horizontal, 48.0 ft² vertical; arm 17.9 ft; volumes 0.277 and 0.0137 | derived |
| Fuselage | 44.4 ft long, 5.05 ft wide, 7.3 ft deep at the nose bulge | drawing; width from the model |
| Nacelle | inlet lip at x = 22.5 ft, exhaust at 39.9 ft, thrust line 8.43 ft above the ground, 3.1 ft above the centre of gravity | drawing |
| Gear | main axles at x = 25.29 ft, nose at 10.55 ft: wheelbase 14.74 ft; track 12.4 ft; two wheels a leg; wheels 1.85 and 1.59 ft across | drawing; track from the model |

Checks (limits set before measuring):

| Check | Value | Target | Error | Limit | |
|---|---|---|---|---|---|
| Model scaled by span: length | 57.11 ft | 44.4 | +28.6 % | 1 % | miss |
| Model scaled by span: height | 20.78 ft | 15.2 | +36.7 % | 3 % | miss |
| Model scaled by span: wing area | 598 ft² | 540 | +10.7 % | 3 % | miss |
| Model scaled by length: span | 90.34 ft | 116.2 | -22.3 % | 1 % | miss |
| Model scaled by length: height | 16.15 ft | 15.2 | +6.2 % | 3 % | miss |
| Model, span by span and chords by length: wing area | 465 ft² | 540 | -13.9 % | 3 % | miss |
| Side view: height against NASA's 15.2 ft | 14.34 ft | 15.2 | -5.6 % | 3 % | miss |
| Side view: height against Northrop Grumman's 14.6 ft | 14.34 ft | 14.6 | -1.8 % | 3 % | pass |
| Wing as built: root chord with fillet, against the side view | 8.85 ft | 7.59 | +16.5 % | 5 % | miss |

What the misses mean:

- The first six say one thing: the model can't be scaled as a whole. That is why it is used for shapes only.
- **Root chord, the open one.** NASA's drawing shows the wing root 7.59 ft long, and the model scaled by length
  agrees (7.61 ft). The wing built here is 16.5 % longer in chord because its chords are fitted to the published
  540 ft². With the drawing's chords the area would be 465 ft² (495 ft² with the fillet). Either Jane's area counts
  something this trapezoid doesn't, or the model's taper is wrong. The published area is kept: lift and drag
  coefficients in the flight-data calibration are referred to it, and the calibration of drag against the measured
  climb and cruise-climb takes up what is left. The chord enters only through the Reynolds number and the mean chord.
- **Height.** The drawing gives 14.3 ft to the fin tips, close to Northrop Grumman's 14.6 ft. NASA's 15.2 ft may be
  measured with the aircraft light and its struts extended; it isn't explained in the sources.
- The drawing carries a centre-of-gravity style symbol on the wing root, at x = 24.19 ft. That is 51 % of the mean
  chord as built here, too far aft to be the centre of gravity with a tail this small; it is recorded and not used.

## Mass, centre of gravity and inertia: estimates

Four weights are published (gross, empty, fuel, engine). Everything else in `mass.json` is an estimate.

| Item | Weight, lb | x, ft | |
|---|---|---|---|
| Wing structure | 2,184 | 23.72 | 24 % of the empty weight (estimate) |
| Fuselage structure | 2,002 | 20.87 | 22 % (estimate) |
| V-tail | 273 | 41.36 | 3 % (estimate) |
| Engine | 1,644 | 32.10 | published weight |
| Nacelle and engine installation | 455 | 31.23 | 5 % (estimate) |
| Main and nose gear | 400 and 100 | 25.29, 10.55 | 5.5 % (estimate) |
| Systems, avionics, antennas | 2,042 | 20.76 | the rest of the empty weight; **position chosen** so the aircraft without fuel balances at 25 % of the mean chord |
| Payload and its fittings | 2,350 | 15.54 | gross less empty less fuel |
| Wing fuel | 6,588 | 23.72 | what the wing box holds: 138 ft³ between 15 and 60 % chord out to 90 % of the semi-span |
| Fuselage fuel | 8,712 | 22.88 | the rest: the wing can't hold 15,300 lb |

| Fuel | Weight, lb | Centre of gravity, % mean chord | Ixx | Iyy | Izz, slug ft² | Nose gear load |
|---|---|---|---|---|---|---|
| 100 % | 26,750 | 29.2 | 174,400 | 35,700 | 207,300 | 15.0 % |
| 50 % | 19,100 | 27.9 | 110,200 | 34,000 | 141,500 | 15.4 % |
| 10 % | 12,980 | 25.9 | 58,800 | 32,500 | 88,800 | 16.1 % |
| none | 11,450 | 25.0 | 45,900 | 32,200 | 75,600 | 16.4 % |

The centre of gravity is a choice, not a finding: the tail is small (horizontal volume 0.277), so the neutral point
will be well ahead of mid-chord, and the choice is looked at again when the aerodynamic model gives the neutral
point. The roll and yaw inertias fall by almost three quarters as the wing fuel burns; that is real for an aircraft
that carries more than half its weight as fuel, and the flight laws have to cope with it.

## Weights

| Item | Value | Source |
|---|---|---|
| Maximum takeoff weight | 26,750 lb | NASA fact sheet FS-098, NASA flight-operations briefings 2009 and 2010, FAA programme briefing, Designation-Systems |
| Maximum takeoff weight, NASA 2008 | 25,600 lb | NASA project update, November 2008 (air vehicle characteristics table) |
| Fuel capacity | 15,300 lb | NASA flight-operations briefings 2009 and 2010 |
| Fuel tank capacity, NASA 2008 | 15,436 lb, with a takeoff fuel of 14,500 lb | NASA project update, November 2008 |
| Empty weight with fluids | 9,100 lb | NASA project update, November 2008 |
| Empty weight | 9,200 lb [FAA programme briefing]; 4,177 kg = 9,209 lb [Jane's 1999] | |
| Payload | over 1,500 lb [NASA 2007-2009]; 1,000-1,500 lb [NASA 2009, 2011]; 2,000 lb [NASA 2010, FAA]; 1,200 lb demonstrated [NASA 2017] | |

The two NASA sets are each consistent: 9,100 + 14,500 + 2,000 = 25,600 lb, and 26,750 - 15,300 = 11,450 lb for the
aircraft with its payload. Choice: empty 9,100 lb, fuel 15,300 lb, gross 26,750 lb, which leaves 2,350 lb for payload
and its fittings (derived). Designation-Systems gives an "empty" weight of 14,800 lb beside the RQ-4A; it is the
RQ-4B's (14,950 lb [USAF]) and is not used.

Centre of gravity and inertias are not published. They are built up from the parts and labelled estimates.

## Performance, published

| Item | Value | Source |
|---|---|---|
| Maximum altitude | 65,000 ft | NASA overviews |
| Service ceiling | 62,500 ft | NASA overview 2017 (earlier overviews: 65,000 ft) |
| Cruise speed above 55,000 ft | 335 KTAS | NASA overviews; "from 56,000 to 65,000 ft" [NASA 2009] |
| Other cruise figures | 350 kt [NASA TM, 2007]; loiter 342-343 KTAS [FAA; NASA TM 2012] | |
| Never-exceed speed | 355 KTAS | NASA project update, November 2008 |
| Turn radius above 55,000 ft | 6.5 nmi | NASA project update, November 2008. Derived: 14.1 deg of bank at 335 KTAS |
| Endurance | over 31 h [NASA 2008]; over 31.5 h [NASA 2009]; over 30 h [NASA 2009-2017]; about 35 h [FAA] | |
| Range | over 11,000 nmi [NASA 2008]; over 10,000 nmi [NASA 2009]; 12,500 nmi [FAA] | |
| Runway | 8,000 ft by 150 ft minimum | NASA 2009 |
| Crosswind for landing | 15 kt maximum | NASA flight-operations briefing |
| Electrical | 28 V DC, 186.3 A (5.2 kW) from the engine's generator; 115 V AC, 400 Hz, 8.3 kVA from a hydraulic generator | NASA project update, November 2008 |

Derived from these: 14,500 lb of fuel over 31 h is 470 lb/h on average.

## Performance, measured in flight

From the paper by Pastor and others (2018), which analysed NASA's navigation records of two 2010 flights of N872NA
(sorties 872-0060 and 872-0062). Speeds are indicated unless marked.

| Item | Value |
|---|---|
| Takeoff | rotation at about 130 kt, 37-38 s after the start of the roll; then 150-157 kt |
| Initial climb | 2,500 to 5,000 ft in 59-63 s (2,300-2,500 ft/min) |
| Climb speed | about 150 kt to FL220, then falling so that Mach rises steadily to 0.6 at FL550 |
| Climb rate, 10,000-20,000 ft | 2,538 and 2,357 ft/min |
| 20,000-30,000 ft | 1,961 and 2,113 ft/min |
| 30,000-40,000 ft | 1,319 and 1,354 ft/min |
| 40,000-50,000 ft | 516 and 533 ft/min |
| 50,000-55,000 ft | 123 and 121 ft/min |
| Time from 10,000 to 55,000 ft | 4,607 and 4,584 s (590 ft/min on average) |
| Cruise-climb | from about FL550 at Mach 0.6; 56,250 ft at 83 min, 59,375 ft at 417 min, 62,000 ft at 750 min, 63,750 ft at 1,250 min (first flight); 2-11 ft/min after the first hours |
| Descent | 4,300 ft/min from FL550 to FL300 with a level-off at FL475; 3,900 ft/min from FL300 to FL100 |
| Approach | 1,480 ft/min, then 840 ft/min to touchdown; 160 kt slowing to 145 kt, then 120 kt with the gear down |
| Turns | bank 21 deg at 3,800 ft falling to 14-15 deg above 50,000 ft; 0.86-0.88 deg/s there |

From the ATTREX data, read by `fdm/attrex.py` (next section): cruise at a median Mach 0.605-0.614 and 322-345 KTAS in
the 2013-2015 flights; the highest pressure altitude in any record is 62,769 ft. Banks in the long turns are about
15 deg, which agrees with the table and with the published turn radius.

## ATTREX flight data

The Meteorological Measurement System (NASA Ames) flew on N872NA through the ATTREX campaigns, 2011 to 2015. Its
records are public in NASA's ESPO archive as ICARTT text files. `fdm/attrex.py` reads them as a gzipped stream and
prints, for each flight, the table below and its long steady segments (the full output goes to `fdm/out/`).

What a 20 Hz record holds: static pressure and temperature, true airspeed, Mach, dynamic pressure, angle of attack
and sideslip at the probe, pitch, roll, heading, ground velocity, vertical speed and acceleration, winds, position.
There is no fuel, weight, engine or control-surface channel.

"Steady" was defined before looking: 60 s blocks with roll under 2.5 deg, height changing by less than 1 m/s and
true airspeed within a 5 m/s band, joined into segments of 10 minutes or more.

| Date (UTC start) | Record | Hours | Ends | Highest, ft | Hours above 49,000 ft | Median Mach there | Median KTAS | Steady segments | Steady hours |
|---|---|---|---|---|---|---|---|---|---|
| 2011-10-20 | 1 Hz path | 5.9 | in flight | 56,122 | 4.7 | 0.587 | 337 | 3 | 4.1 |
| 2011-10-24 | 1 Hz path | 3.3 | low | 52,162 | 0.4 | 0.569 | 327 | 2 | 1.4 |
| 2011-10-28 | 1 Hz path | 21.0 | in flight | 62,769 | 19.1 | 0.587 | 337 | 12 | 15.9 |
| 2011-11-05 | 1 Hz path | 16.2 | in flight | 60,384 | 12.8 | 0.583 | 334 | 16 | 10.2 |
| 2011-11-09 | 1 Hz path | 23.4 | low | 62,549 | 17.6 | 0.585 | 336 | 13 | 16.2 |
| 2013-01-19 | 20 Hz | 6.2 | in flight | 59,691 | 4.2 | 0.606 | 336 | 0 | 0.0 |
| 2013-02-05 | 20 Hz | 24.4 | in flight | 62,271 | 20.7 | 0.608 | 329 | 23 | 10.2 |
| 2013-02-09 | 20 Hz | 23.7 | in flight | 62,656 | 18.8 | 0.607 | 330 | 21 | 10.2 |
| 2013-02-14 | 20 Hz | 24.1 | in flight | 62,271 | 18.3 | 0.606 | 334 | 28 | 9.3 |
| 2013-02-21 | 20 Hz | 24.3 | in flight | 62,300 | 18.4 | 0.606 | 331 | 24 | 7.7 |
| 2013-02-26 | 20 Hz | 24.1 | in flight | 62,489 | 19.3 | 0.605 | 335 | 23 | 10.0 |
| 2013-03-01 | 20 Hz | 23.8 | in flight | 62,158 | 19.8 | 0.606 | 332 | 25 | 9.1 |
| 2013-12-20 | 20 Hz | 6.1 | on the ground | 56,698 | 2.8 | 0.609 | 344 | 0 | 0.0 |
| 2014-01-16 | 20 Hz | 19.5 | in flight | 61,602 | 18.1 | 0.614 | 331 | 30 | 14.7 |
| 2014-02-12 | 20 Hz | 16.9 | in flight | 57,375 | 9.5 | 0.598 | 322 | 18 | 4.7 |
| 2014-02-16 | 20 Hz | 17.4 | in flight | 59,823 | 8.9 | 0.605 | 325 | 0 | 0.0 |
| 2014-03-04 | 20 Hz | 12.2 | in flight | 58,878 | 8.0 | 0.609 | 325 | 6 | 1.5 |
| 2014-03-06 | 20 Hz | 17.0 | on the ground | 59,617 | 12.0 | 0.612 | 329 | 12 | 5.1 |
| 2014-03-09 | 20 Hz | 19.5 | in flight | 59,537 | 12.5 | 0.606 | 326 | 11 | 3.6 |
| 2014-03-11 | 20 Hz | 15.1 | in flight | 59,483 | 9.3 | 0.607 | 330 | 7 | 1.7 |
| 2014-03-13 | 20 Hz | 19.2 | in flight | 60,229 | 13.3 | 0.605 | 327 | 21 | 6.4 |
| 2014-03-14 | 1 Hz | 18.7 | in flight | 60,159 | 12.9 | 0.601 | 325 | 19 | 6.1 |
| 2015-02-26 | 20 Hz | 6.1 | in flight | 57,731 | 4.1 | 0.611 | 345 | 3 | 0.7 |
| 2015-03-05 | 20 Hz | 20.8 | in flight | 60,072 | 16.8 | 0.612 | 334 | 27 | 10.6 |
| 2015-03-10 | 20 Hz | 11.2 | in flight | 56,845 | 8.8 | 0.606 | 333 | 16 | 6.0 |
| 2015-03-13 | 1 Hz | 0.6 | in flight | 37,410 | 0.0 | | | 0 | 0.0 |

What the records do and don't cover:

- **Takeoff:** every record begins in the air, at 118-162 KTAS within a few hundred feet of the airfield's height.
  No takeoff roll is in the data.
- **Landing:** two 20 Hz records run to the ground, 2013-12-20 (Edwards) and 2014-03-06 (Guam), ending at about
  45 KTAS in the rollout. Two 2011 path records end low on the approach, still flying. The others stop in the
  descent, between 10,000 and 45,000 ft. On 2013-12-20 the approach
  is flown at about 140 KTAS with 5.4 m/s of sink and the angle of attack at the probe near 4.7 deg.
- **The 2011 flights** have only 1 Hz files (path, attitude and weather as separate files); their Mach in the table is
  from true airspeed and the standard temperature, so it is approximate. NASA's notes in those files list stretches
  lost to power cycling.
- **2014-01-15 and 2014-01-16** are one flight: the 1 Hz path file is dated a day earlier than the 20 Hz file, with
  the same start time and length. The table keeps the 20 Hz record.
- **Three flights have no steady segment** by the definition above (2013-01-19, 2013-12-20, 2014-02-16): they were
  flown as repeated turns and height changes.
- The position columns are named `LN_LAT`, `LN_LONG`, `LN_ALT` in early 2013 and `G_LAT`, `G_LONG`, `G_ALT` from
  December 2013; the reader gives both as `LAT`, `LON`, `ALT`.
- NASA's stated accuracy: pressure 0.3 hPa, temperature 0.3 K, winds 1 m/s, attitude 0.3 deg or better.

## Engine: Rolls-Royce AE 3007H (F137-RR-100)

| Item | Value | Source |
|---|---|---|
| Thrust, sea level | "flat rated at 7,500 lb" | NASA project update, November 2008 |
| | 7,600 lbf | USAF fact sheet (for the RQ-4B), Designation-Systems |
| | 7,050 lbf | Wikipedia's text |
| | 9,500 lbf | Rolls-Royce's present data sheet, for "AE 3007H" |
| Bypass ratio, pressure ratio | 5.0, 23 | Rolls-Royce data sheet |
| Fan diameter, length, weight | 38.5 in, 115.1 in, 1,644 lb | Rolls-Royce data sheet |
| Layout | one fan stage, 14 high-pressure compressor stages, 2 high-pressure and 3 low-pressure turbine stages (the sheet's table says 2 low-pressure) | Rolls-Royce data sheet |

No thrust or fuel-flow map of the H is public. The method that replaces one, and the sea-level fuel flows of the
civil AE 3007 variants from the ICAO databank, are described with the engine model.

Thrust rating: NASA's own figure for its aircraft is 7,500 lbf flat rated. It was found after the plan had set 7,050 lbf
as the starting value; the choice between them is made from the measured climb rates above, and what decides it is
written down before the comparison is run.

## How the real aircraft is flown (for the flight laws and the ground station)

- The Integrated Mission Management Computer flies the mission plan and manages four navigators, two Kearfott
  KN-4074E and two Litton LN-100G; the Kearfotts are switched off shortly after takeoff by standard procedure
  [USAF accident report, 2017].
- That report's sequence, used later as a failure test: one LN-100G gave a false roll; within 5.5 s the aircraft was
  at about 152 deg of roll; structural-load and load-factor faults at 12-13 s; maximum indicated airspeed at 23.5 s;
  probable structural failure at 34 s.
- Control surfaces named in the reports: ailerons with inner and outer wing actuators [USAF accident report, 2017];
  spoilers [DOT&E annual report, FY 2009]. The V-tail's surfaces are confirmed from the 3-D model.
- NASA operations: no flight in icing, precipitation or cloud; the ground crew surveys runway and taxiways to
  precise coordinates for the autonomous taxi; over 280 contingency landing sites, graded green, yellow, purple or red by the pilots
  [NASA flight-operations briefings 2009, 2010].

## Sources

NASA reports are on the NASA Technical Reports Server (ntrs.nasa.gov) under these numbers.

| Short name above | Document |
|---|---|
| NASA project update, November 2008 | NTRS 20090001264, *NASA Global Hawk: Project Update and Future Missions* |
| NASA flight-operations briefings 2009, 2010 | NTRS 20090029219 and 20100003440, *NASA Flight Operations of Ikhana and Global Hawk* |
| NASA overviews | NTRS 20090022147, 20090022389, 20090040628, 20110023961, 20170006086 |
| NASA TM, 2007 | NTRS 20070012403, *NASA Global Hawk: A Unique Capability for the Pursuit of Earth Science* |
| NASA TM 2012 | NTRS 20120008519, *An Evaluation of Protocols for UAV Science Applications* |
| NASA fact sheet FS-098 | *Global Hawk High-Altitude Long-Endurance Science Aircraft*, NASA Armstrong |
| NASA TM 102840 | NTRS 19910007688, Hicks and Cliff, *An Evaluation of Three Two-Dimensional Computational Fluid Dynamics Codes Including Low Reynolds Numbers and Transonic Mach Numbers*, 1991: the LRN 1015 and its tunnel test |
| UIUC database | UIUC Airfoil Coordinates Database, `lrn1015.dat` |
| Pastor and others (2018) | *Macroscopic Performance Analysis of NASA's Northrop Grumman RQ-4A*, Aerospace 5(1), 6, doi:10.3390/aerospace5010006 |
| ATTREX data | NASA ESPO archive, espoarchive.nasa.gov/archive/browse/attrex, Meteorological Measurement System files |
| FAA programme briefing | *Global Hawk Program Overview*, faa.gov |
| USAF fact sheet | *RQ-4 Global Hawk*, af.mil |
| USAF accident report, 2017 | Accident Investigation Board report, RQ-4B T/N 07-2029, near Lone Pine, California, 21 June 2017 |
| DOT&E annual report, FY 2009 | Director, Operational Test and Evaluation, *Global Hawk*, FY 2009 |
| Rolls-Royce data sheet | *AE 3007 turbofan*, rolls-royce.com |
| Designation-Systems | designation-systems.net, *Northrop Grumman RQ-4 Global Hawk* |
| UTHM thesis | a 2013 thesis on transient flight analysis, Universiti Tun Hussein Onn Malaysia; its table 2.4, *Global Hawk Geometry*, quotes Jane's 1999 |
