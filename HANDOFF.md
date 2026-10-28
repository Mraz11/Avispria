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
- `process` NOT yet run against the real engine (needs >= 5 overlapping photos).
## Open problems / suspicions
- Founder grounded ~1 month; test `process` with a public sample dataset.
- Non-DJI photos: EXIF GPS fallback not implemented (QA warns, processing works).
- PyODX uses deprecated datetime.utcfromtimestamp (narrowly ignored; report upstream).
## Next single task (ready-to-paste)
Run `avispria process` on a public dataset on the founder's PC; fix what it shows.
## Decisions made
- Process through NodeODX directly (not WebODM's API): no login, no WebODM settings
  touched; results importable into WebODM via its Import button.
- Default processing resolution 12.2 MP (JPEG only; DNG sent at full size).
## Do-not-touch notes
- tests/fixtures/* stay byte-exact; never print or persist engine tokens.
