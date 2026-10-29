// SPDX-FileCopyrightText: 2026 Avispria contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// Developer tool, not part of the automated gate: loads the real field page into a simulated
// phone browser (jsdom) and goes through each screen as a person would.
//
//   mkdir /tmp/domcheck && cd /tmp/domcheck && npm init -y && npm install jsdom
//   JSDOM_PATH=/tmp/domcheck/node_modules/jsdom/lib/api.js node tests/field_page/dom_check.mjs
//
// Run it after changing field-page/js/app.js. (jsdom is not a project dependency.)
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { fileURLToPath, pathToFileURL } from "node:url";

const { JSDOM } = await import(process.env.JSDOM_PATH ?? "jsdom");
const SITE = fileURLToPath(new URL("../../field-page", import.meta.url));
const calc = await import(pathToFileURL(`${SITE}/js/calc.js`).href);
const { CAMERAS } = await import(pathToFileURL(`${SITE}/js/generated.js`).href);
let run = 0;
const results = [];
const check = async (name, fn) => { try { await fn(); results.push(["ok", name]); } catch (e) { results.push(["FAIL", name, e.message.split("\n")[0]]); } };

async function load({ hash = "", seed = {}, sw = false, storage = "ok", geo = null, prefersDark = false } = {}) {
  const html = readFileSync(`${SITE}/index.html`, "utf8").replace(/<script type="module"[^>]*><\/script>/, "");
  const dom = new JSDOM(html, { url: "https://mraz11.github.io/Avispria/" + hash, pretendToBeVisual: true, runScripts: "outside-only" });
  const w = dom.window;
  w.scrollTo = () => {};
  for (const [k, v] of Object.entries(seed)) w.localStorage.setItem(k, v);
  if (storage === "refused") {
    Object.defineProperty(w, "localStorage", { get() { throw new Error("SecurityError"); } });
  }
  const copied = [];
  Object.defineProperty(w.navigator, "clipboard", { value: { writeText: async (t) => { copied.push(t); } }, configurable: true });
  w.matchMedia = (query) => ({ matches: prefersDark && query.includes("dark"), media: query });
  w.eval(readFileSync(`${SITE}/js/theme.js`, "utf8")); // the classic script that runs before the page is painted
  if (geo) Object.defineProperty(w.navigator, "geolocation", { value: geo, configurable: true });
  if (sw) Object.defineProperty(w.navigator, "serviceWorker", { value: { controller: null, register: () => Promise.resolve(), ready: Promise.resolve(), addEventListener() {} }, configurable: true });
  const def = (k, v) => Object.defineProperty(globalThis, k, { value: v, configurable: true, writable: true });
  def("window", w); def("document", w.document); def("location", w.location); def("navigator", w.navigator);
  def("confirm", () => true);
  const blobs = [];
  URL.createObjectURL = (b) => { blobs.push(b); return "blob:x"; };
  URL.revokeObjectURL = () => {};
  await import(pathToFileURL(`${SITE}/js/app.js`).href + `?run=${++run}`);
  return { w, d: w.document, copied, blobs };
}
const $ = (d, sel) => d.querySelector(sel);
const words = (n) => (n.nodeType === 3 ? n.textContent : [...n.childNodes].map(words).join(" "));
const text = (el) => words(el).replace(/\s+/g, " ").trim();
const type = (w, el, value) => { el.value = value; el.dispatchEvent(new w.Event("input", { bubbles: true })); };
const click = (w, el) => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
const button = (d, label) => [...d.querySelectorAll("button")].find((b) => text(b) === label);
const visible = (d) => [...d.querySelectorAll("section.view")].filter((s) => !s.hidden).map((s) => s.id);

await check("starts on the checklist with the first list open and nothing ticked", async () => {
  const { d } = await load();
  assert.deepEqual(visible(d), ["view-checklist"]);
  assert.equal($(d, '.tabs a[aria-current="page"]').dataset.tab, "checklist");
  const lists = [...d.querySelectorAll("#view-checklist details")];
  assert.equal(lists.length, 5);
  assert.equal(lists[0].open, true); assert.equal(lists[1].open, false);
  assert.equal(text(lists[0].querySelector(".count")), "0 of 5");
  assert.equal(d.title, "Checklists - Avispria Field");
});

await check("ticking is counted, kept on the phone, and survives a reload", async () => {
  const first = await load();
  const box = first.d.getElementById("tick-batteries");
  box.checked = true; box.dispatchEvent(new first.w.Event("change", { bubbles: true }));
  assert.equal(text(first.d.querySelector("details .count")), "1 of 5");
  const saved = first.w.localStorage.getItem("avispria.checklist.v1");
  assert.equal(JSON.parse(saved).batteries, true);
  const second = await load({ seed: { "avispria.checklist.v1": saved } });
  assert.equal(second.d.getElementById("tick-batteries").checked, true);
  assert.equal(text(second.d.querySelector("details .count")), "1 of 5");
  click(second.w, button(second.d, "Untick all"));
  assert.equal(second.d.getElementById("tick-batteries").checked, false);
  assert.equal(text(second.d.querySelector("details .count")), "0 of 5");
});

await check("damaged saved data is ignored instead of breaking the page", async () => {
  const { d } = await load({ seed: { "avispria.checklist.v1": "{oops", "avispria.log.v1": "42", "avispria.settings.v1": "[]" } });
  assert.deepEqual(visible(d), ["view-checklist"]);
  assert.match(text($(d, "#view-log")), /No flights written down yet/);
});

await check("the tabs switch screens, and an unknown address falls back to the checklist", async () => {
  const { d, w } = await load({ hash: "#/calc" });
  assert.deepEqual(visible(d), ["view-calc"]);
  w.location.hash = "#/log"; w.dispatchEvent(new w.HashChangeEvent("hashchange"));
  assert.deepEqual(visible(d), ["view-log"]);
  assert.equal($(d, '.tabs a[aria-current="page"]').dataset.tab, "log");
  w.location.hash = "#/nonsense"; w.dispatchEvent(new w.HashChangeEvent("hashchange"));
  assert.deepEqual(visible(d), ["view-checklist"]);
});

await check("the calculators show the planner's numbers and update as you type", async () => {
  const { d, w } = await load({ hash: "#/calc" });
  const cam = CAMERAS["lito-x1"];
  const out = () => text($(d, "#view-calc"));
  assert.ok(out().includes(`${(calc.gsd(cam, "12mp", 60) * 100).toFixed(2)} cm/px`), out().slice(0, 400));
  type(w, d.getElementById("f-height"), "40");
  assert.ok(out().includes(`${(calc.gsd(cam, "12mp", 40) * 100).toFixed(2)} cm/px`));
  const sp = calc.spacing(cam, "12mp", 40, 0.8, 0.7);
  assert.ok(out().includes(`Take a photo every ${sp.photo.toFixed(1)} m`) && out().includes(`Fly the lines every ${sp.line.toFixed(1)} m`));
  type(w, d.getElementById("f-wanted"), "2");
  assert.ok(out().includes(`Height needed ${calc.heightForGsd(cam, "12mp", 0.02).toFixed(0)} m`));
  const e = calc.estimateSurvey(cam, "12mp", { width: 200, length: 300, height: 40, front: 0.8, side: 0.7, shutter: 0.001, wind: 0, batteryMin: 20 });
  assert.ok(out().includes(`Flight lines ${e.strips}`) && out().includes(`Photos about ${e.totalPhotos}`) && out().includes(`Batteries (missions) ${e.missions.length}`));
  assert.ok(/Fly at \d+\.\d m\/s/.test(out()) && /Timed shot every \d+\.\d s or less/.test(out()));
});

await check("typing nonsense gives a plain message, not a crash", async () => {
  const { d, w } = await load({ hash: "#/calc" });
  type(w, d.getElementById("f-height"), "abc");
  assert.match(text($(d, "#view-calc")), /Enter a number for "Height above the ground"/);
  type(w, d.getElementById("f-height"), "60"); type(w, d.getElementById("f-shutter"), "fast");
  assert.match(text($(d, "#view-calc")), /Enter the shutter time like 1\/1000/);
  type(w, d.getElementById("f-shutter"), "1/1000"); type(w, d.getElementById("f-wind"), "7");
  assert.match(text($(d, "#view-calc")), /Not flyable like this/);
  type(w, d.getElementById("f-front"), "100");
  assert.match(text($(d, "#view-calc")), /overlap must be from 0 to under 100%/);
});

await check("a decimal comma works, as on many phones", async () => {
  const { d, w } = await load({ hash: "#/calc" });
  type(w, d.getElementById("f-height"), "60,5");
  assert.ok(text($(d, "#view-calc")).includes(`${(calc.gsd(CAMERAS["lito-x1"], "12mp", 60.5) * 100).toFixed(2)} cm/px`));
});

await check("trees: the plan is shown to be too optimistic, with the height that fixes it", async () => {
  const { d, w } = await load({ hash: "#/calc" });
  type(w, d.getElementById("f-height"), "80"); type(w, d.getElementById("f-canopy"), "25");
  const t = text($(d, "#view-calc"));
  assert.match(t, /Height above the treetops 55 m/);
  assert.match(t, /Overlap between lines \d+% \(planned 70%\)/);
  assert.match(t, /fly at 105 m above the takeoff point/);
  assert.match(t, /Overlap under about 65% makes the 3D model unreliable/);
});

await check("choosing an unverified aircraft warns, and the choice is remembered", async () => {
  const first = await load({ hash: "#/calc" });
  const unverified = first.d.querySelector("#view-calc .notice");
  assert.equal(unverified.hidden, true);
  const sel = first.d.getElementById("aircraft");
  sel.value = "mini-4-pro"; sel.dispatchEvent(new first.w.Event("change", { bubbles: true }));
  assert.equal(unverified.hidden, false);
  type(first.w, first.d.getElementById("f-height"), "45");
  const second = await load({ hash: "#/calc", seed: { "avispria.settings.v1": first.w.localStorage.getItem("avispria.settings.v1") } });
  assert.equal(second.d.getElementById("aircraft").value, "mini-4-pro");
  assert.equal(second.d.getElementById("f-height").value, "45");
  const cam = CAMERAS["mini-4-pro"];
  assert.ok(text($(second.d, "#view-calc")).includes(`${(calc.gsd(cam, "12mp", 45) * 100).toFixed(2)} cm/px`));
});

await check("the flight log: save, read back, copy coordinates, export CSV, delete", async () => {
  const { d, w, copied, blobs } = await load({ hash: "#/log" });
  type(w, d.getElementById("l-place"), "Field, north");
  type(w, d.getElementById("l-lat"), "23.8103"); type(w, d.getElementById("l-lon"), "90,4125");
  type(w, d.getElementById("l-wind"), "3"); type(w, d.getElementById("l-notes"), 'he said "go"');
  click(w, button(d, "Save this flight"));
  assert.equal(d.getElementById("l-place").value, ""); // the form is cleared: no accidental duplicate
  const view = text($(d, "#view-log"));
  assert.match(view, /Field, north/); assert.match(view, /Takeoff: 23.8103, 90.4125/); assert.match(view, /Wind: 3 m\/s/);
  assert.equal(JSON.parse(w.localStorage.getItem("avispria.log.v1")).length, 1);
  click(w, button(d, "Copy coordinates")); await new Promise((r) => setTimeout(r, 10));
  assert.deepEqual(copied, ["23.810300, 90.412500"]);
  click(w, button(d, "Download CSV"));
  const csv = (await blobs[0].text()).replace(/^\ufeff/, "");
  assert.ok(csv.startsWith("time,place,latitude,longitude"), csv.slice(0, 60));
  assert.ok(csv.includes('"Field, north",23.8103,90.4125') && csv.includes('"he said ""go"""'));
  click(w, button(d, "Delete"));
  assert.match(text($(d, "#view-log")), /No flights written down yet/);
});

await check("bad coordinates are refused and nothing is saved", async () => {
  const { d, w } = await load({ hash: "#/log" });
  type(w, d.getElementById("l-lat"), "abc"); click(w, button(d, "Save this flight"));
  assert.match(text($("#toast".length ? d : d, "#toast")), /Check the coordinates/);
  type(w, d.getElementById("l-lat"), "95"); type(w, d.getElementById("l-lon"), "10"); click(w, button(d, "Save this flight"));
  assert.equal(w.localStorage.getItem("avispria.log.v1"), null);
});

await check("Use my location fills in the takeoff point; a refusal is explained", async () => {
  const ok = await load({ hash: "#/log", geo: { getCurrentPosition: (good) => good({ coords: { latitude: 23.8103123, longitude: 90.4125456, accuracy: 7.4 } }) } });
  click(ok.w, button(ok.d, "Use my location"));
  assert.equal(ok.d.getElementById("l-lat").value, "23.810312"); assert.equal(ok.d.getElementById("l-lon").value, "90.412546");
  assert.equal(ok.d.getElementById("l-accuracy").value, "7");
  const no = await load({ hash: "#/log", geo: { getCurrentPosition: (_g, bad) => bad({ code: 1 }) } });
  click(no.w, button(no.d, "Use my location"));
  assert.match(text($(no.d, "#view-log")), /Location permission was refused/);
});

await check("text typed into the log is shown as text, never run as HTML", async () => {
  const { d, w } = await load({ hash: "#/log" });
  const scriptsBefore = d.querySelectorAll("script").length; // the page's own (the theme script)
  type(w, d.getElementById("l-place"), "<img src=x onerror=alert(1)>");
  type(w, d.getElementById("l-notes"), "<script>alert(2)</script>");
  click(w, button(d, "Save this flight"));
  assert.equal(d.querySelectorAll("#view-log img").length, 0);
  assert.equal(d.querySelectorAll("script").length, scriptsBefore); // saving text adds none
  assert.match(text($(d, "#view-log .entry")), /<img src=x onerror=alert\(1\)>/);
});

await check("a phone that refuses storage still gets a working page, and is told", async () => {
  const { d } = await load({ hash: "#/log", storage: "refused" });
  assert.match(text($(d, "#view-log")), /would not store data/);
  assert.deepEqual(visible(d), ["view-log"]);
});

await check("About: version, offline status and the install button", async () => {
  const none = await load({ hash: "#/about" });
  assert.match(text($(none.d, "#view-about")), /Offline use is not available in this browser/);
  const sw = await load({ hash: "#/about", sw: true });
  await new Promise((r) => setTimeout(r, 10));
  assert.match(text($(sw.d, "#view-about")), /Ready: this page works without a signal/);
  const install = button(sw.d, "Install on this phone");
  assert.equal(install.hidden, true);
  const event = new sw.w.Event("beforeinstallprompt"); event.prompt = () => {}; event.userChoice = Promise.resolve({});
  sw.w.dispatchEvent(event);
  assert.equal(install.hidden, false);
  assert.match(text($(sw.d, "#view-about")), /Version \d/);
  const link = sw.d.querySelector('#view-about a[href^="https://github.com"]');
  assert.equal(link.href, "https://github.com/Mraz11/Avispria");
});

await check("the saved choice, else the phone's setting, decides the mode before anything is drawn", async () => {
  const theme = async (opts) => (await load(opts)).d.documentElement.getAttribute("data-theme");
  assert.equal(await theme({}), "light");
  assert.equal(await theme({ prefersDark: true }), "dark");
  assert.equal(await theme({ prefersDark: true, seed: { "avispria.theme": "light" } }), "light"); // a saved choice wins
  assert.equal(await theme({ seed: { "avispria.theme": "dark" } }), "dark");
  assert.equal(await theme({ prefersDark: true, storage: "refused" }), "dark"); // no storage: the phone's setting
});

await check("the switch changes the mode, remembers it, and colours the browser's own bar", async () => {
  const { d, w } = await load({ prefersDark: true });
  const root = d.documentElement, button = d.getElementById("theme-toggle");
  assert.equal(root.getAttribute("data-theme"), "dark"); assert.equal(button.getAttribute("aria-pressed"), "true");
  click(w, button);
  assert.equal(root.getAttribute("data-theme"), "light"); assert.equal(button.getAttribute("aria-pressed"), "false");
  assert.equal(w.localStorage.getItem("avispria.theme"), "light");
  assert.ok([...d.querySelectorAll('meta[name="theme-color"]')].every((m) => m.getAttribute("content") === "#FFFFFF"));
  click(w, button);
  assert.equal(root.getAttribute("data-theme"), "dark"); assert.equal(w.localStorage.getItem("avispria.theme"), "dark");
  assert.ok([...d.querySelectorAll('meta[name="theme-color"]')].every((m) => m.getAttribute("content") === "#1F2937"));
  const next = await load({ seed: { "avispria.theme": w.localStorage.getItem("avispria.theme") } }); // a later visit
  assert.equal(next.d.documentElement.getAttribute("data-theme"), "dark");
});

await check("the header has the logo in both variants and the export buttons are the second colour", async () => {
  const { d } = await load({ hash: "#/log" });
  const logos = [...d.querySelectorAll("header img.logo")];
  assert.deepEqual(logos.map((i) => i.getAttribute("src")), ["img/logo.png", "img/logo-dark.png"]);
  assert.equal(logos[0].getAttribute("alt"), "Avispria logo"); assert.equal(logos[1].getAttribute("alt"), "");
  for (const label of ["Copy all as text", "Download CSV"]) assert.ok(button(d, label).classList.contains("secondary"), label);
  assert.ok(button(d, "Save this flight").classList.contains("primary"));
  assert.ok(button(d, "Delete all").classList.contains("danger"));
});

for (const r of results) console.log(r[0].padEnd(5), r[1], r[2] ? `\n      -> ${r[2]}` : "");
console.log(`\n${results.filter((r) => r[0] === "ok").length} of ${results.length} behaviours work`);
process.exit(results.some((r) => r[0] !== "ok") ? 1 : 0);
