# The Global Hawk's head-up display for the nose camera: FlightGear's full-screen Canvas HUD interface
# (Huds/HUDInterface.nas in FlightGear's data; aircraft.HUD loads this file into the namespace "hud" and makes HUD.new()).
#
# One colour, the green of a real HUD's phosphor. Conformal: the horizon line, the pitch ladder and the flight path
# marker lie on the outside world as the camera sees it.
#
# What it shows is what the aircraft's own laws have: nothing here flies it.

var nasal_dir = getprop("/sim/fg-root") ~ "/Huds/";
io.load_nasal(nasal_dir ~ "HUDInterface.nas", "hud");

var J = "/fdm/jsbsim/";
var D2R = math.pi / 180.0;
# The green of a real HUD's phosphor (P43, about 545 nm): on the screen, red 0.30 and blue 0.25 of the green.
# FlightGear's renderer does not show a canvas colour as given: under a full green it lifts red and blue by
# themselves. Measured in screenshots (fdm/phase9c_checks.py): given (0.30, 1, 0.25) it showed 0.55 and 0.47 of the
# green; given pure green it shows 0.32 and 0.27, which is the colour wanted. So pure green is what is given.
var GREEN = [0.0, 1.0, 0.0];
var FONT = "LiberationFonts/LiberationSansNarrow-Bold.ttf";
var MONO = "LiberationFonts/LiberationMono-Bold.ttf";
var BRIGHT = [1.0, 0.7, 0.45];
var NM = 6076.1;

# The earth, WGS84, as the mission manager has it (Nasal/missionmgr.nas, fdm/wgs84.py, js/geo.js: docs/PLAN.md, "One earth"). This file is loaded by aircraft.HUD into a namespace of its own, apart from the
# aircraft's, so what the HUD uses is a copy here: ecef, enu, ft_per_deg and from_enu, to the letter. Positions are [lat, lon]
# in degrees; a local frame is the tangent plane at an origin, north and east in feet.
var A_M = 6378137.0;                       # WGS84 semi-major axis, m
var F_INV = 298.257223563;                 # WGS84 flattening: 1 / F_INV
var E2 = (1.0 / F_INV) * (2.0 - 1.0 / F_INV);     # first eccentricity squared
var FT_PER_M = 1.0 / 0.3048;

# the point on the ellipsoid's surface, metres from the earth's centre
var ecef = func(lat, lon) {
    var p = lat * D2R;
    var l = lon * D2R;
    var sp = math.sin(p);
    var n = A_M / math.sqrt(1.0 - E2 * sp * sp);
    return [n * math.cos(p) * math.cos(l), n * math.cos(p) * math.sin(l), n * (1.0 - E2) * sp];
};
# [north, east] ft of the point p in the tangent plane at o
var enu = func(o, p) {
    var a = ecef(o[0], o[1]);
    var b = ecef(p[0], p[1]);
    var dx = b[0] - a[0];
    var dy = b[1] - a[1];
    var dz = b[2] - a[2];
    var sp = math.sin(o[0] * D2R);
    var cp = math.cos(o[0] * D2R);
    var sl = math.sin(o[1] * D2R);
    var cl = math.cos(o[1] * D2R);
    var e = -sl * dx + cl * dy;
    var n = -sp * cl * dx - sp * sl * dy + cp * dz;
    return [n * FT_PER_M, e * FT_PER_M];
};
# feet in a degree of latitude and in a degree of longitude at the latitude (the meridian's and the parallel's radii of the ellipsoid)
var ft_per_deg = func(lat) {
    var s = math.sin(lat * D2R);
    var w = math.sqrt(1.0 - E2 * s * s);
    var m = A_M * (1.0 - E2) / (w * w * w);
    var nn = A_M / w;
    return [m * D2R * FT_PER_M, nn * math.cos(lat * D2R) * D2R * FT_PER_M];
};
# [lat, lon] of the surface point at (n, e) ft in the tangent plane at o: Newton steps on enu() from the local scale (at most 12, stopped when both residuals are under 0.00001 ft)
var from_enu = func(o, n, e) {
    var k = ft_per_deg(o[0]);
    var lat = o[0] + n / k[0];
    var lon = o[1] + e / k[1];
    for (var i = 0; i < 12; i += 1) {
        var c = enu(o, [lat, lon]);
        if (math.abs(n - c[0]) < 0.00001 and math.abs(e - c[1]) < 0.00001) break;
        k = ft_per_deg(lat);
        lat += (n - c[0]) / k[0];
        lon += (e - c[1]) / k[1];
    }
    return [lat, lon];
};

var jget = func(p, d = 0) { var v = getprop(J ~ p); return v == nil ? d : v; };
var fgget = func(p, d = 0) { var v = getprop(p); return v == nil ? d : v; };
var wrap180 = func(a) { return a - 360.0 * math.floor((a + 180.0) / 360.0); };
var clampv = func(x, lo, hi) { return x < lo ? lo : (x > hi ? hi : x); };
var tand = func(d) { return math.sin(d * D2R) / math.cos(d * D2R); };

var HUD = {
    new: func {
        var m = { parents: [HUD, HUDInterface.new()] };
        m.w = fgget("/sim/startup/xsize", 1024);
        m.h = fgget("/sim/startup/ysize", 640);
        m.u = m.h / 640.0;                       # everything is sized for a window 640 high and scaled from there
        m.bright = 0;
        m.wanted = fgget("/sim/hud/visible", 1);
        # drawn straight onto FlightGear's overlay, as its standard HUD is. (Drawn into a canvas of its own at twice
        # the size and shown as a picture, for smoother lines, the whole window went black: not pursued.)
        m.g = m.root.createChild("group");
        m.g.setScale(m.u, m.u);
        m.hw = m.w / 2 / m.u;                    # half the window in the HUD's own units
        m.hh = 320.0;
        m.build();
        m.timer = maketimer(0, func {
            var err = [];
            call(HUD.update, [], m, nil, err);
            if (size(err)) { printlog("alert", "Global Hawk HUD: ", err[0]); m.timer.stop(); }
        });
        m.timer.start();
        m.listeners = [
            setlistener("/sim/current-view/view-number", func m.show(), 0, 0),
            setlistener("/sim/sceneryloaded", func m.show(), 0, 0),
            setlistener("/sim/hud/visible", func(n) { m.wanted = n.getBoolValue(); m.show(); }, 0, 0),
            setlistener("/sim/startup/xsize", func m.resized(), 0, 0),
            setlistener("/sim/startup/ysize", func m.resized(), 0, 0),
        ];
        m.show();
        return m;
    },
    del: func {
        me.timer.stop();
        foreach (var l; me.listeners) removelistener(l);
        me.root.removeAllChildren();
    },
    # the window changed its size: FlightGear makes the HUD anew
    resized: func {
        if (me.w == fgget("/sim/startup/xsize", me.w) and me.h == fgget("/sim/startup/ysize", me.h)) return;
        settimer(func { if (aircraft.HUD.currentHUD == me) aircraft.HUD.load_current_HUD(); }, 0.5);
    },
    set_visibility: func(visible) { me.wanted = visible; me.show(); },
    get_visible: func { return me.wanted; },
    # only through the nose camera: from outside the aircraft it would lie over the picture of it
    show: func {
        var on = me.wanted and which_camera() != nil and fgget("/sim/sceneryloaded", 0);      # through the cameras only; not over the splash screen
        me.root.setVisible(on);
        setprop("/sim/globalhawk/hud/shown", on ? 1 : 0);
    },
    cycle_color: func { },                       # one colour
    cycle_brightness: func {
        me.bright = math.mod(me.bright + 1, size(BRIGHT));
        me.g.removeAllChildren();                # drawn anew in the dimmer or brighter green
        me.build();
    },

    # ---- drawing helpers
    # A line: FlightGear draws the overlay without anti-aliasing, so a nearly level line is now one row of pixels
    # thick, now two, as it moves (the horizon line grew fat while the camera was pitched). Each line is drawn twice:
    # itself, and under it a wider, faint one, which softens the steps and hides the change.
    path: func(parent, width = 1.6) {
        var k = BRIGHT[me.bright];
        var make = func(w, alpha) {
            return parent.createChild("path").setStrokeLineWidth(w).setColor(GREEN[0] * k, GREEN[1] * k, GREEN[2] * k, alpha).set("stroke-linecap", "round");
        };
        var soft = make(width + 1.8, 0.30);
        var core = make(width, 1.0);
        var both = { parents: [Both], a: soft, b: core };
        return both;
    },
    text: func(parent, size, align = "center-center", font = nil) {
        return parent.createChild("text").setFont(font == nil ? FONT : font).setFontSize(size).setAlignment(align).setColor(GREEN[0] * BRIGHT[me.bright], GREEN[1] * BRIGHT[me.bright], GREEN[2] * BRIGHT[me.bright]).setText("");
    },
    clip: func(group, x0, y0, x1, y1) {
        group.set("clip-frame", canvas.Element.LOCAL);
        group.set("clip", sprintf("rect(%.1f, %.1f, %.1f, %.1f)", y0, x1, y1, x0));
        return group;
    },

    build: func {
        # the nose camera's display, and the belly camera's (the sensor operator's): one of them shows
        me.flight = me.g.createChild("group");
        me.sensor = me.g.createChild("group");
        me.build_sensor();
        var g = me.flight;
        me.ppr = 1.0;                            # set every frame from the camera's field of view

        # ---- the world: horizon, pitch ladder, flight path marker; turned about the aircraft's own axis
        me.world_clip = me.clip(g.createChild("group"), -me.hw * 0.60, -me.hh * 0.70, me.hw * 0.60, me.hh * 0.60);
        me.world = me.world_clip.createChild("group");
        me.ladder = me.world.createChild("group");
        me.bars = [];                            # [group, degrees]
        for (var d = -90; d <= 90; d += 5) {
            var b = me.ladder.createChild("group");
            var p = me.path(b, d == 0 ? 2.0 : 1.5);
            if (d == 0) {
                p.moveTo(-340, 0).lineTo(-44, 0).moveTo(44, 0).lineTo(340, 0);
            } else {
                var out = math.mod(d, 10) == 0 ? 92 : 66;
                var tick = d > 0 ? 7 : -7;       # the ends point at the horizon
                if (d > 0) {
                    p.moveTo(-out, tick).lineTo(-out, 0).lineTo(-36, 0).moveTo(36, 0).lineTo(out, 0).lineTo(out, tick);
                } else {
                    # below the horizon: dashed
                    foreach (var s; [-1, 1]) {
                        p.moveTo(s * out, tick).lineTo(s * out, 0);
                        for (var x = out; x > 36 + 1; x -= 14) p.moveTo(s * x, 0).lineTo(s * maxf(x - 9, 36), 0);
                    }
                }
                if (math.mod(d, 10) == 0) {
                    foreach (var s; [-1, 1])
                        me.text(b, 13, s < 0 ? "right-center" : "left-center").setText(sprintf("%d", math.abs(d))).setTranslation(s * (out + 5), tick * 0.6);
                }
            }
            append(me.bars, [b, d]);
        }
        # the flight path marker: where the aircraft is going
        me.fpm = me.world.createChild("group");
        me.path(me.fpm, 1.8).moveTo(-7, 0).arcSmallCW(7, 7, 0, 14, 0).arcSmallCW(7, 7, 0, -14, 0)
            .moveTo(-7, 0).lineTo(-22, 0).moveTo(7, 0).lineTo(22, 0).moveTo(0, -7).lineTo(0, -15);
        # the runway's aiming point on an approach: a small open square on the ground where the aircraft is to touch
        me.aim = me.world.createChild("group");
        me.path(me.aim, 1.5).moveTo(-9, -5).lineTo(-9, 5).lineTo(-4, 5).moveTo(4, 5).lineTo(9, 5).lineTo(9, -5).lineTo(4, -5).moveTo(-4, -5).lineTo(-9, -5);
        # the aircraft's own axis: fixed in the picture
        me.axis = me.world.createChild("group");
        me.path(me.axis, 1.8).moveTo(-30, 0).lineTo(-12, 0).lineTo(-6, 7).lineTo(0, 0).lineTo(6, 7).lineTo(12, 0).lineTo(30, 0);

        # ---- heading: a scale along the top, the heading in figures over it, the course to steer as a caret
        me.hdg_px = 9.0;                         # per degree
        var hy = -me.hh * 0.80;
        me.hdg_clip = me.clip(g.createChild("group"), -190, hy - 30, 190, hy + 12);
        me.hdg_scale = me.hdg_clip.createChild("group");
        var p = me.path(me.hdg_scale, 1.4);
        for (var d = -40; d <= 40; d += 5) p.moveTo(d * me.hdg_px, hy).lineTo(d * me.hdg_px, hy - (math.mod(d, 10) == 0 ? 9 : 5));
        me.hdg_labels = [];
        for (var k = 0; k < 9; k += 1) append(me.hdg_labels, me.text(me.hdg_clip, 13, "center-bottom"));
        me.hdg_y = hy;
        me.path(g, 1.6).moveTo(0, hy + 2).lineTo(-6, hy + 11).lineTo(6, hy + 11).close();
        # the value's box has the same dark backing as the speed's and the height's frames (tape()), under the figures and the outline
        g.createChild("path").setColorFill(0, 0, 0, 0.35).setStrokeLineWidth(0).rect(-27, hy - 53, 54, 23, { "border-radius": 3 });
        me.hdg_text = me.text(g, 19, "center-center", MONO).setTranslation(0, hy - 42);
        me.path(g, 1.3).rect(-27, hy - 53, 54, 23, { "border-radius": 3 });
        me.course = me.hdg_clip.createChild("group");
        me.path(me.course, 1.6).moveTo(0, hy - 10).lineTo(-6, hy - 19).lineTo(0, hy - 28).lineTo(6, hy - 19).close();

        # ---- speed on the left, height on the right: a moving scale, the value in a frame, the target as a caret
        me.spd = me.tape(-me.hw * 0.66, -1, 3.2, 5, 10, "%d", 34);
        me.alt = me.tape(me.hw * 0.66, 1, 0.26, 100, 500, "%d", 58);            # five figures: 5 x 14 px and a margin
        me.mach = me.text(g, 14, "left-center").setTranslation(me.spd.x - 62, 128);
        me.spd_target = me.text(g, 14, "left-center").setTranslation(me.spd.x - 62, -128);
        me.alt_target = me.text(g, 14, "right-center").setTranslation(me.alt.x + 74, -128);
        me.vs = me.text(g, 14, "right-center").setTranslation(me.alt.x + 74, 128);
        me.ralt = me.text(g, 14, "right-center").setTranslation(me.alt.x + 74, 148);

        # ---- bank: a scale under the picture's middle, a pointer that leans with the aircraft, the laws' limit
        var R = me.hh * 0.72;
        me.bank_r = R;
        p = me.path(g, 1.4);
        foreach (var a; [-45, -30, -20, -10, 0, 10, 20, 30, 45]) {
            var long = (a == 0 or math.abs(a) == 30) ? 13 : 7;
            p.moveTo(R * math.sin(a * D2R), R * math.cos(a * D2R)).lineTo((R + long) * math.sin(a * D2R), (R + long) * math.cos(a * D2R));
        }
        me.bank = g.createChild("group");
        me.path(me.bank, 1.6).moveTo(0, R - 2).lineTo(-6, R - 13).lineTo(6, R - 13).close();
        me.bank_limit = [g.createChild("group"), g.createChild("group")];
        foreach (var b; me.bank_limit) me.path(b, 1.4).moveTo(0, R + 2).lineTo(0, R + 20);

        # ---- figures: lower left what the aircraft is, lower right where it is going
        me.left = [];
        for (var k = 0; k < 5; k += 1) append(me.left, me.text(g, 14, "left-center").setTranslation(-me.hw * 0.90, 150 + 19 * k));
        me.right = [];
        for (var k = 0; k < 2; k += 1) append(me.right, me.text(g, 14, "right-center").setTranslation(me.hw * 0.90, 188 + 19 * k));
        # ---- what the laws are doing, and what the crew must know
        me.doing = me.text(g, 15, "center-center").setTranslation(0, me.hh * 0.86);
        me.then = me.text(g, 12, "center-center").setTranslation(0, me.hh * 0.86 + 17);
        me.alert = me.text(g, 19, "center-center").setTranslation(0, -me.hh * 0.52);
    },

    # The belly camera's overlay, for the sensor operator: a cross on what it looks at, where that is and how far,
    # which way the camera points and how far it is zoomed in, and the aircraft's own figures small in a corner
    build_sensor: func {
        var g = me.sensor;
        me.path(g, 1.5).moveTo(-70, 0).lineTo(-14, 0).moveTo(14, 0).lineTo(70, 0).moveTo(0, -70).lineTo(0, -14).moveTo(0, 14).lineTo(0, 70);
        var p = me.path(g, 1.5);
        foreach (var sx; [-1, 1])
            foreach (var sy; [-1, 1])
                p.moveTo(sx * 150, sy * 100).lineTo(sx * 150, sy * 130).lineTo(sx * 120, sy * 130);
        # locked: the corners close to a box
        me.s_lock = g.createChild("group");
        me.path(me.s_lock, 1.5).moveTo(-150, -130).lineTo(150, -130).lineTo(150, 130).lineTo(-150, 130).close();
        me.s_top = me.text(g, 15, "center-center").setTranslation(0, -me.hh * 0.86);
        me.s_left = [];
        for (var k = 0; k < 4; k += 1) append(me.s_left, me.text(g, 14, "left-center").setTranslation(-me.hw * 0.90, me.hh * 0.62 + 19 * k));
        me.s_right = [];
        for (var k = 0; k < 4; k += 1) append(me.s_right, me.text(g, 14, "right-center").setTranslation(me.hw * 0.90, me.hh * 0.62 + 19 * k));
        me.s_note = me.text(g, 14, "center-center").setTranslation(0, me.hh * 0.86);
    },
    sensor_update: func(cam_hdg, cam_el, fov) {
        var agl = jget("position/h-agl-ft");
        var lat = jget("position/lat-geod-deg");
        var lon = jget("position/long-gc-deg");
        me.s_top.setText(sprintf("BELLY CAMERA   AZ %03d   DEP %4.1f   FOV %4.1f", math.mod(math.floor(cam_hdg + 0.5), 360), -cam_el, fov));
        var lines = ["", "", "", ""];
        var note = "";
        var tlat = 0;
        var tlon = 0;
        if (cam_el < -0.5 and agl > 1) {
            # where the camera's line meets the ground, taken level at the height under the aircraft, and found in the tangent plane at the aircraft
            var along = agl / tand(-cam_el);
            var slant = agl / math.sin(-cam_el * D2R);
            var t = from_enu([lat, lon], along * math.cos(cam_hdg * D2R), along * math.sin(cam_hdg * D2R));
            tlat = t[0];
            tlon = t[1];
            lines[0] = sprintf("%s %08.5f", tlat >= 0 ? "N" : "S", math.abs(tlat));
            lines[1] = sprintf("%s %09.5f", tlon >= 0 ? "E" : "W", math.abs(tlon));
            lines[2] = slant < 3 * NM ? sprintf("RNG %d FT", math.floor(slant / 10 + 0.5) * 10) : sprintf("RNG %.1f NM", slant / NM);
            lines[3] = sprintf("GND %d FT", math.floor((jget("position/h-sl-ft") - agl) / 10 + 0.5) * 10);
            if (along > 80 * NM) note = "NEAR THE HORIZON: POSITION ROUGH";
        } else note = "ABOVE THE HORIZON";
        forindex (var i; me.s_right) me.s_right[i].setText(lines[i]);
        var own = [
            sprintf("HDG %03d", math.mod(math.floor(fgget("/orientation/heading-deg") + 0.5), 360)),
            sprintf("ALT %d FT", math.floor(jget("position/h-sl-ft") / 10 + 0.5) * 10),
            sprintf("%d KCAS  M %.2f", math.floor(jget("velocities/vc-kts") + 0.5), jget("velocities/mach")),
            sprintf("AGL %d FT", math.floor(agl / 10 + 0.5) * 10),
        ];
        forindex (var i; me.s_left) me.s_left[i].setText(own[i]);
        # the lock
        var lock = getprop("/sim/globalhawk/camera/lock") or "";
        if (lock != "") note = sprintf("LOCKED ON %s   %.1f NM", string.uc(getprop("/sim/globalhawk/camera/name") or ""), getprop("/sim/globalhawk/camera/range-nm") or 0) ~ (note != "" ? "   " ~ note : "");
        me.s_lock.setVisible(lock != "");
        me.s_note.setText(note);
        if (cam_el < -0.5 and agl > 1) {
            setprop("/sim/globalhawk/hud/sensor-lat", tlat);
            setprop("/sim/globalhawk/hud/sensor-lon", tlon);
        }
        setprop("/sim/globalhawk/hud/sensor-azimuth-deg", cam_hdg);
        setprop("/sim/globalhawk/hud/sensor-depression-deg", -cam_el);
    },

    # a moving vertical scale at x, figures on the side away from the middle. Returns what update needs
    tape: func(x, side, px, tick_every, label_every, fmt, box_w) {
        var t = { x: x, side: side, px: px, tick: tick_every, label: label_every, fmt: fmt };
        var half = 105;
        t.clip = me.clip(me.flight.createChild("group"), x - 70, -half, x + 70, half);
        t.scale = t.clip.createChild("group");
        var p = me.path(t.scale, 1.4);
        var n = int(half / (px * tick_every)) + int(label_every / tick_every) + 2;
        for (var k = -n; k <= n; k += 1) {
            var major = math.mod(k * tick_every, label_every) == 0;
            p.moveTo(x, k * tick_every * px).lineTo(x + side * (major ? 10 : 5), k * tick_every * px);
        }
        t.labels = [];
        var m = int(half / (px * label_every)) + 2;
        for (var k = -m; k <= m; k += 1) append(t.labels, me.text(t.clip, 13, side > 0 ? "left-center" : "right-center").setTranslation(x + side * 15, 0));
        t.m = m;
        # the value: figures in a frame that points at the scale, over the scale's own figures
        var bx = x + side * 14;
        var frame = me.flight.createChild("group");
        frame.createChild("path").setColorFill(0, 0, 0, 0.35).setStrokeLineWidth(0)
            .moveTo(bx, -12).lineTo(bx + side * (box_w + 24), -12).lineTo(bx + side * (box_w + 24), 12).lineTo(bx, 12).close();
        me.path(frame, 1.4).moveTo(x + side * 3, 0).lineTo(bx, -7).lineTo(bx, -12).lineTo(bx + side * (box_w + 24), -12)
            .lineTo(bx + side * (box_w + 24), 12).lineTo(bx, 12).lineTo(bx, 7).close();
        # in the frame's middle: the frame is as wide as the longest value (a figure of this font is 14 px wide as
        # FlightGear draws it; the height's five did not fit a frame made for the speed's three)
        t.value = me.text(frame, 20, "center-center", MONO).setTranslation(bx + side * (box_w + 24) / 2, 0);
        t.bug = me.flight.createChild("group");
        me.path(t.bug, 1.6).moveTo(x - side * 3, 0).lineTo(x - side * 12, -6).lineTo(x - side * 12, 6).close();
        t.half = half;
        return t;
    },
    tape_update: func(t, value, shown, target) {
        var base = math.floor(value / t.label) * t.label;
        t.scale.setTranslation(0, (value - base) * t.px);
        forindex (var i; t.labels) {
            var v = base + (i - t.m) * t.label;
            t.labels[i].setTranslation(t.x + t.side * 15, (value - v) * t.px);
            t.labels[i].setText(v < 0 ? "" : sprintf(t.fmt, v));
            t.labels[i].setVisible(math.abs(value - v) * t.px > 17);       # not under the value's frame
        }
        t.value.setText(shown);
        if (target == nil) t.bug.hide();
        else {
            t.bug.show();
            t.bug.setTranslation(0, clampv((value - target) * t.px, -t.half, t.half));
        }
    },

    update: func {
        if (!me.root.getVisible()) return;
        var roll = fgget("/orientation/roll-deg");
        var pitch = fgget("/orientation/pitch-deg");
        var hdg = fgget("/orientation/heading-deg");
        # the camera: its field of view across the window, and where it looks relative to the aircraft's axis
        var fov = fgget("/sim/current-view/field-of-view", 70);
        me.ppr = me.hw / tand(fov / 2.0);        # the HUD's units per unit of tangent
        var poff = fgget("/sim/current-view/pitch-offset-deg");
        var hoff = wrap180(fgget("/sim/current-view/heading-offset-deg"));
        # Where the camera looks, whichever way it is turned: its axes in the aircraft (the view's heading offset is
        # positive to the left, its pitch offset up), carried into the world by the aircraft's attitude. From them the
        # camera's own heading, elevation and roll, which the world's symbology is drawn by
        var a = -hoff * D2R;
        var p = poff * D2R;
        var f = to_world([math.cos(p) * math.cos(a), math.cos(p) * math.sin(a), -math.sin(p)], hdg, pitch, roll);
        var r = to_world([-math.sin(a), math.cos(a), 0], hdg, pitch, roll);
        var d = to_world([math.sin(p) * math.cos(a), math.sin(p) * math.sin(a), math.cos(p)], hdg, pitch, roll);
        var cam_el = math.asin(clampv(-f[2], -1, 1)) / D2R;
        var cam_hdg = math.atan2(f[1], f[0]) / D2R;
        var cam_roll = math.atan2(r[2], d[2]) / D2R;
        var cam = which_camera();
        me.flight.setVisible(cam == "nose");
        me.sensor.setVisible(cam == "belly");
        setprop("/sim/globalhawk/hud/camera", cam == nil ? "" : cam);
        if (cam == "belly") {
            me.sensor_update(math.mod(cam_hdg, 360), cam_el, fov);
            return;
        }
        # the world turns about the picture's middle by the camera's roll; the horizon is below it by its elevation
        me.world.setCenter(0, 0);
        me.world.setRotation(math.abs(cam_roll) < 0.25 ? 0 : -cam_roll * D2R);      # level when it is all but level: no steps along the lines
        var hy = me.ppr * tand(cam_el);
        foreach (var b; me.bars) {
            var near = math.abs(b[1] - cam_el) < 26;
            b[0].setVisible(near);
            # on whole pixels: a level line that lies between two rows of them is drawn now one row thick, now two,
            # as it moves (seen as the horizon line growing fat while the camera was pitched quickly)
            if (near) b[0].setTranslation(0, math.floor((hy - me.ppr * tand(b[1])) * me.u + 0.5) / me.u);
        }
        # a direction in the world (heading, elevation) in that turned picture; nil when it is far off to a side
        var place = func(az, el) {
            var off = wrap180(az - cam_hdg);
            if (math.abs(off) > 40) return nil;
            return [me.ppr * tand(off) * math.cos(cam_el * D2R), hy - me.ppr * tand(el)];
        };
        var gs = jget("velocities/vg-fps");
        var gamma = jget("flight-path/gamma-deg");
        var trk = jget("flight-path/psi-gt-rad") / D2R;
        if (gs < 40) { gamma = pitch; trk = hdg; }          # standing or taxiing: on the axis
        var at = place(trk, gamma);
        me.fpm.setVisible(at != nil);
        if (at != nil) me.fpm.setTranslation(at[0], at[1]);
        # the aircraft's own axis: upright in the picture when the camera looks along it
        at = place(hdg, pitch);
        me.axis.setVisible(at != nil);
        if (at != nil) {
            me.axis.setTranslation(at[0], at[1]);
            me.axis.setRotation((cam_roll - roll) * D2R);
        }
        me.aim_update(cam_hdg, hy, place);

        # heading
        var base = math.floor(hdg / 10.0) * 10.0;
        me.hdg_scale.setTranslation(-(hdg - base) * me.hdg_px, 0);
        forindex (var i; me.hdg_labels) {
            var v = base + (i - 4) * 10;
            me.hdg_labels[i].setTranslation((v - hdg) * me.hdg_px, me.hdg_y - 11);
            me.hdg_labels[i].setText(sprintf("%02d", math.mod(v, 360) / 10));
        }
        var shown_hdg = math.mod(math.floor(hdg + 0.5), 360);
        me.hdg_text.setText(sprintf("%03d", shown_hdg));
        var manual = jget("ap/manual");
        var steer = jget("ap/roll-mode") == 2 ? jget("ap/track-cmd-deg") : (jget("ap/roll-mode") == 1 ? jget("ap/heading-cmd-deg") : nil);
        if (steer == nil or manual > 0) me.course.hide();
        else {
            me.course.show();
            me.course.setTranslation(clampv(wrap180(steer - hdg), -20, 20) * me.hdg_px, 0);
        }

        # speed and height
        var kcas = jget("velocities/vc-kts");
        var alt = jget("position/h-sl-ft");
        var auto = jget("ap/engaged") == 1 and manual == 0;
        var t_kcas = jget("ap/speed-target-kcas");
        var t_alt = jget("ap/alt-cmd-ft");
        var shown_kcas = math.floor(kcas + 0.5);
        var shown_alt = math.floor(alt / 10.0 + 0.5) * 10;
        me.tape_update(me.spd, kcas, sprintf("%3d", shown_kcas), auto ? t_kcas : nil);
        me.tape_update(me.alt, alt, sprintf("%5d", shown_alt), auto ? t_alt : nil);
        me.mach.setText(sprintf("M %.2f", jget("velocities/mach")));
        me.spd_target.setText(auto ? sprintf("%d", math.floor(t_kcas + 0.5)) : "");
        me.alt_target.setText(auto ? sprintf("%d", math.floor(t_alt + 0.5)) : "");
        var fpm = jget("velocities/h-dot-fps") * 60.0;
        me.vs.setText(sprintf("%s%d", fpm >= 0 ? "+" : "-", math.floor(math.abs(fpm) / 50.0 + 0.5) * 50));
        var agl = jget("aero/wheel-height-ft", 99999);
        me.ralt.setText(agl < 2500 ? sprintf("R %d", agl < 0 ? 0 : (agl < 200 ? math.floor(agl + 0.5) : math.floor(agl / 10 + 0.5) * 10)) : "");

        # bank
        me.bank.setRotation(-roll * D2R);
        var lim = jget("ap/bank-limit-deg");
        me.bank_limit[0].setRotation(-lim * D2R);
        me.bank_limit[1].setRotation(lim * D2R);
        foreach (var b; me.bank_limit) b.setVisible(lim > 1 and lim < 50);

        # figures
        var gear = jget("gear/gear-pos-norm");
        var splr = jget("ctl/spoiler-norm");
        var lines = [
            sprintf("AOA %4.1f  LIM %4.1f", jget("aero/alpha-deg"), jget("ap/alpha-limit-deg")),
            sprintf("G %4.2f", jget("accelerations/Nz", 1)),
            sprintf("THR %3d", math.floor(jget("ctl/throttle-norm") * 100 + 0.5)),
            sprintf("FUEL %5d", math.floor(jget("fuel/total-lbs") / 10 + 0.5) * 10),
            (gear > 0.98 ? "GEAR" : (gear > 0.02 ? "GEAR ..." : "")) ~ (splr > 0.02 ? sprintf("   SPLR %d", math.floor(splr * 100 + 0.5)) : ""),
        ];
        forindex (var i; me.left) me.left[i].setText(lines[i]);
        var togo = jget("ap/leg-togo-ft") / NM;
        var st = (globals["globalhawk"] != nil and globalhawk["onboard"] != nil) ? globalhawk.onboard.last : nil;
        var kind = st != nil ? st["kind"] : nil;
        var on_leg = kind != nil and (kind == "route" or kind == "land" or kind == "takeoff" or kind == "taxi" or kind == "engine_out");
        me.right[0].setText(on_leg ? sprintf(togo < 10 ? "TO GO %.1f NM" : "TO GO %.0f NM", togo) : "");
        me.right[1].setText(on_leg ? sprintf("XTK %.2f NM", jget("ap/leg-xt-ft") / NM) : "");

        # the laws, and the alerts
        var doing = "";
        var then = "";
        var alert = "";
        var warning = 0;
        if (st != nil) {
            doing = string.uc(st["doing"] ~ "");
            then = string.uc(st["next"] ~ "");
            # one line: the first warning, else the cautions in turn (3 s each), the angle-of-attack one holding the line while it is up (it is the one that is over in seconds; the first
            # caution in the list used to be all that was shown, and FUEL LOW, up the whole flight at 1,000 lb, hid it)
            var cautions = [];
            foreach (var a; st["alerts"]) {
                if (a["level"] == "warning") {
                    alert = a["text"];
                    warning = 1;
                    break;
                }
                if (a["level"] == "caution") append(cautions, a);
            }
            if (!warning and size(cautions)) {
                var pick = cautions[math.mod(math.floor(fgget("/sim/time/elapsed-sec") / 3.0), size(cautions))];
                foreach (var c; cautions) if (c["id"] == "aoa") pick = c;
                alert = pick["text"];
            }
        } elsif (manual > 0) doing = manual == 1 ? "FLOWN BY HAND (PROTECTED)" : "FLOWN BY HAND (DIRECT)";
        if (st != nil and st["started"].json != "true" and manual > 0) doing = "ON THE GROUND: " ~ doing;
        me.doing.setText(doing);
        me.then.setText(then);
        me.alert.setText(alert);
        setprop("/sim/globalhawk/hud/alert", alert);                       # what is shown, for the checks
        me.alert.setVisible(!warning or math.mod(fgget("/sim/time/elapsed-sec"), 1.0) < 0.65);      # a warning flashes

        # what is shown, for the checks
        setprop("/sim/globalhawk/hud/kcas", shown_kcas);
        setprop("/sim/globalhawk/hud/alt-ft", shown_alt);
        setprop("/sim/globalhawk/hud/heading-deg", shown_hdg);
        setprop("/sim/globalhawk/hud/target-kcas", auto ? math.floor(t_kcas + 0.5) : -1);
        setprop("/sim/globalhawk/hud/target-alt-ft", auto ? math.floor(t_alt + 0.5) : -1);
        setprop("/sim/globalhawk/hud/horizon-y", hy * me.u + me.h / 2);       # the horizon at the picture's middle column, in window pixels, wings level
        setprop("/sim/globalhawk/hud/doing", doing);
        setprop("/sim/globalhawk/hud/camera-heading-deg", cam_hdg);
        setprop("/sim/globalhawk/hud/camera-elevation-deg", cam_el);
        setprop("/sim/globalhawk/hud/camera-roll-deg", cam_roll);
    },

    # on an approach, the aiming point: the far end of the leg, on the runway
    aim_update: func(cam_hdg, hy, place) {
        var show = jget("ap/land-mode") == 1 and jget("ap/rollout") == 0;
        me.aim.setVisible(show);
        if (!show) return;
        var lat = jget("position/lat-geod-deg");
        var ne = enu([lat, jget("position/long-gc-deg")], [jget("ap/leg-lat1-deg"), jget("ap/leg-lon1-deg")]);       # north and east of the aircraft to the end of the leg, in the tangent plane at the aircraft
        var dn = ne[0];
        var de = ne[1];
        var dist = math.sqrt(dn * dn + de * de);
        if (dist < 300) { me.aim.hide(); return; }
        var below = math.atan2(jget("position/h-sl-ft") - jget("ap/rwy-elev-ft"), dist) / D2R;
        var at = place(math.atan2(de, dn) / D2R, -below);
        if (at == nil) { me.aim.hide(); return; }
        me.aim.setTranslation(at[0], at[1]);
    },
};

var maxf = func(a, b) { return a > b ? a : b; };

# which of the aircraft's cameras the current view is: "nose", "belly", or nil for a view from outside
var which_camera = func {
    var name = getprop("/sim/current-view/name");
    if (name == nil) return nil;
    if (name == "Nose Camera") return "nose";
    if (name == "Belly Camera") return "belly";
    return nil;
};

# two paths drawn as one (see HUD.path)
var Both = {
    moveTo: func(x, y) { me.a.moveTo(x, y); me.b.moveTo(x, y); return me; },
    lineTo: func(x, y) { me.a.lineTo(x, y); me.b.lineTo(x, y); return me; },
    arcSmallCW: func(rx, ry, rot, dx, dy) { me.a.arcSmallCW(rx, ry, rot, dx, dy); me.b.arcSmallCW(rx, ry, rot, dx, dy); return me; },
    rect: func(x, y, w, h, cfg = nil) { me.a.rect(x, y, w, h, cfg); me.b.rect(x, y, w, h, cfg); return me; },
    close: func { me.a.close(); me.b.close(); return me; },
};

# a vector in the aircraft (x forward, y right, z down) in the world (north, east, down), by its heading, pitch and roll
var to_world = func(v, hdg, pitch, roll) {
    var cf = math.cos(roll * D2R); var sf = math.sin(roll * D2R);
    var ct = math.cos(pitch * D2R); var st = math.sin(pitch * D2R);
    var cp = math.cos(hdg * D2R); var sp = math.sin(hdg * D2R);
    # roll about x, then pitch about y, then heading about z
    var x1 = v[0]; var y1 = v[1] * cf - v[2] * sf; var z1 = v[1] * sf + v[2] * cf;
    var x2 = x1 * ct + z1 * st; var z2 = -x1 * st + z1 * ct;
    return [x2 * cp - y1 * sp, x2 * sp + y1 * cp, z2];
};
