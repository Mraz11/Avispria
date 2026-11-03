# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest

from avispria.app.ui import state
from avispria.app.ui.state import PERSISTED, STATE, settings_path


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    made = {
        "sample": tmp_path / "sample.kmz",
        "plan_a": tmp_path / "survey_01.kmz",
        "plan_b": tmp_path / "survey_02.kmz",
    }
    for path in made.values():
        path.write_bytes(b"x")
    made["photos"] = tmp_path / "photos"
    made["photos"].mkdir()
    return made


def test_nothing_is_written_until_the_program_has_started_remembering() -> None:
    STATE.sample_mission = "/somewhere/sample.kmz"
    assert not settings_path().exists()


def test_what_is_set_after_loading_is_remembered_for_the_next_run(files: dict[str, Path]) -> None:
    STATE.load()
    STATE.sample_mission = str(files["sample"])
    STATE.adb_path = "C:/platform-tools"
    STATE.last_plan_files = [str(files["plan_a"]), str(files["plan_b"])]
    STATE.last_sent_files = [str(files["plan_a"])]
    STATE.photo_folder = str(files["photos"])
    saved = json.loads(settings_path().read_text())
    assert set(saved) == set(PERSISTED)  # only these, and only paths
    state.reset()
    assert STATE.sample_mission == "" and STATE.last_plan_files == []
    STATE.load()  # the next run
    assert STATE.sample_mission == str(files["sample"]) and STATE.adb_path == "C:/platform-tools"
    assert STATE.last_plan_files == [str(files["plan_a"]), str(files["plan_b"])]
    assert STATE.last_sent_files == [str(files["plan_a"])] and STATE.photo_folder == str(
        files["photos"]
    )


def test_files_and_folders_that_are_gone_are_forgotten_not_offered(files: dict[str, Path]) -> None:
    STATE.load()
    STATE.sample_mission = str(files["sample"])
    STATE.last_plan_files = [str(files["plan_a"]), str(files["plan_b"])]
    STATE.photo_folder = str(files["photos"])
    files["sample"].unlink()
    files["plan_b"].unlink()
    files["photos"].rmdir()
    state.reset()
    STATE.load()
    assert STATE.sample_mission == "" and STATE.photo_folder == ""
    assert STATE.last_plan_files == [str(files["plan_a"])]


@pytest.mark.parametrize(
    "content", ["", "not json", "[1, 2]", '{"sample_mission": 5, "last_plan_files": "x"}', "\x00"]
)
def test_a_damaged_settings_file_is_ignored(content: str) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True)
    path.write_text(content)
    STATE.load()
    assert STATE.sample_mission == "" and STATE.last_plan_files == [] and STATE.adb_path == ""


def test_a_settings_folder_that_cannot_be_written_never_stops_the_program(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocker = tmp_path / "file-not-folder"
    blocker.write_text("x")
    monkeypatch.setenv("AVISPRIA_SETTINGS", str(blocker / "settings.json"))
    STATE.load()
    STATE.adb_path = "C:/tools"  # no exception
    assert STATE.adb_path == "C:/tools"


def test_fields_that_are_not_remembered_do_not_trigger_saving() -> None:
    STATE.load()
    assert not settings_path().exists()
    STATE.some_other_attribute = 1  # type: ignore[attr-defined]
    assert not settings_path().exists()


def test_the_default_place_is_the_avispria_folder_in_the_home_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AVISPRIA_SETTINGS")
    assert settings_path() == Path.home() / "Avispria" / "settings.json"
