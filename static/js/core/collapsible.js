window.ArborisCollapsible = (function () {
    function getStoredState(storageKey) {
        if (!storageKey) return null;

        try {
            const value = window.localStorage.getItem(storageKey);
            if (value === "open") return true;
            if (value === "closed") return false;
        } catch (e) {}

        return null;
    }

    function saveState(storageKey, isOpen) {
        if (!storageKey) return;

        try {
            window.localStorage.setItem(storageKey, isOpen ? "open" : "closed");
        } catch (e) {}
    }

    function setState(btn, panel, isOpen) {
        panel.classList.toggle("is-open", isOpen);
        btn.classList.toggle("is-open", isOpen);
        btn.setAttribute("aria-expanded", isOpen ? "true" : "false");

        const label = isOpen ? btn.dataset.labelOpen : btn.dataset.labelClosed;
        if (label) {
            const labelNode = btn.querySelector("[data-collapsible-label]");
            if (labelNode) {
                labelNode.textContent = label;
            } else {
                btn.textContent = label;
            }
        }

        saveState(btn.dataset.storageKey, isOpen);
    }

    // Funzione per gestire le sezioni collapsible (se presenti)
    function initCollapsibleSections(container = document) {
        container.querySelectorAll(".collapsible-title").forEach(btn => {
            if (btn.dataset.collapsibleBound === "1") {
                return;
            }

            btn.dataset.collapsibleBound = "1";

            const targetId = btn.dataset.target;
            const panel = document.getElementById(targetId);

            if (!panel) return;

            const storedState = getStoredState(btn.dataset.storageKey);
            if (storedState !== null) {
                setState(btn, panel, storedState);
            } else {
                const defaultOpen = btn.dataset.defaultOpen !== "false";
                setState(btn, panel, panel.classList.contains("is-open") || defaultOpen);
            }

            btn.addEventListener("click", function () {
                const isOpen = panel.classList.contains("is-open");
                setState(btn, panel, !isOpen);
            });
        });

        if (container === document || container === document.documentElement || container === document.body) {
            document.documentElement.classList.remove("sidebar-state-preload");
            const initialStyle = document.getElementById("sidebar-initial-state-style");
            if (initialStyle) {
                initialStyle.remove();
            }
        }
    }

    return {
        initCollapsibleSections,
    };
})();
