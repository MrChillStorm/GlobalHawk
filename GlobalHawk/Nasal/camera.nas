# The belly camera's lock and slew: the sensor operator's controls.
#
# Locked, the camera is turned every frame to look at a point on the ground (given by its coordinates, or the point
# under the cross when the lock was made) or at a moving object: any model FlightGear has in /ai/models (other
# aircraft, multiplayer, ships, ground vehicles, whatever is put there). Free, it stays where it is turned.
# Slewing turns the free camera, moves a locked point over the ground, and offsets the aim from a locked object.
#
# Commands: the menu and the dialog call lock_cross(), lock_nearest(), lock_point(lat, lon), unlock(); anything
# else (a joystick button, the ground station) can write one into /sim/globalhawk/camera/command:
#   "cross", "nearest", "unlock", "point <lat> <lon> [<elevation ft>]", "level", "level off"
# Slew: /sim/globalhawk/camera/slew-right and slew-up, -1 to 1 (bind a joystick's hat or axes to them); with the
# belly camera's view up and the aircraft flying itself, the main stick slews too.

var CAM = "/sim/globalhawk/camera/";
var R_EARTH = 6371000.0;
var FT2M = 0.3048;
var VIEW = "Belly Camera";
var LEVEL_SIGN = -1;            # FlightGear's roll offset turns the picture the way the lean goes, so it is set against it (found by
                                # trying in a 22 deg banked turn: with +1 the horizon leaned twice as far, with -1 it lay level)

var camera = {
    mode: "",                    # "", "point" or "object"
    target: nil,                 # geo.Coord of the point
    node: nil,                   # the object's property node
    name: "",
    off_h: 0, off_p: 0,          # the aim's offset from a locked object, deg (right, up)
    level: 1,                    # the picture kept level with the horizon, whatever the aircraft's bank

    in_view: func { return (getprop("/sim/current-view/name") or "") == VIEW; },

    # a vector in the world (north, east, down) in the aircraft (forward, right, down)
    to_body: func(v) {
        var h = (getprop("/orientation/heading-deg") or 0) * D2R;
        var t = (getprop("/orientation/pitch-deg") or 0) * D2R;
        var f = (getprop("/orientation/roll-deg") or 0) * D2R;
        var x1 = v[0] * math.cos(h) + v[1] * math.sin(h);
        var y1 = -v[0] * math.sin(h) + v[1] * math.cos(h);
        var x2 = x1 * math.cos(t) - v[2] * math.sin(t);
        var z2 = x1 * math.sin(t) + v[2] * math.cos(t);
        return [x2, y1 * math.cos(f) + z2 * math.sin(f), -y1 * math.sin(f) + z2 * math.cos(f)];
    },
    # and back (as the head-up display's)
    to_world: func(v) {
        var h = (getprop("/orientation/heading-deg") or 0) * D2R;
        var t = (getprop("/orientation/pitch-deg") or 0) * D2R;
        var f = (getprop("/orientation/roll-deg") or 0) * D2R;
        var y1 = v[1] * math.cos(f) - v[2] * math.sin(f);
        var z1 = v[1] * math.sin(f) + v[2] * math.cos(f);
        var x2 = v[0] * math.cos(t) + z1 * math.sin(t);
        var z2 = -v[0] * math.sin(t) + z1 * math.cos(t);
        return [x2 * math.cos(h) - y1 * math.sin(h), x2 * math.sin(h) + y1 * math.cos(h), z2];
    },
    # where the camera looks now, in the world: [heading deg, elevation deg]
    looking: func {
        var a = -(getprop("/sim/current-view/heading-offset-deg") or 0) * D2R;
        var p = (getprop("/sim/current-view/pitch-offset-deg") or 0) * D2R;
        var f = me.to_world([math.cos(p) * math.cos(a), math.cos(p) * math.sin(a), -math.sin(p)]);
        return [math.atan2(f[1], f[0]) / D2R, math.asin(math.max(-1, math.min(1, -f[2]))) / D2R];
    },
    # how far the picture leans: the camera's roll about its own line of sight with no roll of its own, deg, right
    # side down positive (from the aircraft's bank and where the camera is turned)
    leaning: func {
        var a = -(getprop("/sim/current-view/heading-offset-deg") or 0) * D2R;
        var p = (getprop("/sim/current-view/pitch-offset-deg") or 0) * D2R;
        var r = me.to_world([-math.sin(a), math.cos(a), 0]);
        var d = me.to_world([math.sin(p) * math.cos(a), math.sin(p) * math.sin(a), math.cos(p)]);
        return math.atan2(r[2], d[2]) / D2R;
    },
    # turn the camera to a direction in the world
    look: func(hdg, el) {
        var v = me.to_body([math.cos(el * D2R) * math.cos(hdg * D2R), math.cos(el * D2R) * math.sin(hdg * D2R), -math.sin(el * D2R)]);
        var h = geo.normdeg(-math.atan2(v[1], v[0]) / D2R);
        var p = math.atan2(-v[2], math.sqrt(v[0] * v[0] + v[1] * v[1])) / D2R;
        setprop("/sim/current-view/goal-heading-offset-deg", h);
        setprop("/sim/current-view/heading-offset-deg", h);
        setprop("/sim/current-view/goal-pitch-offset-deg", p);
        setprop("/sim/current-view/pitch-offset-deg", p);
    },
    # the direction and the slant range from the aircraft to a place: [heading deg, elevation deg, range m]
    towards: func(c) {
        var here = geo.aircraft_position();
        var d = here.distance_to(c);
        var dh = c.alt() - here.alt() - d * d / (2 * R_EARTH);         # the earth's curve drops it
        return [here.course_to(c), math.atan2(dh, math.max(d, 0.1)) / D2R, math.sqrt(d * d + dh * dh)];
    },
    # the ground under the camera's cross, or nil when it looks above the horizon: the terrain's own height there,
    # found in a few steps from the height under the aircraft
    under_cross: func {
        var look = me.looking();
        if (look[1] > -0.3) return nil;
        var here = geo.aircraft_position();
        var ground = (getprop("/position/ground-elev-m") or 0);
        var c = nil;
        for (var i = 0; i < 4; i += 1) {
            var along = (here.alt() - ground) / math.tan(-look[1] * D2R);
            if (along > 400000) return nil;
            c = geo.Coord.new(here).apply_course_distance(look[0], along);
            var g = geodinfo(c.lat(), c.lon());
            if (g == nil or g[0] == nil) break;
            ground = g[0];
        }
        c.set_alt(ground);
        return c;
    },

    # ---- the locks
    lock_point: func(lat, lon, elev_ft = nil) {
        var c = geo.Coord.new().set_latlon(lat, lon);
        if (elev_ft == nil) {
            var g = geodinfo(lat, lon);
            c.set_alt((g != nil and g[0] != nil) ? g[0] : (getprop("/position/ground-elev-m") or 0));
        } else c.set_alt(elev_ft * FT2M);
        me.mode = "point"; me.target = c; me.node = nil;
        me.name = sprintf("%s %.5f %s %.5f", lat >= 0 ? "N" : "S", math.abs(lat), lon >= 0 ? "E" : "W", math.abs(lon));
        me.tell("Camera locked on " ~ me.name);
    },
    lock_cross: func {
        if (!me.in_view()) { me.tell("Go to the belly camera's view first"); return; }
        var c = me.under_cross();
        if (c == nil) { me.tell("The camera looks above the horizon: nothing to lock on"); return; }
        me.lock_point(c.lat(), c.lon(), c.alt() / FT2M);
    },
    # every model FlightGear has, as [node, geo.Coord, name]
    objects: func {
        var out = [];
        var models = props.globals.getNode("/ai/models");
        if (models == nil) return out;
        foreach (var n; models.getChildren()) {
            var lat = n.getNode("position/latitude-deg");
            var lon = n.getNode("position/longitude-deg");
            if (lat == nil or lon == nil or lat.getValue() == nil or lon.getValue() == nil) continue;
            var valid = n.getNode("valid");
            if (valid != nil and !valid.getBoolValue()) continue;
            var alt = n.getNode("position/altitude-ft");
            var c = geo.Coord.new().set_latlon(lat.getValue(), lon.getValue(), (alt != nil and alt.getValue() != nil ? alt.getValue() : 0) * FT2M);
            var name = n.getNode("callsign") != nil ? n.getNode("callsign").getValue() : nil;
            if (name == nil or name == "") name = n.getNode("name") != nil ? n.getNode("name").getValue() : nil;
            if (name == nil or name == "") name = n.getName() ~ " " ~ n.getIndex();
            append(out, [n, c, name ~ ""]);
        }
        return out;
    },
    # the object nearest the cross, within the picture
    lock_nearest: func {
        if (!me.in_view()) { me.tell("Go to the belly camera's view first"); return; }
        var look = me.looking();
        var fov = getprop("/sim/current-view/field-of-view") or 40;
        var best = nil;
        var least = 1e9;
        foreach (var o; me.objects()) {
            var t = me.towards(o[1]);
            var dh = geo.normdeg180(t[0] - look[0]) * math.cos(look[1] * D2R);
            var off = math.sqrt(dh * dh + (t[1] - look[1]) * (t[1] - look[1]));
            if (off < least) { least = off; best = o; }
        }
        if (best == nil or least > 0.6 * fov) { me.tell("No object in the picture"); return; }
        me.mode = "object"; me.node = best[0]; me.name = best[2]; me.target = nil; me.off_h = 0; me.off_p = 0;
        me.tell("Camera locked on " ~ me.name);
    },
    unlock: func {
        if (me.mode != "") me.tell("Camera unlocked");
        me.mode = ""; me.target = nil; me.node = nil; me.name = "";
    },
    tell: func(text) { gui.popupTip(text, 4); setprop(CAM ~ "said", text); },

    # ---- every frame
    update: func(dt) {
        var sr = getprop(CAM ~ "slew-right") or 0;
        var su = getprop(CAM ~ "slew-up") or 0;
        var view = me.in_view();
        # the main stick, while the aircraft flies itself and the camera's picture is up
        if (view and (getprop("/fdm/jsbsim/ap/manual") or 0) == 0 and (getprop("/fdm/jsbsim/ap/engaged") or 0) == 1) {
            var a = getprop("/controls/flight/aileron") or 0;
            var e = getprop("/controls/flight/elevator") or 0;
            if (math.abs(a) > 0.08) sr += a;
            if (math.abs(e) > 0.08) su -= e;                  # pulled back: the camera looks up
        }
        sr = math.max(-1, math.min(1, sr));
        su = math.max(-1, math.min(1, su));
        var fov = getprop("/sim/current-view/field-of-view") or 40;
        var rate = 0.6 * fov;                                 # deg/s at full slew: the picture's width in under two seconds
        var slewing = math.abs(sr) > 0.01 or math.abs(su) > 0.01;
        if (me.mode == "object") {
            var lat = me.node.getNode("position/latitude-deg");
            var valid = me.node.getNode("valid");
            if (lat == nil or lat.getValue() == nil or (valid != nil and !valid.getBoolValue())) {
                me.tell(me.name ~ " is gone: camera unlocked");
                me.unlock();
            } else {
                var alt = me.node.getNode("position/altitude-ft");
                me.target = geo.Coord.new().set_latlon(lat.getValue(), me.node.getNode("position/longitude-deg").getValue(),
                                                       (alt != nil and alt.getValue() != nil ? alt.getValue() : 0) * FT2M);
                if (slewing) { me.off_h += sr * rate * dt; me.off_p += su * rate * dt; }
            }
        }
        if (me.mode != "" and me.target != nil) {
            var t = me.towards(me.target);
            setprop(CAM ~ "range-nm", t[2] / 1852.0);
            setprop(CAM ~ "target-lat", me.target.lat());
            setprop(CAM ~ "target-lon", me.target.lon());
            setprop(CAM ~ "target-alt-ft", me.target.alt() / FT2M);
            setprop(CAM ~ "bearing-deg", t[0]);
            setprop(CAM ~ "elevation-deg", t[1]);
            if (view) {
                if (me.mode == "point" and slewing) {
                    # move the point: turn the camera, and take the ground under the cross as the new point
                    var look = me.looking();
                    # not above a degree under the horizon: there is no ground to lock on up there
                    me.look(look[0] + sr * rate * dt / math.max(math.cos(look[1] * D2R), 0.2), math.min(look[1] + su * rate * dt, -1.0));
                    var c = me.under_cross();
                    if (c != nil) {
                        me.target = c;
                        me.name = sprintf("%s %.5f %s %.5f", c.lat() >= 0 ? "N" : "S", math.abs(c.lat()), c.lon() >= 0 ? "E" : "W", math.abs(c.lon()));
                    }
                } else {
                    var oh = me.mode == "object" ? me.off_h / math.max(math.cos(t[1] * D2R), 0.2) : 0;
                    me.look(t[0] + oh, t[1] + (me.mode == "object" ? me.off_p : 0));
                }
            }
        } elsif (view and slewing) {
            var look = me.looking();
            me.look(look[0] + sr * rate * dt / math.max(math.cos(look[1] * D2R), 0.2), math.max(-89.5, math.min(30, look[1] + su * rate * dt)));
        }
        # the horizon's stabilisation: the camera rolled about its line of sight against the picture's lean, so the
        # horizon stays level as the aircraft banks (most real turrets leave it leaning). Looking nearly straight
        # down there is no horizon to hold: the roll is faded out over the last 10 deg
        if (view) {
            var roll = 0;
            if (me.level) {
                var steep = math.abs(me.looking()[1]);
                roll = LEVEL_SIGN * me.leaning() * math.max(0, math.min(1, (88 - steep) / 10));
            }
            setprop("/sim/current-view/goal-roll-offset-deg", roll);
            setprop("/sim/current-view/roll-offset-deg", roll);
        }
        setprop(CAM ~ "level", me.level);
        setprop(CAM ~ "lock", me.mode);
        setprop(CAM ~ "name", me.name);
    },
    set_level: func(on) {
        me.level = on ? 1 : 0;
        me.tell(me.level ? "Camera: the horizon is kept level" : "Camera: the picture leans with the aircraft");
    },

    command: func(text) {
        if (text == nil or text == "") return;
        var w = split(" ", text ~ "");
        if (w[0] == "cross") me.lock_cross();
        elsif (w[0] == "nearest") me.lock_nearest();
        elsif (w[0] == "unlock") me.unlock();
        elsif (w[0] == "level") me.set_level(size(w) < 2 or w[1] != "off");
        elsif (w[0] == "point" and size(w) >= 3 and num(w[1]) != nil and num(w[2]) != nil)
            me.lock_point(num(w[1]), num(w[2]), size(w) > 3 ? num(w[3]) : nil);
        else me.tell("Camera: not understood: " ~ text);
    },
    # the dialog's fields
    lock_entered: func {
        var lat = num(getprop(CAM ~ "enter-lat"));
        var lon = num(getprop(CAM ~ "enter-lon"));
        if (lat == nil or lon == nil or math.abs(lat) > 90 or math.abs(lon) > 180) { me.tell("Latitude and longitude in degrees, south and west negative"); return; }
        me.lock_point(lat, lon);
    },
    # a button's nudge: a tenth of the picture
    nudge: func(right, up) {
        setprop(CAM ~ "slew-right", right);
        setprop(CAM ~ "slew-up", up);
        settimer(func { setprop(CAM ~ "slew-right", 0); setprop(CAM ~ "slew-up", 0); }, 0.17);
    },
};

setlistener("/sim/signals/fdm-initialized", func {
    foreach (var k; ["slew-right", "slew-up"]) setprop(CAM ~ k, 0);
    foreach (var k; ["command", "lock", "name", "enter-lat", "enter-lon"]) setprop(CAM ~ k, "");
    setlistener(CAM ~ "command", func(n) {
        var err = [];
        call(camera.command, [n.getValue()], camera, nil, err);
        if (size(err)) printlog("alert", "Global Hawk camera: ", err[0]);
    }, 0, 1);
    var last = systime();
    var loop = maketimer(0, func {
        var now = systime();
        var err = [];
        call(camera.update, [math.min(now - last, 0.2)], camera, nil, err);
        last = now;
        if (size(err)) { printlog("alert", "Global Hawk camera: ", err[0]); loop.stop(); }
    });
    loop.start();
}, 0, 0);
