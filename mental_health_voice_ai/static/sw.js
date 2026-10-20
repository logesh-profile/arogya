// Arogya Companion • High-Performance PWA Service Worker (v1)
const CACHE_NAME = 'arogya-pwa-v1';
const CORE_ASSETS = [
  '/',
  '/login',
  '/analytics',
  '/static/manifest.json',
  '/static/style.css',
  '/static/app.js',
  '/static/login.css',
  '/static/login.js',
  '/static/analytics.css',
  '/static/analytics.js',
  '/static/assets/icon-192.png',
  '/static/assets/icon-512.png',
  '/static/assets/companion_robot_chatting.jpg',
  '/static/assets/companion_robot_elderly.jpg'
];

// 1. Install Event: Cache Core UI Shell
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[*] Arogya PWA: Pre-caching core UI shell');
      return cache.addAll(CORE_ASSETS).catch((err) => {
        console.warn('[!] Core asset caching warning:', err);
      });
    })
  );
});

// 2. Activate Event: Clean Stale Caches & Claim Clients
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[*] Arogya PWA: Removing outdated cache:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch Event: Smart Routing
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Bypass non-GET requests and dynamic backend APIs (chat, voice, db, sensors, audio streaming)
  if (request.method !== 'GET' || url.pathname.startsWith('/api/') || url.pathname.startsWith('/audio/')) {
    return;
  }

  // HTML Page Navigations: Network-first with Cache Fallback
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          if (cached) return cached;
          return caches.match('/');
        })
    );
    return;
  }

  // Static Assets (CSS, JS, Images, Fonts): Cache-First with Background Refresh
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        // Fetch in background to revalidate cache
        fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(request, networkResponse));
          }
        }).catch(() => {});
        return cachedResponse;
      }

      return fetch(request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, responseToCache));
        }
        return networkResponse;
      });
    })
  );
});
