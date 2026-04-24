window.ArborisContrattoPopupForm = (function () {
    function init(config) {
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

        function replaceId(url, id) {
            return url.replace("/0/", `/${id}/`);
        }

        function updateButtons() {
            if (editParametroBtn && parametroSelect) {
                editParametroBtn.disabled = !parametroSelect.value;
            }
            if (deleteParametroBtn && parametroSelect) {
                deleteParametroBtn.disabled = !parametroSelect.value;
            }
        }

        if (addParametroBtn && parametroSelect) {
            addParametroBtn.addEventListener("click", function () {
                relatedPopups.openRelatedPopup(
                    `${config.urls.creaParametroCalcolo}?popup=1&target_input_name=${encodeURIComponent(parametroSelect.name)}`
                );
            });
        }

        if (editParametroBtn && parametroSelect) {
            editParametroBtn.addEventListener("click", function () {
                if (!parametroSelect.value) {
                    return;
                }
                const url = replaceId(config.urls.modificaParametroCalcoloTemplate, parametroSelect.value);
                relatedPopups.openRelatedPopup(
                    `${url}?popup=1&target_input_name=${encodeURIComponent(parametroSelect.name)}`
                );
            });
        }

        if (deleteParametroBtn && parametroSelect) {
            deleteParametroBtn.addEventListener("click", function () {
                if (!parametroSelect.value) {
                    return;
                }
                const url = replaceId(config.urls.eliminaParametroCalcoloTemplate, parametroSelect.value);
                relatedPopups.openRelatedPopup(
                    `${url}?popup=1&target_input_name=${encodeURIComponent(parametroSelect.name)}`
                );
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
