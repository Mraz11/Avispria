# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the phone screens tell a person about DJI Fly, debugging and Wi-Fi."""

from __future__ import annotations

INTRO = (
    "DJI Fly cannot import mission files, and Android does not let any phone app write into it. "
    "So Avispria does it from this computer: it replaces the mission in a placeholder 'slot' that "
    "you made once in DJI Fly. The original is always copied here first."
)

FIRST_TIME = (
    "1. In DJI Fly, open Waypoint and save a few placeholder missions (any two points each). "
    "These are the slots a plan goes into.\n"
    "2. On the phone: Settings > About phone, tap the OS version seven times to switch on "
    "developer mode.\n"
    "3. Settings > Additional settings > Developer options > switch on USB debugging "
    "(on Xiaomi phones also 'USB debugging (Security settings)').\n"
    "4. Plug the phone in, unlock it, and tap Allow on 'Allow USB debugging?' "
    "(tick 'Always allow').\n"
    "5. You also need adb, Google's small free debugging tool: download 'SDK Platform-Tools' from "
    "developer.android.com/tools/releases/platform-tools, unzip it, and choose its folder below if "
    "Avispria does not find it by itself.\n"
    "Switch USB debugging off again when you are not using it."
)

WIFI = (
    "No cable: on the phone open Developer options > Wireless debugging (phone and computer on "
    "the same Wi-Fi, or the phone's hotspot). Tap 'Pair device with pairing code': type the "
    "address and the 6 digits it shows here and press Pair (once). Then type the address shown "
    "on the main Wireless debugging screen (it is a different number) and press Connect."
)
