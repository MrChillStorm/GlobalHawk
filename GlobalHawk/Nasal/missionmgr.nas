# The mission manager: it hands the flight laws their next leg, target and mode ten times a second and does nothing
# else (docs/FLIGHT-LAWS.md, section 5). This is fdm/missionmgr.py in Nasal, line for line: the Python one flies
# the checks in JSBSim alone, this one flies in FlightGear. Change both together.
#
# A plan is a vector of items (hashes):
#   {kind:"taxi", points:[[lat, lon], ...], speed:15, turn_speed:8}
#   {kind:"takeoff", start:[lat, lon], end:[lat, lon], elev:2300}
#   {kind:"route", points:[[lat, lon, alt_ft], ...]}        may carry start:[lat, lon]
#   {kind:"land", fix:[lat, lon], aim:[lat, lon], elev:2300}
#   {kind:"hold", centre:[lat, lon], alt:20000}
#   (made by the manager, not given:) {kind:"go_around", ...}   the landing's entry contract broken: a circle over the fix down to the final's height, then the landing
#   (made by the manager, not given:) {kind:"route", ga:{...}, ...}   the missed approach: the stabilised-approach gate broken on the glide: the climb-out and a right-hand circuit back to the fix, then the landing again
# lost_link: items flown instead of the rest once ap/link-lost is set. sites: runways for a landing without the engine.

var J = "/fdm/jsbsim/";

# What FlightGear writes into the flight model every frame from its own controls: these are set there, or
# FlightGear would write them back.
var CONTROLS = {
    "gear/gear-cmd-norm": "/controls/gear/gear-down",
    "fcs/elevator-cmd-norm": "/controls/flight/elevator",
    "fcs/aileron-cmd-norm": "/controls/flight/aileron",
    "fcs/rudder-cmd-norm": "/controls/flight/rudder",              # FlightGear passes it on with the sign turned
    "fcs/throttle-cmd-norm": "/controls/engines/engine/throttle",  # globalhawk.nas copies it on
    "fcs/speedbrake-cmd-norm": "/controls/flight/speedbrake",
    "fcs/left-brake-cmd-norm": "/controls/gear/brake-left",
    "fcs/right-brake-cmd-norm": "/controls/gear/brake-right",
};
var fget = func(p) {
    var v = getprop(J ~ p);
    return v == nil ? 0 : v;
};
var fset = func(p, v) {
    if (contains(CONTROLS, p)) {
        if (p == "fcs/rudder-cmd-norm") v = -v;
        setprop(CONTROLS[p], v);
    } else setprop(J ~ p, v);
};

var FT_PER_DEG = 364567.2;
var NM = 6076.1;
var D2R = math.pi / 180.0;
var NOSE_FT = 24.6;                # ft: the aircraft's nose (FlightGear's position for it, and the station's) is this far ahead of the centre of gravity the laws steer (GlobalHawk.xml: VRP x 0, CG x 294.98 in)
var GLIDE_TAN = 0.07782;           # the approach path, 4.45 deg (fdm/laws.py)
var CAPTURE_SPEED_KT = 10.0;       # the glide is taken over only within this many kt of the approach speed: 30 kt over it the speed-by-elevator law pitched up 15 deg and the aircraft zoomed through the path
var GLIDE_CL = 0.8;                # the lift coefficient of the glide without the engine
var GLIDE_RATIO = 20.0;            # what the planner counts on: the model's 26 less a margin for wind and turns
var ENTRY_HEIGHT = 2500.0;         # ft above the runway on the glide path: where the entry point is
var TURN_COST = 300.0;             # ft per 90 deg of turn
var IN_HAND = 1000.0;              # ft kept over at the entry point when choosing a site
var CIRCLE_BANK = 15.0;            # deg
var FINAL_SURPLUS = 300.0;         # ft above the glide path the circle aims to leave for the final
var WING_AREA = 540.0;
var K_PSI = 1.2;                   # the heading law's gain (fdm/laws.py), deg of bank per deg at 600 ft/s
var MAX_ALT = 65000.0;             # ft: the aircraft's maximum (NASA 2008)
# the level-off (fdm/missionmgr.py, docs/PLAN.md "Level-off"): the altitude mode takes over where the capture's profile asks for exactly the climb rate there is
var LANDING_LEVEL = 1;             # the level-off before a landing is flown in the landing configuration: the spoilers end at LANDING_SPOILER and the gear goes down as it begins (retracted to nothing and put out again at the landing's start they dipped it 21 ft)
var LANDING_SPOILER = 0.667;      # the spoilers' command in the landing configuration, before the glide path is taken (the laws' spoiler base)
var LEVEL_BEGIN_FT = 400.0;        # the landing keeps the level's height command while the aircraft is within this of it
var HOLD_BANK = 11.5;              # deg: a hold's circle is flown well inside the bank limit

# the landing task's entry contract and the go-around task it hands over to when the contract is broken (docs/PLAN.md, "The aircraft refuses what it cannot fly")
var ENTRY_CAPTURE_W = [12000.0, 20000.0, 26000.0];    # weights, lb, and ...
var ENTRY_CAPTURE_FT = [500.0, 1500.0, 2000.0];        # ... ft above the path at 10 nmi the capture still takes over by 1.5 nmi out: flown, above.py
var ENTRY_MARGIN = 0.8;            # of that
var ENTRY_TOGO_MIN_NM = 1.5;       # to go at which no height above the path is taken; the limit grows from there with the way to go ...
var ENTRY_SPAN_NM = 8.5;           # ... as the 10 nmi it was measured at (1.5 to 10 nmi) ...
var ENTRY_TOGO_MAX_NM = 12.0;      # ... and no further (not measured beyond)
var LAND_FIX_GAP_FT = 2634.0;      # the height under the glide path the final is begun from: the capture gap flown (2,484 ft, fdm/capability.py) and the planner's 150 ft
var GO_AROUND_MIN_AGL = 1000.0;    # ft over the ground: the go-around's circle comes down to this at the least
var GO_AROUND_ALT_ABOVE = 100.0;   # ft: the go-around hands back to the landing no higher than this over the height it came down to (the capture gap has 150 ft of margin) ...
var GO_AROUND_ALT_BELOW = 300.0;   # ... and no lower than this under it ...
var GO_AROUND_FIX_FT = 2500.0;     # ... within this of the fix ...
var GO_AROUND_TRACK_DEG = 20.0;    # ... on a track within this of the final's course
# the stabilised-approach gate and the missed approach (docs/PLAN.md, "The approach that cannot hold its line")
var GATE = 1;                      # 1: the landing's glide is watched and a missed approach is flown when it is not stable
var GATE_TOP_FT = 1000.0;          # ft over the runway: the gate looks from here down to the decision height ...
var GATE_DH_FT = 150.0;            # ... below which the aircraft is committed (a go-around from the flare's last seconds is no safer than the landing)
var GATE_LINE_FT = [15.0, 0.3];    # ft off the line the gate allows, at a height h: the first plus the second times h (315 ft at 1,000 ft, 165 at 500, 60 at 150)
var GATE_PATH_FT = [15.0, 0.2];    # ft off the glide path, the same way (215, 115, 45)
var GATE_SLOW_KT = 15.0;           # kt under the approach speed
var GATE_FAST_KT = 20.0;           # kt over it
var GATE_PERSIST_S = 2.0;          # s: a gust is not a reason; the limit has to be passed this long
var GA_CLIMBOUT_FT = 2.0 * NM;     # ft past the aiming point the missed approach climbs out straight ahead, on the final's line ...
var GA_OFFSET_FT = 2.0 * NM;       # ... turns right and flies out this far to the side ...
var GA_EXTRA_FT = 3.0 * NM;        # ... flies back downwind to this far behind the fix, and turns right twice onto the final's line, so that the final is this long before the fix
var GA_CIRCUIT_ABOVE_FT = 1000.0;  # ft: the circuit is flown this far above the height the final is begun from, and the last leg comes down to it
var GA_GEAR_UP_FT = 150.0;         # ft of height gained, climbing: the gear comes up (the landing puts it down again where the circuit levels at the fix)
var GA_FREE_FT = 1000.0;           # ft of height gained: the go-around's own speed and rates are given up to the route's
var GA_MAX = 2;                    # missed approaches the manager flies; the next one it holds over the fix and asks the operator
var go_arounds = 0;                # how many go-arounds any manager has begun: the checks that should land at once count on it being 0 (a go-around hides nothing)

var mod = func(a, b) { return a - b * math.floor(a / b); };
var clip = func(x, lo, hi) { return x < lo ? lo : (x > hi ? hi : x); };
var absv = func(x) { return x < 0 ? -x : x; };
var maxv = func(a, b) { return a > b ? a : b; };
var minv = func(a, b) { return a < b ? a : b; };
var tand = func(d) { return math.sin(d * D2R) / math.cos(d * D2R); };
var atan2d = func(y, x) { return math.atan2(y, x) / D2R; };
var opt = func(h, k, d) { return (contains(h, k) and h[k] != nil) ? h[k] : d; };
var copy = func(h) { var o = {}; foreach (var k; keys(h)) o[k] = h[k]; return o; };

# course and distance (deg, ft) from a to b
var course = func(a, b) {
    var dn = (b[0] - a[0]) * FT_PER_DEG;
    var de = (b[1] - a[1]) * FT_PER_DEG * math.cos(a[0] * D2R);
    return [mod(atan2d(de, dn), 360.0), math.sqrt(dn * dn + de * de)];
};
var turn = func(c0, c1) { return mod(c1 - c0 + 180.0, 360.0) - 180.0; };
var offset = func(p, brg_deg, dist) {       # the point a distance from p on a bearing
    var c = brg_deg * D2R;
    return [p[0] + dist * math.cos(c) / FT_PER_DEG, p[1] + dist * math.sin(c) / (FT_PER_DEG * math.cos(p[0] * D2R))];
};

var Manager = {
    new: func(plan, lost_link = nil, sites = nil) {
        var m = { parents: [Manager] };
        m.plan = plan;
        m.lost_link = lost_link;
        m.sites = sites == nil ? [] : sites;
        m.contingency = nil;
        m.alert = nil;
        m.waiting = nil;                  # the hold of a taxi item the aircraft is stopped at, until the station clears it (docs/PLAN.md, "Hold points and clearances")
        m.i = 0;
        m.k = 0;
        m.done = 0;
        m.vmode = nil;
        m.missed = 0;
        m.events = [];
        m.begin();
        return m;
    },
    note: func(text) { append(me.events, [fget("simulation/sim-time-sec"), text]); },
    leg: func(a, b) {
        fset("ap/leg-lat0-deg", a[0]); fset("ap/leg-lon0-deg", a[1]);
        fset("ap/leg-lat1-deg", b[0]); fset("ap/leg-lon1-deg", b[1]);
    },
    here: func { return [fget("position/lat-geod-deg"), fget("position/long-gc-deg")]; },

    # the point the leg that ends item i's last waypoint is followed by: a landing's aiming point, else none
    after: func(i) {
        var nxt = i + 1 < size(me.plan) ? me.plan[i + 1] : nil;
        return (nxt != nil and nxt.kind == "land") ? [nxt.aim[0], nxt.aim[1]] : nil;
    },

    set_next: func(p) {
        if (p == nil) fset("ap/next-valid", 0);
        else {
            fset("ap/next-lat-deg", p[0]);
            fset("ap/next-lon-deg", p[1]);
            fset("ap/next-valid", 1);
        }
    },
    track: func { return atan2d(fget("velocities/v-east-fps"), fget("velocities/v-north-fps")); },
    rest: func { return me.i + 1 < size(me.plan) ? subvec(me.plan, me.i + 1) : []; },
    upto: func { return subvec(me.plan, 0, me.i + 1); },          # the plan as far as the item being flown

    # set the laws up for the item that starts now
    begin: func {
        if (me.i >= size(me.plan)) { me.done = 1; return; }
        var it = me.plan[me.i];
        me.k = 0;
        var kind = it.kind;
        me.note("begin " ~ kind);
        var vm = int(fget("ap/vmode") + 0.5);                # what the laws' vertical task was doing, before this item takes it over
        var lv = fget("ap/v-level-alt");
        fset("ap/vt-on", 0); fset("ap/sp-ext", -1); fset("ap/vt-sp-end", 0);
        fset("ap/tk-done", 0); fset("ap/ld-captured", 0);                 # the laws' latches start clear: the item may follow one of its own kind in the same call, and they would never see the task off
        fset("ap/tk-on", 0); fset("ap/tx-on", 0); fset("ap/ld-on", 0); fset("ap/ci-on", 0);          # the laws' takeoff, taxi, landing and circle tasks: each item turns on its own
        fset("ap/ga-on", 0);                                           # the laws' go-around task (the missed approach's climb-out): the item that is one turns it on
        fset("ap/next-valid", 0);
        fset("ap/turn-ack", fget("ap/turn-done"));
        if (kind == "taxi") {
            var pts = [me.here()] ~ it.points;
            it._pts = pts;
            me.leg(pts[0], pts[1]);
            fset("ap/land-mode", 0);
            fset("ap/thrust-mode", 4); fset("ap/ground-steer", 1); fset("ap/pitch-mode", 0); fset("ap/roll-mode", 0);
            fset("ap/spoiler-mode", 1); fset("ap/spoiler-cmd", 0.0);
            fset("ap/taxi-speed-kt", opt(it, "speed", 15.0));
            fset("ap/tx-fast", opt(it, "speed", 15.0)); fset("ap/tx-slow", opt(it, "turn_speed", 8.0)); fset("ap/tx-stop", opt(it, "stop", 1) ? 1 : 0);
            me.taxi_leg(it);
            fset("ap/tx-on", 1);
            fset("gear/gear-cmd-norm", 1);
        } elsif (kind == "takeoff") {
            me.leg(it.start, it.end);
            fset("ap/taxi-speed-kt", 0.0);
            fset("ap/thrust-mode", 1); fset("ap/ground-steer", 1); fset("ap/pitch-mode", 3); fset("ap/roll-mode", 2);
            fset("ap/spoiler-mode", 1); fset("ap/spoiler-cmd", 0.0);
            fset("ap/tk-on", 1);
        } elsif (kind == "route") {
            var first = opt(it, "start", nil) != nil ? [it.start[0], it.start[1]] : me.here();
            var pts = [[first[0], first[1], fget("position/h-sl-ft")]] ~ it.points;
            it._pts = pts;
            me.leg(pts[0], pts[1]);
            fset("ap/roll-mode", 2); fset("ap/ground-steer", 0);
            if (opt(it, "ga", nil) != nil) {
                fset("ap/land-mode", 0);                             # the landing task is left: the glide's laws go with it
                fset("ap/ga-h0-ft", fget("position/h-sl-ft")); fset("ap/ga-on", 1);
                it.ga.h0 = fget("position/h-sl-ft");
            }
            me.vertical(pts[1][2]);
        } elsif (kind == "land") {
            var above = me.above_path(it);
            if (above > me.entry_limit(course(me.here(), it.aim)[1])) {
                me.go_around(it, above);               # the entry contract is broken: nothing of the landing is set up
                return;
            }
            # level towards the runway in the landing configuration until the glide path comes down to the aircraft
            me.leg(it.fix, it.aim);
            fset("ap/rwy-elev-ft", it.elev);
            fset("ap/roll-mode", 3); fset("ap/ground-steer", 1);           # the landing task's own lateral law
            # the height asked for stays the level's if its capture is going on (the aircraft was still coming down to it: a command of the height it has this moment is a step in
            # what the altitude mode asks), else it is the height it has; the spoilers go out as a ramp (it was a step of 0.12 to 0.67: a load factor of 1.31 and the speed 11 kt down)
            var h0 = fget("position/h-sl-ft");
            fset("ap/alt-cmd-ft", (vm == 3 and absv(lv - h0) <= LEVEL_BEGIN_FT) ? lv : h0);
            fset("ap/pitch-mode", 2); fset("ap/thrust-mode", 3);
            fset("ap/speed-schedule", 0);
            fset("ap/speed-cmd-kcas", fget("ap/approach-keas"));
            fset("ap/sp-ext", LANDING_SPOILER);          # the laws move the spoilers there at their slew rate, from where they are
            fset("gear/gear-cmd-norm", 1);
            it._on_path = 0;
            fset("ap/ld-on", 1);
        } elsif (kind == "hold" or kind == "go_around") {
            fset("ap/land-mode", 0);
            fset("ap/roll-mode", 1); fset("ap/ground-steer", 0);
            it.side = 1.0;
            if (opt(it, "radius", nil) == nil) it.radius = me.hold_radius();      # fixed once the hold begins: the station draws it
            fset("ap/ci-lat", it.centre[0]); fset("ap/ci-lon", it.centre[1]); fset("ap/ci-radius-ft", it.radius); fset("ap/ci-side", it.side);
            fset("ap/ci-out-max", 30.0); fset("ap/ci-lead", 1); fset("ap/ci-on", 1);          # the laws fly the circle: the heading command about the centre
            me.vertical(it.alt);
        } elsif (kind == "engine_out") {
            me.choose_site(it);
            fset("ap/land-mode", 0);
            fset("ap/roll-mode", 2); fset("ap/ground-steer", 0);
            fset("ap/pitch-mode", 1); fset("ap/thrust-mode", 2); fset("ap/speed-schedule", 0);
            fset("ap/spoiler-mode", 1); fset("ap/spoiler-cmd", 0.0);
            fset("gear/gear-cmd-norm", 0);
            fset("ap/speed-cmd-kcas", me.glide_kcas());
            me.leg(me.here(), it.entry);
            it.task = "glide";
            me.note("glide to " ~ opt(it.site, "name", "the runway"));
        }
    },

    # ---- without the engine (section 6.3)
    # the calibrated airspeed for the glide's lift coefficient at this weight and height
    glide_kcas: func {
        var q = fget("inertia/weight-lbs") / (GLIDE_CL * WING_AREA);
        var p = fget("atmosphere/P-psf");
        var mach = math.sqrt(q / (0.7 * p));
        var qc = p * (math.pow(1 + 0.2 * mach * mach, 3.5) - 1);
        return 661.4786 * math.sqrt(5 * (math.pow(qc / 2116.2166 + 1, 2 / 7.0) - 1));
    },
    # the entry point: on the extended centreline where the glide path is ENTRY_HEIGHT above the runway
    entry: func(site) { return offset(site.aim, site.course + 180.0, ENTRY_HEIGHT / GLIDE_TAN); },
    # height left over at a site's entry point, by the planner's book: what there is less what is needed
    reach: func(site) {
        var cd = course(me.here(), me.entry(site));
        var need = cd[1] / GLIDE_RATIO + TURN_COST * absv(turn(me.track(), cd[0])) / 90.0 + site.elev + ENTRY_HEIGHT + IN_HAND;
        return fget("position/h-sl-ft") - need;
    },
    choose_site: func(it) {
        var self = me;
        var ranked = sort(me.sites, func(a, b) { var d = self.reach(b) - self.reach(a); return d < 0 ? -1 : (d > 0 ? 1 : 0); });
        var best = ranked[0];
        if (me.reach(best) < 0) {
            # nothing in reach: towards the nearest all the same, and say so. A landing off a runway is not built.
            foreach (var s; me.sites)
                if (course(me.here(), me.entry(s))[1] < course(me.here(), me.entry(best))[1]) best = s;
            me.alert = "no runway in reach";
            me.note("ALERT: no runway in reach");
        }
        it.site = best; it.entry = me.entry(best); it.expected = me.reach(best) + IN_HAND;
        var all = "";
        foreach (var s; ranked) all ~= (all == "" ? "" : ", ") ~ sprintf("%s %+.0f", opt(s, "name", "?"), me.reach(s) + IN_HAND);
        me.note(sprintf("site %s: %.0f ft expected in hand at the entry point (%s)", opt(best, "name", "?"), it.expected, all));
    },
    engine_out: func(it) {
        var site = it.site;
        var ent = it.entry;
        if (it.task == "glide") fset("ap/speed-cmd-kcas", me.glide_kcas());
        elsif (it.task == "circle") fset("ap/speed-cmd-kcas", fget("ap/approach-keas"));
        var vg = maxv(fget("velocities/vg-fps"), 100.0);
        var radius = vg * vg / (32.174 * tand(CIRCLE_BANK));
        var cd = course(me.here(), ent);
        var above = fget("position/h-sl-ft") - site.elev - ENTRY_HEIGHT;
        if (it.task == "glide") {
            it.surplus = above - cd[1] / GLIDE_RATIO;
            if (cd[1] < radius) {
                # circle on the side the aircraft is on, so that the circle touches the centreline at the entry point
                var side = turn(site.course, course(ent, me.here())[0]) >= 0 ? 1.0 : -1.0;
                it.side = side; it.task = "circle"; it.arrived = above;
                fset("ap/roll-mode", 1);
                fset("ap/speed-cmd-kcas", fget("ap/approach-keas"));     # with spoilers out the glide speed is too near the limit
                me.note(sprintf("circle %s over the entry point, %.0f ft above the glide path there (planner expected %.0f)",
                                side > 0 ? "right" : "left", above, it.expected));
            }
        }
        if (it.task == "circle") {
            var side = it.side;
            var centre = offset(ent, site.course + 90.0 * side, radius);
            var od = course(centre, me.here());                     # bearing from the centre to the aircraft, and distance
            var tangent = od[0] + 90.0 * side;
            fset("ap/heading-cmd-deg", mod(tangent + side * clip(60.0 * (od[1] - radius) / radius, -45.0, 80.0), 360.0));
            # the way round to the entry point, which is where the circle touches the centreline
            var at_entry = mod(site.course - 90.0 * side, 360.0);   # bearing from the centre to the entry point
            var arc = mod((at_entry - od[0]) * side, 360.0);
            if (arc > 340.0) arc -= 360.0;                          # just past it
            var surplus = above - arc * D2R * radius / GLIDE_RATIO;
            it.surplus = surplus;
            fset("ap/spoiler-cmd", clip((surplus - FINAL_SURPLUS) / 1000.0, 0.0, 1.0));
            var aligned = absv(turn(me.track(), site.course)) < 20.0 and absv(arc) < 30.0;
            if ((aligned and surplus < 2.0 * FINAL_SURPLUS) or surplus < -500.0) {
                it.task = "final"; it.final = surplus;
                me.leg(ent, site.aim);
                fset("ap/rwy-elev-ft", site.elev);
                fset("ap/roll-mode", 2); fset("ap/ground-steer", 1);
                fset("ap/land-mode", 1);
                fset("gear/gear-cmd-norm", 1);
                me.note(sprintf("final, %.0f ft above the glide path", surplus));
            }
        } elsif (it.task == "final") {
            if (fget("ap/rollout") == 1 and fget("ap/ground-speed-kt") < 15.0) {
                me.note("rollout over");
                fset("ap/taxi-speed-kt", 0.0);
                fset("ap/thrust-mode", 4);
                me.next();
            }
        }
    },

    # Tell the laws what the taxi leg is: the last one, or ends in a bend of so many degrees (they work out the speed from the way to go).
    # the hold of a taxi item at point i (a leg k ends at the item's point k), or nil
    hold_at: func(it, i) {
        var hs = opt(it, "holds", nil);
        if (hs == nil) return nil;
        foreach (var h; hs) if (h.i == i) return h;
        return nil;
    },

    # the station clears the hold the aircraft is stopped at: the taxi goes on to the next leg, or, if the hold was the item's last point, the item is over
    clear: func {
        var w = me.waiting;
        var it = me.plan[me.i];
        me.waiting = nil;
        me.note("cleared at " ~ w.id);
        var pts = it._pts;
        if (me.k == size(pts) - 2) me.next();
        else {
            me.k += 1;
            me.leg(pts[me.k], pts[me.k + 1]);
            me.taxi_leg(it);
        }
    },

    taxi_leg: func(it) {
        var pts = it._pts;
        var last = me.k == size(pts) - 2;
        var hold = me.hold_at(it, me.k) != nil;
        last = last or hold;                                          # a leg that ends at a hold is a last leg: the laws stop at its end
        if (hold) {
            var a = pts[me.k];
            var b = pts[me.k + 1];
            var cd = course(a, b);
            var back = minv(NOSE_FT, cd[1] / 2.0);                    # the leg is shortened by the nose's reach: it is the nose that stops short of the hold point, not the centre of gravity
            me.leg(a, [b[0] - back * math.cos(cd[0] * D2R) / FT_PER_DEG, b[1] - back * math.sin(cd[0] * D2R) / (FT_PER_DEG * math.cos(b[0] * D2R))]);
        }
        fset("ap/tx-last", last ? 1 : 0);
        fset("ap/tx-stop", (hold or opt(it, "stop", 1)) ? 1 : 0);
        if (!last) fset("ap/tx-bend-deg", absv(turn(course(pts[me.k], pts[me.k + 1])[0], course(pts[me.k + 1], pts[me.k + 2])[0])));
    },
    hold_radius: func {
        var vg = maxv(fget("velocities/vg-fps"), 100.0);
        return vg * vg / (32.174 * tand(HOLD_BANK));
    },

    # feet above the glide path to the aiming point (negative under it): the landing task's entry contract is judged on this
    above_path: func(land) {
        var h = fget("position/h-sl-ft") - land.elev;
        return h - (5.3 + GLIDE_TAN * course(me.here(), land.aim)[1]);
    },
    # how far above the path the landing may be begun, ft, by the way to go
    entry_limit: func(togo_ft) {
        var w = fget("inertia/weight-lbs");
        var cap10 = ENTRY_CAPTURE_FT[0];
        if (w >= ENTRY_CAPTURE_W[2]) cap10 = ENTRY_CAPTURE_FT[2];
        elsif (w >= ENTRY_CAPTURE_W[1]) cap10 = ENTRY_CAPTURE_FT[1] + (ENTRY_CAPTURE_FT[2] - ENTRY_CAPTURE_FT[1]) * (w - ENTRY_CAPTURE_W[1]) / (ENTRY_CAPTURE_W[2] - ENTRY_CAPTURE_W[1]);
        elsif (w > ENTRY_CAPTURE_W[0]) cap10 = ENTRY_CAPTURE_FT[0] + (ENTRY_CAPTURE_FT[1] - ENTRY_CAPTURE_FT[0]) * (w - ENTRY_CAPTURE_W[0]) / (ENTRY_CAPTURE_W[1] - ENTRY_CAPTURE_W[0]);
        return ENTRY_MARGIN * cap10 * maxv(0.0, minv(togo_ft / NM, ENTRY_TOGO_MAX_NM) - ENTRY_TOGO_MIN_NM) / ENTRY_SPAN_NM;
    },
    # the landing task's entry contract is broken (too high to take the path over): the go-around task takes the aircraft: a right-hand circle
    # tangent to the final's line at the fix, down to the height the final is begun from, then back to the landing
    go_around: func(land, above) {
        var fix = land.fix;
        var cd = course(fix, land.aim);
        var r = me.hold_radius();
        var centre = offset(fix, cd[0] + 90.0, r);
        var alt = land.elev + maxv(GO_AROUND_MIN_AGL, math.floor((5.3 + GLIDE_TAN * cd[1] - LAND_FIX_GAP_FT) / 100.0) * 100.0);
        go_arounds += 1;
        me.note(sprintf("LANDING NOT COMMITTED: %.0f ft above the glide path; go-around, circling over the fix to %.0f ft", above, alt));
        var ga = { kind: "go_around", reason: "above the glide path", above: above, centre: centre, radius: r, alt: alt, final: cd[0], fix: [fix[0], fix[1]], side: 1.0 };
        me.plan = subvec(me.plan, 0, me.i) ~ [ga] ~ subvec(me.plan, me.i);
        me.begin();
    },
    # the go-around's contract with the landing: at the height it came down to, at the fix, on the final's course
    go_around_over: func(it) {
        var d = course(it.fix, me.here())[1];
        var dh = fget("position/h-sl-ft") - it.alt;
        return (dh >= -GO_AROUND_ALT_BELOW and dh <= GO_AROUND_ALT_ABOVE and d <= GO_AROUND_FIX_FT
                and absv(turn(fget("ap/ground-track-deg"), it.final)) <= GO_AROUND_TRACK_DEG);
    },

    # the stabilised-approach gate: on the glide, from GATE_TOP_FT of height down to the decision height, the aircraft must be within the funnel of GATE_LINE_FT, GATE_PATH_FT and the speed's
    # limits for GATE_PERSIST_S together; if it is not, the landing task has broken its contract with the flare and the missed approach takes the aircraft
    gate: func(it) {
        var h = fget("position/h-sl-ft") - it.elev - 5.3;              # the height over the runway (the wheel height reads no more than 1,000 ft)
        if (!(GATE and it._on_path and fget("ap/flare") == 0 and fget("ap/on-mains") == 0 and fget("ap/manual") == 0 and fget("ap/rollout") == 0
              and h >= GATE_DH_FT and h <= GATE_TOP_FT)) {
            it._gate_t = nil;
            return 0;
        }
        var xt = fget("ap/leg-xt-ft");
        var ge = fget("ap/glide-error-ft");
        var se = fget("ap/speed-error-kt");
        var why = nil;
        if (absv(xt) > GATE_LINE_FT[0] + GATE_LINE_FT[1] * h)
            why = sprintf("%.0f ft %s of the line at %.0f ft", absv(xt), xt > 0 ? "right" : "left", h);
        elsif (absv(ge) > GATE_PATH_FT[0] + GATE_PATH_FT[1] * h)
            why = sprintf("%.0f ft %s the glide path at %.0f ft", absv(ge), ge > 0 ? "above" : "below", h);
        elsif (se > GATE_FAST_KT or se < -GATE_SLOW_KT)
            why = sprintf("%.0f kt %s the approach speed at %.0f ft", absv(se), se > 0 ? "over" : "under", h);
        var now = fget("simulation/sim-time-sec");
        if (why == nil) {
            it._gate_t = nil;
            return 0;
        }
        if (opt(it, "_gate_t", nil) == nil) it._gate_t = now;
        if (now - it._gate_t < GATE_PERSIST_S) return 0;
        me.missed_approach(it, why);
        return 1;
    },
    # the landing task's glide broke the gate: the climb-out straight ahead on the final's line to the circuit's height, a right-hand circuit (out to the side, downwind, back onto the
    # line GA_EXTRA_FT behind the fix) and the landing again from the fix, as the landing is begun. The next time it is needed the aircraft holds over the fix and asks the operator
    missed_approach: func(land, why) {
        var fix = land.fix;
        var aim = land.aim;
        var cd = course(fix, aim);
        var fc = cd[0];
        var d = cd[1];
        go_arounds += 1;
        me.missed += 1;
        var alt = land.elev + maxv(GO_AROUND_MIN_AGL, math.floor((5.3 + GLIDE_TAN * d - LAND_FIX_GAP_FT) / 100.0) * 100.0);          # the height the final is begun from, as the entry contract's go-around has it
        var c = fc * D2R;
        var at = func(a, b) {           # a feet along the final's course and b to the right of it from the aiming point, on a flat earth about it (as Field.ll)
            var n = a * math.cos(c) - b * math.sin(c);
            var e = a * math.sin(c) + b * math.cos(c);
            return [aim[0] + n / FT_PER_DEG, aim[1] + e / (FT_PER_DEG * math.cos(aim[0] * D2R))];
        };
        var circuit = alt + GA_CIRCUIT_ABOVE_FT;
        if (me.missed > GA_MAX) {
            # the third time: the same climb-out, then a hold over the fix (a right-hand circle tangent to the final's line there), until the operator decides
            var rad = me.hold_radius();
            var pa = at(GA_CLIMBOUT_FT, 0.0);
            var centre = at(-d, rad);
            me.note(sprintf("LANDING ABANDONED: %s; climbing out and holding over the fix at %.0f ft", why, circuit));
            var ra = { kind: "route", points: [[pa[0], pa[1], circuit]], ga: { why: why, attempt: me.missed, alt: circuit, fix_alt: alt, abandoned: 1 } };
            var ha = { kind: "hold", centre: centre, alt: circuit, radius: rad, abandoned: why };
            me.plan = subvec(me.plan, 0, me.i) ~ [ra, ha] ~ subvec(me.plan, me.i);
            me.begin();
            return;
        }
        var back = d + GA_EXTRA_FT;
        var p1 = at(GA_CLIMBOUT_FT, 0.0);
        var p2 = at(GA_CLIMBOUT_FT, GA_OFFSET_FT);
        var p3 = at(-back, GA_OFFSET_FT);
        var p4 = at(-back, 0.0);
        var pts = [[p1[0], p1[1], circuit], [p2[0], p2[1], circuit], [p3[0], p3[1], circuit], [p4[0], p4[1], circuit], [fix[0], fix[1], alt]];
        me.note(sprintf("MISSED APPROACH: %s; climbing out and round for another approach (attempt %d)", why, me.missed));
        var r = { kind: "route", points: pts, ga: { why: why, attempt: me.missed, alt: circuit, fix_alt: alt } };
        me.plan = subvec(me.plan, 0, me.i) ~ [r] ~ subvec(me.plan, me.i);
        me.begin();
    },

    # leave the plan when the link is lost or the engine stops. Only in the air, and only once each
    contingencies: func {
        var kind = me.plan[me.i].kind;
        if (fget("engine/failed") == 1 and me.contingency != "engine" and (kind == "route" or kind == "land" or kind == "hold" or kind == "go_around")
            and size(me.sites) and fget("ap/rollout") == 0) {
            me.contingency = "engine";
            me.note("ENGINE FAILED");
            me.plan = me.upto() ~ [{ kind: "engine_out" }];
            me.next();
        } elsif (fget("ap/link-lost") == 1 and me.contingency == nil and (kind == "route" or kind == "hold" or kind == "go_around")
                 and me.lost_link != nil and size(me.lost_link)) {
            me.contingency = "link";
            me.note("LINK LOST: the contingency route");
            var items = [];
            foreach (var d; me.lost_link) append(items, copy(d));
            me.plan = me.upto() ~ items;
            me.next();
        }
    },

    # Ask the laws for a climb, a descent or a hold towards a height (fdm/laws.py, _mission_vertical: the gate, the mode and the spoilers are theirs); path: the height is the one at the
    # end of the leg, and a descent steers its slope with the spoilers to get there. What is read back is the mode, for the status and the notes.
    vertical: func(alt, path = nil) {
        fset("ap/vt-on", 1); fset("ap/vt-ft", alt); fset("ap/vt-path", path ? 1 : 0);
        var mode = [nil, "climb", "descent", "level"][int(fget("ap/vmode") + 0.5)];
        if (mode != nil and me.vmode != mode) {
            me.vmode = mode;
            me.note(sprintf("%s to %.0f ft", mode, alt));
        }
    },

    step: func {
        if (me.done) return;
        me.contingencies();
        if (me.done) return;
        var it = me.plan[me.i];
        var kind = it.kind;
        var togo = fget("ap/leg-togo-ft");
        if (kind == "engine_out") { me.engine_out(it); return; }
        if (kind == "go_around") {
            me.vertical(it.alt);
            if (me.go_around_over(it)) {
                me.note("go-around over: back on the final");
                me.next();                                      # the landing's contract is judged again as it begins
            }
            return;
        }
        if (kind == "hold") {
            me.vertical(it.alt);
            return;
        }
        if (kind == "taxi") {
            var pts = it._pts;
            if (me.waiting != nil) return;                        # stopped at a hold: nothing moves until clear()
            if (fget("ap/tx-leg") == 1) {                         # the laws: the next leg is to be taken
                me.k += 1;
                me.leg(pts[me.k], pts[me.k + 1]);
                me.taxi_leg(it);
            } elsif (fget("ap/tx-done") == 1) {                   # the laws: the item (or the leg to a hold) is over
                var hold = me.hold_at(it, me.k);
                if (hold == nil) me.next();
                else {
                    me.waiting = { i: hold.i, id: hold.id, name: hold.name, kind: hold.kind, since: fget("simulation/sim-time-sec") };
                    me.note("holding at " ~ hold.id ~ ": " ~ hold.name);
                }
            }
        } elsif (kind == "takeoff") {
            if (fget("ap/tk-done") == 1) {                          # the laws took it up: schedule, pitch mode, nose wheel; the gear lever is the supervisor's (FlightGear copies /controls/gear/gear-down into the model every frame, over what the laws write)
                fset("gear/gear-cmd-norm", 0);
                me.note("airborne, climb");
                me.next();
            }
        } elsif (kind == "route") {
            # the turn onto the next leg is the aircraft's (fdm/laws.py, ap/turn-*): the manager gives it the next waypoint and moves on when
            # the laws say the turn is done. Past the last waypoint of a route that a landing follows the next point is the aiming point
            var pts = it._pts;
            if (opt(it, "ga", nil) != nil) {
                var gained = fget("position/h-sl-ft") - it.ga.h0;
                if (fget("gear/gear-cmd-norm") > 0.5 and gained >= GA_GEAR_UP_FT and fget("velocities/h-dot-fps") > 0.0) {
                    fset("gear/gear-cmd-norm", 0);
                    me.note("missed approach: positive climb, gear up");
                }
                if (fget("ap/ga-on") == 1 and gained >= GA_FREE_FT) fset("ap/ga-on", 0);          # the route's speed and rates from here
            }
            me.vertical(opt(it, "alt_override", pts[me.k + 1][2]), 1);
            var last = me.k == size(pts) - 2;
            if (last and LANDING_LEVEL and me.i + 1 < size(me.plan) and me.plan[me.i + 1].kind == "land") {
                # a landing follows: the level-off of the descent ends in the landing configuration (the laws take the spoilers there as they level), and the gear goes down as the level begins
                fset("ap/vt-sp-end", LANDING_SPOILER);
                if (int(fget("ap/vmode") + 0.5) == 3 and int(fget("ap/v-level-from") + 0.5) == 2 and fget("gear/gear-cmd-norm") < 0.5) {
                    fset("gear/gear-cmd-norm", 1);
                    me.note("gear down for the landing");
                }
            }
            var nxt = !last ? pts[me.k + 2] : me.after(me.i);
            me.set_next(nxt);
            if (fget("ap/turn-done") > fget("ap/turn-ack")) {
                fset("ap/turn-ack", fget("ap/turn-done"));
                if (last) me.next();
                else {
                    me.k += 1;
                    it.alt_override = nil;
                    me.leg(pts[me.k], pts[me.k + 1]);
                    me.note(sprintf("leg %d", me.k + 1));
                }
            } elsif (last and nxt == nil and togo < 500.0) {
                me.next();
            }
        } elsif (kind == "land") {
            if (me.gate(it)) return;
            if (!it._on_path) {
                if (fget("ap/ld-captured") == 1) {                    # the laws took the glide over: the pitch mode, the land mode, the spoilers
                    it._on_path = 1;
                    me.note("glide path");
                }
            } elsif (fget("ap/ld-done") == 1) {
                me.note("rollout over");
                me.next();
            }
        }
    },
    next: func {
        me.i += 1;
        me.begin();
    },
};
