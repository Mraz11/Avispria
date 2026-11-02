# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phone: send a plan into DJI Fly on your phone (USB or Wi-Fi) and copy a mission back out."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from nicegui import ui

from avispria.app.phone_workflow import SendError, default_backup_dir
from avispria.app.ui.jobs import run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.phone_job import (
    PhoneStatus,
    SendRequest,
    check_phone,
    check_requests,
    connect_phone,
    pair_phone,
    send_all,
    use_as_sample,
)
from avispria.app.ui.state import STATE
from avispria.app.ui.views import phone_rows, slot_label
from avispria.app.ui.widgets import PathField, status_rows

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


def _problem(box: ui.column, text: str) -> None:
    with box:
        ui.label(text).classes("av-problem-text font-medium")


def _picture(data: bytes | None) -> None:
    if data:
        encoded = base64.b64encode(data).decode("ascii")
        ui.image(f"data:image/jpeg;base64,{encoded}").classes("w-32 h-24 rounded")
    else:
        ui.icon("map").classes("text-5xl av-muted")


async def phone_page() -> None:
    status: dict[str, PhoneStatus] = {"now": PhoneStatus()}
    rows: list[tuple[PathField, ui.select]] = []
    w: dict[str, Any] = {}  # the widgets of the send panel, which is rebuilt on every check

    with frame("Phone"):
        ui.label(INTRO).classes("text-base")

        with ui.card().classes("w-full gap-3"):
            ui.label("1. Connect your phone").classes("text-lg font-bold")
            state_box = ui.column().classes("w-full gap-2")
            check_button = (
                ui.button("Check again", icon="refresh").props("no-caps").mark("phone-refresh")
            )
            with ui.expansion(
                "First time? Switch on debugging (once)", icon="help_outline"
            ).classes("w-full"):
                ui.label(FIRST_TIME).classes("text-sm whitespace-pre-line")
            with ui.expansion("No cable: connect over Wi-Fi", icon="wifi").classes("w-full"):
                ui.label(WIFI).classes("text-sm")
                with ui.row().classes("w-full items-center gap-2"):
                    pair_address = (
                        ui.input("Pairing address (like 192.168.1.5:37123)")
                        .props("outlined dense")
                        .mark("pair-address-input")
                    )
                    pair_code = (
                        ui.input("6-digit code")
                        .props("outlined dense")
                        .classes("w-40")
                        .mark("pair-code-input")
                    )
                    pair_button = ui.button("Pair").props("no-caps outline").mark("pair-button")
                with ui.row().classes("w-full items-center gap-2"):
                    connect_address = (
                        ui.input("Connect address (like 192.168.1.5:41000)")
                        .props("outlined dense")
                        .mark("connect-address-input")
                    )
                    connect_button = (
                        ui.button("Connect").props("no-caps outline").mark("connect-button")
                    )
                wifi_box = ui.column().classes("w-full")
            with ui.expansion("Where is adb?", icon="folder").classes("w-full"):
                adb_field = PathField(
                    "adb (the program, or the folder it is in)",
                    directory=False,
                    value=STATE.adb_path,
                    hint="Leave empty to let Avispria look for it.",
                    marker="adb",
                )

        slots_card = ui.card().classes("w-full gap-3")
        send_card = ui.card().classes("w-full gap-3")
        # the outcome of a send lives OUTSIDE the cards that are rebuilt on every check, so the
        # refresh that follows a send cannot wipe the message the person has to read
        result_box = ui.column().classes("w-full gap-2")

    def slot_cards() -> None:
        slots_card.clear()
        slots_card.set_visibility(bool(status["now"].slots))
        with slots_card:
            ui.label("2. Your missions in DJI Fly").classes("text-lg font-bold")
            ui.label(
                "These are the slots a plan can be sent to. 'Use as my sample mission' copies one "
                "to this computer, so planning matches your aircraft exactly."
            ).classes("text-sm av-muted")
            for slot in status["now"].slots:
                card = ui.card().props("flat bordered").classes("w-full")
                with card, ui.row().classes("w-full items-center gap-4 no-wrap"):
                    _picture(slot.preview)
                    with ui.column().classes("gap-0 grow"):
                        ui.label(f"Mission {slot.short}...").classes("font-medium")
                        ui.label(slot_label(slot)).classes("text-sm av-muted")
                    if slot.waypoints > 0:
                        ui.button(
                            "Use as my sample mission",
                            on_click=lambda _, g=slot.guid: use_sample(g),
                        ).props("no-caps outline").mark(f"use-{slot.short}")
                    else:
                        ui.label(
                            "Avispria cannot read this mission (it may not be a waypoint "
                            "mission), so it is never replaced."
                        ).classes("text-sm av-muted max-w-xs")

    def add_row(file_value: str = "") -> None:
        n = len(rows)
        usable = [s for s in status["now"].slots if s.waypoints > 0]
        options = {s.guid: slot_label(s) for s in usable}
        default = usable[n].guid if n < len(usable) else None
        with w["rows"], ui.column().classes("w-full gap-1"):
            field = PathField(
                "Mission file to send (.kmz)",
                directory=False,
                suffixes=[".kmz"],
                value=file_value,
                marker=f"send-file-{n}",
            )
            chooser = (
                ui.select(options, value=default, label="Send it to this slot")
                .classes("w-full")
                .props("outlined dense")
                .mark(f"send-slot-{n}")
            )
        rows.append((field, chooser))

    def send_panel() -> None:
        send_card.clear()
        send_card.set_visibility(bool(status["now"].slots))
        rows.clear()
        with send_card:
            ui.label("3. Send a plan to DJI Fly").classes("text-lg font-bold")
            w["rows"] = ui.column().classes("w-full gap-3")
            for path in STATE.last_plan_files or [""]:
                add_row(path)
            ui.button("Add another mission", icon="add", on_click=lambda: add_row()).props(
                "flat no-caps"
            ).mark("add-row")
            w["close"] = ui.checkbox(
                "Close DJI Fly on the phone first (be sure no flight is in progress)"
            ).mark("close-app")
            w["confirm"] = ui.checkbox(
                "I understand: the mission in each chosen slot is replaced. The originals are "
                f"copied to {default_backup_dir()} first."
            ).mark("confirm-send")
            ui.button("Send to DJI Fly", icon="send", on_click=lambda: send()).props(
                "no-caps color=primary"
            ).mark("send-button")

    async def check() -> None:
        STATE.adb_path = adb_field.value
        check_button.disable()
        state_box.clear()
        with state_box:
            ui.spinner()
            ui.label("Looking for your phone...")
        result = await run_job(check_phone, adb_field.value)
        state_box.clear()
        with state_box:
            if result.ok and result.value is not None:
                status["now"] = result.value
                status_rows(phone_rows(result.value))
            else:
                status["now"] = PhoneStatus()
                ui.label(f"Could not check the phone: {result.error}").classes("av-problem-text")
        slot_cards()
        send_panel()
        check_button.enable()

    async def use_sample(guid: str) -> None:
        serial = status["now"].serial
        if serial is None:
            return
        result = await run_job(use_as_sample, adb_field.value, serial, guid)
        if result.ok and result.value is not None:
            STATE.sample_mission = str(result.value)
            ui.notify(
                f"Saved. The Plan screen will use {result.value.name} as the sample mission.",
                type="positive",
            )
        else:
            ui.notify(result.error or "The mission could not be copied.", type="negative")

    async def wifi(action: str) -> None:
        wifi_box.clear()
        if action == "pair":
            result = await run_job(
                pair_phone, adb_field.value, pair_address.value or "", pair_code.value or ""
            )
        else:
            result = await run_job(connect_phone, adb_field.value, connect_address.value or "")
        with wifi_box:
            ui.label(result.value if result.ok else (result.error or "That did not work.")).classes(
                "text-sm" if result.ok else "av-problem-text"
            )
        if result.ok and action == "connect":
            await check()

    async def send() -> None:
        send_box = result_box
        send_box.clear()
        serial = status["now"].serial
        requests = [
            SendRequest(Path(field.value).expanduser(), chosen.value or "")
            for field, chosen in rows
            if field.value
        ]
        try:
            check_requests(requests, status["now"].slots)
        except SendError as exc:
            _problem(send_box, str(exc))
            return
        if not w["confirm"].value:
            _problem(
                send_box, "Tick the box above to confirm that the chosen missions may be replaced."
            )
            return
        if serial is None:
            _problem(send_box, "No phone is connected.")
            return
        with send_box:
            ui.spinner()
            ui.label("Sending...")
        result = await run_job(
            send_all, adb_field.value, serial, requests, None, close_app=bool(w["close"].value)
        )
        send_box.clear()
        with send_box:
            if not result.ok or result.value is None:
                ui.label(f"Sending failed: {result.error}").classes("av-problem-text font-medium")
                return
            done = [o for o in result.value if o.result is not None]
            for o in result.value:
                if o.result is not None:
                    ui.label(
                        f"Sent {o.request.plan.name} to {o.result.guid[:8]}... "
                        f"(original kept: {o.result.backup})"
                    ).classes("font-medium")
                else:
                    ui.label(f"{o.request.plan.name}: {o.error}").classes(
                        "av-problem-text font-medium"
                    )
            failed = [o for o in result.value if o.error]
            ui.notify(
                "Sent. Now close DJI Fly completely, open it again and open the mission in "
                "Waypoint."
                if done and not failed
                else "Not everything was sent: read the messages below the Send button.",
                type="positive" if done and not failed else "warning",
                close_button="OK",
                timeout=0,  # stays until dismissed: it must be read, wherever the page is scrolled
            )
            if done:
                with ui.card().classes("w-full av-note-caution"):
                    ui.label("Next, on the phone").classes("font-bold")
                    ui.label(
                        "Close DJI Fly completely (swipe it away), open it again, go to Waypoint "
                        "and open the mission you sent to. The little picture in the list may "
                        "still show the old route: that is only the picture."
                    ).classes("text-sm")
        await check()

    check_button.on_click(check)
    pair_button.on_click(lambda: wifi("pair"))
    connect_button.on_click(lambda: wifi("connect"))
    await ui.context.client.connected()
    await check()
