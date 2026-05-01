window.ArborisPopupWindowTriggers = (function () {
    function wire(container, options) {
        const root = container || document;
        const cfg = options || {};
        const selector = cfg.selector || "[data-window-popup='1']";

        if (!root || typeof root.querySelectorAll !== "function") {
            return;
        }

        root.querySelectorAll(selector).forEach(function (element) {
            if (element.dataset.windowPopupBound === "1") {
                return;
            }

            element.dataset.windowPopupBound = "1";
            element.addEventListener("click", function (event) {
                const popupUrl = element.dataset.popupUrl;
                if (!popupUrl || element.disabled) {
                    return;
                }

                event.preventDefault();
                const windowName = element.dataset.popupWindowName || "arboris-popup-window";
                const windowFeatures = element.dataset.popupWindowFeatures || "width=760,height=680,resizable=yes,scrollbars=yes";
                if (window.ArborisRelatedPopups && typeof window.ArborisRelatedPopups.openManagedPopup === "function") {
                    window.ArborisRelatedPopups.openManagedPopup(popupUrl, windowName, windowFeatures, {
                        lockMessage: "Completa il popup aperto per continuare.",
                    });
                    return;
                }

                window.open(popupUrl, windowName, windowFeatures);
            });
        });
    }

    return {
        wire: wire,
    };
})();
