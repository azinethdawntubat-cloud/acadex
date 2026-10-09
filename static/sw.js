// Acadex service worker.
//
// This app shows private, logged-in data (grades, accounts), so page HTML is
// NEVER cached: every page always comes from the server. We only keep the
// static assets (CSS/JS/icons) and a small offline page so the installed app
// opens cleanly when there is no connection.

const VERSION = "acadex-v1";
const OFFLINE_URL = "/offline";
const PRECACHE = [
    OFFLINE_URL,
    "/static/style.css",
    "/static/script.js",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(VERSION)
            .then((cache) => cache.addAll(PRECACHE))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const req = event.request;
    if (req.method !== "GET") return;

    const url = new URL(req.url);
    if (url.origin !== self.location.origin) return;

    // Page navigations: network only; show the offline page if it fails.
    if (req.mode === "navigate") {
        event.respondWith(
            fetch(req).catch(() => caches.match(OFFLINE_URL))
        );
        return;
    }

    // Static files: network first (so updates show immediately),
    // falling back to the cached copy when offline.
    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            fetch(req)
                .then((res) => {
                    if (res.ok) {
                        const copy = res.clone();
                        caches.open(VERSION).then((cache) => cache.put(req, copy));
                    }
                    return res;
                })
                .catch(() => caches.match(req))
        );
    }
});
