window.ArborisDipendenteForm = (function () {
    function init(config) {
        const relatedPopups = window.ArborisRelatedPopups;
        if (!relatedPopups) {
            return;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        const indirizzoSelect = document.getElementById("id_indirizzo");
        const addIndirizzoBtn = document.getElementById("add-indirizzo-btn");
        const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
        const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");
        const contrattoSelect = document.getElementById("id_contratto");
        const addContrattoBtn = document.getElementById("add-contratto-btn");
        const editContrattoBtn = document.getElementById("edit-contratto-btn");
        const deleteContrattoBtn = document.getElementById("delete-contratto-btn");

        function replaceId(url, id) {
            return url.replace("/0/", `/${id}/`);
        }

        function updateAddressButtons() {
            if (editIndirizzoBtn && indirizzoSelect) editIndirizzoBtn.disabled = !indirizzoSelect.value;
            if (deleteIndirizzoBtn && indirizzoSelect) deleteIndirizzoBtn.disabled = !indirizzoSelect.value;
        }

        function updateContrattoButtons() {
            if (editContrattoBtn && contrattoSelect) editContrattoBtn.disabled = !contrattoSelect.value;
            if (deleteContrattoBtn && contrattoSelect) deleteContrattoBtn.disabled = !contrattoSelect.value;
        }

        if (addIndirizzoBtn && indirizzoSelect) {
            addIndirizzoBtn.addEventListener("click", function () {
                relatedPopups.openRelatedPopup(`${config.urls.creaIndirizzo}?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
            });
        }

        if (editIndirizzoBtn && indirizzoSelect) {
            editIndirizzoBtn.addEventListener("click", function () {
                if (!indirizzoSelect.value) return;
                relatedPopups.openRelatedPopup(`/indirizzi/${indirizzoSelect.value}/modifica/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
            });
        }

        if (deleteIndirizzoBtn && indirizzoSelect) {
            deleteIndirizzoBtn.addEventListener("click", function () {
                if (!indirizzoSelect.value) return;
                relatedPopups.openRelatedPopup(`/indirizzi/${indirizzoSelect.value}/elimina/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
            });
        }

        if (indirizzoSelect) {
            indirizzoSelect.addEventListener("change", updateAddressButtons);
        }

        if (addContrattoBtn && contrattoSelect) {
            addContrattoBtn.addEventListener("click", function () {
                let url = `${config.urls.creaContratto}?popup=1&target_input_name=${encodeURIComponent(contrattoSelect.name)}`;
                if (config.dipendenteId) {
                    url += `&dipendente=${encodeURIComponent(config.dipendenteId)}`;
                }
                relatedPopups.openRelatedPopup(url);
            });
        }

        if (editContrattoBtn && contrattoSelect) {
            editContrattoBtn.addEventListener("click", function () {
                if (!contrattoSelect.value) return;
                const url = replaceId(config.urls.modificaContrattoTemplate, contrattoSelect.value);
                relatedPopups.openRelatedPopup(`${url}?popup=1&target_input_name=${encodeURIComponent(contrattoSelect.name)}`);
            });
        }

        if (deleteContrattoBtn && contrattoSelect) {
            deleteContrattoBtn.addEventListener("click", function () {
                if (!contrattoSelect.value) return;
                const url = replaceId(config.urls.eliminaContrattoTemplate, contrattoSelect.value);
                relatedPopups.openRelatedPopup(`${url}?popup=1&target_input_name=${encodeURIComponent(contrattoSelect.name)}`);
            });
        }

        if (contrattoSelect) {
            contrattoSelect.addEventListener("change", updateContrattoButtons);
        }

        updateAddressButtons();
        updateContrattoButtons();
    }

    return { init };
})();
