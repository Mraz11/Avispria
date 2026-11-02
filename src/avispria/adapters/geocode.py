# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Find a place by name, through a Nominatim-compatible search service.

The default is OpenStreetMap's public service, whose usage policy (operations.osmfoundation.org/
policies/nominatim/) is followed here: at most one request per second for the whole application, a
User-Agent that names this application, answers cached, no search-as-you-type (the caller searches
only when the person presses a button), and the OpenStreetMap credit shown wherever results are. The
service address can be changed to another Nominatim-compatible one (your own, or a commercial one)
without a new version of the program.

Only the text the person typed is sent. Nothing is sent unless they search.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from avispria import __version__

DEFAULT_SERVICE = "https://nominatim.openstreetmap.org/search"
PROJECT_URL = "https://github.com/Mraz11/Avispria"
MIN_INTERVAL_S = 1.1  # the policy allows one request a second; stay clear of it
CACHE_SECONDS = 3600.0
MAX_QUERY_CHARS = 200


class GeocodeError(RuntimeError):
    """The search could not be done; the message says what to do about it."""


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float
    bbox: tuple[float, float, float, float] | None = None  # (south, west, north, east)


Fetch = Callable[[str, dict[str, str], float], bytes]


def user_agent() -> str:
    return f"Avispria/{__version__} (+{PROJECT_URL})"


def _fetch(url: str, headers: dict[str, str], timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data: bytes = response.read(1_000_000)
    return data


def _check_service(service: str) -> str:
    text = service.strip()
    if not text.lower().startswith(("https://", "http://")):
        raise GeocodeError("The search service address must start with https:// (or http://).")
    return text


def _place(raw: object) -> Place | None:
    if not isinstance(raw, dict):
        return None
    try:
        lat, lon = float(raw["lat"]), float(raw["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    bbox = None
    box = raw.get("boundingbox")
    if isinstance(box, list) and len(box) == 4:
        try:
            south, north, west, east = (float(v) for v in box)  # Nominatim's order
            if south <= north and west <= east:
                bbox = (south, west, north, east)
        except (TypeError, ValueError):
            bbox = None
    name = str(raw.get("display_name") or f"{lat:.5f}, {lon:.5f}")
    return Place(name, lat, lon, bbox)


class Geocoder:
    """One per application: it owns the pace and the cache that the usage policy asks for."""

    def __init__(
        self,
        fetch: Fetch = _fetch,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = 8.0,
    ) -> None:
        self._fetch, self._clock, self._sleep, self._timeout = fetch, clock, sleep, timeout_s
        self._lock = threading.Lock()
        self._last_request: float | None = None
        self._cache: dict[tuple[str, str], tuple[float, list[Place]]] = {}

    def search(self, query: str, service: str = "", limit: int = 5) -> list[Place]:
        text = " ".join(query.split())
        if not text:
            raise GeocodeError("Type the name of a place, like 'Madhupur' or 'Dhaka university'.")
        if len(text) > MAX_QUERY_CHARS:
            raise GeocodeError("That search text is too long.")
        address = _check_service(service or DEFAULT_SERVICE)
        key = (address, text.lower())
        with self._lock:
            now = self._clock()
            cached = self._cache.get(key)
            if cached is not None and now - cached[0] < CACHE_SECONDS:
                return list(cached[1])
            if self._last_request is not None:
                wait = MIN_INTERVAL_S - (now - self._last_request)
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()
            places = self._ask(address, text, limit)
            self._cache[key] = (self._clock(), places)
            if len(self._cache) > 200:
                self._cache.pop(next(iter(self._cache)))
        return list(places)

    def _ask(self, address: str, text: str, limit: int) -> list[Place]:
        separator = "&" if "?" in address else "?"
        url = (
            address
            + separator
            + urllib.parse.urlencode(
                {"q": text, "format": "jsonv2", "limit": max(1, min(limit, 10))}
            )
        )
        headers = {"User-Agent": user_agent(), "Accept": "application/json"}
        try:
            body = self._fetch(url, headers, self._timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise GeocodeError("Too many searches: wait a minute and try again.") from exc
            if exc.code in (401, 403):
                raise GeocodeError(
                    "The search service refused this request. If it keeps happening, give a "
                    "different search service address in the map settings."
                ) from exc
            raise GeocodeError(f"The search service answered with an error ({exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GeocodeError(
                "The search needs the internet and the service could not be reached."
            ) from exc
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise GeocodeError("The search service gave an answer that could not be read.") from exc
        if not isinstance(data, list):
            raise GeocodeError("The search service gave an answer that could not be read.")
        return [p for p in (_place(item) for item in data) if p is not None][:limit]


DEFAULT = Geocoder()


def search_places(query: str, service: str = "", limit: int = 5) -> list[Place]:
    """Search with the application-wide geocoder (one pace and one cache for every screen)."""
    return DEFAULT.search(query, service, limit)
