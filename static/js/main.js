document.addEventListener("DOMContentLoaded", () => {
    initServiceWorker();
    initThemeToggle();
    initBarcodeScanner();
    initWineCards();
    initWineActions();
    initMobileSearch();
    initPushNotifications();
    initTutorial();
    initOfflineIndicator();
    initCacheManagement();
});

/**
 * Enregistrement du Service Worker pour la PWA
 */
function initServiceWorker() {
    if ("serviceWorker" in navigator) {
        // Enregistrer immédiatement avec scope racine
        // Note: Le serveur doit envoyer le header Service-Worker-Allowed: /
        navigator.serviceWorker
            .register("/sw.js", { scope: "/" })
            .then((registration) => {
                console.log(
                    "[PWA] Service Worker enregistré:",
                    registration.scope,
                );

                // Vérifier les mises à jour
                registration.addEventListener("updatefound", () => {
                    const newWorker = registration.installing;
                    newWorker.addEventListener("statechange", () => {
                        if (
                            newWorker.state === "installed" &&
                            navigator.serviceWorker.controller
                        ) {
                            // Nouvelle version disponible
                            showUpdateNotification();
                        }
                    });
                });
            })
            .catch((error) => {
                console.error(
                    "[PWA] Erreur d'enregistrement du Service Worker:",
                    error,
                );
            });
    }
}

/**
 * Afficher une notification de mise à jour disponible
 */
function showUpdateNotification() {
    const toast = document.createElement("div");
    toast.className = "position-fixed bottom-0 end-0 p-3";
    toast.style.zIndex = "1100";
    toast.innerHTML = `
        <div class="toast show" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header">
                <strong class="me-auto">🍷 Mise à jour disponible</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Fermer"></button>
            </div>
            <div class="toast-body">
                Une nouvelle version est disponible.
                <div class="mt-2 pt-2 border-top">
                    <button type="button" class="btn btn-primary btn-sm" onclick="location.reload()">
                        Actualiser
                    </button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(toast);
}

/**
 * Gestion des notifications push
 */
function initPushNotifications() {
    const enableBtn = document.getElementById("enableNotifications");
    console.log("[Push] Initialisation, bouton trouvé:", !!enableBtn);

    // Vérifier si les notifications sont supportées
    if (
        !("Notification" in window) ||
        !("serviceWorker" in navigator) ||
        !("PushManager" in window)
    ) {
        console.log("[Push] Notifications non supportées:", {
            Notification: "Notification" in window,
            serviceWorker: "serviceWorker" in navigator,
            PushManager: "PushManager" in window,
        });
        if (enableBtn) {
            enableBtn.disabled = true;
            enableBtn.textContent = "Notifications non supportées";
        }
        return;
    }

    console.log(
        "[Push] Notifications supportées, permission actuelle:",
        Notification.permission,
    );

    // Mettre à jour l'état du bouton si présent
    if (enableBtn) {
        updateNotificationButton(enableBtn);

        enableBtn.addEventListener("click", async () => {
            console.log(
                "[Push] Clic sur le bouton, permission:",
                Notification.permission,
            );
            const isCompact = enableBtn.classList.contains("theme-toggle");
            const originalContent = enableBtn.innerHTML;

            enableBtn.disabled = true;

            if (isCompact) {
                // Mode compact : afficher un spinner à la place de l'icône
                enableBtn.innerHTML =
                    '<span class="spinner-border spinner-border-sm"></span>';
            } else {
                enableBtn.innerHTML =
                    '<span class="spinner-border spinner-border-sm me-1"></span>Chargement...';
            }

            try {
                if (Notification.permission === "granted") {
                    console.log(
                        "[Push] Permission déjà accordée, vérification abonnement...",
                    );
                    // Vérifier si déjà abonné
                    const registration = await navigator.serviceWorker.ready;
                    console.log(
                        "[Push] Service Worker prêt:",
                        registration.scope,
                    );
                    const subscription =
                        await registration.pushManager.getSubscription();
                    console.log("[Push] Abonnement existant:", !!subscription);

                    if (subscription) {
                        await unsubscribeFromPush();
                    } else {
                        await subscribeToPush();
                    }
                } else if (Notification.permission === "default") {
                    console.log("[Push] Demande de permission...");
                    // Demander la permission
                    const permission = await Notification.requestPermission();
                    console.log("[Push] Permission obtenue:", permission);
                    if (permission === "granted") {
                        await subscribeToPush();
                        showNotificationSuccess();
                    }
                } else {
                    console.log(
                        "[Push] Permission refusée:",
                        Notification.permission,
                    );
                }
            } catch (error) {
                console.error("[Push] Erreur:", error);
                showNotificationError(error.message);
            }

            enableBtn.disabled = false;
            updateNotificationButton(enableBtn);
        });
    }

    // Vérifier l'état de l'abonnement au chargement
    checkPushSubscription();
}

async function checkPushSubscription() {
    try {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();

        if (subscription) {
            console.log("[Push] Abonnement actif:", subscription.endpoint);
            // Mettre à jour l'UI si nécessaire
            document.body.classList.add("push-subscribed");
        } else {
            document.body.classList.remove("push-subscribed");
        }
    } catch (error) {
        console.log("[Push] Erreur vérification abonnement:", error);
    }
}

function updateNotificationButton(btn) {
    navigator.serviceWorker.ready.then(async (registration) => {
        const subscription = await registration.pushManager.getSubscription();
        const icon = btn.querySelector("i") || btn;
        const isCompact = btn.classList.contains("theme-toggle");

        if (Notification.permission === "denied") {
            if (isCompact) {
                // Mode compact (navbar)
                icon.className = "bi bi-bell-slash";
                btn.title = "Notifications bloquées par le navigateur";
                btn.style.opacity = "0.5";
            } else {
                btn.innerHTML =
                    '<i class="bi bi-bell-slash me-1"></i>Notifications bloquées';
                btn.classList.remove("btn-primary", "btn-outline-secondary");
                btn.classList.add("btn-secondary");
            }
            btn.disabled = true;
        } else if (subscription) {
            if (isCompact) {
                // Mode compact (navbar) - abonné
                icon.className = "bi bi-bell-fill";
                btn.title = "Notifications activées (cliquer pour désactiver)";
                btn.style.opacity = "1";
                btn.style.color = "#28a745"; // Vert pour indiquer actif
            } else {
                btn.innerHTML =
                    '<i class="bi bi-bell-fill me-1"></i>Notifications activées';
                btn.classList.remove("btn-primary", "btn-secondary");
                btn.classList.add("btn-outline-success");
            }
            btn.disabled = false;
        } else {
            if (isCompact) {
                // Mode compact (navbar) - non abonné
                icon.className = "bi bi-bell";
                btn.title = "Activer les notifications";
                btn.style.opacity = "1";
                btn.style.color = ""; // Couleur par défaut
            } else {
                btn.innerHTML =
                    '<i class="bi bi-bell me-1"></i>Activer les notifications';
                btn.classList.remove(
                    "btn-outline-secondary",
                    "btn-outline-success",
                    "btn-secondary",
                );
                btn.classList.add("btn-primary");
            }
            btn.disabled = false;
        }
    });
}

async function subscribeToPush() {
    try {
        console.log("[Push] Début subscribeToPush...");

        // Attendre que le service worker soit prêt avec un timeout
        console.log("[Push] Attente du Service Worker...");
        const registration = await Promise.race([
            navigator.serviceWorker.ready,
            new Promise((_, reject) =>
                setTimeout(
                    () =>
                        reject(new Error("Service Worker non prêt (timeout)")),
                    10000,
                ),
            ),
        ]);
        console.log("[Push] Service Worker prêt:", registration.scope);

        // Récupérer la clé VAPID depuis le serveur si non définie
        let vapidKey = window.VAPID_PUBLIC_KEY;
        console.log("[Push] Clé VAPID en cache:", !!vapidKey);

        if (!vapidKey) {
            console.log("[Push] Récupération de la clé VAPID...");
            const response = await fetch("/api/push/vapid-key");
            console.log("[Push] Réponse VAPID:", response.status);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(
                    errorData.error || "Impossible de récupérer la clé VAPID",
                );
            }
            const data = await response.json();
            vapidKey = data.publicKey;
            console.log(
                "[Push] Clé VAPID reçue:",
                vapidKey ? vapidKey.substring(0, 20) + "..." : "null",
            );
        }

        if (!vapidKey) {
            throw new Error(
                "Clé VAPID non disponible - notifications push non configurées sur le serveur",
            );
        }

        // S'abonner aux notifications push
        console.log("[Push] Création de l'abonnement pushManager...");
        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidKey),
        });
        console.log(
            "[Push] Abonnement créé:",
            subscription.endpoint.substring(0, 50) + "...",
        );

        // Envoyer la subscription au serveur
        const subscriptionData = subscription.toJSON();
        console.log(
            "[Push] Données à envoyer:",
            JSON.stringify(subscriptionData).substring(0, 100) + "...",
        );

        const response = await fetch("/api/push/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(subscriptionData),
        });
        console.log("[Push] Réponse serveur:", response.status);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error("[Push] Erreur serveur:", errorData);
            // Si erreur serveur, désabonner localement pour éviter l'incohérence
            await subscription.unsubscribe().catch(() => {});
            throw new Error(
                errorData.error || "Erreur serveur lors de l'abonnement",
            );
        }

        const result = await response.json();
        console.log("[Push] Abonnement réussi, ID:", result.id);
        document.body.classList.add("push-subscribed");

        // Envoyer une notification de test
        sendTestNotification();

        return subscription;
    } catch (error) {
        console.error("[Push] Erreur d'abonnement:", error);
        throw error;
    }
}

async function unsubscribeFromPush() {
    try {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();

        if (subscription) {
            // Informer le serveur d'abord
            await fetch("/api/push/unsubscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ endpoint: subscription.endpoint }),
            });

            // Puis se désabonner localement
            await subscription.unsubscribe();
        }

        console.log("[Push] Désabonnement réussi");
        document.body.classList.remove("push-subscribed");
    } catch (error) {
        console.error("[Push] Erreur de désabonnement:", error);
        throw error;
    }
}

function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, "+")
        .replace(/_/g, "/");

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

function showNotificationSuccess() {
    const toast = document.createElement("div");
    toast.className = "position-fixed bottom-0 end-0 p-3";
    toast.style.zIndex = "1100";
    toast.innerHTML = `
        <div class="toast show bg-success text-white" role="alert">
            <div class="toast-header bg-success text-white">
                <i class="bi bi-bell-fill me-2"></i>
                <strong class="me-auto">Notifications activées</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                Vous recevrez des notifications pour les rappels de consommation et les mises à jour importantes.
            </div>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

function showNotificationError(message) {
    const toast = document.createElement("div");
    toast.className = "position-fixed bottom-0 end-0 p-3";
    toast.style.zIndex = "1100";
    toast.innerHTML = `
        <div class="toast show bg-danger text-white" role="alert">
            <div class="toast-header bg-danger text-white">
                <i class="bi bi-exclamation-triangle me-2"></i>
                <strong class="me-auto">Erreur</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message || "Impossible d'activer les notifications"}
            </div>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

async function sendTestNotification() {
    try {
        await fetch("/api/push/test", { method: "POST" });
    } catch (e) {
        console.log("[Push] Notification de test non envoyée");
    }
}

/**
 * Tutoriel interactif pour les nouveaux utilisateurs
 */
function initTutorial() {
    // Vérifier si c'est la première visite
    if (localStorage.getItem("tutorialCompleted")) {
        return;
    }

    // Vérifier si on est sur la page d'accueil et connecté
    const navbar = document.querySelector(".navbar");
    if (!navbar) return;

    // Afficher le tutoriel après un court délai
    setTimeout(() => {
        showTutorialStep(0);
    }, 1000);
}

const tutorialSteps = [
    {
        target: ".navbar-brand",
        title: "Bienvenue dans Ma Cave ! 🍷",
        content:
            "Ce tutoriel va vous guider à travers les principales fonctionnalités de l'application.",
        position: "bottom",
    },
    {
        target: 'a[href*="add"]',
        title: "Ajouter une bouteille",
        content:
            "Cliquez ici pour ajouter une nouvelle bouteille à votre cave. Vous pouvez scanner le code-barres ou saisir les informations manuellement.",
        position: "bottom",
    },
    {
        target: ".dropdown-toggle:has(.bi-archive)",
        title: "Votre cave",
        content:
            "Accédez à votre collection, vos caves, l'historique de consommation et les statistiques depuis ce menu.",
        position: "bottom",
    },
    {
        target: "#themeToggle",
        title: "Mode sombre",
        content:
            "Basculez entre le mode clair et sombre selon vos préférences.",
        position: "left",
    },
    {
        target: ".navbar-search-input, .navbar-search-toggle",
        title: "Recherche rapide",
        content:
            "Recherchez rapidement une bouteille par son nom ou utilisez la recherche avancée.",
        position: "bottom",
    },
];

function showTutorialStep(stepIndex) {
    // Supprimer l'étape précédente
    const existingOverlay = document.querySelector(".tutorial-overlay");
    if (existingOverlay) {
        existingOverlay.remove();
    }

    if (stepIndex >= tutorialSteps.length) {
        // Tutoriel terminé
        localStorage.setItem("tutorialCompleted", "true");
        return;
    }

    const step = tutorialSteps[stepIndex];
    const targetElement = document.querySelector(step.target);

    if (!targetElement) {
        // Passer à l'étape suivante si l'élément n'existe pas
        showTutorialStep(stepIndex + 1);
        return;
    }

    // Créer l'overlay
    const overlay = document.createElement("div");
    overlay.className = "tutorial-overlay";
    overlay.innerHTML = `
        <div class="tutorial-backdrop"></div>
        <div class="tutorial-spotlight"></div>
        <div class="tutorial-tooltip">
            <div class="tutorial-header">
                <span class="tutorial-step-indicator">${stepIndex + 1}/${tutorialSteps.length}</span>
                <button class="tutorial-close" aria-label="Fermer">&times;</button>
            </div>
            <h5 class="tutorial-title">${step.title}</h5>
            <p class="tutorial-content">${step.content}</p>
            <div class="tutorial-actions">
                ${stepIndex > 0 ? '<button class="btn btn-sm btn-outline-secondary tutorial-prev">Précédent</button>' : ""}
                <button class="btn btn-sm btn-primary tutorial-next">
                    ${stepIndex === tutorialSteps.length - 1 ? "Terminer" : "Suivant"}
                </button>
                <button class="btn btn-sm btn-link tutorial-skip">Passer le tutoriel</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    // Positionner le spotlight et le tooltip
    const rect = targetElement.getBoundingClientRect();
    const spotlight = overlay.querySelector(".tutorial-spotlight");
    const tooltip = overlay.querySelector(".tutorial-tooltip");

    spotlight.style.top = `${rect.top - 5}px`;
    spotlight.style.left = `${rect.left - 5}px`;
    spotlight.style.width = `${rect.width + 10}px`;
    spotlight.style.height = `${rect.height + 10}px`;

    // Positionner le tooltip
    positionTooltip(tooltip, rect, step.position);

    // Event listeners
    overlay.querySelector(".tutorial-close").addEventListener("click", () => {
        overlay.remove();
        localStorage.setItem("tutorialCompleted", "true");
    });

    overlay.querySelector(".tutorial-skip").addEventListener("click", () => {
        overlay.remove();
        localStorage.setItem("tutorialCompleted", "true");
    });

    overlay.querySelector(".tutorial-next").addEventListener("click", () => {
        showTutorialStep(stepIndex + 1);
    });

    const prevBtn = overlay.querySelector(".tutorial-prev");
    if (prevBtn) {
        prevBtn.addEventListener("click", () => {
            showTutorialStep(stepIndex - 1);
        });
    }

    // Fermer en cliquant sur le backdrop
    overlay
        .querySelector(".tutorial-backdrop")
        .addEventListener("click", () => {
            overlay.remove();
            localStorage.setItem("tutorialCompleted", "true");
        });
}

function positionTooltip(tooltip, targetRect, position) {
    const tooltipRect = tooltip.getBoundingClientRect();
    const margin = 15;

    switch (position) {
        case "bottom":
            tooltip.style.top = `${targetRect.bottom + margin}px`;
            tooltip.style.left = `${Math.max(10, targetRect.left + targetRect.width / 2 - tooltipRect.width / 2)}px`;
            break;
        case "top":
            tooltip.style.top = `${targetRect.top - tooltipRect.height - margin}px`;
            tooltip.style.left = `${Math.max(10, targetRect.left + targetRect.width / 2 - tooltipRect.width / 2)}px`;
            break;
        case "left":
            tooltip.style.top = `${targetRect.top + targetRect.height / 2 - tooltipRect.height / 2}px`;
            tooltip.style.left = `${targetRect.left - tooltipRect.width - margin}px`;
            break;
        case "right":
            tooltip.style.top = `${targetRect.top + targetRect.height / 2 - tooltipRect.height / 2}px`;
            tooltip.style.left = `${targetRect.right + margin}px`;
            break;
    }

    // S'assurer que le tooltip reste visible
    const finalRect = tooltip.getBoundingClientRect();
    if (finalRect.right > window.innerWidth - 10) {
        tooltip.style.left = `${window.innerWidth - finalRect.width - 10}px`;
    }
    if (finalRect.left < 10) {
        tooltip.style.left = "10px";
    }
}

/**
 * Gestion du thème sombre/clair
 */
function initThemeToggle() {
    const themeToggle = document.getElementById("themeToggle");
    const themeIcon = document.getElementById("themeIcon");

    if (!themeToggle || !themeIcon) {
        return;
    }

    // Mettre à jour l'icône selon le thème actuel
    function updateIcon() {
        const currentTheme =
            document.documentElement.getAttribute("data-theme");
        if (currentTheme === "dark") {
            themeIcon.classList.remove("bi-moon-fill");
            themeIcon.classList.add("bi-sun-fill");
            themeToggle.title = "Passer en mode clair";
        } else {
            themeIcon.classList.remove("bi-sun-fill");
            themeIcon.classList.add("bi-moon-fill");
            themeToggle.title = "Passer en mode sombre";
        }
    }

    // Initialiser l'icône
    updateIcon();

    // Basculer le thème au clic
    themeToggle.addEventListener("click", () => {
        const currentTheme =
            document.documentElement.getAttribute("data-theme");
        const newTheme = currentTheme === "dark" ? "light" : "dark";

        document.documentElement.setAttribute("data-theme", newTheme);
        localStorage.setItem("theme", newTheme);
        updateIcon();

        // Émettre un événement personnalisé pour les composants qui en ont besoin
        window.dispatchEvent(
            new CustomEvent("themechange", { detail: { theme: newTheme } }),
        );
    });

    // Écouter les changements de préférence système
    window
        .matchMedia("(prefers-color-scheme: dark)")
        .addEventListener("change", (e) => {
            // Ne changer que si l'utilisateur n'a pas de préférence enregistrée
            if (!localStorage.getItem("theme")) {
                const newTheme = e.matches ? "dark" : "light";
                document.documentElement.setAttribute("data-theme", newTheme);
                updateIcon();
            }
        });
}

function initBarcodeScanner() {
    const scanBtn = document.getElementById("scan-btn");
    const scannerContainer = document.getElementById("scanner-container");
    const barcodeInput = document.getElementById("barcode");
    const scannerTarget = document.getElementById("scanner");

    if (!scanBtn || !window.Quagga) {
        return;
    }

    scanBtn.addEventListener("click", () => {
        scannerContainer.style.display = "block";
        try {
            Quagga.init(
                {
                    inputStream: {
                        name: "Live",
                        type: "LiveStream",
                        target: scannerTarget,
                        constraints: {
                            facingMode: "environment",
                            width: { ideal: 1280 },
                            height: { ideal: 720 },
                        },
                    },
                    decoder: {
                        readers: [
                            "ean_reader",
                            "ean_8_reader",
                            "upc_reader",
                            "upc_e_reader",
                            "code_128_reader",
                        ],
                    },
                    locate: true,
                },
                (err) => {
                    if (err) {
                        console.error(err);
                        alert("Impossible d'initialiser la caméra");
                        return;
                    }
                    Quagga.start();
                },
            );

            const onDetected = (data) => {
                const code =
                    (data && data.codeResult && data.codeResult.code) || "";
                if (code) {
                    barcodeInput.value = code;
                    Quagga.stop();
                    Quagga.offDetected(onDetected);
                    scannerContainer.style.display = "none";
                }
            };
            Quagga.onDetected(onDetected);
        } catch (e) {
            console.error(e);
            alert(
                "Le scanner ne peut pas démarrer sur cet appareil/navigateur.",
            );
        }
    });
}

function initWineCards() {
    const cards = document.querySelectorAll(".wine-card");
    if (!cards.length || typeof bootstrap === "undefined") {
        return;
    }

    cards.forEach((card) => {
        let content = "Les informations enrichies arrivent…";
        try {
            const rawPreview = card.dataset.winePreview;
            if (rawPreview) {
                const preview = JSON.parse(rawPreview);
                if (Array.isArray(preview) && preview.length) {
                    content = preview
                        .map((item) => {
                            const title = item.title
                                ? `<strong>${item.title}</strong>`
                                : "";
                            const source = item.source
                                ? `<span class="text-muted"> (${item.source})</span>`
                                : "";
                            return `<div class="mb-2">${title}${source}<div>${escapeHtml(item.content)}</div></div>`;
                        })
                        .join("");
                }
            }
        } catch (err) {
            console.warn(
                "Impossible de parser les informations enrichies",
                err,
            );
        }

        const popover = new bootstrap.Popover(card, {
            trigger: "hover focus",
            placement: "auto",
            html: true,
            title:
                card.querySelector(".card-title")?.textContent ||
                "Informations",
            content,
        });

        card.addEventListener("click", (event) => {
            if (event.target.closest(".wine-action-form")) {
                return;
            }
            const url = card.dataset.detailUrl;
            if (url) {
                event.preventDefault();
                popover.hide();
                window.location.href = url;
            }
        });
    });
}

function initWineActions() {
    document
        .querySelectorAll(".wine-action-form[data-confirm]")
        .forEach((form) => {
            form.addEventListener("submit", (event) => {
                const message = form.getAttribute("data-confirm");
                if (message && !window.confirm(message)) {
                    event.preventDefault();
                }
            });
        });
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML.replace(/\n/g, "<br>");
}

function initMobileSearch() {
    const searchToggle = document.querySelector(".navbar-search-toggle");
    const searchMobile = document.querySelector(".navbar-search-mobile");
    const searchClose = document.querySelector(".navbar-search-close");
    const searchInput = searchMobile?.querySelector('input[name="q"]');

    if (!searchToggle || !searchMobile) {
        return;
    }

    // Ouvrir la barre de recherche mobile
    searchToggle.addEventListener("click", () => {
        searchMobile.style.display = "block";
        searchToggle.style.display = "none";
        if (searchInput) {
            searchInput.focus();
        }
    });

    // Fermer la barre de recherche mobile
    if (searchClose) {
        searchClose.addEventListener("click", () => {
            searchMobile.style.display = "none";
            searchToggle.style.display = "block";
            if (searchInput) {
                searchInput.value = "";
            }
        });
    }

    // Fermer avec la touche Escape
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && searchMobile.style.display === "block") {
            searchMobile.style.display = "none";
            searchToggle.style.display = "block";
            if (searchInput) {
                searchInput.value = "";
            }
        }
    });
}

/**
 * Indicateur de connexion hors-ligne
 */
function initOfflineIndicator() {
    // Créer l'indicateur hors-ligne
    const indicator = document.createElement("div");
    indicator.id = "offline-indicator";
    indicator.className = "offline-indicator";
    indicator.innerHTML = `
        <div class="offline-indicator-content">
            <i class="bi bi-wifi-off me-2"></i>
            <span>Mode hors-ligne</span>
        </div>
    `;
    indicator.style.cssText = `
        background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
        color: white;
        text-align: center;
        padding: 0;
        font-size: 0.875rem;
        font-weight: 500;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        overflow: hidden;
        max-height: 0;
        transition: max-height 0.3s ease, padding 0.3s ease;
    `;

    // Insérer le bandeau au tout début du body (avant la navbar)
    document.body.insertBefore(indicator, document.body.firstChild);

    // Fonction pour mettre à jour l'état
    function updateOnlineStatus() {
        if (navigator.onLine) {
            indicator.style.maxHeight = "0";
            indicator.style.padding = "0";
            document.body.classList.remove("is-offline");
            document.body.classList.add("is-online");

            // Synchroniser les données en attente
            if (
                "serviceWorker" in navigator &&
                "sync" in window.ServiceWorkerRegistration.prototype
            ) {
                navigator.serviceWorker.ready.then((registration) => {
                    registration.sync
                        .register("sync-offline-queue")
                        .catch(() => {});
                });
            }
        } else {
            indicator.style.maxHeight = "50px";
            indicator.style.padding = "8px 15px";
            document.body.classList.remove("is-online");
            document.body.classList.add("is-offline");
        }
    }

    // Écouter les changements de connexion
    window.addEventListener("online", updateOnlineStatus);
    window.addEventListener("offline", updateOnlineStatus);

    // Vérifier l'état initial
    updateOnlineStatus();

    // Vérifier périodiquement la connexion réelle (pas juste l'état du navigateur)
    setInterval(async () => {
        try {
            const response = await fetch("/api/ping", {
                method: "HEAD",
                cache: "no-store",
                timeout: 5000,
            });
            if (!response.ok && !navigator.onLine) {
                updateOnlineStatus();
            }
        } catch (e) {
            if (navigator.onLine) {
                // Le navigateur pense être en ligne mais pas de connexion réelle
                indicator.style.maxHeight = "50px";
                indicator.style.padding = "8px 15px";
                document.body.classList.add("is-offline");
            }
        }
    }, 30000); // Vérifier toutes les 30 secondes
}

/**
 * Gestion du cache pour le mode hors-ligne
 */
function initCacheManagement() {
    // Bouton pour vider le cache (si présent dans les paramètres)
    const clearCacheBtn = document.getElementById("clearCacheBtn");
    if (clearCacheBtn) {
        clearCacheBtn.addEventListener("click", async () => {
            clearCacheBtn.disabled = true;
            clearCacheBtn.innerHTML =
                '<span class="spinner-border spinner-border-sm me-1"></span>Nettoyage...';

            try {
                // Envoyer un message au service worker
                if ("serviceWorker" in navigator) {
                    const registration = await navigator.serviceWorker.ready;
                    registration.active.postMessage({ type: "CLEAR_CACHE" });
                }

                // Vider aussi le localStorage des données temporaires
                const keysToKeep = ["theme", "tutorialCompleted"];
                Object.keys(localStorage).forEach((key) => {
                    if (!keysToKeep.includes(key)) {
                        localStorage.removeItem(key);
                    }
                });

                showToast("Cache vidé avec succès", "success");
            } catch (error) {
                console.error("[Cache] Erreur:", error);
                showToast("Erreur lors du nettoyage du cache", "danger");
            }

            clearCacheBtn.disabled = false;
            clearCacheBtn.innerHTML =
                '<i class="bi bi-trash me-1"></i>Vider le cache';
        });
    }

    // Afficher les statistiques du cache (si élément présent)
    const cacheStatsEl = document.getElementById("cacheStats");
    if (cacheStatsEl) {
        updateCacheStats(cacheStatsEl);
    }

    // Pré-cacher la page actuelle pour le mode hors-ligne
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.ready.then((registration) => {
            // Mettre en cache la page actuelle
            registration.active?.postMessage({
                type: "CACHE_PAGE",
                url: window.location.pathname,
            });
        });
    }

    // Écouter les messages du service worker
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.addEventListener("message", (event) => {
            if (event.data.type === "CACHE_STATUS") {
                displayCacheStatus(event.data.status);
            }
        });
    }
}

async function updateCacheStats(element) {
    if (!("caches" in window)) {
        element.innerHTML =
            "<small class='text-muted'>Cache non disponible</small>";
        return;
    }

    try {
        const cacheNames = await caches.keys();
        let totalSize = 0;
        let totalItems = 0;

        for (const name of cacheNames) {
            const cache = await caches.open(name);
            const keys = await cache.keys();
            totalItems += keys.length;
        }

        element.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <span><i class="bi bi-database me-1"></i>Éléments en cache:</span>
                <span class="badge bg-secondary">${totalItems}</span>
            </div>
            <div class="d-flex justify-content-between align-items-center mt-1">
                <span><i class="bi bi-folder me-1"></i>Caches actifs:</span>
                <span class="badge bg-secondary">${cacheNames.length}</span>
            </div>
        `;
    } catch (error) {
        element.innerHTML =
            "<small class='text-muted'>Impossible de lire les statistiques</small>";
    }
}

function displayCacheStatus(status) {
    console.log("[Cache] Statut:", status);
    // Peut être utilisé pour afficher les détails dans l'UI
}

/**
 * Afficher un toast de notification
 */
function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = "position-fixed bottom-0 end-0 p-3";
    toast.style.zIndex = "1100";

    const bgClass =
        {
            success: "bg-success",
            danger: "bg-danger",
            warning: "bg-warning",
            info: "bg-info",
        }[type] || "bg-secondary";

    const icon =
        {
            success: "bi-check-circle",
            danger: "bi-exclamation-triangle",
            warning: "bi-exclamation-circle",
            info: "bi-info-circle",
        }[type] || "bi-info-circle";

    toast.innerHTML = `
        <div class="toast show ${bgClass} text-white" role="alert">
            <div class="toast-body d-flex align-items-center">
                <i class="bi ${icon} me-2"></i>
                ${message}
                <button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

/**
 * Demander la mise en cache d'une page spécifique
 */
function cachePageForOffline(url) {
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.ready.then((registration) => {
            registration.active?.postMessage({
                type: "CACHE_PAGE",
                url: url,
            });
        });
    }
}

// Exposer certaines fonctions globalement pour utilisation dans les templates
window.CaveVin = {
    showToast,
    cachePageForOffline,
    subscribeToPush,
    unsubscribeFromPush,
};
