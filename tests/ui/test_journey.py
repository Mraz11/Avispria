# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
from types import SimpleNamespace

import pytest
from nicegui.testing import User

from avispria.app.ui.journey import STEPS, TOTAL, nav_items, nav_label, step_for
from avispria.app.ui.state import STATE

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]

ORDER = ["/plan", "/phone", "/fly", "/check", "/process"]


def test_the_journey_is_in_the_order_a_project_goes() -> None:
    assert [s.path for s in STEPS] == ORDER and [s.number for s in STEPS] == [1, 2, 3, 4, 5]
    assert TOTAL == 5
    assert [s.title for s in STEPS] == [
        "Plan a flight",
        "Send to DJI Fly",
        "Fly",
        "Check my photos",
        "Make maps",
    ]
    assert nav_items()[0] == ("Start", "/")
    assert [label for label, _ in nav_items()[1:]] == [
        "1. Plan a flight",
        "2. Send to DJI Fly",
        "3. Fly",
        "4. Check my photos",
        "5. Make maps",
    ]
    assert (
        step_for("Fly") is STEPS[2] and step_for("Start") is None and step_for("nonsense") is None
    )
    assert all(s.what.strip().endswith(".") for s in STEPS)


@pytest.mark.parametrize("path", ORDER)
async def test_every_step_says_which_step_it_is_what_to_do_and_what_comes_next(
    user: User, path: str
) -> None:
    step = next(s for s in STEPS if s.path == path)
    await user.open(path)
    await user.should_see(f"Step {step.number} of 5")
    await user.should_see(step.what)
    user.find(marker="journey-bar")
    if step.number > 1:
        await user.should_see(f"Before: {nav_label(STEPS[step.number - 2])}")
    if step.number < TOTAL:
        await user.should_see(f"Next: {nav_label(STEPS[step.number])}")
        await user.should_see("When you are done here")
        user.find(marker="next-step-button")
    else:
        await user.should_see("That is the whole journey")
        await user.should_see("Start a new flight")


@pytest.mark.parametrize("index", range(4))
async def test_the_next_step_button_goes_to_the_next_screen(user: User, index: int) -> None:
    await user.open(ORDER[index])
    user.find(marker="next-step-button").click()
    await user.should_see(f"Step {index + 2} of 5", retries=100)


async def test_the_last_step_leads_back_to_planning_a_new_flight(user: User) -> None:
    await user.open("/process")
    user.find(marker="next-step-button").click()
    await user.should_see("Step 1 of 5", retries=100)


async def test_the_top_bar_has_every_step_and_marks_only_the_current_one(user: User) -> None:
    from nicegui import ui

    labels = {
        "Start",
        "1. Plan a flight",
        "2. Send to DJI Fly",
        "3. Fly",
        "4. Check my photos",
        "5. Make maps",
    }
    await user.open("/fly")
    bar = [e for e in user.find(kind=ui.link).elements if "av-nav" in e.classes]
    assert {e.text for e in bar} == labels  # in this order in the program: see the data test above
    assert [e.text for e in bar if "av-nav-active" in e.classes] == ["3. Fly"]
    await user.open("/")
    bar = [e for e in user.find(kind=ui.link).elements if "av-nav" in e.classes]
    assert [e.text for e in bar if "av-nav-active" in e.classes] == ["Start"]


async def test_the_start_page_is_the_journey_with_a_place_to_start(user: User) -> None:
    await user.open("/")
    await user.should_see("A flight project has five steps. Do them in this order.")
    for step in STEPS:
        await user.should_see(step.title)
        await user.should_see(step.what)
        user.find(marker=f"open-{step.path.strip('/')}")
    await user.should_see("Start here")
    await user.should_see("Go: 1. Plan a flight")
    user.find(marker="open-plan").click()
    await user.should_see("Step 1 of 5", retries=100)


async def test_the_fly_screen_says_what_to_check_and_what_to_do_afterwards(user: User) -> None:
    STATE.last_plan_files = ["a.kmz", "b.kmz", "c.kmz"]
    await user.open("/fly")
    await user.should_see("Your last plan has 3 missions.")
    for text in (
        "Before you leave",
        "If DJI Fly shows different numbers",
        "Global Speed",
        "avispria inspect",
        "At the site",
        "After landing",
        "spot-check sheet",
        "ONE folder",
        "mraz11.github.io/Avispria",
    ):
        await user.should_see(text)
    STATE.last_plan_files = ["a.kmz"]
    await user.open("/fly")
    await user.should_see("Your last plan has 1 mission.")
    STATE.last_plan_files = []
    await user.open("/fly")
    await user.should_not_see("Your last plan has")


def remember(
    tmp_path: Path, *, sample: bool = False, planned: int = 0, sent: int = 0, checked: bool = False
) -> None:
    """Put the project in a state, the way the screens leave it."""
    if sample:
        (tmp_path / "sample.kmz").write_bytes(b"x")
        STATE.sample_mission = str(tmp_path / "sample.kmz")
    plans = []
    for n in range(planned):
        f = tmp_path / f"survey_0{n + 1}.kmz"
        f.write_bytes(b"x")
        plans.append(str(f))
    STATE.last_plan_files = plans
    STATE.last_sent_files = plans[:sent]
    if checked:
        (tmp_path / "photos").mkdir()
        STATE.photo_folder = str(tmp_path / "photos")


async def test_a_new_project_starts_with_the_sample_mission_right_on_the_start_page(
    user: User,
) -> None:
    await user.open("/")
    await user.should_see("Your next step")
    await user.should_see("First, once: get your sample mission from the phone")
    user.find(marker="sample-from-phone")  # the action is here, not on another screen
    with pytest.raises(AssertionError):
        user.find(marker="next-action-button")
    await user.should_see("Start here")


async def test_getting_the_sample_on_the_start_page_moves_on_to_planning(
    user: User, fake_phone: SimpleNamespace
) -> None:
    await user.open("/")
    user.find(marker="sample-from-phone").click()
    await user.should_see("Plan your flight", retries=200)
    user.find(marker="next-action-button")
    user.find(marker="next-action-button").click()
    await user.should_see("Step 1 of 5", retries=100)


@pytest.mark.parametrize(
    ("state", "title", "step_done", "step_next"),
    [
        ({"sample": True}, "Plan your flight", [], 1),
        ({"sample": True, "planned": 3}, "Send your 3 missions to DJI Fly", [1], 2),
        ({"sample": True, "planned": 3, "sent": 3}, "Fly, then check your photos", [1, 2], 3),
        (
            {"sample": True, "planned": 3, "sent": 3, "checked": True},
            "Make your map or 3D model",
            [1, 2, 3, 4],
            5,
        ),
    ],
    ids=["planned nothing", "planned", "sent", "checked"],
)
async def test_the_start_page_always_says_the_one_next_thing_and_marks_what_is_done(
    user: User,
    tmp_path: Path,
    state: dict,
    title: str,
    step_done: list,
    step_next: int,  # type: ignore[type-arg]
) -> None:
    remember(tmp_path, **state)
    await user.open("/")
    await user.should_see(title)
    for n in range(1, 6):
        card = next(iter(user.find(marker=f"step-{n}").elements))
        assert ("av-note-info" in card.classes) == (
            n == step_next
        )  # only the next one is highlighted
    if step_done:
        await user.should_see("Done")
        await user.should_see("Do this next" if step_next != 1 else "Start here")


async def test_the_next_button_goes_to_the_screen_it_names(user: User, tmp_path: Path) -> None:
    remember(tmp_path, sample=True, planned=2)
    await user.open("/")
    await user.should_see("Next: 2. Send to DJI Fly")
    user.find(marker="next-action-button").click()
    await user.should_see("Step 2 of 5", retries=100)
    await user.should_see("Before you send")


async def test_the_step_chips_show_what_is_done_where_you_are_and_what_is_left(
    user: User, tmp_path: Path
) -> None:
    remember(tmp_path, sample=True, planned=2)
    await user.open("/phone")
    icon = lambda n: next(iter(user.find(marker=f"chip-{n}").elements)).props["icon"]  # noqa: E731
    assert [icon(n) for n in range(1, 6)] == [
        "check_circle",
        "radio_button_checked",
        "radio_button_unchecked",
        "radio_button_unchecked",
        "radio_button_unchecked",
    ]
    user.find(marker="chip-5").click()  # a chip is a way to go to that step
    await user.should_see("Step 5 of 5", retries=100)
