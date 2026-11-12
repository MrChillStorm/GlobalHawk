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
var FUEL_LOW_LB = 1500.0;              # assumed: about an hour and a half at cruise
var AOA_NEAR_DEG = 0.3;
var AOA_SEC = 3.0;
var OFFER_SEC = 120.0;                 # a handover offer lapses after this
var FREE = ["control.take", "control.accept"];      # commands a station that does not hold control may send

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

# nil if a list of plan items can be flown, or the first fault as text
var check_items = func(items, what) {
    if (typeof(items) != "vector" or size(items) == 0) return what ~ ": no items";
    forindex (var n; items) {
        var it = items[n];
        if (typeof(it) != "hash" or !among(opt(it, "kind", nil), KINDS))
            return sprintf("%s item %d: unknown kind %s", what, n + 1, JSON.encode(typeof(it) == "hash" ? opt(it, "kind", nil) : it));
    }
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

var Onboard = {
    new: func {
        var m = { parents: [Onboard] };
        m.plan = nil; m.mgr = nil; m.fresh = nil;
        m.started = 0; m.off = nil; m.saved = nil;
        m.answered = {};                         # station -> the last seq answered
        m.beat = nil;
        m.events = [];
        m.aoa_since = nil;
        m.stations = {};                         # name -> when last heard (sim seconds)
        m.holder = nil; m.offer = nil;           # who has control; a handover offered: [to, when]
        m.sender = "";
        m.last_mgr = -1; m.last_status = -1;
        m.last = nil;
        foreach (var p; ["ack", "status", "plan"]) setprop("/gcs/down/" ~ p, "");
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
        s["hold"] = nil; s["leg"] = nil;
        s["link_lost"] = fget("ap/link-lost") ? JSON.T : JSON.F;
        s["link_age"] = fget("ap/link-monitor") ? round_to(fget("ap/link-age-sec"), 1) : nil;
        s["link_timeout"] = fget("ap/link-timeout-sec");
        if (m != nil) {
            var it = m.plan[minv(m.i, size(m.plan) - 1)];
            var kind = m.done ? "done" : it.kind;
            s["item"] = m.i; s["kind"] = kind; s["contingency"] = m.contingency;
            var d = me.describe(m, it, kind);
            s["doing"] = d[0]; s["next"] = d[1];
            if (kind == "hold") {
                var r = opt(it, "radius", nil);
                s["hold"] = { lat: it.centre[0], lon: it.centre[1], radius_ft: math.floor((r != nil ? r : m.hold_radius()) + 0.5), alt_ft: it.alt };
            }
            if (kind != "done" and kind != "hold")
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
        if (fget("limits/overstress")) add("structure", "warning", "STRUCTURAL LIMIT PASSED", "Land");
        if (fget("ap/link-lost")) add("link", "caution", "LINK WAS LOST", "The aircraft left its plan when the link was lost. Resume when ready");
        if (fget("nav/miscompare")) add("nav-disagree", "caution", "NAVIGATORS DISAGREE", "The aircraft is using the one that matches its turn rate. Land");
        if (fget("nav/count") < 2 and t > 1.0)
            add("nav-one", "caution", fget("nav/count") == 1 ? "ONE NAVIGATOR LEFT" : "NO NAVIGATOR", "No cross-check of attitude is left. Switch one on");
        if (fget("fuel/total-lbs") < FUEL_LOW_LB and t > 1.0) add("fuel-low", "caution", "FUEL LOW", "Return home");
        var near = fget("ap/engaged") == 1 and fget("ap/on-mains") == 0 and fget("ap/alpha-limit-deg") - fget("aero/alpha-deg") < AOA_NEAR_DEG;
        me.aoa_since = near ? (me.aoa_since != nil ? me.aoa_since : t) : nil;
        if (near and t - me.aoa_since >= AOA_SEC) add("aoa", "caution", "ANGLE OF ATTACK LIMIT", "The aircraft is holding it");
        if (fget("ap/manual") > 0) add("manual", "advisory", "FLOWN BY HAND: " ~ (fget("ap/manual") == 1 ? "PROTECTED" : "DIRECT, NO PROTECTIONS"));
        if (me.off != nil and (me.off == "goto" or me.off == "hold" or me.off == "home")) add("off-plan", "advisory", "OFF THE PLAN: " ~ string.uc(me.off));
        return out;
    },

    describe: func(m, it, kind) {
        var after = { taxi: "taxi", takeoff: "takeoff", route: "route", land: "landing", hold: "hold", engine_out: "" };
        var rest = m.rest();
        var nxt = size(rest) ? "then " ~ after[rest[0].kind] : "end of plan";
        if (kind == "done") return ["plan complete", ""];
        if (fget("ap/manual") > 0)
            return ["FLOWN BY HAND (" ~ (fget("ap/manual") == 1 ? "protected" : "direct") ~ ")", "automatic when commanded, or if the link is lost"];
        if (kind == "taxi") return [fget("ap/ground-speed-kt") < 0.3 ? "stopped" : sprintf("taxi, %.0f kt", fget("ap/ground-speed-kt")), nxt];
        if (kind == "takeoff") return ["takeoff", nxt];
        if (kind == "route") {
            var n = size(it._pts) - 1;
            var v = m.vmode != nil ? m.vmode : "level";
            var heads = { climb: "climb to", descent: "descend to", level: "level at" };
            var head = heads[v];
            return [sprintf("%s %.0f ft, leg %d of %d, %.0f nmi to go", head, fget("ap/alt-cmd-ft"), m.k + 1, n, fget("ap/leg-togo-ft") / NM),
                    m.k + 1 < n ? sprintf("then leg %d", m.k + 2) : nxt];
        }
        if (kind == "hold") return [sprintf("hold at %.0f ft", it.alt), "until commanded"];
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
