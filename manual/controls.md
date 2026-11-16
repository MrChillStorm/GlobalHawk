# Every control of the station and of the aircraft's menu

The manual's control tables are made from this file by `manual/mkmanual.py`, which also checks it against the
page (`GlobalHawk/gcs/index.html`), the aircraft's menu (`GlobalHawk/GlobalHawk-set.xml`) and the camera dialog:
a control that is there and not here stops the build. The first column is the control's id in the page, or its
label in a menu or dialog; the second is what the operator sees.

## Map

| id | Shown as | What it does |
|---|---|---|
| map | the map | The plan the aircraft holds in white, the leg or hold being flown in magenta, the lost-link route in amber dashes, landing sites in green, other aircraft as arrowheads, the camera's target as a green cross, and in blue dashes whatever is being prepared and not yet sent. Drag to move it, the wheel to zoom. A click gives a point to a command that waits for one. |
| follow | follow | Keeps the aircraft in the middle of the map. Dragging the map switches it off. |
| fit | plan | Shows the whole plan. |
| orient | north up / track up | Turns the map: north at the top, or the way the aircraft is going (its track) at the top. The arrow in the corner points to north. |
| profile | the height profile | Under the map: the heights the plan asks for, dashed, and the height forecast. |

## Confirming a command

| id | Shown as | What it does |
|---|---|---|
| confirm-yes | Send | Sends the command that is described in the bar. Nothing goes to the aircraft before this. |
| confirm-no | Cancel | Drops the command being prepared. |

## Control

| id | Shown as | What it does |
|---|---|---|
| ctl-to | Hand over to | The station to offer control to: one the aircraft is hearing. |
| ctl-offer-go | Offer control | Offers control to that station, once the three checks above it are ticked. |
| ctl-cancel | Withdraw the offer | Takes the offer back; an offer lapses by itself after two minutes. |
| ctl-accept-go | Accept control | At the station offered to: takes control, once its own three checks are ticked. |
| ctl-take | Take control | Shown only when the station that had control is no longer heard and the link is declared lost. |

## By hand

| id | Shown as | What it does |
|---|---|---|
| m-auto | Automatic | Gives the aircraft back to itself: it holds the height and place it has. |
| m-prot | Protected | The stick asks for pitch rate and bank; the aircraft keeps its limits. Enroute only. |
| m-direct | Direct | The surfaces follow the stick; no limits. Enroute only. |
| stick | the stick's picture | Where the stick, pedals, throttle and spoilers are now, and whether a gamepad or the keys are read. |

## Commands

| id | Shown as | What it does |
|---|---|---|
| c-demo | Demo plan | Loads the plan that ships with the aircraft, for the made-up field of the simulator server and the demo. |
| c-here | Plan from here | Lays a local flight from the runway the aircraft stands on: take-off straight ahead, a box at 15,000 ft, a landing on the same runway. |
| c-file | Plan file | Loads a plan from a file. |
| c-edit | Edit plan | Opens the editor on the plan the aircraft holds, or on the one just loaded. |
| c-start | Start | Begins the plan: taxi and take-off. |
| c-goto | Go to… | Then click the map: the aircraft leaves its plan, flies to the point at the height given and holds over it. |
| c-hold | Hold here | The aircraft circles to the right from where it is. |
| c-alt | Altitude… | Changes the height of the leg or hold being flown. |
| c-resume | Resume plan | Back to the leg that was left. |
| c-home | Return home | Flies the lost-link route and lands. |
| c-timeout | Link time-out… | Sets how long the aircraft may go without hearing the station in control before it leaves its plan for the lost-link route. Only the station in control; the aircraft takes 10 to 300 s. |

## Clearances

| id | Shown as | What it does |
|---|---|---|
| clr-go | Clear… | Appears with the Clearances panel when the plan's taxi routes have holds. Clears the hold the aircraft is waiting at, after you confirm; it names the hold and says what the aircraft will do next. Only the station in control; it is off when the aircraft is not waiting at a hold. |

## Station

| id | Shown as | What it does |
|---|---|---|
| st-delay | Link delay | What this station's link adds each way to commands and to what comes down: none (line of sight), 0.6 s, 1.2 s (satellite) or 2.4 s. Takes effect on the next message. The rows above it say the station's name, the connection and how long ago the aircraft was last heard; the rows below it how long the aircraft takes to answer a command and which input is read for flying by hand. |

## Messages

| id | Shown as | What it does |
|---|---|---|
| msg-text | to the other stations | A line of up to 200 characters to the other stations. Enter sends it. |
| msg-send | Send message | Sends it. It reaches the other stations at once, not delayed by the link, and does not go through the aircraft. |

## Camera

| id | Shown as | What it does |
|---|---|---|
| cam-point | Lock on… | Then click the map: the belly camera stays on that point of the ground. |
| cam-nearest | Nearest object | Locks the belly camera on the nearest aircraft, ship or vehicle FlightGear has. |
| cam-unlock | Unlock | Frees the camera: it stays where it is turned. |
| cam-level | Level horizon | Keeps the horizon level in the camera's picture as the aircraft banks. |
| cam-left | ◀ | Turns the camera left, or moves a locked point left, by about a tenth of the picture. |
| cam-up | ▲ | The same, up. |
| cam-down | ▼ | The same, down. |
| cam-right | ▶ | The same, right. |

## Plan editor

| id | Shown as | What it does |
|---|---|---|
| ed-route | Route | Edits the plan's route. |
| ed-lost | Lost-link route | Edits the route flown when the link is lost. |
| ed-runway | Runway past the aiming point, ft | How much runway there is from the aiming point to the far end. The landing's forecast is held against it; the aircraft does not read it. |
| gd-icao | Airport | The four-letter code of the airport whose scenery FlightGear has (EFHK). Filled in from the nearest field when the editor opens. |
| gd-load | Load the ground map | Asks the aircraft for the airport's stands, taxiways and runway ends, which it reads from FlightGear's scenery; they are drawn as the Stands and Taxiways layers. Any station may ask: it moves nothing. |
| gd-pick | Pick the stand… | Then click a stand on the map; a click anywhere else makes a stand of your own there. The stand is kept in the plan (field.stand, field.stand_heading). |
| gd-hdg | facing | The way the aircraft faces on the stand, in degrees: the airport's own for one of its stands, yours to give for any other. |
| gd-place | Place the aircraft here… | Moves the aircraft, stopped on the ground, to the stand (FlightGear's own reposition), on Send. Only before the plan begins. FlightGear loads the scenery at the new place first: half a minute. |
| gd-exit | Leave the runway by | The exit the taxi route in follows: by default the first past where the rollout ends. |
| gd-taxi | Taxi routes from the stand | Lays a taxi route out from the stand to the runway's start (the takeoff then begins at the line-up point) and one in from the runway's exit to the stand, over the airport's taxiways. Replaces the plan's taxi items. |
| gd-untaxi | Remove them | Takes the taxi routes out of the plan again; the takeoff begins where the runway does. |
| gd-holds-on | hold points | When ticked, the taxi routes the editor lays have holds: a stop short of every runway the route enters or crosses and one at the line-up point for the takeoff. Each is cleared by you, one by one, from the Clearances panel. |
| gd-addhold | Add a hold… | Then click a taxi route in the plan: the aircraft will stop there and wait for your clearance. The × beside a hold in the list takes it out. |
| ed-send | Send plan… | Prepares the edited plan for sending; it then goes on Send, as any command. |
| ed-save | Save as file | Keeps the edited plan as a file. |
| ed-close | Close | Leaves the editor; what was not sent is dropped. |

## Flight display

| id | Shown as | What it does |
|---|---|---|
| pfd | the flight display | Attitude, speed, height, vertical speed and heading, with the laws' targets and limits (section on the flight display). |

## Demo

| id | Shown as | What it does |
|---|---|---|
| d-engine | Fail the engine | In the demo only: stops the stand-in aircraft's engine. |
| d-link | Cut the link | In the demo only: silences the station for the aircraft. |

## The aircraft's menu in FlightGear

| Label | What it does |
|---|---|
| Autostart | Starts the engine: the rotors run up in about half a minute. |
| Shutdown | Stops the engine. A plan's start is refused with the engine off. |
| Belly camera: lock and slew... | Opens the camera's dialog. |
| Belly camera: lock on the cross | Locks the camera on the point of the ground under its cross. |
| Belly camera: lock on the nearest object | Locks it on the nearest aircraft, ship or vehicle. |
| Belly camera: level horizon on/off | Keeps the horizon level in the camera's picture, or lets it lean with the aircraft. |
| Belly camera: unlock | Frees the camera. |
| Ground to the horizon at height on/off | Lets the terrain range grow with the height above the ground (on at the start), or leaves FlightGear's own setting. |

## The camera's dialog

| Label | What it does |
|---|---|
| Lock on the cross | As the menu's. |
| Lock on the nearest object | As the menu's. |
| Unlock | As the menu's. |
| Latitude | Degrees, south negative: with Longitude, a point to lock on. |
| Longitude | Degrees, west negative. |
| Lock on these | Locks the camera on the point typed in. |
| Keep the horizon level | As the menu's. |
| Up | Turns the camera up, or moves a locked point. |
| Left | The same, left. |
| Right | The same, right. |
| Down | The same, down. |
