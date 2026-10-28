# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plain record of one survey photo's metadata (filled by adapters, used by QA)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PhotoRecord:
    name: str
    time: datetime | None
    lat: float | None
    lon: float | None
    relative_altitude_m: float | None  # above the takeoff point (DJI XMP)
    gimbal_pitch_deg: float | None  # -90 = straight down
    gimbal_yaw_deg: float | None  # compass direction of the image top
    speed_ms: float | None  # horizontal ground speed at capture
    exposure_s: float | None
    iso: int | None
    focal_mm: float | None
    focal_35mm: int | None
    width_px: int | None
    height_px: int | None
    model: str | None
    product: str | None
    shutter: str | None
