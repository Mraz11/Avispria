# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import box

from avispria.adapters.engine import EngineError
from avispria.app.process_workflow import ProcessBlockedError
from avispria.app.ui import files
from avispria.app.ui.charts import photo_map, route_map
from avispria.app.ui.jobs import QueueReporter, friendly_error
from avispria.core.camera import CameraProfile
from avispria.core.capture import CaptureReport, PhotoQa
from avispria.core.errors import PlanningError
from avispria.core.mission import PhotoMode
from avispria.core.planner import PlanRequest, plan
from avispria.core.safety import Issue, SafetyLimits

CAM = CameraProfile("c", 8.97, 6.72, 6.72, 4032, 3024, min_interval_s=2.0, readout_s=0.03)


# ---------------------------------------------------------------- charts
def test_photo_map_is_centred_square_and_coloured_by_overlap() -> None:
    photos = tuple(
        PhotoQa(
            f"P{i}.JPG",
            500_000.0 + 30 * i,
            5_700_000.0 + 10 * i,
            0.02,
            None,
            None,
            0.5 + 0.02 * i,
            None,
        )
        for i in range(6)
    )
    chart = photo_map(CaptureReport(photos, [], {}))
    data = chart["series"][0]["data"]
    assert [d["name"] for d in data] == [f"P{i}.JPG" for i in range(6)]
    assert sum(d["value"][0] for d in data) == pytest.approx(0.0, abs=0.5)  # centred on the photos
    assert data[3]["value"][2] == pytest.approx(0.56)
    xs, ys = chart["xAxis"], chart["yAxis"]
    assert xs["max"] - xs["min"] == pytest.approx(ys["max"] - ys["min"])  # equal scales
    assert chart["visualMap"]["dimension"] == 2
    assert photo_map(CaptureReport((), [], {})) == {}


def make_result():  # type: ignore[no-untyped-def]
    aoi = box(90.400, 23.800, 90.4015, 23.8012)
    return aoi, plan(
        PlanRequest(
            aoi=aoi,
            camera=CAM,
            drone_max_speed_ms=12.0,
            takeoff_lon=90.4005,
            takeoff_lat=23.8004,
            agl_m=40.0,
            flat_terrain=True,
            photo_mode=PhotoMode.WAYPOINT,
            shutter_s=1 / 2000,
            limits=SafetyLimits(max_waypoints=500),
        )
    )


def test_route_map_has_the_area_each_mission_and_the_takeoff() -> None:
    aoi, result = make_result()
    chart = route_map(result, aoi, (90.4005, 23.8004), photos=[(90.4004, 23.8003)] * 3)
    names = [s["name"] for s in chart["series"]]
    assert names[0] == "Survey area" and "Takeoff" in names and "Photos" in names
    assert names.count("Mission 1") == 1 and len(
        [n for n in names if n.startswith("Mission")]
    ) == len(result.missions)
    outline = chart["series"][0]["data"]
    assert outline[0] == outline[-1]  # closed polygon
    xs, ys = chart["xAxis"], chart["yAxis"]
    assert xs["max"] - xs["min"] == pytest.approx(ys["max"] - ys["min"])
    everything = [p for s in chart["series"] for p in s["data"]]
    assert all(
        xs["min"] <= p[0] <= xs["max"] and ys["min"] <= p[1] <= ys["max"] for p in everything
    )
    assert json.dumps(chart)  # plain data a browser chart can use


def test_route_map_thins_out_very_many_photo_dots() -> None:
    aoi, result = make_result()
    chart = route_map(result, aoi, (90.4005, 23.8004), photos=[(90.4004, 23.8003)] * 5000)
    dots = next(s for s in chart["series"] if s["name"] == "Photos")
    assert len(dots["data"]) <= 600


# ----------------------------------------------------------------- files
def test_list_entries_orders_filters_and_hides(tmp_path: Path) -> None:
    (tmp_path / "zeta").mkdir()
    (tmp_path / "Alpha").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "$Recycle").mkdir()
    (tmp_path / "b.KMZ").write_bytes(b"")
    (tmp_path / "a.geojson").write_bytes(b"")
    (tmp_path / ".secret.kmz").write_bytes(b"")
    names = [e.name for e in files.list_entries(tmp_path)]
    assert names == ["Alpha", "zeta", "a.geojson", "b.KMZ"]  # folders first, case-insensitive
    assert [e.name for e in files.list_entries(tmp_path, suffixes=(".kmz",))] == [
        "Alpha",
        "zeta",
        "b.KMZ",
    ]
    assert [e.name for e in files.list_entries(tmp_path, directories_only=True)] == [
        "Alpha",
        "zeta",
    ]


def test_list_entries_survives_unreadable_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny(self: Path) -> None:
        raise PermissionError("no")

    monkeypatch.setattr(Path, "iterdir", deny)
    assert files.list_entries(tmp_path) == []


def test_start_folder_falls_back_to_the_nearest_existing_parent(tmp_path: Path) -> None:
    deep = tmp_path / "no" / "such" / "place"
    assert files.start_folder(deep) == tmp_path
    assert files.start_folder(tmp_path) == tmp_path
    assert files.start_folder(None) == Path.home()
    assert files.start_folder("") == Path.home()


@pytest.mark.skipif(sys.platform == "win32", reason="drive letters exist on Windows only")
def test_no_windows_drives_elsewhere() -> None:
    assert files.windows_drives() == []


def test_open_in_file_manager_uses_the_folder_of_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[Path] = []
    monkeypatch.setattr(files.os, "startfile", lambda p: opened.append(Path(p)), raising=False)
    monkeypatch.setattr(files.subprocess, "run", lambda cmd, **kw: opened.append(Path(cmd[1])))
    target = tmp_path / "map.tif"
    target.write_bytes(b"")
    assert files.open_in_file_manager(target) is True
    assert files.open_in_file_manager(tmp_path) is True
    assert opened == [tmp_path, tmp_path]


# ------------------------------------------------------------------ jobs
def test_queue_reporter_passes_events_between_threads_in_order() -> None:
    rep = QueueReporter()
    rep.step("Uploading")
    rep.upload(40.0)
    rep.info("hello")
    rep.warn("careful")
    rep.progress(75.0, "RUNNING")
    events = rep.drain()
    assert [(e.kind, e.text, e.percent) for e in events] == [
        ("step", "Uploading", 0.0),
        ("upload", "", 40.0),
        ("info", "hello", 0.0),
        ("warn", "careful", 0.0),
        ("progress", "running", 75.0),
    ]
    assert rep.drain() == []


def test_friendly_errors() -> None:
    assert friendly_error(PlanningError("terrain data required")) == "terrain data required"
    assert friendly_error(EngineError("cannot reach the processing engine")).startswith(
        "cannot reach"
    )
    assert friendly_error(ProcessBlockedError("found 3 photo(s)")) == "found 3 photo(s)"
    assert "was not found" in friendly_error(FileNotFoundError(2, "No such file", "x.kmz"))
    assert "not allowed" in friendly_error(PermissionError(13, "denied", "locked"))
    assert friendly_error(OSError("disk full")).startswith("A file could not be read")
    odd = friendly_error(KeyError("boom"))
    assert odd.startswith("Something unexpected went wrong (KeyError)")
    assert friendly_error(Issue("error", "X", "y")).startswith("Something unexpected")  # type: ignore[arg-type]


def test_charts_take_their_colours_from_the_palette() -> None:
    from avispria.app.ui.theme import DARK, LIGHT

    photos = tuple(
        PhotoQa(f"P{i}.JPG", 500_000.0 + 30 * i, 5_700_000.0, 0.02, None, None, 0.6, None)
        for i in range(4)
    )
    report = CaptureReport(photos, [], {})
    for palette in (LIGHT, DARK):
        chart = photo_map(report, palette)
        assert chart["visualMap"]["inRange"]["color"] == list(palette.ramp)
        assert chart["xAxis"]["nameTextStyle"]["color"] == palette.muted
        assert chart["xAxis"]["splitLine"]["lineStyle"]["color"] == palette.border
        assert chart["backgroundColor"] == "transparent"  # the card shows through
    aoi, result = make_result()
    for palette in (LIGHT, DARK):
        route = route_map(
            result, aoi, (90.4005, 23.8004), photos=[(90.4004, 23.8003)], palette=palette
        )
        series = {s["name"]: s for s in route["series"]}
        assert series["Survey area"]["lineStyle"]["color"] == palette.outline
        assert series["Mission 1"]["lineStyle"]["color"] == palette.missions[0]
        assert series["Photos"]["itemStyle"]["color"] == palette.points
        assert series["Takeoff"]["itemStyle"]["color"] == palette.marker
        assert route["legend"]["textStyle"]["color"] == palette.text
    dark_route = route_map(
        result, aoi, (90.4005, 23.8004), photos=[(90.4004, 23.8003)], palette=DARK
    )
    assert {s["name"]: s for s in dark_route["series"]}["Survey area"]["lineStyle"][
        "color"
    ] == "#00B4D8"  # Bright Cyan
