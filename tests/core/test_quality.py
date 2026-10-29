# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest

from avispria.core.quality import summarize_reconstruction

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "odx" / "stats_brighton_standard.json"


def real_stats() -> dict:  # type: ignore[type-arg]
    return json.loads(FIXTURE.read_text())


def codes(summary) -> set[str]:  # type: ignore[no-untyped-def]
    return {i.code for i in summary.issues}


def test_real_brighton_run_summary() -> None:
    s = summarize_reconstruction(real_stats(), gsd_estimated_cm=1.89)
    assert (s.photos_placed, s.photos_total, s.components) == (18, 18, 1)
    assert s.reprojection_px == pytest.approx(0.827, abs=0.001)
    assert s.gps_error_m == pytest.approx(0.664, abs=0.001)
    assert s.points == 1_412_664 and s.sparse_points == 11_311
    assert s.area_m2 == pytest.approx(7058.6, abs=0.1)
    assert s.points_per_m2 == pytest.approx(200.1, abs=0.2)
    assert s.gsd_cm_measured == pytest.approx(1.59, abs=0.01)
    assert s.gsd_ratio == pytest.approx(1.59 / 1.89, abs=0.01)
    assert s.issues == []  # a good run raises nothing


def test_unplaced_photos_and_split_models_are_flagged() -> None:
    stats = real_stats()
    stats["reconstruction_statistics"]["reconstructed_shots_count"] = 14
    stats["reconstruction_statistics"]["components"] = 2
    s = summarize_reconstruction(stats, gsd_estimated_cm=None)
    assert codes(s) == {"RQ001", "RQ002"}
    assert "14 of 18" in next(i.message for i in s.issues if i.code == "RQ001")


def test_high_reprojection_error_and_gsd_mismatch() -> None:
    stats = real_stats()
    stats["reconstruction_statistics"]["reprojection_error_pixels"] = 2.4
    s = summarize_reconstruction(stats, gsd_estimated_cm=3.2)  # estimate twice the measured GSD
    assert codes(s) == {"RQ003", "RQ004"}
    assert s.gsd_ratio == pytest.approx(0.497, abs=0.01)


def test_missing_or_odd_statistics_never_crash() -> None:
    assert summarize_reconstruction({}, gsd_estimated_cm=1.9).issues == []
    s = summarize_reconstruction(
        {"reconstruction_statistics": {"initial_shots_count": "n/a"}, "gps_errors": None}, None
    )
    assert s.photos_total is None and s.gps_error_m is None
