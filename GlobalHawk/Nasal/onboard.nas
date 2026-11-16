# The aircraft's end of the command link (GlobalHawk/gcs/README.md): it takes the station's heartbeat and commands,
# checks plans, answers every command, and says what the aircraft is doing. It owns the mission manager.
# This is fdm/onboard.py in Nasal, line for line; change both together. Nothing here flies the aircraft: commands
# change the plan the manager works through.
#
# Up from the station: /gcs/up/heartbeat ("STATION:n"), /gcs/up/cmd (JSON), /gcs/up/stick (JSON).
# Down to it: /gcs/down/ack, /gcs/down/status, /gcs/down/plan (JSON text).

var NAVS = ["kna", "knb", "lna", "lnb"];
var KINDS = ["taxi", "takeoff", "route", "land", "hold"];
var MAX_LEG_NM = 3000.0;
var MIN_FINAL_NM = 8.0;
var MAX_DESCENT_DEG = 6.0;
var MIN_GRADIENT_LEG_NM = 2.0;
var FPS_PER_KT = 1.6878099;
# the steady crosswind the landing holds its contracts in, by weight (fdm/landlimit.py, data/landing_limits.json; js/flightmath.js crosswindLimitKt reads the same table)
var XW_WEIGHT = [12000, 16000, 20800, 24000, 26000];
var XW_LIMIT = [15, 20, 25, 25, 30];
var crosswind_limit_kt = func(w) {
    if (w <= XW_WEIGHT[0]) return XW_LIMIT[0];
    for (var i = 1; i < size(XW_WEIGHT); i += 1)
        if (w <= XW_WEIGHT[i]) return XW_LIMIT[i - 1] + (XW_LIMIT[i] - XW_LIMIT[i - 1]) * (w - XW_WEIGHT[i - 1]) / (XW_WEIGHT[i] - XW_WEIGHT[i - 1]);
    return XW_LIMIT[size(XW_LIMIT) - 1];
};
var MAX_HOLDS = 16;                   # holds a taxi item may carry (docs/PLAN.md, "Hold points and clearances")
var HOLD_KINDS = ["runway", "takeoff", "junction", "point"];
var HOLD_ID_MAX = 24;
var HOLD_NAME_MAX = 80;
var REPOSITION_MAX_KT = 2.0;           # the aircraft moves to a new place on the ground only when it stands (docs/GCS.md, `reposition`)
var AIRPORT_MAX_BYTES = 100000;        # what the station takes over the link for an airport (fdm/airportdata.py)
var FUEL_LOW_LB = 1500.0;              # assumed: about an hour and a half at cruise
var AOA_NEAR_DEG = 0.15;               # the near-limit advisory: raised with the angle of attack within 0.15 deg of its limit for 3 s (the approach is flown 0.2 to 0.3 deg under it at light weights) ...
var AOA_SEC = 3.0;
var AOA_NEAR_OFF_DEG = 0.25;          # ... and cleared when it has been more than 0.25 deg under it for 2 s (hysteresis: with one threshold the caution came and went every few seconds)
var AOA_CLEAR_SEC = 2.0;
var AOA_EXCEED_SEC = 0.5;             # the exceeded caution: the angle over its limit for 0.5 s; once raised it stands at least 3 s
var AOA_HOLD_SEC = 3.0;
var OFFER_SEC = 120.0;                 # a handover offer lapses after this
var FREE = ["control.take", "control.accept", "airport"];      # commands a station that does not hold control may send ("airport" only reads the scenery)
var LINK_TIMEOUT_MIN = 10.0;                # s, assumed: under 10 a satellite delay and a missed heartbeat could trigger it
var LINK_TIMEOUT_MAX = 300.0;

var among = func(x, v) {
    if (x == nil or typeof(x) != "scalar") return 0;
    foreach (var e; v) if (cmp(e ~ "", x ~ "") == 0) return 1;
    return 0;
};
var is_num = func(x) { return JSON.is_number(x); };
var round_to = func(x, places) { return num(sprintf("%." ~ places ~ "f", x)); };
var show = func(x) { return typeof(x) == "scalar" ? (x ~ "") : JSON.encode(x); };       # as Python's %s would

var point_fault = func(p, n, what) {
    var ok = typeof(p) == "vector" and size(p) == n;
    if (ok) foreach (var v; p) if (!is_num(v)) ok = 0;
    if (!ok) return sprintf("%s: a point needs %d numbers", what, n);
    if (p[0] < -90.0 or p[0] > 90.0) return sprintf("%s: latitude %g is not on the earth", what, p[0]);
    if (p[1] < -180.0 or p[1] > 180.0) return sprintf("%s: longitude %g is not on the earth", what, p[1]);
    if (n == 3 and (p[2] < 0.0 or p[2] > MAX_ALT)) return sprintf("%s: height %g ft is outside 0 to %.0f ft", what, p[2], MAX_ALT);
    return nil;
};

var is_text = func(x, n) { return typeof(x) == "scalar" and !is_num(x) and size(x) >= 1 and size(x) <= n; };

# nil if a taxi item's holds are good, or the first fault as text. ids: the ids met so far in this list of items
var holds_fault = func(holds, npts, w, ids) {
    if (typeof(holds) != "vector" or size(holds) > MAX_HOLDS) return sprintf("%s (taxi): holds is not a list of at most %d", w, MAX_HOLDS);
    var used = {};
    forindex (var n; holds) {
        var h = holds[n];
        var x = sprintf("%s (taxi) hold %d", w, n + 1);
        if (typeof(h) != "hash") return x ~ ": not a hold";
        var i = opt(h, "i", nil);
        if (!is_num(i) or i != math.floor(i) or i < 0 or i >= npts) return sprintf("%s: i is not a whole number from 0 to %d", x, npts - 1);
        if (contains(used, i ~ "")) return sprintf("%s: point %d is a hold already", x, i + 1);
        used[i ~ ""] = 1;
        var id = opt(h, "id", nil);
        if (!is_text(id, HOLD_ID_MAX)) return sprintf("%s: id is not text of 1 to %d characters", x, HOLD_ID_MAX);
        if (contains(ids, id)) return sprintf("%s: id %s is used twice in the plan", x, id);
        ids[id] = 1;
        if (!is_text(opt(h, "name", nil), HOLD_NAME_MAX)) return sprintf("%s: name is not text of 1 to %d characters", x, HOLD_NAME_MAX);
        var kind = opt(h, "kind", nil);
        if (!among(kind, HOLD_KINDS)) return sprintf("%s: kind %s is not runway, takeoff, junction or point", x, JSON.encode(kind));
        if (kind == "takeoff" and i != npts - 1) return sprintf("%s: a takeoff hold belongs at the last point (point %d)", x, npts);
    }
    return nil;
};

# nil if a list of plan items can be flown, or the first fault as text
var check_items = func(items, what) {
    if (typeof(items) != "vector" or size(items) == 0) return what ~ ": no items";
    forindex (var n; items) {
        var it = items[n];
        if (typeof(it) != "hash" or !among(opt(it, "kind", nil), KINDS))
            return sprintf("%s item %d: unknown kind %s", what, n + 1, JSON.encode(typeof(it) == "hash" ? opt(it, "kind", nil) : it));
    }
    var ids = {};
    forindex (var n; items) {
        var it = items[n];
        var w = sprintf("%s item %d", what, n + 1);
        var kind = it.kind;
        if (kind == "taxi" or kind == "route") {
            var pts = opt(it, "points", nil);
            if (typeof(pts) != "vector" or size(pts) == 0) return sprintf("%s (%s): no points", w, kind);
            forindex (var m; pts) {
                var bad = point_fault(pts[m], kind == "route" ? 3 : 2, sprintf("%s (%s) point %d", w, kind, m + 1));
                if (bad != nil) return bad;
            }
            for (var m = 0; m + 1 < size(pts); m += 1)
                if (course(pts[m], pts[m + 1])[1] / NM > MAX_LEG_NM) return sprintf("%s (%s): a leg longer than %.0f nmi", w, kind, MAX_LEG_NM);
            if (kind == "taxi" and opt(it, "holds", nil) != nil) {
                var bad = holds_fault(it.holds, size(pts), w, ids);
                if (bad != nil) return bad;
            }
            if (kind == "route")
                for (var m = 0; m + 1 < size(pts); m += 1) {
                    var ft = course(pts[m], pts[m + 1])[1];
                    var drop = pts[m][2] - pts[m + 1][2];
                    if (drop > 0 and ft / NM >= MIN_GRADIENT_LEG_NM) {
                        var deg = math.atan2(drop, ft) * 180.0 / math.pi;
                        if (deg > MAX_DESCENT_DEG)
                            return sprintf("%s (route): point %d to point %d goes down %.0f ft in %.1f nmi, %.1f deg: the aircraft does not come down more steeply than %g deg", w, m + 1, m + 2, drop, ft / NM, deg, MAX_DESCENT_DEG);
                    }
                }
        } elsif (kind == "takeoff") {
            var bad = point_fault(opt(it, "start", nil), 2, w ~ " (takeoff) start");
            if (bad == nil) bad = point_fault(opt(it, "end", nil), 2, w ~ " (takeoff) end");
            if (bad != nil) return bad;
            if (n + 1 >= size(items) or items[n + 1].kind != "route") return w ~ ": a takeoff must be followed by a route";
        } elsif (kind == "land") {
            var bad = point_fault(opt(it, "fix", nil), 2, w ~ " (land) fix");
            if (bad == nil) bad = point_fault(opt(it, "aim", nil), 2, w ~ " (land) aim");
            if (bad != nil) return bad;
            var d = course(it.fix, it.aim)[1] / NM;
            if (d < MIN_FINAL_NM) return sprintf("%s (land): the fix is %.1f nmi from the aiming point, less than %.0f", w, d, MIN_FINAL_NM);
        } elsif (kind == "hold") {
            var c = opt(it, "centre", nil);
            var p = typeof(c) == "vector" ? c ~ [opt(it, "alt", nil)] : [opt(it, "alt", nil)];
            var bad = point_fault(p, 3, w ~ " (hold)");
            if (bad != nil) return bad;
        }
    }
    return nil;
};

# nil if the plan is good, or the first fault as text
var check_plan = func(plan) {
    if (typeof(plan) != "hash") return "not a plan";
    var fld = opt(plan, "field", nil);
    if (typeof(fld) != "hash" or !is_num(opt(fld, "elev_ft", nil)) or point_fault([opt(fld, "lat", nil), opt(fld, "lon", nil)], 2, "field") != nil)
        return "field: needs lat, lon and elev_ft";
    var bad = check_items(opt(plan, "items", nil), "plan");
    if (bad != nil) return bad;
    var ll = opt(plan, "lost_link", nil);
    if (ll != nil) {
        bad = check_items(ll, "lost-link route");
        if (bad != nil) return bad;
        if (ll[0].kind != "route" or ll[size(ll) - 1].kind != "land") return "lost-link route: it must begin with a route and end in a land";
    }
    var sites = opt(plan, "sites", nil);
    if (typeof(sites) == "vector")
        forindex (var n; sites) {
            var s = sites[n];
            if (typeof(s) != "hash" or point_fault(opt(s, "aim", nil), 2, "site") != nil or !is_num(opt(s, "course", nil)) or !is_num(opt(s, "elev_ft", nil)))
                return sprintf("site %d: needs aim, course and elev_ft", n + 1);
        }
    return nil;
};

# plan items as the manager takes them: copies, with the field's elevation where a takeoff or landing needs one
var items_for_manager = func(items, elev) {
    var out = [];
    foreach (var it; items) {
        var d = copy(it);
        if (d.kind == "takeoff" or d.kind == "land")
            if (opt(d, "elev", nil) == nil) d.elev = opt(d, "elev_ft", elev);
        append(out, d);
    }
    return out;
};

# ---- an airport's ground network and runway ends, for the `airport` command: fdm/airportdata.py is the same in Python (its docstring has the message).
# FlightGear finds the files in its scenery (resolvepath: whatever the machine) and io.readxml makes an element's attributes children named ___name.
var xml_attr = func(n, k) {
    var c = n.getChild("___" ~ k);
    return c == nil ? nil : c.getValue();
};
var xml_str = func(n, k) {
    var v = xml_attr(n, k);
    return v == nil ? "" : v ~ "";
};
var xml_num = func(n, k, dflt) {
    var v = num(xml_str(n, k));
    return v == nil ? dflt : v;
};
var xml_dm = func(s) {                  # "N60 18.59300820" to degrees
    s = s ~ "";
    var parts = [];
    foreach (var w; split(" ", substr(s, 1)))
        if (size(w)) append(parts, w);
    if (size(parts) < 2) return num(s);
    var v = num(parts[0]) + num(parts[1]) / 60.0;
    var h = substr(s, 0, 1);
    return (h == "S" or h == "W") ? -v : v;
};
var airport_valid = func(icao) {
    if (typeof(icao) != "scalar" or size(icao ~ "") != 4) return 0;
    icao = icao ~ "";
    for (var i = 0; i < 4; i += 1) {
        var c = icao[i];
        if (!((c >= 48 and c <= 57) or (c >= 65 and c <= 90))) return 0;
    }
    return 1;
};
# [message, nil] or [nil, why not]
var airport_message = func(icao) {
    if (typeof(icao) == "scalar") icao = string.uc(icao ~ "");
    if (!airport_valid(icao)) return [nil, "an airport is four letters or digits, like EFHK"];
    var dir = "Airports/" ~ substr(icao, 0, 1) ~ "/" ~ substr(icao, 1, 1) ~ "/" ~ substr(icao, 2, 1) ~ "/";
    var path = resolvepath(dir ~ icao ~ ".groundnet.xml");
    if (path == "") return [nil, "no ground network for " ~ icao ~ " in the scenery"];
    var root = nil;
    var err = [];
    call(func { root = io.readxml(path); }, nil, nil, err);
    if (size(err) or root == nil) return [nil, "the ground network of " ~ icao ~ " cannot be read"];
    var net = root.getChild("groundnet");
    if (net == nil) net = root;
    var msg = { icao: icao, parking: [], nodes: [], arcs: [], names: [], runways: [] };
    err = [];
    call(func {
        var pl = net.getChild("parkingList");
        if (pl != nil)
            foreach (var p; pl.getChildren("Parking"))
                append(msg.parking, { n: xml_str(p, "name"), t: xml_str(p, "type"), lat: round_to(xml_dm(xml_str(p, "lat")), 6), lon: round_to(xml_dm(xml_str(p, "lon")), 6),
                                      h: round_to(mod(xml_num(p, "heading", 0), 360.0), 1), r: xml_num(p, "radius", 0) });
        var at = {};
        var tn = net.getChild("TaxiNodes");
        if (tn != nil)
            foreach (var n; tn.getChildren("node")) {
                at[xml_str(n, "index")] = size(msg.nodes);
                append(msg.nodes, [round_to(xml_dm(xml_str(n, "lat")), 6), round_to(xml_dm(xml_str(n, "lon")), 6)]);
            }
        var ni = {};
        var seen = {};
        var ts = net.getChild("TaxiWaySegments");
        if (ts != nil)
            foreach (var a; ts.getChildren("arc")) {
                var bu = xml_str(a, "begin");
                var bv = xml_str(a, "end");
                if (!contains(at, bu) or !contains(at, bv) or xml_str(a, "isPushBackRoute") == "1") continue;
                var nm = xml_str(a, "name");
                var lo = minv(at[bu], at[bv]);
                var hi = maxv(at[bu], at[bv]);
                var key = lo ~ ":" ~ hi ~ ":" ~ nm;
                if (contains(seen, key)) continue;
                seen[key] = 1;
                if (!contains(ni, nm)) {
                    ni[nm] = size(msg.names);
                    append(msg.names, nm);
                }
                append(msg.arcs, [lo, hi, ni[nm]]);
            }
        var tpath = resolvepath(dir ~ icao ~ ".threshold.xml");
        if (tpath != "") {
            var tp = io.read_properties(tpath);
            if (tp != nil)
                foreach (var rw; tp.getChildren("runway"))
                    foreach (var t; rw.getChildren("threshold"))
                        append(msg.runways, { n: t.getValue("rwy") ~ "", lat: round_to(t.getValue("lat"), 6), lon: round_to(t.getValue("lon"), 6), h: round_to(t.getValue("hdg-deg"), 2),
                                              displ: num(t.getValue("displ-m")), stopw: num(t.getValue("stopw-m")) });
        }
    }, nil, nil, err);
    if (size(err)) return [nil, "the ground network of " ~ icao ~ " cannot be read (" ~ err[0] ~ ")"];
    if (size(JSON.encode(msg)) > AIRPORT_MAX_BYTES) return [nil, "the ground network of " ~ icao ~ " is too big for the link"];
    return [msg, nil];
};

# After a reposition FlightGear starts the flight model over, and in its first frames the structure's latches trip (limits/overstress, limits/failed: the state is empty, nothing
# flew): "STRUCTURAL LIMIT PASSED" stood on the station and the HUD. Found 2026-11-16 in the first flight from a repositioned start. They are cleared once the scenery is
# in and the model has run a few seconds on its wheels, as the start-up does (globalhawk.nas); a reposition is allowed only on the ground with the plan not begun, so
# nothing real is hidden.
var repo_watch = nil;
var repo_settle = func {
    if (repo_watch != nil) repo_watch.stop();
    var tries = 0;
    var unloaded = 0;
    repo_watch = maketimer(0.5, func {
        tries += 1;
        if (!getprop("/sim/sceneryloaded")) unloaded = 1;
        # FlightGear has started over (or ten seconds went by without it: a move within the scenery already loaded), it is loaded again and the model has run for a while
        if ((unloaded or tries > 20) and getprop("/sim/sceneryloaded") and fget("simulation/sim-time-sec") > 2.0 and fget("ap/on-mains") > 0) {
            repo_watch.stop();
            fset("limits/reset", 1);
            settimer(func { fset("limits/reset", 0); }, 1);
        } elsif (tries > 240) repo_watch.stop();                  # two minutes: give up
    });
    repo_watch.start();
};

var Onboard = {
    new: func {
        var m = { parents: [Onboard] };
        m.plan = nil; m.mgr = nil; m.fresh = nil;
        m.started = 0; m.off = nil; m.saved = nil;
        m.answered = {};                         # station -> the last seq answered
        m.beat = nil;
        m.events = [];
        m.aoa = { over_since: nil, over_on: nil, near_since: nil, near_on: 0, clear_since: nil };      # the angle-of-attack alerts' state
        m.stations = {};                         # name -> when last heard (sim seconds)
        m.holder = nil; m.offer = nil;           # who has control; a handover offered: [to, when]
        m.sender = "";
        m.last_mgr = -1; m.last_status = -1;
        m.last = nil;
        foreach (var p; ["ack", "status", "plan", "airport"]) setprop("/gcs/down/" ~ p, "");
        m.status();
        return m;
    },
    now: func { return fget("simulation/sim-time-sec"); },
    note: func(text) { append(me.events, [me.now(), text]); },

    # ---- uplink
    heartbeat: func(value) {
        if (value == nil) return;
        value = value ~ "";
        if (me.beat != nil and cmp(value, me.beat) == 0) return;
        me.beat = value;
        var at = -1;
        for (var i = size(value) - 1; i >= 0; i -= 1) if (value[i] == 58) { at = i; break; }
        if (at < 0) me.alive();                  # a bare counter: keeps the link alive for whoever holds control, takes none
        else me.heard(substr(value, 0, at));
    },
    stick: func(value) {
        var got = JSON.try(value);
        var m = got[0];
        if (typeof(m) != "hash" or opt(m, "station", nil) == nil) return;
        var v = [];
        foreach (var k; ["p", "r", "y", "t", "s"]) {
            if (!is_num(opt(m, k, nil))) return;
            append(v, m[k]);
        }
        var name = m.station ~ "";
        me.heard(name);
        if (me.holder != nil and cmp(name, me.holder) == 0 and fget("ap/manual") > 0) {
            fset("fcs/elevator-cmd-norm", clip(v[0], -1.0, 1.0));
            fset("fcs/aileron-cmd-norm", clip(v[1], -1.0, 1.0));
            fset("fcs/rudder-cmd-norm", clip(v[2], -1.0, 1.0));
            fset("fcs/throttle-cmd-norm", clip(v[3], 0.0, 1.0));
            fset("fcs/speedbrake-cmd-norm", clip(v[4], 0.0, 1.0));
        }
    },
    command: func(value) {
        var got = JSON.try(value);
        var cmd = got[0];
        if (typeof(cmd) != "hash" or !is_num(opt(cmd, "seq", nil)) or opt(cmd, "name", nil) == nil) return;     # not a command: nothing to answer
        var seq = int(cmd.seq);
        var name = cmd.name ~ "";
        var station = opt(cmd, "station", "") ~ "";
        if (contains(me.answered, station) and seq <= me.answered[station]) return;      # an old command is never done again
        me.answered[station] = seq;
        me.heard(station);
        me.sender = station;
        var reason = nil;
        if ((me.holder == nil or cmp(station, me.holder) != 0) and !among(name, FREE)) reason = show(me.holder) ~ " has control";
        else {
            var args = opt(cmd, "args", nil);
            if (typeof(args) != "hash") args = {};
            var fn = contains(Onboard.commands, name) ? Onboard.commands[name] : Onboard.commands["unknown"];
            var err = [];
            reason = call(fn, [args], me, nil, err);
            if (size(err)) reason = "bad arguments (" ~ err[0] ~ ")";
        }
        var ack = { seq: seq, station: station, name: name, status: reason != nil ? "rejected" : "accepted",
                    reason: reason != nil ? reason : "", t: round_to(me.now(), 2) };
        setprop("/gcs/down/ack", JSON.encode(ack));
        me.note(name ~ " " ~ (reason != nil ? "REJECTED: " ~ reason : "accepted"));
        me.status();
    },

    # an uplink from the station that holds control: the link is alive
    alive: func {
        fset("ap/link-last-sec", me.now());
        fset("ap/link-monitor", 1);
    },
    # a station was heard. The first one gets control; the holder's uplinks keep the link alive
    heard: func(name) {
        me.stations[name] = me.now();
        if (me.holder == nil) {
            me.holder = name;
            me.note(name ~ " has control");
        }
        if (cmp(name, me.holder) == 0) me.alive();
    },
    airborne: func {
        if (!me.started or me.mgr == nil or me.mgr.done) return 0;
        var k = me.mgr.plan[me.mgr.i].kind;
        return k == "route" or k == "hold";
    },

    # before leaving the plan: where to come back to. The leg being flown, from its own start, and the rest
    remember: func {
        var m = me.mgr;
        var it = m.plan[m.i];
        if (me.saved == nil and it.kind == "route" and me.off == nil) {
            var pts = it._pts;
            var rest = { kind: "route", start: [pts[m.k][0], pts[m.k][1]], points: subvec(it.points, m.k) };
            me.saved = [rest];
            foreach (var d; m.rest()) append(me.saved, copy(d));
        }
    },
    # leave the plan for other items
    leave: func(items, what) {
        var m = me.mgr;
        me.remember();
        m.plan = m.upto() ~ items;
        me.off = what;
        m.next();
    },
    # back from flying by hand: the laws take over and the aircraft holds where it is
    automatic: func {
        fset("ap/manual", 0);
        foreach (var k; ["elevator", "aileron", "rudder"]) fset("fcs/" ~ k ~ "-cmd-norm", 0.0);
        me.off = nil;
        fset("ap/alt-cmd-ft", math.floor(fget("position/h-sl-ft") / 100.0 + 0.5) * 100.0);
        if (me.airborne()) call(Onboard.commands["hold"], [{}], me);
    },

    # ---- commands: each returns nil when done, or why not
    commands: {
        "unknown": func(a) { return "unknown command"; },
        "plan": func(a) {
            var bad = check_plan(a);
            if (bad != nil) return bad;
            if (me.started and !(me.airborne() and a.items[0].kind == "route"))
                return "a plan is being flown: a new one must begin with a route and be sent while enroute";
            me.plan = a;
            var elev = a.field.elev_ft;
            var sites = [];
            var given = opt(a, "sites", nil);
            if (typeof(given) == "vector")
                foreach (var s; given) append(sites, { name: opt(s, "name", "?"), aim: s.aim, course: s.course, elev: s.elev_ft });
            var lost = opt(a, "lost_link", nil) != nil ? items_for_manager(a.lost_link, elev) : nil;
            if (me.started) {
                var m = me.mgr;
                m.plan = m.upto() ~ items_for_manager(a.items, elev);
                m.lost_link = lost; m.sites = sites;
                me.off = nil; me.saved = nil;
                m.next();
            } else me.fresh = [items_for_manager(a.items, elev), lost, sites];
            setprop("/gcs/down/plan", JSON.encode(a));
            return nil;
        },
        "start": func(a) {
            if (me.plan == nil) return "no plan";
            if (me.started) return "the plan has already begun";
            if (!fget("engine/running")) return "the engine is not running";
            fset("ap/speed-schedule", 1);
            fset("ap/theta-cmd-deg", fget("attitude/theta-deg"));
            fset("fcs/left-brake-cmd-norm", 0); fset("fcs/right-brake-cmd-norm", 0);
            # in FlightGear: the parking brake off, the sticks let go, and the laws out of the manual mode they
            # wait in on the ground (globalhawk.nas)
            setprop("/controls/gear/brake-parking", 0);
            foreach (var k; ["elevator", "aileron", "rudder"]) fset("fcs/" ~ k ~ "-cmd-norm", 0.0);
            fset("ap/manual", 0);
            me.mgr = Manager.new(me.fresh[0], me.fresh[1], me.fresh[2]);
            fset("ap/engaged", 1);
            me.started = 1;
            return nil;
        },
        # clear the hold the aircraft is waiting at (docs/PLAN.md, "Hold points and clearances"): by id, so that a clearance meant for one is never taken for another
        "clear": func(a) {
            var m = me.started ? me.mgr : nil;
            if (m == nil) return "the plan has not begun";
            if (m.waiting == nil) return "the aircraft is not waiting at a hold";
            var w = m.waiting;
            var id = opt(a, "id", nil);
            if (!is_text(id, 1000000)) return "clear: a hold is cleared by its id";
            if (cmp(id, w.id) != 0) return sprintf("the aircraft is waiting at %s (%s), not %s", w.id, w.name, id);
            m.clear();
            return nil;
        },
        "airport": func(a) {
            var got = airport_message(opt(a, "icao", nil));
            if (got[1] != nil) return got[1];
            setprop("/gcs/down/airport", JSON.encode(got[0]));
            return nil;
        },
        "reposition": func(a) {
            var p = [opt(a, "lat", nil), opt(a, "lon", nil)];
            var bad = point_fault(p, 2, "reposition");
            if (bad != nil) return bad;
            if (!is_num(opt(a, "heading", nil))) return "reposition: the heading is not a number";
            if (me.started) return "the plan has begun";
            if (fget("ap/on-mains") == 0) return "only on the ground";
            if (fget("ap/ground-speed-kt") > REPOSITION_MAX_KT) return sprintf("only when the aircraft stands (%.0f kt)", fget("ap/ground-speed-kt"));
            # FlightGear's own reposition, as its Location dialog does it: the presets, on the ground, then the command
            # (an airport, a runway or a parking spot named among the presets would win over the coordinates: cleared, as the teleport of Nasal/aircraft.nas does)
            foreach (var k; ["airport-id", "runway", "parkpos", "carrier", "fix", "vor-id", "ndb-id"]) setprop("/sim/presets/" ~ k, "");
            setprop("/sim/presets/runway-requested", 0);
            setprop("/sim/presets/navaid-id", 0);
            setprop("/sim/presets/offset-distance-nm", 0);
            setprop("/sim/presets/offset-azimuth-deg", 0);
            setprop("/sim/presets/glideslope-deg", 0);
            setprop("/sim/presets/latitude-deg", p[0]);
            setprop("/sim/presets/longitude-deg", p[1]);
            setprop("/sim/presets/heading-deg", mod(a.heading, 360.0));
            setprop("/sim/presets/altitude-ft", -9999);
            setprop("/sim/presets/airspeed-kt", 0);
            setprop("/sim/presets/onground", 1);
            fgcommand("reposition");
            repo_settle();
            return nil;
        },
        "goto": func(a) {
            if (!me.airborne()) return "only while enroute";
            var p = [a["lat"], a["lon"], a["alt_ft"]];
            var bad = point_fault(p, 3, "goto");
            if (bad != nil) return bad;
            me.leave([{ kind: "route", points: [p] }, { kind: "hold", centre: [p[0], p[1]], alt: p[2] }], "goto");
            return nil;
        },
        "hold": func(a) {
            if (!me.airborne()) return "only while enroute";
            var m = me.mgr;
            # the circle starts where the aircraft is: its centre one radius to the right
            var r = m.hold_radius();
            var centre = offset(m.here(), fget("attitude/psi-deg") + 90.0, r);
            me.leave([{ kind: "hold", centre: centre, alt: fget("ap/alt-cmd-ft"), radius: r }], "hold");
            return nil;
        },
        "altitude": func(a) {
            if (!me.airborne()) return "only while enroute";
            var alt = a["alt_ft"];
            if (!is_num(alt) or alt < 0.0 or alt > MAX_ALT) return sprintf("height %s ft is outside 0 to %.0f ft", show(alt), MAX_ALT);
            var it = me.mgr.plan[me.mgr.i];
            if (it.kind == "hold") it.alt = alt;
            else it.alt_override = alt;
            return nil;
        },
        "resume": func(a) {
            var m = me.mgr;
            if (!me.started or me.saved == nil) return "not off the plan";
            if (m.contingency != nil and m.contingency == "engine") return "the engine has failed";
            if (m.contingency != nil and m.contingency == "link") {
                m.contingency = nil;
                fset("ap/link-monitor", 0);      # clears the lost-link latch; the next heartbeat starts the watch again
                fset("ap/link-lost", 0);         # and at once: a heartbeat may switch the watch back on before the latch has run
            }
            m.plan = m.upto() ~ me.saved;
            me.saved = nil; me.off = nil;
            m.next();
            return nil;
        },
        "home": func(a) {
            if (!me.airborne()) return "only while enroute";
            if (me.mgr.lost_link == nil or size(me.mgr.lost_link) == 0) return "the plan has no contingency route";
            var items = [];
            foreach (var d; me.mgr.lost_link) append(items, copy(d));
            me.leave(items, "home");
            return nil;
        },
        "control.offer": func(a) {
            if (a["to"] == nil) die("'to'");
            var to = a["to"] ~ "";
            var t = me.now();
            if (me.holder != nil and cmp(to, me.holder) == 0) return "that is this station";
            if (!contains(me.stations, to) or t - me.stations[to] > 10.0) return "station " ~ to ~ " is not being heard";
            me.offer = [to, t];
            return nil;
        },
        "control.cancel": func(a) {
            if (me.offer == nil) return "no handover is offered";
            me.offer = nil;
            return nil;
        },
        "control.accept": func(a) {
            if (me.offer == nil or cmp(me.offer[0], me.sender) != 0) return "control has not been offered to " ~ me.sender;
            var old = me.holder;
            me.holder = me.sender; me.offer = nil;
            me.alive();
            me.note("control passed from " ~ show(old) ~ " to " ~ me.holder);
            return nil;
        },
        "control.take": func(a) {
            if (me.holder != nil and cmp(me.holder, me.sender) == 0) return "this station already has control";
            if (me.holder != nil and !fget("ap/link-lost")) return me.holder ~ " has control and is being heard";
            var old = me.holder;
            me.holder = me.sender; me.offer = nil;
            me.alive();
            me.note(me.holder ~ " took control" ~ (old != nil ? " (" ~ old ~ " was lost)" : ""));
            return nil;
        },
        "manual": func(a) {
            var mode = a["mode"];
            if (!is_num(mode) or (mode != 0 and mode != 1 and mode != 2)) return "mode must be 0 (automatic), 1 (protected) or 2 (direct)";
            if (mode == 0) {
                if (fget("ap/manual") == 0) return "already automatic";
                me.automatic();
                return nil;
            }
            if (!me.airborne()) return "only while enroute";
            if (fget("ap/manual") == 0) {
                # the levers start where the laws have them; the manager holds here, off the plan, until told otherwise
                fset("fcs/throttle-cmd-norm", fget("ctl/throttle-norm"));
                fset("fcs/speedbrake-cmd-norm", fget("ctl/spoiler-norm"));
                foreach (var k; ["elevator", "aileron", "rudder"]) fset("fcs/" ~ k ~ "-cmd-norm", 0.0);
            }
            fset("ap/land-mode", 0);
            fset("ap/manual", mode);
            me.remember();
            me.off = "manual";
            return nil;
        },
        "linktimeout": func(a) {
            var sec = opt(a, "sec", nil);
            if (!is_num(sec)) return "the time-out needs a number of seconds";
            if (sec < LINK_TIMEOUT_MIN or sec > LINK_TIMEOUT_MAX) return sprintf("the time-out is %g to %g s", LINK_TIMEOUT_MIN, LINK_TIMEOUT_MAX);
            fset("ap/link-timeout-sec", sec);
            return nil;
        },
        "nav": func(a) {
            if (!among(a["name"], NAVS)) return "unknown navigator";
            fset("nav/" ~ a["name"] ~ "-on", a["on"] ? 1 : 0);
            return nil;
        },
    },

    # ---- every frame
    step: func {
        var t = me.now();
        if (me.started) {
            var m = me.mgr;
            if (fget("ap/manual") > 0 and fget("ap/link-lost")) {
                me.note("link lost while flown by hand: automatic");
                me.automatic();
            }
            if (me.offer != nil and t - me.offer[1] > OFFER_SEC) me.offer = nil;
            if (t - me.last_mgr >= 0.1 or t < me.last_mgr) {
                me.last_mgr = t;
                var before = m.contingency;
                if (before == nil and (fget("ap/link-lost") or fget("engine/failed")) and !m.done) me.remember();      # the manager is about to leave the plan by itself
                m.step();
                if (m.contingency != nil and (before == nil or m.contingency != before)) me.off = m.contingency;
            }
        }
        if (t - me.last_status >= 0.5 or t < me.last_status) {
            me.last_status = t;
            me.status();
        }
    },

    status: func {
        var m = me.started ? me.mgr : nil;
        var s = {};
        s["t"] = round_to(me.now(), 1);
        s["plan"] = me.plan != nil ? opt(me.plan, "id", nil) : nil;
        s["started"] = me.started ? JSON.T : JSON.F;
        s["item"] = nil; s["kind"] = nil;
        s["doing"] = me.plan == nil ? "no plan" : "waiting for start";
        s["next"] = ""; s["off_plan"] = me.off; s["contingency"] = nil;
        s["hold"] = nil; s["wait"] = nil; s["leg"] = nil;
        s["link_lost"] = fget("ap/link-lost") ? JSON.T : JSON.F;
        s["link_age"] = fget("ap/link-monitor") ? round_to(fget("ap/link-age-sec"), 1) : nil;
        s["link_timeout"] = fget("ap/link-timeout-sec");
        if (m != nil) {
            var it = m.plan[minv(m.i, size(m.plan) - 1)];
            var kind = m.done ? "done" : it.kind;
            s["item"] = m.i; s["kind"] = kind; s["contingency"] = m.contingency;
            var d = me.describe(m, it, kind);
            s["doing"] = d[0]; s["next"] = d[1];
            if (kind == "hold" or kind == "go_around") {
                var r = opt(it, "radius", nil);
                s["hold"] = { lat: it.centre[0], lon: it.centre[1], radius_ft: math.floor((r != nil ? r : m.hold_radius()) + 0.5), alt_ft: it.alt };
            }
            if (m.waiting != nil) s["wait"] = { id: m.waiting.id, name: m.waiting.name, kind: m.waiting.kind, since: round_to(m.waiting.since, 1) };
            if (kind != "done" and kind != "hold" and kind != "go_around")
                s["leg"] = [[fget("ap/leg-lat0-deg"), fget("ap/leg-lon0-deg")], [fget("ap/leg-lat1-deg"), fget("ap/leg-lon1-deg")]];
            if (kind == "engine_out") {
                s["site"] = opt(opt(it, "site", {}), "name", nil);
                s["surplus_ft"] = math.floor(opt(it, "surplus", 0.0) + 0.5);
            }
        }
        s["alerts"] = me.alerts(m);
        var now = me.now();
        var heard = [];
        foreach (var n; sort(keys(me.stations), func(a, b) cmp(a, b))) append(heard, { name: n ~ "", age: round_to(now - me.stations[n], 1) });
        s["control"] = { holder: me.holder, offer_to: me.offer != nil ? me.offer[0] : nil, stations: heard };
        s["manual"] = int(fget("ap/manual"));
        s["target"] = { alt_ft: math.floor(fget("ap/alt-cmd-ft") + 0.5), kcas: round_to(fget("ap/speed-target-kcas"), 1) };
        var ev = [];
        foreach (var e; (m != nil ? m.events : []) ~ me.events) append(ev, [round_to(e[0], 1), e[1]]);
        ev = sort(ev, func(a, b) { return a[0] < b[0] ? -1 : (a[0] > b[0] ? 1 : cmp(a[1], b[1])); });
        s["events"] = size(ev) > 6 ? subvec(ev, size(ev) - 6) : ev;
        setprop("/gcs/down/status", JSON.encode(s));
        me.last = s;                             # for the head-up display
        return s;
    },

    # the angle-of-attack alerts for one look: [exceeded, near]. margin: the limit less the angle, deg. Exceeded: the angle over the limit for AOA_EXCEED_SEC, then standing at least AOA_HOLD_SEC and until
    # it is back under. Near: within AOA_NEAR_DEG of the limit (or over) for AOA_SEC, then standing until more than AOA_NEAR_OFF_DEG under it for AOA_CLEAR_SEC
    aoa_step: func(margin, active, t) {
        var a = me.aoa;
        if (!active) {
            a.over_since = nil; a.over_on = nil; a.near_since = nil; a.near_on = 0; a.clear_since = nil;
            return [0, 0];
        }
        if (margin < 0) {
            if (a.over_since == nil) a.over_since = t;
            if (a.over_on == nil and t - a.over_since >= AOA_EXCEED_SEC) a.over_on = t;
        } else {
            a.over_since = nil;
            if (a.over_on != nil and t - a.over_on >= AOA_HOLD_SEC) a.over_on = nil;
        }
        if (!a.near_on) {
            if (margin < AOA_NEAR_DEG) {
                if (a.near_since == nil) a.near_since = t;
                if (t - a.near_since >= AOA_SEC) { a.near_on = 1; a.clear_since = nil; }
            } else {
                a.near_since = nil;
            }
        } else {
            if (margin > AOA_NEAR_OFF_DEG) {
                if (a.clear_since == nil) a.clear_since = t;
                if (t - a.clear_since >= AOA_CLEAR_SEC) { a.near_on = 0; a.near_since = nil; a.clear_since = nil; }
            } else {
                a.clear_since = nil;
            }
        }
        return [a.over_on != nil, a.near_on];
    },

    # what the crew must know, as the aircraft sees it. Only what the model computes
    alerts: func(m) {
        var out = [];
        var add = func(i, level, text, action = "") { append(out, { id: i, level: level, text: text, action: action }); };
        var t = me.now();
        if (fget("engine/failed")) {
            var it = m != nil ? m.plan[minv(m.i, size(m.plan) - 1)] : {};
            var site = (opt(it, "kind", "") == "engine_out") ? opt(opt(it, "site", {}), "name", nil) : nil;
            add("engine", "warning", "ENGINE FAILED", (site != nil ? "Gliding to " ~ site ~ " by itself. Clear the runway. " : "") ~ "No restart is modelled");
        }
        if (m != nil and m.alert != nil) add("no-site", "warning", "NO RUNWAY IN REACH", "Gliding towards the nearest");
        if (m != nil and !m.done and m.plan[minv(m.i, size(m.plan) - 1)].kind == "go_around") {
            var ga = m.plan[minv(m.i, size(m.plan) - 1)];
            add("go-around", "warning", "LANDING NOT COMMITTED", sprintf("The aircraft was %.0f ft %s at the landing fix. It is circling over the fix to lose height and will land when it can. Check the plan", ga.above, ga.reason));
        }
        if (m != nil and !m.done) {
            var cur = m.plan[minv(m.i, size(m.plan) - 1)];
            if (cur.kind == "route" and opt(cur, "ga", nil) != nil and !opt(cur.ga, "abandoned", 0))
                add("missed-approach", "warning", "MISSED APPROACH", sprintf("The approach was not stable (%s). The aircraft is climbing out and flying a circuit for another approach, attempt %d. Check the weather and the aircraft", cur.ga.why, cur.ga.attempt));
            elsif ((cur.kind == "route" and opt(cur, "ga", nil) != nil) or (cur.kind == "hold" and opt(cur, "abandoned", nil) != nil))
                add("landing-abandoned", "warning", "LANDING ABANDONED", sprintf("The approach was not stable again (%s). The aircraft is climbing out to hold over the landing fix and will not try again by itself. Decide: another approach, another runway or the engine-out site", cur.kind == "route" ? cur.ga.why : cur.abandoned));
        }
        if (m != nil and !m.done and fget("ap/engaged") == 1 and fget("ap/land-mode") == 1 and fget("ap/on-mains") == 0) {
            var li = m.plan[minv(m.i, size(m.plan) - 1)];
            if (li.kind == "land") {
                var lim = crosswind_limit_kt(fget("inertia/weight-lbs"));
                var cc = course(li.fix, li.aim)[0] * D2R;
                var xw = absv(-fget("ap/wind-north-filt-fps") * math.sin(cc) + fget("ap/wind-east-filt-fps") * math.cos(cc)) / FPS_PER_KT;
                if (xw > lim)
                    add("crosswind", "caution", "CROSSWIND OVER LIMIT", sprintf("The wind across the final is %.0f kt; the landing holds its limits to %.0f kt at %.0f lb. Go around or divert if it is not to be accepted", xw, lim, fget("inertia/weight-lbs")));
            }
        }
        if (m != nil and m.waiting != nil) add("hold", "advisory", "WAITING FOR CLEARANCE: " ~ m.waiting.name, "Check that the way is clear, then clear it");
        if (fget("limits/overstress")) add("structure", "warning", "STRUCTURAL LIMIT PASSED", "Land");
        if (fget("ap/link-lost")) add("link", "caution", "LINK WAS LOST", "The aircraft left its plan when the link was lost. Resume when ready");
        if (fget("nav/miscompare")) add("nav-disagree", "caution", "NAVIGATORS DISAGREE", "The aircraft is using the one that matches its turn rate. Land");
        if (fget("nav/count") < 2 and t > 1.0)
            add("nav-one", "caution", fget("nav/count") == 1 ? "ONE NAVIGATOR LEFT" : "NO NAVIGATOR", "No cross-check of attitude is left. Switch one on");
        if (fget("fuel/total-lbs") < FUEL_LOW_LB and t > 1.0) add("fuel-low", "caution", "FUEL LOW", "Return home");
        var aoa = me.aoa_step(fget("ap/alpha-limit-deg") - fget("aero/alpha-deg"), fget("ap/engaged") == 1 and fget("ap/on-mains") == 0, t);
        if (aoa[0]) add("aoa", "caution", "ANGLE OF ATTACK LIMIT EXCEEDED", "The aircraft is bringing it back");
        elsif (aoa[1]) add("aoa-near", "advisory", "NEAR THE ANGLE OF ATTACK LIMIT", "The aircraft is holding it under the limit");
        if (fget("ap/gust-alert") == 1) add("gust", "caution", "GUSTS OR WIND SHEAR ON THE FINAL", fget("ap/gust-sys") == 1 ? "The gust system is correcting" : "The gust system is off: the landing may be hard");
        if (fget("ap/manual") > 0) add("manual", "advisory", "FLOWN BY HAND: " ~ (fget("ap/manual") == 1 ? "PROTECTED" : "DIRECT, NO PROTECTIONS"));
        if (me.off != nil and (me.off == "goto" or me.off == "hold" or me.off == "home")) add("off-plan", "advisory", "OFF THE PLAN: " ~ string.uc(me.off));
        return out;
    },

    describe: func(m, it, kind) {
        var after = { taxi: "taxi", takeoff: "takeoff", route: "route", land: "landing", hold: "hold", go_around: "go-around", engine_out: "" };
        var rest = m.rest();
        var nxt = size(rest) ? "then " ~ after[rest[0].kind] : "end of plan";
        if (kind == "done") return ["plan complete", ""];
        if (fget("ap/manual") > 0)
            return ["FLOWN BY HAND (" ~ (fget("ap/manual") == 1 ? "protected" : "direct") ~ ")", "automatic when commanded, or if the link is lost"];
        if (kind == "taxi" and m.waiting != nil) return ["HOLD: waiting for clearance: " ~ m.waiting.name, "on the station's clearance"];
        if (kind == "taxi") return [fget("ap/ground-speed-kt") < 0.3 ? "stopped" : sprintf("taxi, %.0f kt", fget("ap/ground-speed-kt")), nxt];
        if (kind == "takeoff") return ["takeoff", nxt];
        if (kind == "route") {
            var n = size(it._pts) - 1;
            var v = m.vmode != nil ? m.vmode : "level";
            var heads = { climb: "climb to", descent: "descend to", level: "level at" };
            var head = heads[v];
            return [sprintf("%s%s %.0f ft, leg %d of %d, %.0f nmi to go", opt(it, "ga", nil) != nil ? (opt(it.ga, "abandoned", 0) ? "LANDING ABANDONED: " : "MISSED APPROACH: ") : "", head, fget("ap/alt-cmd-ft"), m.k + 1, n, fget("ap/leg-togo-ft") / NM),
                    m.k + 1 < n ? sprintf("then leg %d", m.k + 2) : nxt];
        }
        if (kind == "hold") return [opt(it, "abandoned", nil) != nil ? sprintf("LANDING ABANDONED: hold at %.0f ft", it.alt) : sprintf("hold at %.0f ft", it.alt), "until commanded"];
        if (kind == "go_around") return [sprintf("GO-AROUND: circling over the fix to %.0f ft, %.0f ft above the glide path when it began", it.alt, it.above), "then landing"];
        if (kind == "land") {
            if (fget("ap/rollout")) return ["rollout", nxt];
            return [opt(it, "_on_path", 0) ? "approach, glide path" : sprintf("level to the glide path, %.0f nmi out", fget("ap/leg-togo-ft") / NM), "then landing"];
        }
        if (kind == "engine_out") {
            var task = opt(it, "task", "glide");
            var name = opt(opt(it, "site", {}), "name", "the runway");
            var doing = { glide: "ENGINE OUT: glide to " ~ name, circle: "ENGINE OUT: circle to lose height", final: "ENGINE OUT: final" };
            var then = { glide: "then circle", circle: "then final", final: "then landing" };
            return [doing[task], then[task]];
        }
        return [kind, nxt];
    },
};

# ---- in FlightGear
var onboard = nil;
var onboard_start = func {
    if (onboard != nil) return;
    foreach (var p; ["heartbeat", "cmd", "stick"]) if (getprop("/gcs/up/" ~ p) == nil) setprop("/gcs/up/" ~ p, "");
    if (getprop("/gcs/chat/line") == nil) setprop("/gcs/chat/line", "");       # the stations' messages to each other: not the aircraft's business, but the property must exist
    onboard = Onboard.new();
    # a listener must not die: an error in one would stop FlightGear telling it of later commands
    var guarded = func(fn) {
        return func(n) {
            var err = [];
            call(fn, [n.getValue()], onboard, nil, err);
            if (size(err)) printlog("alert", "Global Hawk link: ", err[0]);
        };
    };
    setlistener("/gcs/up/heartbeat", guarded(Onboard.heartbeat), 0, 1);
    setlistener("/gcs/up/cmd", guarded(Onboard.command), 0, 1);
    setlistener("/gcs/up/stick", guarded(Onboard.stick), 0, 1);
    var loop = maketimer(0, func {
        var err = [];
        call(Onboard.step, [], onboard, nil, err);
        if (size(err)) { printlog("alert", "Global Hawk link: ", err[0]); loop.stop(); }
    });
    loop.start();
    print("Global Hawk: the command link is listening on /gcs/up");
};
setlistener("/sim/signals/fdm-initialized", func { settimer(onboard_start, 3); }, 0, 0);
