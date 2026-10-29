// SPDX-FileCopyrightText: 2026 Avispria contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { CHECKLISTS } from "../../field-page/js/checklist.js";
import * as store from "../../field-page/js/store.js";

class FakeStorage {
  constructor() { this.data = new Map(); }
  getItem(k) { return this.data.has(k) ? this.data.get(k) : null; }
  setItem(k, v) { this.data.set(k, String(v)); }
  removeItem(k) { this.data.delete(k); }
}

test("every checklist item has an id and wording, and ids are unique", () => {
  const ids = new Set();
  assert.ok(CHECKLISTS.length >= 5);
  for (const list of CHECKLISTS) {
    assert.match(list.id, /^[a-z]+$/);
    assert.ok(list.title.length > 3 && list.items.length >= 4, list.id);
    for (const item of list.items) {
      assert.match(item.id, /^[a-z][a-z-]+$/, item.id);
      assert.ok(item.text.length > 10 && !item.text.includes("  "), item.id);
      assert.ok(!ids.has(item.id), `duplicate id ${item.id}`);
      ids.add(item.id);
    }
  }
});

test("the checklists carry the lessons of this project", () => {
  const all = JSON.stringify(CHECKLISTS);
  for (const must of ["ORIGINAL photos", "straight down", "timed shot", "spot-check sheet", "rules"]) {
    assert.ok(all.includes(must), must);
  }
});

test("progress counts only ticked items that exist", () => {
  const list = CHECKLISTS[0];
  assert.deepEqual(store.progress(list, {}), { done: 0, total: list.items.length });
  assert.equal(store.progress(list, { batteries: true, card: true, gone: true }).done, 2);
  assert.equal(store.progress(list, { batteries: false }).done, 0);
  assert.equal(store.progress(list, null).done, 0);
});

test("storage keeps values, and survives a phone that refuses to store anything", () => {
  const fine = store.safeStorage(new FakeStorage());
  fine.setItem("a", "1");
  assert.equal(fine.getItem("a"), "1");
  assert.equal(fine.persistent, true);

  const refusing = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); }, removeItem() {} };
  const fallback = store.safeStorage(refusing);
  assert.equal(fallback.persistent, false);
  fallback.setItem("a", "2");
  assert.equal(fallback.getItem("a"), "2"); // kept in memory for this visit
  assert.equal(store.safeStorage(null).persistent, false);
});

test("storage that fails later falls back to memory without losing the visit's data", () => {
  let broken = false;
  const flaky = {
    data: new Map(),
    getItem(k) { if (broken) throw new Error("quota"); return this.data.get(k) ?? null; },
    setItem(k, v) { if (broken) throw new Error("quota"); this.data.set(k, v); },
    removeItem() {},
  };
  const s = store.safeStorage(flaky);
  s.setItem("x", "1");
  broken = true;
  s.setItem("y", "2");
  assert.equal(s.getItem("y"), "2");
});

test("json helpers ignore damaged data", () => {
  const s = new FakeStorage();
  store.writeJson(s, store.KEYS.log, [{ a: 1 }]);
  assert.deepEqual(store.readJson(s, store.KEYS.log, []), [{ a: 1 }]);
  s.setItem(store.KEYS.log, "{not json");
  assert.deepEqual(store.readJson(s, store.KEYS.log, []), []);
  assert.deepEqual(store.readJson(s, "missing", { ok: true }), { ok: true });
});

test("coordinates are written the way Avispria reads them", () => {
  assert.equal(store.formatCoords(23.8103, 90.4125), "23.810300, 90.412500");
  assert.equal(store.formatCoords("23.81", "-90.4", 2), "23.81, -90.40");
});

test("log entries get a notebook-style local time and trimmed fields", () => {
  const entry = store.newEntry({ place: "  Field A ", lat: "23.81", lon: "90.41", wind: 3.5, notes: "ok\n" }, new Date(2026, 9, 30, 7, 5), "id1");
  assert.deepEqual(entry, {
    id: "id1", time: "2026-10-30 07:05", place: "Field A", lat: "23.81", lon: "90.41",
    accuracy: "", mission: "", wind: "3.5", batteryStart: "", batteryEnd: "", notes: "ok",
  });
});

test("the CSV quotes commas, quotes and line breaks so a spreadsheet reads it back exactly", () => {
  const entries = [
    store.newEntry({ place: "Field, north", lat: "23.8", lon: "90.4", notes: 'he said "go"\nsecond line', wind: "2" }, new Date(2026, 9, 30, 14, 5), "a"),
    store.newEntry({ place: "Plain" }, new Date(2026, 9, 30, 15, 0), "b"),
  ];
  const csv = store.entriesToCsv(entries);
  assert.equal(
    csv,
    'time,place,latitude,longitude,accuracy_m,mission,wind_ms,battery_start_percent,battery_end_percent,notes\r\n' +
      '2026-10-30 14:05,"Field, north",23.8,90.4,,,2,,,"he said ""go""\nsecond line"\r\n' +
      "2026-10-30 15:00,Plain,,,,,,,,\r\n",
  );
  assert.equal(store.entriesToCsv([]).trim().split("\r\n").length, 1); // header only
});

test("the text export reads like a notebook and skips what was left empty", () => {
  const text = store.entriesToText([
    store.newEntry({ place: "Field A", lat: "23.8", lon: "90.4", accuracy: "5", mission: "survey_01", wind: "3", batteryStart: "100", batteryEnd: "35", notes: "Clear sky" }, new Date(2026, 9, 30, 8, 30), "a"),
    store.newEntry({}, new Date(2026, 9, 30, 9, 0), "b"),
  ]);
  assert.equal(
    text,
    "2026-10-30 08:30  Field A\nTakeoff: 23.8, 90.4 (about 5 m)\nMission: survey_01\nWind: 3 m/s\nBattery: 100% to 35%\nClear sky\n\n2026-10-30 09:00",
  );
});


test("the saved theme uses the same key as the script that runs before the page is painted", () => {
  const boot = readFileSync(new URL("../../field-page/js/theme.js", import.meta.url), "utf8");
  assert.ok(boot.includes(`"${store.KEYS.theme}"`), "js/theme.js and store.js must agree on the key");
});
