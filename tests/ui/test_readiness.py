# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime

from avispria.app.phone_workflow import Slot
from avispria.app.ui.phone_job import PhoneStatus
from avispria.app.ui.readiness import placeholders_missing, readiness, usable_slots


def slot(n: int, waypoints: int = 2) -> Slot:
    return Slot(
        guid=f"{n:08X}-0000-0000-0000-000000000000",
        waypoints=waypoints,
        created=datetime(2026, 11, 3, 10, n),
        updated=None,
        preview=None,
        last_sent=None,
    )


def phone(slots: list[Slot], serial: str | None = "ABC", problem: str | None = None) -> PhoneStatus:
    return PhoneStatus(
        serial=serial, model="Redmi 2510DRK44C" if serial else "", slots=slots, problem=problem
    )


def test_everything_in_place_is_three_ticks() -> None:
    checks = readiness(phone([slot(1), slot(2), slot(3)]), ["a.kmz", "b.kmz"])
    assert [c.ok for c in checks] == [True, True, True]
    assert checks[0].text == "Your last plan has 2 missions to send."
    assert checks[1].text == "Phone connected: Redmi 2510DRK44C."
    assert checks[2].text == "DJI Fly has 3 missions that can be replaced: enough for your plan."


def test_too_few_placeholder_missions_says_exactly_how_many_to_make() -> None:
    checks = readiness(phone([slot(1)]), ["a.kmz", "b.kmz", "c.kmz"])
    assert [c.ok for c in checks] == [True, True, False]
    assert checks[2].text == "DJI Fly has 1 mission that can be replaced, but your plan has 3."
    assert checks[2].fix.startswith("Make 2 more.") and "Waypoint Flight" in checks[2].fix
    assert checks[2].fix.endswith("Then press Check again.")
    assert placeholders_missing(["a", "b", "c"], [slot(1)]) == 2


def test_a_mission_avispria_cannot_read_is_never_counted_as_a_place_to_send() -> None:
    slots = [
        slot(1),
        slot(2, waypoints=0),
        slot(3, waypoints=0),
    ]  # the leftover folder with no mission
    assert [s.guid[:8] for s in usable_slots(slots)] == ["00000001"]
    assert placeholders_missing(["a", "b"], slots) == 1
    assert "has 1 mission that can be replaced" in readiness(phone(slots), ["a", "b"])[2].text


def test_no_plan_yet_points_to_step_one_and_still_checks_the_phone() -> None:
    checks = readiness(phone([slot(1)]), [])
    assert not checks[0].ok and "step 1" in checks[0].fix
    assert checks[2].ok and checks[2].text.endswith("enough for one mission.")
    none = readiness(phone([]), [])
    assert (
        not none[2].ok
        and "at least one is needed" in none[2].text
        and none[2].fix.startswith("Make 1 more.")
    )


def test_no_phone_explains_what_is_wrong_in_the_phones_own_words_and_stops_there() -> None:
    checks = readiness(
        phone([], serial=None, problem="The phone is not allowed yet: tap Allow."), ["a"]
    )
    assert [c.ok for c in checks] == [True, False] and len(checks) == 2
    assert checks[1].fix == "The phone is not allowed yet: tap Allow."
    plain = readiness(phone([], serial=None), ["a"])
    assert "USB cable" in plain[1].fix


def test_a_phone_without_a_name_is_still_a_phone() -> None:
    status = PhoneStatus(serial="X", model="", slots=[slot(1)])
    assert readiness(status, ["a"])[1].text == "Phone connected: Android phone."
