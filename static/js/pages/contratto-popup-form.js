window.ArborisContrattoPopupForm = (function () {
    function init() {
        const relatedPopups = window.ArborisRelatedPopups;
        if (!relatedPopups) {
            return;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        const parametroSelect = document.getElementById("id_parametro_calcolo");
        const addParametroBtn = document.getElementById("popup-add-parametro-calcolo-btn");
        const editParametroBtn = document.getElementById("popup-edit-parametro-calcolo-btn");
        const deleteParametroBtn = document.getElementById("popup-delete-parametro-calcolo-btn");
        const routes = window.ArborisRelatedEntityRoutes;

        function updateButtons() {
            if (editParametroBtn && parametroSelect) {
                editParametroBtn.disabled = !parametroSelect.value;
            }
            if (deleteParametroBtn && parametroSelect) {
                deleteParametroBtn.disabled = !parametroSelect.value;
            }
        }

        if (addParametroBtn && parametroSelect && routes) {
            addParametroBtn.addEventListener("click", function () {
                const cfg = routes.buildCrudUrls("parametro_calcolo", null, parametroSelect.name);
                if (cfg && cfg.addUrl) {
                    relatedPopups.openRelatedPopup(cfg.addUrl);
                }
            });
        }

        if (editParametroBtn && parametroSelect && routes) {
            editParametroBtn.addEventListener("click", function () {
                if (!parametroSelect.value) {
                    return;
                }
                const cfg = routes.buildCrudUrls("parametro_calcolo", parametroSelect.value, parametroSelect.name);
                if (cfg && cfg.editUrl) {
                    relatedPopups.openRelatedPopup(cfg.editUrl);
                }
            });
        }

        if (deleteParametroBtn && parametroSelect && routes) {
            deleteParametroBtn.addEventListener("click", function () {
                if (!parametroSelect.value) {
                    return;
                }
                const cfg = routes.buildCrudUrls("parametro_calcolo", parametroSelect.value, parametroSelect.name);
                if (cfg && cfg.deleteUrl) {
                    relatedPopups.openRelatedPopup(cfg.deleteUrl);
                }
            });
        }

        if (parametroSelect) {
            parametroSelect.addEventListener("change", updateButtons);
        }

        updateButtons();
    }

    return {
        init,
    };
})();
