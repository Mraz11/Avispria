# HANDOFF - 2026-10-30 - session #4 (doctor, engine, processing, terrain-aware QA, planner, window interface)
## Done this session
- `doctor`: RAM/swap/CPU/disk + verdict with real alternatives (ODM RAM table);
  finds the native WebODM app by its processes/ports; `--details`.
- `engine`: finds WebODM's NodeODX, reads its token from the running command line
  (memory only), connects via PyODX (BSD-3), lists 80 supported options.
- `process`: photos -> QA -> engine -> feasibility -> presets (only supported options;
  rolling-shutter for electronic shutters) -> 12 MP resize keeping EXIF+XMP -> upload ->
  progress -> all.zip + extracted results -> provenance JSON with SHA-256s.
- CLI split into modules (cli.py had hit the 400-line limit).
- Planner over terrain (core/predict.py, plan_model.py, plan_path.py): predicts the plan's real
  resolution/overlap/coverage from the actual height above the surface at each planned photo
  (same analyse_capture as QA, over the AOI). Terrain following used to lift the drone far above
  the requested height (margin 10 m + dilation + slope limits): 40 m hill target 2.0 cm/px gave
  2.73. Now a calibration loop (<=4 passes, keeps the most consistent) moves the route's
  reference height until the MEDIAN height above surface = target, never below
  min_surface_clearance - margin, and computes spacing for the 10th-percentile height.
  Warnings PL001 (typical GSD off by >15%), PL002 (coarsest tenth >30% worse), PL003.
  `--surface-height` = canopy allowance; `--no-calibrate` keeps the old behaviour.
  QA now reports front/side overlap separately (QA014: side < 50%).
- Look and feel: ONE palette in src/avispria/app/ui/theme.py (LIGHT/DARK dataclasses, tokens_css(),
  contrast_ratio(); tests/ui/test_theme.py measures 61 pairings). Brand colours are used as FILLS; where
  small text is needed a derived shade is used (link green #1B766B, dark text #74C69D, etc.). NiceGUI:
  assets/avispria.css (variables only) + ThemeState (theme_state.py) + header logo/toggle in layout.py;
  charts take a Palette and redraw on toggle (widgets.echart(builder)); the browser announces its theme
  via the `avispria_theme` event, the server never awaits JS replies (they hang under the simulated user).
  Phone page: css/theme.css and js/theme.js are GENERATED from theme.py by scripts/field_page.py.
  Logo: designed by the founder, coloured with an AI tool; branding/ + scripts/make_branding.py
  (cut-out, the navy X REDRAWN AS A DRONE - rings variant A chosen by the founder because the original X
  read as a windmill; test counts 4 rotor openings + camera hole; dark variant, icons). LOGO LICENCE
  UNDECIDED (branding/README.md). NOT verified: how either interface looks in a real browser (previews of the phone
  page were rendered with WeasyPrint, approximate). Test pitfalls: never `from main import ...` in a
  NiceGUI test (it runs ui.run); patch objects, not dotted paths, after page tests; type() appends.
- Phone field page (field-page/, PWA, no build step, no dependencies): checklists, calculators
  (js/calc.js = port of camera.py/speed.py/sorties.py, tested against tests/field_page/golden.json
  produced by the REAL planner), flight log with geolocation + CSV, offline via sw.js. Published by
  .github/workflows/pages.yml (Pages Source must be "GitHub Actions"; actions pinned: configure-pages
  v6.0.0, upload-pages-artifact v5.0.0, deploy-pages v5.0.1). `python scripts/field_page.py` regenerates
  js/generated.js (from drones.toml), golden.json and the sw.js asset list + BUILD id; pytest fails if stale.
  Strict CSP (no inline script/style, no outside hosts) is tested. Node tests: tests/field_page/*.test.mjs
  (pytest runs them if node exists; GitHub runners have it). tests/field_page/dom_check.mjs is a manual
  developer tool (needs a scratch jsdom install; see its header). NOT verified: a real phone/browser.
- Window interface (NiceGUI 3, local only: 127.0.0.1): `avispria ui` / Start-Avispria.bat.
  app/ui/: explain.py (plain-language text for all 49 issue codes; a test fails if a code
  lacks one), views.py + views_results.py (pure view models), charts.py (ECharts options),
  plan_job.py / process_job.py (forms as plain data + validation + execution, tested without a
  browser), jobs.py (background threads, QueueReporter, friendly errors), widgets.py (folder
  browser, banners, tiles), pages/ (home, check, plan, process). Screens: Start, Check my
  photos, Plan a flight, Make maps (progress, Cancel, results).
  Cancel: engine.wait(should_cancel) + ProcessRequest.cancel (tested with a fake engine whose
  task never ends). Photo size for processing is a real choice (12/8/6/4/3 MP, full).
  Survey rectangle from numbers: core.geometry.rectangle_polygon.
  TESTING: NiceGUI's simulated `user` runs on the AnyIO plugin (no pytest-asyncio needed);
  main file tests/ui/ui_main.py via the nicegui_main_file marker. NiceGUI quirks: simulated
  type() APPENDS (use clear() first: uihelpers.set_text); it cannot click ui.toggle options
  (use ui.radio); background handlers need `eventually(...)`. tests/ui/test_server.py starts
  the REAL server in a child process (env without PYTEST_*/NICEGUI_*, or NiceGUI enters its
  own test mode), requests every screen and checks it listens on 127.0.0.1 only.
  NOT verified: how it looks in a real browser, the Windows-only parts (drive buttons in the
  folder browser, "Open the folder"), no persistent settings, prepare-copy not in the UI.
- Make maps engine discovery: system_probe.find_engine() = the Windows app's nodeodx PROCESS, else NodeODX at
  its standard address http://localhost:3000 without a token (Docker; `docker run -p 3000:3000
  opendronemap/nodeodm`); the screen has optional Engine address/token (Advanced). ONLY the Windows app
  route has been tested with real WebODM; macOS/Linux/Docker is untested (and Apple Silicon needs an ARM
  image). Launchers: Start-Avispria.bat (Windows), start-avispria.sh + Start-Avispria.command (Linux/macOS;
  keep the executable bit and LF endings; tested). README rewritten with install steps per OS;
  tests/test_docs.py keeps it in step with the CLI.
- Forest dataset (docs/datasets.md): ODM's helenenschacht (Autel EVO II Pro RTK, 176 photos, 2.4 GB, RAW
  PHOTOS ONLY, no DSM/DTM). The sandbox (7 GB disk, 3 GB RAM, 1 thread) cannot run photogrammetry, so only
  the 46 MB of photo HEADERS (range requests) + 6 full photos were fetched. It exposed that QA needed a
  relative altitude (DJI-only): now a photo has a height if it records one above takeoff OR one was
  worked out (elevation model, or `qa --ground-elev M` / the Check screen field); QA015 (no height above
  ground) and QA016 (camera angle not recorded, assumed nadir) added. Finding for later: `process` does not
  upload ODM's gcp_list.txt (GCP support missing); camera-from-photo labels 19.96 MP as "19mp".
- ROADMAP decided with the founder (2026-10-30), NOT built yet: (1) a drawable MAP in Plan a flight
  (ui.leaflet has draw_control; background tiles need the internet, so optional + privacy note; ask which
  basemaps: street / terrain / satellite, check provider terms); (2) a USB/ADB bridge from the PC app to
  DJI Fly on the phone. RESEARCH: DJI Fly has NO import/export of waypoint files; the only way is to overwrite
  a placeholder mission's <GUID>/<GUID>.kmz in Android/data/dji.go.v5/files/waypoint/ (iOS: DJI
  Fly/wayline_mission, with a wpmz.sqlite3 index); folders DJI Fly did not create are reported NOT to be
  listed (the index location on Android is unknown). Since Android 13 no phone app (incl. file managers, SAF)
  can touch another app's Android/data; PC over USB (MTP/ADB) can. So the phone cannot do the transfer
  itself; the PC bridge (pull the missions DJI Fly made = sample mission; push a plan into a chosen
  placeholder with a backup) is the route, once the founder's phone passes the test `adb shell ls
  /sdcard/Android/data/dji.go.v5/files/waypoint` (HyperOS may restrict it; unverified). Experiment for the
  founder: `avispria prepare-copy mission.kmz --out DIR` (no --slot = a NEW id) and see whether DJI Fly lists it.
- Engine detection: doctor/Start screen now tell apart not running / WebODM programs running but not
  answering (starting, or started as administrator so Windows hides their ports) / running; Check again
  button on Start. The founder's Windows PC reported 'No WebODM-related programs are listening'.
- Terrain-aware capture QA: `core/ground.py` (height above the surface per photo; modes
  `takeoff` = DEM differences only, for any external DEM; `absolute` = photo altitude minus
  DEM, only when the DEM shares the photos' height reference, e.g. the engine's own DSM, with a
  plausibility check -> QA011). `qa --dem [--takeoff]`; `process` re-checks its resolution
  estimate against the engine's DSM. DEM reader can decimate (5 cm DSMs).
## Current state (command proof)
- 184 tests pass (Linux sandbox); founder's Windows run of `engine` connected to
  ODX 3.8.4 (API 2.4.0), 12 cores, 16 GB, 80 options.
- `process` verified on the founder's PC with ODM's public Brighton Beach set (18 photos,
  Phantom 3): fast 2 min, standard 8 min; 18/18 photos placed, reprojection 0.83 px,
  GPS agreement 0.66 m, 1.41 M points. Output now at the photos' GSD (1.9 cm/px), not 5.
- Brighton Beach: ODX measured GSD 1.59 cm/px; flat-ground estimate 1.89; terrain-aware 1.68
  (ground ~4-8 m above takeoff, camera ~35.6 m above surface). The remaining ~6% is the
  camera-size convention for the 16:9-cropped FC300S (ODX: f35/36 of image width; ours:
  diagonal-based). Lito X1 (full 4:3) uses our 9.692 mm width; ODX's convention would give
  10.08 mm (4% apart): UNVERIFIED until a Lito X1 set is processed. `process` records
  gsd_ratio (measured/estimate) in provenance for this.
- GitHub main was at 9c30a9f (patch 0010) when last checked: 0011+ were local only.
## Open problems / suspicions
- Founder grounded ~1 month; test `process` with a public sample dataset.
- Non-DJI photos: EXIF GPS fallback not implemented (QA warns, processing works).
- PyODX uses deprecated datetime.utcfromtimestamp (narrowly ignored; report upstream).
## Next single task (ready-to-paste)
Founder to choose: (a) polish the window interface after real use (look, wording, prepare-copy
for the phone, remembered folders); (b) canopy height/change, which needs a terrain model (leaf-off flight,
external LiDAR DTM or open ground) and a public forest dataset to develop against (ODM lists
helenenschacht, 176 photos, 2.5 GB). Whenever Lito X1 data is processed: calibrate the camera
size (gsd_ratio in provenance) and measure the route-curve dip with the probe flight.
## Decisions made
- Process through NodeODX directly (not WebODM's API): no login, no WebODM settings
  touched; results importable into WebODM via its Import button.
- Default processing resolution 12.2 MP (JPEG only; DNG sent at full size).
- Terrain in QA uses the nadir surface point per photo (first order on steep slopes).
- Calibration targets the typical (median) height; spacing the 10th percentile. The 10 m curve
  margin is still unverified: when the probe flight measures the real dip, lowering it makes
  plans fly lower/tighter automatically.
## Do-not-touch notes
- tests/fixtures/* stay byte-exact; never print or persist engine tokens.
