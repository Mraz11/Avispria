# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import urllib.error
import urllib.parse

import pytest

from avispria.adapters.geocode import (
    CACHE_SECONDS,
    DEFAULT_SERVICE,
    MIN_INTERVAL_S,
    GeocodeError,
    Geocoder,
    Place,
    user_agent,
)

# Nominatim's documented answer: lat/lon as strings, boundingbox as [south, north, west, east]
MADHUPUR = {
    "place_id": 1,
    "lat": "24.6264",
    "lon": "90.0383",
    "display_name": "Madhupur, Tangail, Dhaka Division, Bangladesh",
    "boundingbox": ["24.5764", "24.6764", "89.9883", "90.0883"],
    "type": "town",
    "importance": 0.5,
}


class Service:
    """A fake search service that remembers what it was asked."""

    def __init__(self, answer: object = None) -> None:
        self.answer = [MADHUPUR] if answer is None else answer
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> bytes:
        self.calls.append((url, headers))
        if isinstance(self.answer, Exception):
            raise self.answer
        return json.dumps(self.answer).encode()


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make(service: Service, clock: Clock | None = None) -> tuple[Geocoder, Clock]:
    clock = clock or Clock()
    return Geocoder(fetch=service, clock=clock, sleep=clock.sleep), clock


def test_a_place_is_found_with_its_position_and_its_box() -> None:
    geocoder, _ = make(Service())
    (place,) = geocoder.search("Madhupur")
    assert place == Place(
        "Madhupur, Tangail, Dhaka Division, Bangladesh",
        24.6264,
        90.0383,
        (24.5764, 89.9883, 24.6764, 90.0883),
    )  # the box is (south, west, north, east)


def test_the_question_is_encoded_and_cannot_change_the_request() -> None:
    service = Service()
    geocoder, _ = make(service)
    geocoder.search("a&b=c#d %20 Dhaka", limit=3)
    url = service.calls[0][0]
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == DEFAULT_SERVICE
    assert query == {"q": ["a&b=c#d %20 Dhaka"], "format": ["jsonv2"], "limit": ["3"]}
    other = Service()
    make(other)[0].search("x", service="https://geo.example.org/search?key=K")
    assert other.calls[0][0].startswith("https://geo.example.org/search?key=K&q=x&")


def test_the_application_is_named_to_the_service() -> None:
    service = Service()
    make(service)[0].search("Dhaka")
    agent = service.calls[0][1]["User-Agent"]
    assert (
        agent == user_agent()
        and agent.startswith("Avispria/")
        and "github.com/Mraz11/Avispria" in agent
    )
    assert "python-urllib" not in agent.lower()  # the policy refuses a library's stock agent


def test_searches_are_at_least_a_second_apart_for_the_whole_application() -> None:
    geocoder, clock = make(Service())
    geocoder.search("Dhaka")
    assert clock.slept == []  # the first one goes straight away
    geocoder.search("Madhupur")  # straight after: it waits
    assert clock.slept == [pytest.approx(MIN_INTERVAL_S)]
    clock.now += 30.0
    geocoder.search("Sylhet")  # long after: no wait
    assert len(clock.slept) == 1 and MIN_INTERVAL_S > 1.0


def test_an_answer_is_remembered_for_an_hour_whatever_the_case_or_spacing() -> None:
    service = Service()
    geocoder, clock = make(service)
    first = geocoder.search("Madhupur  Forest")
    again = geocoder.search("madhupur forest")
    assert (
        len(service.calls) == 1 and again == first and again is not first
    )  # a copy, not the cache
    assert clock.slept == []  # a remembered answer does not even wait
    clock.now += CACHE_SECONDS + 1
    geocoder.search("Madhupur Forest")
    assert len(service.calls) == 2
    geocoder.search("Madhupur Forest", service="https://geo.example.org/search")  # another service
    assert len(service.calls) == 3


def test_no_result_is_an_empty_list_and_is_remembered_too() -> None:
    service = Service([])
    geocoder, _ = make(service)
    assert geocoder.search("zzzzqqq") == [] and geocoder.search("zzzzqqq") == []
    assert len(service.calls) == 1


def test_entries_that_make_no_sense_are_skipped_not_trusted() -> None:
    broken = [
        {"lat": "95", "lon": "10", "display_name": "off the map"},
        {"lat": "10", "lon": "190", "display_name": "off the map"},
        {"lat": "x", "lon": "10"},
        {"display_name": "no position"},
        "not an object",
        {"lat": "5", "lon": "6", "display_name": "bad box", "boundingbox": ["9", "1", "2", "3"]},
        {"lat": "7", "lon": "8", "boundingbox": ["a", "b", "c", "d"]},
    ]
    places = make(Service(broken))[0].search("anything")
    assert [(p.lat, p.lon, p.bbox) for p in places] == [(5.0, 6.0, None), (7.0, 8.0, None)]
    assert places[1].name == "7.00000, 8.00000"  # a place without a name is shown by its position


@pytest.mark.parametrize("limit", [0, 1, 5, 99])
def test_the_number_of_results_asked_for_is_kept_sensible(limit: int) -> None:
    service = Service([MADHUPUR] * 12)
    places = make(service)[0].search("x", limit=limit)
    asked = int(urllib.parse.parse_qs(urllib.parse.urlparse(service.calls[0][0]).query)["limit"][0])
    assert 1 <= asked <= 10 and len(places) <= max(limit, 0)


def http(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "no", {}, None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (http(429), "Too many searches"),
        (http(403), "refused this request"),
        (http(401), "refused this request"),
        (http(500), r"error \(500\)"),
        (urllib.error.URLError("no route"), "needs the internet"),
        (TimeoutError("slow"), "needs the internet"),
        (ConnectionResetError("reset"), "needs the internet"),
    ],
)
def test_every_way_the_service_can_fail_is_said_in_plain_words(
    failure: Exception, message: str
) -> None:
    with pytest.raises(GeocodeError, match=message):
        make(Service(failure))[0].search("Dhaka")


@pytest.mark.parametrize("body", [b"<html>", b'{"a": 1}', b"3", b"null", b"\xff\xfe"])
def test_an_answer_that_is_not_a_list_of_places_is_reported(body: bytes) -> None:
    geocoder = Geocoder(fetch=lambda *a: body, clock=Clock(), sleep=lambda s: None)
    with pytest.raises(GeocodeError, match="could not be read"):
        geocoder.search("Dhaka")


@pytest.mark.parametrize(
    ("query", "service", "message"),
    [
        ("", "", "Type the name of a place"),
        ("   ", "", "Type the name of a place"),
        ("x" * 201, "", "too long"),
        ("Dhaka", "ftp://example.org/search", "must start with https://"),
        ("Dhaka", "file:///etc/passwd", "must start with https://"),
        ("Dhaka", "javascript:alert(1)", "must start with https://"),
    ],
)
def test_a_search_that_cannot_be_asked_is_refused_before_anything_is_sent(
    query: str, service: str, message: str
) -> None:
    fake = Service()
    with pytest.raises(GeocodeError, match=message):
        make(fake)[0].search(query, service=service)
    assert fake.calls == []
