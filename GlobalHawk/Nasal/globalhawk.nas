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

# ---- a start in the air, from a trim
# FlightGear puts the aircraft into the air level, at idle, its surfaces neutral: no flight condition, and the first
# minute was the aircraft finding one. The flight model's own level trims are in trimtable.nas (fdm/trimtable.py):
# the angle of attack, the pitch command and the throttle by height, airspeed and weight. The start takes them.
var trim_at = func(alt, kcas, weight) {
    var frac = func(grid, x) {
        var n = size(grid);
        if (x <= grid[0]) return 0;
        if (x >= grid[n - 1]) return n - 1;
        for (var i = 0; i < n - 1; i += 1) if (x < grid[i + 1]) return i + (x - grid[i]) / (grid[i + 1] - grid[i]);
        return n - 1;
    };
    var f = [frac(TRIM.alt, alt), frac(TRIM.kcas, kcas), frac(TRIM.weight, weight)];
    var lo = [math.floor(f[0]), math.floor(f[1]), math.floor(f[2])];
    var hi = [math.min(lo[0] + 1, size(TRIM.alt) - 1), math.min(lo[1] + 1, size(TRIM.kcas) - 1), math.min(lo[2] + 1, size(TRIM.weight) - 1)];
    var out = [];
    foreach (var table; [TRIM.alpha, TRIM.elevator, TRIM.throttle]) {
        var sum = 0;
        var whole = 1;
        foreach (var a; [0, 1]) foreach (var b; [0, 1]) foreach (var c; [0, 1]) {
            var share = (a ? f[0] - lo[0] : 1 - (f[0] - lo[0])) * (b ? f[1] - lo[1] : 1 - (f[1] - lo[1])) * (c ? f[2] - lo[2] : 1 - (f[2] - lo[2]));
            if (share == 0) continue;
            var v = table[a ? hi[0] : lo[0]][b ? hi[1] : lo[1]][c ? hi[2] : lo[2]];
            if (v == nil) { whole = 0; continue; }
            sum += v * share;
        }
        if (!whole) return nil;                              # a corner has no level trim: no flight condition here
        append(out, sum);
    }
    return out;
};

# Not every start asked for is a flight condition: with full tanks the aircraft cannot fly level at 60,000 ft at any
# speed (the first start there took the nearest trim in the table and stalled). The start keeps the height asked for
# and gives way on the rest: first fuel (the weight it would have burned down to by then), then speed.
var flyable = func(alt, kcas, weight) {
    foreach (var dk; [0, 5, -5, 10, -10, 15, -15, 20, -20, 30, -30, 40, -40, 50, -50])
        for (var w = weight; w >= TRIM.weight[0]; w -= 250) {
            var t = trim_at(alt, kcas + dk, w);
            if (t != nil) return { trim: t, kcas: kcas + dk, weight: w };
        }
    return nil;
};

var burn_down_to = func(weight) {
    var tanks = props.globals.getNode("/consumables/fuel").getChildren("tank");
    var fuel = 0;
    foreach (var tank; tanks) fuel += tank.getValue("level-lbs") or 0;
    var keep = math.max(0, fuel - ((getprop(J ~ "inertia/weight-lbs") or weight) - weight));
    if (fuel > 0) foreach (var tank; tanks) tank.setValue("level-lbs", (tank.getValue("level-lbs") or 0) * keep / fuel);
    return keep;
};

# FlightGear also starts the flight in the wrong air: its wind is 37 kt at the first frames and then blends to the
# wind aloft within two seconds (measured: the airspeed thrown 20 ft/s either way, the sideslip to 8 deg). So the
# flight model is held until the wind has moved and come to rest, then set down again on the trim in that air, and
# let go.
var air_start = func {
    # the speed asked for is the one held; with none asked, the laws' own schedule for this height: a calibrated
    # airspeed low down, a Mach number above (the flight model's initial conditions turn that into an airspeed)
    var want = { alt: getprop(J ~ "ic/h-sl-ft"), kcas: getprop("/sim/presets/airspeed-kt") or 0, psi: getprop(J ~ "ic/psi-true-deg") };
    var asked = want.kcas >= 50;
    if (!asked) {
        want.kcas = TRIM.schedule_kcas;
        if (want.alt > TRIM.schedule_mach_from_ft) {
            setprop(J ~ "ic/mach", getprop(J ~ "ap/schedule-mach") or 0.6);
            want.kcas = math.round(getprop(J ~ "ic/vc-kts"));
        }
    }
    var weight = getprop(J ~ "inertia/weight-lbs") or 26750;
    var found = flyable(want.alt, want.kcas, weight);
    if (found == nil) {
        gui.popupTip(sprintf("No level flight at %d ft: the aircraft is left as FlightGear started it", want.alt), 15);
        setprop("/sim/globalhawk/started", "untrimmed");
        engage();
        return;
    }
    var t = found.trim;
    var told = "";
    if (found.weight < weight - 1) told = sprintf("fuel down to %d lb, the most it flies level with at %d ft", burn_down_to(found.weight), want.alt);
    if (found.kcas != want.kcas) {
        told ~= (told == "" ? "" : "; ") ~ sprintf("%d KCAS, the nearest to %d that it flies level at there", found.kcas, want.kcas);
        want.kcas = found.kcas;
        asked = 1;
    }
    if (told != "") gui.popupTip("Started with " ~ told, 15);
    setprop("/sim/globalhawk/trim/told", told);
    setprop(J ~ "simulation/pause", 1);
    var wind = func [getprop("/environment/wind-from-north-fps") or 0, getprop("/environment/wind-from-east-fps") or 0];
    var apart = func(a, b) math.abs(a[0] - b[0]) + math.abs(a[1] - b[1]);
    var first = wind();
    var was = first;
    var moved = 0;
    var still = 0;
    var waited = 0;
    var watch = maketimer(0.1, func {
        var now = wind();
        if (apart(now, first) > 0.5) moved = 1;
        still = apart(now, was) < 0.02 ? still + 1 : 0;
        was = now;
        waited += 1;
        # at rest for half a second after it has moved; a wind that never moves was right from the start
        if (still < 5 or (!moved and waited < 60)) return;
        watch.stop();
        # the trim's state: the height, the airspeed (which gives the true one), the nose on the heading at the trim's
        # angle of attack, wings level; and last the velocity over the ground, which leaves the attitude alone: level,
        # along the heading, and carried by the wind (FlightGear's is where it blows from)
        setprop(J ~ "ic/h-sl-ft", want.alt);
        setprop(J ~ "ic/vc-kts", want.kcas);
        var vt = getprop(J ~ "ic/vt-fps");
        foreach (var kv; [["phi-deg", 0], ["theta-deg", t[0]], ["psi-true-deg", want.psi], ["p-rad_sec", 0], ["q-rad_sec", 0], ["r-rad_sec", 0],
                          ["vn-fps", vt * math.cos(want.psi * D2R) - now[0]], ["ve-fps", vt * math.sin(want.psi * D2R) - now[1]], ["vd-fps", 0]])
            setprop(J ~ "ic/" ~ kv[0], kv[1]);
        # the throttle and the stick where the trim has them, and the flight model's lags (the engine's, the wing's
        # bending) at their settled values at once
        setprop("/controls/engines/engine/throttle", t[2]);
        setprop(J ~ "ap/throttle-cmd", t[2]);
        setprop("/controls/flight/elevator", t[1]);
        setprop(J ~ "ctl/instant", 1);
        setprop(J ~ "simulation/reset", 1);
        setprop(J ~ "simulation/pause", 0);
        # the lags run as they are from the next frames on, and then the laws take over (switched on while the lags
        # were still instant, the thrust loop ran the throttle up to 0.49 from the trim's 0.20)
        settimer(func {
            setprop(J ~ "ctl/instant", 0);
            settimer(func {
                engage();
                setprop(J ~ "ap/alt-cmd-ft", want.alt);
                setprop(J ~ "ap/heading-cmd-deg", want.psi);
                if (asked) {
                    setprop(J ~ "ap/speed-cmd-kcas", want.kcas);
                    setprop(J ~ "ap/speed-schedule", 0);
                }
                settimer(func { setprop("/controls/flight/elevator", 0); }, 1.0);
            }, 0.1);
        }, 0.1);
        setprop("/sim/globalhawk/trim/alpha-deg", t[0]);
        setprop("/sim/globalhawk/trim/throttle", t[2]);
        setprop("/sim/globalhawk/trim/waited-sec", waited * 0.1);
    });
    watch.simulatedTime = 1;
    watch.start();
};

setlistener("/sim/signals/fdm-initialized", func {
    # a ground station connected before the flight model loaded leaves the properties it listens to without their
    # starting values (defaults.nas says how): given here
    foreach (var name; keys(DEFAULTS)) if (getprop(J ~ name) == nil) setprop(J ~ name, DEFAULTS[name]);
    every_frame.start();
    if (in_air()) air_start();
    else settimer(engage, 2);                                # on the ground: once it has settled on its wheels
}, 0, 0);

# ---- ground to the horizon
# FlightGear loads terrain 30 km around the aircraft, which from 60,000 ft is a slab in the middle of nothing: the
# horizon is 550 km away. (Earthview, the globe the Space Shuttle draws beyond the terrain, lost its shaders with
# FlightGear 2024.2 and draws nothing.) So the terrain range grows with the height above the ground, 12 times it and
# 250 km at most: far tiles come in coarse and cost little (34 frames a second with either range at 60,000 ft over
# Helsinki). The range is the user's own setting and is saved when FlightGear exits, so it is put back on the way
# down, when the option is switched off (the Global Hawk menu) and at exit.
var FAR = "/sim/globalhawk/far-scenery";
var RANGE = "/sim/rendering/static-lod/bare-delta";
var own_range = getprop(RANGE) or 21000;
if (getprop(FAR) == nil) setprop(FAR, 1);
var far_scenery = maketimer(5, func {
    var want = own_range;
    if (getprop(FAR)) want = math.max(own_range, math.min(250000, 12 * (getprop("/position/altitude-agl-ft") or 0) * FT2M));
    if (math.abs(want - getprop(RANGE)) > 0.1 * want) setprop(RANGE, want);
});
far_scenery.start();
setlistener(FAR, func(n) { if (!n.getValue()) setprop(RANGE, own_range); });
setlistener("/sim/signals/exit", func { far_scenery.stop(); setprop(RANGE, own_range); });

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

# The exterior lights (Models/Lights, made by fdm/ghlights.py), as the X-57's: the wing tips' strobes and the beacons
# flash whenever they are switched on; the position lights' halos show in poor light.
var LAMPS = "/sim/model/globalhawk/lighting/";
var strobes = props.globals.initNode(LAMPS ~ "strobes", 0, "BOOL");
var beacons = props.globals.initNode(LAMPS ~ "beacons", 0, "BOOL");
aircraft.light.new(LAMPS ~ "strobe-left", [0.05, 1.00], strobes);
aircraft.light.new(LAMPS ~ "strobe-right", [0.05, 1.00], strobes);
aircraft.light.new(LAMPS ~ "beacon", [0.10, 1.10], beacons);      # both beacons together
var lamps = maketimer(0.5, func {
    var dim = (getprop("/environment/visibility-m") or 20000) < 5000 or (getprop("/sim/time/sun-angle-rad") or 0) > 1.4;
    strobes.setBoolValue(getprop("/controls/lighting/strobe") ? 1 : 0);
    beacons.setBoolValue(getprop("/controls/lighting/beacon") ? 1 : 0);
    setprop(LAMPS ~ "nav", (getprop("/controls/lighting/nav-lights") and dim) ? 1 : 0);
});
lamps.start();
