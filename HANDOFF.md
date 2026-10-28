# HANDOFF - 2026-10-28 - session #3 (capture QA)
## Done this session
- Dependency-free EXIF (JPEG + DNG SubIFD) and DJI XMP readers; photo scanning.
- Capture QA: GSD, footprints, neighbour overlap, view-count coverage map, blur,
  gimbal, altitude spread, timing gaps. CLI: `qa`, `camera-from-photo`.
- Lito X1 profile now from real EXIF: camera FC9589, sensor 9.692 x 7.269 mm
  (old borrowed values understated GSD by 8%).
## Current state (command proof)
- Windows 11 local run verified 2026-10-27: 115 passed, coverage 89.9%.
- CI green on ubuntu/windows/macos (run #3, 2026-10-28); release v0.1.0a1.
- This session: 134 tests pass (Linux sandbox); real-DNG test passes on founder photos.
## Open problems / suspicions
- No flight possible for ~1 month (founder near an airport).
- Straight legs, curve dip, real photo interval still need the probe flight.
- takePhoto encoding still unseen; interval mode remains the default.
- Footprints assume flat ground at takeoff level; add DEM-aware footprints later.
## Next single task (ready-to-paste)
Processing orchestration: drive a local WebODM/NodeODX node via PyODX from a QA'd
photo folder (Phase 2b), with presets and the provenance bundle.
## Decisions made
- Coverage metric = share of the area seen by >=3 and >=5 photos.
## Do-not-touch notes
- tests/fixtures/* stay byte-exact; photo fixture holds metadata only (no images).
