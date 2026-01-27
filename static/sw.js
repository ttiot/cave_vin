/**
 * Service Worker pour Cave à Vin PWA
 * Gère le cache et le mode hors-ligne
 */

const CACHE_NAME = "cave-vin-v1";
const STATIC_CACHE = "cave-vin-static-v1";
const DYNAMIC_CACHE = "cave-vin-dynamic-v1";

// Ressources statiques à mettre en cache immédiatement
const STATIC_ASSETS = [
    "/",
    "/static/css/styles.css",
    "/static/js/main.js",
    "/static/favico.png",
    "/static/manifest.json",
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css",
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.1/font/bootstrap-icons.min.css",
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js",
];

// Pages à mettre en cache pour le mode hors-ligne
const OFFLINE_PAGES = ["/wines/overview", "/cellars", "/statistics"];

// Installation du service worker
self.addEventListener("install", (event) => {
    console.log("[SW] Installation...");

    event.waitUntil(
        caches
            .open(STATIC_CACHE)
            .then((cache) => {
                console.log("[SW] Mise en cache des ressources statiques");
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
            .catch((err) =>
                console.error("[SW] Erreur lors de l'installation:", err),
            ),
    );
});

// Activation du service worker
self.addEventListener("activate", (event) => {
    console.log("[SW] Activation...");

    event.waitUntil(
        caches
            .keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter(
                            (name) =>
                                name !== STATIC_CACHE && name !== DYNAMIC_CACHE,
                        )
                        .map((name) => {
                            console.log(
                                "[SW] Suppression du cache obsolète:",
                                name,
                            );
                            return caches.delete(name);
                        }),
                );
            })
            .then(() => self.clients.claim()),
    );
});

// Interception des requêtes
self.addEventListener("fetch", (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Ignorer les requêtes non-GET
    if (request.method !== "GET") {
        return;
    }

    // Ignorer les requêtes API (toujours réseau)
    if (url.pathname.startsWith("/api/")) {
        return;
    }

    // Stratégie: Cache First pour les ressources statiques
    if (isStaticAsset(url)) {
        event.respondWith(cacheFirst(request));
        return;
    }

    // Stratégie: Network First pour les pages HTML
    if (request.headers.get("accept")?.includes("text/html")) {
        event.respondWith(networkFirst(request));
        return;
    }

    // Stratégie: Stale While Revalidate pour le reste
    event.respondWith(staleWhileRevalidate(request));
});

// Vérifier si c'est une ressource statique
function isStaticAsset(url) {
    const staticExtensions = [
        ".css",
        ".js",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".woff",
        ".woff2",
    ];
    return staticExtensions.some((ext) => url.pathname.endsWith(ext));
}

// Stratégie Cache First
async function cacheFirst(request) {
    const cached = await caches.match(request);
    if (cached) {
        return cached;
    }

    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, response.clone());
        }
        return response;
    } catch (error) {
        console.error("[SW] Erreur Cache First:", error);
        return new Response("Ressource non disponible hors-ligne", {
            status: 503,
        });
    }
}

// Stratégie Network First
async function networkFirst(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(DYNAMIC_CACHE);
            cache.put(request, response.clone());
        }
        return response;
    } catch (error) {
        console.log("[SW] Réseau indisponible, utilisation du cache");
        const cached = await caches.match(request);
        if (cached) {
            return cached;
        }

        // Page hors-ligne de secours
        return (
            caches.match("/") ||
            new Response(
                `<!DOCTYPE html>
      <html lang="fr">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Hors-ligne - Cave à Vin</title>
        <style>
          body { font-family: system-ui, sans-serif; text-align: center; padding: 50px 20px; background: #1a1d21; color: #e9ecef; }
          h1 { font-size: 2rem; margin-bottom: 1rem; }
          p { color: #adb5bd; }
          .icon { font-size: 4rem; margin-bottom: 1rem; }
          .retry { margin-top: 2rem; padding: 10px 20px; background: #722f37; color: white; border: none; border-radius: 5px; cursor: pointer; }
        </style>
      </head>
      <body>
        <div class="icon">🍷</div>
        <h1>Vous êtes hors-ligne</h1>
        <p>Impossible de charger cette page. Vérifiez votre connexion internet.</p>
        <button class="retry" onclick="location.reload()">Réessayer</button>
      </body>
      </html>`,
                { headers: { "Content-Type": "text/html" } },
            )
        );
    }
}

// Stratégie Stale While Revalidate
async function staleWhileRevalidate(request) {
    const cached = await caches.match(request);

    const fetchPromise = fetch(request)
        .then((response) => {
            if (response.ok) {
                const cache = caches.open(DYNAMIC_CACHE);
                cache.then((c) => c.put(request, response.clone()));
            }
            return response;
        })
        .catch(() => cached);

    return cached || fetchPromise;
}

// Gestion des notifications push
self.addEventListener("push", (event) => {
    console.log("[SW] Notification push reçue");

    let data = { title: "Cave à Vin", body: "Nouvelle notification" };

    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: "/static/icons/icon-192x192.png",
        badge: "/static/icons/icon-72x72.png",
        vibrate: [100, 50, 100],
        data: {
            url: data.url || "/",
            dateOfArrival: Date.now(),
        },
        actions: data.actions || [
            { action: "open", title: "Ouvrir" },
            { action: "close", title: "Fermer" },
        ],
    };

    event.waitUntil(self.registration.showNotification(data.title, options));
});

// Clic sur une notification
self.addEventListener("notificationclick", (event) => {
    console.log("[SW] Clic sur notification");

    event.notification.close();

    if (event.action === "close") {
        return;
    }

    const url = event.notification.data?.url || "/";

    event.waitUntil(
        clients
            .matchAll({ type: "window", includeUncontrolled: true })
            .then((clientList) => {
                // Chercher une fenêtre existante
                for (const client of clientList) {
                    if (client.url === url && "focus" in client) {
                        return client.focus();
                    }
                }
                // Ouvrir une nouvelle fenêtre
                if (clients.openWindow) {
                    return clients.openWindow(url);
                }
            }),
    );
});

// Synchronisation en arrière-plan (pour les actions hors-ligne)
self.addEventListener("sync", (event) => {
    console.log("[SW] Synchronisation:", event.tag);

    if (event.tag === "sync-consumptions") {
        event.waitUntil(syncConsumptions());
    }
});

// Synchroniser les consommations en attente
async function syncConsumptions() {
    // Cette fonction serait utilisée pour synchroniser les actions
    // effectuées hors-ligne une fois la connexion rétablie
    console.log("[SW] Synchronisation des consommations...");
}
