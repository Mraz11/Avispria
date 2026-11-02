# How DJI Fly (Lito X1) stores a waypoint mission

Everything below was read from **real missions made in DJI Fly** on the founder's phone
(`tests/fixtures/dji_fly_poi/`, coordinates moved to Greenwich, nothing else changed) and from the
screens of the app. DJI's public WPML documentation describes enterprise aircraft; DJI Fly differs from
it in places, so the files are the authority.

## The file

- `wpmz/template.kml` is only a header (author `fly`, create/update time, mission settings): **no
  waypoints**. Everything is in `wpmz/waylines.wpml` (namespace `http://www.uav.com/wpmz/1.0.2`).
- The mission list of DJI Fly is **not** the folder: a mission folder DJI Fly did not create is not listed,
  even with `image/ShotSnap.json` and `map_preview/<ID>/` added (tested). Plans go into a placeholder slot
  (see `phone-bridge.md`). Folder layout per mission: `<ID>/<ID>.kmz`, `<ID>/image/ShotSnap.json`,
  `map_preview/<ID>/<ID>.jpg`.
- `distance` and `duration` in the file are 0: DJI Fly computes them (a 300 m route at 6 m/s showed 00:50).

## Settings a waypoint has in the app

Camera Action (None, Take Photo, Start REC, Stop REC), Altitude, Speed (global or its own), Heading
(Follow Course or POI), Gimbal Tilt (an angle, or POI), Zoom, Hover time, and "Apply to All".
The Lito X1's gimbal runs from -90 (straight down) to +40 (tilted up); roll is fixed at 0; speed 0.1-12 m/s.

## How each setting is stored

| In the app | In `waylines.wpml` |
|---|---|
| Altitude | `executeHeight`, relative to takeoff (`executeHeightMode relativeToStartPoint`) |
| Heading: Follow Course | `waypointHeadingMode followWayline` |
| Heading: POI n | `waypointHeadingMode towardPOI` and `waypointPoiPoint lat,lon,height` (6 decimals; the height is the POI's own, 50 in the samples), `waypointHeadingAngleEnable 1`, `waypointHeadingPathMode followBadArc`, `waypointHeadingPoiIndex 0` |
| Take Photo | an `actionGroup` at that waypoint: `actionGroupStartIndex = actionGroupEndIndex = its index`, trigger `reachPoint`, action `takePhoto` with `payloadPositionIndex 0` and `useGlobalPayloadLensIndex 0` |
| Gimbal Tilt: an angle | **on the previous waypoint**: an `actionGroup` over the leg `[k-1, k]` with action `gimbalEvenlyRotate` (`gimbalPitchRotateAngle`, `gimbalRollRotateAngle 0`): the camera turns evenly and arrives at waypoint k with that tilt. The first waypoint uses `gimbalRotate`. |
| Gimbal Tilt: POI | **nothing**: no gimbal action at all (see "Not verified") |
| Turn | `waypointTurnMode` `toPointAndStopWithContinuityCurvature` (ends) or `toPointAndPassWithContinuityCurvature`, `useStraightLine 0` |

The waypoint's own `waypointGimbalPitchAngle` stays 0 in DJI Fly's files and means nothing.
`actionId` is unique across the whole mission, numbered in the order things were created (not in file order).
`actionGroupId`: 1 for the photo and 2 for the evenly-rotating tilt in the samples.

## Bug this found (fixed)

Avispria wrote waypoint `i`'s tilt on its own leg `[i, i+1]`, one waypoint late. All earlier missions used a
single angle (-90), so nothing showed. Fixed together with the reader (`arrival_tilts`) and tested against
the real files.

## Not verified (needs the drone, or DJI Fly's flight simulator)

- That DJI Fly aims the camera at the point of interest by itself, including its height, when Gimbal Tilt
  is "POI" (it stores no angle for it). DJI's documentation says the vertical direction is not supported on
  enterprise aircraft. Avispria can instead write an explicit tilt on a waypoint that faces a point; DJI Fly's
  own `angles` sample has exactly that mix (waypoint 1 faces a POI and has a stored tilt).
- That a photo at each waypoint produces the expected overlap (the camera must have time to shoot: use a
  hover time).
- Whether the aircraft senses obstacles sideways in waypoint missions.
