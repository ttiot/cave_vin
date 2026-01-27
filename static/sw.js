/**
 * Service Worker pour Cave à Vin PWA
 * Gère le cache, le mode hors-ligne et les notifications push
 * Version: 2.0
 */

const CACHE_VERSION = "v2";
const STATIC_CACHE = `cave-vin-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `cave-vin-dynamic-${CACHE_VERSION}`;
const IMAGES_CACHE = `cave-vin-images-${CACHE_VERSION}`;
const OFFLINE_QUEUE_KEY = "cave-vin-offline-queue";
const DEBUG =
    new URL(self.location.href).searchParams.get("debug") === "1";

function logDebug(...args) {
    if (DEBUG) {
        console.log(...args);
    }
}

function warnDebug(...args) {
    if (DEBUG) {
        console.warn(...args);
    }
}

// Ressources statiques à mettre en cache immédiatement
const STATIC_ASSETS = [
    "/",
    "/static/css/styles.css",
    "/static/js/main.js",
    "/static/favico.png",
    "/static/manifest.json",
    "/static/icons/icon-72x72.png",
    "/static/icons/icon-96x96.png",
    "/static/icons/icon-128x128.png",
    "/static/icons/icon-144x144.png",
    "/static/icons/icon-152x152.png",
    "/static/icons/icon-192x192.png",
    "/static/icons/icon-384x384.png",
    "/static/icons/icon-512x512.png",
];

// Pages à pré-cacher pour le mode hors-ligne
const OFFLINE_PAGES = ["/wines/overview", "/cellars/", "/stats", "/search/"];

// Limites de cache
const CACHE_LIMITS = {
    dynamic: 50,
    images: 100,
};

// Page hors-ligne de secours
const OFFLINE_PAGE = `<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Hors-ligne - Cave à Vin</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: system-ui, -apple-system, sans-serif; 
            text-align: center; 
            padding: 50px 20px; 
            background: linear-gradient(135deg, #1a1d21 0%, #2d1f24 100%);
            color: #e9ecef;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        .container { max-width: 400px; }
        .icon { font-size: 5rem; margin-bottom: 1.5rem; animation: pulse 2s infinite; }
        @keyframes pulse {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.1); opacity: 0.8; }
        }
        h1 { font-size: 1.75rem; margin-bottom: 1rem; color: #fff; }
        p { color: #adb5bd; margin-bottom: 0.5rem; line-height: 1.6; }
        .status { 
            margin-top: 2rem; 
            padding: 1rem; 
            background: rgba(255,255,255,0.05); 
            border-radius: 10px;
            font-size: 0.9rem;
        }
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #dc3545;
            margin-right: 8px;
            animation: blink 1.5s infinite;
        }
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .retry { 
            margin-top: 2rem; 
            padding: 12px 30px; 
            background: linear-gradient(135deg, #722f37 0%, #8b3a44 100%);
            color: white; 
            border: none; 
            border-radius: 25px; 
            cursor: pointer;
            font-size: 1rem;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(114, 47, 55, 0.3);
        }
        .retry:hover { 
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(114, 47, 55, 0.4);
        }
        .retry:active { transform: translateY(0); }
        .cached-pages {
            margin-top: 2rem;
            text-align: left;
        }
        .cached-pages h3 {
            font-size: 1rem;
            margin-bottom: 0.75rem;
            color: #adb5bd;
        }
        .cached-pages a {
            display: block;
            padding: 0.5rem 1rem;
            margin: 0.25rem 0;
            background: rgba(255,255,255,0.05);
            border-radius: 5px;
            color: #e9ecef;
            text-decoration: none;
            transition: background 0.2s;
        }
        .cached-pages a:hover {
            background: rgba(255,255,255,0.1);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🍷</div>
        <h1>Vous êtes hors-ligne</h1>
        <p>Impossible de charger cette page pour le moment.</p>
        <p>Vérifiez votre connexion internet et réessayez.</p>
        
        <div class="status">
            <span class="status-indicator"></span>
            Connexion indisponible
        </div>
        
        <button class="retry" onclick="location.reload()">
            🔄 Réessayer
        </button>
        
        <div class="cached-pages">
            <h3>📱 Pages disponibles hors-ligne :</h3>
            <a href="/">🏠 Accueil</a>
            <a href="/wines/overview">🍾 Ma collection</a>
            <a href="/cellars">📦 Mes caves</a>
            <a href="/statistics">📊 Statistiques</a>
        </div>
    </div>
    
    <script>
        // Vérifier la connexion périodiquement
        setInterval(() => {
            fetch('/').then(() => location.reload()).catch(() => {});
        }, 5000);
    </script>
</body>
</html>`;

// ============================================
// INSTALLATION
// ============================================
self.addEventListener("install", (event) => {
    event.waitUntil(
        Promise.all([
            // Cache des ressources statiques
            caches.open(STATIC_CACHE).then((cache) => {
                return Promise.allSettled(
                    STATIC_ASSETS.map((asset) => cache.add(asset)),
                ).then((results) => {
                    results.forEach((result, index) => {
                        if (result.status === "rejected") {
                            warnDebug(
                                "[SW] Ressource statique ignorée:",
                                STATIC_ASSETS[index],
                            );
                        }
                    });
                });
            }),
            // Pré-cache des pages importantes
            caches.open(DYNAMIC_CACHE).then(async (cache) => {
                for (const page of OFFLINE_PAGES) {
                    try {
                        const response = await fetch(page, {
                            credentials: "same-origin",
                        });
                        if (response.ok) {
                            await cache.put(page, response);
                        }
                    } catch (e) {
                        console.error(
                            "[SW] Impossible de pré-cacher une page hors-ligne",
                            e,
                        );
                    }
                }
            }),
        ])
            .then(() => self.skipWaiting())
            .catch((err) => console.error("[SW] Erreur installation:", err)),
    );
});

// ============================================
// ACTIVATION
// ============================================
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => {
                            // Supprimer les anciens caches
                            return (
                                name.startsWith("cave-vin-") &&
                                name !== STATIC_CACHE &&
                                name !== DYNAMIC_CACHE &&
                                name !== IMAGES_CACHE
                            );
                        })
                        .map((name) => caches.delete(name)),
                );
            })
            .then(() => self.clients.claim()),
    );
});

// ============================================
// INTERCEPTION DES REQUÊTES
// ============================================
self.addEventListener("fetch", (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Ignorer les requêtes non-GET
    if (request.method !== "GET") {
        // Mettre en file d'attente les requêtes POST/PUT/DELETE pour sync
        if (["POST", "PUT", "DELETE"].includes(request.method)) {
            handleOfflineRequest(request);
        }
        return;
    }

    // Laisser les requêtes cross-origin au navigateur (ne pas intercepter)
    if (url.origin !== self.location.origin) {
        return;
    }

    // Ignorer les requêtes API (toujours réseau avec fallback)
    if (url.pathname.startsWith("/api/")) {
        event.respondWith(networkOnly(request));
        return;
    }

    // Ignorer les requêtes d'authentification
    if (
        url.pathname.startsWith("/login") ||
        url.pathname.startsWith("/logout")
    ) {
        event.respondWith(networkOnly(request));
        return;
    }

    // Éviter le cache SW pour les vendors locaux (facilite le debugging)
    if (url.pathname.startsWith("/static/vendor/")) {
        event.respondWith(networkOnly(request));
        return;
    }

    // Stratégie pour les images
    if (isImageRequest(url)) {
        event.respondWith(cacheFirstWithExpiry(request, IMAGES_CACHE));
        return;
    }

    // Stratégie: Cache First pour les ressources statiques
    if (isStaticAsset(url)) {
        event.respondWith(cacheFirst(request, STATIC_CACHE));
        return;
    }

    // Stratégie: Network First pour les pages HTML
    if (request.headers.get("accept")?.includes("text/html")) {
        event.respondWith(networkFirstWithOffline(request));
        return;
    }

    // Stratégie: Stale While Revalidate pour le reste
    event.respondWith(staleWhileRevalidate(request));
});

// ============================================
// STRATÉGIES DE CACHE
// ============================================

// Vérifier si c'est une ressource statique
function isStaticAsset(url) {
    const staticExtensions = [".css", ".js", ".woff", ".woff2", ".ttf", ".eot"];
    return staticExtensions.some((ext) => url.pathname.endsWith(ext));
}

// Vérifier si c'est une image
function isImageRequest(url) {
    const imageExtensions = [
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
    ];
    return imageExtensions.some((ext) => url.pathname.endsWith(ext));
}

// Cache First - pour les ressources statiques
async function cacheFirst(request, cacheName) {
    try {
        const cached = await caches.match(request);
        if (cached) {
            return cached;
        }

        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
        }
        return response;
    } catch (error) {
        console.error("[SW] Erreur Cache First:", error);
        try {
            return await fetch(request);
        } catch (fallbackError) {
            return new Response("Ressource non disponible", { status: 503 });
        }
    }
}

// Cache First avec expiration - pour les images
async function cacheFirstWithExpiry(request, cacheName) {
    try {
        const cached = await caches.match(request);
        if (cached) {
            return cached;
        }

        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
            // Nettoyer le cache si trop grand
            limitCacheSize(cacheName, CACHE_LIMITS.images);
        }
        return response;
    } catch (error) {
        // Retourner une image placeholder si hors-ligne
        return new Response(
            `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
                <rect fill="#2d1f24" width="200" height="200"/>
                <text fill="#722f37" font-family="sans-serif" font-size="60" x="50%" y="50%" text-anchor="middle" dy=".3em">🍷</text>
            </svg>`,
            { headers: { "Content-Type": "image/svg+xml" } },
        );
    }
}

// Network First avec page hors-ligne - pour les pages HTML
async function networkFirstWithOffline(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(DYNAMIC_CACHE);
            cache.put(request, response.clone());
            // Nettoyer le cache dynamique
            limitCacheSize(DYNAMIC_CACHE, CACHE_LIMITS.dynamic);
        }
        return response;
    } catch (error) {
        // Chercher dans le cache
        const cached = await caches.match(request);
        if (cached) {
            return cached;
        }

        // Chercher la page d'accueil en cache
        const homeCached = await caches.match("/");
        if (homeCached && request.url.endsWith("/")) {
            return homeCached;
        }

        // Retourner la page hors-ligne
        return new Response(OFFLINE_PAGE, {
            headers: { "Content-Type": "text/html; charset=utf-8" },
        });
    }
}

// Network Only - pour les API et auth
async function networkOnly(request) {
    try {
        return await fetch(request);
    } catch (error) {
        return new Response(
            JSON.stringify({
                error: "Hors-ligne",
                message: "Cette action nécessite une connexion internet",
            }),
            { status: 503, headers: { "Content-Type": "application/json" } },
        );
    }
}

// Stale While Revalidate
async function staleWhileRevalidate(request) {
    const cached = await caches.match(request);

    const fetchPromise = fetch(request)
        .then(async (response) => {
            if (response.ok) {
                const cache = await caches.open(DYNAMIC_CACHE);
                cache.put(request, response.clone());
            }
            return response;
        })
        .catch(() => cached);

    return cached || fetchPromise;
}

// Limiter la taille du cache
async function limitCacheSize(cacheName, maxItems) {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    if (keys.length > maxItems) {
        // Supprimer les plus anciens
        const toDelete = keys.slice(0, keys.length - maxItems);
        await Promise.all(toDelete.map((key) => cache.delete(key)));
    }
}

// ============================================
// GESTION DES REQUÊTES HORS-LIGNE
// ============================================

async function handleOfflineRequest(request) {
    // Stocker les requêtes pour synchronisation ultérieure
    try {
        const queue = JSON.parse(
            localStorage.getItem(OFFLINE_QUEUE_KEY) || "[]",
        );
        queue.push({
            url: request.url,
            method: request.method,
            timestamp: Date.now(),
        });
        localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
    } catch (e) {
        console.error("[SW] Impossible de mettre en file d'attente:", e);
    }
}

// ============================================
// NOTIFICATIONS PUSH
// ============================================

self.addEventListener("push", (event) => {
    let data = {
        title: "Cave à Vin",
        body: "Nouvelle notification",
        icon: "/static/icons/icon-192x192.png",
        badge: "/static/icons/icon-72x72.png",
        tag: "cave-vin-notification",
        url: "/",
    };

    if (event.data) {
        try {
            const payload = event.data.json();
            data = { ...data, ...payload };
        } catch (e) {
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: data.icon,
        badge: data.badge,
        tag: data.tag,
        vibrate: [100, 50, 100, 50, 100],
        renotify: true,
        requireInteraction: data.requireInteraction || false,
        data: {
            url: data.url,
            dateOfArrival: Date.now(),
            primaryKey: data.primaryKey || Date.now(),
        },
        actions: data.actions || [
            {
                action: "open",
                title: "Ouvrir",
                icon: "/static/icons/icon-72x72.png",
            },
            { action: "close", title: "Fermer" },
        ],
    };

    // Ajouter une image si fournie
    if (data.image) {
        options.image = data.image;
    }

    event.waitUntil(self.registration.showNotification(data.title, options));
});

// Clic sur une notification
self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    if (event.action === "close") {
        return;
    }

    const url = event.notification.data?.url || "/";

    event.waitUntil(
        clients
            .matchAll({ type: "window", includeUncontrolled: true })
            .then((clientList) => {
                // Chercher une fenêtre existante avec la même URL
                for (const client of clientList) {
                    if (client.url.includes(url) && "focus" in client) {
                        return client.focus();
                    }
                }
                // Chercher n'importe quelle fenêtre de l'app
                for (const client of clientList) {
                    if ("focus" in client && "navigate" in client) {
                        return client.focus().then(() => client.navigate(url));
                    }
                }
                // Ouvrir une nouvelle fenêtre
                if (clients.openWindow) {
                    return clients.openWindow(url);
                }
            }),
    );
});

// Fermeture d'une notification
self.addEventListener("notificationclose", (event) => {
    // Possibilité de tracker les notifications fermées
});

// ============================================
// SYNCHRONISATION EN ARRIÈRE-PLAN
// ============================================

self.addEventListener("sync", (event) => {
    switch (event.tag) {
        case "sync-consumptions":
            event.waitUntil(syncConsumptions());
            break;
        case "sync-offline-queue":
            event.waitUntil(syncOfflineQueue());
            break;
        default:
            warnDebug("[SW] Tag de sync inconnu:", event.tag);
    }
});

// Synchroniser les consommations en attente
async function syncConsumptions() {
    // Implémentation de la synchronisation des consommations
    // Cette fonction serait appelée quand la connexion est rétablie
}

// Synchroniser la file d'attente hors-ligne
async function syncOfflineQueue() {
    try {
        const queue = JSON.parse(
            localStorage.getItem(OFFLINE_QUEUE_KEY) || "[]",
        );

        for (const item of queue) {
            try {
                await fetch(item.url, { method: item.method });
            } catch (e) {
                console.error("[SW] Échec sync:", item.url, e);
            }
        }

        // Vider la file d'attente
        localStorage.removeItem(OFFLINE_QUEUE_KEY);
    } catch (e) {
        console.error("[SW] Erreur sync queue:", e);
    }
}

// ============================================
// PERIODIC BACKGROUND SYNC (si supporté)
// ============================================

self.addEventListener("periodicsync", (event) => {
    if (event.tag === "update-cache") {
        event.waitUntil(updateCache());
    }
});

// Mettre à jour le cache périodiquement
async function updateCache() {
    const cache = await caches.open(DYNAMIC_CACHE);

    for (const page of OFFLINE_PAGES) {
        try {
            const response = await fetch(page, { credentials: "same-origin" });
            if (response.ok) {
                await cache.put(page, response);
            }
        } catch (e) {
            console.error("[SW] Impossible de mettre à jour:", page, e);
        }
    }
}

// ============================================
// MESSAGES DEPUIS L'APPLICATION
// ============================================

self.addEventListener("message", (event) => {
    switch (event.data.type) {
        case "SKIP_WAITING":
            self.skipWaiting();
            break;
        case "CLEAR_CACHE":
            event.waitUntil(clearAllCaches());
            break;
        case "CACHE_PAGE":
            event.waitUntil(cachePage(event.data.url));
            break;
        case "GET_CACHE_STATUS":
            event.waitUntil(getCacheStatus(event));
            break;
        default:
            warnDebug("[SW] Type de message inconnu:", event.data.type);
    }
});

// Vider tous les caches
async function clearAllCaches() {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.map((name) => caches.delete(name)));
}

// Mettre une page en cache
async function cachePage(url) {
    try {
        const cache = await caches.open(DYNAMIC_CACHE);
        const response = await fetch(url, { credentials: "same-origin" });
        if (response.ok) {
            await cache.put(url, response);
        }
    } catch (e) {
        console.error("[SW] Erreur cache page:", e);
    }
}

// Obtenir le statut du cache
async function getCacheStatus(event) {
    const cacheNames = await caches.keys();
    const status = {};

    for (const name of cacheNames) {
        const cache = await caches.open(name);
        const keys = await cache.keys();
        status[name] = keys.length;
    }

    event.source.postMessage({
        type: "CACHE_STATUS",
        status: status,
    });
}
