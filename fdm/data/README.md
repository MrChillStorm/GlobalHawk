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

Wing sweep, taper, dihedral, twist, the V-tail's chords, the control-surface outlines and the gear positions
are not published anywhere we found (the V-tail's 50 deg angle, 11.4 ft span and 42.8 ft² per surface are: Jane's, through a spec page). Where they come from is the next section.

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
| Width: fuselage | 3-D model | published length |
| Main gear track | 10.8 ft | **measured, two photographs of RQ-4As:** 11.2 +- 0.5 ft (the 2001 head-on view, scaled by the tyre, a person and the aircraft's height) and 10.1 +- 0.7 ft (NASA 871 and 872 on the ramp, a camera-model fit of both aircraft). NASA's 3-D model gave 12.36 ft at the scale of the length (it is not isotropic); the earlier 13.66 ft was that plus an estimate of 0.65 ft a side (`MAIN_TRACK` in `fdm/geometry.py`; docs/PLAN.md, "Lateral dimensions") |

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
| V-tail | two panels at 50 deg from the horizontal, each 11.7 ft long, chords 4.86 and 2.47 ft, 42.8 ft² | height and chords from the drawing; the angle from Jane's and a spec page (50 deg) and head-on photographs (50.8 +-0.5), not the 3-D model, whose raw slope gave 47.1 (its axes are not scaled alike). The published 42.8 ft² per surface is matched by the drawing's chords and this angle; the published 11.4 ft span is 2.6 % shorter than the model's 11.7 (cause not established, left as drawn) |
| V-tail projected areas | 41.6 ft² horizontal, 48.0 ft² vertical; arm 17.9 ft; volumes 0.277 and 0.0137 | derived |
| V-tail lateral position | tips 10.2 ft from the centreline, roots 2.68 ft (follows from the tip, the rise and the 50 deg) | **measured, the same two photographs:** 10.7 +- 0.5 and 10.06 +- 0.2 ft; NASA's 3-D model gave 9.9 ft at the scale of the length; the earlier root offset, 1.26 ft, was a quarter of the model's fuselage width, a guess (`VTAIL_TIP_Y`) |
| Fuselage | 44.4 ft long, 5.05 ft wide, 7.3 ft deep at the nose bulge | drawing; width from the model |
| Nacelle | inlet lip at x = 22.5 ft, exhaust at 39.9 ft, thrust line 8.43 ft above the ground, 3.1 ft above the centre of gravity | drawing |
| Gear | main axles at x = 25.29 ft, nose at 10.55 ft: wheelbase 14.74 ft; track 10.8 ft; two wheels on each main leg, one on the nose leg; wheels 1.85 and 1.59 ft across in the drawing | drawing; track from two photographs; wheel counts from photographs |
| Tyres | nose 18 x 6.5-8 (0.457 x 0.165 m), mains 22 x 5.75-12 (0.559 x 0.146 m) | **assumed, unverified:** no source for the nose size (the F-5's nose gear is said to be the origin of the unit: airforce-technology.com); the mains from the Learjet 45's Goodyear 226K08-4 and a parts catalogue's Goodyear 226K23-2 for the RQ-4A. The 3-D model's nose wheel is the nose size; its main tyres (about 16.5 in) are not yet the main size |

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
| Systems, avionics, antennas | 2,042 | 19.92 | the rest of the empty weight; **position chosen** so the aircraft without fuel balances at 22 % of the mean chord |
| Payload and its fittings | 2,350 | 15.54 | gross less empty less fuel |
| Fuel: wing inboard left | 1,736 | 22.40 | our own layout: the real tanks are not public |
| Fuel: wing inboard right | 1,736 | 22.40 | our own layout |
| Fuel: wing outboard left | 1,557 | 24.54 | our own layout |
| Fuel: wing outboard right | 1,557 | 24.54 | our own layout |
| Fuel: fuselage forward | 5,624 | 19.30 | our own layout |
| Fuel: fuselage aft | 3,088 | 27.50 | our own layout |

The wing box (between 15 and 60 % chord, out to 90 % of the semi-span) holds 138 ft³, 6,588 lb: the wing can't
hold 15,300 lb, so the rest is in the fuselage. The forward and aft fuselage tanks are sized so that all the fuel
together has its centre at 22 % of the mean chord.

| Fuel | Weight, lb | Centre of gravity, % mean chord | Ixx | Iyy | Izz, slug ft² | Nose gear load |
|---|---|---|---|---|---|---|
| 100 % | 26,750 | 22.0 | 164,600 | 37,200 | 198,900 | 17.4 % |
| 50 % | 19,100 | 22.0 | 105,300 | 34,800 | 137,400 | 17.4 % |
| 10 % | 12,980 | 22.0 | 57,800 | 32,900 | 88,200 | 17.4 % |
| none | 11,450 | 22.0 | 45,900 | 32,400 | 75,900 | 17.4 % |

The centre of gravity is a choice, not a finding, and the fuel management holds it: every tank gives up fuel in
proportion to its contents. It was first put at 25 to 29 % of the mean chord; the aerodynamic models then put the
neutral point at 30 to 33 % (next section), so it was moved forward to 22 %, which leaves about 8 % between the
two. The Air Force's flight-test paper refers the real aircraft's performance to 31 %: see the open question
under "Against the Air Force's flight test". The roll and yaw inertias fall by almost three quarters as the wing
fuel burns; that is real for an aircraft that carries more than half its weight as fuel, and the flight laws have
to cope with it.

## Aerodynamics

No wind-tunnel or CFD data of the Global Hawk is public. Two models are built and compared, and the flight data
calibrates what they leave open.

- **The strip model, `fdm/strips.py`: what ships.** The wing is 80 strips on a lifting line, each taking its lift,
  drag and moment from the LRN 1015's section table at its own angle of attack and Reynolds number and the flight
  Mach number, with the trailing vortices of all strips giving each its downwash. The V-tail's strips sit in the
  wing's downwash and sidewash. Fuselage and nacelle add skin-friction drag and the slender-body moments.
- **The reference model, `fdm/aero_ref.py`:** the same geometry in AeroSandbox, by its build-up method (bodies and
  control surfaces in it) and its vortex lattice (wing and tail only).
- **Section data:** NeuralFoil through AeroSandbox, which adds a compressibility correction.

Not in either model: the wing's bending in flight (the real wing takes up dihedral under load, which adds roll
due to sideslip), spoilers, the gear, ground effect. Estimates that no source gives: the ailerons (55 to 95 % of the
semi-span, 25 % chord), the ruddervators (the whole panel span, 30 % chord), the tail section (symmetric, 10 %
thick), 15 % on body drag for antennas and radomes, 60 % of the nacelle's surface in the airflow, and the wing's
incidence on the fuselage (zero for now: the flight data's angle of attack sets it).

### The section data against NASA's tunnel test

NASA TM 102840, figure 24, gives measured lift, drag and moment of the LRN 1015. `fdm/digitise_lrn1015.py` reads the
points off the scanned figure into `lrn1015_tunnel.json`: the three cases whose axes were verified by eye, Mach 0.2
at Reynolds 1 million and Mach 0.6 at 1 and 2 million, which is where the wing cruises. Compared at equal lift
coefficient between 0.4 and 1.0, as the report itself does: it calls its angles of attack uncertain by up to 3 deg
of wall correction. Limits were written first.

| | Mach 0.2, Re 1 million | Mach 0.6, Re 1 million | Mach 0.6, Re 2 million | Limit | |
|---|---|---|---|---|---|
| Profile drag: tunnel, model | 0.00754, 0.00803 | 0.00964, 0.00829 | 0.00751, 0.00655 | | |
| Drag error | +6.5 % | -14.0 % | -12.8 % | 15 % | pass, measured |
| Moment about the quarter chord: tunnel, model | -0.095, -0.107 | -0.108, -0.133 | -0.111, -0.134 | | |
| Moment difference | -0.013 | -0.025 | -0.023 | 0.02 | **miss** at Mach 0.6 |
| Maximum lift: tunnel, model | 1.43, 1.36 | 1.31, 1.20 | 1.42, 1.20 | | |
| Maximum lift error | -5.4 % | -8.8 % | -15.8 % | 10 % | **miss** at Re 2 million |
| Angle of attack, model less tunnel | -0.9 deg | -0.3 deg | -0.3 deg | none | |
| Lift-curve slope per deg: tunnel, model | 0.113, 0.108 | 0.165, 0.131 | 0.154, 0.137 | none | |

- **Drag is inside the limit but one-sided at Mach 0.6:** the model's sections have 13 to 14 % less drag than the
  tunnel there (five and six points). Wing profile drag is about 45 % of the aircraft's drag at cruise, so this
  alone would make the model's lift-to-drag ratio about 6 % too good. It is left as it is, and the calibration
  against the measured cruise-climb decides.
- **Moment:** the compressibility correction scales the low-speed moment by 1.25 at Mach 0.6; the tunnel shows it
  growing by 1.15. The model's wing is more nose-down than the real section by about 0.024, which costs about a
  degree of ruddervator in trim.
- **Maximum lift at Mach 0.6:** the model stops at 1.20, at 4 deg, where the correction puts a shock stall; the
  tunnel reached 1.31 and 1.42. The model stalls early, on the safe side for the flight laws' limits.
- **Lift-curve slope at Mach 0.6:** the tunnel's is 13 to 26 % steeper than the model's. The report's own caveat
  on angle of attack applies, but lift does grow faster than the simple correction says once the flow over the
  section turns supersonic. The flight data's lift curve will tell.

**Compressibility of the moment, 2026-11-13 (a fit and its evidence; `fdm/section_study.py`).** The table above is what NeuralFoil's
data gave. Its moment grew 24 % from Mach 0.2 to 0.6 at the tunnel's lift coefficients (Prandtl-Glauert alone is 22 %), the
tunnel's 15.5 % (14 to 17 %, two Reynolds numbers). XFOIL 6.99 (M. Drela; built here with gfortran, double precision, its plot
library replaced by empty subroutines; the recipe is in `section_study.py`, the build in the untracked `tools/xfoil-build`), with
its Karman-Tsien correction, free transition at n_crit 9, gives 19 %, and at Mach 0.2 a moment of -0.1048 where NeuralFoil gives
-0.1079 and the tunnel -0.0945: the solvers agree with each other, 0.010 to 0.013 more nose-down than the tunnel, which no
compressibility correction touches. At Mach 0.6 XFOIL stops converging past its first sonic point (six points at Re 1 million,
eight at 2 million: not a table; its lift slope falls past Mach 0.55, which is not believed). **Fit, one parameter, named:** the wing's
moment is multiplied by beta^(1-K) with beta = sqrt(1 - M^2), so that it grows as beta^-K; K = 0.651 gives the tunnel's growth,
`strips.CM_MACH_K = 0.65`. Not applied to lift, drag or the tail. After it the moment misses at Mach 0.2, 0.6 (Re 1, 2 million) by
-0.0124, -0.0154, -0.0132 (limit 0.02: S2 now passes); S1 and S3 are as they were (S3 at Mach 0.6, Re 2 million stays a miss).
**What it did that it was not fitted to do:** the bare airframe's speed mode at the cruise (60,000 ft, Mach 0.6, 15,000 lb) was a real
root doubling in 10.4 s; with each table of the aerodynamic model held at its Mach 0.45 values above that Mach, one at a time, only
holding the moment's removed it (the lift's and the drag's left it at 8.7 and 11.1 s). With the exponent it is a phugoid of 176 s,
damping 0.06. The trimmed lift-curve slope is 2.8 and 5.6 % over the flights' (limit 10 %), and the mission's drag increment was
refitted, 0.00564 to 0.00586, because the time to 55,000 ft had gone to -6.1 % (limit 5 %); the fan-speed factor stays 1.01. (Fitted again, 0.00355, with the CFD's wave drag: see below.)

**A transonic RANS run (2026-11-13; `fdm/cfd/`).** SU2 8.6.0 on a 40,000-cell wall-resolved mesh, Spalart-Allmaras, fully turbulent, 42 cases (Mach 0.2 at Re 1
million, 0 to 16 deg; Mach 0.6 at Re 1 and 2 million, -2 to 10 deg; Mach 0.65 at Re 1.5 million, 0 to 8 deg). Written first: trusted for the stall only if its moment
at the tunnel's lifts is within 0.02 of the tunnel's at both Mach 0.6 cases and its maximum lift within 10 % at Re 1 million. **It is not (moment -0.0283 and
-0.0256), so the tables are unchanged.** What it shows: maximum lift at Mach 0.6 1.374 and 1.396 (tunnel 1.312 and 1.423, the model 1.196 and 1.198); the fall from Mach 0.6
to 0.65 -21.8 % (the model's -18 %); the moment's growth from Mach 0.2 to 0.6 at the tunnel's lifts 1.105 (tunnel 1.139, XFOIL 1.187, tables before the exponent 1.237).
Fully turbulent drag at lift 0.7 is 0.0192 (Mach 0.6, Re 1 million) against the tunnel's 0.0096 free-transition figure at its lifts: reported, not limited.

### Against the Air Force's flight test of the Block 20

Eaton and Woolf (U.S. Air Force Flight Test Center, 2009) compare the RQ-4 Block 20's wind-tunnel model with 40
envelope-expansion flights. The Block 20 is the RQ-4B: a longer wing than the aircraft modelled here, the same
engine, the same layout. Their figures have axes without numbers, only scales, so slopes can be read and absolute
values can't. `fdm/digitise_sfte.py` reads the slope of each Mach number's cloud of flight-test points from their
lift-curve figure (untrimmed, standardised to a rigid airframe). No limit was set: the paper arrived after the
model was built.

| Mach | Flight test, Block 20, per deg | Our strips, RQ-4A, per deg | Difference |
|---|---|---|---|
| 0.27 | 0.102 | 0.118 | +16 % |
| 0.40 | 0.114 | 0.124 | +8 % |
| 0.50 | 0.116 | 0.129 | +12 % |
| 0.55 | 0.125 | 0.132 | +6 % |
| 0.575 | 0.138 | 0.134 | -3 % |
| 0.60 | 0.140 | 0.138 | -1 % |

- **At the cruise Mach numbers the lift-curve slope is within 3 % of flight test.** Below Mach 0.55 ours is 6 to 16 %
  steeper: in flight the slope grows faster with Mach number than the compressibility correction gives. The
  low-Mach clouds are short (a lift-coefficient range of 0.34 at Mach 0.27), so their slopes are the least certain.
- **The drag polars can't be used the same way.** The paper puts the scatter of its drag points at plus or minus
  10 %, and a curve fitted to each cloud isn't stable. What the figure does show is the shape: at every Mach number
  the flight points sit in a bucket where drag changes by less than about 0.003 over 0.4 to 0.6 of lift
  coefficient, and above a "break" lift coefficient the drag rises quickly. The paper says the break came about
  0.1 lower in flight than in the tunnel.
- What else the paper says that bears on this model:
  - the performance analysis is referred to a centre of gravity at **31 % of the mean chord**, the aerodynamic
    analysis to 25 %. The real aircraft, then, flies with its centre of gravity well aft of where this model's
    neutral point (30 to 33 %) would allow. Either the real neutral point is further aft than both our models say,
    or the real aircraft flies with little or no static margin and leaves stability to its flight control
    system. Our centre of gravity stays at 22 % until the flight data says more; it is the largest open question
    of the aerodynamic model;
  - directional stability in flight was 20 to 40 % below the wind-tunnel prediction, ruddervator power in yaw
    slightly above, and less nose-up elevator was needed to trim than predicted;
  - the Rolls-Royce cycle deck, with Northrop Grumman's installation effects, predicted installed thrust and fuel
    flow within 5 % at high thrust on the ground and fuel flow within 5 % in flight; power extraction for the
    payload was large enough to be a named condition of the endurance requirement;
  - the aircraft spends most of a mission in climb or cruise-climb at maximum thrust.

### The two models against each other

*(Phase 3 record; not refreshed since: see the 2026-11-13 section above.)* At Mach 0.6 and 60,000 ft, 2.5 deg, moments about 27 % of the mean chord (`fdm/out/aero_compare.txt`,
`aero_compare.json`). The plan set no limits here: the spread between the models is each quantity's uncertainty.

| | Strips | Build-up | Vortex lattice | |
|---|---|---|---|---|
| Lift coefficient at 2.5 deg | 0.712 | 0.774 | | 0.5 deg apart in zero-lift angle |
| Lift-curve slope, per deg | 0.134 | 0.132 | 0.139 | within 5 % |
| **Neutral point, % mean chord** | **29.8** | **32.5** | | |
| Neutral point without the bodies | 35.8 | | 42.3 | the bodies cost 6 % in ours |
| Pitching moment at 2.5 deg | -0.080 | -0.119 | | nose-down: the section's own moment |
| Side force due to sideslip, per deg | -0.0087 | -0.0067 | -0.0084 | |
| Roll due to sideslip, per deg | -0.0003 | -0.0003 | -0.0007 | almost none: no dihedral modelled |
| Yaw due to sideslip, per deg | +0.0008 | +0.0005 | +0.0013 | stable, weakly; the lattice has no bodies |
| Roll due to aileron, per deg | -0.0065 | -0.0080 | | 20 % apart |
| Pitch due to ruddervators, per deg | -0.0219 | none | | the reference gives no tail-control effect; hand formula -0.023 |
| Yaw due to ruddervators, per deg | +0.0010 | none | | |
| Roll damping | -0.91 | -0.83 | -0.85 | within 10 % |
| Pitch damping | -13.0 | -8.9 | -26.1 | a factor of 3 between the reference's own two methods |
| Yaw damping | -0.024 | -0.016 | -0.053 | the same |

| Angle of attack | CL: strips, build-up | CD: strips, build-up | L/D: strips, build-up |
|---|---|---|---|
| 0 deg | 0.371, 0.448 | 0.0194, 0.0188 | 19.1, 23.9 |
| 2 deg | 0.632, 0.710 | 0.0210, 0.0218 | 30.0, 32.5 |
| 4 deg | 0.902, 0.976 | 0.0252, 0.0289 | 35.9, 33.8 |
| 5 deg | 1.026, 1.099 | 0.0284, 0.0341 | 36.1, 32.2 |

Trimmed with the ruddervators (strips): lift-to-drag ratio 29.8 at a lift coefficient of 0.6, 31.9 at 0.7, 34.7 at
0.8, 36.8 at 0.9, with 3.7 to 4.2 deg of ruddervator, trailing edge up.

- **Lift-to-drag ratio:** both models reach 34 to 36, inside the window set beforehand (25 to 40). With the Phase 2
  engine that is about 45 h of Breguet endurance against NASA's 31: too good. Known reasons on the model's side
  are the sections' drag (13 % low against the tunnel), no trim drag from the thrust line, no tail induced drag in
  ours, and whatever the real airframe's antennas, gaps and leaks cost. This is what the flight data is for.
- **Static margin:** with the neutral point at 29.8 % (ours) the first centre-of-gravity choice, up to 29 %, left
  almost none. It is now 20.0 to 24.4 %: 5.4 % of margin at the worst in ours, 8.1 % in the build-up.
- **Pitch and yaw damping** differ by a factor of 2 to 3 between methods. They matter to the flight laws' gains,
  which therefore have to be robust to it.
- **The reference gives no ruddervator derivatives** (its control surfaces on the two tail panels had no effect in
  either of its methods as set up here). The strips' value agrees with the textbook V-tail formula within 5 %.

## The JSBSim model

`fdm/genghawk.py` writes `GlobalHawk/GlobalHawk.xml` and `GlobalHawk/Systems/` from the data files in this folder;
`fdm/harness.py` loads, trims and flies it; `fdm/phase3_checks.py` checks it (32 checks; all passed before the
calibration, and 30 pass after it: the reference build no longer trims at cruise, see "Calibration"). The trims and
modes in the tables below are from before the calibration.

- **Aerodynamics:** tables over angle of attack and Mach number, sampled from the strip model by
  `fdm/aerotables.py`. Each Mach number is sampled at one altitude, the one where the aircraft flies that Mach
  number on its climb schedule (Mach 0.15 at sea level, 0.30 at 10,000 ft, 0.45 at 30,000 ft, 0.55 at 45,000 ft,
  0.60 and 0.65 at 60,000 ft), so the Reynolds number is right along the schedule and approximate off it. Past the
  tables' ends (-6 and 12 deg) they run on to a flat plate, plainly.
- **Engine:** not JSBSim's turbine but system channels, generated from `engine.json`: maximum thrust over pressure
  altitude, Mach number and the temperature's offset from standard, idle thrust, fuel flow against thrust, a 2 s
  spool as the fan's speed (a rate-limited first-order lag fitted to a recording, see "The engine's spool" below; it was a 2 s lag, a class estimate),
  thrust applied on the nacelle's axis.
- **Fuel: our own design**, since the real system isn't public. Six tanks: an inboard and an outboard tank in each
  wing, and a forward and an aft tank in the fuselage, sized so that all the fuel together has its centre at the
  centre-of-gravity target, 22 % of the mean chord. The management draws from every tank in proportion to its
  contents, which keeps the centre of gravity there from full to empty and the wings balanced. Holding the centre
  of gravity comes before relieving wing bending (burning wing fuel last would move it).
- **Controls:** the surfaces follow the commands directly, 20 deg at full command (an estimate). No actuators and
  no flight laws yet.
- **Gear:** three contact points with estimated springs, enough to stand on.
- **A second build** (`python3 fdm/genghawk.py DIR --ref`) takes its tables from AeroSandbox's build-up instead,
  with the strips' tail-control tables.

| Check | Result | Limit |
|---|---|---|
| Weight, centre of gravity and inertias against `mass.json`, full and without fuel | within 0.01 % | 0.1 to 5 % |
| Maximum thrust and its fuel flow at four conditions against `engine.py` | within 0.31 % | 1 % |
| Lift and drag coefficients at the two trims against a direct strip solve | within 0.57 % | 2 % |
| Fuel leaving the tanks in 10 minutes of cruise against the fuel flow integrated | equal | 0.5 % |
| Centre of gravity moved in those 10 minutes | 0.00002 % of the mean chord | 0.2 % |
| Both builds trim at cruise and at the climb point | yes | throttle 5 to 95 %, ruddervators inside 10 deg |
| Both builds fly 120 s from each trim under a plain attitude hold | height within 4 ft, speed within 0.1 kt | 100 ft, 3 kt |

These check the generator against what it was generated from, and that the result flies. They say nothing new
about the real aircraft.

| Trim | Angle of attack | Ruddervators | Thrust, of maximum | Fuel flow | Lift coefficient | L/D |
|---|---|---|---|---|---|---|
| Cruise, Mach 0.6, 60,000 ft, 15,000 lb: strips | 2.83 deg | -6.0 deg | 455 lbf, 71 % | 290 lb/h | 0.724 | 32.7 |
| The same: reference build | 2.47 deg | -7.7 deg | 455 lbf, 70 % | 290 lb/h | 0.724 | 32.8 |
| Climb point, 150 KIAS, 10,000 ft, 26,750 lb: strips | 3.05 deg | -6.0 deg | 741 lbf, 12 % | 481 lb/h | 0.652 | 36.0 |
| The same: reference build | 2.70 deg | -7.2 deg | 749 lbf, 12 % | 484 lb/h | 0.652 | 35.6 |

Modes of the bare airframe with the controls fixed (strips build): at cruise a short period of 4.7 s with damping
0.30, a phugoid of 176 s with damping 0.04, a roll time constant of 0.4 s, a Dutch roll of 5.9 s with damping 0.06
and a spiral that doubles in 76 s. At the climb point the phugoid is neutral and the spiral doubles in 39 s. The
reference build has an unstable aperiodic longitudinal root at cruise (doubling in 11.5 s) where the strips have
the phugoid: its pitching-moment table bends the other way with speed there. The flight laws have to hold all of
these; none is checked against the real aircraft.

What already disagrees with flight data, before any calibration:

- **Low-altitude climb is too good.** At 150 KIAS and 10,000 ft at full weight the model's maximum thrust gives
  3,560 ft/min by the energy balance; Pastor measured 2,357 and 2,538 ft/min between 10,000 and 20,000 ft. Thrust
  less drag is about 45 % too large there. The drag would have to nearly triple to explain it, so most of it is
  the engine's low-altitude thrust: about 4,200 lbf is what the measured climb needs at 15,000 ft, against 5,200 in
  the model. The flat rating or the temperature limit binds harder than Phase 2 has it.
- **Six degrees of ruddervator in trim** is a lot, and it comes from the wing section's nose-down moment and the
  forward centre of gravity. The real tail will have an incidence that carries this; ours has none yet.

### Off the design conditions: days, wind and turbulence (2026-11-13; `fdm/phase11_checks.py`)

Limits were written first (docs/PLAN.md, Q2 and Q3); no source holds any of them, so they are design requirements. **Non-standard days:** the
property `atmosphere/delta-T` (the engine tables' temperature axis now runs -40 to +40 K; the old rows are unchanged). The laws hold height within 0.5 ft
and speed within 0.02 kt hands-off at three conditions on days of -20, +15 and +30 K; the maximum thrust at 20,000 ft falls 0.55 %/K cold to standard and
0.87 %/K from standard to +15 K; the 2013 landing is as on a standard day at -20 and +30 K. The climb at maximum thrust on the schedule is compared in
pressure altitude (a first version compared geometric height and took a 4,500 ft difference of the day's pressure altitude at 55,000 ft for a slow climb):
the rate goes with true airspeed at a given Mach (the schedule is in Mach above FL220), so a cold day climbs 3 % *slower* above FL220 (3,479 s from 10,000 to 55,000 ft against 3,369 s), the
limit that it should grow with temperature is wrong and stays a miss; the service ceiling (100 ft/min) falls to about 54,000 ft at +15 K and 50,000 ft at +30 K.
**Wind and turbulence:** JSBSim's wind is set back to zero by every initial-conditions call (`H.state`, `H.engage`, `H.on_ground`), so it is brought up over 30 s
in the run loops (`Gale`); trims are made in calm air and the turbulence started after the laws engage (trimming with turbulence on fails, and a first version
that did so showed hard landings that were that artefact). MIL-F-8785C turbulence in JSBSim gives nothing at altitude at severity 1 (0.00 m/s at 20,000 ft
and above), 2.0 m/s at 60,000 ft at severity 5 and 1.1 m/s at 20,000 ft at severity 3 (1.9 m/s at 3,000 ft): those were used. One deterministic realisation
(JSBSim's fixed seed), not statistics: a different draw can move a figure by tens of feet. Results: the cruise holds height within 75 and 69 ft and bank
within 0.9 and 1.8 deg with no structural flag, load factor 0.71-1.25 and 0.77-1.23 (pass); the airspeed varies by 11.7 kt (limit 5: a miss, since the gust
along the heading varies by 25 and 15 kt); the whole mission in a 25 kt headwind with light turbulence completes (40 min) with 94 % of the route inside 0.25
nmi (95 % was the limit: a miss; phase 7b's own 80 % passes); the 2013 landing in a 10 kt crosswind with light turbulence is down within 8 ft of the
centreline at 0.31 m/s (pass), at 20 kt within 7 ft at 0.50 m/s, in severe turbulence (severity 5) 50 ft off at 1.26 m/s. **The flare** now starts at the time
to touchdown when the sink is higher than a downdraft's (`laws.FLARE_TTG` 2.6 s, `FLARE_SLACK` 4 ft/s): with the fixed 45 ft flare the severity-5 landing came
down at 3.33 m/s, 460 ft short of the aiming point and 167 ft off the centreline; with it 1.26 m/s. Without the slack the change floated 300-600 ft further in
light turbulence, so the slack was added; calm landings are unchanged.

### The short period from ATTREX at 20 Hz (2026-11-13; `fdm/attrex_shortperiod.py`, `data/attrex_shortperiod.json`)

The 20 Hz records have pitch (0.01 deg), angle of attack, vertical acceleration, Mach number and the dynamic pressure (the column called Q is that, in hPa,
not a pitch rate). In 260 steady, level segments above 50,000 ft (16 flights) the spectra of pitch rate (the derivative of pitch), angle of attack, pitch and
vertical acceleration all have a peak 3 times over the band's median (the limit: half of at least 20 segments): all 260 do. The pitch-rate peak: median
0.293 Hz, middle half 0.244-0.352 Hz, damping about 0.15 (from the half-power width). **By campaign: 2013 flights 0.24-0.26 Hz, 2014-2015 flights 0.33-0.40 Hz**
(not explained: a flight control or configuration change is the candidate); by height 0.42 Hz at 50-53,000 ft to 0.24 Hz above 60,000 ft. The model:
the bare airframe 0.234-0.279 Hz (damping 0.27-0.28); the laws' closed loop in MIL turbulence 0.303-0.322 Hz. Fixed reading: within 30 % of the closed loop
(0.293 against 0.30-0.32) leaves the 22 % centre of gravity and the margin standing. The frequency goes with dynamic pressure to the power 1.05 (correlation
0.61), the model's bare airframe to 0.43 and its closed loop to about 0: the data are neither, so they cannot say whether the real flight control or the bare
airframe sets it. They do say the real pitch stiffness is at least the model's.

### Frame rate (2026-11-13)

120 Hz, which is FlightGear's. `GH_HZ=240` (480, 960) in the environment runs every check script at that rate (`harness.HZ`);
`fdm/rate_study.py` flies phase 7b's take-off, three landings and rollouts at 120, 240, 480 and 960 Hz: every check passes at all
four, lift-off differs by 1 kt and 0.5 deg between 120 and 960 Hz, touchdown by under 0.01 m/s, 0.01 deg and 0.1 kt, the rollout's
deceleration by none. A frame of the model costs 16 microseconds (the model alone, not the properties FlightGear copies in and out
each frame), so reduced-rate channels would save nothing worth the complication; the model stays at 120 Hz.

## Calibration against flight data

Limits were written before any of this was run. Three things were allowed to be fitted, each to its own data.

**The data.** Pastor and others (2018) measured climb rates and cruise-climb heights on two 2010 flights of N872NA;
NASA gives an endurance of "31+ hours" from 14,500 lb of fuel; the ATTREX flights give angle of attack, Mach
number and pressure on 18 long flights. None of them gives a weight, so the takeoff weight is **assumed**: NASA's
2008 figure of 25,600 lb for Pastor's flights, full tanks (26,750 lb) for ATTREX. Standard atmosphere throughout,
though the real days weren't.

**The mission, `fdm/mission.py`.** The JSBSim model is trimmed at maximum thrust at each height and weight on
Pastor's speed schedule (150 KIAS to FL220, then Mach rising with height to 0.6 at FL550); the flight-path angle
gives the climb rate and the fuel flow takes the weight down. Near its ceiling the model stops climbing and then
rises only as it burns fuel: the cruise-climb.

### What came out without fitting: the thrust rating

NASA calls the engine "flat rated at 7,500 lb thrust at sea level". Phase 2 read that as a cap of 7,500 lbf, and
the model then climbed at 3,560 ft/min at 10,000 ft where Pastor measured about 2,450. The thrust the measured
climb needs at 15,000 ft, with the model's drag, is about 4,200 lbf. **The turbine temperature at which the engine
model gives 4,200 lbf there is 1,254 K, and 1,254 K is exactly the temperature at which it gives 7,500 lbf at rest
at sea level.** So the rating is read as one limit on turbine temperature, the one that gives NASA's figure at sea
level, held at every height. Nothing was fitted for it. With it the climb rates from 10,000 to 40,000 ft come out
within 3 % of Pastor's. Above about 27,000 ft the fan-speed limit is the lower one.

### The CFD's wave drag, the 50 deg V-tail and the withdrawn stall fit (2026-11-13)

Limits and every result are in `docs/PLAN.md` ("Wave drag from the CFD", "Stall at Mach 0.6 fitted to the tunnel", "V-tail dihedral"); the summary:

- **Wave drag.** `fdm/cfd/wave_drag.py` takes the SU2 runs at Re 1.5 million (95 cases, Mach 0.45 to 0.7, -3 to 10 deg) and writes
  `data/cfd_wave_drag.json`, which `strips.section_tables()` adds to the wing's drag at Mach above 0.45: the solver's rise of drag with Mach at equal lift, less the table's own rise
  (a difference within the solver: its absolute drag is about twice the tunnel's). Named, CFD-derived, no flight data in it. At lift 0.4 / 0.6 / 0.8 / 0.95 it is +10 / +12 / +13 / +22 counts at
  Mach 0.6 and +21 / +43 / +73 / +170 at 0.65. **Deviation from the first rule, recorded:** cases are used by lift spread under 0.01 alone (the density-residual rule dropped well-converged cases and kept worse
  ones) and a lift counts as supported only between used cases at most 0.30 apart; `wave_drag.py --rule A` reproduces the first. Deleting the file removes the change. Best lift-to-drag in the tables:
  Mach 0.6 37.2 to 34.1, Mach 0.65 31.1 to 24.3.
- **The drag increment** was fitted again, **0.00308** (0.00355 when the CFD's wave drag went in, before the tail's and the gear's lateral positions were measured; 0.00564 and 0.00586 before that), fan-speed factor 1.01: below the 0.0040 to 0.0075 band written beforehand (the wave drag took about 0.0023 of the old value).
  After it **10 of 11 mission checks pass; the time from 10,000 to 55,000 ft is 9.0 % short (limit 5)**, the 40,000 to 55,000 ft climb rates +11.1 and +15.6 %, the cruise-climb heights -453, -570, -881 and +386 ft
  (limit 1,000), endurance 34.9 h (35.1 with no ceiling), cruise lift-to-drag 29.9. The fit of the lateral-dimension change is the one that rule allowed; no further fit.
- **V-tail dihedral 50 deg** (published, and 50.8 +- 0.5 in two head-on photographs), from the 3-D model's raw 47.1: panel 11.70 ft, 42.8 ft2 each, horizontal tail volume 0.277 to 0.236. Static margin
  at the 22 % centre of gravity (strip model, +-0.5 deg): 9.8 to 8.5 % at 60,000 ft, 5.6 to 4.6 % at 50,000 ft (20,000 lb) and 5.3 to 4.3 % at 55,000 ft (17,000 lb) (the 50 deg alone took about 1.9; the measured lateral position gave 0.6 to 0.8 back); the bare short period 0.279 / 0.266 / 0.234
  to 0.230 / 0.220 / 0.185 Hz; the closed loop 0.303 / 0.322 / 0.322 Hz against the flights' 0.293 (+3, +10 and +10 %: within 30 %), so the centre of gravity stays. The published span (11.4 ft) is 2.6 % under the model's 11.70
  (cause not established, left as drawn); the head-on RQ-4A photograph's tail width against its gear track (1.82) disagreed with the model's (1.29): **resolved**, the track is 10.8 ft and the tail tips 10.2 ft from the centreline (rows above; PLAN, "Lateral dimensions").
- **What moved in the checks, found by taking each change out in turn** (one at a time against the full state): A1 at Mach 0.59 to 0.62 (+15.6 %, limit 10) is the wave drag (three of six weights no longer
  trim at full throttle at 57,293 ft); 7d H3 (cruise, full forward stick: Mach 0.653, limit under 0.65) was the tail angle (+0.003) and the wave drag (+0.001) together, and passes (0.643) with the tail tips at their measured 10.2 ft; the climb-time misses (mission P1, 7a A10) are the
  one-number calibration's compromise.
- **The stall fit is withdrawn.** `fdm/cfd/stall_fit.py` (the tunnel's maximum lift with the CFD's shape) met S3, but its blend back to the table's own deep stall after the CFD's last angle (10 to 12 deg) falls 0.26 to
  0.37 per deg against the CFD's steepest 0.13, which its limit (d) forbids; the tables stay as they were and S3 at Mach 0.6, Re 2 million stays a miss (-15.8 %). Its result is in `fdm/cfd/withdrawn/`.
- **Not refreshed:** the Phase 3 table "The two models against each other" below (neutral points 29.8 and 32.5 %) does not match `aero_compare.json` even before this change; kept as the Phase 3 record.

### What was fitted

| Fit | Value | Fitted to |
|---|---|---|
| A constant added to the drag coefficient | 0.00308 (0.00355 before the lateral dimensions were measured; 0.00564 before the moment fit, 0.00586 after it, before the CFD's wave drag) | Pastor's climb rates from 40,000 to 55,000 ft and his four cruise-climb heights, together with the next |
| A factor on the engine's fan-speed limit | 1.01 | the same. The limit came from the Citation X's engine in Phase 2 |
| The wing's incidence | 2.0 deg | the ATTREX lift curve: the model's trimmed lift at a given angle of attack |
| A fuel-flow factor | not used | allowed if endurance missed; the endurance, 34.9 h, is inside its window (29 to 35 h), and it is left alone |

- **Why two numbers.** More drag slows the climb above 40,000 ft, as measured, but also lowers the cruise-climb,
  which already matched. The best pair sits in a shallow valley: fan-speed factors from 1.00 to 1.02 with drag
  increments from 0.0046 to 0.0068 fit almost equally well. Thrust and drag can't be told apart with this data.
- **The drag increment adds 11 % to the model's own drag at cruise** (it was 26 % before the CFD's wave drag went in). It stands for everything the strip model doesn't
  have: the section's own drag shortfall against the tunnel (about 6 %), antennas, radomes, leaks, the nacelle's
  inlet, the tail's induced drag, the flexible wing's shape. Lift-to-drag falls from 33.7 to 30.4 at a lift coefficient of 0.96 (Mach 0.6; the mission's cruise-climb, with trim drag, 29.9).
- **The tail's incidence, -3.0 deg, is a choice,** not a fit: it leaves the ruddervators within a degree of
  neutral in cruise and climb. Two side photographs of RQ-4s just off the runway (the tail panels' tip edges for
  the chord; the drawn profile's belly or the wheel-axle line for the body axis) read -3.8 +-2 deg (an RQ-4D) and
  -2.7 +-1.5 deg (a USAF RQ-4, long lens): consistency checks, not constraints, and not independent (the incidence
  and the centre of gravity trade off 3 deg for 0.11 in Cm).
- `fdm/data/calibration.json` holds the numbers; the generator and the engine tables read it.

### Checks

| Check | Model | Measured | Error | Limit | |
|---|---|---|---|---|---|
| Climb rate 10,000 to 20,000 ft | 2,342 ft/min | 2,447 [Pastor] | -4.3 % | 15 % | pass, predicted by the temperature limit |
| 20,000 to 30,000 ft | 1,916 | 2,037 | -5.9 % | 15 % | pass, predicted |
| 30,000 to 40,000 ft | 1,196 | 1,336 | -10.5 % | 15 % | pass, predicted |
| 40,000 to 50,000 ft | 524 | 525 | -0.2 % | 15 % | pass, fitted |
| 50,000 to 55,000 ft | 134 | 122 | +10.1 % | 30 % | pass, fitted |
| Time from 10,000 to 55,000 ft | 4,452 s | 4,596 | -3.1 % | 5 % | pass |
| The same, flown in time by the flight laws | 4,354 s | 4,596 | -5.3 % | 5 % | just outside |
| Height 237 min after takeoff | 57,199 ft | 57,473 | -274 ft | 1,000 ft | pass, fitted in level |
| 404 min | 58,439 | 58,836 | -397 ft | 1,000 ft | pass |
| 737 min | 60,911 | 61,638 | -728 ft | 1,000 ft | pass |
| 1,237 min | 64,618 | 64,109 | +508 ft | 1,000 ft | pass |
| Endurance, 14,500 lb of fuel to 5 % left | 35.4 h | "31+ h" [NASA] | | 29 to 35 h | **miss**, by 0.4 h |
| ATTREX: trimmed lift-curve slope, Mach 0.59 to 0.62 | 0.121 per deg | 0.116 | +4.0 % | 10 % | pass, predicted |
| ATTREX: the same, Mach 0.50 to 0.54 | 0.131 | 0.130 | +1.1 % | 10 % | pass, predicted |
| ATTREX: bank in 409 long turns against speed times turn rate | | 15.1 deg mean | -0.06 deg, scatter 1.2 | 1 deg | pass |

- **A correction made later.** The first fit left out the energy that goes into true airspeed rising with height
  on the schedule (the climb rate is the unaccelerated trim's divided by 1 + (V / g) dV/dh, 7 to 10 % here). It
  showed when the flight laws flew the climb in time and took 6.6 % longer than the quasi-steady mission. With the
  term in and the fit redone, the time to 55,000 ft is inside its limit; the climb rates from 10,000 to 40,000 ft,
  which had looked 1 % off, are 4 to 10 % low. The numbers in this section are from the corrected fit.
- **Endurance:** 35.4 h to 5 % of the fuel. NASA's figure is a lower bound with unknown reserves. A fan-speed
  factor of 1.04 with a drag increment of 0.0094 would give 31.4 h, at twice the misfit to the climb and
  cruise-climb. The fuel flow may also simply be low: Phase 2 put plus or minus 6 % on it.
- **Cruise-climb:** the model follows Pastor's heights within 830 ft for 20 hours, at a lift coefficient of 0.96 to
  0.97 and a lift-to-drag ratio of 30. It goes on climbing past 65,000 ft as it empties, to 71,000 ft; NASA quotes
  65,000 ft as the maximum, which the flight laws will have to hold as a limit.
- **ATTREX lift curve** (`fdm/attrex_lift.py`). The data's angle of attack is pitch attitude less flight-path
  angle (they agree within 0.2 deg all flight), so it is a true angle of attack in the inertial unit's axes. The
  weight comes from the takeoff weight less our engine model's fuel flow along each flight. Because the takeoff
  weights differ and aren't known, the slope is fitted within flights, each with its own level; only three
  flights at Mach 0.6 and one at Mach 0.52 span a degree of angle of attack in their steady segments (52 and 7
  segments). The flights' levels differ by 0.09 in lift coefficient, which is 0.7 deg of incidence or 10 % of weight.
- **The trimmed slope in flight (0.116) is 17 % below the rigid, untrimmed slope the Air Force measured (0.140)**
  on the Block 20. The model's trimmed slope is 0.121: trim accounts for most of the difference, and the wing's
  flexibility, which the model lacks, may be the rest.

### What the calibration leaves open

- The reference build (AeroSandbox's tables) **no longer trims at the cruise point** after the incidences were
  set: it needs 14 deg of ruddervator and all the thrust, and its short period is unstable there. Its pitching
  moment at Mach 0.6 breaks earlier than the strips'. It is not what ships; it is recorded as a miss of two of the
  earlier checks, not repaired.
- The shipped model has an **unstable aperiodic speed mode at cruise** (doubling in 10 s with controls fixed) where
  it had a phugoid before the incidences: pitching moment and lift change with Mach number near 0.6. The flight
  laws will hold speed with the elevator, as the real aircraft does, but it is a property to look at again.
- Off-standard temperatures, the two ATTREX landings, sideslip in turns, and the Air Force paper's figures 5 to 13.

## Flight laws, part A

The real flight control laws are not public. These are ours (`fdm/laws.py`, generated into
`GlobalHawk/Systems/laws.xml`), built to behave as the public sources say the aircraft does: in climb the throttle
is at maximum and the elevator holds a scheduled airspeed; ruddervators together are the elevator and against each
other the rudder [Eaton and Woolf]; turns are flown at 15 deg of bank at height and about 21 deg low down [Pastor,
ATTREX]. `ap/engaged` = 0 leaves the surfaces on the direct commands.

- **Basic laws:** pitch attitude (proportional, integral, pitch-rate damping), bank (proportional with roll-rate
  damping), yaw (a washed-out yaw-rate damper and sideslip held to zero). Gains follow dynamic pressure.
- **Modes:** speed by elevator, on the schedule or a commanded speed; altitude hold with speed by thrust; heading
  or bank; thrust as commanded, maximum, idle or holding speed.
- **Protections:** the pitch command is a state that moves towards what the mode asks at 2 deg/s at most, and is
  pulled down while the angle of attack is over its limit (the lift break less a margin, by Mach number) or the
  speed is 15 kt under its command. The bank command stops 2 deg inside a bank limit of 25 deg below 30,000 ft and
  15 deg above 50,000 ft.
- **Actuators:** a lag of 0.05 s and 40 deg/s on ruddervators and ailerons: estimates.
- Engaging at a trim is bumpless: the surface angles, attitude and throttle of that moment are latched.

`fdm/phase7a_checks.py`: 44 checks at cruise, at the climb point and in the approach configuration, with the wing
bending's effect on and off; limits written first; all pass.

| | Result |
|---|---|
| Altitude hold, 300 s | within 0.5 ft and 0.01 kt at cruise and climb; 22 ft and 0.4 kt in the approach configuration |
| Pitch step of 2 deg | overshoot 8-9 %, settled in 1.8 s |
| Bank step to half the limit | overshoot 0-9 %, settled in 4-7 s, sideslip up to 0.5 deg at cruise, 1.3 deg on the approach |
| Heading change of 90 deg | final error under 0.2 deg; bank 13.1 deg at cruise, 23.9 at the climb point |
| Sideslip kick of 2 deg | under 0.2 deg after three periods of the bare airframe's Dutch roll, everywhere |
| Speed by elevator at maximum thrust | within 0.8 kt; the bare airframe's unstable speed mode at cruise is held |
| Every gain doubled, and halved | stable |
| Pitch command of 15 deg at cruise | angle of attack held to 3.8 deg (limit 3.5); speed dipped 8 kt under its floor |
| Climb from 10,000 to 55,000 ft, hands off | 4,354 s, speed within 0.5 kt of the schedule; Pastor measured 4,596 s |

Known shortcomings: the yaw law reads true sideslip, which the real aircraft cannot measure (it uses lateral load
factor); phase margin is not measured; no load-factor loop; no sensor or navigator models; energy control above
45,000 ft is not built (the aircraft cruise-climbs at maximum thrust there, as the real one mostly does).

## Flight laws, part B: a whole mission hands off

Everything that has to act at the model's rate is a law in `laws.xml`: following a leg in the air and on the
ground, taxi speed, the takeoff rotation, the glide path, the flare, the rollout and the brakes. A mission manager
hands the laws their next leg, target and mode ten times a second and does nothing else; for these checks it is
`fdm/missionmgr.py`, in Python, standing in for the one that will run in FlightGear.

- **Approach and landing, after the measured ones and after gliders:** the elevator holds the speed for a lift
  coefficient of 0.645 at the present weight, thrust is idle, and **the spoilers hold the glide path** (4.45 deg)
  from a mid setting, so they have room both ways. In the flare the pitch attitude goes to 2.4 deg and the spoilers
  go on working, on sink rate alone: they come in as far as the sink needs. On the runway: full spoilers, nose
  down, and brakes held to 0.235 g.
- **Takeoff:** maximum thrust, nose-wheel steering on the runway's line, pitch to 7 deg from 130 KIAS.
- **Taxi:** the nose wheel follows the leg, the throttle and brakes hold a commanded ground speed, slower for corners.

`fdm/phase7b_checks.py`, 18 checks, limits written first, all pass:

| | Model | Measured |
|---|---|---|
| Approach speed the law picks at 20,800 and 17,100 lb | 132.8, 120.4 KEAS | 133, 120 |
| Glide path on the approach | within 0.9 and 2.0 ft; spoilers 0.68-0.69 and 0.74-0.76 | |
| Touchdown sink | 1.08, 1.12 m/s | 0.66, 0.75 |
| Touchdown pitch attitude | 2.11, 2.13 deg | 2.4, 2.3 |
| Touchdown speed | 128.6, 117.1 KEAS | 130, 122 |
| Spoilers at touchdown | 0.38, 0.42 of full | not known |
| Rollout deceleration | 0.224, 0.221 g | 0.235, 0.26 |

One mission flown from a stand to a stand with nobody touching it, at 25,600 lb from a field at 2,300 ft: taxi 800 ft
with a 90 deg turn, takeoff, climb to 20,000 ft, three legs of 25 nmi with turns of 90 and 120 deg, descent,
level flight in the landing configuration until the glide path comes down to the aircraft, landing, rollout, taxi
off with a 90 deg turn, stop. 39 minutes, 555 lb of fuel.

| | Result |
|---|---|
| Taxi | within 8.6 ft of the path, 1 kt of the commanded speed |
| Takeoff | 130 KIAS in 32.4 s (Pastor: 37.5); liftoff at 144 KEAS and 5.8 deg of pitch; 2.8 ft off the centreline |
| Enroute | height captured within 147 ft, held within 17 ft; cross-track under 0.25 nmi for 95 % of the route; bank up to 22 deg |
| Landing | glide path within 0.7 ft; touchdown at 1.06 m/s and 1.9 deg with the spoilers at 0.36; rollout 0.226 g |
| End | stopped 11 ft from the last point |

Shortcomings: the touchdowns are firmer than the measured ones (1.1 against 0.7 m/s) and 1,100 to 1,400 ft past the
aiming point; liftoff comes at 144 KEAS where the recorded ones were at 121 to 139 (the nose is 3 s late); no wind,
no crosswind, no turbulence has been flown; stops at hold points, traffic, and the choice of taxi route are the
manager's and not built; the manager here is a stand-in.

## Flight laws, part C: navigators, lost link, landing without the engine

All of this is our own design and every result is predicted: nothing public says how the real aircraft does it,
only that it has two pairs of navigators, flies a contingency route when the link is lost, and that one was lost
in 2017 when it flew on one bad navigator of two.

- **Navigators:** four (two Kearfott, two Litton), each the true attitude plus an error a test can set. With three
  or four on the laws take the middle value; with two, their mean while they agree within 3 deg, and otherwise the
  one nearer a reference no navigator supplies: the bank that the turn rate implies, the pitch that angle of attack
  and flight-path angle imply. A disagreement raises `nav/miscompare`.
- **Lost link:** 30 s without an uplink and the aircraft leaves its plan for the contingency route the plan carries.
- **Engine failure** (the tasks borrowed from the MV-22B's engine-out laws): glide at a lift coefficient of 0.8 to
  the runway with the most height to spare by the planner's book (glide ratio 20, 300 ft per 90 deg of turn,
  1,000 ft in hand); circle over a point 5.3 nmi out on the centreline, spoilers burning the surplus; then the
  normal approach, met from above, with the spoilers holding the glide path as always.

`fdm/phase7c_checks.py`, 11 checks, limits written first, all pass:

| | Result |
|---|---|
| The 2017 case: two navigators, one drifts 30 deg in roll | the voted roll is out by 1.5 deg at most, for 0.3 s; bank stays within 0.93 deg (which is settling, there without the failure); flagged at once; height within 0.1 ft (the real aircraft reached 152 deg) |
| One of four jumps 60 deg | the vote doesn't move |
| Both of two wrong the same way | not caught: flies banked 25.9 deg. No vote survives a common error |
| Link cut on a leg at 20,000 ft | leaves the plan 30.1 s later, lands 24 min after: 1.08 m/s, 5.9 ft off the centreline |
| Engine stopped at 20,000 ft, 30 nmi out, flying away | on the runway 1,615 ft past the aiming point, 0.89 m/s, stopped 21 min later |
| Engine stopped at 50,000 ft, 100 nmi out | the same touchdown, 47 min later |
| Height in hand at the entry point: planner against flown | 4,658 against 8,878 ft; 13,174 against 21,368 ft |
| No runway in reach | alert raised; a landing off a runway is not built |

The model glides at 31-33 to 1 at that speed; the planner counts on 20 until wind is modelled. Not modelled: the
windmilling engine's drag, and emergency electrical and hydraulic power.

## Manual mode: flying it by hand

The real aircraft has no stick. This is a simulator choice, so that it can be hand-flown in FlightGear and, from
the ground station with the link's delay, so one can see why nobody does. `ap/manual`: 0 automatic, 1 protected, 2 direct.

- **Protected:** the stick fore and aft asks for a pitch-attitude rate (3 deg/s, less at speed: never more than
  half a g) and holds the attitude when released; sideways it asks for a bank angle, wings level when released;
  pedals ask for sideslip. It goes through the automatic laws' own limits, which here look ahead: the angle of
  attack 2 s on, the speed 8 s on.
- **Direct:** the surfaces follow the stick, with rate damping only. No limits.
- **Structural flags** `limits/overstress` and `limits/failed`: load factor past +2.5 or -1.0 (ultimate 1.5 times),
  200 KEAS, Mach 0.70. **These numbers are assumed**: none is published.

`fdm/phase7d_checks.py`, 26 checks, limits written first, all pass; all predicted:

| | Result |
|---|---|
| Automatic to protected, and protected to direct and back | surfaces move under 0.002 deg |
| Protected, full back stick for 30 s | angle of attack 0.17-0.25 deg over its limit at most; load factor under 1.5 |
| Protected, full forward stick for 30 s | Mach 0.649 at cruise, 179 KCAS low down; load factor above 0 |
| Protected, full side stick | bank 13.0 deg at cruise (limit 15), 22 deg lower (limit 25); level 15 s after release |
| A simple pilot climbs 500 ft and turns 30 deg, stick delayed 0, 0.3, 1.5 s | within 6 ft and 0.4 deg with 0 and 0.3 s; with 1.5 s it arrives but the height hunts 84 ft |
| Takeoff and landing by that pilot | liftoff at 143 KEAS; touchdown at 1.41 m/s, 8 ft off the centreline |
| Direct: Dutch roll damping ratio | 0.29-0.35 (bare airframe 0.03-0.07) |
| Direct at cruise, a nudge and hands off | 10 kt off speed after 81 s |
| Direct, a dive and full back stick | 3.28 g; flagged 0.008 s after passing 2.5 |

## Gear, ground, takeoff and landing

`fdm/phase5_checks.py` (12 checks, all pass). The pilot in these runs is plain Python at the model's rate
(`fdm/harness.py`: `takeoff`, `landing`), standing in for the flight laws, which don't exist yet.

**What the flight data shows** (ATTREX, 20 Hz; read before the limits were written):

| | 2013-12-20, Edwards | 2014-03-06, Guam |
|---|---|---|
| Approach speed | 133 KEAS | 120 KEAS |
| Sink rate, glide angle | 1,079 ft/min, 4.46 deg | 844 ft/min, 4.44 deg |
| Angle of attack, pitch attitude | 4.66 deg, 0.05 deg | 4.29 deg, -0.17 deg |
| Touchdown | 130 KEAS, pitch 2.4 deg, sink 0.66 m/s | 122 KEAS, pitch 2.3 deg, 0.75 m/s |
| Rollout | a steady 0.235 g from 120 to 50 kt; 3,485 ft to 43 kt | 12 s at 0.055 g, then 0.26 g |
| Landing weight, from our fuel model | 20,800 lb (a 6 h flight) | 17,100 lb (a 17 h flight) |

- **The approach is flown at one lift coefficient, 0.645:** the two approach speeds are in the ratio of the square
  roots of the two landing weights within half a percent. (A single assumed landing weight, tried first, could
  not explain them.) That also supports the fuel model's weights.
- **It is flown on spoilers.** Clean, the wing would give a lift coefficient near 1.0 at 4.5 deg; the aircraft has
  0.645. A glide of 4.45 deg needs a lift-to-drag ratio of 13 where the clean aircraft has 28.
- **The brakes hold a deceleration,** 0.235 to 0.26 g, steady from 120 to 50 kt while the air drag falls away.
- The 19 records that start just after liftoff: 121 to 139 KEAS at 4.5 to 7 deg of pitch and 3.3 to 5.8 deg angle of
  attack; half a minute later 147 to 151 KEAS, 10 to 14 deg of pitch, climbing 2,250 to 3,650 ft/min.
- Pastor: 130 KIAS reached 37 and 38 s after the start of the roll; 2,500 to 5,000 ft in 59 to 63 s.

**What was added to the model**

| | | |
|---|---|---|
| Ground effect | lift, drag and moment against height and angle of attack | from the strip model's own vortices mirrored in the ground: at the wheels' height it adds 0.05 of lift coefficient and takes away 60 % of the induced drag |
| Gear drag | 0.0133 (0.0065 before 2026-11-13) | **an estimate, from the parts:** 7.2 ft² of drag area (band 4.1 to 11): the four 22 x 5.75 main tyres 1.8, the 18 x 6.5 nose tyre 0.4, two exposed main struts 2.0, side braces and links 1.0, the nose fork and strut 0.5, three open bays 1.2, hubs, brakes and lights 0.3 (handbook coefficients for wheels, cylinders and cavities, none from a source for this aircraft). The old 3.5 ft² lay below the whole band. The approach fixes only the total with the spoilers; docs/PLAN.md, "Main gear in the 3-D model, and the gear drag again" |
| Gear-door drag | 0.0015 | **an estimate, sized from photographs (2026-11-13):** the main legs' flat door plates (about 6 ft² a side, 2.6 to 3.6 ft below the wing root) and the nose door panel (about 7 ft², 1.55 ft tall) lie within about 5 deg of the airflow (thin rods in the head-on view), so their drag is friction (0.14 ft²), edges (0.31), toe (0.22) and interference (0.15): 0.81 ft², band 0.4 to 1.7 ft² (0.0007 to 0.0031). Scaled by the gear position; docs/PLAN.md, "Gear-door drag". The records cannot test it: the 2013 approach fixes only the total, so the spoilers' fit takes up the rest |
| Spoilers | lift -0.354 and drag +0.0203 at the approach setting (+0.0263 before the 2026-11-13 changes; +0.0271 with the door term, before the gear drag was set from its parts) | **a fit** to the 2013 approach (speed, glide and angle of attack at idle thrust), redone with the door term in: without it the same model needs +0.0286, so the door term takes 0.0015 of the spoilers' drag; the rest of the change from 0.0263 is the lower drag increment (0.00586 to 0.00308), which the approach shares. The setting is taken as 30 of 45 deg: an assumption, as is the straight line to 45 deg |
| Brakes, steering, retraction | JSBSim's wheel brakes; 60 deg of nose-wheel steering; 8 s gear travel | estimates |
| Structure | contact points at the wing tips, nose, tail and belly | so a bad landing shows |

**Checks**

| Check | Model | Measured | Limit | |
|---|---|---|---|---|
| Stands 60 s at 26,750 and 11,450 lb | doesn't move | | 0.5 ft | pass |
| Taxi to 15 kt, turn 90 deg on the nose wheel, stop | bank up to 1.5 deg | | 3 deg | pass |
| Brake release to 130 KIAS | 32.8 s | 37 and 38 s [Pastor] | 15 % | pass, predicted (-12.5 %) |
| Liftoff | 133 KEAS, pitch 5.9 deg, angle of attack 4.4 deg | 121-139 KEAS, 4.5-7 deg, 3.3-5.8 deg [ATTREX] | inside | pass, predicted |
| Climb half a minute after liftoff | 2,765 ft/min at 152 KEAS, pitch 10.6 deg | 2,250-3,650 ft/min, 10-14 deg [ATTREX] | inside | pass, predicted |
| 2,500 to 5,000 ft | 54.4 s | 59 to 63 s [Pastor] | 15 % | pass, predicted (-10.9 %) |
| 2014 approach with the spoilers fitted on 2013: angle of attack | 4.79 deg | 4.29 deg | 1 deg | pass, predicted |
| The same: thrust | idle, 0.008 g left over | | idle to 30 % | pass, predicted |
| Touchdown | 131 KEAS, sink 0.63 m/s | 130 KEAS, 0.66 m/s | sink under 1.5 m/s | pass |
| Rollout from touchdown to 43 kt at 0.235 g | 3,496 ft (3,557 in an earlier state of the model) | 3,485 ft | 15 % | pass |
| Rest to rest without NaN | yes | | | pass |

- **The takeoff is 12 % quick and the first climb 11 % quick,** both inside their limits and both the same way:
  the model has a little too much thrust less drag at low speed and low height, at Pastor's assumed weight.
- **The flare is not right yet.** With the spoilers held open the model can't arrest its sink at the measured
  touchdown attitude, so the stand-in pilot closes them through the flare. It then touches down at the measured
  speed and sink but at 0.4 deg of pitch where the aircraft had 2.4 deg. The real flare lies between: a guess until
  the flight laws design the landing.
- The thrust on the approach is idle with a little to spare (the model wants 130 lbf less than idle on the 2014
  approach): the spoilers' drag carries whatever the real idle thrust is, which isn't known.

## Wing bending: an estimate

**No stiffness, deflection or bending frequency of the Global Hawk's wing is public. Everything in this section is
derived from assumptions and checked only against itself.** `fdm/flex.py` is the beam model; `flex/enable` = 0 in
the JSBSim model takes its aerodynamic effect away and leaves the rigid aircraft.

**The assumptions.** The half wing is a cantilever from the fuselage side, sized by strength: at 1 g and maximum
weight its spar caps are at a strain of 0.0012 (0.0030 at a limit load factor of 2.5), over a box 85 % of the
section's thickness deep, the strain falling linearly to 40 % of that at the tip. These are typical of composite
wings. The load is the strip model's lift along the span less the load factor times the weight of the wing's
structure (2,184 lb, an estimate) and of the fuel in its tanks.

| | Tip deflection | |
|---|---|---|
| Standing, full tanks | 1.6 ft down | |
| Standing, no fuel | 0.5 ft down | |
| 1 g at 26,750 lb, full wing tanks | 4.3 ft up | 7.4 % of the semi-span |
| 1 g at 19,100 lb | 3.2 ft up | |
| 1 g at 15,000 lb, cruise | 2.6 ft up | |
| 1 g at 12,980 lb | 2.3 ft up | |
| First bending frequency | 1.04 Hz with full wing tanks, 1.88 Hz empty | Rayleigh's quotient on the lift shape |

**What it does in the model.** One bending mode, a second-order system at that frequency (it follows the wing
fuel) with 15 % damping (an estimate), driven by the lift and the normal load factor; `flex/tip-deflection-ft` is
its output, for the animation. The bent wing has dihedral, so sideslip rolls the aircraft: the strip model with
the bent shape gives -0.00041 of rolling-moment coefficient per degree of sideslip for each foot of tip
deflection, at every Mach number tried.

| Bare airframe, controls fixed | Roll due to sideslip, per deg | Dutch roll | Spiral |
|---|---|---|---|
| Cruise, rigid | -0.0001 | 8.2 s, damping 0.068 | doubles in 70 s |
| Cruise, bent 2.6 ft | -0.0011 | 7.3 s, damping 0.030 | doubles in 124 s |
| Climb at 10,000 ft, rigid | -0.0002 | 6.2 s, damping 0.126 | doubles in 32 s |
| Climb, bent 4.3 ft | -0.0020 | 5.4 s, damping 0.073 | doubles in 65 s |

The bending does what dihedral does: the spiral slows by half and the Dutch roll loses half its damping. Both
matter to the lateral flight laws. `fdm/phase6_checks.py`: JSBSim's tip deflection equals the beam model's at two
trims and standing, and the mode settles on its static value in flight (4 checks, consistency only).

Not in it: the twist that bending gives a swept wing (it would unload the tips), any change of lift or drag with
the shape, torsion, higher modes, and the fuselage's give at the root. A photograph with a known scale, or one
frequency from a ground vibration test, would replace the assumptions; neither is public.

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

**Changed by the calibration against flight data** (see "Calibration"): the flat rating is no longer a cap of
7,500 lbf but the turbine temperature that gives 7,500 lbf at rest at sea level, 1,254 K, held at every height;
and the fan-speed limit is 1 % higher. The list and the thrust table below are Phase 2's, before that; the current
numbers are in `engine.json`.

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

### The engine's spool (2026-11-13; `genghawk.spool_fragment`, check B3s)

Thrust used to follow one first-order lag of 2.0 s ("a class estimate, no data"). **Evidence:** the Citation X take-off at Portland (`citationx_takeoff_pdx`, outside, audio
only, from the sound work's git-ignored recordings): the fan's blade-passing tone and its second harmonic, tracked in 0.08 s windows, come up out of the noise at about
1,700 Hz at 18.0 s, ramp and settle at 2,885 Hz (21-22.8 s). Normalised to the plateau: 0.60 at 18.26 s, 0.80 at 18.92, 0.90 at 19.50, 0.95 at 19.76, 0.98 at
20.02 s. The aircraft is nearly standing (Doppler under 3 %). A first-order lag alone would take 0.34 s for 0.6 to 0.8; it took 0.66 s: the early rise is a rate
limit. **Fit** (least squares over 210 points of the track, rms 0.019 of the final speed): n' = min(0.23 per s, (1 - n) / 0.38 s) from n = 0.6. **Not measured:** the
rise from idle (the tone is under the noise below about 0.6), the throttle's motion (a snap is assumed), the fall in speed, and that it is a Citation X's AE 3007C1,
not the AE 3007H (same family and fan, a higher rating). The other recordings (the start, the cockpit, the FADEC check, the Global Hawk's own) have no usable ridge.
**The model:** the fan's speed share n of the maximum here is a state, an integral of that rate; thrust is the maximum times n squared (the law the sound's rpm
already had: 2,230 rpm at idle against 8,290 at take-off is 0.27, 7 % thrust); the command is sqrt(commanded thrust / maximum); below n = 0.6 the rate limit is half
the measured, 0.115 per s (an estimate, between the measured rate and the 0.063 that would just meet the 5 s of the certification rule for transport engines, 15 to
95 % of take-off thrust, which I recall and have not checked); down the measured rate (no data); a failed or stopped engine loses its speed at 1.5 per s. The fan's
rpm for the sound and the 3-D model is now the state itself. **Checks:** 0.60 to 0.90 of the final fan speed in 1.31 s against 1.24 and to 0.98 in 1.92 s against
1.76 (+5.5 and +8.9 %, limit 20 %, after the fit); thrust 15 to 95 % in 3.67 s (bound 5.0; the old lag 5.67 s, over it). What changed in flight: the plain take-off's 130
KIAS time from 32.8 to 34.2 s (-12.5 % to -8.8 % of Pastor's 37.5), the laws' take-off from 32.4 to 32.7 s, nothing else outside the checks' limits. Not a fit to
Pastor's times.

### Power taken off the engine (2026-11-13)

Not in the first model; the Air Force's paper names it a condition of the endurance. `Turbofan.run(..., hpx=)` in `fdm/engine.py` takes
power off the high-pressure spool: the compressor's work balance loses that much, so its pressure ratio and the core's flow fall at the
same turbine temperature; held to the same thrust, the engine burns more. `tables()` measures two sensitivities with 20 kW
(`HPX_PROBE_KW`) and writes them into `engine.json` (`hpx_thrust_per_kw[altitude][mach]`, `hpx_fuel_per_kw[altitude][mach][fraction]`,
linear); the flight model has `engine/extra-power-kw` (0 or more, default 0: **every earlier figure is unchanged**, which the logs show),
which scales the maximum thrust and the fuel flow. The part-power fuel law of the ICAO points has no extraction in it, so below 0.4 of
the maximum the sensitivity at 0.4 is used. At 60,000 ft: 20 kW costs +2.1 % fuel at the model's cruise trim (+2.5 % at 500 lbf) and
-0.5 % maximum thrust; at 10,000 ft +0.6 % fuel at a climb's thrust. The efficiency of the extra fuel is 0.47 (H3, limits 0.2 to 0.6).
The mission's endurance, in the model before the CFD's wave drag, falls from 34.7 h to 34.0 at 20 kW and 33.2 at 40 kW. **The size of the effect has nothing to be held to**: no
engine data is in the ATTREX records (their columns are pressure, temperature, speed, wind, position and attitude).

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
| Eaton and Woolf | C. M. Eaton, R. K. Woolf, *Flight Test Validation of the RQ-4 Block 20 Global Hawk Aerodynamic and Propulsive Models*, Society of Flight Test Engineers, 2009 (AFFTC-PA-09254) |
| ICAO | ICAO Aircraft Engine Emissions Databank, rows for the AE 3007 variants, through TU Delft's OpenAP (`engines.csv`) |
| Ghazi | G. Ghazi, doctoral thesis on a Cessna Citation X performance model, ETS Montréal (LARCASE): table 2.1, one AE 3007C1 at maximum climb, from a Level D simulator's model |
| Mattingly | J. D. Mattingly, *Elements of Propulsion: Gas Turbines and Rockets*, AIAA, chapter 8 |
| Designation-Systems | designation-systems.net, *Northrop Grumman RQ-4 Global Hawk* |
| UTHM thesis | a 2013 thesis on transient flight analysis, Universiti Tun Hussein Onn Malaysia; its table 2.4, *Global Hawk Geometry*, quotes Jane's 1999 |
