# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `phone` commands: DJI Fly's missions on an Android phone, from the computer (adb)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from avispria.adapters.adb import Adb, AdbError, Device
from avispria.app.cli._base import app
from avispria.app.phone_workflow import (
    SendError,
    default_backup_dir,
    list_slots,
    pull_mission,
    ready_device,
    send_mission,
)

phone = typer.Typer(
    help="Send plans to DJI Fly on your phone over USB or Wi-Fi, and copy missions back.",
    no_args_is_help=True,
)
app.add_typer(phone, name="phone")

AdbPath = Annotated[
    str | None,
    typer.Option("--adb", help="adb, or the folder it is in (default: find it by itself)"),
]
Serial = Annotated[
    str | None, typer.Option(help="The phone's serial number, if several are connected")
]


def _fail(message: str) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED)
    return typer.Exit(1)


def _connect(adb_path: str | None, serial: str | None) -> tuple[Adb, Device]:
    try:
        adb = Adb.find(adb_path)
        return adb, ready_device(adb, serial)
    except AdbError as exc:
        raise _fail(str(exc)) from exc


@phone.command()
def status(adb_path: AdbPath = None) -> None:
    """Is adb found, and which phones are connected?"""
    try:
        adb = Adb.find(adb_path)
        devices = adb.devices()
    except AdbError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"adb       {' '.join(adb.command)}")
    if not devices:
        typer.secho("phones    none connected", fg=typer.colors.YELLOW)
        typer.echo(
            "          Plug the phone in (unlocked, USB debugging on) or use `avispria phone pair`."
        )
        return
    for d in devices:
        colour = typer.colors.GREEN if d.ready else typer.colors.YELLOW
        how = "Wi-Fi" if d.wireless else "USB"
        typer.secho(f"phones    {d.serial}  {d.model or 'phone'}  {d.state}  ({how})", fg=colour)
    if any(d.state == "unauthorized" for d in devices):
        typer.echo("          Look at the phone and tap Allow on 'Allow USB debugging?'.")


@phone.command()
def slots(
    backup_dir: Annotated[
        Path | None, typer.Option(help="Where originals and the sent-log are kept")
    ] = None,
    adb_path: AdbPath = None,
    serial: Serial = None,
) -> None:
    """List the missions DJI Fly keeps on the phone (the places a plan can be sent to)."""
    adb, device = _connect(adb_path, serial)
    try:
        found = list_slots(adb, device.serial, backup_dir)
    except AdbError as exc:
        raise _fail(str(exc)) from exc
    if not found:
        raise _fail(
            "DJI Fly has no missions on this phone. Make a placeholder mission in DJI Fly first."
        )
    typer.echo(f"{len(found)} mission(s) on {device.model or device.serial}:")
    for s in found:
        made = f"{s.created:%Y-%m-%d %H:%M}" if s.created else "unknown date"
        sent = f"   last sent by Avispria: {s.last_sent}" if s.last_sent else ""
        note = "" if s.waypoints else "   (cannot be read: not offered as a slot)"
        typer.echo(f"  {s.guid}  {s.waypoints:3d} waypoints  made {made}{sent}{note}")


@phone.command()
def pull(
    slot: Annotated[str, typer.Argument(help="Mission id, as listed by `phone slots`")],
    out: Annotated[Path, typer.Option(help="Folder to copy the mission file into")],
    adb_path: AdbPath = None,
    serial: Serial = None,
) -> None:
    """Copy a mission from the phone (e.g. to use it as the sample mission for planning)."""
    adb, device = _connect(adb_path, serial)
    try:
        path = pull_mission(adb, device.serial, slot, out)
    except (AdbError, SendError) as exc:
        raise _fail(str(exc)) from exc
    typer.secho(f"Copied to {path}", fg=typer.colors.GREEN)


@phone.command()
def send(
    kmz: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="The mission file to send")
    ],
    slot: Annotated[str, typer.Option(help="Mission id to replace, as listed by `phone slots`")],
    close_app: Annotated[
        bool, typer.Option("--close-app/--keep-app", help="Close DJI Fly on the phone first")
    ] = False,
    backup_dir: Annotated[Path | None, typer.Option(help="Where the original is kept")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False,
    adb_path: AdbPath = None,
    serial: Serial = None,
) -> None:
    """Replace the mission in a DJI Fly slot with a plan. The original is backed up first."""
    adb, device = _connect(adb_path, serial)
    backups = backup_dir or default_backup_dir()
    try:
        target = next((s for s in list_slots(adb, device.serial, backups) if s.guid == slot), None)
    except AdbError as exc:
        raise _fail(str(exc)) from exc
    if target is None:
        raise _fail(
            f"There is no mission {slot} on the phone. Run `avispria phone slots` to see them."
        )
    if target.waypoints == 0:
        raise _fail(
            f"Avispria cannot read mission {target.short}... (it may not be a waypoint mission), "
            "so it will not replace it. Choose another slot."
        )
    typer.echo(
        f"This replaces mission {target.short} ({target.waypoints} waypoints) on the phone with"
    )
    typer.echo(f"{kmz.name}. The original is copied to {backups} first.")
    if close_app:
        typer.secho(
            "DJI Fly will be closed on the phone: be sure no flight is in progress.",
            fg=typer.colors.YELLOW,
        )
    if not yes and not typer.confirm("Continue?"):
        raise typer.Exit(1)
    try:
        result = send_mission(adb, device.serial, kmz, slot, backups, close_app=close_app)
    except (AdbError, SendError) as exc:
        raise _fail(str(exc)) from exc
    typer.secho(f"Sent. Original kept as {result.backup}", fg=typer.colors.GREEN)
    typer.echo("Now close DJI Fly completely, open it again, go to Waypoint and open the mission.")


@phone.command()
def pair(
    address: Annotated[
        str, typer.Argument(help="Address shown on the phone, like 192.168.1.5:37123")
    ],
    code: Annotated[str, typer.Argument(help="The 6-digit pairing code shown on the phone")],
    adb_path: AdbPath = None,
) -> None:
    """Pair with a phone over Wi-Fi (once). On the phone: Developer options > Wireless debugging."""
    try:
        typer.echo(Adb.find(adb_path).pair(address, code))
    except AdbError as exc:
        raise _fail(str(exc)) from exc
    typer.echo("Now connect with the (different) address on the Wireless debugging screen:")
    typer.echo("  avispria phone connect 192.168.1.5:41000")


@phone.command()
def connect(
    address: Annotated[str, typer.Argument(help="Address shown on the Wireless debugging screen")],
    adb_path: AdbPath = None,
) -> None:
    """Connect to a phone over Wi-Fi (after pairing)."""
    try:
        typer.echo(Adb.find(adb_path).connect(address))
    except AdbError as exc:
        raise _fail(str(exc)) from exc
