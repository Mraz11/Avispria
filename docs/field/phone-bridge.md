# Sending plans to DJI Fly (Android)

DJI Fly cannot import mission files, and since Android 13 no phone app may write into another app's
folder. So Avispria does the job from the **computer**, through Android's official debugging channel
(`adb`), over a USB cable or over Wi-Fi. **The phone needs no Avispria app.**

## How it works

DJI Fly lists only missions it made itself. So a plan goes into a **slot**: a placeholder mission you
make once in DJI Fly (any two points). Avispria replaces that mission's file, the way
people do it by hand (it is the founder's method, also reported by others):

1. the plan is checked, and a file DJI Fly could not read is never sent;
2. the slot's current file is copied to this computer (`~/Avispria/phone-backups`) and checked;
3. the plan is written next to it under a temporary name, and its checksum is verified on the phone;
4. only then is it moved into place, and verified again;
5. if anything fails after step 2, the original is put back.

A mission that has not been sent to is never touched. Avispria never deletes a mission.

## One-time setup

1. **In DJI Fly:** open Waypoint and save a few placeholder missions (any two points each). Make one
   per mission you expect to send at once, plus a spare. You can reuse them for ever.
2. **On the phone:** Settings > About phone, tap the OS version seven times (developer mode). Then
   Settings > Additional settings > Developer options > **USB debugging** on. On Xiaomi/Redmi phones also
   switch on *USB debugging (Security settings)* if a command is refused.
3. **On the computer:** download *SDK Platform-Tools* (free, from developer.android.com/tools/releases/platform-tools)
   and unzip it anywhere. Avispria finds it by itself on the PATH, in `~/Avispria/platform-tools`, or in the
   Android SDK; otherwise choose its folder on the Phone screen (*Where is adb?*).
4. Plug the phone in, unlock it, and tap **Allow** on *Allow USB debugging?* (tick *Always allow*).

Switch USB debugging off when you are not using it: it gives the computer deep access to the phone.

## Every day

Plan a flight, press **Send to DJI Fly...**, choose a slot for each mission, tick the confirmation and
press **Send**. Then, on the phone, close DJI Fly completely, open it again, go to Waypoint and open the
mission. The little map picture in the list may still show the old route: that is only the picture.
Compare the waypoints and heights with the spot-check sheet before you fly.

Closing DJI Fly from the computer is optional (*Close DJI Fly on the phone first*): only do it with the
drone on the ground.

## Without a cable (Wi-Fi)

On the phone: Developer options > **Wireless debugging** (phone and computer on the same Wi-Fi, or on the
phone's hotspot). Tap *Pair device with pairing code*, then on the Phone screen (*No cable*) type the
address and the 6 digits and press **Pair** (once). Then type the address from the main Wireless
debugging screen (a different number) and press **Connect**. The command line equivalents:

    uv run avispria phone pair 192.168.1.5:37123 123456
    uv run avispria phone connect 192.168.1.5:41000

## The same from the command line

    uv run avispria phone status                 # adb found? which phones?
    uv run avispria phone slots                  # the missions in DJI Fly
    uv run avispria phone pull <ID> --out samples   # copy one out, to use as the sample mission
    uv run avispria phone send plan_01.kmz --slot <ID>   # asks first; --yes to skip, --close-app

## What was verified, and what was not

Tested with a fake `adb` that behaves like a phone, including refused writes, files damaged in transit
or at the swap, and a failing restore (`tests/fakes/fake_adb.py`). **Verified on a real phone** (the
founder's Redmi, USB): `adb devices`, listing DJI Fly's waypoint folder, writing and deleting a file in it.
**Not yet verified on a real phone:** the whole send, over Wi-Fi, on iPhone/macOS (not supported), and
DJI Fly opening a mission sent this way (the manual replacement it automates is known to work).
