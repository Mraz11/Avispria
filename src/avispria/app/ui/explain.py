# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plain-language explanations for every warning and error code Avispria can raise.

Each entry says what happened in everyday words, and what to do about it. A test scans
the source for code literals and fails if one has no explanation, so none is forgotten.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Explanation:
    title: str
    meaning: str
    action: str


def _e(title: str, meaning: str, action: str) -> Explanation:
    return Explanation(title, meaning, action)


_FILE = "Re-create the file with Avispria from your own DJI Fly mission file. If it keeps failing, send the file to the developers."

EXPLANATIONS: dict[str, Explanation] = {
    # ---- checking photos
    "QA001": _e(
        "Camera not pointing straight down",
        "Some photos were taken at an angle. They are left out of the overlap and resolution checks.",
        "For mapping, set the camera angle to -90 degrees (straight down) before the flight.",
    ),
    "QA002": _e(
        "Photos may be blurred by movement",
        "At this speed and exposure time the drone moves more than about one pixel while the picture is taken.",
        "Fly more slowly, or use a faster shutter (shorter exposure time). Bright light helps.",
    ),
    "QA003": _e(
        "Resolution varies across the flight",
        "The height above the ground changes by more than about 5%, so some photos are sharper than others.",
        "That is normal over hills. Over flat ground fly at a steady height; over hills use terrain following (add an elevation model when planning).",
    ),
    "QA005": _e(
        "Gap in the photo sequence",
        "The time between two photos was much longer than usual, so photos may be missing there.",
        "Check that the camera kept shooting. If the gap crosses your survey area, fly that part again.",
    ),
    "QA006": _e(
        "Too little overlap for reliable 3D",
        "Not enough of the area is seen by at least five photos, so the 3D model may be weak or have holes.",
        "Next time fly with about 80% forward and 70% sideways overlap, or add a second set of lines across the first.",
    ),
    "QA007": _e(
        "Some photos have no position",
        "Photos without a GPS position or height cannot be checked and are skipped here.",
        "Turn location tagging on in the camera. Photos without a position can still be processed, but less reliably.",
    ),
    "QA008": _e(
        "Different camera than expected",
        "The photos come from a different camera than the aircraft you selected.",
        "Select the right aircraft, or leave it empty so the camera is read from the photos.",
    ),
    "QA009": _e(
        "Not enough usable photos",
        "At least three photos that look straight down and carry a position are needed.",
        "Check that you chose the right folder and that the photos still contain their position data (original files, not edited copies).",
    ),
    "QA010": _e(
        "Little overlap between neighbouring photos",
        "Some photos overlap their nearest neighbour by less than 60%.",
        "Fly more slowly or take photos closer together, so that every point is seen several times.",
    ),
    "QA011": _e(
        "Elevation model could not be used",
        "Its heights do not match the photos' height reference, or the photos carry no altitude.",
        "Enter the takeoff point (latitude, longitude). Then only height differences within the model are used, so its reference no longer matters.",
    ),
    "QA012": _e(
        "Takeoff point is outside the elevation model",
        "The elevation model has no data at the takeoff point you gave, so the terrain could not be used.",
        "Check the takeoff coordinates (latitude first, then longitude), or choose a model that covers the takeoff point.",
    ),
    "QA013": _e(
        "Some photos are outside the elevation model",
        "For those photos the height above the takeoff point was used instead of the height above the ground.",
        "Use an elevation model that covers the whole flight area.",
    ),
    "QA014": _e(
        "Little overlap between flight lines",
        "Some photos overlap the neighbouring flight line by less than 50%.",
        "Space the flight lines closer together (more sideways overlap).",
    ),
    "QA015": _e(
        "No height above the ground in the photos",
        "These photos record where they were taken and a height above sea level, but not how high above the ground or the takeoff point the drone was (DJI drones record this; many other drones do not), so the resolution cannot be worked out.",
        "Tell Avispria the height of the ground above sea level (for a flat site), or give an elevation model for sites with hills. The height above the ground is then the photo's height above sea level minus the ground's.",
    ),
    "QA016": _e(
        "Camera angle not recorded",
        "These photos do not say which way the camera was pointing, so Avispria assumed straight down, as for a mapping flight.",
        "That is fine if you set the camera to look straight down. If you are not sure, check a few photos by eye: tilted photos make the overlap and resolution figures optimistic.",
    ),
    # ---- results of processing
    "RQ001": _e(
        "Some photos were not used",
        "The 3D reconstruction could not place every photo, so those were left out.",
        "Check those photos for blur and for overlap with their neighbours; fly the area again if needed.",
    ),
    "RQ002": _e(
        "The photos formed separate models",
        "The photos split into groups that may not line up with each other.",
        "More overlap between flight lines usually fixes this. Check the orthophoto for seams or shifts.",
    ),
    "RQ003": _e(
        "Poor fit between photos and 3D geometry",
        "The average reprojection error is high (under about 1 pixel is good), so the model fits the photos poorly.",
        "Look for blurred photos, moving objects (water, vehicles, swaying trees) or very uniform surfaces, and consider re-flying.",
    ),
    "RQ004": _e(
        "Resolution differs from what was expected",
        "The engine measured a ground resolution quite different from the estimate made from the photos' metadata.",
        "Usually the camera profile or the terrain assumption is off. Compare with your plan and tell the developers if it repeats.",
    ),
    # ---- planning
    "PL001": _e(
        "Requested resolution cannot be reached safely",
        "Reaching it would need flying lower than the clearance rules allow, so the typical resolution will be coarser than requested.",
        "Ask for a coarser resolution, or lower the clearance limit only if your local rules and site allow it.",
    ),
    "PL002": _e(
        "Resolution varies a lot over the terrain",
        "The relief and clearance margins are large for this flying height, so the coarsest tenth of the photos will be noticeably worse than requested.",
        "Fly at a bit more height or accept coarser resolution on the steepest parts.",
    ),
    "PL003": _e(
        "Part of the plan could not be checked",
        "Some planned photos fall outside the elevation model or too close to the surface, so they are not in the prediction.",
        "Use an elevation model that covers the whole route, including the turns outside the survey area.",
    ),
    # ---- safety checks on a plan
    "SAF001": _e(
        "Too high above the takeoff point",
        "The plan climbs higher than the height limit you set.",
        "Fly at a lower height (ask for a coarser resolution). Raise the limit only if local rules allow.",
    ),
    "SAF002": _e(
        "Too high above the ground",
        "Somewhere the drone would be higher above the ground than the legal height limit you set.",
        "Choose a lower height or a smaller area; check the limit that applies where you fly.",
    ),
    "SAF003": _e(
        "Too close to the surface",
        "At some point the drone would be closer to the ground, trees or buildings than the minimum clearance.",
        "Plan higher, or check the area for tall obstacles and add a surface height (trees, buildings).",
    ),
    "SAF004": _e(
        "Too far from the takeoff point",
        "A waypoint is farther away than the distance limit, so you might lose sight of the aircraft.",
        "Move the takeoff point closer to the area, or split the survey and fly from several takeoff points.",
    ),
    "SAF005": _e(
        "Too many waypoints for one mission",
        "DJI Fly may not accept this many waypoints in one mission.",
        "The plan is normally split into several missions automatically; check the waypoint limit setting.",
    ),
    "SAF006": _e(
        "Flight too long for one battery",
        "The estimated flight time is longer than the battery time you allowed.",
        "The plan is normally split into several missions; check the battery time setting.",
    ),
    "SAF007": _e(
        "Speed above the limit",
        "The planned speed is higher than the speed limit.",
        "Reduce the speed limit input, or fly higher so that slower speeds are not needed.",
    ),
    "SAF008": _e(
        "Planned without terrain data",
        "The plan assumes the ground is flat at the takeoff level. Over hills the drone could be much closer to the ground than planned.",
        "Add an elevation model for hilly sites. Only use flat ground where you are sure the site is flat.",
    ),
    "SAF009": _e(
        "Photo interval shorter than the camera allows",
        "The camera cannot take photos as quickly as this plan needs.",
        "Fly more slowly, fly higher, or ask for less overlap.",
    ),
    # ---- notes about your setup
    "AVI001": _e(
        "Photo-at-waypoint mode is not verified yet",
        "Your DJI Fly sample mission has no 'Take Photo' action, so Avispria cannot copy exactly how DJI Fly stores it.",
        "Use timed shot (interval) mode: set the interval shown in the plan in DJI Fly before starting.",
    ),
    "AVI002": _e(
        "Aircraft ID differs from the profile",
        "Your sample mission carries a different aircraft ID than the selected aircraft profile.",
        "Nothing to do: the ID from your own file is used, which is correct for your aircraft.",
    ),
    "AVI003": _e(
        "Camera numbers not yet verified",
        "The camera profile for this aircraft has not been confirmed with a real flight.",
        "Run the camera check on an original photo (camera-from-photo) and compare.",
    ),
    # ---- mission-file checks
    "WPML001": _e(
        "Not a valid mission file", "The file could not be read as a DJI Fly mission.", _FILE
    ),
    "WPML002": _e(
        "Mission file parts do not match", "The two parts of the file use different formats.", _FILE
    ),
    "WPML003": _e(
        "Not the DJI Fly format",
        "The file uses a format other than DJI Fly's, so DJI Fly may not open it.",
        "Create the file from your own DJI Fly sample mission.",
    ),
    "WPML004": _e(
        "Heights are not relative to takeoff",
        "The file measures heights in a way DJI Fly consumer drones do not support.",
        _FILE,
    ),
    "WPML005": _e("Fewer than two waypoints", "A mission needs at least two waypoints.", _FILE),
    "WPML006": _e(
        "Waypoint numbering is wrong",
        "The waypoints are not numbered 0, 1, 2, ... in order.",
        _FILE,
    ),
    "WPML007": _e(
        "Invalid coordinates", "A waypoint has a latitude or longitude that is not valid.", _FILE
    ),
    "WPML008": _e("Height out of range", "A waypoint height is not a sensible number.", _FILE),
    "WPML009": _e(
        "Speed out of range",
        "A speed in the file is zero, negative or above what the aircraft can do.",
        _FILE,
    ),
    "WPML010": _e("Too many waypoints", "The file has more waypoints than the limit.", _FILE),
    "WPML011": _e(
        "Two waypoints at the same place",
        "Two neighbouring waypoints are almost on top of each other.",
        _FILE,
    ),
    "WPML012": _e(
        "Very long straight leg",
        "One leg between two waypoints is unusually long.",
        "Check that this is intended, and that the drone stays in sight.",
    ),
    "WPML013": _e(
        "Camera angle out of range",
        "A waypoint asks for a camera angle the gimbal cannot reach.",
        _FILE,
    ),
    "WPML014": _e(
        "Camera action on the wrong waypoint",
        "An action in the file refers to a waypoint it does not belong to.",
        _FILE,
    ),
    "WPML015": _e("Duplicate action numbers", "Two actions share the same ID.", _FILE),
    "WPML016": _e(
        "Unusual finish or signal-lost behaviour",
        "The aircraft would not return home when the mission ends or the signal is lost, as DJI Fly normally sets it.",
        "Check this is what you want before flying.",
    ),
}


def explain(code: str) -> Explanation:
    """The explanation for ``code``; a neutral one for a code that has none."""
    return EXPLANATIONS.get(code, Explanation("Notice", "", ""))
