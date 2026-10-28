# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.core.processing import PRESETS, build_options, plan_resize

ALL = frozenset(
    {
        "dsm",
        "dtm",
        "fast-orthophoto",
        "pc-quality",
        "feature-quality",
        "auto-boundary",
        "rolling-shutter",
    }
)


def test_standard_preset_for_electronic_shutter() -> None:
    p = build_options("standard", ALL, electronic_shutter=True)
    assert p.options == {
        "dsm": True,
        "pc-quality": "medium",
        "feature-quality": "high",
        "auto-boundary": True,
        "rolling-shutter": True,
    }
    assert p.dropped == []
    assert any("rolling-shutter" in n for n in p.notes)


def test_fast_preset_skips_3d_and_mechanical_shutter_has_no_correction() -> None:
    p = build_options("fast", ALL, electronic_shutter=False)
    assert p.options["fast-orthophoto"] is True and "dsm" not in p.options
    assert "rolling-shutter" not in p.options


def test_unsupported_options_are_dropped_not_sent() -> None:
    p = build_options("detailed", frozenset({"dsm", "pc-quality"}), electronic_shutter=True)
    assert set(p.options) == {"dsm", "pc-quality"}
    assert set(p.dropped) == {"dtm", "feature-quality", "auto-boundary", "rolling-shutter"}


def test_unknown_preset() -> None:
    with pytest.raises(ValueError, match="preset"):
        build_options("ultra-max", ALL, electronic_shutter=False)  # type: ignore[arg-type]


def test_presets_are_described() -> None:
    assert set(PRESETS) == {"fast", "standard", "detailed"}
    assert all(p.description for p in PRESETS.values())


def test_resize_plan() -> None:
    assert plan_resize(8064, 6048, 12.2) == (4032, 3024)  # 48 MP -> 12 MP, same aspect
    assert plan_resize(4032, 3024, 12.2) is None  # already small enough
    assert plan_resize(8064, 6048, None) is None  # full resolution requested
    w, h = plan_resize(5472, 3648, 12.2) or (0, 0)  # 20 MP 3:2
    assert w * h <= 12.2e6 and abs(w / h - 1.5) < 0.01
