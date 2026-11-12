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
    # FlightGear puts the aircraft into the air untrimmed, and the first moments can pass a structural limit that no
    # flight did: the limits' latches are cleared once the start is over
    setprop(J ~ "limits/reset", 1);
    settimer(func { setprop(J ~ "limits/reset", 0); }, airborne ? 5 : 1);
    setprop("/sim/globalhawk/started", airborne ? "air" : "ground");
};

setlistener("/sim/signals/fdm-initialized", func {
    every_frame.start();
    # An air start begins with the throttle closed. The laws take the throttle they find as their starting point and
    # correct it slowly, so they are given a cruise setting to start from, not idle (with idle it glided for minutes).
    if (in_air()) setprop("/controls/engines/engine/throttle", 0.2);     # about what level flight at 20,000 ft takes
    settimer(engage, 2);          # once the flight model has run a moment from its starting state
}, 0, 0);

# The aircraft's own head-up display in place of FlightGear's standard one (Huds/hud.nas): first in FlightGear's
# list of HUDs, and loaded at once if one is already up.
var own_hud = func {
    var first = props.globals.getNode("/sim/hud/hud-list/hud[0]", 1);
    first.getNode("name", 1).setValue("Global Hawk nose camera");
    first.getNode("description", 1).setValue("The aircraft's own: green, conformal, with the flight laws' targets and limits.");
    first.getNode("path", 1).setValue(getprop("/sim/aircraft-dir") ~ "/Huds/hud.nas");
    aircraft.HUD.currentHUDIndex = 0;
    aircraft.HUD.load_current_HUD();
    # on from the start: the nose camera is this aircraft's cockpit (h switches it off, as on any aircraft)
    setprop("/sim/hud/visible", 1);
    if (aircraft.HUD.currentHUD != nil) aircraft.HUD.currentHUD.set_visibility(1);
};
setlistener("/sim/signals/fdm-initialized", func { settimer(own_hud, 0); }, 0, 0);       # at once: it is there when the picture is

# For the sounds: the inside loops (what a microphone in the nose bay would hear) play in the two cameras' views, the
# outside loops in the others (Sounds/globalhawk-sound.xml). The cameras are not views FlightGear calls internal: as
# one, FlightGear drew the nose's skin round the camera. So the aircraft keeps its own switch.
var inside_sounds = func {
    var view = getprop("/sim/current-view/name") or "";
    setprop("/sim/sound/pywopwop/inside", (view == "Nose Camera" or view == "Belly Camera") ? 1 : 0);
};
setlistener("/sim/current-view/name", inside_sounds, 1, 0);

# The menu's Autostart and Shutdown: the engine's master switch (the flight model's engine/master). The aircraft
# comes with its engine running, as the ground crew hands it over; no start sequence is modelled, the rotors come up
# to idle in about half a minute.
var autostart = func {
    if (getprop(J ~ "engine/failed")) { gui.popupTip("The engine has failed: no restart is modelled", 5); return; }
    if ((getprop(J ~ "fuel/total-lbs") or 0) < 1) { gui.popupTip("No fuel", 5); return; }
    if (getprop(J ~ "engine/master") and getprop(J ~ "engine/running")) { gui.popupTip("The engine is running", 3); return; }
    setprop("/controls/engines/engine/throttle", 0);
    setprop(J ~ "engine/master", 1);
    gui.popupTip("Engine starting: at idle in about half a minute", 5);
};
var shutdown = func {
    if ((getprop(J ~ "aero/wheel-height-ft") or 0) > 20) { gui.popupTip("In the air: the engine is left running", 5); return; }
    setprop("/controls/engines/engine/throttle", 0);
    setprop("/controls/gear/brake-parking", 1);
    setprop(J ~ "engine/master", 0);
    gui.popupTip("Engine shut down, parking brake set", 5);
};

# The lamps (Models/GlobalHawk.xml shows each while its property is true): navigation lights steady, the wing tips'
# white strobes flashing, the red beacons flashing slower; by FlightGear's own lighting switches.
var LAMPS = "/sim/model/globalhawk/lights/";
setlistener("/sim/signals/fdm-initialized", func {
    foreach (var k; ["nav-lights", "strobe", "beacon"])
        if (getprop("/controls/lighting/" ~ k) == nil) setprop("/controls/lighting/" ~ k, 1);
    props.globals.getNode(LAMPS ~ "nav", 1).setBoolValue(getprop("/controls/lighting/nav-lights") ? 1 : 0);
    setlistener("/controls/lighting/nav-lights", func(n) { setprop(LAMPS ~ "nav", n.getBoolValue() ? 1 : 0); }, 0, 0);
    # a lamp that flashes: on for a moment every period, while its switch is on
    var flash = func(lamp, on_s, period_s, switch) {
        var loop = func {
            if (getprop(switch)) {
                setprop(LAMPS ~ lamp, 1);
                settimer(func { setprop(LAMPS ~ lamp, 0); }, on_s);
            } else setprop(LAMPS ~ lamp, 0);
            settimer(loop, period_s);
        };
        loop();
    };
    flash("strobe", 0.07, 1.3, "/controls/lighting/strobe");
    flash("beacon", 0.14, 1.2, "/controls/lighting/beacon");
}, 0, 0);
