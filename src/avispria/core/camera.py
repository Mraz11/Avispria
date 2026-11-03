# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pinhole camera model: ground sampling distance, footprints and photo spacing.

Conventions: the camera is mounted landscape with the image width across the
flight line, so the along-track footprint uses the image height.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DIAGONAL_35MM_MM = math.hypot(36.0, 24.0)


@dataclass(frozen=True)
class CameraProfile:
    """Geometry and timing of one camera mode (for example 48 MP or 12 MP)."""

    name: str
    sensor_width_mm: float
    sensor_height_mm: float
    focal_mm: float
    image_width_px: int
    image_height_px: int
    min_interval_s: float
    readout_s: float

    def __post_init__(self) -> None:
        for field in (
            "sensor_width_mm",
            "sensor_height_mm",
            "focal_mm",
            "image_width_px",
            "image_height_px",
            "min_interval_s",
            "readout_s",
        ):
            value = getattr(self, field)
            if not (isinstance(value, int | float) and math.isfinite(value) and value > 0):
                raise ValueError(f"{field} must be a positive number, got {value!r}")

    @property
    def focal_px(self) -> float:
        """Focal length expressed in pixels (square pixels assumed)."""
        return self.focal_mm / self.sensor_width_mm * self.image_width_px


@dataclass(frozen=True)
class Spacing:
    """Distance between photos along a line and between adjacent lines (metres)."""

    photo_m: float
    line_m: float


def _check_height(agl_m: float) -> None:
    if not (math.isfinite(agl_m) and agl_m > 0):
        raise ValueError(f"height above ground must be positive, got {agl_m!r}")


def gsd_m(cam: CameraProfile, agl_m: float) -> float:
    """Nadir ground sampling distance in metres per pixel."""
    _check_height(agl_m)
    return agl_m * cam.sensor_width_mm / (cam.focal_mm * cam.image_width_px)


def altitude_for_gsd(cam: CameraProfile, target_gsd_m: float) -> float:
    """Height above the surface that gives the requested nadir GSD."""
    if not (math.isfinite(target_gsd_m) and target_gsd_m > 0):
        raise ValueError(f"target GSD must be positive, got {target_gsd_m!r}")
    return target_gsd_m * cam.focal_mm * cam.image_width_px / cam.sensor_width_mm


def footprint_m(cam: CameraProfile, agl_m: float) -> tuple[float, float]:
    """Nadir image footprint as (across-track, along-track) metres."""
    g = gsd_m(cam, agl_m)
    return g * cam.image_width_px, g * cam.image_height_px


def spacing_m(
    cam: CameraProfile, agl_m: float, front_overlap: float, side_overlap: float
) -> Spacing:
    """Photo and line spacing for the given fractional overlaps (0 <= overlap < 1)."""
    for label, value in (("front_overlap", front_overlap), ("side_overlap", side_overlap)):
        if not (0.0 <= value < 1.0):
            raise ValueError(f"{label} must be in [0, 1), got {value!r}")
    across, along = footprint_m(cam, agl_m)
    return Spacing(photo_m=along * (1.0 - front_overlap), line_m=across * (1.0 - side_overlap))


def oblique_gsd_m(
    cam: CameraProfile, agl_m: float, tilt_deg: float, row_px: float = 0.0
) -> tuple[float, float]:
    """(along, across) GSD for a camera tilted ``tilt_deg`` from nadir over flat ground.

    ``row_px`` is the pixel offset from the principal point toward the far edge.
    """
    _check_height(agl_m)
    phi = math.atan2(row_px, cam.focal_px)
    theta = math.radians(tilt_deg) + phi
    if not (0.0 <= theta < math.radians(89.0)):
        raise ValueError("ray must point below the horizon (tilt + offset < 89 deg)")
    along = agl_m * math.cos(phi) ** 2 / (cam.focal_px * math.cos(theta) ** 2)
    across = agl_m * math.cos(phi) / (cam.focal_px * math.cos(theta))
    return along, across


def sensor_size_from_exif(
    focal_mm: float, focal_35mm_mm: float, width_px: int, height_px: int
) -> tuple[float, float]:
    """Estimate sensor (width, height) in mm from EXIF focal lengths and image size.

    Uses the diagonal crop factor that defines the 35 mm equivalent focal length.
    """
    for label, value in (("focal_mm", focal_mm), ("focal_35mm_mm", focal_35mm_mm)):
        if not (math.isfinite(value) and value > 0):
            raise ValueError(f"{label} must be positive, got {value!r}")
    if width_px <= 0 or height_px <= 0:
        raise ValueError("image dimensions must be positive")
    diagonal_mm = DIAGONAL_35MM_MM * focal_mm / focal_35mm_mm
    diagonal_px = math.hypot(width_px, height_px)
    return diagonal_mm * width_px / diagonal_px, diagonal_mm * height_px / diagonal_px


# ------------------------------------------------------------ a camera tilted off straight down
MAX_RAY_DEG = 80.0  # the picture's farthest ray may not be steeper than this from straight down
OBLIQUE_MIN_DEG = 1.0  # less tilt than this is treated as straight down


@dataclass(frozen=True)
class ObliqueView:
    """What a camera tilted ``tilt_deg`` from straight down (looking ahead, along the flight) sees
    over flat ground from ``agl_m`` above it. Distances are along the ground, from the point
    directly below the aircraft; 'near' is the bottom edge of the picture, 'far' the top."""

    tilt_deg: float
    agl_m: float
    near_ahead_m: float  # where the near edge lands (negative: behind the aircraft)
    far_ahead_m: float
    across_near_m: float  # the picture's width at its near edge, at its centre, at its far edge
    across_centre_m: float
    across_far_m: float
    gsd_near_m: float  # metres per pixel across the track, at those same three places
    gsd_centre_m: float
    gsd_far_m: float
    gsd_along_near_m: float  # metres per pixel ALONG the track at the near edge: the finest, so
    # the one that decides how much motion blur a shutter speed gives

    @property
    def along_m(self) -> float:
        """Ground length of one picture along the flight direction."""
        return self.far_ahead_m - self.near_ahead_m


def oblique_view(cam: CameraProfile, agl_m: float, tilt_deg: float) -> ObliqueView:
    """The footprint of one picture from a camera tilted ``tilt_deg`` from straight down.

    Raises ValueError when the tilt is so steep that the top of the picture would look near the
    horizon (the ground there is stretched out of all use).
    """
    _check_height(agl_m)
    if not (math.isfinite(tilt_deg) and 0.0 <= tilt_deg < 90.0):
        raise ValueError(
            f"tilt must be between 0 and 90 degrees from straight down, got {tilt_deg!r}"
        )
    half = math.atan(
        (cam.image_height_px / 2.0) / cam.focal_px
    )  # half the picture's height, as an angle
    theta = math.radians(tilt_deg)
    if math.degrees(theta + half) > MAX_RAY_DEG:
        worst = MAX_RAY_DEG - math.degrees(half)
        raise ValueError(
            f"a tilt of {tilt_deg:g} degrees is too steep: the top of the picture would look more "
            f"than {MAX_RAY_DEG:g} degrees from straight down; use at most {worst:.0f} degrees"
        )

    def across_gsd(offset: float) -> float:
        ray = theta + offset
        return agl_m * math.cos(offset) / (cam.focal_px * math.cos(ray))

    def along_gsd(offset: float) -> float:
        ray = theta + offset
        return agl_m * math.cos(offset) ** 2 / (cam.focal_px * math.cos(ray) ** 2)

    width = float(cam.image_width_px)
    return ObliqueView(
        tilt_deg=tilt_deg,
        agl_m=agl_m,
        near_ahead_m=agl_m * math.tan(theta - half),
        far_ahead_m=agl_m * math.tan(theta + half),
        across_near_m=across_gsd(-half) * width,
        across_centre_m=across_gsd(0.0) * width,
        across_far_m=across_gsd(half) * width,
        gsd_near_m=across_gsd(-half),
        gsd_centre_m=across_gsd(0.0),
        gsd_far_m=across_gsd(half),
        gsd_along_near_m=along_gsd(-half),
    )


def altitude_for_oblique_gsd(cam: CameraProfile, target_gsd_m: float, tilt_deg: float) -> float:
    """Height above the surface that gives ``target_gsd_m`` at the CENTRE of a tilted picture."""
    if not (math.isfinite(target_gsd_m) and target_gsd_m > 0):
        raise ValueError(f"target GSD must be positive, got {target_gsd_m!r}")
    return target_gsd_m * cam.focal_px * math.cos(math.radians(tilt_deg))
