# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the Phone screen does, as plain functions: check the connection, send plans, copy a sample.

The screen only calls these and draws what they return, so the rules (which slot may be chosen, what
happens after a failure) are tested without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from avispria.adapters.adb import Adb, AdbError, AdbNotFound, Device
from avispria.app.phone_workflow import (
    SendError,
    SendResult,
    Slot,
    default_backup_dir,
    list_slots,
    pull_mission,
    ready_device,
    send_mission,
)


def default_sample_dir() -> Path:
    return Path.home() / "Avispria" / "phone-samples"


@dataclass(frozen=True)
class PhoneStatus:
    adb: str | None = None  # how adb is started, for display
    adb_missing: bool = False
    devices: list[Device] = field(default_factory=list)
    serial: str | None = None  # the phone that will be used (connected and allowed)
    model: str = ""
    slots: list[Slot] = field(default_factory=list)
    problem: str | None = None  # what is wrong, in plain words


@dataclass(frozen=True)
class SendRequest:
    plan: Path
    guid: str


@dataclass(frozen=True)
class SendOutcome:
    request: SendRequest
    result: SendResult | None = None
    error: str | None = None


def check_phone(adb_path: str = "", backup_dir: Path | None = None) -> PhoneStatus:
    """Is adb there, is a phone connected and allowed, and which missions does DJI Fly hold?"""
    try:
        adb = Adb.find(adb_path or None)
    except AdbNotFound as exc:
        return PhoneStatus(adb_missing=True, problem=str(exc))
    shown = " ".join(adb.command)
    try:
        devices = adb.devices()
    except AdbError as exc:
        return PhoneStatus(adb=shown, problem=str(exc))
    try:
        device = ready_device(adb)
    except AdbError as exc:
        return PhoneStatus(adb=shown, devices=devices, problem=str(exc))
    try:
        slots = list_slots(adb, device.serial, backup_dir)
    except AdbError as exc:
        return PhoneStatus(
            adb=shown, devices=devices, serial=device.serial, model=device.model, problem=str(exc)
        )
    problem = None
    if not slots:
        problem = (
            "DJI Fly has no missions on this phone yet. In DJI Fly, open Waypoint and save a "
            "placeholder mission (any two points), then check again."
        )
    return PhoneStatus(shown, False, devices, device.serial, device.model, slots, problem)


def pair_phone(adb_path: str, address: str, code: str) -> str:
    return Adb.find(adb_path or None).pair(address.strip(), code.strip())


def connect_phone(adb_path: str, address: str) -> str:
    return Adb.find(adb_path or None).connect(address.strip())


def use_as_sample(adb_path: str, serial: str, guid: str, folder: Path | None = None) -> Path:
    """Copy a mission from the phone to use as the sample mission when planning."""
    return pull_mission(Adb.find(adb_path or None), serial, guid, folder or default_sample_dir())


def check_requests(requests: list[SendRequest], slots: list[Slot]) -> None:
    """Refuse a send that cannot be right, before anything is written."""
    if not requests:
        raise SendError("Choose a mission file to send.")
    known = {s.guid for s in slots}
    usable = {s.guid for s in slots if s.waypoints > 0}  # only a mission we can read is a slot
    used: set[str] = set()
    for r in requests:
        if not r.guid:
            raise SendError(f"Choose the slot on the phone for {r.plan.name}.")
        if r.guid not in known:
            raise SendError(
                "A chosen slot is not on the phone any more. Check again and choose once more."
            )
        if r.guid not in usable:
            raise SendError(
                f"Avispria cannot read mission {r.guid[:8]}... (it may not be a waypoint mission), "
                "so it will not replace it. Choose another slot."
            )
        if r.guid in used:
            raise SendError("The same slot is chosen twice: each mission needs its own slot.")
        used.add(r.guid)
        if not r.plan.is_file():
            raise SendError(f"The mission file was not found: {r.plan}")


def send_all(
    adb_path: str,
    serial: str,
    requests: list[SendRequest],
    backup_dir: Path | None = None,
    *,
    close_app: bool = False,
) -> list[SendOutcome]:
    """Send each plan to its slot, one after another; the first failure stops the rest.

    Every send is safe on its own (see ``send_mission``), so after a failure the missions already
    sent stay sent, the failed one is as it was, and the rest were not started.
    """
    adb = Adb.find(adb_path or None)
    backups = backup_dir or default_backup_dir()
    outcomes: list[SendOutcome] = []
    for n, request in enumerate(requests):
        try:
            result = send_mission(
                adb, serial, request.plan, request.guid, backups, close_app=close_app and n == 0
            )
        except (AdbError, SendError) as exc:
            outcomes.append(SendOutcome(request, error=str(exc)))
            break
        outcomes.append(SendOutcome(request, result=result))
    return outcomes
