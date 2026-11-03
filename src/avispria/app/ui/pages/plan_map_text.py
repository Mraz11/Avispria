# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The words, colours and icons of the drawing map (kept apart so ``plan_map`` stays short)."""

from __future__ import annotations

from avispria.core.shapes import Role

ROLE_LABELS = {
    Role.INSIDE: "Map inside it",
    Role.LEAVE_OUT: "Leave it out",
    Role.BAND: "Map a band around it (outside)",
    Role.CORRIDOR: "Map a strip along it",
}

ROLE_COLOURS = {
    Role.INSIDE: "#2D9A5B",
    Role.LEAVE_OUT: "#D1495B",
    Role.BAND: "#E08E2B",
    Role.CORRIDOR: "#2F7FD1",
}

KIND_ICONS = {
    "polygon": "polyline",
    "rectangle": "crop_square",
    "circle": "radio_button_unchecked",
    "line": "timeline",
}

HELP = (
    "Use the tools at the top left of the map: polygon, rectangle, circle, line, or the pin for "
    "the takeoff point. Each shape you draw appears in the list below with what it does. The "
    "area that will be planned is drawn in green."
)

BACKGROUND_NOTE = (
    "The background is OpenStreetMap, loaded from the internet only while this switch is on "
    "(their terms: openstreetmap.org/copyright). The map works without it: you then see only your "
    "shapes."
)

PRIVACY_NOTE = (
    "Searching for a place sends the words you typed to the search service (OpenStreetMap's, "
    "unless you give another address below), only when you press Search. 'My location' asks your "
    "browser, which may ask its own location service. Nothing else leaves this computer."
)

LEAVE_OUT_NOTE = (
    "Parts you leave out are not planned for coverage, but the aircraft may still fly over them to "
    "turn or to reach the next line. Do not rely on this for anything that must not be overflown."
)

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
)
