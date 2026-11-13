# User test of the ground control station

**Not run yet.** The script, what is counted and the pass mark are written here before anyone is tested, so the
result cannot move the mark. It needs the operator's manual (`GlobalHawk-operators-manual.pdf` in the
repository's root) and someone who has not seen the station.

## Who and with what

- One person at a time, new to this station; some flying or flight-simulator background helps but is not asked for.
- They get the operator's manual and 20 minutes with it and with the demo (`index.html?demo=1&speed=10`). No help
  from the tester after that, except to restart the software.
- The test itself runs against the flight model (`python3 fdm/gcs_server.py --speed 5`), not the demo.
- The tester watches and notes; the screen is recorded if the person agrees.

## The mission (about 25 minutes at 5x)

| # | Task, as told to the person | What it tests |
|---|---|---|
| 1 | "Send the demo plan and start the flight." | plan, preview, start |
| 2 | "Once airborne, tell me what the aircraft is doing, what it will do next, and what it will do if this station stops working." | mode strip, lost-link route |
| 3 | "Add a point to the route east of point 2 at 30,000 ft and send the change. Before sending, tell me how much fuel there will be at landing." | editor, forecast |
| 4 | "Send the aircraft to a point I show on the map, at 25,000 ft. How long will it take?" | go to, preview |
| 5 | "Return to the plan." | resume |
| 6 | (The tester switches a navigator's error on.) "Something has changed. What, and what should you do?" | alerts, navigators |
| 7 | (The tester cuts the station's link for 40 s, then restores it.) "What happened? Get the flight back to its plan." | lost link, resume |
| 8 | (The tester fails the engine.) "What is the aircraft doing? Is there anything you must do?" | engine-out alert, strip |
| 9 | After landing: "How much fuel was used?" | status |

## What is counted

- **Wrong command:** a command sent that was not the one the task needed, or sent with wrong values, whether or
  not it was corrected afterwards. A command cancelled at the confirm bar is not one: that is the confirm bar
  doing its job (count these separately as *caught*).
- **Hesitation:** more than 30 s of real time between a task being given and the first purposeful action.
- **Wrong reading:** a question in tasks 2, 3, 4, 6, 7, 8 or 9 answered wrongly.
- **Help:** any time the tester has to step in.
- The time for each task, and what the person says aloud, are noted but not judged.

## Pass mark (set 2026-11-12, before any test)

For one person: all nine tasks completed, **no help**, **at most 2 wrong commands**, **at most 3 hesitations**,
**at most 1 wrong reading**, and neither of the two questions that matter most answered wrongly: task 2's "what
if this station stops working" and task 8's "is there anything you must do".

For the station: **at least 4 of 5 people pass.** Any task that two or more people get wrong is a design fault to
be fixed and tested again, whatever the totals say.

## Afterwards

Ask: what was hardest to find; what did you expect to happen that didn't; what would you remove. Write the
answers down in their words.
