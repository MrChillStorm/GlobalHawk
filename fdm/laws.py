#!/usr/bin/env python3
"""The flight laws as a JSBSim system: GlobalHawk/Systems/laws.xml, written by fdm/genghawk.py through laws_file().

The real laws aren't public; these are ours, built to behave as the public sources say the aircraft does. The
design, its sources and its checks are in docs/FLIGHT-LAWS.md (local) and summarised in fdm/data/README.md.
Part A: the basic laws (pitch attitude, bank, yaw damping), the autopilot modes on top of them (speed by elevator,
altitude hold, heading), thrust modes, protections and actuators.

Properties: ap/engaged, ap/pitch-mode (0 attitude, 1 speed by elevator, 2 altitude), ap/roll-mode (3: the landing task's lateral law, 0 bank,
1 heading), ap/thrust-mode (0 as commanded, 1 maximum, 2 idle, 3 speed by thrust), and the targets ap/theta-cmd-deg,
ap/speed-cmd-kcas, ap/speed-schedule, ap/speed-offset-kcas, ap/alt-cmd-ft, ap/bank-cmd-deg, ap/heading-cmd-deg,
ap/throttle-cmd. ap/gain-scale multiplies every loop gain (for the gain-margin checks).
"""
import json
import math
import os

# gains at a dynamic pressure of 50 psf (docs/FLIGHT-LAWS.md, section 3)
G = dict(K_theta=1.4, K_q=0.6, K_theta_i=0.4, K_phi=0.5, K_phi_i=0.0, K_p=0.6, K_r=0.5, K_beta=1.5, K_beta_i=0.15, K_ari=0.0,
         K_alpha=3.0, K_slow=0.4,
         K_v=0.5, K_v_i=0.08, K_h=0.012, K_h_i=0.0012, K_hd=0.06, K_psi=1.2, K_thr=0.04, K_thr_i=0.004)
SURFACE = dict(lag=20.0, rate=40.0, limit=20.0)          # actuators: 0.05 s lag, 40 deg/s, 20 deg. Estimates
SCHEDULE = [(0.0, 0.0), (22000.0, 0.345), (55000.0, 0.60), (80000.0, 0.60)]     # pressure altitude, Mach above FL220
SCHEDULE_KCAS = 150.0
ALPHA_LIMIT = [(0.0, 7.0), (0.3, 6.0), (0.5, 5.0), (0.6, 3.5), (0.65, 2.5)]       # Mach, deg in body axes
BANK_LIMIT = [(0.0, 25.0), (30000.0, 25.0), (50000.0, 15.0), (80000.0, 15.0)]     # pressure altitude, deg
ALTITUDE_LIMIT = 65000.0
LEVEL_PROFILE = 1               # the altitude capture asks for the climb rate that a constant deceleration LEVEL_A_FPS2 can still take to nothing at the height (the circular path), where the linear law's would be harder than that (docs/PLAN.md, "Level-off")
LEVEL_I_FAR_FT = 150.0          # ft: and out to this where the aircraft is settled (LEVEL_I_RATE_GATE)
LEVEL_I_RATE_FPS = 3.0          # ft/s: settled: the climb rate under this
LEVEL_I_RATE_GATE = 1           # the integral's band is the near one whatever the rate, the far one only where settled
LEVEL_I_HOLD = 1                # the integral keeps its value while the gate is off (JSBSim's trigger resets it to zero: with the climb rate crossing 3 ft/s every 8 s it was reset every 8 s, the pitch swung 3.5 to 5.8 deg and the aircraft held 95 ft low, docs/PLAN.md)
LEVEL_OFFSET_TO_I = 2           # 1: always, 2: only where the height is below the aircraft (a capture from above), 0: never. In climbs it carried the pitch of the climb and the capture, whose lag and lead were tuned with the pitch let go, overshot 11 ft and rang (the user, 5,510 then 5,490); in descents it is what takes the dip from 20 to 13 ft. The pitch the previous mode was holding beyond its path angle, which the altitude mode lets go over LEVEL_OFFSET_TC, moves into the small integral instead of vanishing (offset + integral stay what they were): level flight needs the angle of attack (0.9 deg at 150 kt: 3.5 ft/s of sink) and the integral, winding 0.07 deg a second at 15 ft, took it back slowly: the descent's level-off went 20 ft under the height in the bench, 13 ft with this (docs/PLAN.md)
THRUST_ENTRY_TABLE = 1          # the speed law's throttle starts, where the mode begins in flight, from the aircraft's own table: the level-flight throttle at this speed, weight and height plus the path angle's and the configuration's terms (the baseline is latched afresh): the speed law began every hold from zero, the integral took 40 s to find the level throttle and the aircraft bled 153 to 145 kt in the descent's level-off (docs/PLAN.md)
LEVEL_ALPHA_FF = 1              # the altitude mode's pitch command carries the angle of attack of level flight at this Mach number, lift coefficient and height (pathperf.py's third grid) less the attitude latched at engagement: the command was anchored to that attitude (the runway's, about -0.3 deg), which is the right angle of attack at about 20,500 lb at 150 KCAS only: a 12,450 lb aircraft (level at -2.0 deg) flew its climb capture 1.7 deg nose high and overshot 8,000 ft by 34 ft, a 26,750 lb one (+1.1 deg) 1.4 deg nose low (docs/PLAN.md, "the level-flight angle of attack")
LEVEL_SPOILER_PITCH = 5.0       # deg of pitch per unit of spoiler (its actual position less its position at engagement) in the altitude mode: the spoilers dump 0.53 of lift coefficient a unit (data/calibration.json) and the lift curve's slope at the approach is 0.09 to 0.12 a degree, so the wing needs about 5 deg more angle of attack; the altitude mode had nothing to give it but a slow climb-rate command (docs/PLAN.md)
CFG_THRUST_FF = 1               # the speed law's throttle follows the drag of the spoilers and the gear (as a path angle, with the one feed-forward it has for the flight path angle): with the engine at idle
                                # and the landing configuration going out the thrust law waited for the speed to fall 4 kt, then the throttle's rate limit and the spool: thrust began 14 s after the drag (docs/PLAN.md)
CFG_GEAR_CD = 0.0148            # the gear's drag coefficient with the doors (fdm/genghawk.py GEAR_DRAG 0.0133 + GEAR_DOOR_DRAG 0.0015)
CFG_INDUCED_X = 1.10            # the spoilers' drag grows by this for the induced drag of the lift the wing makes up for them (at the approach: 2,570 lbf against 1,000 lbf clean, 0.0387 of drag coefficient against 0.0351 of the parts)
LEVEL_I_BAND_FT = 10.0          # ft: the capture's small integral runs within this of the height only (over a long capture it wound up and the aircraft went through the height); it was 25 ft with the integral's gain at 4 times, which made up for the level-flight angle of attack the command did not have (LEVEL_ALPHA_FF): with it, the integral inside 25 ft only wound up on the way in: +8 to +9 ft over the height at every weight, 10 ft: +4 to +6 (docs/PLAN.md, "the level-flight angle of attack")
LEVEL_THRUST_FF = 1            # the speed law's throttle follows the flight path angle: the throttle latched at engagement plus the table's slope (data/path_thrust.json) times the angle now less the angle at engagement
LEVEL_THETA_MAX = 30.0          # deg: the altitude capture's pitch attitude clip (the pitch command governor and the protections still limit what the aircraft is given)
CLIMB_MARGIN = 0.85             # of the climb rate the throttle table says the thrust holds: the manager flies a height change shorter than the capture of that rate wants entirely under the profile
LEVEL_OFFSET_SETTLED = 1        # also where the altitude mode takes the pitch settled at the height (LEVEL_OFFSET_TO_I 2 moves the offset into the integral for a capture from above only): the cruise-climb's capture of its ceiling, 95 ft of dip (docs/PLAN.md, "the ceiling ride")
LEVEL_OFFSET_TC = 6.0          # s: the pitch the aircraft was holding beyond what its path angle asks (a descent on spoilers and idle thrust holds 2.3 deg more than level flight does) is carried into the altitude mode and let go over this time, not stepped
LEVEL_SOFTMIN = 1              # the capture's climb rate is the soft minimum of the linear law's and the constant deceleration's
LEVEL_LAG_S = 2.0               # s: the capture's climb rate is also lagged, so that its acceleration begins as a ramp (a deceleration begun at once is a step of the load factor); the manager's gate is earlier by it
LEVEL_DIR_BAND_FT = 30.0        # ft: within this of the height the capture's direction (up or down to it) is held, not taken from the sign of the error
LEVEL_FOLLOW = 1               # the capture's climb rate is a state that starts from the climb rate there is and moves towards the profile at LEVEL_A_FPS2 at most: no step at the handover
TURN_BANK_LAG_S = 5.0           # s: the lag on the bank the turn's lead and radius are worked out for (0: none): the lead is a prediction and must not follow the gusts' flicker of the angle of attack's bank cap
THROTTLE_PATH_RATE = 0.9        # deg/s: the throttle goes up in the vertical modes so that the path angle it can hold changes by this much a second at most (the table's throttle per degree, by weight, height and speed): the pull-up of a climb entered at full thrust follows it, at a load factor change of 0.026 g in half a second. A fixed rate was 0.028 g at 20,800 lb and 0.13 at 12,000
THROTTLE_MODE2_X = 1.0           # times the throttle's up-rate where the speed law has the thrust (altitude mode, thrust mode 3): the limiter is for the climb entry's step to full thrust; at the end of a descent the thrust has to come back in a few seconds, and at 0.09 a second the aircraft kept sinking 12 ft under the height
THROTTLE_PATH_RATE_DOWN = 0.9   # deg/s: the same coming down (the climb's end and a descent's start)
THROTTLE_SLEW_UP = 0.08         # per second: ... and how fast it goes up in them (a climb entered at full thrust in 4 s is a pull-up of 1.6 g); the default is the same as down
PITCH_ENTRY = 0                 # in pitch mode 1 in the air (a climb or a descent flown on the speed) the pitch rate asked for is shaped: it is stopped on a constant deceleration profile and it builds up at no more than the rate below
PITCH_NZ_PER_S = 0.04          # g per second: the most the load factor is asked to change by the pitch rate's change (the contract is 0.03 g in half a second, 0.06 g/s; the airframe's response adds to what is asked)
SPEED_BUMPLESS = 1             # the speed law takes over from the pitch command with its proportional term cancelled (see ap/theta-speed-entry-deg)
GLIDE_SPOILER_RATE = 0            # per second: the most the spoilers' selection moves while the glide is flown, before the flare (0: no limit)
GLIDE_ALPHA_LEAD_S = 3.5         # s: in the glide before the flare the angle-of-attack protection looks this far ahead on a rising angle of attack, as it does by hand (0: not)
GA_SPEED_ADD_KT = 0.0            # the go-around task (ap/ga-on, set by the manager's missed approach) holds the approach speed plus this where it begins (swept: +10 kt put the nose down 7 deg and 149 ft under the 300 ft it was begun from: the speed law pitches for a speed it does not have; none loses 35 ft) ...
GA_SPEED_RAMP = 0.06             # ... and asks for this much more per foot of height gained, up to the schedule's speed (the schedule's 150 KCAS asked of an aircraft at 105 pitched it down 20 deg)
# ---- the smarter go-around (ap/ga-smart 1; docs/PLAN.md, "The go-around chases the airspeed in turbulence"): in the go-around's climb-out (ap/ga-on, pitch mode 1) the pitch holds the attitude that the thrust and the
# weight give (the path the thrust can climb at, plus the angle of attack), the speed's error, filtered, moving it only beyond a dead band and only within a limited range, and a slow integral taking out what is left
GA_LD = 30.0                     # the lift-to-drag ratio the scheduled attitude is worked out for (1 / L/D is the drag's share of the weight)
GA_THRUST_LBF = 5400.0           # lb: the thrust the climb is worked out for (full thrust at 150 KCAS low down: 5,450 measured)
GA_ALPHA_DEG = 1.0               # deg: the angle of attack in the climb (0.4 to 1.5 measured)
GA_SPEED_FILT_S = 4.0            # s: the speed's error is filtered over this: a gust is not an energy change
GA_BAND_KT = 8.0                 # kt: no pitch change for a speed error inside this
GA_KP = 0.25                     # deg of pitch per kt beyond the band
GA_AUTH_DEG = 4.0                # deg: the most the speed moves the attitude from the scheduled one
GA_KI = 0.02                     # deg per kt beyond the band per second: the slow integral ...
GA_I_MAX = 3.0                   # deg: ... and its limit
GA_THETA_MIN, GA_THETA_MAX = 0.0, 16.0      # deg: the attitude range of the climb-out
GA_THROTTLE_RATE = 3.0           # deg/s: the throttle goes up this fast in the go-around, in the climb's path-angle rate (THROTTLE_PATH_RATE is 0.9: 14 s to full thrust from the glide's)
GA_SPOILER_SLEW = 0.3            # per second at SPOILER_SLEW_LB: the spoilers come in this fast in the go-around (0.06: 16 s from the glide's 0.97)
THROTTLE_SLEW_LAND = 1          # the throttle's rate limit goes on in the landing until the flare (the landing law's idle was a step of 0.43 at the start of the glide: Nz 0.86)
THRUST_PITCH_FF = 0             # in pitch mode 1 the pitch asked for by the speed law carries the flight path angle that the change of thrust since the mode took over makes (asin(change / weight)): the pitch follows the thrust, so the speed does not run off while the nose is brought up (or down) by the speed error alone
THROTTLE_SLEW = 0.10            # per second: the throttle moves at most this fast while the aircraft is flying its vertical modes (pitch mode 1 or 2, not landing), so a change of thrust mode is not a step
LEVEL_FF = 1                    # the pitch for the flight path angle the climb rate asked for is fed forward (the speed held by the thrust, the attitude follows the path: pitch = path + the angle of attack)
LEVEL_CAP_RATE = 0              # the capture's climb rate asked for is no more than the aircraft's table of what the thrust holds (climb) or idle holds (descent)
LEVEL_CAP_MIN_FPS = 5.0         # ft/s: but at least this
LEVEL_GROW_FPS2 = 1.0           # ft/s^2: the most the capture's climb rate asked for may grow towards the height by (a climb under the profile from rest rises at 0.08 g)
MISSION_VERTICAL = 1            # the vertical task (climb, descent, level and the spoilers) is the laws': the manager gives ap/vt-on, ap/vt-ft and ap/vt-path and reads ap/vmode (docs/PLAN.md, "Job 2 in the laws")
MISSION_PHASES = 1              # the takeoff's handover, the taxi speed, the landing's pre-glide logic and the circle's heading are the laws' too (stage 2 of docs/PLAN.md, "Job 2 in the laws")
AIRBORNE_FT = 100.0             # ft: the takeoff hands over to the climb at this wheel height
CAPTURE_SPEED_KT = 10.0         # the glide is taken over only within this many kt of the approach speed: 30 kt over it the speed-by-elevator law pitched up 15 deg and the aircraft zoomed through the path
ROLLOUT_OVER_KT = 15.0          # kt: the landing's rollout is over below this ground speed
LEVEL_GATE_FT = 150.0           # ft: the altitude hold takes over from the climb or descent within this of the height ... (the manager's, moved here)
LEVEL_SHORT_FACTOR = 1.6        # ... and up to this many times the capture of the climb rate the aircraft can hold: a height change that short is flown entirely under the profile, from no climb rate
LEVEL_SHORT = 1                 # that short rule
LEVEL_ENERGY = 1                  # above LEVEL_ENERGY_ALT_FT a climb is not captured (the altitude mode is not begun) while the throttle for level flight at this speed, weight and height is LEVEL_ENERGY_THROTTLE or more: the thrust cannot hold the height, the altitude mode asks for a climb it cannot give and the aircraft goes to its angle-of-attack limit at Mach 0.57 for hours (the cruise-climb's last 1,000 ft, docs/PLAN.md, the 65,000 ft scenario); it goes on climbing at full thrust on the speed schedule and takes the height when it is light enough
LEVEL_ENERGY_ALT_FT = 45000.0     # the throttle table (pathperf.py) is to 65,000 ft and 14,000 and 16,000 lb since 2026-11-15; below this the rule is not used (the flights it was tuned on)
LEVEL_ENERGY_THROTTLE = 0.95
THRUST_ANTIWINDUP = 1           # the speed law's integral stops while the throttle it asks for is over its limit (0 or 1) and the error would push it further: JSBSim's PID limits only its output, the integral kept going: the landing start's step of the speed target from 150 to 102 KCAS (48 kt) wound it to about -3.4 under an output pinned at -1, the throttle stayed at idle 85 s after the speed fell under the target and a 12,450 lb aircraft sank 806 ft at the alpha limit (docs/PLAN.md, "the light-weight landing start")
LEVEL_STAY_FT = 8000.0          # once the altitude hold has the height it keeps it while the height stays the same, unless the aircraft is this far off it
DESCENT_SPOILER = 0.5           # the spoilers' command in a descent that has no path to steer along (and the base of the one that has)
DESCENT_ON_SPOILERS = 1         # a descent with a path (ap/vt-path) steers its slope with the spoilers: the sink the height over the target and the way to go ask for, DESCENT_SPOILER at the sink there is, DESCENT_SPOILER_K more for each ft/s lacking
DESCENT_SPOILER_K = 0.04        # spoiler travel per ft/s of sink the path asks for more than there is
DESCENT_SPOILER_KI = 0.003       # the same per second of ft/s lacking: the integral takes out the steady error of the proportional law (it left the aircraft 1.7 ft/s short of the sink the path asked for, falling behind it all the way down, and the spoilers piled on at the end: 0.56 to 0.75 in the box flight)
DESCENT_SPOILER_I_MAX = 0.4     # the integral's limit (spoiler travel)
DESCENT_LEAD_S = 20.0           # s: the path is flown to arrive this long before the point, the capture's time
LEVEL_SPOILER_END = 1             # the level-off of a descent ends at the spoiler setting ap/vt-sp-end (the manager gives the landing's when a landing follows), not at none
LEVEL_SPOILER_RAMP = 1          # coming out of a descent the spoilers go in with the height left to the level, over the capture, from where they were
SPOILER_SLEW = 0.06             # per second: the spoilers' command moves at most this fast at SPOILER_SLEW_LB (0.5 in 8 s): going in or coming out is a ramp, not a lift step
SPOILER_SLEW_LB = 20800.0       # lb: and in proportion to the weight below it (the same lift step is a larger load factor on a lighter aircraft)
LEVEL_RESPONSE_S = 2.5          # s: the aircraft's climb rate lags the command by about this: the capture's profile is worked out for where the aircraft will be by then (the height error less this times the climb rate towards the height), and the gate is earlier by the same distance (0: as it was)
LEVEL_SPOILER_ONESIDED = 1      # the spoilers go in with the height still to lose, none once the aircraft is under the height (by the distance from it they came back out after the crossing and held it down: 55 ft under 1,900 ft in the box flight)
LEVEL_SPOILER_LEAD = 0          # the capture of a descent with the spoilers out begins earlier by the time they take to come in (0.06 a second: 10 s from 0.63, the capture's 150 ft at 14 ft/s is 11 s: the aircraft was still shedding lift when it should have been level)
DESCENT_PATH_TO_TURN = 1        # the path to the height ends where the turn onto the next leg begins (the leg's end less the turn's lead), not at the corner: the aircraft was still settling onto 1,900 ft when it rolled into the 100 deg turn onto the final, and the bank (Nz 1.10) took it to 1,845 ft
LEVEL_BANK_FF = 1.0              # the altitude hold feeds forward the pitch a bank asks for: the load factor above 1 times the angle of attack over the zero-lift angle (a turn of 22 deg at 1.08 g took the aircraft 10 ft under the height; 0: none)
LEVEL_BANK_CLALPHA = 0.117       # per deg: the lift curve's slope the bank's pitch feed-forward is worked out with
LEVEL_BANK_PHYS = 1              # 1: the bank's feed-forward is (sec bank - 1) x the lift coefficient over the lift curve's slope, not the angle of attack over the zero-lift angle
LEVEL_BANK_LEAD_S = 4.0           # s: the bank-for-pitch feed-forward looks this far ahead along the bank's rate; 0: the bank now
ALPHA_ZERO_DEG = -3.0          # deg: the zero-lift angle of attack (the wing's: about 2.8 deg at the approach's lift coefficient of 0.645)
LEVEL_I_GAIN_X = 4.0            # times the altitude integral's gain
LEVEL_A_FPS2 = 2.6              # ft/s^2: 0.08 g of vertical acceleration at the level-off
BANK_COMMAND = 0.86            # of the bank limit: 21.5 deg low down (Pastor: 21), 13 deg at height (ATTREX: 15)
# part B (docs/FLIGHT-LAWS.md section 5)
WGS84_A = 6378137.0             # m: the semi-major axis of the ellipsoid GPS, FlightGear and JSBSim fly on (fdm/wgs84.py is the reference; the same formulas are in the Python and Nasal managers, the HUD and the station's geo.js)
WGS84_E2 = 0.00669437999014      # the first eccentricity squared
FT_PER_M = 1.0 / 0.3048
GLIDE_TAN = 0.07782              # tan of 4.45 deg: the measured approaches
APPROACH_CL = 0.645              # the measured approaches
SPOILER_BASE = 0.667             # 30 of 45 deg
# the turn onto the next leg is the aircraft's (docs/PLAN.md, "Turns onto a new leg"): the manager gives the laws the next waypoint and
# advances the leg when the laws say the turn is done
BANK_RATE = 5.0                  # deg/s: the rate limit of the bank target (the actuator below)
ALPHA_ZERO_LIFT = -4.6           # deg, body axes: where the lift is nothing. From two trims at 150 KEAS, clean: 12,000 lb at -2.0 deg and 26,000 lb at +1.0, a lift
                                 # coefficient of 0.292 and 0.632 (weight / q S), so 0.114 per deg and the lift is nothing at -4.6
TURN_ALPHA_MARGIN = 0.5          # deg kept under the angle-of-attack limit by the bank of a turn
TURN_MIN_BANK = 8.0              # deg: the least the angle-of-attack margin takes the bank down to (the pitch law's protection holds the rest)
TURN_DESIGN_LAG_S = 10.0         # s: the design bank is also held to the instantaneous cap through this lag: the tables' cap near an angle-of-attack margin of nothing (the cruise-climb at 56,000 ft: 0.5 deg of margin) is 13 deg where the aircraft's own is 8, a 0.1 deg difference, and the arc was 3 nmi wide of the lead
TURN_PRED_ON_HELD = 1            # the trim works once the bank is 90 % of the bank the turn is commanding (the design bank, or the one it holds), not of the instantaneous limit: a bank held below 90 % of a limit that had risen again never let it work
TURN_END_CONFIG = 1             # the turn's lead is worked out for the bank the angle-of-attack margin allows in the configuration the leg ends in (level, the spoilers at ap/vt-sp-end: the landing's when a landing follows), from the tables, not for the instantaneous margin: in a descent with the spoilers out in turbulence that margin flickers between 8 and 60 deg, the lead for a 140 deg turn between 25,000 and 90,000 ft, and the turn began on a spike of it (docs/PLAN.md, "The join onto the final")
TURN_FLY_BY_MAX = 150.0          # deg: past this the corner is led as if it were 150 deg (the waypoint is nearly flown over)
TURN_LEG_I = 1                  # and its small integral (within +-30 ft of the line) runs on a leg too, taking out the offset a leg keeps in a wind that was changing
TURN_LEG_LAW = 1                # a leg is followed (before its turn) with the landing task's damped lateral law (a velocity loop inside a position loop), not the cruise law's lookahead: the cruise law crosses the line once after a turn
TURN_SPEED_PRED = 1             # the arc is worked out at the mean of the airspeed now and the speed the laws hold (a speed still recovering from a wind step widens the arc)
TURN_SPEED_CLIP = 0.10           # the target over the airspeed, held to 1 +- this
TURN_PRED = 1                  # the turn trims its bank so that the arc from where it is ends on the new line (docs/PLAN.md, "the turn predicts its own exit")
TURN_PRED_MIN_REM_DEG = 25.0     # the prediction is held from here to the end: the arc to go is too short to be worked out from
TURN_PRED_MIN_B = 0.08           # and when 1 - cos(the heading to go) is under this
TURN_DRIFT = 1                  # the roll out's sideways drift is in the lead and in the predictor (docs/PLAN.md): the heading's tail runs on after the instant-roll-out equivalent stops
TURN_DRIFT_FADE_DEG = (30.0, 60.0)   # none under the first corner, all over the second: the roll in and the roll out overlap in a small turn
TURN_PRED_HOLD = 1              # when the prediction no longer applies (under TURN_PRED_MIN_REM_DEG to go) the trimmed bank is held to the end of the turn, not let back to the turn's own (the arc to go would be wider than it was worked for: 100 ft out at the exit, `phase8f` P5)
TURN_PRED_TC = 2.0               # s: the trimmed bank's lag
TURN_PRED_LO = 0.5               # the least bank the trim takes, of the turn's bank
TURN_WIND_MIN_DEG = 10.0         # a turn under this takes the old lead (R tan(delta / 2)): the wind term divides by sin(delta)
# the glide path on spoilers: the capture and the hold are one profile (docs/PLAN.md, "The takeoff's veer and the glide path's overshoot")
GLIDE_TAU = 4.0                  # s: the path error dies away with this time constant, so the aircraft arrives on the path and not through it
GLIDE_AZ = 3.0                   # ft/s2: far off the path the profile asks the sink rate to change no faster than this (it matters beyond 2 a tau^2, 96 ft)
GLIDE_KS, GLIDE_KIS, GLIDE_ICLIP = 0.15, 0.01, 0.25    # spoiler per ft/s of sink error against the profile; its integral per ft/s*s; the integral's limit
GLIDE_IBAND = 30.0               # ft: the integral runs only this close to the path and is held at zero outside (JSBSim's clip limits the output, not the state: it wound up far off the path)
YAW_AIR_BLEND_S = 3.0            # s: after lift-off the sideslip law comes in and the ground yaw term goes out over this time, not at once (at once: the yaw command stepped 8 deg in 0.5 s, the nose turned 7 deg in 1.5 s and the loop rang for 4 s; 0: at once)
ROLL_NO_BETA = 1               # 1: the sideslip law is off while the takeoff roll holds the line (on the mains, steering, not landing)
# The flare and the rotation, set against the records on 2026-11-13 (docs/PLAN.md, "FDM issues"): the first design (flare at
# 70 ft, gain 0.25, 2.3 ft/s wanted) touched down at 1.1 m/s where the two recorded landings had 0.66 and 0.75; at a gain
# of 0.6, 1.6 ft/s wanted and a flare from 45 ft it is 0.64 to 0.71 m/s from 12,500 to 26,000 lb, at 2.2 deg, with a peak
# of 1.4 g. The rotation began at 130 KIAS (Pastor's milestone, not a rotation speed) and the aircraft left the ground
# at 144 KEAS, above the 121 to 139 of the records; from 120 KIAS to 6.5 deg it leaves at 137 KEAS and 6.7 to 6.9 deg (records: 4.5 to 7).
PITCH_Q_TAKEOFF_X = 3.0        # times the pitch-rate damper's gain in the takeoff mode (pitch mode 3): the pitch pop at rotation; 1: as it was
ROLLOUT_NOSE_BLEND_S = 2.0        # s: the rollout's nose-down (3 deg of ruddervator) is blended in over this time, the pitch law flying the derotation meanwhile; 0: the step
FLARE_HEIGHT = 45.0             # ft of wheel height
FLARE_PITCH = 2.4                # deg: the measured touchdowns
FLARE_SINK = 1.6                 # ft/s wanted at the ground (0.5 m/s)
FLARE_GAIN = 0.6                 # spoiler travel per ft/s of sink error in the flare
FLARE_TTG = 2.6                  # s: the flare starts at this many seconds to touchdown at the sink it has beyond FLARE_SLACK, if that is higher than FLARE_HEIGHT
FLARE_SLACK = 4.0                # ft/s of sink that is not a downdraft: the approach's own is 17.2 and gusts of light turbulence reach 21, so only more
# ---- the gust system (docs/PLAN.md, "Gusts: find out first"): a switch, ap/gust-sys (0: the aircraft as it was, 1: on), that does nothing but in the landing (ap/land-mode 1, on the glide and in the flare, in the air)
GS_H_FT = 500.0                  # ft of wheel height: the system is on from here down
GS_PITCH_FLOOR_DEG = -1.0        # deg: in the glide the speed law may not take the nose under this attitude (the approach's own is +0.4): a lost headwind pitched it to -7 deg and the sink from 18 to 33 ft/s
GS_THR_PER_KT = 0.06             # throttle per kt of speed lost beyond GS_THR_DEAD_KT: the landing's throttle is idle (0.00) all the way down, nothing in it could be had against a shear
GS_THR_DEAD_KT = 4.0             # kt
GS_THR_MAX = 0.7                 # throttle
GS_THR_UP = 0.6                  # per second: the system's own rate limit up (the landing's is 0.08, a ramp for the engine's sake) ...
GS_THR_DOWN = 0.4                # ... and down (the throttle goes to idle in the flare)
GS_FLARE_K = 0.35                # deg of pitch more in the flare per ft/s of sink beyond what the flare wants (the spoilers are at their floor after a sink error of 1 ft/s: the pitch is what is left)
GS_FLARE_OK_FPS = 2.0            # ft/s of sink beyond the flare's own that the spoilers take, before the extra pitch
GS_GLIDE_K = 0.25                # deg of pitch more in the glide per ft/s of sink beyond the path's (plus GS_GLIDE_OK_FPS): a downdraught takes the angle of attack and the spoilers are at their floor in a second
GS_GLIDE_OK_FPS = 2.0            # ft/s
GS_GLIDE_MAX_DEG = 4.0           # deg
# ---- the approach speed's addition, picked by the aircraft (ap/approach-add-auto 1; docs/PLAN.md, "Gusts: find out first", the optimum): GS_AUTO_MAX kt times how gusty the air is (the wind at 20 ft that the
# spread of the wind about its 10 s mean would be: 10 times the per-axis rms) times how little of the wind is across the final; latched at GS_PICK_H_FT of wheel height and held below it
GS_AUTO_MAX_KT = 12.0
GS_AUTO_HP_S = 10.0              # s: the wind's mean the gusts are measured from is the total wind through this lag
GS_AUTO_EST_S = 30.0             # s: the mean square of the gusts goes through this lag
GS_PICK_H_FT = 1000.0            # ft of wheel height: above it the addition follows the estimate, from it down it is held
GS_AUTO_GUST = [(0.0, 0.0), (14.0, 0.0), (18.0, 1.0), (24.0, 1.0), (28.0, 0.0), (200.0, 0.0)]      # FITTED (2026-11-16, docs/PLAN.md, "The fitting rule") on the corrected `opt` flights, seeds 1 to 16, and frozen: in the units of the aircraft's own estimate (it reads about three quarters of the wind at 20 ft behind the turbulence): all of the maximum addition for a wind at 20 ft of about 30 kt, none below 19 and none above 38 (the addition did not bring the protection's events down at 40 kt and up, nor cost less than 5 ft of line and a hard landing)
GS_AUTO_CROSS = [(0.0, 1.0), (10.0, 1.0), (21.0, 0.5), (30.0, 0.0), (200.0, 0.0)]    # the wind across the final (kt) to the share of it: with a steady wind across, +6 kt was the most the line allowed (30 kt steady at 45 deg), +3 or more at 40 kt and up added hard landings or 20 ft of line
GS_ALERT_SPEED_KT = 8.0          # kt: the gust alert (ap/gust-alert, whether the system is on or not): speed lost this far under the target on the final ...
GS_ALERT_SINK_FPS = 8.0          # ft/s: ... or sink this far beyond the path's (in the flare, beyond the flare's own) ...
GS_ALERT_HOLD_S = 4.0            # s: ... and it stands this long after the last frame that met either
GS_FLARE_MAX_DEG = 3.5           # deg: the most the extra pitch adds to the flare's (tail clearance is not modelled: no source; the angle-of-attack protection stays above this)
DECRAB_H_START = 8.0             # ft of wheel height: the nose starts to come round to the runway's course (the MV-22B's engine-out landing does it from 3 s to 0.5 s before the wheels, by wheel height over the sink; the flare slows the descent as it goes, which holds that time at its own time constant from the flare's start: the decrab began 6 s out and the aircraft drifted off the line meanwhile; counted in height, it is in the last 3 s)
DECRAB_H_END = 1.0               # ft of wheel height: the decrab has gone as far as it goes in the air
DECRAB_K = 2.0                   # deg of rudder per deg of heading error in the air, from the decrab's weight (on the ground the ruddervators' own 0.5). Headless, 20 kt across: 8 to 1 ft, gain 1 leaves 3.8 deg of the 8.5 deg crab to the wheels (the rest taken on the runway, as the MV-22B does), 6 to 1.5 ft with gain 2 takes it nearly all off (1.2 deg left) and touches down with 7.8 deg of sideslip instead of 5.8
LANDING_YAW_K = 2.0              # deg of ruddervator per deg of heading error on the mains when it is not the takeoff roll (the landing's rollout, the taxi)
TAKEOFF_YAW_K = 3.0              # deg of ruddervator per deg of heading error on the takeoff roll (it is LANDING_YAW_K on the landing's rollout: gain 3 there doubled the yaw rate at touchdown and did not hold the line closer)
TAKEOFF_BLEND_K = 3.0             # the same gain for the ground term's fade-out over YAW_AIR_BLEND_S after the wheels leave (until the nose wheel's steering goes off at AIRBORNE_FT)
DECRAB = 1                       # 1: the landing task owns the yaw axis in its last seconds and on the runway (the sideslip law is faded out by the weight)
FINAL_T_OUTER_S = 25.0           # s: the landing task's lateral law (roll mode 3): the cross-track rate the line asks for is the cross-track over this ...
FINAL_T_INNER_S = 6.0            # s: ... and the lateral acceleration is the difference from the rate there is, over this (four times faster: no overshoot)
FINAL_SCHED = 1                  # 1: the landing task's loop times shorten with the height (the four numbers below; on from 2026-11-17), 0: FINAL_T_OUTER_S and FINAL_T_INNER_S at every height. A scan of the times against FlightGear-like turbulence (docs/PLAN.md, "The lateral law's loop times") cut the cross-track at the wheels from sd 44 ft to 17 ft at 10 s and 2.5 s; the legs and the join share the law, so the short times apply only in the landing task (roll mode 3) and only low
FINAL_T_OUTER_LAND_S = 8.0       # s: the position loop's time at and under FINAL_SCHED_LO_FT of wheel height (8 s and 2 s are the edge: faster rings in turbulence) ...
FINAL_T_INNER_LAND_S = 2.0       # s: ... and the rate loop's
FINAL_SCHED_LO_FT = 300.0        # ft of wheel height: the short times apply at and under this ...
FINAL_SCHED_HI_FT = 800.0        # ft: ... and the long ones (FINAL_T_OUTER_S, FINAL_T_INNER_S) at and over this, linearly between (the wheel height reads 1,000 above 1,000 ft)
FINAL_ANGLE_MAX_DEG = 30.0       # the intercept angle at the most: the rate asked for is at most vg sin of it
FINAL_BANK_MAX_DEG = 12.0        # the bank of the final's lateral law, at the most (swept: 8 deg makes a 30 deg intercept from 2,000 ft cross the line by 62 to 304 ft, 12 deg by 7 to 9 ft; 15 deg adds nothing on course)
FINAL_KI = 0.0002                # deg of bank per ft of cross-track and second: the slow integral that takes out the bias between the track and the leg's course (swept: 0 leaves 5 ft, 0.0005 over a 100 ft band overshoots 33 ft)
# ---- the final's integral for an offset that is not closing (ap/final-wide 1; docs/PLAN.md, "The landing in a strong crosswind from the right ends left of the centreline"): the lateral law is a position loop (the
# rate the line asks for, the cross-track over FINAL_T_OUTER_S) around a velocity loop with no integral, and the old cross-track integral runs only within 30 ft of the line at 0.0002 deg of bank per ft and second:
# a lack of bank of 0.5 deg (the roll loop's own accuracy) leaves 60 to 80 ft that nothing takes out (FlightGear, a 30 kt crosswind from the right). The position loop asks a closing rate of at least
# FINAL_I_FAR_FT / FINAL_T_OUTER_S = 1.2 ft/s beyond FINAL_I_FAR_FT, so a cross-track beyond it with a rate under FINAL_I_RATE_FPS is an offset that is not closing: this integral runs only then (and under
# FINAL_I_BELOW_FT of wheel height, within FINAL_I_BAND_WIDE_FT of the line). An intercept, whose rate follows what the loop asks, never meets the condition; three first versions that integrated
# the cross-track or the rate error whenever they were near the line or low overshot an intercept from 1,000 and 2,000 ft by 18 to 67 ft
FINAL_KI_WIDE = 0.0006           # deg of bank per ft of cross-track and second
FINAL_I_FAR_FT = 30.0            # ft: beyond this (the old integral's band) ...
FINAL_I_BAND_WIDE_FT = 300.0     # ft: ... and within this of the line ...
FINAL_I_RATE_FPS = 1.0           # ft/s: ... while the cross-track rate is under this ...
FINAL_I_BELOW_FT = 100000.0      # ft of wheel height: ... and under this height (the whole approach: legs and final; the wheel height reads 1,000 above 1,000 ft)
FINAL_I_WIDE_CLIP_DEG = 3.0      # deg of bank: its limit
# ---- the final's wind feed-forward (ap/final-ff 1; docs/PLAN.md, "The drift in the flare"): in the last 100 ft of FlightGear's 36 kt flights the crosswind fell by 7 kt (1.5 ft/s^2) and the aircraft, whose lateral
# velocity follows the wind with a lag of a few seconds, drifted away from the line at 2 to 5 ft/s before the position and rate loops (25 s and 6 s) could answer. The crosswind (the total wind across the leg's
# course) is smoothed (FF_SMOOTH_S) and differentiated (a washout over FF_DERIV_S: its output is FF_DERIV_S times the rate of change), the drift the change is about to cause is FF_TAU_S times the rate, and the bank
# that takes that rate out over FF_T_S is added to the lateral law's, within FF_CLIP_DEG, under FF_BELOW_FT of wheel height in the landing's roll mode
# ---- the final's rate-error integral (ap/final-ri 1): the position loop asks a rate and the velocity loop takes the bank for the rate error over FINAL_T_INNER_S, with no integral, so a wind that changes steadily
# (the nose follows the relative wind and turns the track off at a steady rate: 0.36 deg/s of heading in FlightGear's last 40 ft, against the 0.14 deg/s a bank of 1 deg turns) leaves a steady rate error and an offset
# that grows for as long as the wind changes. The integral of the rate error takes it out whatever the cause (no model of the wind), only close to the line (FINAL_RI_BAND_FT) and low (FINAL_RI_BELOW_FT)
FINAL_KI_RI = 0.02               # deg of bank per ft/s of rate error and second
FINAL_RI_BAND_FT = 60.0          # ft: within this of the line ...
FINAL_RI_BELOW_FT = 990.0        # ft of wheel height: ... and under this height
FINAL_RI_CLIP_DEG = 3.0          # deg of bank: its limit
FF_SMOOTH_S = 3.0                # s: the crosswind is smoothed over this before it is differentiated (turbulence is not a change of the wind)
FF_DERIV_S = 5.0                 # s: the washout's time constant
FF_TAU_S = 2.0                   # s: the lag with which the aircraft's lateral velocity follows the wind (an estimate)
FF_TAU_WEIGHT_LB = 26750.0       # lb: the weight FF_TAU_S was tuned at; the lag goes with the square root of the weight (the lift coefficient is held, so the speed goes with its root and the side force with the weight)
FF_T_S = 3.0                     # s: the time the bank takes the predicted rate out over
# ---- the aim offset (ap/final-aim 1; the user, 2026-11-17: the 36 kt wind from the side is what puts the touchdown left of the line, so aim upwind by an amount that goes with it): the line the position loop and the
# integral steer to is moved upwind by FINAL_AIM_FT_PER_KT feet for each knot of the crosswind component (the total wind, smoothed over FINAL_AIM_FILT_S, across the leg's course), from FINAL_AIM_FROM_FT of wheel
# height (0) to FINAL_AIM_FULL_FT (all of it), in the landing's roll mode only (the rollout's steering still reads the real line). The coefficient is the offset the FlightGear flights show: 1.3 to 2.4 ft per knot
# (28 kt: -68 and -73 ft at the wheels, 36 kt: -49 and -80 ft); the bench's steady wind shows 0.12 ft per knot (the decrab alone), so this is for the wind FlightGear blows and has to be judged against both
FINAL_AIM_FT_PER_KT = 2.0        # ft of aim point per kt of crosswind component
FINAL_AIM_FILT_S = 10.0          # s: the crosswind is smoothed over this (the aim does not follow the gusts)
FINAL_AIM_FROM_FT = 1000.0       # ft of wheel height: the aim begins ...
FINAL_AIM_FULL_FT = 700.0        # ft of wheel height: ... and is all there at this height
FF_CLIP_DEG = 3.0                # deg of bank: the most the feed-forward adds
FF_BELOW_FT = 500.0              # ft of wheel height: it runs under this
FINAL_I_BAND_FT = 30.0           # the integral runs only this close to the line and is held at zero outside it (JSBSim's clip limits the output, not the state)
FINAL_LAW = 1                    # 1: the landing item flies roll mode 3 (the manager sets it)
                                 # than about 21 ft/s makes the flare earlier (a first version, with no slack, floated 300-600 ft further in light turbulence)
ROTATE_KIAS, ROTATE_PITCH = 120.0, 6.5
DECEL_G = 0.235                  # the measured rollout
WING_AREA = 540.0


def roll_delay():
    """the bank's delay behind its target against the calibrated airspeed, s (rolltest.py writes data/roll_delay_gh.json, as the MV-22B's
    roll delay is measured and tabulated); none measured: 2 s"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'roll_delay_gh.json')
    if not os.path.exists(path):
        return [0.0, 300.0], [2.0, 2.0]
    d = json.load(open(path))
    return d['kcas'], d['delay_s']


def _cal_spoiler_cd():
    """the spoilers' drag coefficient for a spoiler setting of 1 (data/calibration.json, the fit of phase5_checks.py --fit)"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'calibration.json')
    return float(json.load(open(path)).get('spoiler_drag', 0.0)) if os.path.exists(path) else 0.0


def path_thrust():
    """the throttle for level flight and per degree of flight path angle (fdm/pathperf.py writes data/path_thrust.json), by Mach number, lift coefficient and pressure altitude; none measured: None"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'path_thrust.json')
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    return d if 'grid_throttle_per_deg' in d else None


def turn_performance():
    """the turn performance table (fdm/turnperf.py writes data/turn_performance.json): the bank flown over the bank commanded, less 1, by calibrated airspeed,
    weight and pressure altitude, and the largest bank the aircraft holds in a turn; none measured: None (the bank flown is the bank commanded)"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'turn_performance.json')
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    return d if 'grid_flown_per_cmd' in d else None


def _table3g(table_axis, row_axis, column_axis, grid, props, offset=0.0, ind='          '):
    """a JSBSim 3D table: grid[table][row][column] over the three axes (ascending), the lookups being props (table, row, column); trilinear, clamped at the edges; offset is added to every value"""
    rows = []
    for k, kv in enumerate(table_axis):
        rows.append('%s  <tableData breakPoint="%g">' % (ind, kv))
        rows.append('%s       %s' % (ind, ' '.join('%g' % h for h in column_axis)))
        for w, wv in enumerate(row_axis):
            rows.append('%s    %g  %s' % (ind, wv, ' '.join('%.5f' % (v + offset) for v in grid[k][w])))
        rows.append('%s  </tableData>' % ind)
    return ('%s<table>\n%s  <independentVar lookup="row">%s</independentVar>\n%s  <independentVar lookup="column">%s</independentVar>\n'
            '%s  <independentVar lookup="table">%s</independentVar>\n%s\n%s</table>' % (ind, ind, props[1], ind, props[2], ind, props[0], '\n'.join(rows), ind))


def _table3(axes, grid, props, offset=0.0, ind='          '):
    """a JSBSim 3D table: grid[speed][weight][height] over axes (speed_kcas, weight_lb, pressure_alt_ft), the lookups being props (speed, weight, height);
    offset is added to every value"""
    return _table3g(axes['speed_kcas'], axes['weight_lb'], axes['pressure_alt_ft'], grid, props, offset, ind)


def _table(pts, prop, ind='          '):
    rows = '\n'.join('%s    %g %g' % (ind, x, y) for x, y in pts)
    return '%s<table><independentVar lookup="row">%s</independentVar><tableData>\n%s\n%s</tableData></table>' % (ind, prop, rows, ind)


def _fn(name, expr, desc='', clip=None, out=None):
    s = '    <fcs_function name="%s">\n' % name
    if desc:
        s += '      <description>%s</description>\n' % desc
    s += '      <function>\n%s\n      </function>\n' % expr
    if clip:
        s += '      <clipto><min>%s</min><max>%s</max></clipto>\n' % clip
    if out:
        s += '      <output>%s</output>\n' % out
    return s + '    </fcs_function>'


def _p(name):
    return '<property>%s</property>' % name


def _v(x):
    return '<value>%g</value>' % x


def _op(op, *terms):
    return '        <%s>%s</%s>' % (op, ''.join(terms), op)


def _latch(name, follow, desc):
    """A property that follows another while the laws are off and holds it from the frame they come on."""
    return '''    <switch name="ap/latch-%s">
      <description>%s</description>
      <default value="ap/%s"/>
      <test value="%s">ap/engaged == 0</test>
      <output>ap/%s</output>
    </switch>''' % (name, desc, name, follow, name)


def _trigger(name, *conds):
    """An integrator's trigger: 0 lets it run, -1 holds it at zero. It runs only while every condition holds."""
    return '''    <switch name="ap/trig-%s">
      <default value="-1"/>
      <test logic="AND" value="0">
        %s
      </test>
    </switch>''' % (name, '\n        '.join(('ap/engaged == 1',) + conds))


def _pid(name, inp, kp, ki, trig, clip=None):
    s = '''    <pid name="%s">
      <input>%s</input>
      <kp>%s</kp>
      <ki>%s</ki>
      <kd>0</kd>
      <trigger>ap/trig-%s</trigger>
''' % (name, inp, kp, ki, trig)
    if clip:
        s += '      <clipto><min>%s</min><max>%s</max></clipto>\n' % clip
    return s + '    </pid>'


def _gain(name, value):
    """A gain property: its value at 50 psf times the dynamic-pressure schedule and the test scale."""
    return _fn('ap/k-%s' % name, _op('product', _v(value), _p('ap/gain-q'), _p('ap/gain-scale')))


def _actuator(name, inp, lag, rate, lo, hi):
    return '''    <actuator name="%s">
      <input>%s</input>
      <lag>%g</lag>
      <rate_limit>%g</rate_limit>
      <clipto><min>%g</min><max>%g</max></clipto>
    </actuator>''' % (name, inp, lag, rate, lo, hi)


def _final(name, law, manual, desc, out=None):
    """The surface: the law through its actuator when engaged, the manual value otherwise; no actuator in trims."""
    return '''    <switch name="ap/sel-%s">
      <default value="%s"/>
      <test value="%s">ap/engaged == 1</test>
    </switch>
%s
    <switch name="%s">
      <description>%s</description>
      <default value="ap/act-%s"/>
      <test value="ap/sel-%s">ctl/instant == 1</test>%s
    </switch>''' % (name, manual, law, _actuator('ap/act-%s' % name, 'ap/sel-%s' % name, SURFACE['lag'], SURFACE['rate'], -SURFACE['limit'], SURFACE['limit']),
                    'ctl/%s' % name, desc, name, name, ('\n      <output>%s</output>' % out) if out else '')


STICK_DEAD = 0.05
MANUAL_PITCH_RATE = 3.0                    # deg/s of pitch attitude at full stick
MANUAL_NZ = 0.5                            # g: the load factor change a full stick may ask for
MANUAL_BETA = 5.0                          # deg of sideslip at full pedal
MANUAL_PEDAL = 5.0                         # deg of ruddervator straight from the pedals
DIRECT = dict(pitch=12.0, roll=15.0, yaw=10.0)     # deg of surface at full stick in the direct law
LEAD_ALPHA, LEAD_SPEED = 2.0, 8.0          # s: how far ahead the protections look in the protected manual law
FAST_KCAS = 175.0                          # the governor pulls the nose up above this
LIMIT_NZ = (-1.0, 2.5)                     # assumed limit load factors (2.5: what the Phase 6 beam was sized for)
LIMIT_KEAS, LIMIT_MACH, FAIL_KEAS = 200.0, 0.70, 230.0      # assumed


def _direct_latch(axis, follow):
    """The surface command as it was on entering the direct law."""
    return '''    <switch name="ap/latch-direct-%s">
      <default value="ap/direct-%s-deg"/>
      <test value="%s">ap/manual lt 2</test>
      <output>ap/direct-%s-deg</output>
    </switch>''' % (axis, axis, follow, axis)


NAVS = ('kna', 'knb', 'lna', 'lnb')        # two Kearfott KN-4074E, two Litton LN-100G
NAV_DISAGREE_DEG = 3.0


def _navigators():
    """Four navigators, each the truth plus an error a test can set, and the selection between them
    (docs/FLIGHT-LAWS.md 6.1). Output: nav/roll-deg, nav/pitch-deg, nav/miscompare."""
    ch = []
    ch.append(_fn('nav/count', _op('sum', *[_p('nav/%s-on' % n) for n in NAVS]), 'navigators switched on'))
    ch.append('''    <lag_filter name="nav/roll-kinematic-deg">
      <description>the bank the turn rate implies, from the flight control system's own yaw-rate gyro: a reference no navigator supplies</description>
      <input>nav/roll-kinematic-raw-deg</input>
      <c1>1</c1>
    </lag_filter>''')
    ch.insert(len(ch) - 1, _fn('nav/roll-kinematic-raw-deg', '        <todegrees><atan><quotient><product>%s%s</product>%s</quotient></atan></todegrees>' % (
        _p('velocities/vt-fps'), _p('velocities/r-rad_sec'), _v(32.174))))
    ch.append(_fn('nav/pitch-kinematic-deg', _op('sum', _p('aero/alpha-deg'), _p('flight-path/gamma-deg')),
                  'the pitch attitude that air data and vertical speed imply'))
    for axis, truth, ref in (('roll', 'attitude/phi-deg', 'nav/roll-kinematic-deg'), ('pitch', 'attitude/theta-deg', 'nav/pitch-kinematic-deg')):
        vals = []
        for n in NAVS:
            ch.append(_fn('nav/%s-%s-deg' % (n, axis), _op('sum', _p(truth), _p('nav/%s-%s-error-deg' % (n, axis)))))
            vals.append('nav/%s-%s-deg' % (n, axis))
        sum_on = '<sum>%s</sum>' % ''.join('<product>%s%s</product>' % (_p('nav/%s-on' % n), _p(v)) for n, v in zip(NAVS, vals))
        ch.append(_fn('nav/%s-mean-deg' % axis, '        <quotient>%s<max>%s%s</max></quotient>' % (sum_on, _v(1), _p('nav/count')), 'mean of those switched on'))
        filled = []
        for n, v in zip(NAVS, vals):
            # one that is off takes the mean of the others' place, so it can be neither the highest nor the lowest
            ch.append(_fn('nav/%s-%s-filled-deg' % (n, axis), '        <ifthen><gt>%s%s</gt>%s%s</ifthen>' % (_p('nav/%s-on' % n), _v(0.5), _p(v), _p('nav/%s-mean-deg' % axis))))
            filled.append(_p('nav/%s-%s-filled-deg' % (n, axis)))
        ch.append(_fn('nav/%s-high-deg' % axis, '        <max>%s</max>' % ''.join(filled)))
        ch.append(_fn('nav/%s-low-deg' % axis, '        <min>%s</min>' % ''.join(filled)))
        ch.append(_fn('nav/%s-spread-deg' % axis, _op('difference', _p('nav/%s-high-deg' % axis), _p('nav/%s-low-deg' % axis))))
        ch.append(_fn('nav/%s-mid4-deg' % axis, '        <quotient><difference><difference><sum>%s</sum>%s</difference>%s</difference>%s</quotient>' % (
            ''.join(filled), _p('nav/%s-high-deg' % axis), _p('nav/%s-low-deg' % axis), _v(2)), 'of four, the mean of the middle two'))
        ch.append(_fn('nav/%s-mid3-deg' % axis, '        <difference><difference>%s%s</difference>%s</difference>' % (
            sum_on, _p('nav/%s-high-deg' % axis), _p('nav/%s-low-deg' % axis)), 'of three, the middle one'))
        ch.append(_fn('nav/%s-nearer-deg' % axis, '''        <ifthen>
          <lt><abs><difference>%s%s</difference></abs><abs><difference>%s%s</difference></abs></lt>
          %s
          %s
        </ifthen>''' % (_p('nav/%s-low-deg' % axis), _p(ref), _p('nav/%s-high-deg' % axis), _p(ref), _p('nav/%s-low-deg' % axis), _p('nav/%s-high-deg' % axis)),
                      'of two that disagree, the one nearer the reference'))
        ch.append('''    <switch name="nav/select-%(a)s">
      <description>%(a)s: the middle value of three or four; of two, their mean while they agree and the one nearer the reference when they don't; the last value with none</description>
      <default value="nav/%(a)s-deg"/>
      <test value="nav/%(a)s-mid4-deg">nav/count == 4</test>
      <test value="nav/%(a)s-mid3-deg">nav/count == 3</test>
      <test logic="AND" value="nav/%(a)s-nearer-deg">
        nav/count == 2
        nav/%(a)s-spread-deg gt %(d)g
      </test>
      <test value="nav/%(a)s-mean-deg">nav/count ge 1</test>
      <output>nav/%(a)s-deg</output>
    </switch>''' % dict(a=axis, d=NAV_DISAGREE_DEG))
    ch.append('''    <switch name="nav/latch-miscompare">
      <description>two navigators disagree: for the operator. Stays set until nav/miscompare-reset</description>
      <default value="nav/miscompare"/>
      <test value="0">nav/miscompare-reset == 1</test>
      <test logic="AND" value="1">
        nav/count == 2
        nav/roll-spread-deg gt %g
      </test>
      <test logic="AND" value="1">
        nav/count == 2
        nav/pitch-spread-deg gt %g
      </test>
      <output>nav/miscompare</output>
    </switch>''' % (NAV_DISAGREE_DEG, NAV_DISAGREE_DEG))
    return ch


def _mission_vertical():
    """The manager's vertical task (fdm/missionmgr.py vertical(), slew_spoiler(), descent_spoiler(), capture_gate(): job 2) as laws, so that it is one implementation, runs at the
    frame rate and is benched with the laws. Inputs: ap/vt-on (1: this task has the pitch mode, the thrust mode, the height command, the speed schedule and the spoilers),
    ap/vt-ft (the height at the end of the leg), ap/vt-path (1: a descent steers its slope with the spoilers to arrive there), ap/sp-ext (>= 0: the spoilers' command is moved
    towards this, whatever vt-on). Out: ap/vmode (1 climb, 2 descent, 3 level, 0 not on). The states (the level's height, what the aircraft was doing and how far out when the
    capture began, the spoilers then) are the manager's old ones."""
    X = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
    P, V = _p, _v
    M = lambda *a: X('product', *a)
    S = lambda *a: X('sum', *a)
    D = lambda a, b: X('difference', a, b)
    Q = lambda a, b: X('quotient', a, b)
    MAX = lambda *a: X('max', *a)
    MIN = lambda *a: X('min', *a)
    ABS = lambda a: X('abs', a)
    IF = lambda c, a, b: X('ifthen', c, a, b)
    AND = lambda *a: X('and', *a)
    OR = lambda *a: X('or', *a)
    GT = lambda a, b: X('gt', a, b)
    LE = lambda a, b: X('le', a, b)
    LT = lambda a, b: X('lt', a, b)
    GE = lambda a, b: X('ge', a, b)
    EQ = lambda a, b: X('eq', a, b)
    NQ = lambda a, b: X('nq', a, b)
    ch = []
    on = EQ(P('ap/vt-on'), V(1))
    err, alt = P('ap/v-err-ft'), P('ap/v-alt-ft')
    k, a, lag = G['K_h'] / G['K_hd'], LEVEL_A_FPS2, LEVEL_LAG_S + LEVEL_RESPONSE_S
    assert LEVEL_SOFTMIN

    def gate(r, floor, extra=V(0)):
        """the height error at which the capture asks for exactly the climb rate r (the soft minimum of the linear law k e and the constant deceleration sqrt(2 a e) is r: 2 a k^2 e^2 =
        r^2 (k^2 e + 2 a)), and the command's lag puts it back by r times the lag"""
        return MAX(V(floor), S(Q(S(M(r, r, V(k)), M(r, X('sqrt', S(M(r, r, V(k * k)), V(16 * a * a))))), V(4 * a * k)), M(r, S(V(lag), extra))))
    ch.append(_fn('ap/v-alt-ft', MIN(P('ap/vt-ft'), V(ALTITUDE_LIMIT)), 'the height the vertical task is asked for'))
    ch.append(_fn('ap/v-err-ft', D(alt, P('position/h-sl-ft')), 'the height to go, up positive'))
    ch.append(_fn('ap/v-toward-fps', MAX(V(0), M(IF(GT(err, V(0)), V(1), V(-1)), P('velocities/h-dot-fps'))), 'the climb rate towards the height'))
    ch.append(_fn('ap/v-sp-rate', M(IF(EQ(P('ap/ga-on'), V(1)), V(GA_SPOILER_SLEW), V(SPOILER_SLEW)), MIN(V(1), Q(P('inertia/weight-lbs'), V(SPOILER_SLEW_LB)))), 'the spoilers\' slew rate, per second (the go-around\'s faster)'))
    sp_in = IF(AND(LT(err, V(0)), V(1 if LEVEL_SPOILER_LEAD else 0)), Q(MAX(V(0), P('ap/spoiler-cmd')), P('ap/v-sp-rate')), V(0))      # a descent: the time the spoilers take to come in
    ch.append(_fn('ap/v-gate-ft', gate(P('ap/v-toward-fps'), LEVEL_GATE_FT, sp_in), 'the height to go at which the altitude mode takes over with no step in what it asks: where the profile asks for the climb rate there is'))
    short = V(0)
    if LEVEL_SHORT and path_thrust() is not None:
        ch.append(_fn('ap/v-rup-fps', IF(GT(err, V(0)), P('ap/climb-rate-max-fps'), P('ap/descent-rate-idle-fps')),
                      'the climb rate the thrust holds going up, the descent rate the speed law holds at idle going down'))
        ch.append(_fn('ap/v-short', IF(LE(ABS(err), M(V(LEVEL_SHORT_FACTOR), gate(P('ap/v-rup-fps'), 0.0))), V(1), V(0)),
                      'a height change shorter than the capture of the rate the aircraft can hold is flown entirely under the profile, from no climb rate'))
        short = EQ(P('ap/v-short'), V(1))
    stay = AND(EQ(P('ap/vmode'), V(3)), EQ(P('ap/v-level-alt'), alt), LE(ABS(err), V(LEVEL_STAY_FT)))
    refuse = V(0)
    if LEVEL_ENERGY and path_thrust() is not None:
        ch.append(_fn('ap/v-energy-short', IF(AND(GT(err, V(5)), GT(P('engine/pressure-altitude-ft'), V(LEVEL_ENERGY_ALT_FT)), GE(P('ap/throttle-level'), V(LEVEL_ENERGY_THROTTLE))), V(1), V(0)),
                      'a climb the thrust cannot hold level at the end of (the throttle for level flight here is at least %g): the altitude capture is not begun yet' % LEVEL_ENERGY_THROTTLE))
        refuse = EQ(P('ap/v-energy-short'), V(1))
    normal = IF(OR(stay, AND(OR(LE(ABS(err), P('ap/v-gate-ft')), short), EQ(refuse, V(0)))), V(3), IF(GT(err, V(0)), V(1), V(2)))
    ch.append(_fn('ap/v-mode-raw', IF(AND(EQ(P('ap/ga-on'), V(1)), GT(err, P('ap/v-gate-ft'))), V(1), normal),
                  'this frame\'s mode: 3 level (within the gate or a short change, not begun while the thrust cannot hold the height; or the height held), else 1 climb or 2 descent; the go-around climbs (full thrust) until the capture of its height'))
    mode = P('ap/v-mode-raw')
    # the capture's own states, latched on the frame the level begins (or its height changes)
    ch.append(_fn('ap/v-level-new', IF(AND(on, EQ(mode, V(3)), OR(NQ(P('ap/vmode'), V(3)), NQ(P('ap/v-level-alt'), alt))), V(1), V(0)), 'the frame the level (a new one) begins'))
    new = EQ(P('ap/v-level-new'), V(1))
    ch.append(_fn('ap/v-from-eff', IF(new, P('ap/vmode'), P('ap/v-level-from')), 'what the aircraft was doing when the capture began'))
    ch.append(_fn('ap/v-span-eff', IF(new, MAX(V(LEVEL_GATE_FT), ABS(err)), P('ap/v-level-span')), 'how far out the capture began: the spoilers go in with the height left over all of it'))
    ch.append(_fn('ap/v-sp0-eff', IF(new, P('ap/spoiler-cmd'), P('ap/v-level-sp0')), 'the spoilers\' command when the capture began: they go in from where they were'))
    ch.append(_fn('ap/v-level-from-next', P('ap/v-from-eff'), out='ap/v-level-from'))
    ch.append(_fn('ap/v-level-span-next', P('ap/v-span-eff'), out='ap/v-level-span'))
    ch.append(_fn('ap/v-level-sp0-next', P('ap/v-sp0-eff'), out='ap/v-level-sp0'))
    ch.append(_fn('ap/v-level-alt-next', IF(AND(on, EQ(mode, V(3))), alt, P('ap/v-level-alt')), out='ap/v-level-alt'))
    ch.append(_fn('ap/vmode-next', IF(on, mode, V(0)), 'the vertical task\'s mode: 1 climb, 2 descent, 3 level, 0 not on', out='ap/vmode'))
    # the spoilers
    way = D(P('ap/leg-togo-ft'), MAX(V(0), P('ap/turn-lead-ft'))) if DESCENT_PATH_TO_TURN else P('ap/leg-togo-ft')          # the way to the point where the turn begins
    t_go = MAX(V(10), D(Q(way, MAX(V(100), P('velocities/vg-fps'))), V(DESCENT_LEAD_S)))
    ch.append(_fn('ap/v-need-fps', MAX(V(0), Q(D(P('position/h-sl-ft'), alt), t_go)), 'the sink the path to the point asks for: the height over the target over the time to go, less the capture\'s time'))
    lacking = D(P('ap/v-need-fps'), M(V(-1), P('velocities/h-dot-fps')))
    steering = AND(on, EQ(mode, V(2)), EQ(P('ap/vt-path'), V(1)))
    ch.append(_fn('ap/v-sp-i-next', IF(steering, MIN(V(DESCENT_SPOILER_I_MAX), MAX(V(-DESCENT_SPOILER_I_MAX), S(P('ap/v-sp-i'), M(V(DESCENT_SPOILER_KI), P('simulation/dt'), lacking)))), V(0)),
                  'the spoilers\' integral on the sink the path asks for: held at nothing unless a descent is steering', out='ap/v-sp-i'))
    steer = MIN(V(1), MAX(V(0), S(V(DESCENT_SPOILER), M(V(DESCENT_SPOILER_K), lacking), P('ap/v-sp-i'))))
    ch.append(_fn('ap/v-sp-descent', IF(AND(EQ(P('ap/vt-path'), V(1)), V(1 if DESCENT_ON_SPOILERS else 0)), steer, V(DESCENT_SPOILER)),
                  'the spoilers in a descent: steering the slope onto the point (a path), else the fixed setting'))
    togo_h = MAX(V(0), M(V(-1), err)) if LEVEL_SPOILER_ONESIDED else ABS(err)          # the height still to lose (a descent: the height under the aircraft)
    frac = IF(EQ(P('ap/v-from-eff'), V(2)), MIN(V(1), Q(togo_h, P('ap/v-span-eff'))), V(0)) if LEVEL_SPOILER_RAMP else V(0)
    # the spoilers' level: coming out of a descent they go in with the height left to the setting the task ends at (ap/vt-sp-end: 0, or the landing's when a landing follows, so that the level
    # before it is already in the landing configuration and there is no retracting and putting them out again 76 s later: that was the dip of 21 ft of which the spoilers were 16)
    level_sp = IF(EQ(P('ap/v-from-eff'), V(2)), S(P('ap/vt-sp-end'), M(D(P('ap/v-sp0-eff'), P('ap/vt-sp-end')), frac)), M(P('ap/v-sp0-eff'), frac)) if LEVEL_SPOILER_END else M(P('ap/v-sp0-eff'), frac)
    ch.append(_fn('ap/v-sp-want', IF(EQ(mode, V(3)), level_sp, IF(EQ(mode, V(1)), V(0), P('ap/v-sp-descent'))), 'the spoilers\' command the task wants, before the slew'))
    own = OR(on, GE(P('ap/sp-ext'), V(0)))
    rate = P('ap/v-sp-rate')
    want = IF(on, P('ap/v-sp-want'), P('ap/sp-ext'))
    ch.append(_fn('ap/spoiler-cmd-next', IF(own, S(P('ap/spoiler-cmd'), MAX(M(V(-1), rate, P('simulation/dt')), MIN(M(rate, P('simulation/dt')), D(want, P('ap/spoiler-cmd'))))), P('ap/spoiler-cmd')),
                  'the spoilers\' command moved towards what the task (or ap/sp-ext) wants at the slew rate, whichever way; held when neither has it', out='ap/spoiler-cmd'))
    # the modes the task gives (held while it is not on: the manager or a bench sets them)
    other = IF(OR(EQ(P('ap/tk-air'), V(1)), EQ(P('ap/ld-cap-new'), V(1))), V(1), P('ap/pitch-mode')) if MISSION_PHASES else P('ap/pitch-mode')          # the takeoff's handover and the landing's capture (stage 2)
    ch.append(_fn('ap/pitch-mode-next', IF(on, IF(EQ(mode, V(3)), V(2), V(1)), other), out='ap/pitch-mode'))
    ch.append(_fn('ap/thrust-mode-next', IF(on, IF(EQ(mode, V(3)), V(3), IF(EQ(mode, V(1)), V(1), V(2))), P('ap/thrust-mode')), out='ap/thrust-mode'))
    ch.append(_fn('ap/alt-cmd-next', IF(on, alt, P('ap/alt-cmd-ft')), out='ap/alt-cmd-ft'))
    ch.append(_fn('ap/speed-schedule-next', IF(OR(on, EQ(P('ap/tk-air'), V(1))) if MISSION_PHASES else on, V(1), P('ap/speed-schedule')), out='ap/speed-schedule'))
    ch.append(_fn('ap/spoiler-mode-next', IF(own, V(1), P('ap/spoiler-mode')), out='ap/spoiler-mode'))
    return ch


def _mission_phases():
    """Stage 2 of job 2 (docs/PLAN.md, "Job 2 in the laws"): what the manager did at the frame rate in the takeoff, the taxi, the landing before the glide and the circle, as laws.
    Takeoff (ap/tk-on): at AIRBORNE_FT of wheel height the gear goes up, the speed schedule and the climb's pitch mode come on, the nose wheel's steering goes off, ap/tk-done is 1.
    Taxi (ap/tx-on, -fast, -slow, -bend-deg, -last, -stop): ap/taxi-speed-kt from the way to go on the leg; ap/tx-leg is 1 where the next leg is to be taken, ap/tx-done where the
    item is over. Landing before the glide (ap/ld-on): the approach speed is the speed command, the glide is captured (ap/ld-captured, latched) where the aircraft is within the
    profile's lead of the path and CAPTURE_SPEED_KT of the approach speed: the pitch mode 1, the land mode 1, the spoilers the glide law's; ap/ld-done at the rollout's end.
    Circle (ap/ci-on, -lat, -lon, -radius-ft, -side, -out-max, -lead): the heading command that flies a circle about a centre: the tangent, turned in or out for the distance off it."""
    X = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
    P, V = _p, _v
    M = lambda *a: X('product', *a)
    S = lambda *a: X('sum', *a)
    D = lambda a, b: X('difference', a, b)
    Q = lambda a, b: X('quotient', a, b)
    MAX = lambda *a: X('max', *a)
    MIN = lambda *a: X('min', *a)
    ABS = lambda a: X('abs', a)
    IF = lambda c, a, b: X('ifthen', c, a, b)
    AND = lambda *a: X('and', *a)
    OR = lambda *a: X('or', *a)
    GT = lambda a, b: X('gt', a, b)
    LT = lambda a, b: X('lt', a, b)
    EQ = lambda a, b: X('eq', a, b)
    ch = []
    # ---- takeoff
    ch.append(_fn('ap/tk-air', IF(AND(EQ(P('ap/tk-on'), V(1)), GT(P('aero/wheel-height-ft'), V(AIRBORNE_FT))), V(1), V(0)), 'the takeoff item is on and the aircraft is airborne'))
    ch.append(_fn('ap/tk-done-next', IF(EQ(P('ap/tk-on'), V(1)), IF(EQ(P('ap/tk-air'), V(1)), V(1), P('ap/tk-done')), V(0)), 'the takeoff has handed over (latched while the item is on)', out='ap/tk-done'))
    ch.append(_fn('ap/ground-steer-next', IF(EQ(P('ap/tk-air'), V(1)), V(0), P('ap/ground-steer')), out='ap/ground-steer'))
    ch.append(_fn('gear/gear-cmd-next', IF(EQ(P('ap/tk-air'), V(1)), V(0), P('gear/gear-cmd-norm')), 'the gear comes up when the takeoff hands over', out='gear/gear-cmd-norm'))
    # ---- taxi
    togo = P('ap/leg-togo-ft')
    fast, slow = P('ap/tx-fast'), P('ap/tx-slow')
    on_tx = EQ(P('ap/tx-on'), V(1))
    ch.append(_fn('ap/tx-speed-leg', IF(GT(P('ap/tx-bend-deg'), V(20)), MIN(fast, MAX(slow, S(slow, M(D(fast, slow), Q(D(togo, V(100)), V(250)))))), fast),
                  'the taxi speed on a leg that ends in a bend: slow for the corner, over the last 350 ft'))
    ch.append(_fn('ap/tx-speed-last', IF(EQ(P('ap/tx-stop'), V(1)), IF(LT(togo, V(12)), V(0), MIN(fast, MAX(V(3), M(V(0.12), togo)))), P('ap/taxi-speed-kt')),
                  'the taxi speed on the last leg: down to a walk, then stopped on the point (or what it was, if it does not stop)'))
    ch.append(_fn('ap/taxi-speed-next', IF(on_tx, IF(EQ(P('ap/tx-last'), V(1)), P('ap/tx-speed-last'), P('ap/tx-speed-leg')), P('ap/taxi-speed-kt')), out='ap/taxi-speed-kt'))
    ch.append(_fn('ap/tx-leg', IF(AND(on_tx, EQ(P('ap/tx-last'), V(0)), LT(togo, V(40))), V(1), V(0)), 'the next taxi leg is to be taken'))
    ch.append(_fn('ap/tx-done', IF(AND(on_tx, EQ(P('ap/tx-last'), V(1)),
                                       IF(EQ(P('ap/tx-stop'), V(1)), AND(LT(togo, V(12)), LT(P('ap/ground-speed-kt'), V(0.3))), LT(togo, V(40)))), V(1), V(0)), 'the taxi item is over'))
    # ---- the landing before the glide
    on_ld = EQ(P('ap/ld-on'), V(1))
    ch.append(_fn('ap/ld-cap-new', IF(AND(on_ld, EQ(P('ap/ld-captured'), V(0)), GT(P('ap/glide-error-ft'), M(V(-1), P('ap/glide-lead-ft'))),
                                         LT(D(P('velocities/vc-kts'), P('ap/approach-keas')), V(CAPTURE_SPEED_KT))), V(1), V(0)), 'the frame the glide is taken over'))
    ch.append(_fn('ap/ld-captured-next', IF(on_ld, IF(OR(EQ(P('ap/ld-captured'), V(1)), EQ(P('ap/ld-cap-new'), V(1))), V(1), V(0)), V(0)), 'the glide has been taken over (latched while the item is on)', out='ap/ld-captured'))
    ch.append(_fn('ap/speed-cmd-next', IF(AND(on_ld, EQ(P('ap/ld-captured'), V(0))), P('ap/approach-keas'), P('ap/speed-cmd-kcas')), 'the approach speed until the glide is taken', out='ap/speed-cmd-kcas'))
    ch.append(_fn('ap/land-mode-next', IF(EQ(P('ap/ld-cap-new'), V(1)), V(1), P('ap/land-mode')), out='ap/land-mode'))
    ch.append(_fn('ap/sp-ext-next', IF(AND(on_ld, OR(EQ(P('ap/ld-captured'), V(1)), EQ(P('ap/ld-cap-new'), V(1)))), V(-1), P('ap/sp-ext')), 'the spoilers are the glide law\'s from the capture', out='ap/sp-ext'))
    ch.append(_fn('ap/ld-done', IF(AND(on_ld, EQ(P('ap/ld-captured'), V(1)), EQ(P('ap/rollout'), V(1)), LT(P('ap/ground-speed-kt'), V(ROLLOUT_OVER_KT))), V(1), V(0)), 'the rollout is over'))
    # ---- the circle: the heading command about a centre
    RAD = lambda a: X('toradians', a)
    DEG = lambda a: X('todegrees', a)
    on_ci = EQ(P('ap/ci-on'), V(1))
    ch.extend(_g_point('cic', 'ap/ci-lat', 'ap/ci-lon'))
    ch.extend(_g_point('cia', 'position/lat-geod-deg', 'position/long-gc-deg'))
    ch.extend(_g_enu('cic', 'cia', 'ap/ci-dn-ft', 'ap/ci-de-ft', 'aircraft, in the tangent plane at the circle\'s centre'))
    ch.append(_fn('ap/ci-out-deg', DEG(X('atan2', P('ap/ci-de-ft'), P('ap/ci-dn-ft'))), 'the bearing from the centre to the aircraft, -180 to 180'))
    ch.append(_fn('ap/ci-dist-ft', X('sqrt', S(M(P('ap/ci-dn-ft'), P('ap/ci-dn-ft')), M(P('ap/ci-de-ft'), P('ap/ci-de-ft')))), 'the distance from the centre'))
    radius, side = P('ap/ci-radius-ft'), P('ap/ci-side')
    bank = DEG(X('atan', Q(M(P('velocities/vg-fps'), P('velocities/vg-fps')), M(V(32.174), radius))))
    ahead = IF(EQ(P('ap/ci-lead'), V(1)), Q(bank, Q(M(V(G['K_psi']), MAX(P('velocities/vt-fps'), V(100))), V(600))), V(0))
    inout = MIN(V(80), MAX(M(V(-1), P('ap/ci-out-max')), M(V(60), Q(D(P('ap/ci-dist-ft'), radius), radius))))
    raw = S(P('ap/ci-out-deg'), M(V(90), side), M(side, S(ahead, inout)))
    ch.append(_fn('ap/ci-heading-deg', IF(GT(DEG(X('atan2', X('sin', RAD(raw)), X('cos', RAD(raw)))), V(0)), DEG(X('atan2', X('sin', RAD(raw)), X('cos', RAD(raw)))),
                                          S(DEG(X('atan2', X('sin', RAD(raw)), X('cos', RAD(raw)))), V(360))), 'the heading that flies the circle, 0 to 360'))
    ch.append(_fn('ap/heading-cmd-next', IF(on_ci, P('ap/ci-heading-deg'), P('ap/heading-cmd-deg')), out='ap/heading-cmd-deg'))
    return ch


def _ga_smart():
    """The smarter go-around's pitch (see GA_*): active while ap/ga-smart is 1, the go-around task is on (ap/ga-on), the pitch mode is 1 and the aircraft is in the air and not flaring."""
    X = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
    P, V = _p, _v
    M = lambda *a: X('product', *a)
    S = lambda *a: X('sum', *a)
    D = lambda a, b: X('difference', a, b)
    Q = lambda a, b: X('quotient', a, b)
    MAX = lambda *a: X('max', *a)
    MIN = lambda *a: X('min', *a)
    ABS = lambda a: X('abs', a)
    IF = lambda c, a, b: X('ifthen', c, a, b)
    AND = lambda *a: X('and', *a)
    GT = lambda a, b: X('gt', a, b)
    EQ = lambda a, b: X('eq', a, b)
    ch = []
    # the climb-out is flown for the whole missed approach, not only the first GA_FREE_FT of height gained that the go-around task (ap/ga-on) lasts: latched when the task begins, held while the pitch mode is the
    # speed's and the aircraft climbs (not landing, not on the ground), released at the level-off (pitch mode 2), when the landing begins or when the laws are off
    ch.append(_fn('ap/ga-latch-next', IF(AND(EQ(P('ap/ga-smart'), V(1)), EQ(P('ap/ga-on'), V(1))), V(1),
                                         IF(AND(EQ(P('ap/ga-latch'), V(1)), EQ(P('ap/pitch-mode'), V(1)), EQ(P('ap/land-mode'), V(0)), EQ(P('ap/on-mains'), V(0)), EQ(P('ap/engaged'), V(1))), V(1), V(0))),
                  'the missed approach\'s climb-out is on (latched from the go-around task to the level-off)', out='ap/ga-latch'))
    ch.append(_fn('ap/ga-smart-active', IF(AND(EQ(P('ap/ga-smart'), V(1)), EQ(P('ap/ga-latch'), V(1)), EQ(P('ap/pitch-mode'), V(1)), EQ(P('ap/flare'), V(0)), EQ(P('ap/on-mains'), V(0))), V(1), V(0)),
                  'the smarter go-around holds the pitch'))
    ch.append(_fn('ap/ga-verr-kt', D(P('velocities/vc-kts'), P('ap/speed-target-kcas')), 'the climb-out\'s speed error, kt (fast is positive): the go-around speed while the task is on, then the speed the route asks'))
    ch.append('''    <lag_filter name="ap/ga-verr-f-kt">
      <input>ap/ga-verr-kt</input>
      <c1>%g</c1>
    </lag_filter>''' % (1.0 / GA_SPEED_FILT_S))
    ch.append(_fn('ap/ga-vband-kt', IF(GT(ABS(P('ap/ga-verr-f-kt')), V(GA_BAND_KT)), D(P('ap/ga-verr-f-kt'), M(IF(GT(P('ap/ga-verr-f-kt'), V(0)), V(1), V(-1)), V(GA_BAND_KT))), V(0)),
                  'the filtered speed error beyond the dead band, kt'))
    ch.append(_fn('ap/ga-theta-ref-deg', S(M(V(57.29578), X('asin', MIN(V(0.5), MAX(V(0), D(Q(V(GA_THRUST_LBF), MAX(V(5000), P('inertia/weight-lbs'))), V(1.0 / GA_LD)))))), V(GA_ALPHA_DEG)),
                  'the attitude the thrust and the weight give a climb at: the path (thrust over weight less the drag\'s share) and the angle of attack'))
    ch.append(_fn('ap/ga-theta-i-next', IF(EQ(P('ap/ga-smart-active'), V(1)), MAX(V(-GA_I_MAX), MIN(V(GA_I_MAX), S(P('ap/ga-theta-i-deg'), M(V(-GA_KI), P('ap/ga-vband-kt'), P('simulation/dt'))))), V(0)),
                  'the slow integral of the speed error beyond the band (fast pitches down), deg', out='ap/ga-theta-i-deg'))
    ch.append(_fn('ap/theta-ga-deg', D(MAX(V(GA_THETA_MIN), MIN(V(GA_THETA_MAX), S(P('ap/ga-theta-ref-deg'), MAX(V(-GA_AUTH_DEG), MIN(V(GA_AUTH_DEG), M(V(-GA_KP), P('ap/ga-vband-kt')))), P('ap/ga-theta-i-deg')))), P('ap/theta-latched-deg')),
                  'the go-around\'s attitude as a change from the latched one'))
    return ch


def _g_point(tag, lat, lon):
    """channels for a point on the ellipsoid: sin and cos of its latitude and longitude, and its ECEF coordinates in metres (x to 0 N 0 E, y to 0 N 90 E, z to the pole)"""
    la, lo = '<toradians>%s</toradians>' % _p(lat), '<toradians>%s</toradians>' % _p(lon)
    out = [_fn('ap/g-%s-sp' % tag, '<sin>%s</sin>' % la), _fn('ap/g-%s-cp' % tag, '<cos>%s</cos>' % la),
           _fn('ap/g-%s-sl' % tag, '<sin>%s</sin>' % lo), _fn('ap/g-%s-cl' % tag, '<cos>%s</cos>' % lo)]
    sp, cp, sl, cl = [_p('ap/g-%s-%s' % (tag, k)) for k in ('sp', 'cp', 'sl', 'cl')]
    rn = '<quotient>%s<sqrt><difference>%s<product>%s%s%s</product></difference></sqrt></quotient>' % (_v(WGS84_A), _v(1), _v(WGS84_E2), sp, sp)
    out.append(_fn('ap/g-%s-x' % tag, _op('product', rn, cp, cl)))
    out.append(_fn('ap/g-%s-y' % tag, _op('product', rn, cp, sl)))
    out.append(_fn('ap/g-%s-z' % tag, _op('product', rn, _v(1.0 - WGS84_E2), sp)))
    return out


def _g_enu(org, pt, out_n, out_e, desc):
    """channels: the point's feet north and east in the tangent plane at the origin (through the ECEF coordinates: exact, no scale factors)"""
    sp, cp, sl, cl = [_p('ap/g-%s-%s' % (org, k)) for k in ('sp', 'cp', 'sl', 'cl')]
    d = lambda k: '<difference>%s%s</difference>' % (_p('ap/g-%s-%s' % (pt, k)), _p('ap/g-%s-%s' % (org, k)))
    e = _op('product', _v(FT_PER_M), _op('sum', _op('product', _v(-1), sl, d('x')), _op('product', cl, d('y'))))
    n = _op('product', _v(FT_PER_M), _op('sum', _op('product', _v(-1), sp, cl, d('x')), _op('product', _v(-1), sp, sl, d('y')), _op('product', cp, d('z'))))
    return [_fn(out_n, n, 'feet north of the %s of the %s' % ('origin', desc)), _fn(out_e, e, 'feet east of the origin of the %s' % desc)]


def _g_track(org, ac, out, desc, vel=None):
    """a channel: the ground track in the tangent plane at the origin: the aircraft's velocity (north, east, down at where it is) turned into the origin's north and east.
    With vel = (north, east, down) given as expressions, the same for that vector: (1, 0, 0) gives the turn of the origin's north against the local north at the aircraft."""
    s = lambda t, k: _p('ap/g-%s-%s' % (t, k))
    vn, ve, vd = vel if vel else (_p('velocities/v-north-fps'), _p('velocities/v-east-fps'), _p('velocities/v-down-fps'))
    m1 = _v(-1)
    vx = _op('sum', _op('product', m1, s(ac, 'sp'), s(ac, 'cl'), vn), _op('product', m1, s(ac, 'sl'), ve), _op('product', m1, s(ac, 'cp'), s(ac, 'cl'), vd))
    vy = _op('sum', _op('product', m1, s(ac, 'sp'), s(ac, 'sl'), vn), _op('product', s(ac, 'cl'), ve), _op('product', m1, s(ac, 'cp'), s(ac, 'sl'), vd))
    vz = _op('sum', _op('product', s(ac, 'cp'), vn), _op('product', m1, s(ac, 'sp'), vd))
    ve2 = _op('sum', _op('product', m1, s(org, 'sl'), vx), _op('product', s(org, 'cl'), vy))
    vn2 = _op('sum', _op('product', m1, s(org, 'sp'), s(org, 'cl'), vx), _op('product', m1, s(org, 'sp'), s(org, 'sl'), vy), _op('product', s(org, 'cp'), vz))
    return _fn(out, '        <todegrees><atan2>%s%s</atan2></todegrees>' % (ve2, vn2), desc)


def _gust_picker():
    """The approach speed's addition, picked by the aircraft: from the wind's spread about its 10 s mean (the three axes' mean square, through GS_AUTO_EST_S) and the wind across the leg's course (the final's:
    the filtered wind the turn prediction and the crosswind caution use), by the tables GS_AUTO_GUST and GS_AUTO_CROSS; followed from wherever the aircraft is and held from GS_PICK_H_FT of wheel height down, so that
    the speed does not move in the glide. ap/approach-add-auto 1 uses it, 0 (the default) the addition ap/approach-add-kt as it was set (0)."""
    X = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
    P, V = _p, _v
    M = lambda *a: X('product', *a)
    S = lambda *a: X('sum', *a)
    D = lambda a, b: X('difference', a, b)
    Q = lambda a, b: X('quotient', a, b)
    MAX = lambda *a: X('max', *a)
    ABS = lambda a: X('abs', a)
    IF = lambda c, a, b: X('ifthen', c, a, b)
    GT = lambda a, b: X('gt', a, b)
    EQ = lambda a, b: X('eq', a, b)
    k = math.pi / 180.0
    ch = []
    ch.append('''    <lag_filter name="ap/gs-wind-down-filt-fps">
      <input>atmosphere/total-wind-down-fps</input>
      <c1>%g</c1>
    </lag_filter>''' % (1.0 / GS_AUTO_HP_S))
    for comp in ('north', 'east'):
        ch.append('''    <lag_filter name="ap/gs-wind-%s-filt-fps">
      <input>atmosphere/total-wind-%s-fps</input>
      <c1>%g</c1>
    </lag_filter>''' % (comp, comp, 1.0 / GS_AUTO_HP_S))
    sq = lambda a, b: X('pow', D(P(a), P(b)), V(2))
    ch.append(_fn('ap/gs-dw2-fps2', S(sq('atmosphere/total-wind-north-fps', 'ap/gs-wind-north-filt-fps'), sq('atmosphere/total-wind-east-fps', 'ap/gs-wind-east-filt-fps'),
                                        sq('atmosphere/total-wind-down-fps', 'ap/gs-wind-down-filt-fps')), 'the wind\'s departure from its mean, squared, summed over the three axes'))
    ch.append('''    <lag_filter name="ap/gs-dw2-lp-fps2">
      <input>ap/gs-dw2-fps2</input>
      <c1>%g</c1>
    </lag_filter>''' % (1.0 / GS_AUTO_EST_S))
    ch.append(_fn('ap/gust-sigma-kt', Q(X('sqrt', Q(MAX(V(0), P('ap/gs-dw2-lp-fps2')), V(3))), V(1.68781)), 'how gusty the air is: the per-axis rms of the wind about its mean, kt'))
    ch.append(_fn('ap/gs-w20e-kt', M(V(10), P('ap/gust-sigma-kt')), 'the wind at 20 ft that spread belongs to (sigma_w = 0.1 W20), kt'))
    ch.append(_fn('ap/gs-xw-kt', Q(ABS(S(M(V(-1), P('ap/gs-wind-north-filt-fps'), X('sin', M(P('ap/leg-course-deg'), V(k)))), M(P('ap/gs-wind-east-filt-fps'), X('cos', M(P('ap/leg-course-deg'), V(k)))))), V(1.68781)),
                  'the mean wind across the leg\'s course, kt'))
    ch.append(_fn('ap/gs-add-gust', _table(GS_AUTO_GUST, 'ap/gs-w20e-kt'), 'the share of the maximum addition the gusts are worth'))
    ch.append(_fn('ap/gs-add-cross', _table(GS_AUTO_CROSS, 'ap/gs-xw-kt'), 'the share of it the crosswind leaves'))
    ch.append(_fn('ap/gs-add-now', M(V(GS_AUTO_MAX_KT), P('ap/gs-add-gust'), P('ap/gs-add-cross')), 'the addition the air asks for now, kt'))
    ch.append(_fn('ap/gs-add-lat-next', IF(GT(P('aero/wheel-height-ft'), V(GS_PICK_H_FT - 1.0)), P('ap/gs-add-now'), P('ap/gs-add-lat')), 'followed above GS_PICK_H_FT of wheel height (the wheel height reads 1,000 ft above 1,000: it is clipped there), held under it', out='ap/gs-add-lat'))
    # the ground-speed minimum, as the A320 family's FMGC has it (Nasal/FMGC/FMGC.nas: gsMini = Vapp - max(10, the entered wind's component); the target = max(Vapp, gsMini + the live headwind)): the target
    # is Vapp plus how far the live headwind (the filtered wind along the final's course) is over the entered one (the tower's, ap/tower-hw-kt, at least 10 kt): a gust's extra speed is kept, so that
    # when it ends the airspeed falls back to Vapp and not under it. Switch ap/gsmini-on (0 by default)
    k = math.pi / 180.0
    ch.append(_fn('ap/gs-hw-live-kt', Q(M(V(-1), S(M(P('ap/gs-wind-north-filt-fps'), X('cos', M(P('ap/leg-course-deg'), V(k)))), M(P('ap/gs-wind-east-filt-fps'), X('sin', M(P('ap/leg-course-deg'), V(k)))))), V(1.68781)),
                  'the live headwind along the leg\'s course, kt (positive: into the wind)'))
    ch.append(_fn('ap/gs-gsmini-add', IF(EQ(P('ap/gsmini-on'), V(1)), MAX(V(0), D(P('ap/gs-hw-live-kt'), MAX(V(10), P('ap/tower-hw-kt')))), V(0)), 'what the ground-speed minimum adds to the approach speed, kt'))
    ch.append(_fn('ap/approach-add-used', S(IF(EQ(P('ap/approach-add-auto'), V(1)), P('ap/gs-add-lat'), P('ap/approach-add-kt')), P('ap/gs-gsmini-add')), 'the addition the approach speed carries: the aircraft\'s own pick, or the one set, and the ground-speed minimum\'s'))
    return ch


def _gust_system():
    """The gust system's channels (constants GS_*; the switch is ap/gust-sys). On only in the landing, in the air, from GS_H_FT of wheel height down: (1) in the glide the speed law may not take the nose under GS_PITCH_FLOOR_DEG
    (the nose-down that a lost headwind asks for doubled the sink); (2) the throttle, idle all through the landing otherwise, is GS_THR_PER_KT per kt of speed lost beyond GS_THR_DEAD_KT, with its own rate limits, and goes to idle
    in the flare; (3) in the flare the pitch goes up by GS_FLARE_K deg for each ft/s of sink beyond what the flare wants (plus GS_FLARE_OK_FPS), to GS_FLARE_MAX_DEG: the spoilers are at their floor for any sink error over 1 ft/s,
    the pitch is the control that is left. The angle-of-attack protection is above all of these."""
    X = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
    P, V = _p, _v
    M = lambda *a: X('product', *a)
    S = lambda *a: X('sum', *a)
    D = lambda a, b: X('difference', a, b)
    MAX = lambda *a: X('max', *a)
    MIN = lambda *a: X('min', *a)
    IF = lambda c, a, b: X('ifthen', c, a, b)
    AND = lambda *a: X('and', *a)
    GT = lambda a, b: X('gt', a, b)
    LT = lambda a, b: X('lt', a, b)
    EQ = lambda a, b: X('eq', a, b)
    ch, early = [], []
    early.append(_fn('ap/gs-on', IF(AND(EQ(P('ap/gust-sys'), V(1)), EQ(P('ap/engaged'), V(1)), EQ(P('ap/manual'), V(0)), EQ(P('ap/land-mode'), V(1)), EQ(P('ap/rollout'), V(0)), EQ(P('ap/on-mains'), V(0)),
                                 LT(P('aero/wheel-height-ft'), V(GS_H_FT))), V(1), V(0)), 'the gust system is on: switched on, in the landing, in the air, under GS_H_FT'))
    early.append(_fn('ap/gs-glide-extra-deg', IF(AND(EQ(P('ap/gs-on'), V(1)), EQ(P('ap/flare'), V(0))), MIN(V(GS_GLIDE_MAX_DEG), M(V(GS_GLIDE_K), MAX(V(0), D(D(V(0), P('ap/glide-sink-error-fps')), V(GS_GLIDE_OK_FPS))))), V(0)),
                  'pitch more in the glide for the sink beyond the path\'s that the spoilers cannot take'))
    early.append(_fn('ap/theta-speed-gs-deg', IF(AND(EQ(P('ap/gs-on'), V(1)), EQ(P('ap/flare'), V(0))), S(MAX(P('ap/theta-speed-deg'), D(V(GS_PITCH_FLOOR_DEG), P('ap/theta-latched-deg'))), P('ap/gs-glide-extra-deg')), P('ap/theta-speed-deg')),
                  'the speed law\'s pitch, not under the floor in the glide while the gust system is on, and the extra for the sink'))
    ch.append(_fn('ap/gs-throttle-target', IF(AND(EQ(P('ap/gs-on'), V(1)), EQ(P('ap/flare'), V(0))), MIN(V(GS_THR_MAX), M(V(GS_THR_PER_KT), MAX(V(0), D(M(V(-1), P('ap/speed-error-kt')), V(GS_THR_DEAD_KT))))), V(0)),
                  'the throttle the speed lost asks for (idle in the flare)'))
    ch.append(_fn('ap/gs-throttle-next', S(P('ap/gs-throttle'), MAX(M(V(-GS_THR_DOWN), P('simulation/dt')), MIN(M(V(GS_THR_UP), P('simulation/dt')), D(P('ap/gs-throttle-target'), P('ap/gs-throttle'))))),
                  'the gust system\'s throttle, rate limited', out='ap/gs-throttle'))
    ch.append(_fn('ap/gs-flare-extra-deg', IF(AND(EQ(P('ap/gs-on'), V(1)), EQ(P('ap/flare'), V(1))),
                                              MIN(V(GS_FLARE_MAX_DEG), M(V(GS_FLARE_K), MAX(V(0), D(D(V(0), S(P('velocities/h-dot-fps'), P('ap/flare-sink-wanted-fps'))), V(GS_FLARE_OK_FPS))))), V(0)),
                  'pitch more in the flare for the sink the spoilers cannot take'))
    # the gust alert: a monitor, not a control: it works with the system off. Under GS_H_FT in the landing, in the air, the speed lost or the sink beyond what the path (or the flare) asks, for a frame,
    # holds an alert for GS_ALERT_HOLD_S; the aircraft's alert list (onboard.py, onboard.nas) raises GUSTS OR WIND SHEAR ON THE FINAL while ap/gust-alert is 1
    sink_flare = S(P('velocities/h-dot-fps'), P('ap/flare-sink-wanted-fps'))
    ch.append(_fn('ap/gs-detect', IF(AND(EQ(P('ap/engaged'), V(1)), EQ(P('ap/manual'), V(0)), EQ(P('ap/land-mode'), V(1)), EQ(P('ap/rollout'), V(0)), EQ(P('ap/on-mains'), V(0)),
                                         LT(P('aero/wheel-height-ft'), V(GS_H_FT)),
                                         X('or', GT(M(V(-1), P('ap/speed-error-kt')), V(GS_ALERT_SPEED_KT)),
                                            AND(EQ(P('ap/flare'), V(0)), LT(P('ap/glide-sink-error-fps'), V(-GS_ALERT_SINK_FPS))),
                                            AND(EQ(P('ap/flare'), V(1)), LT(sink_flare, V(-GS_ALERT_SINK_FPS))))), V(1), V(0)),
                  'speed lost or sink beyond the path on the final, whatever the gust system is doing'))
    ch.append(_fn('ap/gs-detect-t-next', IF(EQ(P('ap/gs-detect'), V(1)), P('simulation/sim-time-sec'), P('ap/gs-detect-t')), 'the last time the gust monitor met its threshold', out='ap/gs-detect-t'))
    ch.append(_fn('ap/gust-alert', IF(LT(D(P('simulation/sim-time-sec'), P('ap/gs-detect-t')), V(GS_ALERT_HOLD_S)), V(1), V(0)), 'the gust alert: raised from the monitor and held GS_ALERT_HOLD_S'))
    return early, ch


def laws_file():
    props = ''.join('  <property value="%g">ap/%s</property>\n' % (v, k) for k, v in (
        ('engaged', 0), ('pitch-mode', 0), ('roll-mode', 0), ('thrust-mode', 0), ('theta-cmd-deg', 0), ('speed-cmd-kcas', 150),
        ('speed-schedule', 1), ('speed-offset-kcas', 0), ('alt-cmd-ft', 0), ('bank-cmd-deg', 0), ('heading-cmd-deg', 0),
        ('throttle-cmd', 0.5), ('gain-scale', 1), ('bias-pitch-deg', 0), ('bias-yaw-deg', 0), ('bias-throttle', 0),
        ('theta-latched-deg', 0), ('theta-delta-deg', 0), ('theta-speed-bias-deg', 0), ('land-mode', 0), ('ground-steer', 0), ('taxi-speed-kt', 0),
        ('spoiler-mode', 0), ('spoiler-cmd', 0), ('rwy-elev-ft', 0), ('leg-lat0-deg', 0), ('leg-lon0-deg', 0), ('leg-lat1-deg', 0.01),
        ('leg-lon1-deg', 0), ('rollout', 0), ('spoiler-base', 0.667), ('flare-height-ft', FLARE_HEIGHT), ('link-last-sec', 0), ('link-timeout-sec', 30), ('link-monitor', 0),
        ('link-lost', 0), ('manual', 0), ('direct-pitch-deg', 0), ('direct-roll-deg', 0), ('direct-yaw-deg', 0),
        ('next-lat-deg', 0), ('next-lon-deg', 0), ('next-valid', 0), ('turn-phase', 0), ('turn-done', 0), ('yaw-air-w', 1), ('rollout-w', 0), ('turn-ack', 0), ('decrab-w', 0),
        ('tk-on', 0), ('tk-done', 0), ('tx-on', 0), ('tx-fast', 15), ('tx-slow', 8), ('tx-bend-deg', 0), ('tx-last', 0), ('tx-stop', 1), ('ld-on', 0), ('ld-captured', 0),
        ('ci-on', 0), ('ci-lat', 0), ('ci-lon', 0), ('ci-radius-ft', 1000), ('ci-side', 1), ('ci-out-max', 30), ('ci-lead', 1),
        ('ga-on', 0), ('ga-h0-ft', 0), ('ga-smart', 0), ('ga-latch', 0), ('final-wide', 0), ('final-i-wide-deg', 0), ('final-ff', 0), ('final-ri', 0), ('final-aim', 0), ('final-aim-ft', 0), ('final-i-rate-deg', 0), ('final-ff-bank-deg', 0), ('ga-smart-active', 0), ('ga-theta-i-deg', 0), ('vt-on', 0), ('vt-sp-end', 0), ('v-sp-i', 0), ('vt-ft', 0), ('vt-path', 0), ('sp-ext', -1), ('vmode', 0), ('v-level-alt', 0), ('v-level-from', 0), ('v-level-span', LEVEL_GATE_FT), ('v-level-sp0', 0), ('gust-sys', 0), ('approach-add-kt', 0), ('approach-add-auto', 0), ('gsmini-on', 0), ('tower-hw-kt', 0), ('gs-gsmini-add', 0), ('gs-hw-live-kt', 0), ('approach-add-used', 0), ('gs-add-lat', 0), ('gs-on', 0), ('gs-throttle', 0), ('gs-detect', 0), ('gs-detect-t', -1000), ('gust-alert', 0), ('gs-flare-extra-deg', 0), ('gs-glide-extra-deg', 0), ('theta-speed-gs-deg', 0)))
    props += ''.join('  <property value="0">limits/%s</property>\n' % k for k in ('overstress', 'failed', 'reset'))
    ch = []
    # ---- part C: navigators and the link, ahead of everything that uses them
    ch += _navigators()
    ch.append(_fn('ap/link-age-sec', _op('difference', _p('simulation/sim-time-sec'), _p('ap/link-last-sec')), 'time since the last uplink'))
    ch.append('''    <switch name="ap/latch-link-lost">
      <description>the link is lost: set after the timeout while it is being watched, cleared only by switching the watch off</description>
      <default value="ap/link-lost"/>
      <test value="0">ap/link-monitor == 0</test>
      <test logic="AND" value="1">
        ap/link-monitor == 1
        ap/link-age-sec gt ap/link-timeout-sec
      </test>
      <output>ap/link-lost</output>
    </switch>''')
    # ---- manual mode (section 7): the stick, pedals and their dead band
    for nm, src in (('stick-pitch', 'fcs/elevator-cmd-norm'), ('stick-roll', 'fcs/aileron-cmd-norm'), ('pedal', 'fcs/rudder-cmd-norm')):
        ch.append(_fn('ap/' + nm, '        <quotient><difference>%s<max><min>%s%s</min>%s</max></difference>%s</quotient>' % (
            _p(src), _p(src), _v(STICK_DEAD), _v(-STICK_DEAD), _v(1 - STICK_DEAD)), 'with a dead band of %g; forward, right and nose right are positive' % STICK_DEAD,
            clip=('-1', '1')))
    ch.append(_fn('ap/protected', '        <eq>%s%s</eq>' % (_p('ap/manual'), _v(1)), '1 in the protected manual law'))
    # ---- schedules
    ch.append(_fn('ap/gain-q', _op('quotient', _v(50), '<max>%s%s</max>' % (_p('aero/qbar-psf'), _v(1))),
                  'gain schedule: control power goes with dynamic pressure', clip=('0.4', '2.5')))
    for n in ('theta', 'q', 'theta_i', 'phi', 'phi_i', 'p', 'r', 'beta', 'beta_i'):
        ch.append(_gain(n.replace('_', '-'), G['K_' + n]))
    ch.append(_fn('ap/schedule-mach', _table(SCHEDULE, 'engine/pressure-altitude-ft'), 'the scheduled Mach number above FL220'))
    ch.append(_fn('ap/schedule-kcas', '''        <ifthen>
          <lt>%s%s</lt>
          %s
          <product>%s<quotient>%s<max>%s%s</max></quotient></product>
        </ifthen>''' % (_p('engine/pressure-altitude-ft'), _v(SCHEDULE[1][0]), _v(SCHEDULE_KCAS), _p('velocities/vc-kts'),
                        _p('ap/schedule-mach'), _p('velocities/mach'), _v(0.05)),
                  'the scheduled speed as calibrated airspeed at this height: %g KCAS low down, the scheduled Mach above' % SCHEDULE_KCAS))
    ch.append('''    <switch name="ap/speed-target-kcas">
      <description>the commanded speed: the schedule less the operator's offset, or a commanded speed</description>
      <default value="ap/speed-cmd-kcas"/>
      <test value="ap/ga-speed-kcas">ap/ga-on == 1</test>
      <test value="ap/approach-keas">ap/land-mode == 1</test>
      <test value="ap/schedule-less-offset">ap/speed-schedule == 1</test>
    </switch>''')
    ch.insert(len(ch) - 1, _fn('ap/schedule-less-offset', _op('difference', _p('ap/schedule-kcas'), _p('ap/speed-offset-kcas'))))
    ch.insert(len(ch) - 1, _fn('ap/ga-speed-kcas', '        <min>%s<sum>%s%s<product>%s<max>%s<difference>%s%s</difference></max></product></sum></min>' % (
        _p('ap/schedule-less-offset'), _p('ap/approach-keas'), _v(GA_SPEED_ADD_KT), _v(GA_SPEED_RAMP), _v(0), _p('position/h-sl-ft'), _p('ap/ga-h0-ft')),
        'the speed of the go-around: the approach speed plus GA_SPEED_ADD_KT where it began, more with the height gained, at the schedule\'s at the most'))
    ch.append(_fn('ap/alpha-limit-deg', _table(ALPHA_LIMIT, 'velocities/mach'), 'angle-of-attack limit: the lift break less a margin'))
    ch.append(_fn('ap/bank-limit-deg', _table(BANK_LIMIT, 'engine/pressure-altitude-ft'), 'bank limit'))
    # ---- part B: the leg, in the WGS84 tangent plane at its end (the same ellipsoid as everything else: docs/PLAN.md, "One earth")
    lat, lon = 'position/lat-geod-deg', 'position/long-gc-deg'
    for _tag, _la, _lo in (('start', 'ap/leg-lat0-deg', 'ap/leg-lon0-deg'), ('end', 'ap/leg-lat1-deg', 'ap/leg-lon1-deg'), ('ac', lat, lon)):
        ch.extend(_g_point(_tag, _la, _lo))
    ch.extend(_g_enu('end', 'start', 'ap/leg-sn-ft', 'ap/leg-se-ft', 'leg\'s start, in the tangent plane at its end (the plane is at the end: the turn, the descent and the landing all happen there, so that is where it has to be exact; a plane at the start of a 200 nmi leg makes the distance to go 0.17 % short at its end)'))
    ch.append(_fn('ap/leg-dn-ft', _op('product', _v(-1), _p('ap/leg-sn-ft')), 'the leg\'s length north (the end less the start), ft'))
    ch.append(_fn('ap/leg-de-ft', _op('product', _v(-1), _p('ap/leg-se-ft')), 'the leg\'s length east, ft'))
    ch.append(_fn('ap/leg-length-ft', '        <max>%s<pow><sum><product>%s%s</product><product>%s%s</product></sum>%s</pow></max>' % (
        _v(1), _p('ap/leg-dn-ft'), _p('ap/leg-dn-ft'), _p('ap/leg-de-ft'), _p('ap/leg-de-ft'), _v(0.5))))
    ch.append(_fn('ap/leg-course-deg', '        <todegrees><atan2>%s%s</atan2></todegrees>' % (_p('ap/leg-de-ft'), _p('ap/leg-dn-ft')), 'the leg\'s course, east of north'))
    ch.extend(_g_enu('end', 'ac', 'ap/pos-n-ft', 'ap/pos-e-ft', 'aircraft, in the tangent plane at the leg\'s end'))
    ch.append(_fn('ap/leg-togo-ft', '        <difference>%s<quotient><sum><product>%s%s</product><product>%s%s</product></sum>%s</quotient></difference>' % (
        _v(0), _p('ap/pos-n-ft'), _p('ap/leg-dn-ft'), _p('ap/pos-e-ft'), _p('ap/leg-de-ft'), _p('ap/leg-length-ft')), 'distance to the end of the leg'))
    ch.append(_fn('ap/leg-xt-ft', '        <quotient><difference><product>%s%s</product><product>%s%s</product></difference>%s</quotient>' % (
        _p('ap/pos-e-ft'), _p('ap/leg-dn-ft'), _p('ap/pos-n-ft'), _p('ap/leg-de-ft'), _p('ap/leg-length-ft')), 'cross-track error, right of the leg positive'))
    ch.append(_fn('ap/ground-speed-kt', _op('product', _v(1 / 1.6878099), _p('velocities/vg-fps'))))
    ch.append(_fn('ap/ground-track-deg', '        <todegrees><atan2>%s%s</atan2></todegrees>' % (_p('velocities/v-east-fps'), _p('velocities/v-north-fps'))))
    # the ground track in the plane the leg is worked out in: the aircraft's velocity turned into the leg end's north and east (the local frames differ by the meridians' convergence, dlon x sin(lat))
    ch.append(_g_track('end', 'ac', 'ap/plane-track-deg', 'the ground track in the tangent plane at the leg\'s end, deg east of north'))

    def intercept(name, per_second, least):
        """the wanted course: the leg's, turned towards the leg by atan(cross-track / lookahead), 45 deg at most"""
        return _fn(name, '''        <difference>
          %s
          <max>%s<min>%s<todegrees><atan><quotient>%s<max>%s<product>%s%s</product></max></quotient></atan></todegrees></min></max>
        </difference>''' % (_p('ap/leg-course-deg'), _v(-45), _v(45), _p('ap/leg-xt-ft'), _v(least), _v(per_second), _p('velocities/vg-fps')))

    def wrapped(name, a, b, desc=''):
        """a less b, turned into -180 to 180 deg. Through sin and cos: JSBSim's <mod> works on whole numbers (found in a
        FlightGear takeoff record, 770 of 770 rows), which left this error in whole degrees, rounded down: nothing seen
        between 0 and 1 deg on one side, and the error read 0.5 deg low on average."""
        d = '<toradians><difference>%s%s</difference></toradians>' % (_p(a), _p(b))
        return _fn(name, '        <todegrees><atan2><sin>%s</sin><cos>%s</cos></atan2></todegrees>' % (d, d), desc)
    ch.append(intercept('ap/track-cmd-deg', 15.0, 3000.0))
    ch.append(wrapped('ap/track-error-deg', 'ap/track-cmd-deg', 'ap/plane-track-deg', 'wanted course less ground track'))
    ch.append(_g_track('end', 'ac', 'ap/plane-conv-deg', 'the angle the local north at the aircraft is turned from the north of the leg\'s plane, deg (the meridians\' convergence: 0.35 deg 12 nmi from the end at 60 N)', vel=(_v(1), _v(0), _v(0))))
    ch.append(_fn('ap/psi-plane-deg', _op('sum', _p('attitude/psi-deg'), _p('ap/plane-conv-deg')), 'the heading in the leg\'s plane (the leg\'s courses are in that plane; the heading is in the local frame)'))
    ch.append(intercept('ap/ground-course-cmd-deg', 4.0, 60.0))
    ch.append(wrapped('ap/ground-error-deg', 'ap/ground-course-cmd-deg', 'ap/psi-plane-deg', 'wanted course less heading, on the ground'))
    # ---- part B: landing phases
    ch.append(_fn('ap/on-mains', _op('sum', _p('gear/unit[1]/WOW'), _p('gear/unit[2]/WOW'))))
    ch.append('''    <switch name="ap/latch-rollout">
      <description>on the runway: set by weight on a main wheel while landing, cleared when landing is switched off</description>
      <default value="ap/rollout"/>
      <test value="0">ap/land-mode == 0</test>
      <test logic="AND" value="1">
        ap/land-mode == 1
        ap/on-mains gt 0
      </test>
      <output>ap/rollout</output>
    </switch>
    <fcs_function name="ap/flare-height-now-ft">
      <description>the wheel height at which the flare would start now: the design height, or the time to touchdown at the present sink if that is higher</description>
      <function>
        <max>
          <value>%g</value>
          <product><value>%g</value><max><value>0</value><difference><product><value>-1</value><property>velocities/h-dot-fps</property></product><value>%g</value></difference></max></product>
        </max>
      </function>
      <clipto><min>%g</min><max>150</max></clipto>
    </fcs_function>
    <switch name="ap/flare-height-ft">
      <description>the flare's height, followed until the flare starts and held from then</description>
      <default value="ap/flare-height-ft"/>
      <test value="ap/flare-height-now-ft">ap/flare == 0</test>
      <output>ap/flare-height-ft</output>
    </switch>
    <switch name="ap/flare">
      <default value="0"/>
      <test logic="AND" value="1">
        ap/land-mode == 1
        ap/rollout == 0
        aero/wheel-height-ft lt ap/flare-height-ft
      </test>
    </switch>''' % (FLARE_HEIGHT, FLARE_TTG, FLARE_SLACK, FLARE_HEIGHT))
    ch += _gust_picker()
    ch += _ga_smart()
    ch.append(_fn('ap/approach-keas', '        <sum><quotient><pow><quotient>%s%s</quotient>%s</pow>%s</quotient>%s</sum>' % (
        _p('inertia/weight-lbs'), _v(APPROACH_CL * WING_AREA * 0.5 * 0.0023769), _v(0.5), _v(1.6878099), _p('ap/approach-add-used')),
        'the speed for a lift coefficient of %g at this weight, and ap/approach-add-kt more (0: as it was; the gusty-wind addition of docs/PLAN.md, "Gusts: find out first")' % APPROACH_CL))
    # ---- latches
    ch.append(_latch('bias-pitch-deg', 'ctl/manual-pitch-deg', 'ruddervator angle at engagement'))
    ch.append(_latch('bias-yaw-deg', 'ctl/manual-yaw-deg', 'yaw command at engagement'))
    if not (THRUST_ENTRY_TABLE and LEVEL_THRUST_FF and path_thrust()):
        ch.append(_latch('bias-throttle', 'fcs/throttle-cmd-norm', 'throttle at engagement'))
    ch.append(_latch('bias-spoiler', 'ctl/spoiler-norm', 'spoiler position at engagement'))
    ch.append(_fn('ap/gamma-deg', '        <product>%s<quotient>%s<max>%s%s</max></quotient></product>' % (_v(57.29578), _p('velocities/h-dot-fps'), _v(100), _p('velocities/vt-fps')),
                  'the flight path angle, deg (small angles)'))
    ch.append(_latch('bias-gamma-deg', 'ap/gamma-deg', 'flight path angle at engagement'))
    if CFG_THRUST_FF:
        ch.append(_fn('ap/cl-now', '        <quotient>%s<product><max>%s%s</max>%s</product></quotient>' % (_p('inertia/weight-lbs'), _p('aero/qbar-psf'), _v(1), _p('metrics/Sw-sqft')),
                      'the lift coefficient the aircraft flies at (weight over dynamic pressure and wing area)', clip=('0.3', '1.5')))
        ch.append(_fn('ap/cfg-drag-deg', '        <product>%s<quotient><sum><product>%s%s</product><product>%s%s</product></sum>%s</quotient></product>' % (
            _v(57.29578 * CFG_INDUCED_X), _v(_cal_spoiler_cd()), _p('ctl/spoiler-norm'), _v(CFG_GEAR_CD), _p('ctl/gear-norm'), _p('ap/cl-now')),
            'the drag of the spoilers and the gear as a flight path angle, deg (drag coefficient over lift coefficient): what the thrust must give up or take on with the configuration'))
        ch.append(_latch('bias-cfg-deg', 'ap/cfg-drag-deg', 'configuration drag at engagement'))
    ch.append(_latch('theta-latched-deg', 'nav/pitch-deg', 'pitch attitude at engagement'))
    # ---- autopilot: the pitch attitude command
    ch.append(_fn('ap/speed-error-kt', _op('difference', _p('velocities/vc-kts'), _p('ap/speed-target-kcas')), 'fast is positive'))
    ch.append(_trigger('speed', 'ap/pitch-mode == 1', 'ap/ga-smart-active == 0'))          # the smarter go-around holds the pitch: the speed law's integral is held at nothing meanwhile (and its bias follows the command, below)
    # the integral holds still while the angle-of-attack limit is what keeps the speed up: the governor won't let
    # the nose rise, and an integral that went on asking would be wound up when the limit lets go (it was: the
    # first glide without the engine came down final 15 kt slow, on the speed floor)
    ch.append(_fn('ap/speed-error-i-kt', '''        <ifthen>
          <and><gt>%s%s</gt><lt><difference>%s%s</difference>%s</lt></and>
          %s
          %s
        </ifthen>''' % (_p('ap/speed-error-kt'), _v(0), _p('ap/alpha-limit-deg'), _p('aero/alpha-deg'), _v(0.3), _v(0), _p('ap/speed-error-kt'))))
    X_ = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
    ch.append(_pid('ap/theta-speed-i-deg', 'ap/speed-error-i-kt', 0.0, G['K_v_i'], 'speed', clip=('-20', '20')))
    # Entered from another attitude (the take-off's 7 deg at 100 ft), the loop's integral begins at nothing and its output
    # asks for the attitude latched at engagement: the nose came down from 9 deg to -1 and the speed ran on to 165 KEAS
    # before it came back. So the change the pitch command had on entry is carried into the loop: it follows the command
    # while another mode flies and holds from the frame this one takes over. Entered from a trim, the change is nil and
    # nothing is different.
    # Bumpless: the speed law's pitch is its bias + K_v * the speed error + the integral, and the bias followed the pitch command, so at the handover the law added K_v * the error to
    # it at once (the takeoff's handover at 100 ft, 6 kt under the climb speed: 3 deg down in a second and a half, Nz 0.73). The bias follows the pitch command less K_v * the error,
    # so that the law's first output is the pitch command it takes over from.
    ch.append(_fn('ap/theta-speed-entry-deg', '        <difference>%s<product>%s%s</product></difference>' % (_p('ap/theta-delta-deg'), _v(G['K_v']), _p('ap/speed-error-kt')),
                  'the bias the speed law starts from: the pitch command less what its proportional term will add'))
    ch.append('''    <switch name="ap/latch-theta-speed-bias">
      <description>the pitch command's change from the latched attitude, as it was when the speed mode took over</description>
      <default value="ap/theta-speed-bias-deg"/>
      <test value="%s">ap/pitch-mode ne 1</test>
      <test value="%s">ap/pitch-mode-prev ne 1</test>
      <test value="%s">ap/engaged == 0</test>
      <test value="%s">ap/ga-smart-active == 1</test>
      <output>ap/theta-speed-bias-deg</output>
    </switch>''' % (('ap/theta-speed-entry-deg',) * 4 if SPEED_BUMPLESS else ('ap/theta-delta-deg',) * 4))
    # the thrust the engine gave when the speed mode took over: followed in any other mode, held from the frame this one takes over (as the bias above)
    ch.append('''    <switch name="ap/latch-thrust-entry-lbf">
      <description>the engine thrust as it was when the speed mode took over</description>
      <default value="ap/thrust-entry-lbf"/>
      <test value="engine/thrust-lbf">ap/pitch-mode ne 1</test>
      <test value="engine/thrust-lbf">ap/engaged == 0</test>
      <output>ap/thrust-entry-lbf</output>
    </switch>''')
    ch.append(_fn('ap/theta-thrust-ff-deg', X_('product', _v(57.29578 * THRUST_PITCH_FF), X_('asin', X_('min', _v(0.9), X_('max', _v(-0.9), X_('quotient', X_('difference', _p('engine/thrust-lbf'), _p('ap/thrust-entry-lbf')),
                                                                                                                                           X_('max', _v(1000), _p('inertia/weight-lbs'))))))),
                  'the flight path angle the thrust gained since the speed mode took over makes, deg'))
    ch.append(_fn('ap/theta-speed-deg', '        <sum>%s<product>%s%s</product>%s%s</sum>' % (_p('ap/theta-speed-bias-deg'), _v(G['K_v']), _p('ap/speed-error-kt'), _p('ap/theta-speed-i-deg'), _p('ap/theta-thrust-ff-deg')),
                  clip=('-20', '20')))
    ch += _gust_system()[0]          # after the speed law, before the pitch mode's switch: with the system off the floor passes the law through with no frame of delay
    # the pitch mode of the frame before, for the bias above: the bias follows one frame into the mode, so that it is worked out with the speed error of the first frame the law is on (the
    # speed target can change in the same step as the mode: against the old target the bias carried a wrong correction, 13 deg of it in phase 7a's A10: a dive and 26 kt of speed)
    ch.append(_fn('ap/pitch-mode-prev-next', _p('ap/pitch-mode'), 'the pitch mode of the frame before', out='ap/pitch-mode-prev'))
    ch.append(_fn('ap/alt-error-ft', _op('difference', _p('ap/alt-cmd-ft'), _p('position/h-sl-ft')), clip=('-6000', '6000')))      # the capture's gate is further out than 1,500 ft for a fast climb (2,260 ft at 12,000 lb): the profile saw the clipped error and asked for less climb rate than there was
    if LEVEL_PROFILE and LEVEL_I_RATE_GATE:
        # The small integral runs within LEVEL_I_BAND_FT of the height whatever the climb rate, and out to LEVEL_I_FAR_FT while the aircraft is settled (under LEVEL_I_RATE_FPS): not while it
        # is closing on the height. In a capture from above the error was negative for 15 s and the integral wound the pitch down 1.4 deg: the aircraft sank more than the profile asked,
        # went 32 ft under the height and climbed back; and with it off outside 25 ft nothing took out the pitch a change of configuration (spoilers out in level flight) asks for:
        # the aircraft held 119 ft low (docs/PLAN.md, the box flight, 2026-11-14)
        e_ = '<property>ap/alt-error-ft</property>'
        ch.append(_fn('ap/alt-i-enable', '''        <ifthen>
          <or>
            <lt><abs>%s</abs><value>%g</value></lt>
            <and><lt><abs>%s</abs><value>%g</value></lt><lt><abs><property>velocities/h-dot-fps</property></abs><value>%g</value></lt></and>
          </or>
          <value>1</value>
          <value>0</value>
        </ifthen>''' % (e_, LEVEL_I_BAND_FT, e_, LEVEL_I_FAR_FT, LEVEL_I_RATE_FPS), 'the altitude mode\'s integral runs: near the height, or settled within LEVEL_I_FAR_FT of it'))
        ch.append(_trigger('alt', 'ap/pitch-mode == 2', 'ap/alt-i-enable == 1'))
    else:
        ch.append(_trigger('alt', 'ap/pitch-mode == 2', *(('ap/alt-error-ft lt %g' % LEVEL_I_BAND_FT, 'ap/alt-error-ft gt %g' % -LEVEL_I_BAND_FT) if LEVEL_PROFILE else ())))
    if LEVEL_PROFILE:
        # The linear law (K_h * error - K_hd * climb rate) asks for a climb rate of K_h / K_hd * error: 0.2 * the error, an exponential approach of 5 s, which at a climb rate of
        # 95 ft/s asks for 0.6 g at 475 ft. The capture's climb rate is the less of that and the one a constant deceleration takes to nothing at the height: sqrt(2 a error).
        X_ = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
        err = _p('ap/alt-error-ft')
        perr = err
        if LEVEL_RESPONSE_S:
            hd = _p('velocities/h-dot-fps')
            ch.append(_fn('ap/alt-error-lead-ft', X_('ifthen', X_('gt', err, _v(0)),
                                                       X_('max', _v(0), X_('difference', err, X_('product', _v(LEVEL_RESPONSE_S), X_('max', _v(0), hd)))),
                                                       X_('min', _v(0), X_('sum', err, X_('product', _v(LEVEL_RESPONSE_S), X_('max', _v(0), X_('product', _v(-1), hd)))))),
                          'the height error the profile is worked out for: where the aircraft will be after the response time (it overshot the height by 10 to 40 ft, still climbing at the rate the command had left behind)'))
            perr = _p('ap/alt-error-lead-ft')
        sign = X_('ifthen', X_('gt', perr, _v(0)), _v(1), _v(-1))
        vlin = X_('product', _v(G['K_h'] / G['K_hd']), perr)
        vcon = X_('product', sign, X_('sqrt', X_('product', _v(2.0 * LEVEL_A_FPS2), X_('abs', perr))))
        if LEVEL_SOFTMIN:
            # the soft minimum of the two, v1 v2 / sqrt(v1^2 + v2^2): the profile's deceleration is then a (1 - 1 / (u + 1)^2), u = K^2 error / 2a (K the linear law's gain): from nothing
            # and never over a, where the plain minimum jumps from a to 2a at the crossover
            v1, v2 = X_('abs', vlin), X_('abs', vcon)
            soft = X_('quotient', X_('product', vlin, X_('abs', vcon)), X_('sqrt', X_('sum', X_('product', v1, v1), X_('product', v2, v2), _v(1e-6))))
            if LEVEL_CAP_RATE:
                # never more rate than the aircraft's own table says the thrust holds (ap/climb-rate-max-fps going up, ap/descent-rate-idle-fps going down, at least LEVEL_CAP_MIN_FPS): a capture
                # begun with the profile above that (a descent handed over 228 ft high at 11 ft/s, the profile asking 27) took the sink to 23 ft/s with the thrust at idle and the aircraft went
                # 288 ft through the height and climbed back (docs/PLAN.md, the box flight, 2026-11-14)
                capv = X_('max', _v(LEVEL_CAP_MIN_FPS), X_('ifthen', X_('gt', err, _v(0)), _p('ap/climb-rate-max-fps'), _p('ap/descent-rate-idle-fps')))
                soft = X_('product', X_('ifthen', X_('gt', err, _v(0)), _v(1), _v(-1)), X_('min', X_('abs', soft), capv))
            ch.append(_fn('ap/alt-vs-target-fps', soft, 'the climb rate the altitude capture should have at this height error: the soft minimum of the linear law\'s and the constant deceleration\'s (%g ft/s^2), no more than the thrust holds' % LEVEL_A_FPS2))
        else:
            ch.append(_fn('ap/alt-vs-target-fps', X_('ifthen', X_('gt', X_('abs', vlin), X_('abs', vcon)), vcon, vlin),
                          'the climb rate the altitude capture should have at this height error: the linear law\'s, or the constant deceleration\'s (%g ft/s^2) where that is less' % LEVEL_A_FPS2))
        if LEVEL_FOLLOW:
            # Following the climb rate there is while another mode flies, and the profile at LEVEL_A_FPS2 at most once this one does: the command begins where the aircraft is
            # Towards the height: the climb rate there is while another mode flies (its sign taken so that towards the height is positive), the profile's once this one does. A lag, and an
            # acceleration limit on speeding up only: from rest the command rises at LEVEL_A_FPS2 (a climb under the profile begins at 0.08 g, not at 0.7 g), while slowing down keeps the
            # authority to catch up when the aircraft is late (the profile asks for no more than LEVEL_A_FPS2 of it).
            # The state is the signed climb rate asked for, and the direction (the sign of the error) is held within LEVEL_DIR_BAND_FT of the height, so that crossing it is not a change of
            # frame: the state's sign used to follow the error's, and an aircraft crossing the height while the lagged command was still +14 ft/s got -14 at once (a dip of 0.36 g).
            # The command is the lagged profile; its growth towards the height is limited to LEVEL_A_FPS2 (from rest it rises at 0.08 g, not 0.7 g), its fall is not (the authority to
            # catch up when the aircraft is late, and to turn round after crossing). While another mode flies it is the climb rate there is.
            dt_ = _p('simulation/dt')
            ch.append(_fn('ap/alt-dir-next', X_('ifthen', X_('or', X_('nq', _p('ap/pitch-mode'), _v(2)), X_('eq', _p('ap/engaged'), _v(0)), X_('gt', X_('abs', err), _v(LEVEL_DIR_BAND_FT))),
                                                  X_('ifthen', X_('gt', err, _v(0)), _v(1), _v(-1)), _p('ap/alt-dir')),
                          'the direction the height is in (+1 above), held within %g ft of it' % LEVEL_DIR_BAND_FT, out='ap/alt-dir'))
            step = X_('product', X_('difference', _p('ap/alt-vs-target-fps'), _p('ap/alt-vs-cmd-fps')), dt_, _v(1.0 / LEVEL_LAG_S))
            lim = X_('product', _v(LEVEL_GROW_FPS2), dt_)
            ch.append(_fn('ap/alt-vs-next', X_('ifthen', X_('and', X_('eq', _p('ap/pitch-mode'), _v(2)), X_('eq', _p('ap/engaged'), _v(1))),
                                                X_('sum', _p('ap/alt-vs-cmd-fps'), X_('ifthen', X_('gt', _p('ap/alt-dir'), _v(0)), X_('min', step, lim), X_('max', step, X_('product', _v(-1), lim)))),
                                                _p('velocities/h-dot-fps')),
                          'the climb rate asked for, signed: the climb rate there is while another mode flies; then the profile lagged by %g s, its growth towards the height limited to %g ft/s^2' % (LEVEL_LAG_S, LEVEL_A_FPS2),
                          out='ap/alt-vs-cmd-fps'))
        else:
            ch.append(_fn('ap/alt-vs-cmd-fps', _p('ap/alt-vs-target-fps')))
        offset_to_i = X_('lt', _p('ap/alt-dir'), _v(0)) if LEVEL_OFFSET_TO_I == 2 else X_('gt', _v(1), _v(0))
        if LEVEL_OFFSET_TO_I == 2 and LEVEL_OFFSET_SETTLED:
            # a state: whether the aircraft was settled at the height (within LEVEL_I_BAND_FT of it, climbing or sinking less than LEVEL_I_RATE_FPS) in the last frame before the altitude mode took
            # the pitch, held from then on. A mode that arrives at the height settled is a hold: the pitch the aircraft holds beyond its path angle is the level flight's angle of attack, and
            # letting it go (it is for a climb capture, which was tuned with it let go) cost the height: 95 ft and 8 ft/s of sink at the 65,000 ft capture, where the thrust cannot win the energy back
            ch.append(_fn('ap/alt-settled-next', X_('ifthen', X_('and', X_('eq', _p('ap/pitch-mode'), _v(2)), X_('eq', _p('ap/engaged'), _v(1))), _p('ap/alt-settled'),
                                                   X_('ifthen', X_('and', X_('lt', X_('abs', err), _v(LEVEL_I_BAND_FT)), X_('lt', X_('abs', _p('velocities/h-dot-fps')), _v(LEVEL_I_RATE_FPS))), _v(1), _v(0))),
                          'the aircraft was settled at the height when the altitude mode took the pitch', out='ap/alt-settled'))
            offset_to_i = X_('or', offset_to_i, X_('eq', _p('ap/alt-settled'), _v(1)))
        if LEVEL_I_HOLD and LEVEL_I_RATE_GATE:
            # a state: the integral of the height error runs while the gate is open, is held while it is shut, and is zero while the altitude mode is not flying
            ch.append(_fn('ap/theta-alt-i-next', X_('ifthen', X_('and', X_('eq', _p('ap/engaged'), _v(1)), X_('eq', _p('ap/pitch-mode'), _v(2))),
                                                   X_('max', _v(-12), X_('min', _v(12), X_('sum', _p('ap/theta-alt-i-deg'),
                                                      X_('ifthen', X_('eq', _p('ap/alt-i-enable'), _v(1)), X_('product', _v(G['K_h_i'] * LEVEL_I_GAIN_X), err, _p('simulation/dt')), _v(0)),
                                                      *((X_('ifthen', offset_to_i,
                                                            X_('product', _p('ap/theta-alt-offset-deg'), _p('simulation/dt'), _v(1.0 / LEVEL_OFFSET_TC)), _v(0)),) if LEVEL_OFFSET_TO_I else ())))),
                                                   _v(0)),
                          'the small integral of the height error, deg: runs while the gate is open, held (not reset) while it is shut, zero while the altitude mode is not flying', out='ap/theta-alt-i-deg'))
        else:
            ch.append(_pid('ap/theta-alt-i-deg', 'ap/alt-error-ft', 0.0, G['K_h_i'] * LEVEL_I_GAIN_X, 'alt', clip=('-12', '12')))
        ff = X_('product', _v(57.29578 * LEVEL_FF), X_('quotient', _p('ap/alt-vs-cmd-fps'), X_('max', _v(100), _p('velocities/vt-fps'))))      # the flight path angle asked for, deg (small angles)
        # the attitude the aircraft holds beyond the path angle (its pitch less the pitch latched at engagement less the path angle): followed while another mode flies, then let go
        sp_ff = X_('product', _v(LEVEL_SPOILER_PITCH), X_('difference', _p('ctl/spoiler-norm'), _p('ap/bias-spoiler')))          # the pitch the spoilers' lift loss asks for beyond what they asked at engagement, deg (engaged in the approach trim with them out there is no step)
        pt_ = path_thrust()
        alpha_ff = X_('difference', _p('ap/alpha-level-deg'), _p('ap/theta-latched-deg')) if (LEVEL_ALPHA_FF and LEVEL_THRUST_FF and pt_ and 'grid_alpha_level_deg' in pt_) else None
        if alpha_ff is not None:
            # the table's angle is the clean aircraft's: the spoilers' share is the whole of it, not what it is beyond the position at engagement (that cancelled against the attitude latched there, which
            # the approach trim's spoilers are in; with the angle in the command an engagement in the approach trim stepped the pitch by 1.4 deg: phase 7a A1)
            sp_ff = _p('ap/alpha-spoiler-deg') if 'grid_alpha_spoiler_deg' in pt_ else X_('product', _v(LEVEL_SPOILER_PITCH), _p('ctl/spoiler-norm'))
            # (with the table: the spoilers' effect on the level angle by their position, the lift coefficient and Mach number, not a constant per unit: 3.1 deg at 2/3 and CL 0.3, 3.7 at 0.65, 5.5 at 1.0)
        alpha_ff_all = (alpha_ff,) if alpha_ff is not None else ()
        # (the pitch the level flight needs beyond the path angle, from the latched attitude: alpha_ff; the offset the other mode holds is what it holds beyond that, so that the command does not step at the handover)
        ch.append(_fn('ap/theta-alt-offset-in-deg', X_('ifthen', X_('eq', _p('ap/pitch-mode'), _v(2)), _v(0),
                      X_('difference', _p('ap/theta-delta-deg'), X_('product', _v(57.29578), X_('quotient', _p('velocities/h-dot-fps'), X_('max', _v(100), _p('velocities/vt-fps')))),
                         *((sp_ff,) if LEVEL_SPOILER_PITCH else ()), *alpha_ff_all)),
                      'the pitch beyond the path angle that another mode is holding; 0 once the altitude mode has the pitch'))
        ch.append('''    <lag_filter name="ap/theta-alt-offset-deg">
      <description>that pitch, followed while another mode flies and let go over %g s from the frame the altitude mode takes the pitch</description>
      <input>ap/theta-alt-offset-in-deg</input>
      <c1>%g</c1>
    </lag_filter>''' % (LEVEL_OFFSET_TC, 1.0 / LEVEL_OFFSET_TC))
        # the bank the pitch is fed forward for is the bank LEVEL_BANK_LEAD_S from now (bank plus its rate times the lead): the pitch follows with the response time, so with the bank itself the load factor
        # came first and the aircraft sank 6 ft rolling in, rose 8 ft rolling out and sank 6 ft again as the integral unwound (the user: "turns are ringing between 5490 and 5510")
        phi_ff = X_('sum', _p('attitude/phi-deg'), X_('product', _v(LEVEL_BANK_LEAD_S), X_('todegrees', _p('velocities/phidot-rad_sec')))) if LEVEL_BANK_LEAD_S else _p('attitude/phi-deg')
        sec_less_1 = X_('max', _v(0), X_('difference', X_('quotient', _v(1), X_('max', _v(0.5), X_('cos', X_('toradians', phi_ff)))), _v(1)))
        if LEVEL_BANK_PHYS:
            # the extra angle of attack a bank asks for: the extra lift is (sec bank - 1) of the weight, a lift coefficient of (sec - 1) x the one flown (ap/cl-now: the total, the spoilers' dump
            # included, which does not scale with the bank), over the lift curve's slope (0.117 a degree below 2 deg of angle of attack). The old form, the angle of attack over the zero-lift
            # angle, grows with the angle of attack: 0.8 deg wanted in the landing configuration where 0.45 does it (the aircraft climbed 1.3 ft/s in the turn); the lift curve's flattening at the
            # approach's angle of attack (0.079 a degree) asked for 50 % more than that (+8 ft): the same slope in both configurations is what the two turns want (docs/PLAN.md)
            bank_ff = X_('product', _v(LEVEL_BANK_FF), sec_less_1, X_('quotient', _p('ap/cl-now'), _v(LEVEL_BANK_CLALPHA))) if LEVEL_BANK_FF else _v(0)
        else:
            bank_ff = X_('product', _v(LEVEL_BANK_FF), sec_less_1, X_('max', _v(0), X_('difference', _p('aero/alpha-deg'), _v(ALPHA_ZERO_DEG)))) if LEVEL_BANK_FF else _v(0)
        ch.append(_fn('ap/theta-alt-deg', X_('sum', ff, X_('product', _v(G['K_hd']), X_('difference', _p('ap/alt-vs-cmd-fps'), _p('velocities/h-dot-fps'))), _p('ap/theta-alt-i-deg'), _p('ap/theta-alt-offset-deg'), bank_ff, *((sp_ff,) if LEVEL_SPOILER_PITCH else ()), *(((alpha_ff_all[0], *alpha_ff_all[1:]) if alpha_ff_all else ()))),
                      'pitch attitude for the climb rate asked for, and the small integral of the height error (the old law\'s clip of 12 deg held a climb of 17 deg to 12 at the handover: a 0.5 g unload)', clip=('-%g' % LEVEL_THETA_MAX, '%g' % LEVEL_THETA_MAX)))
    else:
        ch.append(_pid('ap/theta-alt-pi-deg', 'ap/alt-error-ft', G['K_h'], G['K_h_i'], 'alt', clip=('-12', '12')))
        ch.append(_fn('ap/theta-alt-deg', _op('difference', _p('ap/theta-alt-pi-deg'), '<product>%s%s</product>' % (_v(G['K_hd']), _p('velocities/h-dot-fps')))))
    ch.append('''    <switch name="ap/theta-mode-deg">
      <description>pitch attitude asked for by the mode, from the attitude latched at engagement</description>
      <default value="ap/theta-cmd-less-latched"/>
      <test value="ap/theta-follow-deg">ap/manual == 2</test>
      <test value="ap/theta-manual-deg">ap/manual == 1</test>
      <test value="ap/theta-flare-deg">ap/flare == 1</test>
      <test value="ap/theta-takeoff-deg">ap/pitch-mode == 3</test>
      <test value="ap/theta-ga-deg">ap/ga-smart-active == 1</test>
      <test value="ap/theta-speed-gs-deg">ap/pitch-mode == 1</test>
      <test value="ap/theta-alt-deg">ap/pitch-mode == 2</test>
    </switch>''')
    ch.insert(len(ch) - 1, _fn('ap/theta-manual-deg', '        <difference>%s<product>%s%s</product></difference>' % (
        _p('ap/theta-delta-deg'), '<min>%s<quotient>%s<max>%s%s</max></quotient></min>' % (
            _v(MANUAL_PITCH_RATE / 2.0), _v(0.5 * MANUAL_NZ * 32.174 * 57.29578), _v(100), _p('velocities/vt-fps')), _p('ap/stick-pitch')),
        'by hand: the stick asks for a rate, %g deg/s at full travel or what gives %g g more or less than 1, whichever is less '
        '(the governor moves at twice the difference)' % (MANUAL_PITCH_RATE, MANUAL_NZ)))
    ch.insert(len(ch) - 1, _fn('ap/theta-follow-deg', _op('difference', _p('nav/pitch-deg'), _p('ap/theta-latched-deg')),
                               'in the direct law the command follows the aircraft, so that coming back is bumpless'))
    ch.insert(len(ch) - 1, _fn('ap/theta-cmd-less-latched', _op('difference', _p('ap/theta-cmd-deg'), _p('ap/theta-latched-deg'))))
    ch.insert(len(ch) - 1, _fn('ap/theta-flare-deg', _op('sum', _op('difference', _v(FLARE_PITCH), _p('ap/theta-latched-deg')), _p('ap/gs-flare-extra-deg')), 'the flare\'s pitch attitude, and the gust system\'s extra'))
    ch.insert(len(ch) - 1, _fn('ap/theta-takeoff-deg', '''        <ifthen>
          <or><ge>%s%s</ge><gt>%s%s</gt></or>
          <difference>%s%s</difference>
          %s
        </ifthen>''' % (_p('velocities/vc-kts'), _v(ROTATE_KIAS), _p('aero/wheel-height-ft'), _v(3), _v(ROTATE_PITCH), _p('ap/theta-latched-deg'), _v(0)),
                                 'takeoff: the attitude on the ground until %g KIAS, then %g deg' % (ROTATE_KIAS, ROTATE_PITCH)))
    # ---- the pitch command governor: the command is a state that moves towards what the mode asks at 2 deg/s at
    # most, and is pulled down, whatever the mode asks, while the angle of attack is over its limit or the speed is
    # under its floor. Being a rate, it has nothing to wind up and nothing to release with a jump.
    # by hand the stick can hold the nose where the speed runs away from it, so there the protections look ahead:
    # the angle of attack 2 s on at its present rate, the speed 8 s on at its present acceleration
    glide_lead = ''
    if GLIDE_ALPHA_LEAD_S:
        glide_lead = '<product>%s%s%s%s<max>%s%s</max></product>' % (_p('ap/land-mode'), '<difference>%s%s</difference>' % (_v(1), _p('ap/flare')), _v(GLIDE_ALPHA_LEAD_S * 57.29578), '', _v(0), _p('aero/alphadot-rad_sec'))
    ch.append(_fn('ap/alpha-ahead-deg', '        <sum>%s<product>%s%s%s%s</product>%s</sum>' % (
        _p('aero/alpha-deg'), _p('ap/protected'), _v(LEAD_ALPHA), _v(57.29578), _p('aero/alphadot-rad_sec'), glide_lead), 'angle of attack, looked ahead by hand, and on a rising angle in the glide'))
    ch.append(_fn('ap/speed-ahead', '        <sum>%s<product>%s%s<quotient>%s<max>%s%s</max></quotient></product></sum>' % (
        _v(1), _p('ap/protected'), _v(LEAD_SPEED), _p('accelerations/udot-ft_sec2'), _v(100), _p('velocities/vt-fps')),
        'the factor on speed and Mach number when looked ahead by hand', clip=('0.8', '1.5')))
    ch.append(_fn('ap/alpha-margin-deg', _op('difference', _p('ap/alpha-limit-deg'), _p('ap/alpha-ahead-deg')), 'room under the angle-of-attack limit'))
    ch.append(_fn('ap/speed-margin-kt', '''        <ifthen>
          <or><gt>%s%s</gt><ge>%s%s</ge></or>
          %s
          <difference>%s<difference>%s%s</difference></difference>
        </ifthen>''' % (_p('ap/on-mains'), _v(0), _p('ap/manual'), _v(1), _v(50), _p('velocities/vc-kts'), _p('ap/speed-target-kcas'), _v(15)),
                  'room above the lowest speed allowed: 15 kt under the commanded speed. Not on the ground: a takeoff starts from rest'))
    ch.append(_fn('ap/protect-fast-deg', '        <sum><product>%s<max>%s<difference>%s%s</difference></max></product><product>%s<max>%s<difference>%s%s</difference></max></product></sum>' % (
        _v(200.0), _v(0), '<product>%s%s</product>' % (_p('velocities/mach'), _p('ap/speed-ahead')), _v(0.63),
        _v(0.3), _v(0), '<product>%s%s</product>' % (_p('velocities/vc-kts'), _p('ap/speed-ahead')), _v(FAST_KCAS)), 'nose up above Mach 0.63 or %g KCAS' % FAST_KCAS))
    # The mode's own pitch rate, shaped (PITCH_ENTRY): the attitude error's rate (2 per second, 3 deg/s at most) is stopped on a constant deceleration profile, and it builds up (more up or more down) by
    # no more than the pitch acceleration that changes the load factor at PITCH_NZ_PER_S. A climb entered at full thrust asked 3 deg/s at once and pulled 1.56 g, a step of 0.15 g in half a second.
    # The pitch acceleration is in deg/s^2 and goes with 1 / true airspeed: the load factor is V q / g. The protections stay in the minimum below and act at once.
    X_ = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
    ch.append(_fn('ap/theta-accel-deg_sec2', X_('product', _v(PITCH_NZ_PER_S * 32.174 * 57.29578), X_('quotient', _v(1), X_('max', _v(100), _p('velocities/vt-fps')))),
                  'the pitch acceleration that changes the load factor at %g g per second, deg/s^2' % PITCH_NZ_PER_S))
    err_t = X_('difference', X_('min', _v(18), X_('max', _v(-16), X_('sum', _p('ap/theta-mode-deg'), _p('ap/protect-fast-deg')))), _p('ap/theta-delta-deg'))
    ch.append(_fn('ap/theta-err-mode-deg', err_t, 'the attitude error the mode asks to remove: to what it asks within the governor\'s limits (-16 to +18 deg), so that the profile stops there and not against the limit'))
    lin = X_('product', _v(2.0), _p('ap/theta-err-mode-deg'))
    cst = X_('product', X_('ifthen', X_('gt', _p('ap/theta-err-mode-deg'), _v(0)), _v(1), _v(-1)),
             X_('sqrt', X_('product', _v(2.0), _p('ap/theta-accel-deg_sec2'), X_('abs', _p('ap/theta-err-mode-deg')))))
    soft = X_('quotient', X_('product', lin, cst), X_('max', _v(1e-6), X_('sqrt', X_('sum', X_('pow', lin, _v(2)), X_('pow', cst, _v(2))))))
    ch.append(_fn('ap/theta-rate-profile-deg_sec', soft, 'the pitch rate that the constant deceleration can stop at the attitude asked for, the less of it and of the linear law (2 per second)', clip=('-3', '3')))
    hi = X_('sum', X_('max', _p('ap/theta-rate-mode-deg_sec'), _v(0)), X_('product', _p('ap/theta-accel-deg_sec2'), _p('simulation/dt')))
    lo = X_('difference', X_('min', _p('ap/theta-rate-mode-deg_sec'), _v(0)), X_('product', _p('ap/theta-accel-deg_sec2'), _p('simulation/dt')))
    shaped = X_('max', lo, X_('min', hi, _p('ap/theta-rate-profile-deg_sec')))
    plain = X_('min', _v(3), X_('max', _v(-3), X_('product', _v(2.0), _p('ap/theta-err-mode-deg'))))
    ch.append(_fn('ap/theta-rate-mode-next', X_('ifthen', X_('and', X_('eq', _p('ap/pitch-mode'), _v(1)), X_('eq', _p('ap/land-mode'), _v(0)), X_('eq', _p('ap/on-mains'), _v(0)),
                                                         X_('eq', _p('ap/manual'), _v(0)), X_('eq', _v(PITCH_ENTRY), _v(1))), shaped, plain),
                  'the mode\'s pitch rate: shaped in pitch mode 1 in the air, as it was elsewhere', out='ap/theta-rate-mode-deg_sec'))
    ch.append(_fn('ap/theta-rate-deg_sec', '''        <max>
          <max>%s<product>%s<difference>%s%s</difference></product></max>
          <min>
            <product>%s<difference>%s%s</difference></product>
            %s
            <product>%s%s</product>
            <product>%s%s</product>
            <product>%s%s</product>
          </min>
        </max>''' % (_v(-6), _v(10), _v(-16), _p('ap/theta-delta-deg'), _v(10), _v(18), _p('ap/theta-delta-deg'),
                     _p('ap/theta-rate-mode-deg_sec'),
                     _v(G['K_alpha']), _p('ap/alpha-margin-deg'), '<sum>%s<product>%s%s</product></sum>' % (_v(G['K_alpha']), _v(2 * G['K_alpha']), _p('ap/protected')), _p('ap/alpha-margin-deg'), _v(G['K_slow']), _p('ap/speed-margin-kt')),
                  'how fast the pitch command moves: towards the mode\'s, or down for angle of attack or speed, whichever is lowest; and never past -16 or +18 deg (the integrator behind it has no limit of its own)'))
    ch.append(_trigger('governor'))
    ch.append('''    <pid name="ap/theta-governor">
      <description>the pitch command, as a change from the attitude latched at engagement</description>
      <input>ap/theta-rate-deg_sec</input>
      <kp>0</kp><ki>1</ki><kd>0</kd>
      <trigger>ap/trig-governor</trigger>
      <clipto><min>-16</min><max>18</max></clipto>
      <output>ap/theta-delta-deg</output>
    </pid>''')
    ch.append(_fn('ap/protect-alpha-deg', '        <product>%s<min>%s%s</min></product>' % (_v(2.0), _v(0), _p('ap/alpha-margin-deg')),
                  'a direct push down in proportion to the angle of attack over its limit, ahead of the governor'))
    # ---- basic law: pitch
    ch.append(_fn('ap/theta-error-deg', '        <difference>%s<sum>%s%s%s</sum></difference>' % (
        _p('nav/pitch-deg'), _p('ap/theta-latched-deg'), _p('ap/theta-delta-deg'), _p('ap/protect-alpha-deg')), 'nose high is positive'))
    # the pitch integral runs in the air, and on the ground only from 5 kt under the rotation speed: left running
    # through a taxi it winds up against the nose wheel and then holds the nose down at rotation (it did: the first
    # mission left the ground at 249 kt)
    ch.append('''    <switch name="ap/trig-pitch">
      <default value="-1"/>
      <test logic="AND" value="0">
        ap/engaged == 1
        ap/on-mains == 0
      </test>
      <test logic="AND" value="0">
        ap/engaged == 1
        velocities/vc-kts ge %g
        ap/rollout == 0
      </test>
    </switch>''' % (ROTATE_KIAS - 5.0))
    ch.append(_pid('ap/pitch-pi-deg', 'ap/theta-error-deg', 'ap/k-theta', 'ap/k-theta-i', 'pitch', clip=('-25', '25')))
    kq_pitch = _p('ap/k-q')
    if PITCH_Q_TAKEOFF_X != 1:
        # the rate damper is stronger in the takeoff mode (pitch mode 3): the nose gear needs about -13 deg of ruddervator to unload at 135 kt and about -6.6 deg is enough once the nose is free, so the surplus
        # rotated the aircraft at 7 deg/s into 1.9 deg of overshoot and 1.5 g at lift-off; while the nose is pinned the rate is zero and the damper asks for nothing, so the breakaway is not delayed
        kq_pitch = '<ifthen><eq>%s%s</eq><product>%s%s</product>%s</ifthen>' % (_p('ap/pitch-mode'), _v(3), _p('ap/k-q'), _v(PITCH_Q_TAKEOFF_X), _p('ap/k-q'))
    ch.append(_fn('ap/pitch-law-deg', '        <sum>%s%s<product>%s%s%s</product></sum>' % (
        _p('ap/bias-pitch-deg'), _p('ap/pitch-pi-deg'), kq_pitch, _v(57.29578), _p('velocities/q-rad_sec')),
        'ruddervators together, trailing edge down positive', clip=('-20', '20')))
    if ROLLOUT_NOSE_BLEND_S:
        # the nose-down of the rollout comes in as a blend over ROLLOUT_NOSE_BLEND_S, the pitch law (with its rate damper) flying the derotation meanwhile: at once it was a step of 4.7 deg of
        # ruddervator in a quarter second on top of the fall onto the nose wheel, a pitch rate of -14 deg/s, and a ramp from the old value threw away what the damper asked as the nose fell
        ch.append(_fn('ap/rollout-w-next', '        <ifthen><and><eq>%s%s</eq><eq>%s%s</eq></and><min>%s<sum>%s<product>%s%s</product></sum></min>%s</ifthen>' % (
            _p('ap/rollout'), _v(1), _p('ap/manual'), _v(0), _v(1), _p('ap/rollout-w'), _p('simulation/dt'), _v(1.0 / ROLLOUT_NOSE_BLEND_S), _v(0)),
            'the weight of the rollout\'s nose-down: 0 until the rollout, then up to 1 over ROLLOUT_NOSE_BLEND_S', out='ap/rollout-w'))
        ch.append(_fn('ap/rollout-nose-deg', '        <sum>%s<product>%s<difference>%s%s</difference></product></sum>' % (
            _p('ap/pitch-law-deg'), _p('ap/rollout-w'), _v(3), _p('ap/pitch-law-deg')), 'the pitch law with 3 deg of nose-down blended in by the rollout\'s weight'))
    ch.append('''    <switch name="ap/pitch-out-deg">
      <description>on the runway after landing: 3 deg nose-down</description>
      <default value="ap/pitch-law-deg"/>
      <test value="ap/pitch-direct-deg">ap/manual == 2</test>
      <test logic="AND" value="%s">
        ap/rollout == 1
        ap/manual == 0
      </test>
    </switch>''' % ('ap/rollout-nose-deg' if ROLLOUT_NOSE_BLEND_S else '3'))
    ch.insert(len(ch) - 1, _direct_latch('pitch', 'ap/pitch-law-deg'))
    ch.insert(len(ch) - 1, _fn('ap/pitch-direct-deg', '        <sum>%s<product>%s%s</product><product>%s%s%s</product></sum>' % (
        _p('ap/direct-pitch-deg'), _v(DIRECT['pitch']), _p('ap/stick-pitch'), _p('ap/k-q'), _v(57.29578), _p('velocities/q-rad_sec')),
        'direct law: the angle on entry, the stick, and pitch-rate damping', clip=('-20', '20')))
    # ---- basic law: roll
    ch.append(_fn('ap/heading-error-deg', '''        <difference>
          <mod><sum><difference>%s%s</difference>%s</sum>%s</mod>
          %s
        </difference>''' % (_p('ap/heading-cmd-deg'), _p('attitude/psi-deg'), _v(540), _v(360), _v(180)), 'right of the nose is positive'))
    ch.append(_fn('ap/bank-heading-deg', _op('product', _v(G['K_psi']), _p('ap/heading-error-deg'), '<quotient>%s%s</quotient>' % (_p('velocities/vt-fps'), _v(600)))))
    ch.append(_fn('ap/bank-track-deg', _op('product', _v(G['K_psi']), _p('ap/track-error-deg'), '<quotient>%s%s</quotient>' % (_p('velocities/vt-fps'), _v(600)))))
    # ---- the turn onto the next leg, the aircraft's own. The manager gives the next waypoint (ap/next-lat-deg, -lon-, ap/next-valid) and
    # advances the leg when ap/turn-done passes ap/turn-ack. Everything else is worked out here, live: the turn's size from the leg's
    # course and the next, its radius from the ground speed (the wind is in it) and the bank the aircraft can use (its limit, and what
    # its angle-of-attack margin allows), where it starts (where an arc of that radius joins the two legs, less half the roll in and
    # the bank's own delay), and where the roll out starts (when the track still has to turn what the roll out turns). Phases:
    # 0 on the leg, 1 turning at that bank, 2 rolling out onto the next leg's course, 3 on it, waiting for the manager.
    X = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
    P, V = _p, _v
    M = lambda *a: X('product', *a)
    S = lambda *a: X('sum', *a)
    D = lambda a, b: X('difference', a, b)
    Q = lambda a, b: X('quotient', a, b)
    GT = lambda a, b: X('gt', a, b)
    LT = lambda a, b: X('lt', a, b)
    EQ = lambda a, b: X('eq', a, b)
    MAX = lambda *a: X('max', *a)
    MIN = lambda *a: X('min', *a)
    ABS = lambda a: X('abs', a)
    IF = lambda c, a, b: X('ifthen', c, a, b)
    AND = lambda *a: X('and', *a)
    DEG = lambda a: X('todegrees', a)
    RAD = lambda a: X('toradians', a)
    TAN = lambda a: X('tan', RAD(a))
    ch.extend(_g_point('next', 'ap/next-lat-deg', 'ap/next-lon-deg'))
    ch.extend(_g_enu('end', 'next', 'ap/next-dn-ft', 'ap/next-de-ft', 'next waypoint, in the tangent plane at the end of this leg'))
    n2, e2 = P('ap/next-dn-ft'), P('ap/next-de-ft')
    ch.append(_fn('ap/next-course-deg', DEG(X('atan2', e2, n2)), 'the next leg\'s course, from the end of this one to the next waypoint'))
    ch.append(wrapped('ap/turn-delta-deg', 'ap/next-course-deg', 'ap/leg-course-deg', 'the turn at the end of the leg, right positive'))
    ch.append(wrapped('ap/turn-err-deg', 'ap/next-course-deg', 'ap/plane-track-deg', 'the next leg\'s course less the ground track'))
    # the bank an angle-of-attack margin allows: the load factor at which the angle reaches its limit less a margin, the lift's slope
    # taken from where the aircraft is (its angle above the zero-lift angle, per g)
    nz = MAX(P('accelerations/Nz'), V(0.5))
    slope = Q(MAX(V(0.5), D(P('aero/alpha-deg'), V(ALPHA_ZERO_LIFT))), nz)
    ncap = S(nz, Q(D(D(P('ap/alpha-limit-deg'), V(TURN_ALPHA_MARGIN)), P('aero/alpha-deg')), slope))
    ch.append(_fn('ap/bank-alpha-cap-deg', DEG(X('acos', Q(V(1), MAX(V(1.0001), ncap)))),
                  'the bank the angle-of-attack margin allows: acos(1 / n), n the load factor at which the angle reaches its limit less %g deg' % TURN_ALPHA_MARGIN,
                  clip=('%g' % TURN_MIN_BANK, '60')))
    rk, rt = roll_delay()
    ch.append(_fn('ap/roll-lag-s', _table(list(zip(rk, rt)), 'velocities/vc-kts'), 'the bank\'s delay behind its target at this speed (rolltest.py), s'))
    ch.append(_fn('ap/turn-bank-deg', MIN(P('ap/bank-command-limit-deg'), P('ap/bank-alpha-cap-deg')),
                  'the bank of a turn on a leg: the bank command limit, and what the angle-of-attack margin allows (heading mode and the pilot are not held to the margin)'))
    lim = P('ap/turn-bank-deg')
    # The bank the aircraft flies for the bank it is commanded (fdm/turnperf.py, data/turn_performance.json, docs/PLAN.md "a turn performance table"): the bank law settles above its
    # command by 0.3 to 4 % at cruise speeds and by up to 12 % slow and heavy, so the arc is worked out at the bank the table says it flies, not the one asked for.
    tp = turn_performance()
    if tp:
        ratio = _table3(tp['axes'], tp['grid_flown_per_cmd'], ('velocities/vc-kts', 'inertia/weight-lbs', 'engine/pressure-altitude-ft'), offset=1.0)
        ch.append(_fn('ap/turn-bank-ratio', ratio, 'the bank flown over the bank commanded in a turn at this speed, weight and height (turnperf.py)'))
    else:
        ch.append(_fn('ap/turn-bank-ratio', V(1), 'the bank flown over the bank commanded in a turn (none measured: 1)'))
    # The bank's effective delays rolling in and rolling out (turnperf.py: the area between the steady bank and the bank's response, less the command's own ramp): the bank
    # settles with a long tail, so the turn starts later and ends later than the ramp and the time-to-10-degrees delay (ap/roll-lag-s) say.
    lag_props = ('velocities/vc-kts', 'inertia/weight-lbs', 'engine/pressure-altitude-ft')
    for name, key, what in (('ap/turn-lag-in-s', 'grid_lag_in_s', 'rolling in'), ('ap/turn-lag-out-s', 'grid_lag_out_s', 'rolling out')):
        if tp and key in tp:
            ch.append(_fn(name, _table3(tp['axes'], tp[key], lag_props), 'the bank\'s effective delay %s, s (turnperf.py)' % what))
        else:
            ch.append(_fn(name, P('ap/roll-lag-s'), 'the bank\'s delay %s (none measured: the delay of rolltest.py)' % what))
    if tp and 'grid_moment_out_s2' in tp:
        ch.append(_fn('ap/turn-moment-out-s2', _table3(tp['axes'], tp['grid_moment_out_s2'], lag_props),
                      'the roll out\'s sideways drift, s^2: the area between the heading and the instant-roll-out equivalent over the steady turn rate (turnperf.py); times g tan(bank) it is the drift, to the outside, ft'))
    else:
        ch.append(_fn('ap/turn-moment-out-s2', V(0), 'the roll out\'s sideways drift (none measured: 0)'))
    ch.append(_fn('ap/turn-bank-flown-deg', M(lim, P('ap/turn-bank-ratio')), 'the bank a turn is flown at: the bank commanded times what the aircraft flies for it'))
    lead_bank = P('ap/turn-bank-flown-deg')
    design = False
    pt_ = path_thrust()
    if TURN_END_CONFIG and LEVEL_THRUST_FF and pt_ and 'grid_alpha_level_deg' in pt_ and 'grid_alpha_spoiler_deg' in pt_:
        sa_ = pt_['spoiler_axes']
        ch.append(_fn('ap/alpha-end-deg', S(P('ap/alpha-level-deg'), _table3g(sa_['spoiler'], sa_['cl'], sa_['mach'], pt_['grid_alpha_spoiler_deg'], ('ap/vt-sp-end', 'ap/cl-level', 'velocities/mach'))),
                      'the angle of attack level flight has at this speed and weight in the configuration the leg ends in: the spoilers at ap/vt-sp-end (pathperf.py)'))
        ncap_end = S(V(1), Q(D(D(P('ap/alpha-limit-deg'), V(TURN_ALPHA_MARGIN)), P('ap/alpha-end-deg')), MAX(V(0.5), D(P('ap/alpha-end-deg'), V(ALPHA_ZERO_LIFT)))))
        ch.append(_fn('ap/bank-alpha-cap-end-deg', DEG(X('acos', Q(V(1), MAX(V(1.0001), ncap_end)))),
                      'the bank the angle-of-attack margin allows level in the configuration the leg ends in (as ap/bank-alpha-cap-deg, at 1 g and without the gusts): steady', clip=('%g' % TURN_MIN_BANK, '60')))
        cap_lag = P('ap/bank-alpha-cap-lag-deg')
        if TURN_DESIGN_LAG_S:
            ch.append('''    <lag_filter name="ap/bank-alpha-cap-lag-deg">
      <description>the angle-of-attack cap of the bank, lagged: what it is on the whole, not in a gust</description>
      <input>ap/bank-alpha-cap-deg</input>
      <c1>%g</c1>
    </lag_filter>''' % (1.0 / TURN_DESIGN_LAG_S))
            design_cap = MIN(P('ap/bank-alpha-cap-end-deg'), cap_lag)
        else:
            design_cap = P('ap/bank-alpha-cap-end-deg')
        ch.append(_fn('ap/turn-bank-design-deg', MIN(P('ap/bank-command-limit-deg'), design_cap),
                      'the bank a turn is designed for: the bank command limit, the steady cap of the configuration the leg ends in and the angle-of-attack cap lagged (the bank commanded)'))
        ch.append(_fn('ap/turn-bank-end-deg', M(P('ap/turn-bank-design-deg'), P('ap/turn-bank-ratio')), 'the bank a turn will be flown at when the leg ends: the design bank times what the aircraft flies for it'))
        lead_bank = P('ap/turn-bank-end-deg')
        design = True
    # The turn's start, its radius and its lead are a prediction, not a protection: the bank limit they use goes through a lag (TURN_BANK_LAG_S), so that a gust that moves the angle of
    # attack (and with it the bank cap, 8 to 11 deg from frame to frame in 15 ft/s of turbulence at 143 KCAS with spoilers out) does not move the lead: a 152 deg turn's lead at 8 deg
    # is 88,000 ft, and one frame of it over the distance to go began the turn 14 nmi early and the route ended (docs/PLAN.md, phase 11 W2, 2026-11-14). The bank itself is not lagged.
    ch.append('''    <lag_filter name="ap/turn-bank-lead-deg">
      <description>the bank the turn's lead is worked out for: the bank flown, lagged</description>
      <input>%s</input>
      <c1>%g</c1>
    </lag_filter>''' % (lead_bank.replace('<property>', '').replace('</property>', ''), 1.0 / TURN_BANK_LAG_S))
    limf = MAX(V(2), P('ap/turn-bank-lead-deg')) if TURN_BANK_LAG_S else P('ap/turn-bank-flown-deg')
    vgt = MAX(P('velocities/vg-fps'), V(60))
    radius = Q(M(vgt, vgt), M(V(32.174), TAN(limf)))
    ch.append(_fn('ap/turn-radius-ft', radius, 'the radius of a turn at the bank the aircraft flies, in ground speed'))
    # The lead in a wind (docs/PLAN.md, "Turns in a wind"). The arc is flown in the air: its radius is vt^2 / (g tan bank), the heading goes from the present one to the
    # new leg's (the new course less the crab the wind needs there), and the wind pushes the aircraft for the turning time. The lead is the distance before the corner at which the
    # predicted exit of the arc lies on the new line: ((the arc's chord + wind * time) . the new leg's right normal) / (the old leg's direction . it). In calm air that is exactly
    # R tan(delta / 2). The wind is the total wind through a 10 s lag, so that gusts do not move the lead.
    for comp in ('north', 'east'):
        ch.append('''    <lag_filter name="ap/wind-%s-filt-fps">
      <input>atmosphere/total-wind-%s-fps</input>
      <c1>0.1</c1>
    </lag_filter>''' % (comp, comp))
    SINd = lambda a: X('sin', RAD(a))
    COSd = lambda a: X('cos', RAD(a))
    ds = IF(GT(P('ap/turn-delta-deg'), V(0)), V(1), V(-1))
    wn, we = P('ap/wind-north-filt-fps'), P('ap/wind-east-filt-fps')
    vt_now = MAX(P('velocities/vt-fps'), V(100))
    # the speed the arc is flown at: the airspeed now and the speed the speed law is taking it to (calibrated, so the same ratio holds for the true airspeed at this height), half and half
    tgt = MAX(V(1 - TURN_SPEED_CLIP), MIN(V(1 + TURN_SPEED_CLIP), Q(P('ap/speed-target-kcas'), MAX(V(50), P('velocities/vc-kts')))))
    vta = IF(V(TURN_SPEED_PRED), M(vt_now, S(V(0.5), M(V(0.5), tgt))), vt_now)
    c1d, psi0 = P('ap/next-course-deg'), P('ap/psi-plane-deg')
    ch.append(_fn('ap/turn-wind-cross-fps', S(M(V(-1), wn, SINd(c1d)), M(we, COSd(c1d))), 'the wind across the new leg, towards its right, ft/s'))
    ch.append(_fn('ap/turn-psi1-deg', D(c1d, DEG(X('asin', MAX(V(-0.5), MIN(V(0.5), Q(P('ap/turn-wind-cross-fps'), vta)))))), 'the heading on the new leg: its course less the crab the wind needs'))
    ch.append(wrapped('ap/turn-dpsi-raw-deg', 'ap/turn-psi1-deg', 'ap/psi-plane-deg', 'the heading change to the new leg\'s heading'))
    ch.append(_fn('ap/turn-dpsi-rad', RAD(MAX(V(0), M(ds, P('ap/turn-dpsi-raw-deg')))), 'the heading change in the turn\'s direction, rad'))
    ch.append(_fn('ap/turn-radius-air-ft', Q(M(vta, vta), M(V(32.174), TAN(limf))), 'the radius of the turn in the air'))
    ch.append(_fn('ap/turn-time-s', M(P('ap/turn-dpsi-rad'), Q(P('ap/turn-radius-air-ft'), vta)), 'the time the turn takes'))
    p1 = P('ap/turn-psi1-deg')
    cn = M(ds, P('ap/turn-radius-air-ft'), D(SINd(p1), SINd(psi0)))
    ce = M(V(-1), ds, P('ap/turn-radius-air-ft'), D(COSd(p1), COSd(psi0)))
    num = S(M(V(-1), SINd(c1d), S(cn, M(wn, P('ap/turn-time-s')))), M(COSd(c1d), S(ce, M(we, P('ap/turn-time-s')))))
    # The roll out's sideways drift: the exit is on the outside of the arc by g tan(bank) times the response's moment (the heading's tail runs on after the instant-roll-out
    # equivalent has stopped), seen across the new line in full: to the left of it for a right turn. exit(L) = L sin(delta) + num + dexit, so it moves num.
    fade = MAX(V(0), MIN(V(1), Q(D(ABS(P('ap/turn-delta-deg')), V(TURN_DRIFT_FADE_DEG[0])), V(TURN_DRIFT_FADE_DEG[1] - TURN_DRIFT_FADE_DEG[0]))))
    ch.append(_fn('ap/turn-drift-exit-ft', M(V(-1), ds, V(TURN_DRIFT), fade, V(32.174), TAN(limf), P('ap/turn-moment-out-s2')),
                  'the roll out\'s drift at the exit across the new line, right of it positive: outward is to the left of the new line for a right turn'))
    num = S(num, P('ap/turn-drift-exit-ft'))
    use = AND(GT(ABS(P('ap/turn-delta-deg')), V(TURN_WIND_MIN_DEG)), LT(ABS(P('ap/turn-delta-deg')), V(TURN_FLY_BY_MAX)))
    den = IF(use, M(V(-1), SINd(P('ap/turn-delta-deg'))), V(-1))
    ch.append(_fn('ap/turn-lead-wind-ft', Q(num, den), 'the distance before the corner at which the arc\'s predicted exit is on the new line, in the wind'))
    old_lead = M(P('ap/turn-radius-ft'), TAN(M(V(0.5), MIN(ABS(P('ap/turn-delta-deg')), V(TURN_FLY_BY_MAX)))))
    ch.append(_fn('ap/turn-lead-ft', S(IF(use, MAX(V(0), P('ap/turn-lead-wind-ft')), old_lead),
                                        M(vgt, S(M(V(0.5), Q(lim, V(BANK_RATE))), P('ap/turn-lag-in-s')))),
                  'the distance before the corner a turn starts at: where the arc joins the two legs in the wind (the old R tan(delta / 2) for a turn under %g deg or a fly-over), less half the roll in and the bank\'s delay' % TURN_WIND_MIN_DEG))
    phi = P('attitude/phi-deg')
    ch.append(_fn('ap/turn-rollout-deg', M(DEG(Q(M(V(32.174), TAN(ABS(phi))), vgt)), S(M(V(0.5), Q(ABS(phi), V(BANK_RATE))), P('ap/turn-lag-out-s'))),
                  'the track still to turn when the roll out starts: the turn rate times half the roll out and the delay'))
    dsign = IF(GT(P('ap/turn-delta-deg'), V(0)), V(1), V(-1))
    ch.append(_fn('ap/turn-remaining-deg', M(dsign, P('ap/turn-err-deg')), 'the track still to turn to the next leg\'s course, in the turn\'s direction'))
    # ---- the turn predicts its own exit (docs/PLAN.md, "Turns: the lead's roll terms are measured as well, and the turn predicts its own exit"). The arc in the air is a circle
    # whose radius the bank sets, and the wind only moves it, so where it ends is linear in the radius: the cross-track on the new line of the aircraft's predicted position when its
    # heading reaches the new leg's is A + R B, A the cross-track now (right of the new line positive), B the chord of the arc and the wind's push per foot of radius. The radius
    # that makes it 0 is R* = -A / B (the tangent circle: the distance to the corner over 1 - cos(the heading to go), in calm air), the bank atan(vt^2 / (g R*)) over the table's
    # flown-per-commanded. It is held to the sourced bank limit (flown) and the angle-of-attack cap above and half the turn's bank below, and lagged by TURN_PRED_TC s.
    # It works once the bank is made (90 % of the turn's) and while the heading to go is over TURN_PRED_MIN_REM_DEG.
    ch.append(_fn('ap/turn-xt-new-ft', S(M(P('ap/leg-togo-ft'), SINd(P('ap/turn-delta-deg'))), M(P('ap/leg-xt-ft'), COSd(P('ap/turn-delta-deg')))),
                  'the cross-track on the new leg\'s line, right of it positive'))
    crab = D(c1d, p1)
    cos_rem = COSd(S(P('ap/turn-dpsi-raw-deg'), crab))
    ch.append(_fn('ap/turn-pred-b', S(M(V(-1), ds, D(COSd(crab), cos_rem)), M(P('ap/turn-dpsi-rad'), Q(P('ap/turn-wind-cross-fps'), vta))),
                  'the exit\'s cross-track on the new line per foot of radius: the arc\'s chord and the wind\'s push over its time'))
    rstar = Q(M(V(-1), S(P('ap/turn-xt-new-ft'), P('ap/turn-drift-exit-ft'))), P('ap/turn-pred-b'))
    ch.append(_fn('ap/turn-radius-star-ft', rstar, 'the radius of the arc from here that ends on the new line'))
    bank_hi = MAX(lim, MIN(Q(P('ap/bank-limit-deg'), P('ap/turn-bank-ratio')), P('ap/bank-alpha-cap-deg')))
    ch.append(_fn('ap/turn-bank-hi-deg', bank_hi, 'the most bank commanded in a turn: the sourced bank limit as flown, and the angle-of-attack cap'))
    # The trim works on the bank the turn is designed for (the steady cap of the configuration the leg ends in), not on the instantaneous limit: in turbulence with the spoilers out the limit
    # flickers between 8 and 60 deg, the trim took a dip of it at the turn's start for the bank it held to the end (it only works once the bank is 90 % of the limit, which a bank held at
    # 8 deg never reaches again), and the arc was wider than the lead had been worked out for. The instantaneous limit still clips the command (below), as a protection does.
    dlim = P('ap/turn-bank-design-deg') if design else lim
    dhi = MAX(dlim, MIN(Q(P('ap/bank-limit-deg'), P('ap/turn-bank-ratio')), P('ap/bank-alpha-cap-end-deg'), P('ap/bank-alpha-cap-lag-deg') if TURN_DESIGN_LAG_S else P('ap/bank-alpha-cap-end-deg'))) if design else P('ap/turn-bank-hi-deg')
    star = IF(GT(P('ap/turn-radius-star-ft'), V(1)),
              Q(DEG(X('atan', Q(M(vta, vta), M(V(32.174), P('ap/turn-radius-star-ft'))))), P('ap/turn-bank-ratio')), dhi)
    pred_on = AND(V(TURN_PRED), EQ(P('ap/roll-mode'), V(2)), EQ(P('ap/turn-phase'), V(1)), use,
                  GT(ABS(phi), M(V(0.9), MIN(dlim, P('ap/turn-bank-pred-deg')) if TURN_PRED_ON_HELD else dlim)), GT(P('ap/turn-dpsi-rad'), V(math.radians(TURN_PRED_MIN_REM_DEG))), GT(ABS(P('ap/turn-pred-b')), V(TURN_PRED_MIN_B)))
    holding = AND(V(TURN_PRED_HOLD), V(TURN_PRED), EQ(P('ap/roll-mode'), V(2)), EQ(P('ap/turn-phase'), V(1)), use)
    ch.append(_fn('ap/turn-bank-pred-raw-deg', IF(pred_on, MAX(M(V(TURN_PRED_LO), dlim), MIN(dhi, star)), IF(holding, P('ap/turn-bank-pred-deg'), dlim)), 'the bank that puts the arc\'s exit on the new line (the turn\'s own bank when it does not apply)'))
    ch.append('''    <lag_filter name="ap/turn-bank-pred-deg">
      <input>ap/turn-bank-pred-raw-deg</input>
      <c1>%g</c1>
    </lag_filter>''' % (1.0 / TURN_PRED_TC))
    ch.append(_fn('ap/turn-bank-cmd-deg', MAX(M(V(TURN_PRED_LO), lim), MIN(P('ap/turn-bank-hi-deg'), P('ap/turn-bank-pred-deg'))), 'the bank commanded in the turn: the trimmed bank'))
    armed = AND(EQ(P('ap/roll-mode'), V(2)), EQ(P('ap/next-valid'), V(1)), EQ(P('ap/engaged'), V(1)), EQ(P('ap/on-mains'), V(0)), EQ(P('ap/manual'), V(0)),
                GT(P('velocities/vg-fps'), V(60)))
    small = LT(ABS(P('ap/turn-delta-deg')), V(2.5))
    phase = P('ap/turn-phase')
    new = IF(armed,
             IF(LT(phase, V(0.5)), IF(LT(P('ap/leg-togo-ft'), IF(small, V(150), P('ap/turn-lead-ft'))), IF(small, V(3), V(1)), V(0)),
                IF(LT(phase, V(1.5)), IF(LT(P('ap/turn-remaining-deg'), P('ap/turn-rollout-deg')), V(2), V(1)),
                   IF(LT(phase, V(2.5)), IF(AND(LT(ABS(phi), V(1.5)), LT(ABS(P('ap/turn-err-deg')), V(4))), V(3), V(2)),
                      IF(LT(P('ap/turn-ack'), P('ap/turn-done')), V(3), V(0))))),
             V(0))
    ch.append(_fn('ap/turn-phase-new', new, 'the turn\'s phase this frame'))
    ch.append(_fn('ap/turn-done-next', S(P('ap/turn-done'), IF(AND(GT(P('ap/turn-phase-new'), V(2.5)), LT(phase, V(2.5))), V(1), V(0))), out='ap/turn-done'))
    ch.append(_fn('ap/turn-phase-next', P('ap/turn-phase-new'), out='ap/turn-phase'))
    leg_other = MAX(X('product', V(-1), lim), MIN(lim, IF(LT(phase, V(0.5)), IF(V(TURN_LEG_LAW), P('ap/bank-final-deg'), P('ap/bank-track-deg')), M(V(G['K_psi']), P('ap/turn-err-deg'), Q(P('velocities/vt-fps'), V(600))))))
    ch.append(_fn('ap/bank-leg-deg', IF(AND(GT(phase, V(0.5)), LT(phase, V(1.5))), M(dsign, P('ap/turn-bank-cmd-deg')), leg_other),
                  'the bank on a leg: the leg\'s law; in the turn the bank fed forward; rolling out the heading law onto the next course'))
    ch.append('''    <switch name="ap/bank-mode-deg">
      <default value="ap/bank-cmd-deg"/>
      <test value="0">ap/on-mains gt 0</test>
      <test value="nav/roll-deg">ap/manual == 2</test>
      <test value="ap/bank-manual-deg">ap/manual == 1</test>
      <test value="ap/bank-heading-deg">ap/roll-mode == 1</test>
      <test value="ap/bank-leg-deg">ap/roll-mode == 2</test>
      <test value="ap/bank-final-deg">ap/roll-mode == 3</test>
    </switch>''')
    ch.append(_fn('ap/bank-command-limit-deg', _op('product', _p('ap/bank-limit-deg'), _v(BANK_COMMAND)),
                  'the bank command stops at %g of the limit: turning, the bank overshoots its command and then settles '
                  'above it (a proportional law; an integral was tried and overshot)' % BANK_COMMAND))
    ch.append(_fn('ap/bank-clip-deg', IF(AND(EQ(P('ap/roll-mode'), V(2)), EQ(P('ap/turn-phase'), V(1))), MAX(P('ap/bank-command-limit-deg'), P('ap/turn-bank-hi-deg')), P('ap/bank-command-limit-deg')),
                  'the bank command stops at the bank command limit; the turn on a leg, in its arc, has its own most (ap/turn-bank-hi-deg)'))
    ch.append(_fn('ap/bank-manual-deg', _op('product', _p('ap/stick-roll'), _p('ap/bank-command-limit-deg')), 'by hand: the stick\'s position is the bank'))
    ch.append(_fn('ap/bank-clipped-deg', '''        <max>
          <product>%s%s</product>
          <min>%s%s</min>
        </max>''' % (_v(-1), _p('ap/bank-clip-deg'), _p('ap/bank-clip-deg'), _p('ap/bank-mode-deg')), 'inside the bank limit'))
    ch.append('''    <switch name="ap/bank-gated-deg">
      <default value="0"/>
      <test value="ap/bank-clipped-deg">ap/engaged == 1</test>
    </switch>''')
    ch.append('''    <actuator name="ap/bank-target-deg">
      <description>the bank command moves at 5 deg/s at most</description>
      <input>ap/bank-gated-deg</input>
      <rate_limit>%g</rate_limit>
    </actuator>''' % BANK_RATE)
    ch.append(_fn('ap/bank-error-deg', _op('difference', _p('ap/bank-target-deg'), _p('nav/roll-deg'))))
    # the integral trims the ailerons in a steady turn; it runs only close to the target, so it can't wind up
    # while the bank command is still ramping
    ch.append(_trigger('roll', 'ap/bank-error-deg lt 3', 'ap/bank-error-deg gt -3'))
    ch.append(_pid('ap/roll-pi-deg', 'ap/bank-error-deg', 'ap/k-phi', 'ap/k-phi-i', 'roll', clip=('-20', '20')))
    ch.append(_fn('ap/roll-law-deg', '''        <difference>
          %s
          <product>%s%s%s</product>
        </difference>''' % (_p('ap/roll-pi-deg'), _p('ap/k-p'), _v(57.29578), _p('velocities/p-rad_sec')),
                  'roll command, right wing down positive', clip=('-20', '20')))
    # ---- the decrab (the landing task's yaw axis in its last seconds and on the runway). The final is flown crabbed into the wind, the sideslip law keeping the
    # nose on the relative wind; the wheels then have the nose off the runway's course and the decrab happens on the ground, the mains rolling along the nose
    # (headless, 20 kt across: 48 ft off the line). The MV-22B's engine-out landing takes the crab off at the last: from 3 s to 0.5 s before the wheels, the nose goes
    # onto the course the line gives, and it stays there on the runway; here by wheel height (DECRAB_H_START to DECRAB_H_END). The weight is 0 before, rises
    # to 1, is held, and is 1 from the first wheel until the landing is left.
    w_now = MAX(V(0), MIN(V(1), Q(D(V(DECRAB_H_START), P('aero/wheel-height-ft')), V(DECRAB_H_START - DECRAB_H_END))))
    landing = AND(EQ(P('ap/land-mode'), V(1)), EQ(P('ap/engaged'), V(1)), EQ(P('ap/manual'), V(0)), V(DECRAB))
    ch.append(_fn('ap/decrab-w-next', IF(landing, IF(X('or', GT(P('ap/on-mains'), V(0)), EQ(P('ap/rollout'), V(1))), V(1), MAX(P('ap/decrab-w'), w_now)), V(0)),
                  'the decrab\'s weight: 0 on the final, from %g ft of wheel height to 1 at %g ft, 1 on the runway' % (DECRAB_H_START, DECRAB_H_END), out='ap/decrab-w'))
    # ---- the landing task's lateral law (roll mode 3): the final's line, a velocity loop inside a position loop (docs/PLAN.md, "The final wobbles across its line").
    # The cruise law (the leg's course turned toward the line by atan(cross-track / a 15 s lookahead), into a proportional bank) crosses the line on the final:
    # 44 to 671 ft past it for offsets of 300 to 4,000 ft, and stays 6 to 8 ft off it for ever (a bias between the track and the leg's course).
    ch.append(wrapped('ap/final-trk-err-deg', 'ap/plane-track-deg', 'ap/leg-course-deg', 'the ground track less the leg\'s course'))
    vgf = MAX(P('velocities/vg-fps'), V(60))
    ch.append(_fn('ap/final-xt-rate-fps', M(vgf, X('sin', RAD(P('ap/final-trk-err-deg')))), 'the rate the cross-track grows at, right positive'))
    cca = RAD(P('ap/leg-course-deg'))
    ch.append(_fn('ap/aim-wleft-raw-fps', D(M(P('atmosphere/total-wind-north-fps'), X('sin', cca)), M(P('atmosphere/total-wind-east-fps'), X('cos', cca))), 'the total wind blowing to the left of the leg\'s course, ft/s'))
    ch.append('''    <lag_filter name="ap/aim-wleft-fps">
      <input>ap/aim-wleft-raw-fps</input>
      <c1>%g</c1>
    </lag_filter>''' % (1.0 / FINAL_AIM_FILT_S))
    aim_w = MAX(V(0), MIN(V(1), Q(D(V(FINAL_AIM_FROM_FT), P('aero/wheel-height-ft')), V(FINAL_AIM_FROM_FT - FINAL_AIM_FULL_FT))))
    ch.append(_fn('ap/final-aim-ft', IF(AND(EQ(P('ap/final-aim'), V(1)), EQ(P('ap/roll-mode'), V(3))), M(V(FINAL_AIM_FT_PER_KT / 1.68781), P('ap/aim-wleft-fps'), aim_w), V(0)),
                  'the aim point\'s offset from the line, right positive: upwind by %g ft per knot of the crosswind component, from %g to %g ft of wheel height' % (FINAL_AIM_FT_PER_KT, FINAL_AIM_FROM_FT, FINAL_AIM_FULL_FT)))
    ch.append(_fn('ap/final-xt-aimed-ft', D(P('ap/leg-xt-ft'), P('ap/final-aim-ft')), 'the cross-track from the aim point, right positive'))
    vmax = M(vgf, V(math.sin(math.radians(FINAL_ANGLE_MAX_DEG))))
    t_sched = lambda base, land: (IF(EQ(P('ap/roll-mode'), V(3)), _table([(0.0, land), (FINAL_SCHED_LO_FT, land), (FINAL_SCHED_HI_FT, base), (1000.0, base)], 'aero/wheel-height-ft'), V(base))
                                  if FINAL_SCHED else V(base))
    ch.append(_fn('ap/final-t-outer-s', t_sched(FINAL_T_OUTER_S, FINAL_T_OUTER_LAND_S), 'the position loop\'s time: the cross-track over this is the rate the line asks for, s'))
    ch.append(_fn('ap/final-t-inner-s', t_sched(FINAL_T_INNER_S, FINAL_T_INNER_LAND_S), 'the rate loop\'s time: the rate error over this is the lateral acceleration asked for, s'))
    ch.append(_fn('ap/final-want-rate-fps', M(V(-1), MAX(M(V(-1), vmax), MIN(vmax, Q(P('ap/final-xt-aimed-ft'), P('ap/final-t-outer-s'))))),
                  'the cross-track rate the line asks for: the cross-track over the position loop\'s time, at most vg sin(%g deg), towards the line' % FINAL_ANGLE_MAX_DEG))
    ch.append(_fn('ap/final-bank-p-deg', DEG(X('atan', Q(Q(D(P('ap/final-want-rate-fps'), P('ap/final-xt-rate-fps')), P('ap/final-t-inner-s')), V(32.174)))),
                  'the bank the lateral acceleration asked for takes: the rate wanted less the rate there is, over the rate loop\'s time'))
    ch.append(_fn('ap/final-xt-neg-ft', M(V(-1), P('ap/final-xt-aimed-ft')), 'the integral\'s input: towards the line'))
    ch.append(_trigger('final', 'ap/roll-mode gt %d' % (1 if TURN_LEG_I else 2), 'ap/leg-xt-ft lt %g' % FINAL_I_BAND_FT, 'ap/leg-xt-ft gt %g' % -FINAL_I_BAND_FT))
    ch.append(_pid('ap/final-i-deg', 'ap/final-xt-neg-ft', 0.0, FINAL_KI, 'final', clip=('-2', '2')))
    ch.append(_fn('ap/final-xt-far', IF(AND(GT(ABS(P('ap/leg-xt-ft')), V(FINAL_I_FAR_FT)), LT(ABS(P('ap/leg-xt-ft')), V(FINAL_I_BAND_WIDE_FT))), V(1), V(0)), 'the cross-track is beyond the old integral\'s band and within the wide one\'s'))
    ch.append(_trigger('final-wide', 'ap/final-wide == 1', 'ap/roll-mode gt 1', 'ap/final-xt-far == 1', 'ap/final-xt-rate-fps lt %g' % FINAL_I_RATE_FPS, 'ap/final-xt-rate-fps gt %g' % -FINAL_I_RATE_FPS,
                       'aero/wheel-height-ft lt %g' % FINAL_I_BELOW_FT))
    ch.append(_pid('ap/final-i-wide-deg', 'ap/final-xt-neg-ft', 0.0, FINAL_KI_WIDE, 'final-wide', clip=('-%g' % FINAL_I_WIDE_CLIP_DEG, '%g' % FINAL_I_WIDE_CLIP_DEG)))
    cc = RAD(P('ap/leg-course-deg'))
    ch.append(_fn('ap/ff-wleft-fps', D(M(P('atmosphere/total-wind-north-fps'), X('sin', cc)), M(P('atmosphere/total-wind-east-fps'), X('cos', cc))), 'the total wind blowing to the left of the leg\'s course, ft/s'))
    ch.append('''    <lag_filter name="ap/ff-wleft-s-fps">
      <input>ap/ff-wleft-fps</input>
      <c1>%g</c1>
    </lag_filter>''' % (1.0 / FF_SMOOTH_S))
    ch.append('''    <washout_filter name="ap/ff-wleft-wash-fps">
      <input>ap/ff-wleft-s-fps</input>
      <c1>%g</c1>
    </washout_filter>''' % (1.0 / FF_DERIV_S))
    ch.append(_fn('ap/final-ff-bank-deg', IF(AND(EQ(P('ap/final-ff'), V(1)), EQ(P('ap/roll-mode'), V(3)), LT(P('aero/wheel-height-ft'), V(FF_BELOW_FT))),
                                             DEG(X('atan', Q(M(V(-FF_TAU_S / FF_DERIV_S), X('sqrt', Q(P('inertia/weight-lbs'), V(FF_TAU_WEIGHT_LB))), P('ap/ff-wleft-wash-fps')), V(FF_T_S * 32.174)))), V(0)),
                  'the bank that takes out the drift the crosswind\'s change is about to cause, deg (right positive)', clip=('%g' % -FF_CLIP_DEG, '%g' % FF_CLIP_DEG)))
    ch.append(_fn('ap/final-rate-err-fps', D(P('ap/final-want-rate-fps'), P('ap/final-xt-rate-fps')), 'the rate wanted less the rate there is, towards the line positive, ft/s'))
    ch.append(_trigger('final-ri', 'ap/final-ri == 1', 'ap/roll-mode == 3', 'ap/leg-xt-ft lt %g' % FINAL_RI_BAND_FT, 'ap/leg-xt-ft gt %g' % -FINAL_RI_BAND_FT, 'aero/wheel-height-ft lt %g' % FINAL_RI_BELOW_FT))
    ch.append(_pid('ap/final-i-rate-deg', 'ap/final-rate-err-fps', 0.0, FINAL_KI_RI, 'final-ri', clip=('-%g' % FINAL_RI_CLIP_DEG, '%g' % FINAL_RI_CLIP_DEG)))
    ch.append(_fn('ap/bank-final-deg', S(P('ap/final-bank-p-deg'), P('ap/final-ff-bank-deg'), P('ap/final-i-rate-deg'), IF(EQ(P('ap/final-wide'), V(1)), S(P('ap/final-i-deg'), P('ap/final-i-wide-deg')), P('ap/final-i-deg'))),
                  'the bank on the final: the lateral law of the landing task (roll mode 3)', clip=('%g' % -FINAL_BANK_MAX_DEG, '%g' % FINAL_BANK_MAX_DEG)))
    # ---- basic law: yaw
    ch.append('''    <washout_filter name="ap/yaw-rate-washed">
      <input>velocities/r-rad_sec</input>
      <c1>0.3333</c1>
    </washout_filter>''')
    ch.append(_fn('ap/takeoff-roll', '        <ifthen><and><eq>%s%s</eq><gt>%s%s</gt><eq>%s%s</eq></and>%s%s</ifthen>' % (
        _p('ap/ground-steer'), _v(1), _p('ap/on-mains'), _v(0), _p('ap/land-mode'), _v(0), _v(1), _v(0)), 'on the mains with steering on and not landing: the takeoff roll'))
    if YAW_AIR_BLEND_S:
        # 0 on the takeoff roll, then up to 1 over YAW_AIR_BLEND_S from the frame the wheels leave: the sideslip law comes in and the ground term goes out together, not at once
        ch.append(_fn('ap/yaw-air-w-next', '        <ifthen><eq>%s%s</eq>%s<min>%s<sum>%s<product>%s%s</product></sum></min></ifthen>' % (
            _p('ap/takeoff-roll'), _v(1), _v(0), _v(1), _p('ap/yaw-air-w'), _p('simulation/dt'), _v(1.0 / YAW_AIR_BLEND_S)),
            'the weight of the airborne yaw law: 0 on the takeoff roll, rising to 1 over %g s from lift-off' % YAW_AIR_BLEND_S, out='ap/yaw-air-w'))
    ch.append(_trigger('beta', *((('ap/takeoff-roll == 0',) if ROLL_NO_BETA else ()) + (('ap/decrab-w lt 0.01',) if DECRAB else ()))))
    ch.append(_fn('ap/beta-error-deg', '        <sum>%s<product>%s%s%s</product></sum>' % (_p('aero/beta-deg'), _v(MANUAL_BETA), _p('ap/protected'), _p('ap/pedal')),
                  'sideslip less the pedals\' (nose right is negative sideslip)'))
    roll_gate = (_p('ap/yaw-air-w') if YAW_AIR_BLEND_S else '<difference>%s%s</difference>' % (_v(1), _p('ap/takeoff-roll'))) if ROLL_NO_BETA else ''
    beta_gate = roll_gate + (('<difference>%s%s</difference>' % (_v(1), _p('ap/decrab-w'))) if DECRAB else '')
    ch.append(_fn('ap/beta-gated-deg', '        <product>%s<max>%s<min>%s<quotient><difference>%s%s</difference>%s</quotient></min></max>%s</product>' % (
        _p('ap/beta-error-deg'), _v(0), _v(1), _p('velocities/vc-kts'), _v(40), _v(20), beta_gate),
        'sideslip, faded out below 60 kt: it means nothing at a walk' + ('; off on the takeoff roll' if ROLL_NO_BETA else '') + ('; faded out by the decrab\'s weight' if DECRAB else '')))
    ch.append(_pid('ap/yaw-beta-deg', 'ap/beta-gated-deg', 'ap/k-beta', 'ap/k-beta-i', 'beta', clip=('-12', '12')))
    if YAW_AIR_BLEND_S:
        # on the mains as before; in the air the crab's decrab weight at its gain, and for the blend after lift-off the ground term fades out with the weight at the gain it had on the ground
        ground_w = IF(GT(P('ap/on-mains'), V(0)), _op('product', MAX(MIN(V(1), P('ap/on-mains')), P('ap/decrab-w')), IF(EQ(P('ap/takeoff-roll'), V(1)), V(TAKEOFF_YAW_K), V(LANDING_YAW_K))),
                      MAX(_op('product', P('ap/decrab-w'), V(DECRAB_K)), _op('product', _op('difference', V(1), P('ap/yaw-air-w')), V(TAKEOFF_BLEND_K))))
        yaw_ground = _op('product', _p('ap/ground-steer'), ground_w, _p('ap/ground-error-deg'))
    else:
        yaw_ground = _op('product', _p('ap/ground-steer'), MAX(MIN(V(1), P('ap/on-mains')), P('ap/decrab-w')),
                         IF(GT(P('ap/on-mains'), V(0)), V(0.5), V(DECRAB_K)), _p('ap/ground-error-deg'))
    ch.append(_fn('ap/yaw-ground-deg', yaw_ground,
                  'the ruddervators on the heading error to the course the line gives: help the nose wheel on the ground, and take the crab off in the air from the decrab\'s weight', clip=('-10', '10')))
    ch.append(_fn('ap/yaw-law-deg', '''        <sum>
          %s
          <product>%s%s%s%s</product>
          %s
          <product>%s%s</product>
          %s
          <product>%s%s%s</product>
        </sum>''' % (_p('ap/bias-yaw-deg'), _v(-1), _p('ap/k-r'), _v(57.29578), _p('ap/yaw-rate-washed'), _p('ap/yaw-beta-deg'),
                     _v(-G['K_ari']), _p('ap/roll-law-deg'), _p('ap/yaw-ground-deg'), _v(MANUAL_PEDAL), _p('ap/protected'), _p('ap/pedal')),
                  'ruddervators against each other, nose right positive: damper, sideslip to zero (interconnect with the ailerons: gain 0 for now)', clip=('-20', '20')))
    # ---- thrust
    ch.append(_fn('ap/thrust-error-kt', _op('difference', _p('ap/speed-target-kcas'), _p('velocities/vc-kts')), 'slow is positive'))
    ch.append(_trigger('thrust', 'ap/thrust-mode == 3'))
    if THRUST_ANTIWINDUP:
        # the integral is a state: it runs while the speed mode flies and the laws are on, is held while the throttle the speed law asks for (before its limits) is at a limit and the error
        # would take it further, and is zero otherwise (the PID's trigger of -1 did the last)
        X_ = lambda tag, *a: '<%s>%s</%s>' % (tag, ''.join(a), tag)
        err_t, raw_t = _p('ap/thrust-error-kt'), _p('ap/thrust-speed-raw')
        at_limit = X_('or', X_('and', X_('le', raw_t, _v(0)), X_('lt', err_t, _v(0))), X_('and', X_('ge', raw_t, _v(1)), X_('gt', err_t, _v(0))))
        ch.append(_fn('ap/thrust-i-next', X_('ifthen', X_('and', X_('eq', _p('ap/thrust-mode'), _v(3)), X_('eq', _p('ap/engaged'), _v(1))),
                                              X_('max', _v(-1), X_('min', _v(1), X_('sum', _p('ap/thrust-i'), X_('ifthen', at_limit, _v(0), X_('product', _v(G['K_thr_i']), err_t, _p('simulation/dt')))))),
                                              _v(0)),
                      'the speed law\'s integral: held while its throttle is at a limit and the error would take it further', out='ap/thrust-i'))
        ch.append(_fn('ap/thrust-pi', X_('sum', X_('product', _v(G['K_thr']), err_t), _p('ap/thrust-i')), 'the speed error\'s proportional and integral terms', clip=('-1', '1')))
    else:
        ch.append(_pid('ap/thrust-pi', 'ap/thrust-error-kt', G['K_thr'], G['K_thr_i'], 'thrust', clip=('-1', '1')))
    pt = path_thrust()
    if LEVEL_THRUST_FF and pt:
        # the tables are in the lift coefficient the aircraft flies at (weight over dynamic pressure and wing area), Mach number and pressure altitude (pathperf.py): the drag is a function of the first two
        # and above the tropopause so is the throttle for level flight
        ch.append(_fn('ap/cl-level', '        <quotient>%s<product><max>%s%s</max>%s</product></quotient>' % (_p('inertia/weight-lbs'), _p('aero/qbar-psf'), _v(1), _p('metrics/Sw-sqft')),
                      'the lift coefficient the aircraft flies at: weight over dynamic pressure and wing area (not limited as ap/cl-now is: the throttle tables look it up)', clip=('0.05', '2.5')))
        tprops = ('engine/pressure-altitude-ft', 'ap/cl-level', 'velocities/mach')            # table, row, column
        if 'grid_alpha_spoiler_deg' in pt:
            sa_ = pt['spoiler_axes']
            ch.append(_fn('ap/alpha-spoiler-deg', _table3g(sa_['spoiler'], sa_['cl'], sa_['mach'], pt['grid_alpha_spoiler_deg'], ('ctl/spoiler-norm', 'ap/cl-level', 'velocities/mach')),
                          'the spoilers\' effect on the level angle of attack, deg, by their position, the lift coefficient and Mach number (pathperf.py)'))
        if 'grid_alpha_level_deg' in pt:
            ch.append(_fn('ap/alpha-level-deg', _table3g(pt['axes']['pressure_alt_ft'], pt['axes']['cl'], pt['axes']['mach'], pt['grid_alpha_level_deg'], tprops),
                          'the angle of attack of level flight at this Mach number, lift coefficient and height, deg, body axes (pathperf.py)'))
        ch.append(_fn('ap/thrust-per-deg', _table3g(pt['axes']['pressure_alt_ft'], pt['axes']['cl'], pt['axes']['mach'], pt['grid_throttle_per_deg'], tprops),
                      'the throttle a degree of flight path angle takes at this Mach number, lift coefficient and height (pathperf.py)'))
        # the climb rate the thrust can hold at this speed, weight and height: the path angle the throttle left over by level flight makes, (1 - level) / per degree, at CLIMB_MARGIN of it
        ch.append(_fn('ap/throttle-level', _table3g(pt['axes']['pressure_alt_ft'], pt['axes']['cl'], pt['axes']['mach'], pt['grid_throttle_level'], tprops),
                      'the throttle for level flight at this Mach number, lift coefficient and height (pathperf.py)'))
        table_climb = '        <product>%s%s<quotient><max>%s<difference>%s%s</difference></max>%s</quotient><quotient>%s%s</quotient></product>' % (
            _v(CLIMB_MARGIN), _p('velocities/vt-fps'), _v(0), _v(1), _p('ap/throttle-level'), _p('ap/thrust-per-deg'), _v(1), _v(57.29578))
        ch.append(_fn('ap/climb-rate-max-fps', table_climb,
            'the climb rate the thrust holds at this speed: the path angle the throttle above level flight makes (pathperf.py), at %g of it' % CLIMB_MARGIN))
        ch.append(_fn('ap/descent-rate-idle-fps', '        <product>%s%s<quotient>%s%s</quotient><quotient>%s%s</quotient></product>' % (
            _v(CLIMB_MARGIN), _p('velocities/vt-fps'), _p('ap/throttle-level'), _p('ap/thrust-per-deg'), _v(1), _v(57.29578)),
            'the descent rate the speed law can fly without the spoilers: the path angle the level-flight throttle gives up going to idle, at %g of it' % CLIMB_MARGIN))
        if THRUST_ENTRY_TABLE:
            # The baseline of the speed law's throttle: the throttle command while the laws are off (the latch at engagement); where the speed mode (3) begins in flight it is the table's level
            # throttle plus the path angle's and the configuration's terms at engagement, so that the throttle (baseline + integral + the terms for the change since engagement) is the table's
            # for the path and the configuration there are now; held otherwise. The baseline is NOT limited to 0..1: the terms after it are relative to the path and configuration latched at engagement
            # (the takeoff's, with the gear down), so a limit on the baseline alone breaks the sum: at the ceiling, where the table's level throttle is over 1, the clipped baseline less the
            # gear's term was 0.23 of throttle at the first capture (docs/PLAN.md, "the ceiling ride"); the throttle the laws send on is limited at the end (ap/thrust-speed).
            bias_xml = ('        <ifthen>\n          <eq>%s%s</eq>\n          %s\n          <ifthen>\n'
                        '            <and><eq>%s%s</eq><nq>%s%s</nq><eq>%s%s</eq><eq>%s%s</eq></and>\n'
                        '            <sum>%s<product>%s<sum>%s%s</sum></product></sum>\n'
                        '            %s\n          </ifthen>\n        </ifthen>') % (
                _p('ap/engaged'), _v(0), _p('fcs/throttle-cmd-norm'),
                _p('ap/thrust-mode'), _v(3), _p('ap/thrust-mode-prev'), _v(3), _p('ap/engaged-prev'), _v(1), _p('ap/engaged'), _v(1),
                _p('ap/throttle-level'), _p('ap/thrust-per-deg'), _p('ap/bias-gamma-deg'), _p('ap/bias-cfg-deg'),
                _p('ap/bias-throttle'))
            ch.append(_fn('ap/bias-throttle-next', bias_xml, 'the throttle baseline of the speed law: the throttle command while the laws are off, the table\'s at the start of the speed mode in flight, else held', out='ap/bias-throttle'))
            ch.append(_fn('ap/thrust-mode-prev-next', _p('ap/thrust-mode'), 'the thrust mode of the frame before', out='ap/thrust-mode-prev'))
            ch.append(_fn('ap/engaged-prev-next', _p('ap/engaged'), 'whether the laws were on in the frame before', out='ap/engaged-prev'))
        ff = '<product>%s<difference>%s%s</difference></product>' % (_p('ap/thrust-per-deg'), _p('ap/gamma-deg'), _p('ap/bias-gamma-deg'))
        if CFG_THRUST_FF:
            ff = '<product>%s<sum><difference>%s%s</difference><difference>%s%s</difference></sum></product>' % (
                _p('ap/thrust-per-deg'), _p('ap/gamma-deg'), _p('ap/bias-gamma-deg'), _p('ap/cfg-drag-deg'), _p('ap/bias-cfg-deg'))
        thrust_sum, thrust_desc = _op('sum', _p('ap/bias-throttle'), _p('ap/thrust-pi'), ff), 'the thrust that holds the speed: the throttle at engagement, the path angle\'s feed-forward and the speed error\'s integral'
    else:
        thrust_sum, thrust_desc = _op('sum', _p('ap/bias-throttle'), _p('ap/thrust-pi')), ''
    if THRUST_ANTIWINDUP:
        ch.append(_fn('ap/thrust-speed-raw', thrust_sum, 'the speed law\'s throttle before its limits (the integral looks at it)'))
        ch.append(_fn('ap/thrust-speed', _p('ap/thrust-speed-raw'), thrust_desc, clip=('0', '1')))
    else:
        ch.append(_fn('ap/thrust-speed', thrust_sum, thrust_desc, clip=('0', '1')))
    ch.append(_fn('ap/taxi-error-kt', _op('difference', _p('ap/taxi-speed-kt'), _p('ap/ground-speed-kt'))))
    ch.append(_trigger('taxi', 'ap/thrust-mode == 4', 'ap/taxi-speed-kt gt 0.5'))
    ch.append(_pid('ap/taxi-throttle', 'ap/taxi-error-kt', 0.03, 0.003, 'taxi', clip=('0', '0.4')))
    ch.append('''    <switch name="ap/thrust-law">
      <default value="ap/throttle-cmd"/>
      <test value="fcs/throttle-cmd-norm">ap/manual ge 1</test>
      <test value="0">ap/land-mode == 1</test>
      <test value="ap/taxi-throttle">ap/thrust-mode == 4</test>
      <test value="1">ap/thrust-mode == 1</test>
      <test value="0">ap/thrust-mode == 2</test>
      <test value="ap/thrust-speed">ap/thrust-mode == 3</test>
    </switch>
    <switch name="ctl/throttle-norm">
      <description>what the engine takes: the laws' throttle when engaged, the throttle command otherwise; the gust system's while it is on in the landing</description>
      <default value="fcs/throttle-cmd-norm"/>
      <test value="ap/gs-throttle">ap/gs-on == 1</test>
      <test value="ap/throttle-slewed">ap/engaged == 1</test>
    </switch>''')
    # The throttle the engine takes: the laws' throttle with its rate limited, in the vertical modes in the air (a climb entered by a step to full thrust was a pull-up of 1.6 g; the speed
    # law's own changes are slow). JSBSim's actuator limits a rate property-valued only downwards, so it is done here: the last frame's value moved towards the law's at THROTTLE_SLEW_UP
    # per second at most going up and THROTTLE_SLEW going down; following the throttle the engine has while the laws are off (so that engaging them is no step) and the law's while the aircraft is landing, on the ground or flown by hand.
    ch.append(_fn('ap/throttle-slewed-next', '''        <ifthen>
          <and><eq>%s%s</eq><ge>%s%s</ge><le>%s%s</le><eq>%s%s</eq><eq>%s%s</eq><eq>%s%s</eq></and>
          <sum>%s<max><product>%s%s%s</product><min><product>%s%s</product><difference>%s%s</difference></min></max></sum>
          %s
        </ifthen>''' % (_p('ap/engaged'), _v(1), _p('ap/pitch-mode'), _v(1), _p('ap/pitch-mode'), _v(2), *((_p('ap/flare'), _v(0)) if THROTTLE_SLEW_LAND else (_p('ap/land-mode'), _v(0))), _p('ap/on-mains'), _v(0), _p('ap/manual'), _v(0),
                        _p('ap/throttle-slewed'), '<product>%s%s%s</product>' % (_v(-THROTTLE_PATH_RATE_DOWN), _p('ap/thrust-per-deg'), '') if THROTTLE_PATH_RATE else _v(-THROTTLE_SLEW), _p('simulation/dt'), '', '<product>%s%s<ifthen><and><eq>%s%s</eq><eq>%s%s</eq></and>%s%s</ifthen></product>' % ('<ifthen><eq>%s%s</eq>%s%s</ifthen>' % (_p('ap/ga-on'), _v(1), _v(GA_THROTTLE_RATE), _v(THROTTLE_PATH_RATE)), _p('ap/thrust-per-deg'), _p('ap/pitch-mode'), _v(2), _p('ap/thrust-mode'), _v(3), _v(THROTTLE_MODE2_X), _v(1)) if THROTTLE_PATH_RATE else _v(THROTTLE_SLEW_UP), _p('simulation/dt'), _p('ap/thrust-law'), _p('ap/throttle-slewed'),
                        '<ifthen><eq>%s%s</eq>%s%s</ifthen>' % (_p('ap/engaged'), _v(0), _p('fcs/throttle-cmd-norm'), _p('ap/thrust-law'))),
                  'the laws\' throttle with its rate limited in the vertical modes in the air: THROTTLE_SLEW_UP per second going up, THROTTLE_SLEW going down', out='ap/throttle-slewed'))
    # ---- part B: the glide path on spoilers
    ch.append(_fn('ap/glide-height-ft', '        <sum>%s%s<product>%s<max>%s%s</max></product></sum>' % (
        _p('ap/rwy-elev-ft'), _v(5.3), _v(GLIDE_TAN), _v(0), _p('ap/leg-togo-ft')), 'height of the glide path here: the leg ends at the aiming point'))
    ch.append(_fn('ap/glide-error-ft', _op('difference', _p('position/h-sl-ft'), _p('ap/glide-height-ft')), 'high is positive (not clipped: the lead is compared with it, and the lead can be 300 ft or more)', clip=('-3000', '3000')))
    ch.append(_fn('ap/glide-sink-error-fps', '        <sum>%s<product>%s%s</product></sum>' % (_p('velocities/h-dot-fps'), _v(GLIDE_TAN), _p('velocities/vg-fps')),
                  'sinking less than the path asks is positive'))
    # the profile: the sink the aircraft should lack at this height off the path. On the path none; below it the sink it can still lose
    # before it arrives, at the most GLIDE_AZ (the square root of twice that times the height), and near the path no more than a
    # first-order approach with GLIDE_TAU (height / tau): the arrival is tangent, as the end of a turn is
    e, ea = _p('ap/glide-error-ft'), '<abs>%s</abs>' % _p('ap/glide-error-ft')
    mag = '<min><quotient>%s%s</quotient><pow><product>%s%s%s</product>%s</pow></min>' % (ea, _v(GLIDE_TAU), _v(2 * GLIDE_AZ), '', ea, _v(0.5))
    ch.append(_fn('ap/glide-sink-want-fps', '        <ifthen><gt>%s%s</gt><product>%s%s</product>%s</ifthen>' % (e, _v(0), _v(-1), mag, mag),
                  'the sink the aircraft should lack at this height off the path (sinking less than the path asks is positive): none on it, below it the profile\'s'))
    ch.append(_fn('ap/glide-track-fps', _op('difference', _p('ap/glide-sink-error-fps'), _p('ap/glide-sink-want-fps')),
                  'the sink the aircraft lacks less what the profile asks: nothing when it flies the profile, ft/s'))
    # the lead: the height under the path at which the profile asks for exactly the sink the aircraft lacks now, r (the path's fall in
    # ground speed, so the wind, less its own sink): the larger of r tau and r^2 / 2a. The task takes the glide over there, and
    # the law starts on its profile with no step in the spoilers
    r_lack = '<max>%s%s</max>' % (_v(0), _p('ap/glide-sink-error-fps'))
    ch.append(_fn('ap/glide-lead-ft', '        <max><product>%s%s</product><quotient><pow>%s%s</pow>%s</quotient></max>' % (r_lack, _v(GLIDE_TAU), r_lack, _v(2), _v(2 * GLIDE_AZ)),
                  'the height under the path the glide is taken over at: where the profile asks for the sink the aircraft lacks'))
    ch.append(_trigger('glide', 'ap/land-mode == 1', 'ap/flare == 0', 'ap/rollout == 0', 'ap/glide-error-ft lt %g' % GLIDE_IBAND, 'ap/glide-error-ft gt %g' % -GLIDE_IBAND))
    ch.append(_pid('ap/glide-i', 'ap/glide-track-fps', 0.0, GLIDE_KIS, 'glide', clip=('-%g' % GLIDE_ICLIP, '%g' % GLIDE_ICLIP)))
    ch.append(_fn('ap/spoiler-glide', '        <sum>%s<product>%s%s</product>%s</sum>' % (_v(SPOILER_BASE), _v(GLIDE_KS), _p('ap/glide-track-fps'), _p('ap/glide-i')),
                  'spoilers hold the glide path: they follow the profile', clip=('0.10', '1')))
    ch.append('''    <switch name="ap/latch-spoiler-base">
      <description>the spoiler setting at the start of the flare</description>
      <default value="ap/spoiler-base"/>
      <test value="ap/spoiler-glide">ap/flare == 0</test>
      <output>ap/spoiler-base</output>
    </switch>''')
    ch.append(_fn('ap/flare-sink-wanted-fps', '        <max>%s<product>%s%s<quotient>%s%s</quotient></product></max>' % (
        _v(FLARE_SINK), _v(GLIDE_TAN), _p('velocities/vg-fps'), _p('aero/wheel-height-ft'), _p('ap/flare-height-ft')),
        'the sink wanted in the flare: the approach\'s, falling with height to %.1f ft/s at the ground' % FLARE_SINK))
    ch.append(_fn('ap/spoiler-flare', '        <sum>%s<product>%s<sum>%s%s</sum></product></sum>' % (
        _p('ap/spoiler-base'), _v(FLARE_GAIN), _p('velocities/h-dot-fps'), _p('ap/flare-sink-wanted-fps')),
        'in the flare the spoilers work on sink rate alone: they come in as far as the sink needs', clip=('0.10', '1')))
    ch.append('''    <switch name="ap/spoiler-law">
      <default value="ctl/manual-spoiler-norm"/>
      <test value="ctl/manual-spoiler-norm">ap/manual ge 1</test>
      <test value="1">ap/rollout == 1</test>
      <test value="ap/spoiler-flare">ap/flare == 1</test>
      <test value="ap/spoiler-glide">ap/land-mode == 1</test>
      <test value="ap/spoiler-cmd">ap/spoiler-mode == 1</test>
    </switch>
    <switch name="ap/sel-spoiler">
      <default value="ctl/manual-spoiler-norm"/>
      <test value="ap/spoiler-law">ap/engaged == 1</test>
    </switch>''')
    # The glide's capture moves the spoilers at a limited rate (GLIDE_SPOILER_RATE a second), from the flare's start the law's own. The profile asks the sink to build up at 0.15 g at once
    # (a first-order approach with GLIDE_TAU from 80 ft under the path) and the feedback answered with the spoilers from 0.67 to 0.90 in half a second (a lift step of 0.13 g at 25,000 lb:
    # Nz 0.86 at the landing's start in the whole mission and in FlightGear). The spoilers' lift is about 0.6 g for the whole travel: 0.1 a second is 0.03 g in half a second.
    # Following the selection (bumpless) while the landing is not on, the flare, the rollout or the laws are not.
    ch.append(_fn('ap/sel-spoiler-slewed-next', '''        <ifthen>
          <and><eq>%s%s</eq><eq>%s%s</eq><eq>%s%s</eq><eq>%s%s</eq><eq>%s%s</eq><eq>%s%s</eq></and>
          <sum>%s<max><product>%s%s</product><min><product>%s%s</product><difference>%s%s</difference></min></max></sum>
          %s
        </ifthen>''' % (_p('ap/engaged'), _v(1), _p('ap/land-mode'), _v(1), _p('ap/flare'), _v(0), _p('ap/rollout'), _v(0), _p('ap/on-mains'), _v(0), _p('ap/manual'), _v(0),
                        _p('ap/sel-spoiler-slewed'), _v(-GLIDE_SPOILER_RATE), _p('simulation/dt'), _v(GLIDE_SPOILER_RATE), _p('simulation/dt'), _p('ap/sel-spoiler'), _p('ap/sel-spoiler-slewed'), _p('ap/sel-spoiler')),
                  'the spoiler selection with its rate limited while the glide is being flown (GLIDE_SPOILER_RATE a second), the selection itself otherwise', out='ap/sel-spoiler-slewed'))
    ch.append('''    <actuator name="ap/act-spoiler">
      <input>%s</input>
      <lag>10</lag>
      <rate_limit>0.667</rate_limit>
      <clipto><min>0</min><max>1</max></clipto>
    </actuator>
    <switch name="ctl/spoiler-norm">
      <description>spoilers, 0 to 1 (1 is 45 deg)</description>
      <default value="ap/act-spoiler"/>
      <test value="ap/sel-spoiler">ctl/instant == 1</test>
    </switch>''' % ('ap/sel-spoiler-slewed' if GLIDE_SPOILER_RATE else 'ap/sel-spoiler'))
    # ---- part B: brakes and nose-wheel steering
    ch.append(_fn('ap/decel-error-g', '        <sum>%s<quotient>%s%s</quotient></sum>' % (_v(DECEL_G), _p('accelerations/udot-ft_sec2'), _v(32.174)), 'wanted deceleration less the present one'))
    ch.append(_trigger('decel', 'ap/rollout == 1', 'gear/unit[0]/WOW == 1', 'ap/ground-speed-kt gt 15'))
    ch.append(_pid('ap/brake-decel', 'ap/decel-error-g', 0.0, 0.8, 'decel', clip=('0', '1')))
    ch.append(_fn('ap/brake-taxi', '''        <ifthen>
          <and><lt>%s%s</lt><lt>%s%s</lt></and>
          %s
          <product>%s<difference><difference>%s%s</difference>%s</difference></product>
        </ifthen>''' % (_p('ap/taxi-speed-kt'), _v(0.5), _p('ap/ground-speed-kt'), _v(1.5), _v(1), _v(0.6), _p('ap/ground-speed-kt'), _p('ap/taxi-speed-kt'), _v(0.2)),
                  'taxi: brakes when over the speed, held on when stopped', clip=('0', '1')))
    ch.append('''    <switch name="ap/brake-law">
      <default value="0"/>
      <test value="ap/brake-decel">ap/rollout == 1</test>
      <test value="ap/brake-taxi">ap/thrust-mode == 4</test>
    </switch>''')
    for side in ('left', 'right'):
        ch.append(_fn('ap/brake-%s' % side, '        <ifthen><and><eq>%s%s</eq><eq>%s%s</eq></and>%s%s</ifthen>' % (_p('ap/engaged'), _v(1), _p('ap/manual'), _v(0), _p('ap/brake-law'), _p('fcs/%s-brake-cmd-norm' % side)),
                      out='fcs/%s-brake-cmd-norm' % side))
    ch.append(_fn('ap/steer-limit', '        <quotient>%s<max>%s%s</max></quotient>' % (_v(12), _v(1), _p('velocities/vg-fps')),
                  'nose-wheel travel allowed, falling with speed', clip=('0.08', '0.6')))
    ch.append(_fn('ap/steer-law', '''        <max>
          <product>%s%s</product>
          <min>%s<difference><product>%s%s</product><product>%s%s</product></difference></min>
        </max>''' % (_v(-1), _p('ap/steer-limit'), _p('ap/steer-limit'), _v(0.02), _p('ap/ground-error-deg'), _v(0.8), _p('velocities/r-rad_sec'))))
    ch.append(_fn('ap/steer-out-deg', '''        <product>
          %s
          <ifthen><and><eq>%s%s</eq><eq>%s%s</eq><eq>%s%s</eq></and>%s%s</ifthen>
        </product>''' % (_v(60), _p('ap/engaged'), _v(1), _p('ap/ground-steer'), _v(1), _p('ap/manual'), _v(0), _p('ap/steer-law'), _p('fcs/steer-cmd-norm')),
                  'the nose wheel: the law\'s when steering on the ground, the direct command otherwise', out='fcs/steer-pos-deg'))
    # ---- surfaces
    ch.append(_final('pitch-deg', 'ap/pitch-out-deg', 'ctl/manual-pitch-deg', 'both ruddervators, trailing edge down positive: nose down'))
    ch.append(_direct_latch('roll', 'ap/roll-law-deg'))
    ch.append(_fn('ap/roll-direct-deg', '        <difference><sum>%s<product>%s%s</product></sum><product>%s%s%s</product></difference>' % (
        _p('ap/direct-roll-deg'), _v(DIRECT['roll']), _p('ap/stick-roll'), _p('ap/k-p'), _v(57.29578), _p('velocities/p-rad_sec')),
        'direct law: the stick and roll-rate damping', clip=('-20', '20')))
    ch.append(_direct_latch('yaw', 'ap/yaw-law-deg'))
    ch.append(_fn('ap/yaw-direct-deg', '        <difference><sum>%s<product>%s%s</product></sum><product>%s%s%s</product></difference>' % (
        _p('ap/direct-yaw-deg'), _v(DIRECT['yaw']), _p('ap/pedal'), _p('ap/k-r'), _v(57.29578), _p('ap/yaw-rate-washed')),
        'direct law: the pedals and the yaw damper', clip=('-20', '20')))
    for ax in ('roll', 'yaw'):
        ch.append('''    <switch name="ap/%s-out-deg">
      <default value="ap/%s-law-deg"/>
      <test value="ap/%s-direct-deg">ap/manual == 2</test>
    </switch>''' % (ax, ax, ax))
    ch.append(_final('roll-cmd-deg', 'ap/roll-out-deg', 'ctl/manual-roll-deg', 'roll command, right wing down positive'))
    ch.append(_final('yaw-deg', 'ap/yaw-out-deg', 'ctl/manual-yaw-deg', 'ruddervators against each other, nose right positive'))
    # ---- structural limits (section 7.3): assumed, not published. Always running
    ch.append('''    <switch name="limits/latch-overstress">
      <description>past a limit: load factor %(n1)g or %(n0)g, %(v)g KEAS, Mach %(m)g. Latched until limits/reset. Load factor counts in the air only: on the wheels it is the gear's</description>
      <default value="limits/overstress"/>
      <test value="0">limits/reset == 1</test>
      <test logic="OR" value="1">
        velocities/ve-kts gt %(v)g
        velocities/mach gt %(m)g
        <test logic="AND">
          ap/on-mains == 0
          accelerations/Nz gt %(n1)g
        </test>
        <test logic="AND">
          ap/on-mains == 0
          accelerations/Nz lt %(n0)g
        </test>
      </test>
      <output>limits/overstress</output>
    </switch>
    <switch name="limits/latch-failed">
      <description>past an ultimate: load factor %(u1)g or %(u0)g, %(vf)g KEAS. The structure is taken to have failed</description>
      <default value="limits/failed"/>
      <test value="0">limits/reset == 1</test>
      <test logic="OR" value="1">
        velocities/ve-kts gt %(vf)g
        <test logic="AND">
          ap/on-mains == 0
          accelerations/Nz gt %(u1)g
        </test>
        <test logic="AND">
          ap/on-mains == 0
          accelerations/Nz lt %(u0)g
        </test>
      </test>
      <output>limits/failed</output>
    </switch>''' % dict(n1=LIMIT_NZ[1], n0=LIMIT_NZ[0], u1=1.5 * LIMIT_NZ[1], u0=1.5 * LIMIT_NZ[0], v=LIMIT_KEAS, m=LIMIT_MACH, vf=FAIL_KEAS))
    ch.append(_fn('ctl/aileron-deg', _op('product', _v(-1), _p('ctl/roll-cmd-deg')),
                  'ailerons as the aerodynamic tables take them: right trailing edge down positive, which rolls left'))
    if MISSION_VERTICAL:
        ch += _mission_vertical()
    if MISSION_PHASES:
        ch += _mission_phases()
    ch += _gust_system()[1]
    props += ''.join('  <property value="%g">nav/%s</property>\n' % (v, k) for k, v in (
        [('%s-on' % n, 1) for n in NAVS] + [('%s-%s-error-deg' % (n, a), 0) for n in NAVS for a in ('roll', 'pitch')] +
        [('roll-deg', 0), ('pitch-deg', 0), ('miscompare', 0), ('miscompare-reset', 0)]))
    return '''<?xml version="1.0"?>
<!-- Generated by fdm/genghawk.py (fdm/laws.py). The flight laws: our own design, the real ones are not public.
     ap/engaged = 0 leaves the surfaces on the direct commands. -->
<system name="laws">
%s  <channel name="flight laws">
%s
  </channel>
</system>
''' % (props, '\n'.join(ch))
