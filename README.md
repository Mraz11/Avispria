<p align="center"><img src="branding/logo.png" alt="Avispria logo" width="140" /></p>

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
- Tunes the route so the photos really get the requested height above the terrain (terrain
  following lifts the drone, which used to leave resolution 30-55% coarser than reported),
  and sets photo and line spacing from the lowest photos. Never below the clearance limit.
- Predicts what each plan will achieve over the real surface before anyone flies it:
  resolution, front and side overlap, and coverage of the survey area, with warnings.
- `--surface-height M` tells the planner how high trees or buildings stand above the ground
  model, so the canopy (not the ground) gets the requested height.
- Chooses a speed from motion blur, rolling-shutter skew, photo interval and wind.
- Splits large surveys into battery- and waypoint-limited missions.
- Writes DJI Fly KMZ files built on **your own** DJI Fly dummy mission, then lints
  every file independently and writes an RC spot-check sheet and a provenance report.
- Refuses to write anything if a safety check fails.
- Checks a folder of photos (JPEG or DNG) from metadata alone: ground resolution,
  overlap with neighbours, how much of the area is seen by 3+ and 5+ photos,
  motion blur risk, gimbal angle, altitude consistency and timing gaps.
- Can take the terrain into account: `qa --dem model.tif` computes each photo's height above
  the surface beneath it (use `--takeoff LAT,LON` with any external elevation model, or
  none with the surface model the engine made from the same photos), so resolution and
  overlap are right over hills, not only over flat ground.
- Derives a camera profile for any DJI drone from one original photo.
- `avispria doctor` checks this computer (memory, virtual memory, disk, CPU, whether
  WebODM is running) and says whether a photo folder can be processed here. If not,
  it lists what would work: lower resolution, splitting, more virtual memory or a
  bigger computer, with the memory each option needs.
- `avispria engine` finds WebODM's local engine (NodeODX) and checks it; the access
  token is read from the running engine and never printed or stored.
- `avispria process` checks a photo folder, confirms this computer can handle it,
  resizes JPEGs to 12 MP (keeping GPS and DJI metadata), uploads, follows progress,
  downloads the orthophoto, surface model and point cloud, summarises the result quality
  in plain language (photos placed, reprojection error, GPS agreement, point density,
  measured vs estimated resolution), and writes a provenance
  record with checksums of every input and output. Presets: fast, standard, detailed.

## Field page for your phone

A small companion that runs in the phone's browser and keeps working with no signal:
pre-flight, in-air and after-landing **checklists** (plus a first-test-flight list), **calculators**
that follow the planner (resolution, spacing, speed and timed-shot interval, how long a survey takes,
what trees do to a plan made for flat ground), and a **flight log** with "use my location" for the
takeoff coordinates that Avispria asks for. It stores everything on the phone only, loads nothing from
the internet and makes no network requests.

Once published (below) it lives at `https://mraz11.github.io/Avispria/`. Open it on the phone, then
Android (Chrome): menu, *Install app*; iPhone (Safari): Share, *Add to Home Screen*.

To publish it: in the repository on GitHub open **Settings > Pages** and set **Source** to
**GitHub Actions**. After that every push to `main` that touches `field-page/` updates the page
(or run the *Field page* workflow by hand from the Actions tab).

For developers: the camera numbers in `field-page/js/generated.js`, the offline file list and build id
in `field-page/sw.js`, and `tests/field_page/golden.json` are written by `python scripts/field_page.py`
(run it after changing the page or `drones.toml`; the tests fail if they are out of date). The page's
JavaScript calculators are tested against values produced by the real Python planner
(`node --test tests/field_page/*.test.mjs`, run automatically by pytest when Node is installed).

## The window interface (no terminal needed)

Double-click `Start-Avispria.bat` (Windows) or run `uv run avispria ui`. Avispria opens in your
web browser, with four screens:

- **Start**: what your computer can do, whether WebODM is running, and where to go.
- **Check my photos**: a verdict, the key numbers, a map of where each photo was taken, and every
  warning explained in plain words ("what it means" and "what to do").
- **Plan a flight**: describe the survey area (by numbers or a map file), your drone and what you
  want; get DJI Fly missions, the route on a map, and a prediction of the resolution and overlap
  you will really get.
- **Make maps**: pick the photos and a quality level, see your computer's capacity, follow the
  progress, cancel if needed, and get the orthophoto, surface model and point cloud.

Everything runs on your own computer and listens on `127.0.0.1` only: nothing is sent anywhere and
nothing is reachable from the network.

## Look and feel

Both the window interface and the phone page share one colour system, light and dark, defined in
`src/avispria/app/ui/theme.py`: Warm Beige and White (Deep Slate and Charcoal Blue in dark mode),
Leaf Green / Emerald for the main actions, Terra Cotta for the second ones, Golden Yellow for
highlights and cautions, and Bright Cyan and Neon Green for map overlays in dark mode. Where a colour
cannot carry small text (white on Leaf Green is 3.3:1), a darker or lighter shade of the same hue is
used, and a test measures the contrast of every pairing. Switch modes with the button in the header;
the choice is remembered. The phone page's stylesheet is generated from the same module.

The logo files are made from `branding/logo-source.jpg` by `python scripts/make_branding.py`
(transparent cut-out, a dark-mode variant, icons). See `branding/README.md` about its licence.

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
