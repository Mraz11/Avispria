# What do you want to capture? The three kinds of scan

Choosing the kind decides how the camera points, how the aircraft flies, what you must enter and how the
photos become a result. (The command line: `plan` for the first two, `scan` for the third.)

| Kind | You get | The camera and the flight |
|---|---|---|
| **Flat map of an area** | an orthomosaic and a height model | straight down, parallel lines, a photo at every photo point |
| **3D model of an area** | a 3D model of ground, trees and buildings | tilted about 30 degrees, lines in TWO directions (about twice the photos and flying) |
| **3D model of one object** | a 3D model of one tree or building | rings around it at several heights, always facing it, camera up at the bottom and down at the top |

## On the screen (step 1, Plan a flight)

The first card asks what you want to capture. Your answer shows only the cards that kind needs and sets
their recommended values (you can change them afterwards):

- **Flat map**: the area (numbers, a map file, or drawn on a map), resolution or height, overlaps, how photos
  are taken, the ground.
- **3D model of an area**: the same, plus the camera tilt (30 degrees to start with) and lines in two
  directions.
- **3D model of one object**: the object (a pin on a map, or latitude and longitude, its height and widest
  radius) and the rings (distance from the object, lowest height, overlaps, how far the camera looks up
  and down, how long to stand still at each photo, the speed, the photos over the top).

The numbered cards are 1 What, 2 Where, 3 Your drone, 4 Settings, 5 Where to save. The sample mission
(step 3) comes from DJI Fly once: the screen says how, and links to the Send to DJI Fly step.

## A photo at every photo point

Avispria puts a waypoint wherever a photo is taken (not only where the aircraft turns). You see every photo
position in DJI Fly and the camera needs no setting. DJI Fly takes about 99 waypoints in a mission, so a bigger
area is several missions, each needing a slot on the phone. `--photo-mode interval` (timed shot) gives one
mission with only the line ends as waypoints, and you set the camera's timer yourself.

## 3D model of an area (`avispria plan ... --tilt 30 --crosshatch`)

- The resolution you ask for is the one at the CENTRE of a picture. A tilted picture is finest at its bottom
  edge and coarsest at its top, and the plan lists all three.
- A tilted picture lands AHEAD of the aircraft, so each line starts earlier than in a flat plan (the
  nearest edge's distance plus two photo spacings) to photograph the edge of the area from at least three
  photos.
- Overlap is counted along the picture and across its centre; as an area it is a little less along the line
  (about 78% for 80%), because the far end of a picture is its wide end.
- No coverage prediction is made for tilted photos: after the flight, use Check my photos.
- Verified without a flight: the geometry matches independent ray casting; and every sample point of
  several areas (squares, a long rotated rectangle, three tilts) is seen by at least 3 photos, usually 9 or
  more. Not verified by a flight: that DJI Fly flies the tilted missions as planned.
- The largest tilt is set by the camera: the top of the picture may not look more than 80 degrees from
  straight down (about 51 degrees for the Lito X1's 12 MP picture).

## 3D model of one object

See `object-scan.md`.
