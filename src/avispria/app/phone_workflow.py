# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DJI Fly's missions on a phone: list them, copy one out, and replace one with a plan.

DJI Fly cannot import mission files, and lists only missions it made itself. So a plan goes into a
*slot*: a mission made in DJI Fly (any two points will do) whose file is replaced. Replacing is the
dangerous step, so it is done in a way that cannot lose the original or leave a half-written file:

1. the plan is checked (a file DJI Fly cannot read is never sent);
2. the slot's current file is copied to this computer, and that copy is checked;
3. the plan is written next to it under a temporary name, and its checksum is checked on the phone;
4. only then is it moved into place, and checked again;
5. if anything goes wrong after step 2 the original is put back.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from avispria.adapters.adb import GUID_PATTERN, Adb, AdbError, Device
from avispria.core.wpml.kmz import KmzError
from avispria.core.wpml.lint import LintLimits, lint_kmz
from avispria.core.wpml.reader import read_mission

FLY_PACKAGE = "dji.go.v5"  # DJI Fly on Android
WAYPOINT_DIR = f"/sdcard/Android/data/{FLY_PACKAGE}/files/waypoint"
NEW_SUFFIX = ".avispria-new"
SENT_LOG = "sent-log.json"


def default_backup_dir() -> Path:
    return Path.home() / "Avispria" / "phone-backups"


class SendError(RuntimeError):
    """The mission was not sent (or was sent and then put back); the message says what happened."""


@dataclass(frozen=True)
class Slot:
    guid: str
    waypoints: int  # 0 if the file could not be read
    created: datetime | None
    updated: datetime | None
    preview: bytes | None  # the small map picture DJI Fly keeps for its list
    last_sent: str | None  # what Avispria last put here, from the local log

    @property
    def short(self) -> str:
        return self.guid[:8]


@dataclass(frozen=True)
class SendResult:
    guid: str
    backup: Path
    sha256: str
    closed_app: bool


def kmz_path(guid: str) -> str:
    return f"{WAYPOINT_DIR}/{guid}/{guid}.kmz"


def check_guid(guid: str) -> str:
    if not GUID_PATTERN.fullmatch(guid):
        raise SendError(
            f"Not a DJI Fly mission id (like 6103D3C8-E79A-4B48-BBFE-50932D2E1306): {guid!r}"
        )
    return guid


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _times(data: bytes) -> tuple[datetime | None, datetime | None]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            text = z.read("wpmz/template.kml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError, OSError):
        return None, None

    def stamp(tag: str) -> datetime | None:
        m = re.search(rf"<wpml:{tag}>(\d{{10,13}})<", text)
        return datetime.fromtimestamp(int(m.group(1)) / 1000) if m else None

    return stamp("createTime"), stamp("updateTime")


def _log(backup_dir: Path) -> dict[str, str]:
    try:
        return json.loads((backup_dir / SENT_LOG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def list_slots(adb: Adb, serial: str, backup_dir: Path | None = None) -> list[Slot]:
    """The missions DJI Fly keeps on the phone, newest first."""
    backup_dir = backup_dir or default_backup_dir()
    sent = _log(backup_dir)
    try:
        names = adb.ls(serial, WAYPOINT_DIR)
    except AdbError as exc:
        if exc.missing:
            raise AdbError(
                "DJI Fly's mission folder is not on this phone. Open DJI Fly once, go to Waypoint "
                "and save a mission, then try again."
            ) from exc
        raise
    slots = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            if not GUID_PATTERN.fullmatch(name):
                continue  # capability, map_preview and anything else that is not a mission
            waypoints, created, updated = 0, None, None
            try:
                local = adb.pull(serial, kmz_path(name), Path(tmp) / f"{name}.kmz")
                data = local.read_bytes()
                waypoints = len(read_mission(data).waypoints)
                created, updated = _times(data)
            except (AdbError, KmzError):
                pass  # an empty or unreadable slot is still listed
            preview = None
            try:
                picture = adb.pull(
                    serial,
                    f"{WAYPOINT_DIR}/map_preview/{name}/{name}.jpg",
                    Path(tmp) / f"{name}.jpg",
                )
                preview = picture.read_bytes()
            except AdbError:
                pass
            slots.append(Slot(name, waypoints, created, updated, preview, sent.get(name)))
    slots.sort(key=lambda s: s.created or datetime.min, reverse=True)
    return slots


def pull_mission(adb: Adb, serial: str, guid: str, folder: Path) -> Path:
    """Copy a slot's mission file to ``folder`` (e.g. to use it as the sample mission)."""
    check_guid(guid)
    return adb.pull(serial, kmz_path(guid), folder / f"{guid}.kmz")


def _restore(adb: Adb, serial: str, backup: Path, guid: str) -> None:
    target = kmz_path(guid)
    adb.push(serial, backup, target + NEW_SUFFIX)
    adb.move(serial, target + NEW_SUFFIX, target)


def send_mission(
    adb: Adb,
    serial: str,
    plan: Path,
    guid: str,
    backup_dir: Path | None = None,
    *,
    close_app: bool = False,
    limits: LintLimits | None = None,
    now: datetime | None = None,
) -> SendResult:
    """Replace a slot's mission file with ``plan``; the original is kept and restored on failure."""
    check_guid(guid)
    backup_dir = backup_dir or default_backup_dir()
    try:
        data = plan.read_bytes()
    except OSError as exc:
        raise SendError(f"The mission file could not be read: {exc}") from exc
    errors = [i for i in lint_kmz(data, limits or LintLimits()) if i.level == "error"]
    if errors:
        raise SendError(
            "This mission file has problems, so it was not sent: "
            + "; ".join(f"{i.code} {i.message}" for i in errors[:3])
        )
    target = kmz_path(guid)
    if not adb.exists(serial, target):
        raise SendError(
            "That slot is not on the phone any more. Refresh the list and choose again."
        )

    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = adb.pull(serial, target, backup_dir / f"{guid}_{stamp}_original.kmz")
    try:
        read_mission(backup.read_bytes())
    except KmzError as exc:  # a backup we could not read again would be worth nothing
        raise SendError(
            f"The copy of the original could not be checked, so nothing was changed: {exc}"
        ) from exc

    wanted = hashlib.sha256(data).hexdigest()
    if close_app:
        adb.close_app(serial, FLY_PACKAGE)
    temporary = target + NEW_SUFFIX
    try:
        adb.push(serial, plan, temporary)
        if adb.sha256(serial, temporary) != wanted:
            raise SendError("The file arrived damaged on the phone. Nothing was changed.")
    except (AdbError, SendError) as exc:
        _quiet_remove(adb, serial, temporary)
        if isinstance(exc, SendError):
            raise
        raise SendError(f"Writing to the phone failed, and nothing was changed: {exc}") from exc

    try:
        adb.move(serial, temporary, target)
        if adb.sha256(serial, target) != wanted:
            raise SendError("The mission on the phone does not match what was sent.")
    except (AdbError, SendError) as exc:
        try:
            _restore(adb, serial, backup, guid)
        except AdbError as again:
            raise SendError(
                f"Sending failed ({exc}) and putting the original back failed too ({again}). "
                f"Your original is safe on this computer: {backup}"
            ) from again
        raise SendError(f"Sending failed ({exc}). The original mission was put back.") from exc

    sent = _log(backup_dir)
    sent[guid] = f"{plan.name} at {(now or datetime.now()):%Y-%m-%d %H:%M}"
    (backup_dir / SENT_LOG).write_text(json.dumps(sent, indent=1), encoding="utf-8")
    return SendResult(guid, backup, wanted, close_app)


def _quiet_remove(adb: Adb, serial: str, remote: str) -> None:
    with contextlib.suppress(
        AdbError
    ):  # a leftover temporary file does no harm: DJI Fly ignores it
        adb.remove(serial, remote)


def ready_device(adb: Adb, serial: str | None = None) -> Device:
    """The phone to use: the given serial, or the only one that is ready."""
    devices = adb.devices()
    if serial:
        match = next((d for d in devices if d.serial == serial), None)
        if match is None:
            raise AdbError(f"The phone {serial} is not connected.")
        candidates = [match]
    else:
        candidates = devices
    ready = [d for d in candidates if d.ready]
    if ready and len(ready) == 1:
        return ready[0]
    if len(ready) > 1:
        raise AdbError("More than one phone is connected: say which one (its serial number).")
    if any(d.state == "unauthorized" for d in candidates):
        raise AdbError(
            "The phone has not allowed this computer yet. Look at the phone's screen and tap "
            "Allow on the 'Allow USB debugging?' question (tick 'Always allow')."
        )
    if candidates:
        raise AdbError(
            "The phone is connected but not ready (it says it is offline). Unplug and replug it."
        )
    raise AdbError(
        "No phone is connected. Plug it in with a USB cable (unlocked, USB debugging on), or "
        "connect it over Wi-Fi with Wireless debugging."
    )
