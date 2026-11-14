# Ground control station

A browser page from which the Global Hawk is supervised: you tell the aircraft what you want (a plan, "go there",
"hold", "come home") and it works out how. The autonomy is on board; this page is a terminal. **Close it and the
aircraft notices the silence and flies its lost-link route home.**

So far: the command link, a map with layers (base maps, airspace, weather, airports, the link's limit), a flight display, engine, fuel and navigator status, one alert list, a plan
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
- **Map layers** (the **Layers** button on the map): a base map, airspace, weather, airports, the line-of-sight limit and more, each **Off, Auto or
  On**, with a **Declutter** button. See "Map layers" below.

## Map layers

The map has a base map and layers on it, chosen in the **Layers** panel (a popover over the map: it opens no window and the map stays in use).
Each layer is **Off**, **Auto** or **On**. **On** and **Off** are yours. **Auto** shows the layer while its reason holds and **says why**, in a chip
under the toolbar ("Airspace: R-2508 restricted, entered 25 nmi ahead ✕"); the ✕ puts it away until the reason has gone and come back. Nearly
everything starts on Auto, so the screen is as clean as before and things arrive when they matter.

| Layer | Shows | Comes up by itself when |
|---|---|---|
| **Link range** | how far a station that needs line of sight can hear the aircraft at its height (the radio horizon, 1.23 × (√h₁ + √h₂) nmi: the most the link could reach, over a smooth earth, not what it does reach), and at the plan's highest point; the station is taken to be at the field with a 30 ft antenna | **forced** near the limit: within 15 % of it, or the path reaches it in 10 minutes (NASA's list for remote pilot stations asks for exactly this). No ring for a satellite station (MCE, or 600 ms of delay and more) |
| **Traffic**, **Glide reach**, **Camera target**, **Trail** | what the station always had | traffic within 60 nmi (forced while a traffic alert stands); flying (forced while the engine is out); the camera is locked; trail always |
| **Airspace** | restricted, prohibited, danger, warning and alert areas, MOAs, TFRs, controlled B, C, D; Auto shows the zones that reach the aircraft's height, On shows all heights; Class A and E are never drawn. The heights are read as MSL (an AGL limit is marked), the **times of use are not read** | the plan is being edited, or a zone is inside, ahead on the path (20 minutes) or crossed by the plan. The station then also raises an alert, never louder than a caution. The airspace of the aircraft's own field is not news |
| **Weather hazards** | SIGMET and G-AIRMET areas for turbulence, icing, convection and ash that reach the aircraft's height | one meets the path, by NASA's rules for this aircraft (see below) |
| **Airports** | fields with a long runway, marked **usable now** (the station's own landing forecast at the present weight, plus 800 ft for the aiming point) or **only lighter** (at the reserve weight); On shows the short ones too | on the field, in a contingency, when planning, below 18,000 ft, or within 100 nmi of the landing |
| **Airport weather (METAR)** | category, wind and the crosswind on the best runway at the airports shown and the landing sites | with the airports |
| **Terrain** | ground within 500 ft below the aircraft's height (lighter) or above it (darker) | flying below 15,000 ft and more than 1,000 ft above the ground; engine out |
| **Rain radar** | the newest radar picture | flying at or below FL500, where NASA's rule is to stay 25 nmi from thunderstorms |
| **Cloud tops (infrared)** | infrared satellite, cold = high, from the satellite that looks at the map's centre | flying above FL500, where tops matter; planning |
| **Winds aloft** | wind arrows at the pressure level nearest the aircraft's height, and the head or tail wind on each leg (now, or +3 to +24 h) | planning; a headwind of 40 kt or more on the leg |
| **Loaded areas** | GeoJSON you load: a survey box, a storm to chase | a file is loaded |

**Rules that keep it calm:** a reason must hold for 2 s before a layer comes up and be false for 60 s before it goes; at most three layers come up by
themselves at once on top of the station's own picture (the most safety-relevant first; the others wait, and the panel says so); nothing opens a
window or moves the map; the **forced** layers (the link's edge, a traffic alert, an engine out) show even when Off or decluttered, for as long as the
cause lasts. **Declutter** puts every optional layer away and a second click brings the same ones back. The plan, the aircraft, the active leg and
the lost-link route are not layers and are never hidden. The numbers (2 s, 60 s, three) are choices made here: none is published.

**NASA's rules for this aircraft** (Cecil et al., "Weather avoidance guidelines for NASA Global Hawk", the 2012 rules): at or below FL500 stay 25 nmi from thunderstorms;
above FL500 stay 25 nmi from reported lightning where the tops are FL500 or higher, and 10,000 ft above it where they are lower; no flight into forecast or
reported icing; none into forecast or reported moderate or severe turbulence. The station applies them to the SIGMET polygons it has and says what it compared:
**a SIGMET is not a thunderstorm report, a polygon is not the weather, and a cell can grow faster than any data shows**, so a weather layer is an aid to a
judgement and never a clearance. Nothing here refuses, changes or sends a command.

**Where the data comes from** (all free, nothing needs an account or a key): base maps from Esri (dark gray, satellite), OpenStreetMap and OpenTopoMap; airports and
runways from OurAirports (17 MB the first time, then kept in the browser); airspace from the FAA's open-data service (US only, shared quota: when it says it is busy
the station asks again after a minute) or from files; radar from RainViewer; satellite from NASA GIBS (GOES, Himawari) and EUMETSAT (Meteosat); winds from Open-Meteo;
US observations from the National Weather Service; terrain from Terrarium tiles. SIGMETs, G-AIRMETs and METAR for the rest of the world come from aviationweather.gov,
which sends no header that lets a web page read it, so they need the small helper: `node tools/awc-proxy.js`, then open the station with `?awc=http://localhost:5402`.
The helper passes six paths of that one service on, to this computer only, and keeps nothing. **All of it is real-world data, not the simulator's weather.**
Files can be loaded in the Layers panel or dropped on the map: airspace (OpenAir, GeoJSON as the FAA's service gives it, OpenAIP JSON), airports and runways
(OurAirports' CSV files), areas (any other GeoJSON).

**Go offline** (in the panel, or `?offline=1`) stops every request to anyone else; the map then shows the grid and what was loaded from files or kept in the browser.
The tiles and data are asked of other people's servers, which see the area being looked at. The demo has made-up airspace, fields, a report and wind around its made-up field.

Address options: `?layers=airspace:on,wx-radar:off` (set layers), `?base=none|dark|streets|topo|satellite`, `?offline=1`, `?awc=…` (the helper),
`?tiles=http://localhost:9000` (every tile asked of a local fake that serves `{id}/{z}/{x}/{y}.png`, for testing), `?sources=…` (an OurAirports mirror).
`node tools/overlay-probe.js` asks the real services through the station's own modules and says what came back.

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

The Camera panel is the sensor operator's. **A click on the map locks the camera there**: on an aircraft (at its height), a landing site,
a route point, an airfield, or the bare place (not while a command or the plan editor is waiting for a click; a tick box in the panel turns it
off). That is the same as **Lock on…** and a click, which stays. A click on an aircraft locks on where it was at that moment, not on the aircraft:
**Nearest object** is the one that follows it. **Lock on…** and a click on the map keeps the belly camera on that point
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

## The route planner

In the plan editor (route being edited) **Plan a route** works out a route from where the route begins (the takeoff's end, or the aircraft when it is flying) to the plan's
landing fix, and shows it as **cards**, as a map program does. Choose, then **Find routes**:

- **Least fuel**, **Fastest**, **Cautious** and the **Direct** route to compare with. Each card gives time, fuel, distance, height, how it differs from the least-fuel one, what it goes
  round (or, for the direct one, what it crosses) and its **emergency landing sites**: "a landing site in glide reach all the way", or the longest stretch with none. Routes that are practically
  one (every point within 5 nmi, the same height) are one card with both names. Click a card to see it on the map (cyan dashes; amber where no site is in reach). **Use this route** puts its
  points into the editor, and **Undo** gives the old route back exactly. Nothing is sent: **Send plan…** does that, through the confirm bar, and the aircraft checks the plan.
- **Emergency landing sites: Prefer, Require or Off** (the operator's choice, kept in the browser). A site is in reach when the distance to it plus 5.3 nmi is within 0.85 of the
  aircraft's own planner's glide radius at the height there (`(height - the site's height - 3,500 ft) x 20`, still air: `js/reach.js`; the 0.85 is this station's margin for turns and
  wind), which is low in the climb and the descent, and within 12 nmi of a site it is in its pattern. **Prefer** (the default) makes a stretch out of reach cost a third more, so that a detour is taken to stay covered;
  **Require** never leaves the reach of a site and may find no route (over the sea, for one: it then says how long the direct route's gap is); **Off** does not look at sites at all. The sites are
  the plan's own and the airports that can hold the landing at the present weight (a paved runway of what the landing forecast asks plus 800 ft); "count shorter strips too" adds paved runways of
  at least three quarters of that (a landing that may run off its end: the MV-22B's engine-out finder keeps such strips as a last resort too) and marks them. With no airports loaded only the plan's sites count, and it says so.
- **Height:** the best of 10,000 to 65,000 ft in 5,000 ft steps (the ones the route is long enough to climb to and come down from, at the weight, by the station's own tables), or one you choose.
- **The winds aloft** (Open-Meteo, the pressure level of each height, now or +3 to +24 h from the Layers panel) change the ground speed along each join, so the route leans on a tailwind and
  keeps out of a headwind; the editor then also shows the forecast **with** them (the aircraft does not use it, and the forecast above it stays the no-wind one).
- **What it goes round:** restricted, prohibited, danger and TFR areas at the cruise height (2 nmi of room; the aircraft's own home airspace, which cannot be avoided, is left out), turbulence and icing
  areas at that height (NASA's rules 4 and 5; 1.5 nmi), and convection with 25 nmi at or below FL500 or where the tops are FL500 or more, 10,000 ft over the tops otherwise (NASA's rules 1 and 2; the **Cautious** route doubles
  the room). MOAs and warning areas cost a quarter more. **Not looked at:** terrain, radar echoes, traffic, the times of use of airspace, the climb and the descent against the zones (only the cruise is), step
  climbs (a height the weight does not allow at the start is not offered), and points the route must visit. SIGMET areas need the helper (see the layers); without it none are avoided, and it says so.
  **A SIGMET area is the weather the station has, and a route round it is not a route round the weather.**
- The method is this station's own (a lattice of 0.25 degrees, each point joined to its 16 nearest directions, Dijkstra's path on fuel or time, thinned and checked again); the real aircraft's is not public.
  It takes a few seconds with real data (the wind fetch is most of it, once).

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
- `js/layers.js` (the layers' modes, rules and declutter), `js/overlayctx.js` (the situation, and each layer's Auto rule), `js/overlays.js` (what is drawn, the data each layer asks for, the panel),
  `js/tiles.js` (slippy-map tiles through the station's projection), `js/airspace.js`, `js/airports.js`, `js/weather.js`, `js/linkrange.js`, `js/terrain.js`, `js/palette.js`,
  `js/store.js` (what is kept in the browser), `js/pick.js` (what a click lands on), `js/demodata.js` (the demo's made-up zones, fields and weather),
  `tools/awc-proxy.js` (the weather helper), `tools/overlay-probe.js`. The route planner: `js/router.js` (lattice, hard and soft areas, emergency-site coverage, heights, the four routes),
  `js/routeinputs.js` (what it is given from a plan, and the words on a card); the forecast's wind option is in `js/predict.js`.
- `js/map.js`, `js/main.js`, `index.html`, `css/gcs.css`: the page. Plain JavaScript, no build step.
- The aircraft's end: `fdm/onboard.py` and `fdm/missionmgr.py` (Python, for the checks and the simulator server;
  the same logic goes into the aircraft's Nasal for FlightGear).

The demo field is made up, and so are the two aircraft the simulator server shows as traffic. With no connection the map is a grid and a scale.
