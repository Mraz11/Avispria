# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Height-profile shaping for terrain following.

DJI Fly flies a straight line between waypoint heights, so the required profile
must be represented by a set of waypoints whose straight segments never dip
below it.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable

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
    d: FloatArray, h_req: FloatArray, mandatory: Iterable[int], max_excess_m: float
) -> list[int]:
    """Choose sample indices to keep as waypoints.

    Guarantees, for every sample between kept points, that the straight line
    between them is never below ``h_req`` and never more than ``max_excess_m``
    above it. The first and last samples and all ``mandatory`` indices are kept.
    """
    d = np.asarray(d, dtype=float)
    h = np.asarray(h_req, dtype=float)
    _check(d, h)
    if max_excess_m <= 0:
        raise ValueError("max_excess_m must be positive")
    n = len(d)
    keep = sorted({0, n - 1, *(int(i) for i in mandatory)})
    if keep[0] < 0 or keep[-1] > n - 1:
        raise ValueError("mandatory index out of range")
    changed = True
    while changed:
        changed = False
        new_keep = [keep[0]]
        for a, b in itertools.pairwise(keep):
            if b - a > 1:
                seg = np.arange(a, b + 1)
                line = np.interp(d[seg], [d[a], d[b]], [h[a], h[b]])
                deficit = h[seg] - line
                excess = line - h[seg]
                k_def = int(np.argmax(deficit))
                k_exc = int(np.argmax(excess))
                if deficit[k_def] > 1e-9:
                    new_keep.append(a + k_def)
                    changed = True
                elif excess[k_exc] > max_excess_m:
                    new_keep.append(a + k_exc)
                    changed = True
            new_keep.append(b)
        keep = sorted(set(new_keep))
    return keep
