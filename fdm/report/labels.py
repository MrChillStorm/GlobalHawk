"""What each check is held to, by log and by the check's tag or words (the first pattern that matches, else the log's
default): F a flight record of this aircraft, P a published figure or test of the aircraft, its engine or its wing section, M another model or
another aircraft's data, D a design requirement of ours (the laws against their own limits, the software against its
specification), G generated (the model against the numbers it was generated from)."""

# (log, the report's name for it, [default, (pattern, group), ...])
LOGS = [
    ('engine', 'Engine', ['P', (r'^(V4|V5|V7|V6b) ', 'M')]),                 # ICAO and Rolls-Royce; the Citation X's engine from the ETS theses
    ('engine_pycycle', 'Engine against pyCycle', ['M']),
    ('phase1_checks', 'Geometry and mass', ['P', (r'by construction', 'G')]),
    ('phase3_checks', 'JSBSim model as generated', ['G', (r'^(B4|B5|B6) ', 'D')]),
    ('phase4_checks', 'Section data and lift curve', ['F', (r'^S[123] ', 'P')]),     # NASA's tunnel test of the section; the ATTREX flights
    ('mission', 'Climb, cruise-climb, endurance', ['F', (r'^P3 ', 'P')]),    # Pastor's figures from NASA's flights; NASA's endurance
    ('phase5_checks', 'Gear and ground', ['F', (r'^(G1|G2|L2|L4) ', 'D')]),
    ('phase6_checks', 'Wing bending', ['G']),
    ('phase7a_checks', 'Flight laws', ['D']),
    ('phase7b_checks', 'Landings and a whole mission', ['D', (r'^M[5-8] 201[34] landing', 'F')]),
    ('phase7c_checks', 'Navigators, lost link, engine out', ['D']),
    ('phase7d_checks', 'Flown by hand', ['D']),
    ('phase8a_checks', 'Station: link and commands', ['D']),
    ('phase8b_checks', 'Station: alerts', ['D']),
    ('phase8c_checks', 'Station: forecast', ['D']),
    ('phase8d_checks', 'Station: several stations', ['D']),
    ('phase8e_checks', 'Station: traffic and demo', ['D']),
    ('phase9a_checks', 'FlightGear: starts', ['D']),
    ('phase9b_checks', 'FlightGear: flown through the link', ['D']),
    ('phase9c_checks', 'FlightGear: head-up display', ['D']),
    ('phase9d_checks', 'FlightGear: belly camera', ['D']),
]
GROUPS = dict(F='a flight record of this aircraft', P='a published figure or test', M='another model or aircraft', D='a design requirement', G='generated')
