# Ground control station

A browser page from which the Global Hawk is supervised: you tell the aircraft what you want (a plan, "go there",
"hold", "come home") and it works out how. The autonomy is on board; this page is a terminal. **Close it and the
aircraft notices the silence and flies its lost-link route home.**

So far: the command link, a map, a flight display, engine, fuel and navigator status, one alert list, and a plan
editor with a forecast of time, fuel and height. Several stations with a handover and hand-flying with a stick come next.

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

With FlightGear (`fgfs --httpd=5400`, once the aircraft package is complete) the page is pointed at it the same
way: `index.html?host=…&port=5400`. Also `&station=LRE` (the station's name) and `&latency=1200` (milliseconds
of delay each way, as over a satellite).

Tests: `npm test` in this folder (plain `node`, nothing to install); `python3 fdm/phase8a_checks.py` flies a
whole scenario through the link; `fdm/phase8c_checks.py` holds the forecast and the two ports against the model.

## What the page shows

- **Doing / Next**: what the aircraft is doing now and what comes after, in its own words.
- **Altitude and speed** with the target the aircraft is flying towards beside them.
- **Link**: whether the aircraft is hearing this station, and what it will do if it stops hearing it.
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
- **The height profile** under the map: the heights the plan asks for (dashed) and the height forecast.

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

Every command is shown or described first and goes only on **Send**. It counts only when the aircraft answers.

## The link

Everything goes through FlightGear's web server: the `PropertyListener` websocket
(`{"command":"addListener"|"get"|"set","node":path,"value":v}`) and `/json/<path>`.

| Property | Written by | Content |
|---|---|---|
| `/gcs/up/heartbeat` | station, once a second | a counter; each change tells the aircraft the link is alive |
| `/gcs/up/cmd` | station | `{"seq":n,"station":"LRE","name":"goto","args":{…}}` as a string |
| `/gcs/down/ack` | aircraft | `{"seq":n,"status":"accepted"` or `"rejected","reason":"…"}` |
| `/gcs/down/status` | aircraft, twice a second | doing, next, alerts, the leg or hold, targets, its last notes |
| `/gcs/down/plan` | aircraft | the plan it holds, with its lost-link route and landing sites |

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

A plan is JSON (`../Missions/demo-local.json` is one): a `field`, `items` (`taxi`, `takeoff`, `route`, `land`,
`hold`), a `lost_link` route that begins with a route and ends in a landing, and landing `sites` for a glide
without the engine. The aircraft refuses a plan with an unknown item, a point off the earth, a height outside
0-65,000 ft, a leg over 3,000 nmi, a takeoff not followed by a route, or a landing whose fix is under 8 nmi out.

## Files

- `js/link.js`: the station's end of the link (commands and their fates, heartbeat, delay), and the websocket.
- `js/geo.js`: small-area geometry, as the aircraft does it.
- `js/alerts.js`: the alert list's order, tones and acknowledging. `js/pfdmath.js`, `js/pfd.js`: the flight display.
- `js/predict.js` with `js/perfdata.js`: the forecast. `js/editor.js`: the plan editor's logic. `js/plancheck.js`,
  `js/reach.js`: the aircraft's plan check and glide planner, ported so the station can show them at once.
- `js/map.js`, `js/main.js`, `index.html`, `css/gcs.css`: the page. Plain JavaScript, no build step.
- The aircraft's end: `fdm/onboard.py` and `fdm/missionmgr.py` (Python, for the checks and the simulator server;
  the same logic goes into the aircraft's Nasal for FlightGear).

The demo field is made up. There is no background map yet, only a grid and a scale.
