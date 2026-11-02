# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A stand-in for Android's `adb` tool, for tests: the "phone" is a folder on this computer.

Run as ``python fake_adb.py <adb arguments>``. Environment:
  FAKE_ADB_ROOT    the phone's file system (``/sdcard/...`` is ``$FAKE_ADB_ROOT/sdcard/...``)
  FAKE_ADB_STATE   device (default) | unauthorized | offline | none
  FAKE_ADB_SERIAL  serial number to show (default f2e66f48)
  FAKE_ADB_FAIL    comma list of commands that fail: push, mv, pull, ls
  FAKE_ADB_CORRUPT "push": the phone stores something different from what was sent;
                   "mv": the first swap into place leaves a damaged file
  FAKE_ADB_LOG     file that gets one line per call
"""

import hashlib
import os
import shutil
import sys
from pathlib import Path

root = Path(os.environ["FAKE_ADB_ROOT"])
state = os.environ.get("FAKE_ADB_STATE", "device")
serial_shown = os.environ.get("FAKE_ADB_SERIAL", "f2e66f48")
failing = set(filter(None, os.environ.get("FAKE_ADB_FAIL", "").split(",")))
args = sys.argv[1:]
if os.environ.get("FAKE_ADB_LOG"):
    with open(os.environ["FAKE_ADB_LOG"], "a", encoding="utf-8") as log:
        log.write(" ".join(args) + "\n")


def phone(remote: str) -> Path:
    return root / remote.lstrip("/")


def fail(message: str, code: int = 1) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(code)


serial = None
if args[:1] == ["-s"]:
    serial, args = args[1], args[2:]
cmd = args[0] if args else ""

if cmd == "version":
    print("Android Debug Bridge version 1.0.41 (fake)")
    sys.exit(0)
if cmd == "devices":
    print("* daemon not running; starting now at tcp:5037")
    print("* daemon started successfully")
    print("List of devices attached")
    if state != "none":
        print(f"{serial_shown}\t{state} usb:1-1 product:fake model:Redmi_K90 device:fake")
    sys.exit(0)
if cmd == "pair":
    if args[2] != "123456":
        fail("error: wrong pairing code")
    print(f"Successfully paired to {args[1]} [guid=adb-fake]")
    sys.exit(0)
if cmd == "connect":
    print(f"connected to {args[1]}")
    sys.exit(0)

if state == "none":
    fail("error: no devices/emulators found")
if state == "unauthorized":
    fail("error: device unauthorized.\nThis adb server's $ADB_VENDOR_KEYS is not set")
if state == "offline":
    fail("error: device offline")
if serial and serial != serial_shown:
    fail(f"error: device '{serial}' not found")

if cmd == "shell":
    sub = args[1:]
    name, rest = sub[0], sub[1:]
    if name == "ls":
        if "ls" in failing:
            fail("ls: Permission denied")
        target = phone(rest[-1])
        if not target.exists():
            fail(f"ls: {rest[-1]}: No such file or directory")
        print(
            "\n".join(sorted(p.name for p in target.iterdir())) if target.is_dir() else target.name
        )
    elif name == "test":
        sys.exit(0 if phone(rest[-1]).exists() else 1)
    elif name == "mv":
        if "mv" in failing:
            fail("mv: Permission denied")
        shutil.move(str(phone(rest[-2])), str(phone(rest[-1])))
        marker = root / ".corrupted"
        if os.environ.get("FAKE_ADB_CORRUPT") == "mv" and not marker.exists():
            marker.write_text("once")  # the first swap leaves a damaged file; later ones are fine
            phone(rest[-1]).write_bytes(phone(rest[-1]).read_bytes()[:-1] + b"?")
    elif name == "rm":
        phone(rest[-1]).unlink(missing_ok=True)
    elif name == "mkdir":
        phone(rest[-1]).mkdir(parents=True, exist_ok=True)
    elif name == "sha256sum":
        target = phone(rest[0])
        if not target.is_file():
            fail(f"sha256sum: {rest[0]}: No such file or directory")
        print(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {rest[0]}")
    elif name == "am":
        pass  # am force-stop <package>
    else:
        fail(f"/system/bin/sh: {name}: inaccessible or not found", 127)
    sys.exit(0)
if cmd == "pull":
    if "pull" in failing:
        fail("adb: error: failed to copy: Permission denied")
    source = phone(args[1])
    if not source.is_file():
        fail(f"adb: error: failed to stat remote object '{args[1]}': No such file or directory")
    Path(args[2]).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, args[2])
    print(f"{args[1]}: 1 file pulled, 0 skipped.")
    sys.exit(0)
if cmd == "push":
    if "push" in failing:
        fail("adb: error: failed to copy: Permission denied")
    target = phone(args[2])
    target.parent.mkdir(parents=True, exist_ok=True)
    data = Path(args[1]).read_bytes()
    target.write_bytes(data[:-1] + b"?" if os.environ.get("FAKE_ADB_CORRUPT") == "push" else data)
    print(f"{args[1]}: 1 file pushed, 0 skipped.")
    sys.exit(0)
fail(f"adb: unknown command {cmd}")
