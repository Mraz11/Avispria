// SPDX-FileCopyrightText: 2026 Avispria contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// The calculators of the field page. Pure functions (no page, no storage): they mirror the
// Python planner (camera.py, speed.py, sorties.py) and are tested against values the real
// planner produced (tests/field_page/golden.json).

export const MIN_SPEED = 1.0; // m/s: below this a plan is not flyable (same as the planner)

export function modeOf(cam, modeKey) {
  const m = cam.modes[modeKey];
  if (!m) throw new Error(`unknown photo size "${modeKey}"`);
  return m;
}

function positive(label, value) {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${label} must be more than zero`);
}

function overlapOk(label, value) {
  if (!Number.isFinite(value) || value < 0 || value >= 1) throw new Error(`${label} must be from 0 to under 100%`);
}

/** Size on the ground of one photo: across (image width) and along (image height), in metres. */
export function footprint(cam, modeKey, height) {
  const g = gsd(cam, modeKey, height);
  const m = modeOf(cam, modeKey);
  return { across: g * m.w, along: g * m.h }; // the photo's shape follows its pixel grid
}

/** Ground resolution in metres per pixel at ``height`` metres above the surface. */
export function gsd(cam, modeKey, height) {
  positive("height", height);
  const m = modeOf(cam, modeKey);
  return (height * m.sensorW) / (m.focal * m.w);
}

/** Height above the surface that gives ``gsdM`` metres per pixel. */
export function heightForGsd(cam, modeKey, gsdM) {
  positive("resolution", gsdM);
  const m = modeOf(cam, modeKey);
  return (gsdM * m.focal * m.w) / m.sensorW;
}

/** Distance between photos along a line, and between lines, for fractional overlaps. */
export function spacing(cam, modeKey, height, front, side) {
  overlapOk("front overlap", front);
  overlapOk("side overlap", side);
  const fp = footprint(cam, modeKey, height);
  return { photo: fp.along * (1 - front), line: fp.across * (1 - side) };
}

/** The fastest speed that keeps blur, rolling-shutter skew and photo rate in budget. */
export function solveSpeed(cam, modeKey, gsdM, shutterS, photoM, wind = 0) {
  positive("resolution", gsdM);
  positive("shutter time", shutterS);
  positive("photo spacing", photoM);
  if (!Number.isFinite(wind) || wind < 0) throw new Error("wind must be zero or more");
  const m = modeOf(cam, modeKey);
  const limits = {
    "motion blur": (0.5 * gsdM) / shutterS,
    "rolling-shutter skew": (15 * gsdM) / m.readout,
    "camera photo interval": photoM / m.minInterval,
    "wind headroom": 0.5 * cam.maxSpeed - wind,
    "drone maximum": cam.maxSpeed,
  };
  let binding = "motion blur";
  for (const key of Object.keys(limits)) if (limits[key] < limits[binding]) binding = key;
  const raw = limits[binding];
  const feasible = raw >= MIN_SPEED;
  return { speed: feasible ? raw : MIN_SPEED, binding, feasible, limits };
}

/**
 * Rough size of a survey of a rectangle, flown the way the planner flies it: lines along the
 * long side, each extended by one photo spacing, whole lines grouped into battery-sized missions.
 */
export function estimateSurvey(cam, modeKey, p) {
  const { width, length, height, front, side, shutter } = p;
  const wind = p.wind ?? 0;
  const batteryMin = p.batteryMin ?? 20;
  const climbRate = p.climbRate ?? 3;
  const maxWaypoints = p.maxWaypoints ?? 99;
  positive("area width", width);
  positive("area length", length);
  positive("battery time", batteryMin);
  const sp = spacing(cam, modeKey, height, front, side);
  const sol = solveSpeed(cam, modeKey, gsd(cam, modeKey, height), shutter, sp.photo, wind);
  const speed = Math.floor(sol.speed * 10 + 1e-9) / 10; // DJI Fly works in 0.1 m/s steps
  const base = { photoM: sp.photo, lineM: sp.line, speed, binding: sol.binding };
  if (!sol.feasible || speed < MIN_SPEED) return { ...base, feasible: false, missions: [], strips: 0 };

  const long = Math.max(width, length);
  const short = Math.min(width, length);
  const n = Math.max(1, Math.ceil(short / sp.line));
  const half = long / 2 + sp.photo; // lines run one photo spacing past the area at each end
  const strips = [];
  for (let k = 0; k < n; k++) {
    const y = (-(n - 1) * sp.line) / 2 + k * sp.line;
    strips.push(k % 2 === 0 ? [[-half, y], [half, y]] : [[half, y], [-half, y]]);
  }
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const route = (wps) => wps.slice(1).reduce((sum, w, i) => sum + dist(wps[i], w), 0);
  // takeoff at the middle of the area: out to the first waypoint, along the route, and back
  const duration = (wps) =>
    (Math.hypot(...wps[0]) + route(wps) + Math.hypot(...wps[wps.length - 1])) / speed + (2 * height) / climbRate;

  const groups = [];
  let current = [];
  for (const strip of strips) {
    const candidate = current.concat(strip);
    const tooBig = candidate.length > maxWaypoints || duration(candidate) > batteryMin * 60;
    if (current.length && tooBig) {
      groups.push(current);
      current = strip.slice();
    } else {
      current = candidate;
    }
  }
  if (current.length) groups.push(current);

  const step = speed * (sp.photo / speed); // distance between timed-shot photos
  const missions = groups.map((wps) => ({
    minutes: duration(wps) / 60,
    photos: Math.ceil((route(wps) + 1e-9) / step),
    distance: route(wps),
  }));
  return {
    ...base,
    feasible: true,
    strips: n,
    intervalS: sp.photo / speed,
    missions,
    totalMinutes: missions.reduce((s, m) => s + m.minutes, 0),
    totalPhotos: missions.reduce((s, m) => s + m.photos, 0),
  };
}

/** What trees or buildings do to a plan made for flat ground: the surface is closer than assumed. */
export function canopyEffect(cam, modeKey, p) {
  const { flight, canopy, front, side } = p;
  positive("flight height", flight);
  if (!Number.isFinite(canopy) || canopy < 0) throw new Error("canopy height must be zero or more");
  const above = flight - canopy;
  if (above <= 0) throw new Error("the canopy is as high as the drone: fly higher");
  const planned = spacing(cam, modeKey, flight, front, side);
  const fp = footprint(cam, modeKey, above);
  return {
    above,
    gsdGround: gsd(cam, modeKey, flight),
    gsdCanopy: gsd(cam, modeKey, above),
    frontActual: 1 - planned.photo / fp.along,
    sideActual: 1 - planned.line / fp.across,
  };
}

/** Flight height above the takeoff point so the canopy gets ``aboveCanopy`` metres. */
export function heightOverCanopy(aboveCanopy, canopy) {
  positive("height above the canopy", aboveCanopy);
  if (!Number.isFinite(canopy) || canopy < 0) throw new Error("canopy height must be zero or more");
  return aboveCanopy + canopy;
}

/** A number typed on a phone: accepts a comma as decimal mark; null if it is not a number. */
export function parseNumber(text) {
  if (typeof text === "number") return Number.isFinite(text) ? text : null;
  const cleaned = String(text ?? "").trim().replace(",", ".");
  if (cleaned === "" || !/^[-+]?(\d+\.?\d*|\.\d+)$/.test(cleaned)) return null;
  return Number(cleaned);
}

/** "1/1000" or "0.001" to seconds; null if it makes no sense. */
export function parseShutter(text) {
  const cleaned = String(text ?? "").trim();
  if (cleaned.includes("/")) {
    const [top, bottom] = cleaned.split("/").map(parseNumber);
    return top && bottom && top > 0 && bottom > 0 && top / bottom <= 1 ? top / bottom : null;
  }
  const value = parseNumber(cleaned);
  return value !== null && value > 0 && value <= 1 ? value : null;
}
