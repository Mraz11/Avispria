// SPDX-FileCopyrightText: 2026 Avispria contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// Checklists for a mapping flight. Plain data: edit the wording here. Ids must stay unique
// (they are what a phone remembers as ticked).

export const CHECKLISTS = [
  {
    id: "leaving",
    title: "Before you leave",
    items: [
      { id: "batteries", text: "Drone batteries, controller and phone are charged (and a power bank, if you have one)" },
      { id: "card", text: "A microSD card is in the drone and has free space", note: "A 12 MP photo is roughly 4 to 6 MB; 48 MP or DNG (raw) files are about 60 MB each." },
      { id: "rules", text: "You know the rules for the place: permission, airspace (airports, restricted zones) and the height limit", note: "Rules differ by country and site. You are responsible for following them." },
      { id: "weather", text: "The weather is suitable: wind under about 5 m/s, no rain, and the sun is not very low", note: "A low sun makes long shadows that spoil the photos." },
      { id: "missions", text: "The mission files are on the phone and open in DJI Fly", note: "Compare the number of waypoints with your plan's spot-check sheet." },
    ],
  },
  {
    id: "site",
    title: "At the site",
    items: [
      { id: "takeoff", text: "You take off from an open spot, clear of trees, wires and people" },
      { id: "coords", text: "The takeoff coordinates are written down (Log tab, Use my location)", note: "Avispria uses them to check heights over hills." },
      { id: "obstacles", text: "You have looked for tall trees, towers, wires and buildings higher than your flying height" },
      { id: "warnings", text: "DJI Fly shows no compass, IMU or obstacle warnings" },
      { id: "gps", text: "GPS is ready (about 12 satellites or more) and the home point is recorded" },
      { id: "rth", text: "Return-to-home height is set above the tallest obstacle" },
      { id: "camera-down", text: "The camera points straight down (-90 degrees)" },
      { id: "photo-size", text: "Photo size is set as in your plan (12 MP is the usual choice)" },
      { id: "interval", text: "Timed shot is set to the interval your plan shows, or shorter", note: "Start it when the drone reaches the first waypoint and stop it at the last." },
      { id: "shutter", text: "The shutter is fast enough: about 1/1000 s or faster in good light", note: "A slow shutter smears the photos when the drone moves." },
      { id: "mission-check", text: "The mission is open in DJI Fly and its waypoints and heights match the spot-check sheet" },
      { id: "sight", text: "You can see the drone all the time, or a spotter can" },
    ],
  },
  {
    id: "air",
    title: "In the air",
    items: [
      { id: "start", text: "Start the mission, then start timed shot at the first waypoint" },
      { id: "watch", text: "Watch the drone, the battery and the wind, not only the screen" },
      { id: "problem", text: "If anything looks wrong, pause the mission and take manual control" },
      { id: "stop", text: "Stop timed shot at the last waypoint, let the drone return, and land with a good battery reserve" },
    ],
  },
  {
    id: "after",
    title: "After landing",
    items: [
      { id: "count", text: "The number of photos looks right for the plan (the plan shows how many to expect)" },
      { id: "originals", text: "Copy the ORIGINAL photos from the microSD card, not from the DJI Fly album", note: "The album copy has lost its position data." },
      { id: "backup", text: "Make a second copy of the photos before you clear the card" },
      { id: "log", text: "Write the flight in the Log tab: wind, battery, notes" },
      { id: "check", text: "At your computer, run Check my photos soon, while you can still fly gaps again" },
    ],
  },
  {
    id: "first",
    title: "First test flight (probe)",
    note: "A small, safe flight to learn how DJI Fly flies a plan from Avispria.",
    items: [
      { id: "first-area", text: "Open, flat ground with nothing within 100 m: no trees, wires, buildings or people" },
      { id: "first-size", text: "A small area (about 60 x 60 m) at about 30 m height" },
      { id: "first-plan", text: "Planned with It is flat and timed shot (only on a really flat, open site)" },
      { id: "first-wind", text: "Wind under about 5 m/s and good GPS" },
      { id: "first-copy", text: "The mission is in DJI Fly's folder and opens; waypoints and heights match the sheet" },
      { id: "first-hands", text: "Hands near the sticks: pause and take control if the aircraft drifts toward anything" },
      { id: "first-notice", text: "Notice and write down: are the lines straight, how far does it dip between waypoints, did every photo fire?" },
      { id: "first-send", text: "Copy the ORIGINAL photos (zipped) with the plan files and your DJI Fly version, to share" },
    ],
  },
];
