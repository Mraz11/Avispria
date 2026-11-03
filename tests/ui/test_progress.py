# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest

from avispria.app.ui.progress import NextAction, Progress, current_progress, next_action, step_done
from avispria.app.ui.state import STATE


def test_a_new_project_starts_with_the_sample_mission_and_nothing_is_done() -> None:
    p = current_progress()
    assert p == Progress(False, 0, 0, False)
    action = next_action(p)
    assert action.step == 0 and "sample mission" in action.title and action.path == ""
    assert not any(step_done(n, p) for n in range(1, 6))


def test_the_next_action_follows_the_journey_one_step_at_a_time() -> None:
    sample = Progress(has_sample=True)
    planned = Progress(has_sample=True, planned=3)
    sent = Progress(has_sample=True, planned=3, sent=3)
    checked = Progress(has_sample=True, planned=3, sent=3, checked=True)
    steps = [next_action(p) for p in (sample, planned, sent, checked)]
    assert [a.step for a in steps] == [1, 2, 3, 5]
    assert [a.path for a in steps] == ["/plan", "/phone", "/fly", "/process"]
    assert steps[1].title == "Send your 3 missions to DJI Fly"
    assert (
        next_action(Progress(has_sample=True, planned=1)).title == "Send your 1 mission to DJI Fly"
    )
    assert all(isinstance(a, NextAction) and a.text.endswith(".") and a.button for a in steps)


def test_a_step_is_done_when_what_it_makes_exists() -> None:
    p = Progress(has_sample=True, planned=2, sent=2, checked=False)
    assert [step_done(n, p) for n in range(1, 6)] == [True, True, False, False, False]
    q = Progress(has_sample=True, planned=2, sent=2, checked=True)
    assert [step_done(n, q) for n in range(1, 6)] == [True, True, True, True, False]
    assert step_done(99, q) is False


def test_progress_is_read_from_what_the_screens_remember(tmp_path: Path) -> None:
    sample, plan_a, plan_b, photos = (tmp_path / n for n in ("s.kmz", "a.kmz", "b.kmz", "photos"))
    for f in (sample, plan_a, plan_b):
        f.write_bytes(b"x")
    photos.mkdir()
    STATE.sample_mission = str(sample)
    STATE.last_plan_files = [str(plan_a), str(plan_b)]
    STATE.last_sent_files = [str(plan_a)]
    STATE.photo_folder = str(photos)
    assert current_progress() == Progress(True, 2, 1, True)


@pytest.mark.parametrize("what", ["sample", "plan", "photos"])
def test_what_was_deleted_since_does_not_count(tmp_path: Path, what: str) -> None:
    sample, plan, photos = tmp_path / "s.kmz", tmp_path / "a.kmz", tmp_path / "photos"
    for f in (sample, plan):
        f.write_bytes(b"x")
    photos.mkdir()
    STATE.sample_mission, STATE.last_plan_files, STATE.photo_folder = (
        str(sample),
        [str(plan)],
        str(photos),
    )
    {"sample": sample, "plan": plan}.get(
        what, photos
    ).unlink() if what != "photos" else photos.rmdir()
    p = current_progress()
    assert {"sample": not p.has_sample, "plan": p.planned == 0, "photos": not p.checked}[what]
