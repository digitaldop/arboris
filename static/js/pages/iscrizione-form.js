window.ArborisIscrizioneForm = (function () {
    function init() {
        const relatedPopups = window.ArborisRelatedPopups;
        if (!relatedPopups) {
            return;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        function bindRelatedField(config) {
            const select = document.getElementById(config.selectId);
            const addBtn = document.getElementById(config.addBtnId);
            const editBtn = document.getElementById(config.editBtnId);
            const deleteBtn = document.getElementById(config.deleteBtnId);

            if (!select || !addBtn || !editBtn || !deleteBtn) {
                return;
            }

            function refreshButtons() {
                const hasValue = Boolean(select.value);
                editBtn.disabled = !hasValue;
                deleteBtn.disabled = !hasValue;
            }

            addBtn.addEventListener("click", function () {
                relatedPopups.openRelatedPopup(`${config.baseAddUrl}?popup=1&target_input_name=${encodeURIComponent(select.name)}`);
            });

            editBtn.addEventListener("click", function () {
                if (!select.value) return;
                relatedPopups.openRelatedPopup(`${config.baseEditUrl.replace("__id__", select.value)}?popup=1&target_input_name=${encodeURIComponent(select.name)}`);
            });

            deleteBtn.addEventListener("click", function () {
                if (!select.value) return;
                relatedPopups.openRelatedPopup(`${config.baseDeleteUrl.replace("__id__", select.value)}?popup=1&target_input_name=${encodeURIComponent(select.name)}`);
            });

            select.addEventListener("change", refreshButtons);
            refreshButtons();
        }

        bindRelatedField({
            selectId: "id_studente",
            addBtnId: "add-studente-btn",
            editBtnId: "edit-studente-btn",
            deleteBtnId: "delete-studente-btn",
            baseAddUrl: "/studenti/nuovo/",
            baseEditUrl: "/studenti/__id__/modifica/",
            baseDeleteUrl: "/studenti/__id__/elimina/",
        });

        bindRelatedField({
            selectId: "id_anno_scolastico",
            addBtnId: "add-anno-scolastico-btn",
            editBtnId: "edit-anno-scolastico-btn",
            deleteBtnId: "delete-anno-scolastico-btn",
            baseAddUrl: "/scuola/anni-scolastici/nuovo/",
            baseEditUrl: "/scuola/anni-scolastici/__id__/modifica/",
            baseDeleteUrl: "/scuola/anni-scolastici/__id__/elimina/",
        });

        bindRelatedField({
            selectId: "id_classe",
            addBtnId: "add-classe-btn",
            editBtnId: "edit-classe-btn",
            deleteBtnId: "delete-classe-btn",
            baseAddUrl: "/scuola/classi/nuova/",
            baseEditUrl: "/scuola/classi/__id__/modifica/",
            baseDeleteUrl: "/scuola/classi/__id__/elimina/",
        });

        bindRelatedField({
            selectId: "id_stato_iscrizione",
            addBtnId: "add-stato-iscrizione-btn",
            editBtnId: "edit-stato-iscrizione-btn",
            deleteBtnId: "delete-stato-iscrizione-btn",
            baseAddUrl: "/economia/stati-iscrizione/nuovo/",
            baseEditUrl: "/economia/stati-iscrizione/__id__/modifica/",
            baseDeleteUrl: "/economia/stati-iscrizione/__id__/elimina/",
        });

        bindRelatedField({
            selectId: "id_condizione_iscrizione",
            addBtnId: "add-condizione-iscrizione-btn",
            editBtnId: "edit-condizione-iscrizione-btn",
            deleteBtnId: "delete-condizione-iscrizione-btn",
            baseAddUrl: "/economia/condizioni-iscrizione/nuova/",
            baseEditUrl: "/economia/condizioni-iscrizione/__id__/modifica/",
            baseDeleteUrl: "/economia/condizioni-iscrizione/__id__/elimina/",
        });

        bindRelatedField({
            selectId: "id_agevolazione",
            addBtnId: "add-agevolazione-btn",
            editBtnId: "edit-agevolazione-btn",
            deleteBtnId: "delete-agevolazione-btn",
            baseAddUrl: "/economia/agevolazioni/nuova/",
            baseEditUrl: "/economia/agevolazioni/__id__/modifica/",
            baseDeleteUrl: "/economia/agevolazioni/__id__/elimina/",
        });

        const condizioneSelect = document.getElementById("id_condizione_iscrizione");
        const agevolazioneSelect = document.getElementById("id_agevolazione");
        const riduzioneCheckbox = document.getElementById("id_riduzione_speciale");
        const importoInput = document.getElementById("id_importo_riduzione_speciale");
        const agevolazioneRow = document.querySelector(".iscrizione-agevolazione-row");
        const riduzioneRow = document.querySelector(".iscrizione-riduzione-row");
        const importoRow = document.querySelector(".iscrizione-importo-riduzione-row");

        if (condizioneSelect && riduzioneCheckbox && importoInput) {
            function condizioneAmmetteRiduzioni() {
                const selected = condizioneSelect.options[condizioneSelect.selectedIndex];
                return !selected || selected.dataset.riduzioneSpecialeAmmessa !== "0";
            }

            function syncRiduzioneSpeciale() {
                const riduzioniAmmesse = condizioneAmmetteRiduzioni();
                const enabled = riduzioniAmmesse && riduzioneCheckbox.checked;
                const currencyGroup = importoInput.closest(".currency-input-group");

                if (agevolazioneRow) agevolazioneRow.classList.toggle("is-hidden", !riduzioniAmmesse);
                if (riduzioneRow) riduzioneRow.classList.toggle("is-hidden", !riduzioniAmmesse);
                if (importoRow) importoRow.classList.toggle("is-hidden", !riduzioniAmmesse);

                if (!riduzioniAmmesse) {
                    if (agevolazioneSelect) {
                        agevolazioneSelect.value = "";
                    }
                    riduzioneCheckbox.checked = false;
                }

                importoInput.readOnly = !enabled;
                importoInput.classList.toggle("is-readonly", !enabled);
                if (currencyGroup) {
                    currencyGroup.classList.toggle("is-disabled", !enabled || !riduzioniAmmesse);
                }

                if (!enabled) {
                    importoInput.value = "0.00";
                }
            }

            condizioneSelect.addEventListener("change", syncRiduzioneSpeciale);
            riduzioneCheckbox.addEventListener("change", syncRiduzioneSpeciale);
            syncRiduzioneSpeciale();
        }
    }

    return {
        init,
    };
})();
