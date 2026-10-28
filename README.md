# Avispria

**Canopy structure and change, seen from above.**

Avispria is an offline-first toolkit for planning drone survey missions,
checking capture quality and orchestrating photogrammetry processing for
forestry and environmental research. It works with consumer **RGB-only**
drones: no multispectral sensor required, and no claims beyond what visible
light can support.

*Name:* from *avis* (Latin, "bird") and the osprey, a raptor that surveys
from height.

**Status:** pre-alpha. Mission planning works and is tested against a real DJI
Fly mission from a DJI Lito X1. It has **not yet been flight-tested**: start with
[the first test flight guide](docs/field/first-test-flight.md).
Read [DISCLAIMER.md](DISCLAIMER.md) before using any output near an aircraft.

## What it does today

- Plans lawnmower surveys (optional cross-hatch) from a GeoJSON polygon, for a
  target ground resolution or height.
- Follows terrain from a GeoTIFF DEM with a dilated safety surface, slope limits,
  a curve-dip margin, and a proof that no straight segment dips below clearance.
- Chooses a speed from motion blur, rolling-shutter skew, photo interval and wind.
- Splits large surveys into battery- and waypoint-limited missions.
- Writes DJI Fly KMZ files built on **your own** DJI Fly dummy mission, then lints
  every file independently and writes an RC spot-check sheet and a provenance report.
- Refuses to write anything if a safety check fails.
- Checks a folder of photos (JPEG or DNG) from metadata alone: ground resolution,
  overlap with neighbours, how much of the area is seen by 3+ and 5+ photos,
  motion blur risk, gimbal angle, altitude consistency and timing gaps.
- Derives a camera profile for any DJI drone from one original photo.
- `avispria doctor` checks this computer (memory, virtual memory, disk, CPU, whether
  WebODM is running) and says whether a photo folder can be processed here. If not,
  it lists what would work: lower resolution, splitting, more virtual memory or a
  bigger computer, with the memory each option needs.
- `avispria engine` finds WebODM's local engine (NodeODX) and checks it; the access
  token is read from the running engine and never printed or stored.
- `avispria process` checks a photo folder, confirms this computer can handle it,
  resizes JPEGs to 12 MP (keeping GPS and DJI metadata), uploads, follows progress,
  downloads the orthophoto, surface model and point cloud, and writes a provenance
  record with checksums of every input and output. Presets: fast, standard, detailed.

## Install (Windows, PowerShell)

    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    git clone https://github.com/<you>/avispria.git
    cd avispria
    uv sync --locked

## Use

    uv run avispria drones                      # aircraft profiles
    uv run avispria inspect my_dummy.kmz        # what a DJI Fly file contains
    uv run avispria plan area.geojson --template my_dummy.kmz `
        --takeoff 23.8290,90.4170 --agl 60 --dem dem.tif --out out\survey
    uv run avispria lint out\survey\avispria_01.kmz
    uv run avispria prepare-copy out\survey\avispria_01.kmz --slot <GUID> --out out\copy

Run `uv run avispria plan --help` for every option.

## Develop

    uv run pre-commit install
    uv run python scripts/check.py

## License
AGPL-3.0-or-later (provisional). See [LICENSE](LICENSE) and
[docs/LICENSING.md](docs/LICENSING.md).
