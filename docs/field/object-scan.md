# Scanning a tree or other object (rings of photos)

`avispria scan` plans rings of photos around ONE object (a tree, a building, a tower) so that it can be
reconstructed in 3D. It is the counterpart of `plan`, which maps an area from above.

    uv run avispria scan LAT,LON --template my_sample.kmz --out out\tree1 `
      --object-height 25 --object-radius 6 --standoff 14

## What to enter

- **centre**: the object's axis (the trunk, for a tree).
- **object height**: the top of the object above the ground at its foot.
- **object radius**: its WIDEST horizontal radius (the crown, not the trunk).
- **standoff**: the distance from the object's surface to the camera. The camera flies on a ring at
  radius + standoff from the axis. GPS is only good to a few metres and wind pushes the aircraft, so
  Avispria refuses less than 5 m and warns below 10 m; 12 to 20 m is a comfortable start for a tree.
- **base height**: the lowest height to photograph (0 = the foot). **Ground offset**: how much higher
  (+) or lower (-) the ground at the object is than your takeoff point (heights are relative to takeoff).

## What it does

The object is treated as an upright cylinder. The plan, in the order the logic runs:

1. Each photo sees a patch of the surface as tall as the picture's short side at that distance. The
   heights the rings must be **centred on** are spaced evenly so neighbouring patches overlap by the
   side overlap (default 70%), the lowest reaching the base and the highest the top.
2. The camera tilts **up** a little on the lowest ring and **down** on the highest (defaults +10 and
   -20 degrees): views from different angles reconstruct better than level ones. Given the tilt, the
   ring's height follows: the camera has to be where its line of sight meets the surface at the
   centre height. (Aiming every ring at one point would squeeze the visible patches toward the middle
   and need absurdly high rings.)
3. Around a ring, neighbouring photos are at most 10 degrees apart (3D reconstruction loses a point
   once the view turns more than about 15 degrees) and overlap by the front overlap (80%) on the
   surface, whichever needs more photos.
4. A **top cap**: a small grid of straight-down photos 8 m above the top.
5. The rings are a spiral: every ring is flown the same way round, starting at the bearing that faces
   the takeoff point. Two waypoints in the same place are refused by DJI Fly, so a ring never starts
   straight above where the last one ended.
6. Every waypoint **faces the object** (DJI Fly's "Face POI"), **stops, hovers 1 s and takes one photo**;
   the camera tilt is written explicitly (the encoding verified from real DJI Fly files).
7. Rings are kept whole when the plan is split into missions (at most 99 waypoints and one battery each).

Example (a 25 m tree with a 6 m crown radius, camera 14 m from it, Lito X1 at 12 MP): 4 rings of 36
photos at 20 m from the axis plus a 32-photo cap: 176 photos at 0.29 to 0.53 cm/px, in 3 missions of
about 5 minutes each (the first two limited by the waypoint count, not the battery).

## Before you fly one

Heights assume flat ground at the object (use the ground offset otherwise). Avispria cannot see
the object, so **check the plan in DJI Fly**: open the first mission, look at the ring on the map and the
heights of its waypoints, and compare them with the spot-check sheet. Try the first scan on an open,
easy object (a pole, a lone tree away from others) with a larger standoff, a low wind and the aircraft in
sight, and keep your hand ready on the sticks. The sideways obstacle sensing of the aircraft in waypoint
missions is unknown to us.

## Not verified yet (no flight has been made)

- That DJI Fly accepts and flies a 72-waypoint mission with a point of interest, explicit camera tilts,
  a hover and a photo at each waypoint (each part is in a real DJI Fly file; the mix is not).
- That one second of hover is enough for a sharp photo at every stop, and that the photo is taken while
  stopped (try 2 s: `--hover 2`).
- That 99 waypoints per mission is accepted (conservative figure; one source claims 200).
- The top cap's coverage. It is flagged by a warning on every plan.

## Processing

An object scan needs a 3D model (a mesh or a point cloud), not the map and surface model that `process`
makes by default. A 3D preset for **Make maps** is the next step.
