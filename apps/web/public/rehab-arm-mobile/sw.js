const CACHE_NAME = "rehab-arm-mobile-v2";
const ASSETS = [
  "./index.html",
  "./mobile-bridge.js",
  "./home.html",
  "./device.html",
  "./training-library.html",
  "./ai-plan.html",
  "./training-session.html",
  "./emg.html",
  "./report.html",
  "./profile.html",
  "./manifest.json",
  "./icon.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
});

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  if (requestUrl.origin !== self.location.origin) {
    return;
  }
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
