# HANDOFF - 2026-10-27 - session #2 (build)
## Done this session
- Core: camera, speed solver, AOI/UTM, strips, DEM sampling/filters, profile
  fitting (segment-safe, lift-based), planner, sorties, safety validator.
- WPML: safe KMZ/XML reader, dummy-template bootstrap, writer, independent linter,
  spot-check sheet. Built against the founder's real Lito X1 DJI Fly file.
- CLI: drones, inspect, lint, sheet, plan, prepare-copy. GeoTIFF DEM loader.
- Docs: docs/field/first-test-flight.md.
## Current state (command proof)
- 115 tests pass; scripts/check.py green on Linux (Claude sandbox).
- NOT yet verified: Windows/macOS CI, any real flight.
## Open problems / suspicions
- Straight legs (useStraightLine=1) and curve-dip size unverified: probe flight.
- takePhoto encoding unverified: need a DJI Fly dummy with a Take Photo action.
- Camera geometry assumed (FC8482); needs an ORIGINAL Lito X1 photo (zipped).
- Pins: rasterio<1.5 (macOS wheels), numpy<2.5 (rasterio 1.4 read()).
## Next single task (ready-to-paste)
After the probe flight: build capture QA (read photo EXIF/XMP: positions,
RelativeAltitude, gimbal pitch, timestamps) and measure straightness, curve dip
and photo interval from the founder's probe photos.
## Decisions made
- Default photo mode = interval. Curve-dip margin 10 m. Skew budget 15 px.
## Do-not-touch notes
- tests/fixtures/dji_fly_dummy/* must stay byte-exact (excluded from hooks).
