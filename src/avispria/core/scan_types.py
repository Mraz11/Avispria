# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The kinds of scan Avispria plans, in plain words, with the settings each one recommends.

Choosing what you want to capture decides everything else: how the camera points, how the aircraft
flies, which numbers you must give and how the photos are turned into a result afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScanType:
    key: str
    title: str
    summary: str  # what you get
    good_for: str
    how: str  # what the aircraft and camera do
    you_tell: str  # what you have to enter
    after: str  # what to do with the photos
    # settings the type recommends (the screen applies them when the type is chosen)
    gsd_cm: float = 2.0  # resolution at the centre of a picture, for the two area types
    front_percent: float = 80.0
    side_percent: float = 70.0
    tilt_deg: float = 0.0  # camera tilt from straight down
    crosshatch: bool = False  # lines in two directions

    @property
    def is_area(self) -> bool:
        return self.key in ("flat", "area_3d")


FLAT = ScanType(
    key="flat",
    title="Flat map of an area",
    summary="A top-down map: a stitched picture (orthomosaic) and a height model of the surface.",
    good_for="Fields, plots, roads, forest cover, canopy height, and change between flights.",
    how="The camera looks straight down and the aircraft flies parallel lines over the area, "
    "taking a photo at regular points along them.",
    you_tell="Where the area is, and how much detail you need.",
    after="Make maps: choose 'Map of an area'.",
)

AREA_3D = ScanType(
    key="area_3d",
    title="3D model of an area",
    summary="A 3D model of a site: its ground, trees and buildings seen from several sides.",
    good_for="Forest canopy structure, buildings and small sites, slopes and cliffs.",
    how="The camera is tilted about 30 degrees from straight down and the aircraft flies lines in "
    "two directions across the area, so every part is photographed from several sides. It takes "
    "about twice the photos and flying of a flat map.",
    you_tell="Where the area is, how much detail you need, and how far the camera is tilted.",
    after="Make maps: choose '3D model'.",
    gsd_cm=2.5,
    tilt_deg=30.0,
    crosshatch=True,
)

OBJECT_3D = ScanType(
    key="object_3d",
    title="3D model of one object",
    summary="A 3D model of a single tree, building or tower, seen from all around.",
    good_for="One big tree, a building, a tower, a statue or a rock.",
    how="The aircraft circles the object in rings at several heights, always facing it, with the "
    "camera tilted up a little at the bottom and down a little at the top, and stops to take a "
    "photo every few degrees. A few photos straight down cover the top.",
    you_tell="Where the object is, how tall it is, its widest radius, and how far from it the "
    "camera may fly.",
    after="Make maps: choose '3D model'.",
)

SCAN_TYPES: dict[str, ScanType] = {t.key: t for t in (FLAT, AREA_3D, OBJECT_3D)}
DEFAULT_TYPE = "flat"
