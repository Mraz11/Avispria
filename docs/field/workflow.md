# The workflow: from an idea to a map, in order

A flight project is **one set-up (once)** and **five steps**. The window shows them in this order on its
Start page, with "Step n of 5" on every screen, five chips that show what is done, and a button to the next
step at the bottom. The Start page also says the one thing to do next.

```
 ONCE            1 Plan         2 Send            3 Fly            4 Check         5 Make maps
 sample mission  on the PC      PC + phone        phone, outside   PC              PC (WebODM)
 from the phone  (what, where,  (placeholder      (compare, fly)   (copy photos,   (map or 3D
                 drone, set-    missions, then                    check overlap)  model)
                 tings, save)   send)
```

## Once: the sample mission

Avispria copies the exact file format of your DJI Fly from one mission that DJI Fly made. In DJI Fly make a
Waypoint Flight with two points and save it (do not fly it), plug the phone in (USB debugging on), and press
**Get it from my phone** (on the Start page or in step 1). It is remembered between runs, in
`~/Avispria/settings.json` (paths only, never coordinates).

## 1. Plan a flight (on the computer)

1. **What do you want to capture?** A flat map, a 3D model of an area, or a 3D model of one object.
2. **Where:** the area (numbers, a map file, or drawn on a map) or the object (a pin).
3. **Your drone** and its sample mission.
4. **Settings** for that kind (resolution, overlaps, tilt, the rings).
5. **Where to save**, then **Plan the flight**.

The results say how many missions the plan has, and what **DJI Fly should show** for each (waypoints, route
length, time).

## 2. Send to DJI Fly (computer and phone)

DJI Fly cannot import missions, so a plan is put into a *placeholder mission* that DJI Fly made. A plan of N
missions needs N placeholders. The screen's checklist says how many DJI Fly has and how many more to make
(Waypoint Flight, any two points, Save). Then press Send. Originals are copied to the computer first.

## 3. Fly (outside)

Open each mission in DJI Fly and compare its map with the plan's **DJI Fly should show** column. If they
differ, do not fly it (see the Fly screen: Global Speed, and `avispria phone pull` then `avispria inspect`).

## 4. Check my photos / 5. Make maps (on the computer)

Copy the photos to one folder, check that they overlap enough, then turn them into a map or a model.

## Why a step can seem to go backwards

The only trip back is making the placeholder missions: how many are needed is only known once the plan
exists. The Send screen says it before anything is sent.
