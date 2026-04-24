window.ArborisListRowLinks = (function () {
    function init() {
        const rows = document.querySelectorAll("[data-row-href]");

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
