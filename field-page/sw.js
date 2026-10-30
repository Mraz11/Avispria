// SPDX-FileCopyrightText: 2026 Avispria contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// Keeps the field page working offline. The asset list and BUILD are written by
// scripts/field_page.py: run it after changing any file of the page.
const BUILD = "a3e5c32ae2a2";
const CACHE = `avispria-field-${BUILD}`;
// BEGIN GENERATED ASSETS
const ASSETS = [
  "./",
  "css/app.css",
  "css/theme.css",
  "icons/apple-touch-icon.png",
  "icons/favicon.png",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/icon-maskable-512.png",
  "img/logo-dark.png",
  "img/logo.png",
  "index.html",
  "js/app.js",
  "js/calc.js",
  "js/checklist.js",
  "js/generated.js",
  "js/store.js",
  "js/theme.js",
  "manifest.webmanifest"
];
// END GENERATED ASSETS

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k.startsWith("avispria-field-") && k !== CACHE).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  if (new URL(request.url).origin !== self.location.origin) return;
  event.respondWith(
    caches.match(request, { ignoreSearch: true }).then((hit) => {
      if (hit) return hit;
      // a page that was never cached (e.g. the site opened at an odd address): fall back to the app
      return fetch(request).catch(() => caches.match("./"));
    }),
  );
});
