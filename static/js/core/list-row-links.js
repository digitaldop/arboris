window.ArborisListRowLinks = (function () {
    function openPopup(row, url) {
        if (typeof window.ArborisResetLongWaitCursor === "function") {
            window.ArborisResetLongWaitCursor();
        }

        const features = row.dataset.popupWindowFeatures || "width=1180,height=820,resizable=yes,scrollbars=yes";
        const title = row.dataset.popupTitle || row.getAttribute("aria-label") || "Scheda";

        if (window.ArborisModalPopups && typeof window.ArborisModalPopups.open === "function") {
            window.ArborisModalPopups.open(url, { features, title });
            return;
        }

        window.open(url, row.dataset.popupWindowName || "arboris-popup-window", features);
    }

    function init() {
        const rows = document.querySelectorAll("[data-row-href], [data-row-popup-url]");

        rows.forEach(row => {
            row.addEventListener("click", function (event) {
                const alwaysInteractive = event.target.closest("a, button, label");
                if (alwaysInteractive) {
                    return;
                }

                const formField = event.target.closest("input, select, textarea");
                if (formField && !formField.disabled && !formField.readOnly) {
                    return;
                }

                const detailForm = row.closest(".detail-form");
                if (detailForm && !detailForm.classList.contains("is-view-mode")) {
                    return;
                }

                const popupUrl = row.dataset.rowPopupUrl;
                if (popupUrl) {
                    openPopup(row, popupUrl);
                    return;
                }

                const href = row.dataset.rowHref;
                if (href) {
                    if (typeof window.ArborisArmLongWaitForNavigationUrl === "function") {
                        window.ArborisArmLongWaitForNavigationUrl(href);
                    }
                    window.location.assign(href);
                }
            });
        });
    }

    return {
        init,
    };
})();
