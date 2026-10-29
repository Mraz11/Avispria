# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.app.ui.inputs import parse_latlon_text


@pytest.mark.parametrize(
    "text",
    [
        "23.8290, 90.4170",
        "23.8290,90.4170",
        " 23.8290   90.4170 ",
        "23.8290; 90.4170",
        "23.8290\N{DEGREE SIGN} 90.4170",
    ],
)
def test_latitude_and_longitude_are_read_flexibly(text: str) -> None:
    assert parse_latlon_text(text) == (23.8290, 90.4170)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "two numbers"),
        ("23.8", "two numbers"),
        ("23.8, 90.4, 12", "two numbers"),
        ("north, east", "two numbers"),
        ("95, 10", "Latitude 95 is not between"),
        ("10, 190", "Longitude 190 is not between"),
        ("90.4170, 23.8290", "Latitude comes first"),  # the usual mix-up: longitude typed first
    ],
)
def test_bad_coordinates_say_what_to_do(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_latlon_text(text)


@pytest.mark.parametrize(
    ("text", "seconds"), [("1/1000", 0.001), (" 1/2000 ", 0.0005), ("0.004", 0.004), ("1/1", 1.0)]
)
def test_shutter_times(text: str, seconds: float) -> None:
    from avispria.app.ui.inputs import parse_shutter_text

    assert parse_shutter_text(text) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["", "fast", "1/0", "0", "-1/1000", "5", "1/"])
def test_bad_shutter_times(text: str) -> None:
    from avispria.app.ui.inputs import parse_shutter_text

    with pytest.raises(ValueError, match="like 1/1000"):
        parse_shutter_text(text)
