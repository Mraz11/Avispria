# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Processing presets, engine options and photo resizing plans (pure logic).

Option names follow the ODX/ODM engine. Only options the connected engine reports
are sent; anything else is listed as dropped so the provenance stays truthful.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

PresetName = Literal["fast", "standard", "detailed"]
MIN_PHOTOS = 5  # WebODM's stated minimum; 16-32 is typically the practical minimum
DEFAULT_RESIZE_MP = 12.2  # like WebODM's upload resizing; keeps memory predictable


@dataclass(frozen=True)
class Preset:
    name: PresetName
    description: str
    options: dict[str, object]
    outputs: tuple[str, ...]
    # surface-model cell size as a multiple of the GSD, matching the point density the
    # preset's pc-quality produces (each quality step halves the depth-map resolution);
    # None: the preset makes no surface model
    dem_gsd_factor: float | None = None


PRESETS: dict[str, Preset] = {
    "fast": Preset(
        "fast",
        "Orthophoto only, straight from the sparse model: quickest, lowest memory, no 3D.",
        {"fast-orthophoto": True, "feature-quality": "medium", "auto-boundary": True},
        ("orthophoto",),
    ),
    "standard": Preset(
        "standard",
        "Orthophoto, surface model (DSM) and point cloud at medium density.",
        {"dsm": True, "pc-quality": "medium", "feature-quality": "high", "auto-boundary": True},
        ("orthophoto", "dsm", "point cloud"),
        dem_gsd_factor=4.0,  # pc-quality medium
    ),
    "detailed": Preset(
        "detailed",
        "Adds a terrain model (DTM) and a denser point cloud: slower, more memory.",
        {
            "dsm": True,
            "dtm": True,
            "pc-quality": "high",
            "feature-quality": "high",
            "auto-boundary": True,
        },
        ("orthophoto", "dsm", "dtm", "point cloud"),
        dem_gsd_factor=2.0,  # pc-quality high
    ),
}


@dataclass(frozen=True)
class ProcessingOptions:
    preset: PresetName
    options: dict[str, object]
    dropped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _round_up(value: float, step: float = 0.1) -> float:
    return math.ceil(value / step - 1e-9) * step


def effective_gsd_cm(gsd_cm: float, *, native_mp: float, processing_mp: float) -> float:
    """GSD of the photos actually sent: downscaling by k in area coarsens GSD by sqrt(k)."""
    if processing_mp <= 0 or native_mp <= processing_mp:
        return gsd_cm
    return gsd_cm * math.sqrt(native_mp / processing_mp)


def build_options(
    preset: PresetName,
    supported: frozenset[str],
    *,
    electronic_shutter: bool,
    gsd_cm: float | None = None,
) -> ProcessingOptions:
    """Engine options for ``preset``, limited to what the engine ``supported``.

    With a known ``gsd_cm`` (of the photos as uploaded) the orthophoto is made at that
    resolution instead of the engine's 5 cm default, and the surface model at the
    preset's multiple of it.
    """
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose {', '.join(PRESETS)}")
    chosen = PRESETS[preset]
    wanted = dict(chosen.options)
    notes: list[str] = []
    if gsd_cm is not None and gsd_cm > 0:
        ortho = round(_round_up(gsd_cm), 1)
        wanted["orthophoto-resolution"] = ortho
        text = f"orthophoto at {ortho:g} cm/px (the photos' ground resolution)"
        if chosen.dem_gsd_factor is not None:
            dem = round(_round_up(gsd_cm * chosen.dem_gsd_factor), 1)
            wanted["dem-resolution"] = dem
            text += f", surface model at {dem:g} cm/px"
        notes.append(text)
    if electronic_shutter:
        wanted["rolling-shutter"] = True
        notes.append(
            "rolling-shutter correction on: the camera has an electronic (rolling) shutter"
        )
    options = {k: v for k, v in wanted.items() if k in supported}
    dropped = [k for k in wanted if k not in supported]
    return ProcessingOptions(preset, options, dropped, notes)


def plan_resize(width: int, height: int, max_mp: float | None) -> tuple[int, int] | None:
    """New (width, height) keeping the aspect ratio, or None if no resize is needed."""
    if max_mp is None or width * height <= max_mp * 1e6:
        return None
    scale = math.sqrt(max_mp * 1e6 / (width * height))
    factor = 1 / scale
    whole = round(factor)
    if whole >= 2 and abs(factor - whole) / whole < 0.02:
        # e.g. 48 MP -> 12 MP: an exact half matches the camera's own 12 MP mode
        return max(1, width // whole), max(1, height // whole)
    return max(1, math.floor(width * scale)), max(1, math.floor(height * scale))
