# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent ground truth for photo footprints: cast rays, share no formulas with the program."""

import math

from shapely.geometry import Polygon

from avispria.core.camera import CameraProfile


def ground_point(
    cam: CameraProfile, h: float, tilt_deg: float, x_px: float, v_px: float
) -> tuple[float, float]:
    """Where the ray through a pixel meets flat ground: the camera is h metres up, looks north
    and is tilted tilt_deg from straight down; x_px is right, v_px towards the top (far)."""
    t = math.radians(tilt_deg)
    axis = (0.0, math.sin(t), -math.cos(t))  # where the camera points
    up = (0.0, math.cos(t), math.sin(t))  # towards the top of the picture
    f = cam.focal_px
    d = (f * axis[0] + x_px, f * axis[1] + v_px * up[1], f * axis[2] + v_px * up[2])
    s = h / -d[2]  # d[2] < 0: the ray goes down
    return s * d[0], s * d[1]


def footprint(
    cam: CameraProfile, h: float, tilt_deg: float, east: float, north: float, course_deg: float
) -> Polygon:
    """The ground a photo covers: its four corners cast onto flat ground, turned to the course."""
    b = math.radians(course_deg)
    forward = (math.sin(b), math.cos(b))
    right = (math.cos(b), -math.sin(b))
    hw, hh = cam.image_width_px / 2.0, cam.image_height_px / 2.0
    corners = []
    for x_px, v_px in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        cx, cy = ground_point(cam, h, tilt_deg, x_px, v_px)
        corners.append(
            (east + cx * right[0] + cy * forward[0], north + cx * right[1] + cy * forward[1])
        )
    return Polygon(corners)
