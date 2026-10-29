// SPDX-FileCopyrightText: 2026 Avispria contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// The screens of the field page. Everything stays on the phone: no network calls, no tracking.
// Text is always set with textContent (never as HTML), so nothing typed can run as code.
import * as calc from "./calc.js";
import { CHECKLISTS } from "./checklist.js";
import { AVISPRIA_VERSION, CAMERAS } from "./generated.js";
import * as store from "./store.js";

const REPO = "https://github.com/Mraz11/Avispria";
const LIMIT_WORDS = {
  "motion blur": ["motion blur", "A slower shutter would smear the photos at a higher speed."],
  "rolling-shutter skew": ["sensor readout", "The sensor reads the picture out too slowly for a higher speed."],
  "camera photo interval": ["camera interval", "The camera cannot take photos any faster than this."],
  "wind headroom": ["wind reserve", "Half of the drone's top speed is kept spare for wind."],
  "drone maximum": ["top speed", "This is the drone's own top speed."],
};

let backing = null;
try {
  backing = window.localStorage;
} catch {
  backing = null; // some browsers refuse storage: the page still works for this visit
}
const storage = store.safeStorage(backing);
const settings = { aircraft: "lito-x1", mode: "12mp", ...store.readJson(storage, store.KEYS.settings, {}) };
if (!settings.inputs || typeof settings.inputs !== "object") settings.inputs = {};
const saveSettings = () => store.writeJson(storage, store.KEYS.settings, settings);

/** Build an element. Strings and numbers become text nodes; ``text`` sets textContent. */
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const toastEl = document.getElementById("toast");
let toastTimer = 0;
function toast(message, action) {
  toastEl.replaceChildren(h("span", { text: message }));
  if (action) toastEl.append(h("button", { type: "button", text: action.label, onclick: action.run }));
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  if (!action) toastTimer = setTimeout(() => (toastEl.hidden = true), 3500);
}

async function copyText(text, done = "Copied") {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = h("textarea", { "aria-hidden": "true" });
    area.value = text;
    document.body.append(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    area.remove();
    if (!ok) return toast("Could not copy. Select the text and copy it by hand.");
  }
  toast(done);
}

const fmt = (x, digits = 1) => Number(x).toFixed(digits);
const percent = (x) => `${Math.round(x * 100)}%`;

// ------------------------------------------------------------------ checklists
function buildChecklist() {
  const ticked = store.readJson(storage, store.KEYS.checklist, {});
  const save = () => store.writeJson(storage, store.KEYS.checklist, ticked);
  const section = h("section", { class: "view", id: "view-checklist", hidden: true },
    h("h2", { text: "Checklists" }),
    h("p", { class: "hint", text: "Tick items as you go. Your ticks stay on this phone. Rules and safety are your responsibility." }),
  );
  CHECKLISTS.forEach((list, index) => {
    const bar = h("progress", { max: list.items.length, value: 0, "aria-hidden": "true" });
    const count = h("span", { class: "count" });
    const items = h("div", { class: "items" });
    const refresh = () => {
      const p = store.progress(list, ticked);
      bar.max = p.total;
      bar.value = p.done;
      count.textContent = `${p.done} of ${p.total}`;
    };
    for (const item of list.items) {
      const box = h("input", { type: "checkbox", id: `tick-${item.id}` });
      box.checked = ticked[item.id] === true;
      box.addEventListener("change", () => {
        ticked[item.id] = box.checked;
        save();
        refresh();
      });
      items.append(h("label", { class: "item", for: `tick-${item.id}` }, box,
        h("span", { class: "text" }, item.text, item.note ? h("small", { text: item.note }) : null)));
    }
    const untick = h("button", { type: "button", class: "link", text: "Untick all", onclick: () => {
      for (const item of list.items) ticked[item.id] = false;
      items.querySelectorAll("input").forEach((box) => (box.checked = false));
      save();
      refresh();
    } });
    section.append(h("details", { class: "card", open: index === 0 }, h("summary", {}, h("div", { class: "head" }, h("span", { class: "title", text: list.title }), count, bar)),
      list.note ? h("p", { class: "hint", text: list.note }) : null, items, h("div", { class: "actions" }, untick)));
    refresh();
  });
  return section;
}

// ------------------------------------------------------------------ calculators
function buildCalc() {
  const section = h("section", { class: "view", id: "view-calc", hidden: true });
  const aircraft = h("select", { id: "aircraft" });
  for (const [key, cam] of Object.entries(CAMERAS)) {
    aircraft.append(h("option", { value: key, text: cam.name + (cam.verified ? "" : " (numbers not verified)") }));
  }
  const mode = h("select", { id: "mode" });
  const unverified = h("p", { class: "notice", hidden: true, text: "The camera numbers for this aircraft are not verified yet, so the results are only approximate." });
  const fillModes = () => {
    const modes = Object.keys(CAMERAS[aircraft.value].modes);
    mode.replaceChildren(...modes.map((m) => h("option", { value: m, text: m.replace("mp", " MP") })));
    mode.value = modes.includes(settings.mode) ? settings.mode : modes.includes("12mp") ? "12mp" : modes[0];
    unverified.hidden = CAMERAS[aircraft.value].verified;
  };
  aircraft.value = CAMERAS[settings.aircraft] ? settings.aircraft : Object.keys(CAMERAS)[0];

  const inputs = {};
  const field = (id, label, unit, fallback, hint) => {
    const input = h("input", { id: `f-${id}`, type: "text", inputmode: "decimal", autocomplete: "off", autocapitalize: "off" });
    input.value = String(settings.inputs[id] ?? fallback);
    input.addEventListener("input", () => {
      settings.inputs[id] = input.value;
      saveSettings();
      update();
    });
    inputs[id] = input;
    return h("label", { class: "field", for: `f-${id}` }, h("span", { class: "label", text: label }),
      h("span", { class: "control" }, input, unit ? h("span", { class: "unit", text: unit }) : null), hint ? h("small", { text: hint }) : null);
  };
  const outputs = {};
  const card = (id, title, intro, ...body) => {
    outputs[id] = h("div", { "aria-live": "polite" });
    return h("section", { class: "card" }, h("h3", { text: title }), intro ? h("p", { class: "hint", text: intro }) : null, ...body, outputs[id]);
  };
  const rows = (pairs) => h("dl", { class: "results" }, pairs.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: v })]));
  const num = (id, name) => {
    const value = calc.parseNumber(inputs[id].value);
    if (value === null) throw new Error(`Enter a number for "${name}".`);
    return value;
  };

  const flight = h("section", { class: "card" }, h("h3", { text: "Your flight" }),
    h("div", { class: "grid" },
      field("height", "Height above the ground", "m", 60, "or above the treetops"),
      field("front", "Overlap along the line", "%", 80),
      field("side", "Overlap between lines", "%", 70),
      field("shutter", "Shutter time", "s", "1/1000", "like 1/1000"),
      field("wind", "Wind", "m/s", 0)));
  const resolution = card("resolution", "What you get", "For the height above.");
  const speed = card("speed", "Speed and timed shot", "How fast you can fly, and how often the camera must shoot.");
  const wanted = card("wanted", "Height for a resolution", "Work backwards from the detail you need.",
    h("div", { class: "grid" }, field("wanted", "Resolution I want", "cm/px", 2)));
  const survey = card("survey", "How long will a survey take?", "A rectangle, flown with the lines along its long side.",
    h("div", { class: "grid" }, field("width", "Area width", "m", 200), field("length", "Area length", "m", 300), field("battery", "Usable flying time per battery", "min", 20)));
  const trees = card("trees", "Trees or buildings", "A plan made for flat ground is too optimistic over trees: the surface is closer than assumed.",
    h("div", { class: "grid" }, field("canopy", "Height of the trees", "m", 0)));

  const update = () => {
    const cam = CAMERAS[aircraft.value];
    const m = mode.value;
    const show = (id, build) => {
      try {
        outputs[id].replaceChildren(build());
      } catch (error) {
        outputs[id].replaceChildren(h("p", { class: "problem", text: error.message }));
      }
    };
    const get = () => ({
      height: num("height", "Height above the ground"),
      front: num("front", "Overlap along the line") / 100,
      side: num("side", "Overlap between lines") / 100,
      shutter: calc.parseShutter(inputs.shutter.value) ?? (() => { throw new Error('Enter the shutter time like 1/1000.'); })(),
      wind: num("wind", "Wind"),
    });
    show("resolution", () => {
      const f = get();
      const fp = calc.footprint(cam, m, f.height);
      const sp = calc.spacing(cam, m, f.height, f.front, f.side);
      return rows([
        ["Ground resolution", `${fmt(calc.gsd(cam, m, f.height) * 100, 2)} cm/px`],
        ["One photo covers", `${fmt(fp.across, 0)} by ${fmt(fp.along, 0)} m`],
        ["Take a photo every", `${fmt(sp.photo)} m`],
        ["Fly the lines every", `${fmt(sp.line)} m`],
      ]);
    });
    show("speed", () => {
      const f = get();
      const sp = calc.spacing(cam, m, f.height, f.front, f.side);
      const s = calc.solveSpeed(cam, m, calc.gsd(cam, m, f.height), f.shutter, sp.photo, f.wind);
      const [short, long] = LIMIT_WORDS[s.binding];
      if (!s.feasible) {
        return h("p", { class: "problem", text: `Not flyable like this: the slowest limit (${short}) is below 1 m/s. Try less wind, a faster shutter, more height or less overlap.` });
      }
      const v = Math.floor(s.speed * 10 + 1e-9) / 10; // DJI Fly sets speed in 0.1 m/s steps
      return h("div", {}, rows([
        ["Fly at", `${fmt(v)} m/s`],
        ["Timed shot every", `${fmt(Math.floor((sp.photo / v) * 10) / 10)} s or less`],
        ["Limited by", short],
      ]), h("p", { class: "hint", text: long }));
    });
    show("wanted", () => {
      const needed = calc.heightForGsd(cam, m, num("wanted", "Resolution I want") / 100);
      return h("div", {}, rows([["Height needed", `${fmt(needed, 0)} m`]]), h("p", { class: "hint", text: "Above the ground (or above the treetops)." }),
        needed > 120 ? h("p", { class: "notice", text: "That is high. Many places limit flights to about 120 m: check the rule where you fly." }) : null);
    });
    show("survey", () => {
      const f = get();
      const e = calc.estimateSurvey(cam, m, { ...f, width: num("width", "Area width"), length: num("length", "Area length"), batteryMin: num("battery", "Usable flying time per battery") });
      if (!e.feasible) return h("p", { class: "problem", text: `Not flyable like this: the speed would be below 1 m/s (limited by ${LIMIT_WORDS[e.binding][0]}).` });
      return h("div", {}, rows([
        ["Flight lines", String(e.strips)],
        ["Photos", `about ${e.totalPhotos}`],
        ["Flying time", `about ${fmt(e.totalMinutes, 0)} min`],
        ["Batteries (missions)", String(e.missions.length)],
      ]), h("p", { class: "hint", text: e.missions.map((x, i) => `Mission ${i + 1}: about ${fmt(x.minutes, 0)} min`).join(" · ") }),
      h("p", { class: "hint", text: "A plan made in Avispria will be close to this. Add time for takeoff, landing and changing batteries." }));
    });
    show("trees", () => {
      const f = get();
      const canopy = num("canopy", "Height of the trees");
      if (canopy === 0) return h("p", { class: "hint", text: "No trees: the plan holds as calculated." });
      const e = calc.canopyEffect(cam, m, { flight: f.height, canopy, front: f.front, side: f.side });
      const weak = e.frontActual < 0.65 || e.sideActual < 0.65; // WebODM asks for at least 65%
      return h("div", {}, rows([
        ["Height above the treetops", `${fmt(e.above, 0)} m`],
        ["Resolution at the treetops", `${fmt(e.gsdCanopy * 100, 2)} cm/px`],
        ["Overlap along the line", `${percent(e.frontActual)} (planned ${percent(f.front)})`],
        ["Overlap between lines", `${percent(e.sideActual)} (planned ${percent(f.side)})`],
      ]), weak ? h("p", { class: "notice", text: "Overlap under about 65% makes the 3D model unreliable. Fly higher, or space the lines closer." }) : null,
      h("div", { class: "result-box" }, h("p", { text: `To really have ${fmt(f.height, 0)} m above the treetops, fly at ${fmt(calc.heightOverCanopy(f.height, canopy), 0)} m above the takeoff point.` })));
    });
  };

  aircraft.addEventListener("change", () => {
    settings.aircraft = aircraft.value;
    fillModes();
    settings.mode = mode.value;
    saveSettings();
    update();
  });
  mode.addEventListener("change", () => {
    settings.mode = mode.value;
    saveSettings();
    update();
  });
  fillModes();
  section.append(h("h2", { text: "Calculators" }),
    h("div", { class: "card" }, h("div", { class: "grid" },
      h("label", { class: "field", for: "aircraft" }, h("span", { class: "label", text: "Aircraft" }), aircraft),
      h("label", { class: "field", for: "mode" }, h("span", { class: "label", text: "Photo size" }), mode)), unverified),
    flight, resolution, speed, wanted, survey, trees);
  update();
  return section;
}

// -------------------------------------------------------------------- flight log
function buildLog() {
  let entries = store.readJson(storage, store.KEYS.log, []);
  if (!Array.isArray(entries)) entries = [];
  const section = h("section", { class: "view", id: "view-log", hidden: true });
  const f = {};
  const input = (id, label, props = {}) => {
    f[id] = h(props.area ? "textarea" : "input", { id: `l-${id}`, ...(props.area ? {} : { type: "text", inputmode: props.mode ?? "text" }), autocomplete: "off" });
    return h("label", { class: "field", for: `l-${id}` }, h("span", { class: "label", text: label }), f[id], props.hint ? h("small", { text: props.hint }) : null);
  };
  const status = h("p", { class: "hint" });
  const locate = h("button", { type: "button", class: "primary wide", text: "Use my location", onclick: () => {
    if (!navigator.geolocation) return (status.textContent = "This browser cannot find your location. Type the coordinates instead.");
    status.textContent = "Finding your location (this can take a few seconds outdoors)...";
    locate.disabled = true;
    navigator.geolocation.getCurrentPosition((pos) => {
      f.lat.value = pos.coords.latitude.toFixed(6);
      f.lon.value = pos.coords.longitude.toFixed(6);
      f.accuracy.value = String(Math.round(pos.coords.accuracy));
      status.textContent = `Found: about ${Math.round(pos.coords.accuracy)} m accurate.`;
      locate.disabled = false;
    }, (error) => {
      status.textContent = error.code === 1 ? "Location permission was refused. You can type the coordinates instead." : "Could not find your location. Try outdoors, or type the coordinates.";
      locate.disabled = false;
    }, { enableHighAccuracy: true, timeout: 25000, maximumAge: 0 });
  } });
  const list = h("div");
  const save = () => store.writeJson(storage, store.KEYS.log, entries);
  const entryNode = (e) =>
    h("div", { class: "entry" },
      h("div", { class: "when", text: e.time + (e.place ? `  ${e.place}` : "") }),
      h("div", { class: "meta", text: store.entriesToText([{ ...e, time: "", place: "" }]).trim() }),
      h("div", { class: "actions" },
        e.lat && e.lon
          ? h("button", { type: "button", text: "Copy coordinates", onclick: () => copyText(store.formatCoords(e.lat, e.lon), "Coordinates copied") })
          : null,
        h("button", { type: "button", class: "danger", text: "Delete", onclick: () => {
          if (!confirm("Delete this entry?")) return;
          entries = entries.filter((x) => x.id !== e.id);
          save();
          draw();
        } })));
  const draw = () => {
    if (!entries.length) return list.replaceChildren(h("p", { class: "hint", text: "No flights written down yet." }));
    list.replaceChildren(...[...entries].reverse().map(entryNode));
  };
  const add = h("button", { type: "button", class: "primary", text: "Save this flight", onclick: () => {
    const values = Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value]));
    const lat = values.lat.trim() && calc.parseNumber(values.lat);
    const lon = values.lon.trim() && calc.parseNumber(values.lon);
    if ((values.lat.trim() && lat === null) || (values.lon.trim() && lon === null) || (lat !== "" && lat !== null && Math.abs(lat) > 90) || (lon !== "" && lon !== null && Math.abs(lon) > 180)) {
      return toast("Check the coordinates: latitude first, then longitude.");
    }
    const now = new Date();
    entries.push(store.newEntry({ ...values, lat: lat === "" ? "" : String(lat), lon: lon === "" ? "" : String(lon) }, now, `${now.getTime()}-${entries.length}`));
    save();
    draw();
    for (const el of Object.values(f)) el.value = ""; // ready for the next flight, no accidental duplicates
    status.textContent = "";
    toast("Saved on this phone");
  } });
  const exportRow = h("div", { class: "actions" },
    h("button", { type: "button", text: "Copy all as text", onclick: () => entries.length ? copyText(store.entriesToText(entries), "Log copied") : toast("The log is empty.") }),
    h("button", { type: "button", text: "Download CSV", onclick: () => {
      if (!entries.length) return toast("The log is empty.");
      const blob = new Blob(["\ufeff" + store.entriesToCsv(entries)], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = h("a", { href: url, download: "avispria-flight-log.csv" });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } }),
    navigator.share ? h("button", { type: "button", text: "Share", onclick: () => entries.length && navigator.share({ title: "Avispria flight log", text: store.entriesToText(entries) }).catch(() => {}) }) : null,
    h("button", { type: "button", class: "danger", text: "Delete all", onclick: () => {
      if (entries.length && confirm("Delete the whole log from this phone?")) {
        entries = [];
        save();
        draw();
      }
    } }));
  section.append(h("h2", { text: "Flight log" }),
    h("p", { class: "hint", text: storage.persistent ? "Kept on this phone only. Nothing is sent anywhere." : "This browser would not store data: the log lasts only until you close the page." }),
    h("section", { class: "card" }, h("h3", { text: "Takeoff point" }), locate, status,
      h("div", { class: "grid" }, input("lat", "Latitude", { mode: "decimal" }), input("lon", "Longitude", { mode: "decimal" }), input("accuracy", "Accuracy (m)", { mode: "decimal" })),
      h("p", { class: "hint", text: "Avispria wants these as: latitude, longitude (for example 23.8103, 90.4125)." })),
    h("section", { class: "card" }, h("h3", { text: "This flight" }),
      h("div", { class: "grid" }, input("place", "Place"), input("mission", "Mission name"), input("wind", "Wind (m/s)", { mode: "decimal" }),
        input("batteryStart", "Battery at start (%)", { mode: "numeric" }), input("batteryEnd", "Battery at end (%)", { mode: "numeric" })),
      input("notes", "Notes", { area: true }), h("div", { class: "actions" }, add)),
    h("section", { class: "card" }, h("h3", { text: "Your flights" }), list, exportRow));
  draw();
  return section;
}

// ------------------------------------------------------------------------ about
function buildAbout() {
  const offline = h("p", { text: "Setting up offline use..." });
  const install = h("button", { type: "button", class: "primary", hidden: true, text: "Install on this phone" });
  let deferred = null;
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferred = event;
    install.hidden = false;
  });
  install.addEventListener("click", async () => {
    if (!deferred) return;
    deferred.prompt();
    await deferred.userChoice.catch(() => {});
    deferred = null;
    install.hidden = true;
  });
  const setOffline = (ready) => {
    offline.textContent = ready ? "Ready: this page works without a signal." : "Offline use is not available in this browser, so this page needs a signal.";
  };
  if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.ready.then(() => setOffline(true), () => setOffline(false));
  else setOffline(false);
  return h("section", { class: "view", id: "view-about", hidden: true },
    h("h2", { text: "About" }),
    h("div", { class: "card" }, h("h3", { text: "What this is" }),
      h("p", { text: "A small companion to Avispria, the open-source toolkit for planning drone surveys, checking photos and making maps with consumer RGB drones. Use it in the field, with or without a signal." })),
    h("div", { class: "card" }, h("h3", { text: "Your data" }),
      h("p", { text: "Everything you tick or write stays on this phone. There are no accounts, no tracking and no outside services. Your location is used only when you tap Use my location, and is never sent anywhere." })),
    h("div", { class: "card" }, h("h3", { text: "Offline and home screen" }), offline, install,
      h("p", { class: "hint", text: "Android (Chrome): menu, then Install app or Add to Home screen. iPhone (Safari): Share, then Add to Home Screen." })),
    h("div", { class: "card" }, h("h3", { text: "Please note" }),
      h("p", { text: "These are aids, not guarantees. The calculators follow the Avispria planner but are simplified. Check the rules where you fly and fly safely." }),
      h("p", { class: "hint", text: `Version ${AVISPRIA_VERSION} · early version, not yet flight-tested.` }),
      h("p", {}, h("a", { href: REPO, text: "Avispria on GitHub", rel: "noopener" }))));
}

// ---------------------------------------------------------------------- routing
const sections = { checklist: buildChecklist(), calc: buildCalc(), log: buildLog(), about: buildAbout() };
const main = document.getElementById("view");
main.append(...Object.values(sections));
const TITLES = { checklist: "Checklists", calc: "Calculators", log: "Flight log", about: "About" };

function route() {
  const wanted = location.hash.replace(/^#\/?/, "");
  const name = sections[wanted] ? wanted : "checklist";
  for (const [key, el] of Object.entries(sections)) el.hidden = key !== name;
  document.querySelectorAll(".tabs a").forEach((a) => {
    if (a.dataset.tab === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  document.title = `${TITLES[name]} - Avispria Field`;
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
route();

// ------------------------------------------------------------------ offline cache
if ("serviceWorker" in navigator && location.protocol !== "file:") {
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.register("sw.js").catch(() => {});
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController) toast("A new version is ready.", { label: "Reload", run: () => location.reload() });
  });
}
