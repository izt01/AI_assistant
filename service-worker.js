const CACHE_NAME = "lumina-pwa-v23";  // v20: JSON強制先頭注入・リトライJSON強制・fallbackログ
const OFFLINE_URL = "/offline.html";
// admin系ファイルはキャッシュしない（更新が頻繁なため常にネットワーク取得）
const NO_CACHE_PATTERNS = [/^\/admin/, /^\/api\//];
const PRECACHE_URLS = [
  "/",
  "/index.html",
  "/login.html",
  "/register.html",
  "/dashboard.html",
  "/chat.html",
  "/plan.html",
  "/profile.html",
  "/hotel.html",
  "/shopping-list.html",
  "/forgot-password.html",
  "/reset-password.html",
  "/shared.css",
  "/shared.js",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
  OFFLINE_URL
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  // admin系・API系は常にネットワークから取得（キャッシュしない）
  if (NO_CACHE_PATTERNS.some(p => p.test(url.pathname))) {
    event.respondWith(fetch(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => (await caches.match(request)) || caches.match(OFFLINE_URL))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (!response || response.status !== 200 || response.type === "opaque") return response;
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        return response;
      });
    }).catch(() => caches.match(OFFLINE_URL))
  );
});