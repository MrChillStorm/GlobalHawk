# Ground control station

A browser page from which the Global Hawk is supervised: you tell the aircraft what you want (a plan, "go there",
"hold", "come home") and it works out how. The autonomy is on board; this page is a terminal. **Close it and the
aircraft notices the silence and flies its lost-link route home.**

This is the first part: the command link and a first station page. The flight display, alerts, the plan editor,
several stations with a handover and hand-flying with a stick come next.

## Run it

Without FlightGear, against the flight model itself (needs Python with `jsbsim`, `numpy`, `scipy`):

```
python3 fdm/gcs_server.py            # add --speed 10 to fly ten times as fast
```

then open <http://localhost:5400/gcs/>. The aircraft stands on its stand, engine running.

1. **Demo plan**: the plan is drawn dashed in blue. Nothing has been sent. **Send**.
2. **Start**, **Send**: it taxis out, takes off and flies the route.
3. In the air: **Go to…** and click the map, **Hold here**, **Altitude…**, **Resume plan**, **Return home**.
4. Close the tab in flight: 30 s later the aircraft turns for home and lands.

With FlightGear (`fgfs --httpd=5400`, once the aircraft package is complete) the page is pointed at it the same
way: `index.html?host=…&port=5400`. Also `&station=LRE` (the station's name) and `&latency=1200` (milliseconds
of delay each way, as over a satellite).

Tests: `npm test` in this folder (plain `node`, nothing to install); `python3 fdm/phase8a_checks.py` flies a
whole scenario through the link.

## What the page shows

- **Doing / Next**: what the aircraft is doing now and what comes after, in its own words.
- **Altitude and speed** with the target the aircraft is flying towards beside them.
- **Link**: whether the aircraft is hearing this station, and what it will do if it stops hearing it.
- **The map**: the plan as the aircraft holds it (white), the leg or hold it is flying (magenta), **the
  lost-link route (amber, dashed), always**, landing sites (green), and in blue dashes whatever you are
  preparing and have not sent.
- **Sent**: every command and its fate: sent, accepted, rejected with the aircraft's reason, or no answer.

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
- `js/map.js`, `js/main.js`, `index.html`, `css/gcs.css`: the page. Plain JavaScript, no build step.
- The aircraft's end: `fdm/onboard.py` and `fdm/missionmgr.py` (Python, for the checks and the simulator server;
  the same logic goes into the aircraft's Nasal for FlightGear).

The demo field is made up. There is no background map yet, only a grid and a scale.
