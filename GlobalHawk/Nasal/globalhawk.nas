# Global Hawk: what FlightGear has to do for the flight model at the start and every frame.
#
# - The flight model has no JSBSim engine object (its engine is a system of its own), so FlightGear does not pass
#   the throttle to it: it is copied here every frame.
# - The flight laws are on board (Systems/laws.xml). At the start they are switched on: in the air holding the
#   height, heading and scheduled speed the aircraft starts with; on the ground in the protected manual law, so
#   that a joystick flies it through its limits. The ground control station takes it from there.

var J = "/fdm/jsbsim/";

var every_frame = maketimer(0, func {
    setprop(J ~ "fcs/throttle-cmd-norm", getprop("/controls/engines/engine/throttle") or 0);
});

# FlightGear says whether it was asked to start on the ground; the height above it is not known until the scenery is in
var in_air = func { !getprop("/sim/presets/onground") and (getprop("/position/altitude-agl-ft") or 0) > 300; };

var engage = func {
    var airborne = in_air();
    setprop(J ~ "ap/theta-cmd-deg", getprop(J ~ "attitude/theta-deg") or 0);
    setprop(J ~ "ap/alt-cmd-ft", getprop(J ~ "position/h-sl-ft") or 0);
    setprop(J ~ "ap/heading-cmd-deg", getprop(J ~ "attitude/psi-deg") or 0);
    setprop(J ~ "ap/bank-cmd-deg", 0);
    setprop(J ~ "ap/gain-scale", 1);
    setprop(J ~ "ap/land-mode", 0);
    if (airborne) {
        # height, heading and the scheduled speed, held by the laws
        setprop("/controls/gear/gear-down", 0);
        setprop("/controls/gear/brake-parking", 0);
        setprop(J ~ "ap/speed-schedule", 1);
        setprop(J ~ "ap/pitch-mode", 2);
        setprop(J ~ "ap/roll-mode", 1);
        setprop(J ~ "ap/thrust-mode", 3);
        setprop(J ~ "ap/manual", 0);
    } else {
        # on the ground: the stick and the throttle lever, through the protected law
        setprop(J ~ "ap/pitch-mode", 0);
        setprop(J ~ "ap/roll-mode", 0);
        setprop(J ~ "ap/thrust-mode", 0);
        setprop(J ~ "ap/manual", 1);
    }
    setprop(J ~ "ap/engaged", 1);
    setprop("/sim/globalhawk/started", airborne ? "air" : "ground");
};

setlistener("/sim/signals/fdm-initialized", func {
    every_frame.start();
    # An air start begins with the throttle closed. The laws take the throttle they find as their starting point and
    # correct it slowly, so they are given a cruise setting to start from, not idle (with idle it glided for minutes).
    if (in_air()) setprop("/controls/engines/engine/throttle", 0.2);     # about what level flight at 20,000 ft takes
    settimer(engage, 2);          # once the flight model has run a moment from its starting state
}, 0, 0);
