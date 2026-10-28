// Offline shell: the app and its data are static files, so cache them and refresh in the background.
const NAME = "finn-v4";
const SHELL = ["./", "index.html", "app.css", "app.js", "logic.js", "icon.svg", "manifest.webmanifest", "data/snapshot.json", "data/enrich.json", "data/ledger.json", "data/research/index.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(NAME).then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== NAME).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  e.respondWith((async () => {
    const cache = await caches.open(NAME);
    const hit = await cache.match(req);
    const refresh = fetch(req).then(async (r) => {
      if (r.ok) await cache.put(req, r.clone());
      return r;
    });
    e.waitUntil(refresh.then(() => undefined).catch(() => undefined));
    return hit || refresh.catch(() => new Response("Offline and this page is not cached.", { status: 503 }));
  })());
});
