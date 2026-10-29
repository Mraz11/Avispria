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
