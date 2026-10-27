# First test flight (probe) — DJI Lito X1 + RC-N3 + Android phone

Purpose: confirm on real hardware that DJI Fly loads an Avispria mission and flies
it as planned. Nothing here is a survey yet. You are the pilot in command.

## What this flight measures

1. DJI Fly accepts the file and shows the expected waypoints and heights.
2. Legs are straight (we write `useStraightLine = 1`; DJI Fly's own default is curved).
3. How far the aircraft dips below waypoint heights between waypoints.
4. The real minimum photo interval in timed-shot mode at 12 MP.
5. The gimbal stays at -90 degrees (straight down) for the whole route.

## Site and conditions

- Open, flat ground with no trees, wires, buildings or people within 100 m.
- Wind below 5 m/s, good GPS (at least 12 satellites shown in DJI Fly).
- A full battery. Follow your local drone rules and keep visual line of sight.

## 1. Draw a small area

Open https://geojson.io, draw a rectangle of roughly 60 m x 60 m over the test
site, and save it as `probe.geojson` (Save > GeoJSON). Note a takeoff point next
to it (long-press in Google Maps shows `LAT, LON`).

## 2. Plan

Use your ORIGINAL DJI Fly dummy KMZ (not the shifted test fixture):

```powershell
uv run avispria plan probe.geojson `
  --template C:\path\to\37924189-3F0F-4792-AA10-D50082167E9C.kmz `
  --takeoff 23.8290,90.4170 `
  --agl 30 --flat --mode 12mp `
  --max-distance 200 --name probe `
  --out out\probe
```

`--flat` is correct only because the site is flat and open. The output folder gets
`probe_01.kmz`, `probe_01_spotcheck.csv` and `plan_report.json`. Write down the
"Set DJI Fly timed shot to ... s" line it prints.

## 3. Install on the phone (FV File Explorer)

1. In DJI Fly, open Waypoint Flight, add two points, save, and exit. This creates a
   new mission folder (a long ID such as `37924189-...`). Note which one is newest.
2. In FV File Explorer go to `Android/data/dji.go.v5/files/waypoint/<ID>/`.
3. Rename `<ID>.kmz` to `<ID>.kmz.bak` (your backup).
4. Copy `probe_01.kmz` into that folder and rename it to exactly `<ID>.kmz`
   (one `.kmz`, same ID as the folder).
5. Force-close DJI Fly and reopen it.

## 4. Check in DJI Fly before takeoff

Open the mission and compare with `probe_01_spotcheck.csv`:

- the number of waypoints;
- the height of the first, last and one middle waypoint;
- the speed.

If anything differs, do not fly. Send me the CSV and a screenshot.

## 5. Fly

1. Camera: Photo, 12 MP, **Timed Shot** at the interval printed in step 2.
2. Start the mission. When the aircraft reaches the first waypoint, start timed shot.
3. Keep your thumbs on the sticks. If the aircraft drifts toward anything, pause
   the mission and take manual control.
4. Stop timed shot at the last waypoint; let it return home.

## 6. Send back

Copy the ORIGINAL photos from the aircraft's storage or microSD card to the PC
(not from the DJI Fly album, which removes the metadata). Put them in a ZIP so the
chat upload cannot re-encode them, and upload:

- the ZIP of photos (all of them, or at least 15 consecutive ones);
- `plan_report.json` and `probe_01_spotcheck.csv`;
- your DJI Fly version (Profile > Settings > About);
- anything unexpected you saw.
