document.addEventListener("DOMContentLoaded", () => {
    initServiceWorker();
    initThemeToggle();
    initBarcodeScanner();
    initWineCards();
    initWineActions();
    initMobileSearch();
    initPushNotifications();
    initTutorial();
});

/**
 * Enregistrement du Service Worker pour la PWA
 */
function initServiceWorker() {
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker
                .register("/static/sw.js")
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
    if (!enableBtn) return;

    // Vérifier si les notifications sont supportées
    if (!("Notification" in window) || !("serviceWorker" in navigator)) {
        enableBtn.disabled = true;
        enableBtn.textContent = "Notifications non supportées";
        return;
    }

    // Mettre à jour l'état du bouton
    updateNotificationButton(enableBtn);

    enableBtn.addEventListener("click", async () => {
        if (Notification.permission === "granted") {
            // Désactiver les notifications
            await unsubscribeFromPush();
            updateNotificationButton(enableBtn);
        } else {
            // Demander la permission
            const permission = await Notification.requestPermission();
            if (permission === "granted") {
                await subscribeToPush();
            }
            updateNotificationButton(enableBtn);
        }
    });
}

function updateNotificationButton(btn) {
    if (Notification.permission === "granted") {
        btn.innerHTML =
            '<i class="bi bi-bell-slash me-1"></i>Désactiver les notifications';
        btn.classList.remove("btn-primary");
        btn.classList.add("btn-outline-secondary");
    } else if (Notification.permission === "denied") {
        btn.innerHTML =
            '<i class="bi bi-bell-slash me-1"></i>Notifications bloquées';
        btn.disabled = true;
    } else {
        btn.innerHTML =
            '<i class="bi bi-bell me-1"></i>Activer les notifications';
        btn.classList.remove("btn-outline-secondary");
        btn.classList.add("btn-primary");
    }
}

async function subscribeToPush() {
    try {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(
                window.VAPID_PUBLIC_KEY || "",
            ),
        });

        // Envoyer la subscription au serveur
        await fetch("/api/push/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(subscription),
        });

        console.log("[Push] Abonnement réussi");
    } catch (error) {
        console.error("[Push] Erreur d'abonnement:", error);
    }
}

async function unsubscribeFromPush() {
    try {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();

        if (subscription) {
            await subscription.unsubscribe();

            // Informer le serveur
            await fetch("/api/push/unsubscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ endpoint: subscription.endpoint }),
            });
        }

        console.log("[Push] Désabonnement réussi");
    } catch (error) {
        console.error("[Push] Erreur de désabonnement:", error);
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
