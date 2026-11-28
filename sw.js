// Offline support. Network first, so new config/data show up as soon as
// there's signal; falls back to the last cached copy when there isn't
// (much of the Kepler track has no coverage).
const CACHE = "kc26-v4";
const ASSETS = [
  "./", "index.html", "grunt.html", "style.css", "app.js", "model.js",
  "config.js", "grunt-config.js", "data/results-2025.json", "data/grunt-2025.json",
  "app.webmanifest",
  "icons/kepler-180.png", "icons/kepler-192.png", "icons/kepler-512.png",
  "icons/grunt-180.png", "icons/grunt-192.png", "icons/grunt-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true }))
  );
});
