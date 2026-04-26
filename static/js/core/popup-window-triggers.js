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
                window.open(
                    popupUrl,
                    element.dataset.popupWindowName || "arboris-popup-window",
                    element.dataset.popupWindowFeatures || "width=760,height=680,resizable=yes,scrollbars=yes"
                );
            });
        });
    }

    return {
        wire: wire,
    };
})();
