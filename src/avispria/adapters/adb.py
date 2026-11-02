# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Talking to an Android phone through Google's ``adb`` tool, from the computer.

The phone needs no Avispria app: since Android 13 no app may touch another app's folder, but
a computer connected through the official debugging channel (USB or Wi-Fi) may.

Everything that reaches the phone's shell is checked first: serial numbers and paths may contain
only plain characters, because ``adb shell`` hands its arguments to the phone's own shell.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

GUID_PATTERN = re.compile(r"^[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}$")  # a DJI Fly mission id
SERIAL = re.compile(r"^[A-Za-z0-9._:\-]{1,80}$")
REMOTE_PATH = re.compile(r"^/sdcard/[A-Za-z0-9._/\-]{1,300}$")
HOST_PORT = re.compile(r"^[A-Za-z0-9.\-]{1,100}:[0-9]{2,5}$")
PAIRING_CODE = re.compile(r"^[0-9]{6}$")


class AdbError(RuntimeError):
    """Something went wrong talking to the phone; the message says what to do."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing  # the file or folder asked for does not exist


class AdbNotFound(AdbError):
    """The adb program itself was not found."""


@dataclass(frozen=True)
class Device:
    serial: str
    state: str  # device (ready), unauthorized, offline
    model: str = ""

    @property
    def ready(self) -> bool:
        return self.state == "device"

    @property
    def wireless(self) -> bool:
        return ":" in self.serial or "_adb-tls-connect" in self.serial


def _friendly(text: str) -> AdbError:
    low = text.lower()
    if "no devices/emulators" in low or "no devices found" in low:
        return AdbError(
            "No phone is connected. Plug it in with a USB cable (and unlock it), or connect it "
            "over Wi-Fi with Wireless debugging."
        )
    if "unauthorized" in low:
        return AdbError(
            "The phone has not allowed this computer yet. Look at the phone's screen and tap "
            "Allow on the 'Allow USB debugging?' question (tick 'Always allow')."
        )
    if "offline" in low:
        return AdbError(
            "The phone is offline. Unplug the cable and plug it in again, or switch USB "
            "debugging off and on in Developer options."
        )
    if "more than one" in low:
        return AdbError("More than one phone is connected: choose one by its serial number.")
    if "no such file" in low or "failed to stat remote object" in low:
        return AdbError("That file or folder is not on the phone.", missing=True)
    if "permission denied" in low:
        return AdbError(
            "Android refused access. Keep the phone unlocked, and check that USB debugging is on "
            "(on Xiaomi phones also 'USB debugging (Security settings)')."
        )
    return AdbError(f"adb reported: {text.strip()[:300] or 'an unknown problem'}")


def candidate_locations() -> list[Path]:
    """Where adb usually is when it is not on the PATH."""
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    home = Path.home()
    bases = [
        Path(os.environ[v]) / "platform-tools"
        for v in ("ANDROID_HOME", "ANDROID_SDK_ROOT")
        if os.environ.get(v)
    ]
    bases += [
        home / "Avispria" / "platform-tools",
        home / "platform-tools",
        home / "Android" / "Sdk" / "platform-tools",
        home / "Library" / "Android" / "sdk" / "platform-tools",
        home / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools",
    ]
    return [b / exe for b in bases]


class Adb:
    """A handle on the adb program. ``command`` is the program (and any leading arguments)."""

    def __init__(self, command: Sequence[str], timeout: float = 30.0) -> None:
        self.command = list(command)
        self.timeout = timeout

    @classmethod
    def find(cls, explicit: str | None = None) -> Adb:
        """The adb program: the given path or folder, the PATH, or a usual place."""
        exe = "adb.exe" if sys.platform == "win32" else "adb"
        if explicit and explicit.strip():
            path = Path(explicit.strip()).expanduser()
            if path.is_dir():
                path = path / exe
            if not path.is_file():
                raise AdbNotFound(f"adb was not found at {path}.")
            return cls([str(path)])
        on_path = shutil.which("adb")
        if on_path:
            return cls([on_path])
        for path in candidate_locations():
            if path.is_file():
                return cls([str(path)])
        raise AdbNotFound(
            "adb (Android's free debugging tool) was not found. Download 'SDK Platform-Tools' from "
            "developer.android.com/tools/releases/platform-tools, unzip it, and choose the folder."
        )

    # ------------------------------------------------------------------ running
    def run(
        self, *args: str, serial: str | None = None, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        if serial is not None and not SERIAL.fullmatch(serial):
            raise AdbError(f"Not a valid phone serial number: {serial!r}")
        full = [*self.command, *(["-s", serial] if serial else []), *args]
        try:
            return subprocess.run(
                full,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdbNotFound("adb could not be started: " + str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(
                "The phone did not answer in time. Keep it unlocked and check the connection."
            ) from exc

    def _ok(self, *args: str, serial: str | None = None, timeout: float | None = None) -> str:
        done = self.run(*args, serial=serial, timeout=timeout)
        if done.returncode != 0:
            raise _friendly(done.stderr + "\n" + done.stdout)
        return done.stdout

    @staticmethod
    def _path(remote: str) -> str:
        if not REMOTE_PATH.fullmatch(remote) or ".." in remote.split("/"):
            raise AdbError(f"Refusing an unusual path on the phone: {remote!r}")
        return remote

    # ------------------------------------------------------------------ devices
    def devices(self) -> list[Device]:
        out = self._ok("devices", "-l")
        found = []
        for line in out.splitlines():
            if not line.strip() or line.startswith(("*", "List of devices")):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), "")
            found.append(Device(parts[0], parts[1], model.replace("_", " ")))
        return found

    def pair(self, host_port: str, code: str) -> str:
        if not HOST_PORT.fullmatch(host_port) or not PAIRING_CODE.fullmatch(code):
            raise AdbError(
                "Enter the address shown on the phone (like 192.168.1.5:37123) "
                "and its 6-digit code."
            )
        done = self.run("pair", host_port, code)
        if done.returncode != 0 or "success" not in done.stdout.lower():
            raise AdbError("Pairing failed. " + (done.stdout + done.stderr).strip()[:200])
        return done.stdout.strip()

    def connect(self, host_port: str) -> str:
        if not HOST_PORT.fullmatch(host_port):
            raise AdbError("Enter the address shown on the phone (like 192.168.1.5:37123).")
        done = self.run("connect", host_port)
        text = (done.stdout + done.stderr).strip()
        if done.returncode != 0 or "connected" not in text.lower() or "cannot" in text.lower():
            raise AdbError("Could not connect: " + (text[:200] or "no answer"))
        return text

    # -------------------------------------------------------------------- files
    def ls(self, serial: str, remote: str) -> list[str]:
        out = self._ok("shell", "ls", "-1", self._path(remote), serial=serial)
        return [line.strip() for line in out.splitlines() if line.strip()]

    def exists(self, serial: str, remote: str) -> bool:
        return self.run("shell", "test", "-e", self._path(remote), serial=serial).returncode == 0

    def pull(self, serial: str, remote: str, local: Path) -> Path:
        local.parent.mkdir(parents=True, exist_ok=True)
        self._ok("pull", self._path(remote), str(local), serial=serial, timeout=120)
        if not local.is_file():
            raise AdbError("The file was not copied from the phone.")
        return local

    def push(self, serial: str, local: Path, remote: str) -> None:
        if not local.is_file():
            raise AdbError(f"The file to send was not found: {local}")
        self._ok("push", str(local), self._path(remote), serial=serial, timeout=120)

    def move(self, serial: str, source: str, target: str) -> None:
        self._ok("shell", "mv", "-f", self._path(source), self._path(target), serial=serial)

    def remove(self, serial: str, remote: str) -> None:
        self._ok("shell", "rm", "-f", self._path(remote), serial=serial)

    def sha256(self, serial: str, remote: str) -> str:
        out = self._ok("shell", "sha256sum", self._path(remote), serial=serial)
        digest = out.split()[0] if out.split() else ""
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise AdbError("The phone could not check the file's checksum.")
        return digest

    def close_app(self, serial: str, package: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._]{3,100}", package):
            raise AdbError(f"Not a valid app name: {package!r}")
        self._ok("shell", "am", "force-stop", package, serial=serial)
