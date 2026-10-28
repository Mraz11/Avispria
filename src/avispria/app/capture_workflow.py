# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capture QA and camera calibration from photo folders."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from pathlib import Path

from avispria.adapters.photos import read_photo, scan_photos
from avispria.adapters.profiles import DroneProfile
from avispria.core.camera import CameraProfile, sensor_size_from_exif
from avispria.core.capture import CaptureReport, QaThresholds, analyse_capture
from avispria.core.photo import PhotoRecord
from avispria.core.safety import Issue

DEFAULT_MIN_INTERVAL_S = 2.0
DEFAULT_READOUT_S = 0.03


def camera_from_record(record: PhotoRecord) -> CameraProfile:
    """Camera geometry from one photo's EXIF (focal length, 35 mm equivalent, size)."""
    if None in (record.focal_mm, record.focal_35mm, record.width_px, record.height_px):
        raise ValueError(f"{record.name}: EXIF lacks focal length, 35 mm equivalent or image size")
    assert record.focal_mm and record.focal_35mm and record.width_px and record.height_px
    width_mm, height_mm = sensor_size_from_exif(
        record.focal_mm, float(record.focal_35mm), record.width_px, record.height_px
    )
    return CameraProfile(
        name=f"{record.model or 'camera'}-{record.width_px}x{record.height_px}",
        sensor_width_mm=width_mm,
        sensor_height_mm=height_mm,
        focal_mm=record.focal_mm,
        image_width_px=record.width_px,
        image_height_px=record.height_px,
        min_interval_s=DEFAULT_MIN_INTERVAL_S,
        readout_s=DEFAULT_READOUT_S,
    )


def camera_chooser(
    profile: DroneProfile | None, notes: list[Issue]
) -> Callable[[PhotoRecord], CameraProfile]:
    """Pick the profile mode matching each photo's width, else derive it from EXIF."""
    cache: dict[tuple[str | None, int | None], CameraProfile] = {}

    def choose(record: PhotoRecord) -> CameraProfile:
        key = (record.model, record.width_px)
        if key not in cache:
            match = None
            if profile is not None:
                match = next(
                    (m for m in profile.modes.values() if m.image_width_px == record.width_px), None
                )
                if profile.camera_model and record.model and record.model != profile.camera_model:
                    notes.append(
                        Issue(
                            "warning",
                            "QA008",
                            f"photos are from camera {record.model}, profile expects "
                            f"{profile.camera_model}",
                        )
                    )
            cache[key] = match or camera_from_record(record)
        return cache[key]

    return choose


def run_qa(
    folder: Path,
    profile: DroneProfile | None,
    thresholds: QaThresholds | None = None,
    *,
    recursive: bool = False,
) -> tuple[CaptureReport, list[tuple[str, str]]]:
    records, skipped = scan_photos(folder, recursive=recursive)
    notes: list[Issue] = []
    report = analyse_capture(records, camera_chooser(profile, notes), thresholds)
    report.issues.extend(notes)
    return report, skipped


def report_csv(report: CaptureReport) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        ["photo", "gsd_cm", "overlap_prev_pct", "best_overlap_pct", "best_neighbour", "blur_px"]
    )
    for p in report.photos:
        w.writerow(
            [
                p.name,
                f"{p.gsd_m * 100:.2f}",
                "" if p.overlap_prev is None else f"{p.overlap_prev * 100:.0f}",
                "" if p.best_overlap is None else f"{p.best_overlap * 100:.0f}",
                p.best_neighbour or "",
                "" if p.blur_px is None else f"{p.blur_px:.2f}",
            ]
        )
    return buf.getvalue()


def camera_toml(path: Path, key: str = "my-drone") -> str:
    """A drones.toml snippet for the camera mode found in ``path``."""
    record = read_photo(path)
    cam = camera_from_record(record)
    mode = f"{int(cam.image_width_px * cam.image_height_px / 1e6)}mp"  # DJI rounds down
    return (
        f"# derived from {record.name} ({record.product or 'unknown aircraft'}, {record.model})\n"
        f"[{key}.modes.{mode}]\n"
        f"sensor_width_mm = {cam.sensor_width_mm:.3f}\n"
        f"sensor_height_mm = {cam.sensor_height_mm:.3f}\n"
        f"focal_mm = {cam.focal_mm:g}\n"
        f"image_width_px = {cam.image_width_px}\n"
        f"image_height_px = {cam.image_height_px}\n"
        f"min_interval_s = {DEFAULT_MIN_INTERVAL_S}   # measure with a probe flight\n"
        f"readout_s = {DEFAULT_READOUT_S}   # OpenDroneMap default\n"
    )
