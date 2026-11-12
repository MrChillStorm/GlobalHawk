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
var GLIDE_TAN = 0.07782;           # the approach path, 4.45 deg (fdm/laws.py)
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
var HOLD_BANK = 11.5;              # deg: a hold's circle is flown well inside the bank limit

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
        m.i = 0;
        m.k = 0;
        m.done = 0;
        m.vmode = nil;
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
        if (kind == "taxi") {
            var pts = [me.here()] ~ it.points;
            it._pts = pts;
            me.leg(pts[0], pts[1]);
            fset("ap/land-mode", 0);
            fset("ap/thrust-mode", 4); fset("ap/ground-steer", 1); fset("ap/pitch-mode", 0); fset("ap/roll-mode", 0);
            fset("ap/spoiler-mode", 1); fset("ap/spoiler-cmd", 0.0);
            fset("ap/taxi-speed-kt", opt(it, "speed", 15.0));
            fset("gear/gear-cmd-norm", 1);
        } elsif (kind == "takeoff") {
            me.leg(it.start, it.end);
            fset("ap/taxi-speed-kt", 0.0);
            fset("ap/thrust-mode", 1); fset("ap/ground-steer", 1); fset("ap/pitch-mode", 3); fset("ap/roll-mode", 2);
            fset("ap/spoiler-mode", 1); fset("ap/spoiler-cmd", 0.0);
        } elsif (kind == "route") {
            var first = opt(it, "start", nil) != nil ? [it.start[0], it.start[1]] : me.here();
            var pts = [[first[0], first[1], fget("position/h-sl-ft")]] ~ it.points;
            it._pts = pts;
            me.leg(pts[0], pts[1]);
            fset("ap/roll-mode", 2); fset("ap/ground-steer", 0);
            me.vertical(pts[1][2]);
        } elsif (kind == "land") {
            # level towards the runway in the landing configuration until the glide path comes down to the aircraft
            me.leg(it.fix, it.aim);
            fset("ap/rwy-elev-ft", it.elev);
            fset("ap/roll-mode", 2); fset("ap/ground-steer", 1);
            fset("ap/alt-cmd-ft", fget("position/h-sl-ft"));
            fset("ap/pitch-mode", 2); fset("ap/thrust-mode", 3);
            fset("ap/speed-schedule", 0);
            fset("ap/speed-cmd-kcas", fget("ap/approach-keas"));
            fset("ap/spoiler-mode", 1); fset("ap/spoiler-cmd", 0.667);
            fset("gear/gear-cmd-norm", 1);
            it._on_path = 0;
        } elsif (kind == "hold") {
            fset("ap/land-mode", 0);
            fset("ap/roll-mode", 1); fset("ap/ground-steer", 0);
            it.side = 1.0;
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

    # the heading that flies a circle about a centre: the tangent, turned in or out for the distance off it
    circle: func(centre, radius, side, out_max = 45.0, lead = 0) {
        var od = course(centre, me.here());
        var ahead = 0.0;
        if (lead) {
            # the heading law banks in proportion to the heading error, so a steady turn needs the command ahead
            # of the nose by the error that gives the circle's bank (without it the hold sat 0.7 nmi outside)
            var vg = fget("velocities/vg-fps");
            var bank = math.atan2(vg * vg, 32.174 * radius) / D2R;
            ahead = bank / (K_PSI * maxv(fget("velocities/vt-fps"), 100.0) / 600.0);
        }
        fset("ap/heading-cmd-deg", mod(od[0] + 90.0 * side + side * (ahead + clip(60.0 * (od[1] - radius) / radius, -out_max, 80.0)), 360.0));
        return od;
    },
    hold_radius: func {
        var vg = maxv(fget("velocities/vg-fps"), 100.0);
        return vg * vg / (32.174 * tand(HOLD_BANK));
    },

    # leave the plan when the link is lost or the engine stops. Only in the air, and only once each
    contingencies: func {
        var kind = me.plan[me.i].kind;
        if (fget("engine/failed") == 1 and me.contingency != "engine" and (kind == "route" or kind == "land" or kind == "hold")
            and size(me.sites) and fget("ap/rollout") == 0) {
            me.contingency = "engine";
            me.note("ENGINE FAILED");
            me.plan = me.upto() ~ [{ kind: "engine_out" }];
            me.next();
        } elsif (fget("ap/link-lost") == 1 and me.contingency == nil and (kind == "route" or kind == "hold")
                 and me.lost_link != nil and size(me.lost_link)) {
            me.contingency = "link";
            me.note("LINK LOST: the contingency route");
            var items = [];
            foreach (var d; me.lost_link) append(items, copy(d));
            me.plan = me.upto() ~ items;
            me.next();
        }
    },

    # climb, descend or hold towards a height
    vertical: func(alt) {
        var h = fget("position/h-sl-ft");
        alt = minv(alt, MAX_ALT);
        fset("ap/alt-cmd-ft", alt);
        fset("ap/speed-schedule", 1);
        var mode = "";
        if (absv(alt - h) <= 150.0) {
            mode = "level";
            fset("ap/pitch-mode", 2); fset("ap/thrust-mode", 3); fset("ap/spoiler-cmd", 0.0);
        } elsif (alt > h) {
            mode = "climb";
            fset("ap/pitch-mode", 1); fset("ap/thrust-mode", 1); fset("ap/spoiler-cmd", 0.0);
        } else {
            mode = "descent";
            fset("ap/pitch-mode", 1); fset("ap/thrust-mode", 2); fset("ap/spoiler-cmd", 0.5);
        }
        fset("ap/spoiler-mode", 1);
        if (me.vmode != mode) {
            me.vmode = mode;
            me.note(sprintf("%s to %.0f ft", mode, alt));
        }
    },

    # call ten times a second
    step: func {
        if (me.done) return;
        me.contingencies();
        if (me.done) return;
        var it = me.plan[me.i];
        var kind = it.kind;
        var togo = fget("ap/leg-togo-ft");
        if (kind == "engine_out") { me.engine_out(it); return; }
        if (kind == "hold") {
            if (opt(it, "radius", nil) == nil) it.radius = me.hold_radius();      # fixed once the hold begins: the station draws it
            me.circle(it.centre, it.radius, it.side, 30.0, 1);
            me.vertical(it.alt);
            return;
        }
        if (kind == "taxi") {
            var pts = it._pts;
            var last = me.k == size(pts) - 2;
            var fast = opt(it, "speed", 15.0);
            if (!last) {
                var bend = absv(turn(course(pts[me.k], pts[me.k + 1])[0], course(pts[me.k + 1], pts[me.k + 2])[0]));
                # slow for the corner, then take the next leg a little before it
                var slow = opt(it, "turn_speed", 8.0);
                fset("ap/taxi-speed-kt", bend <= 20.0 ? fast : clip(slow + (fast - slow) * (togo - 100.0) / 250.0, slow, fast));
                if (togo < 40.0) {
                    me.k += 1;
                    me.leg(pts[me.k], pts[me.k + 1]);
                }
            } elsif (opt(it, "stop", 1)) {
                # come down to a walk, then stop on the point
                fset("ap/taxi-speed-kt", togo < 12.0 ? 0.0 : minv(fast, maxv(3.0, 0.12 * togo)));
                if (togo < 12.0 and fget("ap/ground-speed-kt") < 0.3) me.next();
            } elsif (togo < 40.0) me.next();
        } elsif (kind == "takeoff") {
            if (fget("aero/wheel-height-ft") > 100.0) {
                fset("gear/gear-cmd-norm", 0);
                fset("ap/speed-schedule", 1); fset("ap/pitch-mode", 1); fset("ap/ground-steer", 0);
                me.note("airborne, climb");
                me.next();
            }
        } elsif (kind == "route") {
            var pts = it._pts;
            me.vertical(opt(it, "alt_override", pts[me.k + 1][2]));
            var last = me.k == size(pts) - 2;
            var lead = 0.0;
            if (!last) {
                var c0 = course(pts[me.k], pts[me.k + 1])[0];
                var c1 = course(pts[me.k + 1], pts[me.k + 2])[0];
                var vg = fget("velocities/vg-fps");
                var radius = vg * vg / (32.174 * tand(maxv(fget("ap/bank-limit-deg") - 2.0, 5.0)));
                lead = radius * tand(absv(turn(c0, c1)) / 2.0) + 5.0 * vg;
            }
            if (togo < maxv(lead, 500.0)) {
                if (last) me.next();
                else {
                    me.k += 1;
                    it.alt_override = nil;
                    me.leg(pts[me.k], pts[me.k + 1]);
                    me.note(sprintf("leg %d", me.k + 1));
                }
            }
        } elsif (kind == "land") {
            if (!it._on_path) {
                fset("ap/speed-cmd-kcas", fget("ap/approach-keas"));
                if (fget("ap/glide-error-ft") > -10.0) {
                    it._on_path = 1;
                    fset("ap/pitch-mode", 1);
                    fset("ap/land-mode", 1);
                    me.note("glide path");
                }
            } elsif (fget("ap/rollout") == 1 and fget("ap/ground-speed-kt") < 15.0) {
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
