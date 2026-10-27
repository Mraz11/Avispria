# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from avispria.core.clearance import along_track_envelope, enforce_slope, fit_profile


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
    keep, heights = fit_profile(d, h, mandatory=[4], max_excess_m=5.0)
    assert keep == [0, 4, 10]
    assert np.allclose(heights, 60.0)


def test_fit_profile_inserts_at_hill() -> None:
    d = np.arange(0.0, 101.0, 5.0)
    h = enforce_slope(d, np.where(np.abs(d - 50) < 1, 80.0, 60.0), 0.4)
    keep, _ = fit_profile(d, h, mandatory=[], max_excess_m=100.0)
    assert 10 in keep  # the hill top must become a waypoint


@settings(max_examples=150, deadline=None)
@given(
    st.lists(st.floats(0, 120), min_size=3, max_size=60),
    st.floats(0.1, 1.0),
    st.floats(0.5, 20.0),
    st.floats(0.0, 1.0),
)
def test_fitted_lines_never_dip_below_requirement(
    raw: list[float], slope: float, excess: float, lift_frac: float
) -> None:
    d = np.arange(len(raw), dtype=float) * 5.0
    h = enforce_slope(d, np.asarray(raw), slope)
    lift = excess * lift_frac
    keep, heights = fit_profile(
        d, h, mandatory=[], max_excess_m=excess, lift_m=lift, max_slope=slope
    )
    line = np.interp(d, d[keep], heights)
    assert np.all(line >= h - 1e-6)
    assert np.all(line - h <= excess + lift + 1e-6)
    assert np.all(heights >= h[keep] - 1e-9)
    chord = np.diff(heights) / np.diff(d[keep])
    assert np.all(np.abs(chord) <= slope + 1e-9)


def test_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        enforce_slope(np.array([0.0, 1.0]), np.array([1.0]), 0.5)
    with pytest.raises(ValueError):
        fit_profile(np.array([0.0, 0.0, 1.0]), np.zeros(3), [], 1.0)


def test_envelope_never_lowers_and_spreads_peaks() -> None:
    d = np.arange(0.0, 101.0, 5.0)
    h = np.zeros_like(d)
    h[10] = 7.0
    env = along_track_envelope(d, h, window_m=10.0)
    assert np.all(env >= h)
    assert np.count_nonzero(env == 7.0) == 5  # +/- 10 m around the peak
    assert np.array_equal(along_track_envelope(d, h, 0.0), h)
