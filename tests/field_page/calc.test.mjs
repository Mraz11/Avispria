// SPDX-FileCopyrightText: 2026 Avispria contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// Run with: node --test tests/field_page/
// The expected numbers in golden.json come from the real Python planner (scripts/field_page.py).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import * as calc from "../../field-page/js/calc.js";
import { CAMERAS } from "../../field-page/js/generated.js";

const golden = JSON.parse(readFileSync(new URL("./golden.json", import.meta.url), "utf8"));

function close(actual, expected, rel = 1e-9, what = "") {
  const ok = Math.abs(actual - expected) <= rel * Math.max(1, Math.abs(expected));
  assert.ok(ok, `${what} ${actual} is not within ${rel} of ${expected}`);
}

test("the golden file covers every aircraft and photo size", () => {
  const seen = new Set(golden.camera.map((c) => `${c.camera}/${c.mode}`));
  for (const [key, cam] of Object.entries(CAMERAS)) {
    for (const mode of Object.keys(cam.modes)) assert.ok(seen.has(`${key}/${mode}`), `${key}/${mode}`);
  }
});

test("resolution, footprint and spacing match the planner", () => {
  for (const c of golden.camera) {
    const cam = CAMERAS[c.camera];
    const where = `${c.camera}/${c.mode}@${c.height}`;
    close(calc.gsd(cam, c.mode, c.height), c.gsd_m, 1e-10, where);
    const fp = calc.footprint(cam, c.mode, c.height);
    close(fp.across, c.across, 1e-10, where);
    close(fp.along, c.along, 1e-10, where);
    const sp = calc.spacing(cam, c.mode, c.height, 0.8, 0.7);
    close(sp.photo, c.photo_m, 1e-10, where);
    close(sp.line, c.line_m, 1e-10, where);
  }
});

test("the height for a wanted resolution matches the planner", () => {
  for (const c of golden.height) {
    close(calc.heightForGsd(CAMERAS[c.camera], c.mode, c.gsd_cm / 100), c.height, 1e-10, `${c.camera}/${c.mode}`);
  }
});

test("height and resolution are each other's inverse", () => {
  const cam = CAMERAS["lito-x1"];
  for (const h of [20, 55.5, 120]) close(calc.heightForGsd(cam, "12mp", calc.gsd(cam, "12mp", h)), h, 1e-10);
});

test("the speed limits and the binding one match the planner", () => {
  assert.equal(golden.speed.length, 48);
  for (const c of golden.speed) {
    const cam = CAMERAS[c.camera];
    const where = JSON.stringify([c.mode, c.height, c.front, c.shutter, c.wind]);
    const got = calc.solveSpeed(cam, c.mode, calc.gsd(cam, c.mode, c.height), c.shutter, c.photo_m, c.wind);
    close(got.speed, c.speed, 1e-10, where);
    assert.equal(got.binding, c.binding, where);
    assert.equal(got.feasible, c.feasible, where);
    close(got.limits["motion blur"], c.limits.blur, 1e-10, where);
    close(got.limits["rolling-shutter skew"], c.limits.skew, 1e-10, where);
    close(got.limits["camera photo interval"], c.limits.trigger, 1e-10, where);
    close(got.limits["wind headroom"], c.limits.wind, 1e-10, where);
  }
});

test("too much wind makes a plan infeasible, as in the planner", () => {
  const cam = CAMERAS["lito-x1"];
  const s = calc.solveSpeed(cam, "12mp", 0.02, 1 / 1000, 12, 7);
  assert.equal(s.feasible, false);
  assert.equal(s.speed, calc.MIN_SPEED);
  assert.equal(s.binding, "wind headroom");
});

test("a survey is laid out and timed like the planner does", () => {
  assert.equal(golden.survey.length, 5);
  for (const c of golden.survey) {
    const cam = CAMERAS[c.camera];
    const where = `${c.width}x${c.length}@${c.height}`;
    const got = calc.estimateSurvey(cam, c.mode, {
      width: c.width, length: c.length, height: c.height, front: c.front, side: c.side,
      shutter: c.shutter, wind: c.wind, batteryMin: c.battery_min,
    });
    assert.equal(got.feasible, true, where);
    assert.equal(got.strips, c.strips, `${where} strips`);
    close(got.photoM, c.photo_m, 1e-10, `${where} photo spacing`);
    close(got.lineM, c.line_m, 1e-10, `${where} line spacing`);
    close(got.speed, c.speed, 1e-10, `${where} speed`);
    assert.equal(got.binding, c.binding, `${where} limit`);
    close(got.intervalS, c.interval_s, 1e-9, `${where} interval`);
    assert.equal(got.missions.length, c.missions.length, `${where} missions`);
    got.missions.forEach((m, i) => {
      close(m.minutes, c.missions[i].minutes, 0.015, `${where} mission ${i} minutes`);
      assert.ok(Math.abs(m.photos - c.missions[i].photos) <= 2, `${where} mission ${i} photos ${m.photos} vs ${c.missions[i].photos}`);
    });
    close(got.totalMinutes, c.total_minutes, 0.015, `${where} total minutes`);
  }
});

test("trees make the real overlap smaller than planned", () => {
  for (const c of golden.canopy) {
    const got = calc.canopyEffect(CAMERAS[c.camera], c.mode, {
      flight: c.flight, canopy: c.canopy, front: c.front, side: c.side,
    });
    close(got.above, c.above, 1e-10);
    close(got.gsdCanopy, c.gsd_canopy_m, 1e-10);
    close(got.gsdGround, c.gsd_ground_m, 1e-10);
    close(got.frontActual, c.front_actual, 1e-10);
    close(got.sideActual, c.side_actual, 1e-10);
  }
  const bare = calc.canopyEffect(CAMERAS["lito-x1"], "12mp", { flight: 60, canopy: 0, front: 0.8, side: 0.7 });
  close(bare.frontActual, 0.8, 1e-10); // no trees: the plan holds
  close(bare.sideActual, 0.7, 1e-10);
  const forest = calc.canopyEffect(CAMERAS["lito-x1"], "12mp", { flight: 80, canopy: 25, front: 0.8, side: 0.7 });
  assert.ok(forest.sideActual < 0.6, "25 m of trees under an 80 m flight cut the side overlap well below 70%");
});

test("flying over the canopy needs the canopy height added", () => {
  assert.equal(calc.heightOverCanopy(60, 25), 85);
  assert.throws(() => calc.heightOverCanopy(0, 25), /more than zero/);
  assert.throws(() => calc.heightOverCanopy(60, -1), /canopy height/);
});

test("nonsense input is refused with a clear message", () => {
  const cam = CAMERAS["lito-x1"];
  assert.throws(() => calc.gsd(cam, "12mp", 0), /height must be more than zero/);
  assert.throws(() => calc.gsd(cam, "99mp", 50), /unknown photo size/);
  assert.throws(() => calc.spacing(cam, "12mp", 50, 1, 0.7), /front overlap/);
  assert.throws(() => calc.spacing(cam, "12mp", 50, 0.8, -0.1), /side overlap/);
  assert.throws(() => calc.solveSpeed(cam, "12mp", 0.02, 0, 10, 0), /shutter time/);
  assert.throws(() => calc.solveSpeed(cam, "12mp", 0.02, 0.001, 10, -1), /wind/);
  assert.throws(() => calc.canopyEffect(cam, "12mp", { flight: 20, canopy: 25, front: 0.8, side: 0.7 }), /fly higher/);
  assert.throws(() => calc.estimateSurvey(cam, "12mp", { width: 0, length: 100, height: 50, front: 0.8, side: 0.7, shutter: 0.001 }), /area width/);
});

test("an impossible survey says so instead of inventing a time", () => {
  const cam = CAMERAS["lito-x1"];
  const got = calc.estimateSurvey(cam, "12mp", { width: 100, length: 100, height: 50, front: 0.8, side: 0.7, shutter: 0.001, wind: 7 });
  assert.equal(got.feasible, false);
  assert.deepEqual(got.missions, []);
});

test("numbers typed on a phone are read forgivingly", () => {
  const cases = [["60", 60], [" 60.5 ", 60.5], ["2,5", 2.5], [".5", 0.5], ["-3", -3], [7, 7]];
  for (const [text, expected] of cases) assert.equal(calc.parseNumber(text), expected, String(text));
  for (const bad of ["", "abc", "1.2.3", "1e3", "12 m", null, undefined, NaN]) assert.equal(calc.parseNumber(bad), null, String(bad));
});

test("shutter times are read as 1/1000 or 0.001", () => {
  assert.equal(calc.parseShutter("1/1000"), 0.001);
  assert.equal(calc.parseShutter(" 1/2000 "), 0.0005);
  assert.equal(calc.parseShutter("0.004"), 0.004);
  for (const bad of ["", "fast", "1/0", "0", "-1/100", "5", "1/"]) assert.equal(calc.parseShutter(bad), null, bad);
});
