# HANDOFF - 2026-10-29 - session #4 (doctor, engine, processing, terrain-aware QA)
## Done this session
- `doctor`: RAM/swap/CPU/disk + verdict with real alternatives (ODM RAM table);
  finds the native WebODM app by its processes/ports; `--details`.
- `engine`: finds WebODM's NodeODX, reads its token from the running command line
  (memory only), connects via PyODX (BSD-3), lists 80 supported options.
- `process`: photos -> QA -> engine -> feasibility -> presets (only supported options;
  rolling-shutter for electronic shutters) -> 12 MP resize keeping EXIF+XMP -> upload ->
  progress -> all.zip + extracted results -> provenance JSON with SHA-256s.
- CLI split into modules (cli.py had hit the 400-line limit).
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
Canopy height/change design: needs a terrain model (leaf-off flight, external LiDAR DTM or
open ground) - pick a public forest dataset to develop against. Alternatively feed terrain
into the planner's overlap/spacing check. Calibrate camera size when Lito X1 data is processed.
## Decisions made
- Process through NodeODX directly (not WebODM's API): no login, no WebODM settings
  touched; results importable into WebODM via its Import button.
- Default processing resolution 12.2 MP (JPEG only; DNG sent at full size).
- Terrain in QA uses the nadir surface point per photo (first order on steep slopes).
## Do-not-touch notes
- tests/fixtures/* stay byte-exact; never print or persist engine tokens.
