# Ground control station

A browser page from which the Global Hawk is supervised: you tell the aircraft what you want (a plan, "go there",
"hold", "come home") and it works out how. The autonomy is on board; this page is a terminal. **Close it and the
aircraft notices the silence and flies its lost-link route home.**

So far: the command link, a map, a flight display, engine, fuel and navigator status, one alert list, a plan
editor with a forecast of time, fuel and height, several stations with a handover between them, and flying by hand
with a gamepad or the keyboard, other aircraft on the map, and a demo that needs nothing but this folder.

## Try it with nothing else: the demo

Open `index.html?demo=1` (add `&speed=10` to run it ten times as fast). The aircraft is then a stand-in inside
the page: it takes the same commands and answers in the same words, but it is **not the flight model**, only a
point that follows the plan with the real aircraft's climb, descent and turn rates. Good for learning the station;
the demo strip can fail the engine or cut the link. It has no flying by hand and one station only.

## Run it

Without FlightGear, against the flight model itself (needs Python with `jsbsim`, `numpy`, `scipy`):

```
python3 fdm/gcs_server.py            # add --speed 10 to fly ten times as fast
```

then open <http://localhost:5400/gcs/>. The aircraft stands on its stand, engine running.

1. **Demo plan**: the plan is drawn dashed in blue. Nothing has been sent. **Send**.
2. **Start**, **Send**: it taxis out, takes off and flies the route.
3. In the air: **Go to…** and click the map, **Hold here**, **Altitude…**, **Resume plan**, **Return home**.
4. **Edit plan**: click the map to add a point, drag points, change heights; **Send plan…** when it looks right.
5. Close the tab in flight: 30 s later the aircraft turns for home and lands.

With FlightGear the page is pointed at it the same way: start FlightGear with the aircraft and `--httpd=5400`
at any airport, open `index.html` (from the folder is fine; `?host=…&port=5400` if FlightGear is elsewhere), then
**Plan from here**, **Send**, **Start**, **Send**. "Plan from here" lays a local flight from the runway the
aircraft stands on: takeoff straight ahead, a box at 15,000 ft, a landing on the same runway. The aircraft's end
of the link runs in FlightGear's Nasal (`GlobalHawk/Nasal/`). The demo plan is for the made-up field of the
simulator server, not for FlightGear. Also `&station=LRE` (the station's name; `MCE` gets 1.2 s of delay each
way, an assumed figure for a satellite link) and `&latency=…` in milliseconds to set the delay yourself.

Tests: `npm test` in this folder (plain `node`, nothing to install); `python3 fdm/phase8a_checks.py` flies a
whole scenario through the link; `fdm/phase8c_checks.py` holds the forecast and the two ports against the model.

## What the page shows

- **Doing / Next**: what the aircraft is doing now and what comes after, in its own words.
- **Altitude and speed** with the target the aircraft is flying towards beside them.
- **Link**: whether the aircraft is hearing this station, and what it will do if it stops hearing it. After 3 s without an
  uplink from the station in control the note becomes a count ("the aircraft has not heard this station for 12 s: route home
  in 18 s"). The loss of the link has a tone of its own, two notes in turn, that no other alert uses; when the link comes back
  **LINK RESTORED** stands for 20 s. Closing the page asks first when this station has control of a flight.
- **Station**: its name, the connection and its address, how long ago the aircraft was last heard, the **link delay** (chosen
  while the page runs: none, 0.6, 1.2 or 2.4 s), the measured **answer time** (the median of the last five commands the
  aircraft answered, in ms) and the input read for flying by hand.
- **Messages**: a line of up to 200 characters to the other stations, at once, not delayed by the link and not through the
  aircraft; the last eight are shown with who sent them and when they arrived. The demo has one station and no messages.
- **north up / track up** on the map: the arrow in the corner always points to north.
- **The map**: the plan as the aircraft holds it (white), the leg or hold it is flying (magenta), **the
  lost-link route (amber, dashed), always**, landing sites (green), and in blue dashes whatever you are
  preparing and have not sent.
- **Sent**: every command and its fate: sent, accepted, rejected with the aircraft's reason, or no answer.
- **Alerts**, under the strip: one list, the worst on top, each with what to do. The aircraft raises them, so every
  station sees the same; the station adds only "no link". A tone sounds for a new warning or caution until **OK**
  (click the page once first: browsers give no sound before that).
- **The flight display**: attitude with a flight path marker (where the aircraft is going) and its acceleration
  chevron; a speed tape with the target in magenta, a 10 s trend arrow and **red where the aircraft cannot fly**:
  below, the angle-of-attack limit, above, Mach 0.63 or 175 KCAS. High up the two close in. Altitude with target and
  trend, vertical speed, heading with the track (green) and the leg's course (magenta); bank limit in amber.
- **Engine and fuel**: running or failed, thrust, fuel flow, hours left at that flow, the six tanks.
- **Navigators**: the four attitude sources; a button switches one off or on (confirmed, like any command).
- **Glide reach**, in flight: a dotted green ring is how far the aircraft's own planner would count on gliding
  without the engine, and each landing site says what height it would have in hand there, or OUT OF REACH.
- **Other aircraft** (FlightGear's AI and multiplayer traffic): an arrowhead with its callsign and its height
  against ours in hundreds of feet. One that will come inside 0.75 nmi and 450 ft raises TRAFFIC, AVOID (within
  55 s) or TRAFFIC, MANEUVER NOW (within 25 s); a pass inside 1 nmi and 700 ft, TRAFFIC, MONITOR. The levels are
  those of NASA's detect-and-avoid studies; the prediction here is a simple straight-line one, and no avoiding
  manoeuvre is suggested.
- **The height profile** under the map: the heights the plan asks for (dashed) and the height forecast.

## Several stations, and handing over

Open the page more than once, each with its own `?station=` name: they are separate crew positions. **The aircraft
decides who has control**: the first station it hears. The others watch: same map, same alerts, commands greyed.
The lost-link watch follows the station in control, not the watchers.

To hand over, the station in control ticks its three checks under **Control** and offers control to another;
that one ticks its own three and accepts, and control passes at that moment. If the station in control goes
silent and the link is declared lost, any other station may **Take control**.

## Flying by hand

Enroute, the station in control can choose **Protected** or **Direct** under **By hand** (confirmed like any
command). Protected: the stick asks for pitch rate and bank angle and the aircraft keeps its limits. Direct: the
surfaces follow the stick, with no limits. **Automatic** gives it back: the aircraft holds where it is.

A gamepad is used if one is connected (left stick pitch and roll, right stick pedals, triggers throttle, bumpers
spoilers); otherwise keys: arrows for the stick (up is stick forward), Q/E pedals, W/S throttle, Z/X spoilers. With a
delay set, everything you do arrives that much later and what you see is that much older, which is why nobody
hand-flies the real aircraft over a satellite. If the link is lost while flying by hand, the aircraft goes back to
automatic by itself and flies its lost-link route.

## The belly camera

The Camera panel is the sensor operator's. **Lock on…** and a click on the map keeps the belly camera on that point
of the ground; **Nearest object** locks it on the nearest aircraft, ship or vehicle FlightGear has; **Unlock** frees
it. The arrows turn it (or move a locked point, while FlightGear shows the belly camera's view), and **Level
horizon** keeps the horizon level in the picture as the aircraft banks. What it is locked on is written in the panel
and drawn on the map as a green cross with the line of sight. These are not flight commands: they need no control
of the aircraft and get no acknowledgement; they arrive late by the link's delay like everything else. The demo's
stand-in aircraft has no camera.

## Editing a plan

**Edit plan** takes the plan the aircraft holds. Choose **Route** or **Lost-link route**; click the map to add a
point after the selected one, drag a point to move it, type a height, **×** to delete. Taxi, takeoff and landing
are kept as they came. While you edit, the table gives for each point the leg's length, and the **forecast** of
the time, the fuel left and whether the height asked for is reached by then; the same check the aircraft makes
runs here first, so a fault shows before sending. **Send plan…** then confirms as any command; **Save as file**
keeps it. Sent while the aircraft is enroute, the plan goes from its first route on, and the aircraft turns onto it
at once.

**The forecast** comes from a table sampled from the flight model (`js/perfdata.js`, written by
`fdm/gcs_perf.py`): climb at maximum thrust, level flight and idle descent on the speed schedule, standard
atmosphere, **no wind, no turns**. Against flights of the model it was within 3 % on time and fuel. Go to and
Return home show it too: time to get there, fuel on arrival, and for a go to the fuel left on landing if the
aircraft goes home from there. The aircraft itself does not use the forecast.

**The landing's roll** is forecast too, from the flight model's own landings at each weight (the same table): where
it touches down past the aiming point, where the rollout ends, and the runway to have past the aiming point (the
rollout and 15 % in hand, an assumed allowance; no wind, a dry level runway). A landing soon after takeoff is a
heavy one: about 5,800 ft of rollout with full tanks against 3,100 ft at the end of a long flight. Type how much
runway there is in **Runway past the aiming point** and too little is a warning, in the editor and before a
Return home. The figure is kept in the plan (`field.runway_past_aim_ft`) as the station's own note: the aircraft
does not read it, and lands where it is told.

Every command is shown or described first and goes only on **Send**. It counts only when the aircraft answers.

## The link

Everything goes through FlightGear's web server: the `PropertyListener` websocket
(`{"command":"addListener"|"get"|"set","node":path,"value":v}`) and `/json/<path>`.

| Property | Written by | Content |
|---|---|---|
| `/gcs/up/heartbeat` | station, once a second | `"NAME:n"`; from the station in control, each change tells the aircraft the link is alive |
| `/gcs/up/stick` | station in control, 20 a second by hand | `{"station","p","r","y","t","s"}`: pitch, roll, pedals -1..1; throttle, spoilers 0..1 |
| `/gcs/up/cmd` | station | `{"seq":n,"station":"LRE","name":"goto","args":{…}}` as a string |
| `/gcs/down/ack` | aircraft | `{"seq":n,"status":"accepted"` or `"rejected","reason":"…"}` |
| `/gcs/down/status` | aircraft, twice a second | doing, next, alerts, the leg or hold, targets, its last notes |
| `/gcs/down/plan` | aircraft | the plan it holds, with its lost-link route and landing sites |
| `/gcs/chat/line` | any station | `{"station","n","text","t"}`: a message to the other stations. The aircraft does not read it; FlightGear's web server (or the simulator server) hands it to every station listening |

Telemetry is FlightGear's own properties (`/position`, `/orientation`, `/velocities`) and the flight model's
under `/fdm/jsbsim/`.

| Command | Arguments | The aircraft | Refused |
|---|---|---|---|
| `plan` | a plan | checks it and takes it | when the check fails, with the fault named |
| `start` | | begins the plan: taxi and takeoff | with no plan; twice |
| `goto` | `lat`, `lon`, `alt_ft` | leaves the plan, flies there, holds over it | on the ground, landing, height outside 0-65,000 ft |
| `hold` | | circles to the right from where it is | on the ground, landing |
| `altitude` | `alt_ft` | changes the height of the leg or hold | as `goto` |
| `resume` | | returns to the leg it left | when not off the plan; engine failed |
| `home` | | flies the lost-link route and lands | with no such route; on the ground |
| `nav` | `name`, `on` | switches a navigator | unknown name |
| `linktimeout` | `sec` | sets how long the station in control may be silent before the lost-link route | not a number; under 10 s or over 300 s (assumed bounds) |
| `manual` | `mode` 0, 1, 2 | automatic, protected or direct flying by hand | 1 and 2 when not enroute |
| `control.offer` | `to` | offers control to a station it hears | to itself; to a station not heard |
| `control.cancel` | | withdraws the offer | with none made |
| `control.accept` | | the station offered to takes control | when not offered to it |
| `control.take` | | takes control | while the station in control is still heard |

Every command but the last two is done only for the station that has control; another's is refused, naming who has it.

A plan is JSON (`../Missions/demo-local.json` is one): a `field`, `items` (`taxi`, `takeoff`, `route`, `land`,
`hold`), a `lost_link` route that begins with a route and ends in a landing, and landing `sites` for a glide
without the engine. The aircraft refuses a plan with an unknown item, a point off the earth, a height outside
0-65,000 ft, a leg over 3,000 nmi, a takeoff not followed by a route, or a landing whose fix is under 8 nmi out.

## Files

- `js/link.js`: the station's end of the link (commands and their fates, heartbeat, delay), and the websocket.
- `js/geo.js`: small-area geometry, as the aircraft does it.
- `js/linkinfo.js`: the count to the lost-link route, the restored message, the closing warning and the time-out's bounds.
- `js/camera.js`: the belly camera's state and commands. `js/controls.js`: gamepad and keys to the stick message. `js/traffic.js`: other aircraft and their alert levels.
- `js/demo.js`, `js/demoplan.js`: the demo's stand-in aircraft and its plan.
- `USER-TEST.md`: how the station is to be tested with people, and the pass mark. Not run yet.
- `js/alerts.js`: the alert list's order, tones and acknowledging. `js/pfdmath.js`, `js/pfd.js`: the flight display.
- `js/predict.js` with `js/perfdata.js`: the forecast. `js/editor.js`: the plan editor's logic. `js/plancheck.js`,
  `js/reach.js`: the aircraft's plan check and glide planner, ported so the station can show them at once.
- `js/map.js`, `js/main.js`, `index.html`, `css/gcs.css`: the page. Plain JavaScript, no build step.
- The aircraft's end: `fdm/onboard.py` and `fdm/missionmgr.py` (Python, for the checks and the simulator server;
  the same logic goes into the aircraft's Nasal for FlightGear).

The demo field is made up, and so are the two aircraft the simulator server shows as traffic. There is no
background map yet, only a grid and a scale.
