# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Height-profile shaping for terrain following.

DJI Fly flies a straight line between waypoint heights, so the required profile
must be represented by a set of waypoints whose straight segments never dip
below it.
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def _check(d: FloatArray, h: FloatArray) -> None:
    if d.ndim != 1 or d.shape != h.shape:
        raise ValueError("distance and height arrays must be 1-D and the same length")
    if len(d) < 2:
        raise ValueError("a profile needs at least two samples")
    if np.any(np.diff(d) <= 0):
        raise ValueError("distances must be strictly increasing")
    if not (np.all(np.isfinite(d)) and np.all(np.isfinite(h))):
        raise ValueError("profile contains non-finite values")


def along_track_envelope(d: FloatArray, h: FloatArray, window_m: float) -> FloatArray:
    """Moving maximum of ``h`` over +/- ``window_m`` along the path.

    The result is never below ``h``; it turns many small surface kinks into a few
    plateaus and ramps, so far fewer waypoints are needed for the same guarantee.
    """
    d = np.asarray(d, dtype=float)
    h = np.asarray(h, dtype=float)
    _check(d, h)
    if window_m < 0:
        raise ValueError("window_m must be >= 0")
    if window_m == 0:
        return h.copy()
    lo = np.searchsorted(d, d - window_m, side="left")
    hi = np.searchsorted(d, d + window_m, side="right")
    return np.array([h[a:b].max() for a, b in zip(lo, hi, strict=True)])


def enforce_slope(d: FloatArray, h: FloatArray, max_slope: float) -> FloatArray:
    """Raise heights so no climb or descent exceeds ``max_slope`` (rise over run).

    A forward pass limits descents and a backward pass makes climbs start early
    enough; values are only ever raised, so clearance is preserved.
    """
    d = np.asarray(d, dtype=float)
    out = np.array(h, dtype=float)
    _check(d, out)
    if max_slope <= 0:
        raise ValueError("max_slope must be positive")
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1] - max_slope * (d[i] - d[i - 1]))
    for i in range(len(out) - 2, -1, -1):
        out[i] = max(out[i], out[i + 1] - max_slope * (d[i + 1] - d[i]))
    return out


def fit_profile(
    d: FloatArray,
    h_req: FloatArray,
    mandatory: Iterable[int],
    max_excess_m: float,
    *,
    lift_m: float = 0.0,
    max_slope: float | None = None,
) -> tuple[list[int], FloatArray]:
    """Choose waypoint samples and their heights.

    Returns ``(keep, heights)``. Guarantees that the straight line between
    consecutive kept waypoints is never below ``h_req`` at any sample. Waypoints
    are inserted where a segment dips more than ``lift_m`` below the requirement
    or rises more than ``max_excess_m`` above it; smaller dips are fixed by
    lifting the segment's endpoints (at most ``lift_m``). If ``max_slope`` is
    given, chords steeper than it are fixed by raising the lower endpoint.
    Heights are only ever raised, so the clearance guarantee holds throughout.
    """
    d = np.asarray(d, dtype=float)
    h = np.asarray(h_req, dtype=float)
    _check(d, h)
    if max_excess_m <= 0:
        raise ValueError("max_excess_m must be positive")
    if not 0 <= lift_m <= max_excess_m:
        raise ValueError("lift_m must be in [0, max_excess_m]")
    n = len(d)
    keep = sorted({0, n - 1, *(int(i) for i in mandatory)})
    if keep[0] < 0 or keep[-1] > n - 1:
        raise ValueError("mandatory index out of range")
    changed = True
    while changed:
        changed = False
        new_keep = [keep[0]]
        for a, b in pairwise(keep):
            if b - a > 1:
                deficit, excess = _segment_errors(d, h, a, b)
                k_def = int(np.argmax(deficit))
                k_exc = int(np.argmax(excess))
                if deficit[k_def] > lift_m + 1e-9:
                    new_keep.append(a + k_def)
                    changed = True
                elif excess[k_exc] > max_excess_m:
                    new_keep.append(a + k_exc)
                    changed = True
            new_keep.append(b)
        keep = sorted(set(new_keep))

    heights = h[keep].copy()
    for j, (a, b) in enumerate(pairwise(keep)):
        if b - a > 1:
            deficit, _ = _segment_errors(d, h, a, b)
            lift = max(float(deficit.max()), 0.0)
            heights[j] = max(heights[j], h[a] + lift)
            heights[j + 1] = max(heights[j + 1], h[b] + lift)
    if max_slope is not None and len(keep) > 1:
        heights = enforce_slope(d[keep], heights, max_slope)
    return keep, heights


def _segment_errors(d: FloatArray, h: FloatArray, a: int, b: int) -> tuple[FloatArray, FloatArray]:
    seg = np.arange(a, b + 1)
    line = np.interp(d[seg], [d[a], d[b]], [h[a], h[b]])
    return h[seg] - line, line - h[seg]
