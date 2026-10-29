// SPDX-FileCopyrightText: 2026 Avispria contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// What the page keeps on the phone (ticked items, the flight log, settings) and how the log is
// exported. No page code here, so it can be tested; storage is passed in.

export const KEYS = {
  checklist: "avispria.checklist.v1",
  log: "avispria.log.v1",
  settings: "avispria.settings.v1",
};

/** Storage that never throws: a private-browsing phone may refuse localStorage. */
export function safeStorage(backing) {
  const memory = new Map();
  let usable = !!backing;
  if (usable) {
    try {
      backing.setItem("avispria.probe", "1");
      backing.removeItem("avispria.probe");
    } catch {
      usable = false;
    }
  }
  return {
    persistent: usable,
    getItem(key) {
      if (usable) {
        try {
          return backing.getItem(key);
        } catch {
          usable = false;
        }
      }
      return memory.has(key) ? memory.get(key) : null;
    },
    setItem(key, value) {
      if (usable) {
        try {
          backing.setItem(key, value);
          return;
        } catch {
          usable = false;
        }
      }
      memory.set(key, String(value));
    },
  };
}

export function readJson(storage, key, fallback) {
  try {
    const raw = storage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback; // damaged data is ignored, never fatal
  }
}

export function writeJson(storage, key, value) {
  storage.setItem(key, JSON.stringify(value));
}

/** How many items of a checklist are ticked. ``ticked`` maps item id to true. */
export function progress(list, ticked) {
  const total = list.items.length;
  const done = list.items.filter((item) => ticked && ticked[item.id] === true).length;
  return { done, total };
}

export function formatCoords(lat, lon, digits = 6) {
  return `${Number(lat).toFixed(digits)}, ${Number(lon).toFixed(digits)}`;
}

const pad = (n) => String(n).padStart(2, "0");

/** Local date and time as "2026-10-30 14:05" (what a person would write in a notebook). */
export function localStamp(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

const text = (v) => (v === undefined || v === null ? "" : String(v).trim());

/** A flight log entry from the form fields (everything optional except that it gets a time). */
export function newEntry(fields, now = new Date(), id = String(now.getTime())) {
  return {
    id,
    time: localStamp(now),
    place: text(fields.place),
    lat: text(fields.lat),
    lon: text(fields.lon),
    accuracy: text(fields.accuracy),
    mission: text(fields.mission),
    wind: text(fields.wind),
    batteryStart: text(fields.batteryStart),
    batteryEnd: text(fields.batteryEnd),
    notes: text(fields.notes),
  };
}

const CSV_COLUMNS = [
  ["time", "time"], ["place", "place"], ["latitude", "lat"], ["longitude", "lon"],
  ["accuracy_m", "accuracy"], ["mission", "mission"], ["wind_ms", "wind"],
  ["battery_start_percent", "batteryStart"], ["battery_end_percent", "batteryEnd"], ["notes", "notes"],
];

function csvCell(value) {
  const s = text(value);
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

/** The log as CSV (opens in a spreadsheet); quotes and line breaks in notes are kept intact. */
export function entriesToCsv(entries) {
  const rows = [CSV_COLUMNS.map(([name]) => name).join(",")];
  for (const e of entries) rows.push(CSV_COLUMNS.map(([, key]) => csvCell(e[key])).join(","));
  return rows.join("\r\n") + "\r\n";
}

/** The log as readable text, for pasting into a message. */
export function entriesToText(entries) {
  return entries
    .map((e) => {
      const lines = [e.time + (e.place ? `  ${e.place}` : "")];
      if (e.lat && e.lon) lines.push(`Takeoff: ${e.lat}, ${e.lon}` + (e.accuracy ? ` (about ${e.accuracy} m)` : ""));
      if (e.mission) lines.push(`Mission: ${e.mission}`);
      if (e.wind) lines.push(`Wind: ${e.wind} m/s`);
      if (e.batteryStart || e.batteryEnd) lines.push(`Battery: ${e.batteryStart || "?"}% to ${e.batteryEnd || "?"}%`);
      if (e.notes) lines.push(e.notes);
      return lines.join("\n");
    })
    .join("\n\n");
}
