// =============================================================================
// sw.js — Service Worker (PWA)
// =============================================================================
// Strategy:
//   • /api/*        → always network  (live booking data, never cached)
//   • CSS / JS      → network-first   (always try fresh; fallback to cache)
//   • images / icons → cache-first    (stable assets, rarely change)
//
// Bump CACHE_VERSION whenever you deploy changes so PWA users get the update.
// =============================================================================

const CACHE_VERSION = 'v12';
const CACHE_NAME = `room-booking-${CACHE_VERSION}`;

const SHELL_URLS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

// ── Install: pre-cache the shell ─────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return Promise.all(
        SHELL_URLS.map(url =>
          cache.add(url).catch(() => console.warn('[SW] Could not pre-cache:', url))
        )
      );
    })
  );
  // Activate immediately — don't wait for old tabs to close
  self.skipWaiting();
});

// ── Activate: clean up all old caches ────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => {
            console.log('[SW] Deleting old cache:', key);
            return caches.delete(key);
          })
      )
    )
  );
  // Take control of all open tabs immediately
  self.clients.claim();
});

// ── Fetch strategy ───────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // 1. Always hit the network for API calls and non-GET requests
  if (url.pathname.startsWith('/api/') || event.request.method !== 'GET') {
    event.respondWith(fetch(event.request));
    return;
  }

  // 2. CSS & JS → Network-first so the PWA always gets the latest code.
  //    Falls back to cache only when offline.
  if (url.pathname.startsWith('/static/css/') || url.pathname.startsWith('/static/js/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (response && response.status === 200 && response.type === 'basic') {
            const toCache = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, toCache));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // 3. Everything else (HTML, icons) → Cache-first, network fallback
  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) return cached;

      return fetch(event.request).then(response => {
        if (response && response.status === 200 && response.type === 'basic') {
          const toCache = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, toCache));
        }
        return response;
      });
    }).catch(() => {
      if (event.request.mode === 'navigate') {
        return caches.match('/');
      }
    })
  );
});

