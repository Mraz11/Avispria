# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from avispria.core.clearance import enforce_slope, fit_profile


def test_enforce_slope_never_lowers_and_bounds_gradient() -> None:
    d = np.arange(0.0, 101.0, 5.0)
    h = np.full_like(d, 50.0)
    h[10] = 90.0  # a single tall tree
    out = enforce_slope(d, h, max_slope=0.5)
    assert np.all(out >= h)
    assert np.all(np.abs(np.diff(out)) <= 0.5 * np.diff(d) + 1e-9)
    assert out[10] == 90.0


def test_fit_profile_keeps_mandatory_points_and_ends() -> None:
    d = np.arange(0.0, 51.0, 5.0)
    h = np.full_like(d, 60.0)
    keep = fit_profile(d, h, mandatory=[4], max_excess_m=5.0)
    assert keep == [0, 4, 10]


def test_fit_profile_inserts_at_hill() -> None:
    d = np.arange(0.0, 101.0, 5.0)
    h = enforce_slope(d, np.where(np.abs(d - 50) < 1, 80.0, 60.0), 0.4)
    keep = fit_profile(d, h, mandatory=[], max_excess_m=100.0)
    assert 10 in keep  # the hill top must become a waypoint


@settings(max_examples=80, deadline=None)
@given(
    st.lists(st.floats(0, 120), min_size=3, max_size=60),
    st.floats(0.1, 1.0),
    st.floats(0.5, 20.0),
)
def test_fitted_lines_never_dip_below_requirement(
    raw: list[float], slope: float, excess: float
) -> None:
    d = np.arange(len(raw), dtype=float) * 5.0
    h = enforce_slope(d, np.asarray(raw), slope)
    keep = fit_profile(d, h, mandatory=[], max_excess_m=excess)
    line = np.interp(d, d[keep], h[keep])
    assert np.all(line >= h - 1e-6)
    assert np.all(line - h <= excess + 1e-6)
    chord = np.diff(h[keep]) / np.diff(d[keep])
    assert np.all(np.abs(chord) <= slope + 1e-9)


def test_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        enforce_slope(np.array([0.0, 1.0]), np.array([1.0]), 0.5)
    with pytest.raises(ValueError):
        fit_profile(np.array([0.0, 0.0, 1.0]), np.zeros(3), [], 1.0)
