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

No thrust or fuel-flow map of the H is public. `fdm/engine.py` is the model that replaces one; it writes
`engine.json` (maximum thrust and its fuel flow, idle, and TSFC at part power, over altitude to 70,000 ft and Mach to
0.7, standard atmosphere).

### The engine model

**One engine, several ratings.** The AE 3007 family is treated as one piece of hardware run at different ratings.
The ICAO Engine Emissions Databank measures every civil variant at sea level (thrust, fuel flow at 100, 85, 30 and
7 % thrust, pressure ratio, bypass ratio). The highest-rated, the AE 3007A2 at 9,494 lbf, is where the model's
reference point is fitted; that is also Rolls-Royce's "9,500 lbf" for the H. The Citation X's C1 at 7,073 lbf is
then the same engine throttled back, and its ICAO row becomes a check. **Our reading of the thrust figures:** the
H can give about 9,500 lbf at sea level and is flat rated at 7,500 lbf in the Global Hawk [NASA], as the C1 is
flat rated in the Citation X; 7,600 and 7,050 lbf are other statements of a rating. Above about 15,000 ft the
rating no longer matters: the engine is on its own limits.

**The cycle.** A two-spool turbofan with separate exhausts, by the textbook analysis (Mattingly, *Elements of
Propulsion*): away from the reference point both turbines stay choked, and the power balance of each spool gives the
fan and compressor pressure ratios, the bypass ratio and the air flow. Component efficiencies are fixed. It has no
component maps and no Reynolds-number effect.

| Reference point (sea level, static) | Value | |
|---|---|---|
| Thrust, pressure ratio, bypass ratio, fuel flow | 42.23 kN, 20.2, 4.79, 0.466 kg/s | ICAO, AE 3007A2 |
| Air flow | 129 kg/s (284 lb/s) | **estimate:** the 38.5 in fan with Mach 0.55 at its face |
| Bypass jet speed over core jet speed | 0.8 | **choice:** usual design practice |
| Fan pressure ratio, turbine entry temperature, polytropic efficiencies | 1.758, 1,380 K, 0.918 | fitted to the three lines above |

**Limits on maximum thrust**, the lowest of:
- the fan's corrected speed: 1.064 of its value at the A2's takeoff. **A fit** to one number, the C1's thrust at
  45,000 ft in Ghazi's table;
- the turbine entry temperature of the A2's takeoff, 1,380 K;
- the flat rating, 7,500 lbf.

**Fuel flow** is the cycle's above 60 % of the thrust at the reference fan speed. Throttled further back the cycle
fails (at 30 % thrust it is 40 to 60 % low), so below 30 % the fuel flow follows the shape of the A2's ICAO points,
with a blend between. Idle is 7 % thrust, as the ICAO idle point: a class estimate, as are spool times later.
On top lies an **installation factor, a fit:** the engine in the Citation X burns 6.2 % more at 1,500 ft and 10.1 %
more at 45,000 ft than the cycle fitted to the bare engine's ICAO test (bleed, power offtake, inlet). The factor is
held at 10.1 % above 45,000 ft and used unchanged for the Global Hawk, whose installation is not the Citation X's.

### Checks

Limits were written before any result. "Predicted" rows used nothing from the source they are compared with.

| Check | Model | Source | Error | Limit | |
|---|---|---|---|---|---|
| C1 takeoff as a rating of this engine: fuel flow | 0.3308 kg/s | 0.3222 [ICAO] | +2.7 % | 5 % | pass, predicted |
| C1 takeoff: pressure ratio | 15.88 | 16.58 [ICAO] | -4.2 % | 5 % | pass, predicted |
| C1 takeoff: bypass ratio | 5.21 | 5.10 [ICAO] | +2.1 % | 5 % | pass, predicted |
| C1 fuel flow at 85 % thrust | 0.2858 kg/s | 0.2689 [ICAO] | +6.3 % | 5 % | **miss**, predicted |
| C1 fuel flow at 30 % thrust | 0.1103 kg/s | 0.0991 [ICAO] | +11.3 % | 15 % | pass, from the A2's ICAO shape |
| C1 fuel flow at 7 % thrust | 0.0521 kg/s | 0.0418 [ICAO] | +24.7 % | none | from the A2's ICAO shape |
| A2 fuel flow at 85 % thrust | 0.3832 kg/s | 0.3880 [ICAO] | -1.2 % | 5 % | pass, predicted |
| TSFC at 1,500 ft, Mach 0.234, maximum climb | 0.500 | 0.531 [Ghazi] | -5.9 % | 8 % | pass, predicted |
| TSFC at 45,000 ft, Mach 0.564, maximum climb | 0.565 | 0.622 [Ghazi] | -9.2 % | 8 % | **miss**, predicted |
| Fan corrected speed, 45,000 ft over 1,500 ft | 1.220 | 1.258 [Ghazi's N1] | -3.0 % | 5 % | pass, predicted |
| Thrust at 43,835 ft at the fitted limit | 1,382 lbf | 1,335 [Ghazi] | +3.5 % | 2 % | **miss**, after the fit |
| H: pressure ratio at the limit, 60,000 ft, Mach 0.6 | 23.7 | 23 [Rolls-Royce] | +3.1 % | 10 % | pass, predicted |

- **The two TSFC rows** say the bare-engine cycle is 6 to 9 % low on fuel against the installed engine, more at
  altitude. That is what the installation factor then takes up; after it, Ghazi's five other rows are within 0.4 %,
  which only shows the fit is smooth.
- **C1 at 85 %:** the family members differ by a few percent at the same thrust (the A1E burns 3 % more than the
  model there, the C1 6 % less). The H's own place in that spread isn't known: plus or minus 6 % on fuel flow.
- **Thrust at 43,835 ft:** Ghazi's table gives 2 % more thrust for 3.5 % more air pressure. The table is an
  illustration in his thesis (its time column implies 2,600 ft/min at 45,000 ft), so 2 % was too tight a limit for it.
- **Pressure ratio 23:** the model reaches Rolls-Royce's figure at its altitude limit, not at sea level takeoff
  (16.6 at the flat rating). The data sheet's 23 is taken to be the top-of-climb value.
- **The altitude data is thin:** one table of seven rows at two heights, from a simulator model of another aircraft's
  engine, stopping at 45,000 ft. From 45,000 to 65,000 ft the model is physics with nothing to check it against
  until the whole aircraft is compared with NASA's climb and cruise-climb.
### A second model: NASA's pyCycle

`fdm/engine_pycycle.py` builds the same engine in pyCycle (NASA's cycle analysis tool on OpenMDAO): fan, splitter,
high-pressure compressor, burner, two turbines, two nozzles, two shafts, laid out as pyCycle's own turbofan example
without its booster. It differs from the model above where that one is weakest: it has component maps (pyCycle's
generic ones, scaled), turbine cooling flows and tabulated gas properties. Its design point is the same ICAO row of
the A2 with the same fan pressure ratio; the turbine entry temperature is a round 3,000 R (1,667 K), because at the
first model's 1,380 K this cycle has no solution; nothing is tuned. pyCycle is a tool, not part of this repository:
`fdm/mkpycycle.sh` sets it up in `tools/pycycle/`, which git ignores (pyCycle 4.4.0 needs two lines patched to run
under NumPy 2, which the script does on a copy).

Limits written before any run of it.

| Check | pyCycle | Source | Error | Limit | |
|---|---|---|---|---|---|
| A2 takeoff (the design point): fuel flow | 3,589 lb/h | 3,698 [ICAO] | -3.0 % | 5 % | pass, predicted |
| A2 fuel flow at 85 % thrust | 2,876 lb/h | 3,079 [ICAO] | -6.6 % | 5 % | **miss** |
| C1 takeoff as a rating: fuel flow | 2,464 lb/h | 2,557 [ICAO] | -3.6 % | 5 % | pass |
| C1 takeoff: pressure ratio | 15.66 | 16.58 [ICAO] | -5.6 % | 5 % | **miss** |
| C1 takeoff: bypass ratio | 5.10 | 5.10 [ICAO] | 0.0 % | 5 % | pass |
| TSFC at 1,500 ft, Mach 0.234 | 0.448 | 0.531 [Ghazi] | -15.6 % | 8 % | **miss** |
| TSFC at 45,000 ft, Mach 0.564 | 0.556 | 0.622 [Ghazi] | -10.6 % | 8 % | **miss** |
| Fan corrected speed, 45,000 ft over 1,500 ft | 1.462 | 1.258 [Ghazi's N1] | +16.2 % | 5 % | **miss** |
| Pressure ratio at the limit, 60,000 ft | 23.7 | 23 [Rolls-Royce] | +3.1 % | 10 % | pass |

The two models against each other, each with its fan-speed limit fitted to the same number (Ghazi's thrust at
45,000 ft), at Mach 0.6, bare engine:

| Altitude, ft | Maximum thrust, lbf: pyCycle, ours | Difference | TSFC: pyCycle, ours | Difference | Limit |
|---|---|---|---|---|---|
| 50,000 | 1,033, 1,035 | -0.2 % | 0.572, 0.580 | -1.4 % | 5 %, pass |
| 55,000 | 817, 814 | +0.4 % | 0.573, 0.580 | -1.2 % | 5 %, pass |
| 60,000 | 645, 640 | +0.7 % | 0.572, 0.580 | -1.4 % | 5 %, pass |
| 65,000 | 502, 503 | -0.2 % | 0.572, 0.580 | -1.4 % | 5 %, pass |

What this does and doesn't show:

- **At altitude the two models are the same engine:** pressure ratio 23.7 and bypass ratio 4.5 in both at the limit,
  fuel within 1.4 %. They share the design point and the one fitted thrust, and nothing else: one has component
  maps and cooling flows, the other neither.
- **The thrust agreement is weaker evidence than it looks.** Above 45,000 ft the air temperature is constant, so at
  a fixed fan corrected speed and nearly the same Mach number any cycle model scales thrust with air pressure. Both
  do. What neither has is the loss of efficiency at low Reynolds number, which grows with height: that stays open
  until the whole aircraft is compared with NASA's cruise-climb.
- **Both bare-engine models burn about 10 % less than the Citation X's installed engine at 45,000 ft** (-9.2 and
  -10.6 %). Two models agreeing on that supports reading the difference as installation, which is what the
  installation factor carries.
- **At low altitude and part power they differ:** at 1,500 ft pyCycle is 15.6 % under Ghazi, the first model 5.9 %.
  There the fuel flow carries about 10 % of model uncertainty. It matters for the climb's fuel, little for endurance.
- **pyCycle's fan needs far more speed for the same job** (+16 % on the speed ratio; its fan runs at 118 % of the
  top speed line of its generic map at the limit, extrapolated). The first model's simple fan-speed measure is the
  closer one to Ghazi's N1 (-3 %). Fan speed from either is for display only.

### The AE 3007H as modelled (standard atmosphere)

| Altitude, ft | Mach | Maximum thrust, lbf | Fuel flow, lb/h | TSFC | Limit |
|---|---|---|---|---|---|
| 0 | 0 | 7,500 | 2,972 | 0.396 | rating (9,494 lbf without it) |
| 10,000 | 0.27 | 6,149 | 3,283 | 0.534 | temperature |
| 20,000 | 0.33 | 4,212 | 2,305 | 0.547 | fan speed |
| 30,000 | 0.42 | 2,666 | 1,515 | 0.568 | fan speed |
| 40,000 | 0.50 | 1,654 | 979 | 0.592 | fan speed |
| 50,000 | 0.60 | 1,035 | 661 | 0.638 | fan speed |
| 55,000 | 0.60 | 814 | 520 | 0.638 | fan speed |
| 60,000 | 0.60 | 640 | 409 | 0.638 | fan speed |
| 65,000 | 0.60 | 503 | 321 | 0.638 | fan speed |

Against NASA's whole-aircraft figures (windows, not checks, until the drag model exists): at 60,000 ft and 15,000 lb,
a lift-to-drag ratio of 25 to 35 needs 430 to 600 lbf of the 640 available and burns 273 to 382 lb/h; NASA's flights
average about 470 lb/h over 31 h with the climb in it. Breguet endurance with TSFC 0.637 and all 15,300 lb of fuel
is 33 h at a lift-to-drag ratio of 25 and 40 h at 30.

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
| ICAO | ICAO Aircraft Engine Emissions Databank, rows for the AE 3007 variants, through TU Delft's OpenAP (`engines.csv`) |
| Ghazi | G. Ghazi, doctoral thesis on a Cessna Citation X performance model, ETS Montréal (LARCASE): table 2.1, one AE 3007C1 at maximum climb, from a Level D simulator's model |
| Mattingly | J. D. Mattingly, *Elements of Propulsion: Gas Turbines and Rockets*, AIAA, chapter 8 |
| Designation-Systems | designation-systems.net, *Northrop Grumman RQ-4 Global Hawk* |
| UTHM thesis | a 2013 thesis on transient flight analysis, Universiti Tun Hussein Onn Malaysia; its table 2.4, *Global Hawk Geometry*, quotes Jane's 1999 |
