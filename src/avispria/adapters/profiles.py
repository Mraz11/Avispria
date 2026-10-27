# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load aircraft/camera profiles from the packaged TOML file or a user file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from avispria.core.camera import CameraProfile


@dataclass(frozen=True)
class DroneProfile:
    key: str
    name: str
    max_speed_ms: float
    drone_enum: int
    waypoint_limit: int
    verified: bool
    notes: str
    modes: dict[str, CameraProfile]


def _parse(data: dict[str, Any]) -> dict[str, DroneProfile]:
    profiles: dict[str, DroneProfile] = {}
    for key, raw in data.items():
        modes = {
            mode: CameraProfile(
                name=f"{key}-{mode}",
                sensor_width_mm=float(m["sensor_width_mm"]),
                sensor_height_mm=float(m["sensor_height_mm"]),
                focal_mm=float(m["focal_mm"]),
                image_width_px=int(m["image_width_px"]),
                image_height_px=int(m["image_height_px"]),
                min_interval_s=float(m["min_interval_s"]),
                readout_s=float(m["readout_s"]),
            )
            for mode, m in raw.get("modes", {}).items()
        }
        if not modes:
            raise ValueError(f"profile {key!r} defines no camera modes")
        profiles[key] = DroneProfile(
            key=key,
            name=str(raw["name"]),
            max_speed_ms=float(raw["max_speed_ms"]),
            drone_enum=int(raw["drone_enum"]),
            waypoint_limit=int(raw["waypoint_limit"]),
            verified=bool(raw.get("verified", False)),
            notes=str(raw.get("notes", "")),
            modes=modes,
        )
    return profiles


def load_profiles(path: Path | None = None) -> dict[str, DroneProfile]:
    """Packaged profiles, overridden key-by-key by ``path`` if given."""
    packaged = resources.files("avispria.data").joinpath("drones.toml").read_text("utf-8")
    profiles = _parse(tomllib.loads(packaged))
    if path is not None:
        profiles.update(_parse(tomllib.loads(path.read_text("utf-8"))))
    return profiles
