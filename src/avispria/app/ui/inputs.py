# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading what a person typed, with error messages that say what to do."""

from __future__ import annotations

import re


def parse_latlon_text(text: str) -> tuple[float, float]:
    """Latitude and longitude from text like ``23.8290, 90.4170`` (comma or space)."""
    cleaned = text.replace(";", ",").replace("\N{DEGREE SIGN}", " ").strip()
    parts = [p for p in re.split(r"[,\s]+", cleaned) if p]
    example = "Enter latitude and longitude as two numbers, like 23.8290, 90.4170"
    if len(parts) != 2:
        raise ValueError(example)
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        raise ValueError(example) from None
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"Latitude {lat:g} is not between -90 and 90. Latitude comes first.")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"Longitude {lon:g} is not between -180 and 180.")
    return lat, lon
