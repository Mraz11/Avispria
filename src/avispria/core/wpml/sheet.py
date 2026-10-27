# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""RC spot-check sheet: what the pilot should see in DJI Fly before flying."""

from __future__ import annotations

import csv
import hashlib
import io

from avispria.core.wpml.reader import read_mission


def plan_hash(kmz: bytes) -> str:
    """Short fingerprint printed on the sheet and in the flight log."""
    return hashlib.sha256(kmz).hexdigest()[:12]


def spot_check_csv(kmz: bytes) -> str:
    """CSV with one row per waypoint plus a header comment with totals and hash."""
    m = read_mission(kmz)
    buf = io.StringIO()
    buf.write(f"# plan {plan_hash(kmz)}  waypoints {len(m.waypoints)}  ")
    buf.write(f"speed {m.auto_speed_ms:g} m/s  heights relative to takeoff\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["index", "lat", "lon", "height_m", "speed_ms", "gimbal_pitch", "turn", "photo"]
    )
    for w in m.waypoints:
        writer.writerow(
            [
                w.index,
                f"{w.lat:.7f}",
                f"{w.lon:.7f}",
                f"{w.height_m:g}",
                f"{w.speed_ms:g}",
                "" if w.gimbal_pitch_deg is None else f"{w.gimbal_pitch_deg:g}",
                "stop" if "Stop" in w.turn_mode else "pass",
                "yes" if any(a.func == "takePhoto" for a in w.actions) else "",
            ]
        )
    return buf.getvalue()
