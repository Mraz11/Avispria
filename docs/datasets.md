# Test datasets

Photos are never committed to this repository (they are large, and have their own licences). They are
fetched when needed.

## Helenenschacht (forest roadway, Autel EVO II Pro RTK)

- Source: <https://github.com/OpenDroneMap/odm_data_helenenschacht> (branch `main`), part of the
  OpenDroneMap sample data (<https://www.opendronemap.org/odm/datasets/>). Licence of the repository: GPL-3.0.
- 176 JPEGs (20 MP, 5472 x 3648, 2.4 GB), straight down, 1-inch sensor, position in the EXIF, RTK logs in
  `RTK_Data/`, and surveyed ground control points in `GCP/gcp_list.txt` (EPSG:4326; altitude 463.66 m).
- It holds **only raw photos**: no surface or terrain model. To get one, process it with Avispria on a
  computer with enough memory (WebODM recommends much more than 16 GB for a set this size at full size;
  `avispria process --preset detailed` sends 12 MP copies, which fits a 16 GB computer).

What Avispria finds in it (the photo check, from metadata alone):

    uv run avispria qa images --ground-elev 463.7

- 176 photos used, about 49.4 m above the ground (GPS height 513.0-513.2 m, very steady), 1.12 cm/px.
- Overlap 87% along the line and 89% between lines (about 56 views per point): far more than needed.
- The block is only about 93 m x 85 m and the flight lasted 8 minutes. One 16 s gap in the sequence.
- This drone records **no height above takeoff and no camera angle**. Without `--ground-elev` (or an
  elevation model) the check cannot work out the resolution and says so (QA015); the camera angle is
  assumed straight down and said aloud (QA016).

### Fetching only what is needed

A photo's metadata is in its first few kilobytes, so the headers of all 176 photos (46 MB) can be fetched
with HTTP range requests (`Range: bytes=0-262143` against
`https://raw.githubusercontent.com/OpenDroneMap/odm_data_helenenschacht/main/images/MAX_0002.JPG`)
instead of the 2.4 GB: enough for `avispria qa`, `camera-from-photo` and `doctor`, not for processing.

## Brighton Beach (18 photos, DJI Phantom 3)

<https://github.com/pierotofy/drone_dataset_brighton_beach>. Used for processing runs and the terrain-aware
checks; its 1 m surface model is in `tests/fixtures/odx/`.
