window.ArborisTabs = (function () {
    // Funzione per attivare una tab specifica
    function activateTab(tabId, storageKey = null) {
        document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("is-active"));
        document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("is-active"));

        const btn = document.querySelector(`[data-tab-target="${tabId}"]`);
        const panel = document.getElementById(tabId);

        if (btn) btn.classList.add("is-active");
        if (panel) panel.classList.add("is-active");

        if (storageKey) {
            try {
                localStorage.setItem(storageKey, tabId);
            } catch (e) {}
        }
    }

    // Funzione per ripristinare la tab attiva al caricamento della pagina
    function restoreActiveTab(storageKey = null) {
        let savedTabId = null;

        if (storageKey) {
            try {
                savedTabId = localStorage.getItem(storageKey);
            } catch (e) {}
        }

        const existingPanel = savedTabId ? document.getElementById(savedTabId) : null;

        if (existingPanel) {
            activateTab(savedTabId, storageKey);
        } else {
            const defaultBtn = document.querySelector(".tab-btn.is-active") || document.querySelector(".tab-btn");
            if (defaultBtn) {
                activateTab(defaultBtn.dataset.tabTarget, storageKey);
            }
        }
    }

    function bindTabButtons(storageKey = null, container = document) {
        container.querySelectorAll(".tab-btn").forEach(btn => {
            if (btn.dataset.tabBound === "1") {
                return;
            }

            btn.dataset.tabBound = "1";

            btn.addEventListener("click", function (event) {
                const beforeEvent = new CustomEvent("arboris:before-tab-activate", {
                    bubbles: true,
                    cancelable: true,
                    detail: {
                        tabId: btn.dataset.tabTarget,
                        button: btn,
                    },
                });

                if (!btn.dispatchEvent(beforeEvent) || beforeEvent.defaultPrevented) {
                    event.preventDefault();
                    return;
                }

                activateTab(btn.dataset.tabTarget, storageKey);
            });
        });
    }

    return {
        activateTab,
        restoreActiveTab,
        bindTabButtons,
    };
})();
