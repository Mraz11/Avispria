# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exception types shared across the core."""


class PlanningError(ValueError):
    """A mission cannot be planned safely from the given inputs."""
