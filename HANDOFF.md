# HANDOFF - 2026-10-29 - session #4 (doctor, engine, processing)
## Done this session
- `doctor`: RAM/swap/CPU/disk + verdict with real alternatives (ODM RAM table);
  finds the native WebODM app by its processes/ports; `--details`.
- `engine`: finds WebODM's NodeODX, reads its token from the running command line
  (memory only), connects via PyODX (BSD-3), lists 80 supported options.
- `process`: photos -> QA -> engine -> feasibility -> presets (only supported options;
  rolling-shutter for electronic shutters) -> 12 MP resize keeping EXIF+XMP -> upload ->
  progress -> all.zip + extracted results -> provenance JSON with SHA-256s.
- CLI split into modules (cli.py had hit the 400-line limit).
## Current state (command proof)
- 184 tests pass (Linux sandbox); founder's Windows run of `engine` connected to
  ODX 3.8.4 (API 2.4.0), 12 cores, 16 GB, 80 options.
- `process` verified on the founder's PC with ODM's public Brighton Beach set (18 photos,
  Phantom 3): fast 2 min, standard 8 min; 18/18 photos placed, reprojection 0.83 px,
  GPS agreement 0.66 m, 1.41 M points. Output now at the photos' GSD (1.9 cm/px), not 5.
- ODX measured GSD 1.59 cm/px vs Avispria's estimate 1.89 (ratio 0.84). Causes not yet
  separated: terrain above takeoff level (flat-ground assumption) and/or the 35 mm-equivalent
  sensor-size convention for 16:9 crops. `process` now records both for calibration.
- GitHub main was at 9c30a9f (patch 0010) when last checked: 0011+ were local only.
## Open problems / suspicions
- Founder grounded ~1 month; test `process` with a public sample dataset.
- Non-DJI photos: EXIF GPS fallback not implemented (QA warns, processing works).
- PyODX uses deprecated datetime.utcfromtimestamp (narrowly ignored; report upstream).
## Next single task (ready-to-paste)
DEM-aware footprints/GSD in capture QA (use the engine's DSM or a DEM instead of flat ground),
then compare estimated vs measured GSD on Brighton Beach and the Lito X1 once flights resume.
## Decisions made
- Process through NodeODX directly (not WebODM's API): no login, no WebODM settings
  touched; results importable into WebODM via its Import button.
- Default processing resolution 12.2 MP (JPEG only; DNG sent at full size).
## Do-not-touch notes
- tests/fixtures/* stay byte-exact; never print or persist engine tokens.
