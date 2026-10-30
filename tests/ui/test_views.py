# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

from avispria.adapters.system_probe import EngineStatus
from avispria.app.doctor import DoctorReport
from avispria.app.ui.views import (
    explain_issues,
    feasibility_verdict,
    photos_that_fit,
    qa_tiles,
    qa_verdict,
    system_rows,
)
from avispria.app.ui.views_results import key_outputs, plan_verdict, process_tiles, process_verdict
from avispria.core.capture import CaptureReport
from avispria.core.feasibility import Assessment, SystemSpec
from avispria.core.safety import Issue

STATS = {
    "photos_total": 18.0,
    "photos_used": 18.0,
    "gsd_cm_median": 1.68,
    "altitude_m_median": 35.6,
    "terrain_aware": 1.0,
    "terrain_photos": 18.0,
    "min_views": 3,
    "good_views": 5,
    "area_pct_min_views": 100.0,
    "area_pct_good_views": 83.0,
    "interval_s_median": 7.0,
    "front_overlap_median": 0.64,
    "front_overlap_p10": 0.60,
    "side_overlap_median": 0.61,
    "side_overlap_p10": 0.56,
}


def report(issues: list[Issue] | None = None, **stats: float) -> CaptureReport:
    return CaptureReport((), issues or [], {**STATS, **stats})


def test_issues_are_grouped_by_code_and_errors_come_first() -> None:
    issues = [
        Issue("warning", "SAF008", "m1: planned without terrain data"),
        Issue("warning", "SAF008", "m2: planned without terrain data"),
        Issue("error", "SAF004", "waypoint 510 m from takeoff exceeds 500 m"),
        Issue("warning", "ZZZ001", "something unknown"),
    ]
    out = explain_issues(issues)
    assert [e.code for e in out] == ["SAF004", "SAF008", "ZZZ001"]
    assert out[0].level == "error" and out[0].title == "Too far from the takeoff point"
    assert out[1].count == 2 and out[1].detail.startswith("m1:") and out[1].action
    assert out[2].title == "Notice" and out[2].detail == "something unknown"


def test_qa_verdict_levels() -> None:
    assert qa_verdict(report()).level == "good"
    caution = qa_verdict(report([Issue("warning", "QA006", "x"), Issue("warning", "QA010", "y")]))
    assert caution.level == "caution" and "2 points" in caution.detail
    one = qa_verdict(report([Issue("warning", "QA003", "x")]))
    assert "1 point below" in one.detail
    bad = qa_verdict(
        report([Issue("error", "QA009", "only 0 usable nadir photo(s)")], photos_used=0.0)
    )
    assert bad.level == "problem" and bad.headline == "Not enough usable photos"
    assert (
        qa_verdict(report(photos_used=2.0)).level == "problem"
    )  # too few even without an error issue


def test_qa_tiles_describe_the_flight_in_plain_terms() -> None:
    tiles = {t.label: t for t in qa_tiles(report())}
    assert tiles["Photos checked"].value == "18 of 18"
    assert tiles["Height"].value == "36 m" and "above the surface" in tiles["Height"].hint
    assert tiles["Ground resolution"].value == "1.68 cm/px"
    assert tiles["Overlap"].value == "front 64%, side 61%" and tiles["Overlap"].hint.endswith(
        "60% / 56%"
    )
    assert (
        tiles["Area coverage"].value == "100% seen by 3+ photos"
        and "83% by 5+" in tiles["Area coverage"].hint
    )
    assert tiles["Photo interval"].value == "7.0 s"
    flat = {t.label: t for t in qa_tiles(report(terrain_aware=0.0))}
    assert "flat ground assumed" in flat["Height"].hint
    assert [
        t.label for t in qa_tiles(CaptureReport((), [], {"photos_used": 0, "photos_total": 5}))
    ] == ["Photos"]


def test_plan_verdict_separates_serious_notes_from_information() -> None:
    assert plan_verdict([]).level == "good"
    info = plan_verdict([Issue("warning", "AVI001", "x")])
    assert info.level == "good" and "1 note to read" in info.detail
    serious = plan_verdict([Issue("warning", "PL001", "x"), Issue("warning", "AVI001", "y")])
    assert serious.level == "caution" and "2 notes" in serious.detail


def doctor(
    ram: float = 16.0, swap: float = 12.0, disk: float = 115.0, engine: bool = True
) -> DoctorReport:
    spec = SystemSpec("Windows 11", 12, ram, ram * 0.3, swap, disk)
    engines = [EngineStatus("WebODM", "http://127.0.0.1:29800/", engine, "HTTP 200")]
    return DoctorReport(spec, engines, False, None, None, 0)


def test_system_rows_for_a_capable_computer() -> None:
    rows = {r.label: r for r in system_rows(doctor())}
    assert rows["Memory"].level == "good" and "GB (4.8 GB free right now)" in rows["Memory"].value
    assert (
        "Comfortable for about" in rows["Memory"].hint and "virtual memory" in rows["Memory"].hint
    )
    assert rows["Free disk space"].level == "good"
    assert (
        rows["Map-making engine"].level == "good"
        and rows["Map-making engine"].value == "WebODM is running"
    )


def test_system_rows_warn_about_small_computers_and_a_missing_engine() -> None:
    rows = {r.label: r for r in system_rows(doctor(ram=6.0, disk=12.0, engine=False))}
    assert rows["Memory"].level == "caution" and rows["Free disk space"].level == "problem"
    engine = rows["Map-making engine"]
    assert engine.level == "caution" and "webodm.org/download" in engine.hint
    assert system_rows(doctor(ram=3.0))[1].level == "problem"


def test_photos_that_fit_follows_the_opendronemap_table() -> None:
    assert photos_that_fit(4.0) == 40
    assert photos_that_fit(16.0) == 250
    assert photos_that_fit(3.9) == 0 or photos_that_fit(3.9) < 40
    assert photos_that_fit(32.0) == 500


def test_feasibility_verdict_words() -> None:
    def assessment(verdict: str) -> Assessment:
        return Assessment(verdict, 4.0, 20.0, 12.2, 10.0, ["close other programs"], [])  # type: ignore[arg-type]

    assert feasibility_verdict(assessment("ok")).level == "good"
    assert feasibility_verdict(assessment("slow")).level == "caution"
    no = feasibility_verdict(assessment("not-possible"))
    assert no.level == "problem" and "close other programs" in no.detail


PROVENANCE = {
    "status": "COMPLETED",
    "task": {"processing_s": 492.0},
    "reconstruction": {
        "photos_placed": 18,
        "photos_total": 18,
        "reprojection_px": 0.827,
        "gps_error_m": 0.664,
        "points": 1_412_664,
        "points_per_m2": 200.1,
        "area_m2": 7058.6,
        "gsd_cm_measured": 1.59,
        "issues": [],
    },
    "outputs": [
        {"file": "results/odm_orthophoto/odm_orthophoto.tif"},
        {"file": "results/odm_dem/dsm.tif"},
        {"file": "results/odm_georeferencing/odm_georeferenced_model.laz"},
        {"file": "results/odm_report/report.pdf"},
        {"file": "results/cameras.json"},
    ],
}


def test_process_results_in_plain_terms() -> None:
    assert process_verdict(PROVENANCE).level == "good"
    tiles = {t.label: t for t in process_tiles(PROVENANCE)}
    assert tiles["Processing time"].value == "8.2 min" and tiles["Photos used"].value == "18 of 18"
    assert (
        tiles["Fit of the 3D model"].value == "0.83 px"
        and tiles["Point cloud"].hint == "about 200 per m2"
    )
    assert tiles["Area covered"].value == "0.71 ha"
    noted = {
        **PROVENANCE,
        "reconstruction": {**PROVENANCE["reconstruction"], "issues": [{"code": "RQ004"}]},
    }
    assert process_verdict(noted).level == "caution"
    assert process_verdict({"status": "CANCELED"}).level == "caution"
    failed = process_verdict({"status": "FAILED", "error": "Process exited with code 1"})
    assert failed.level == "problem" and failed.detail == "Process exited with code 1"


def test_key_outputs_have_plain_labels_and_full_paths(tmp_path: Path) -> None:
    found = key_outputs(PROVENANCE, tmp_path)
    assert [label for label, _ in found] == [
        "Orthophoto (the map)",
        "Surface model (heights including trees and buildings)",
        "Point cloud",
        "Quality report from the engine",
    ]
    assert found[0][1] == tmp_path / "results/odm_orthophoto/odm_orthophoto.tif"
    assert json.dumps(PROVENANCE)  # plain data, as written to the provenance file


def test_the_engine_row_tells_three_situations_apart() -> None:
    from avispria.core.feasibility import SystemSpec  # noqa: F401  (doctor() builds the spec)

    nothing = {r.label: r for r in system_rows(doctor(engine=False))}["Map-making engine"]
    assert (
        nothing.value == "Not found"
        and "not only installed" in nothing.hint
        and "Check again" in nothing.hint
    )
    report = doctor(engine=False)
    report.programs.extend(["WebODM.exe", "nodeodx.exe"])
    hidden = {r.label: r for r in system_rows(report)}["Map-making engine"]
    assert hidden.level == "caution" and "running, but none is answering" in hidden.value
    assert "administrator" in hidden.hint and "wait until its dashboard opens" in hidden.hint
    up = {r.label: r for r in system_rows(doctor(engine=True))}["Map-making engine"]
    assert up.level == "good" and up.value == "WebODM is running"
