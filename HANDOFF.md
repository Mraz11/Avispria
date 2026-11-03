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
- PHONE BRIDGE (built, docs/field/phone-bridge.md): `avispria phone status|slots|pull|send|pair|connect` and the
  Phone screen. RESEARCH behind it: DJI Fly has NO import/export of waypoint files; a mission folder DJI Fly did not
  create is NOT listed even with image/ShotSnap.json and map_preview/<ID>/ added (founder tested, 2026-10-30), so
  the only route is to OVERWRITE a placeholder ("slot") mission's <ID>/<ID>.kmz in
  Android/data/dji.go.v5/files/waypoint/ (the founder's method). Since Android 13 no phone app can touch that
  folder, so the PC does it over adb (USB or Wireless debugging): no Avispria phone app. Safety design in
  app/phone_workflow.py: lint first, back up the original to ~/Avispria/phone-backups, push to <ID>.kmz.avispria-new,
  verify sha256 on the phone, mv into place, verify again, restore on failure; ids/paths/serials validated because
  adb shell hands arguments to the phone's shell. adb is NOT bundled (user downloads platform-tools; found on PATH,
  ~/Avispria/platform-tools, ANDROID_HOME, or chosen on the screen). A real DJI Fly mission folder holds the .kmz +
  image/ShotSnap.json ({"POI_POINT":{},"WAY_POINT":{}}) + map_preview/<ID>/<ID>.jpg (480x360 Google map picture:
  never redistribute) and a capability/ folder (same as our fixture). VERIFIED on the founder's Redmi over USB:
  adb devices, ls of the waypoint folder, push + rm of a file there. NOT verified on a real phone: the full send,
  Wi-Fi pairing, DJI Fly opening a sent mission. Tested only against tests/fakes/fake_adb.py.
  First real-phone run (founder, 2026-10-30): adb found in the Android SDK folder by itself, Redmi connected over USB,
  2 missions listed; one (F6C1AB6D) read as 0 waypoints (probably a point-of-interest mission): a mission Avispria
  cannot read is never offered as a slot. BUG found by the founder: the 'Sent / Next, on the phone' message
  vanished after a split second because the refresh after a send rebuilt the card holding it; tests passed because
  they read the message before the refresh finished. RULE: the outcome of an action lives OUTSIDE widgets that a
  refresh rebuilds, and a test must wait for the refresh and then check the message is still there.
  CI FINDING (founder's screenshot, 2026-10-30): ubuntu-latest failed tests/field_page (golden survey[2] total_minutes
  6.9086 vs 6.8819) while Windows/macOS passed. Cause: grid.auto_heading decided a SQUARE's strip direction with
  `height > width` (and by which hull edge came first), i.e. by floating-point noise: ~1/3 of square and
  near-square surveys changed by 0.1-1.6 s between machines (a 1e-12 relative nudge was enough to flip them).
  Also ceil(height/spacing) on whole-number ratios. Fixed with tolerances + a fixed rule for squares (heading in
  [0,90)). RULE: any comparison/ceil/round on a derived float needs a tolerance; tests/core/test_planner_determinism.py
  nudges inputs by 1e-12 and demands an identical plan. A 150-case hunt (squares, near-squares, rotations) found 49
  unstable cases before the fix and 0 after.
  REAL DJI FLY SAMPLES (founder, 2026-11-02): a POI mission and a mission with per-waypoint camera angles
  (tests/fixtures/dji_fly_poi/, shifted to Greenwich) settled the encoding of Take Photo at a waypoint, POI
  headings and gimbal tilts: see docs/field/dji-fly-mission-format.md. BUG FIXED: the writer put waypoint i's tilt
  on leg [i, i+1] (one waypoint late); DJI Fly stores waypoint k's tilt on leg [k-1, k]. The reader now derives
  `gimbal_pitch_deg` from the actions (arrival_tilts) and reports heading_mode/poi; Waypoint has `poi`; camera limits
  are the Lito's -90..+40. NEXT (decided with the founder): drawable map with shape roles (map inside / leave out /
  band around / corridor line / keep clear), then 3D patterns (oblique crosshatch first, then orbit/dome and wall
  scans), each needing a 3D processing preset. Map tiles: OSM tile policy forbids offline downloading and heavy
  use, requires attribution; default OSM street, bring-your-own tile URL, no satellite default.
  Third real sample (custom heading, hover 3 s, zoom 2x, own speed, tilt +20, first-waypoint camera set-up):
  heading Custom = smoothTransition + angle; hover = `hover` action; zoom = `zoom` action (group 4, seen only at
  waypoint 1); DJI Fly groups actions by KIND (group 1 = arrival actions incl. several in one group, 2 = evenly
  turning tilt, 4 = zoom). The writer now writes that structure, supports Waypoint.heading_deg and hover_s, and its
  default takePhoto has useGlobalPayloadLensIndex (it was missing). Zoom is read but not written.
  MAP SEARCH + LOCATION (2026-11-02, patch 0033; founder confirmed the map itself works in his browser: map,
  toolbar, OSM credit): adapters/geocode.py (Nominatim-compatible; at most 1 request/s for the whole application
  via a lock and 1.1 s pace, answers cached 1 h, User-Agent 'Avispria/<ver> (+repo)', search only on a button
  press (policy forbids search-as-you-type), OSM credit shown unless another service is configured, error text for
  403/429/offline/bad JSON); the service address is a setting because the public service's policy counts ALL users of
  an application together. 'My location' = navigator.geolocation through ui.run_javascript (secure context needed:
  http://127.0.0.1 or localhost); AreaMap._browser_location is the only JS call so tests replace it (awaiting JS under
  the simulated user hangs). UNVERIFIED: live Nominatim answers (the sandbox cannot reach it), real browser location.
  EDITING + UNDO (same patch; founder asked: 'no option to edit after drawing; the edit icon in the toolbar does not
  work'): Leaflet.draw's own edit tool cannot work because hide_drawn_items=True keeps its feature group empty (and
  NiceGUI strips an `edit: False` option), so it is hidden with CSS (EDIT_CSS, :has() selector). NiceGUI forwards only
  MAP-level events (map-click with latlng, draw:*), NOT marker drag/dragend, so editing is by CLICKING: Edit button in a
  shape's row -> numbered circleMarker discs on its corners -> pick a corner -> click the map to move it (documented
  pattern: m.on('map-click', ...) with e.args['latlng']). Add corner = midpoint of the longest side; remove picked
  corner (area >= 3, line >= 2); circle = centre by click + typed radius; a rectangle becomes a polygon when a corner
  moves; a move that makes the outline cross itself is refused (core/shapes.move_corner validates). Undo (history of 50,
  consecutive changes to one field = one step, restores shapes AND the takeoff pin/box). Pure operations are in
  core/shapes.py (move_corner, insert_corner, delete_corner, with_radius). The Start page promise is now exact: nothing
  is sent unless the map background or place search is used.
  FILE LAYOUT (the gate has a HARD 400-line limit per file; plan_map.py hit 591 and was split): pages/plan_map.py
  (AreaMap: build, shapes list, result; 399 lines: NO headroom, split further before adding to it), plan_map_edit.py
  (EditingMixin: undo + corner editing), plan_map_places.py (PlacesMixin: search, coordinates, location),
  plan_map_text.py (labels, colours, help texts). Tests patch plan_map_places.search_places and read LOCATION_JS there.
  UNVERIFIED in a real browser: the numbered tooltips (bindTooltip on circleMarker), the corner discs, clicks while a
  draw tool is active (draw:drawstart ends editing), live Nominatim answers, real browser location.
  FOUNDER'S FIRST REAL USE (2026-11-02): planned a map on the PC, sent it, it opened in DJI Fly (no flight yet).
  Three complaints: (1) waypoints only at line ends, wanted one at every photo point; (2) no separate 3D vs flat
  scanning with their own settings; (3) steps not in order / no direction. DONE: (1) PhotoMode.WAYPOINT was already
  implemented; the UI/CLI defaulted to interval. Now the default everywhere; AVI001 only for aircraft whose profile lacks
  photo_action_verified (Lito X1 has it); waypoint mode = more missions (200x300 m @2 cm: 3 x 84 waypoints, not 1 x 18):
  results say how many slots are needed. (2) ENGINE: core/camera.oblique_view (verified against independent ray casting in
  tests/raycast.py), planner tilt (spacing from the tilted footprint, overrun = near_ahead + 2 photo spacings, shutter limit
  from the finest along-track GSD, resolution asked = at the picture centre), PlanOptions/CLI --tilt, results tiles;
  core/scan_types.py (flat / area_3d / object_3d with recommended settings); app/ui/scan_job.py (object scan from the
  form). A coverage simulation (every photo footprint cast onto flat ground) shows every point seen by >= 9 photos in a
  30-degree crosshatch plan. TODO: (2) the SCREEN (scan-type chooser on Plan a flight, per-type fields, object card with a
  map pin, object results view) and (3) the guided order (nav Plan > Send > Fly > Check > Make maps, numbered journey on the
  Start page, 'step n of 5' lines, Next-step buttons). plan_form.py is 332 lines (hard limit 400): split before adding.
  OBJECT SCAN (built 2026-11-02, patch 0032; no flight yet): `avispria scan` (core/scan.py, app/scan_workflow.py,
  docs/field/object-scan.md). Object = upright cylinder; rings at radius+standoff; ring HEIGHTS follow from the heights on
  the surface each ring must be centred on (even, overlapping, base..top) and the tilt schedule (+10 up at the bottom,
  -20 down at the top): camera height = centre - tan(pitch)*standoff (aiming all rings at one point squeezes coverage by
  r/R); photos per ring = max(360/max_step 10 deg, footprint rule); top cap = nadir lattice 8 m above; spiral route (same
  direction, same start bearing: two consecutive waypoints in the same place are refused by lint WPML011); every waypoint
  faces the POI, stops, hovers, takes a photo, explicit tilt; whole rings per mission (99 waypoints, battery).
  Geometry is in UTM metres (grid north differs from true north by ~2 deg here; haversine is ~0.3% short of true metres).
  STILL TO BUILD: a Scan screen (map pin + fields) and a 3D processing preset (mesh/point cloud, not orthophoto/DSM),
  dome pattern, wall scans (custom heading + vertical columns), oblique crosshatch, route over the map.
  MAP (built 2026-11-02, patch 0031; NOT yet seen in a real browser): Plan a flight has a third way to choose the area,
  'Draw it on a map' (ui.leaflet with the Leaflet.draw toolbar, hide_drawn_items=True). The SERVER owns the shapes
  (pages/plan_map.py AreaMap): every drawn layer is parsed (map_events.parse_layer, tolerant of the payload formats)
  into core/shapes.py DrawnShape with a ROLE: inside (map it), leave_out (a hole), band (a ring of N m OUTSIDE the
  shape = 'map the outside of the polygon'), corridor (a line made a strip N m wide); build_area() combines them in a
  local UTM frame (union of mapped minus union of left-out, simplified 0.25 m, pieces under 100 m2 dropped) into
  polygons the planner already accepts (ONE polygon at a time, holes allowed; separate pieces are planned one by one
  via a chooser). Editing is in the list under the map, not Leaflet's own edit tools (the edit toolbar is empty
  because drawn items are hidden). The widget's default OSM layer is REMOVED at creation; the background is an opt-in
  switch (OSM tile policy: attribution, no offline use) or the person's own tile URL. 'Leave out' only means not
  planned for coverage: the planner still overruns strip ends into the hole and may fly across it (6 waypoints
  inside a 50 m hole in the test); a real 'keep clear' needs routing and is NOT built. Takeoff = the pin (also written
  into the takeoff box, and cleared with it). Tests hand the map what the toolbar would send (AreaMap.add_drawn); the
  browser-side drawing, tile loading and the exact draw:created payload are UNVERIFIED (founder to test with
  screenshots). STILL TO BUILD: route over the map after planning; vertex editing; 'keep clear'; GCP upload;
  canopy height model; 3D patterns (oblique crosshatch, orbit/dome, wall).
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
