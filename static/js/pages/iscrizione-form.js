window.ArborisIscrizioneForm = (function () {
    function init() {
        const relatedPopups = window.ArborisRelatedPopups;
        if (!relatedPopups) {
            return;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        function bindRelatedField(relatedType, selectId, addBtnId, editBtnId, deleteBtnId) {
            const select = document.getElementById(selectId);
            const addBtn = document.getElementById(addBtnId);
            const editBtn = document.getElementById(editBtnId);
            const deleteBtn = document.getElementById(deleteBtnId);
            const routes = window.ArborisRelatedEntityRoutes;

            if (!select || !addBtn || !editBtn || !deleteBtn || !routes) {
                return;
            }

            function refreshButtons() {
                const hasValue = Boolean(select.value);
                editBtn.disabled = !hasValue;
                deleteBtn.disabled = !hasValue;
            }

            addBtn.addEventListener("click", function () {
                const cfg = routes.buildCrudUrls(relatedType, null, select.name);
                if (cfg && cfg.addUrl) {
                    relatedPopups.openRelatedPopup(cfg.addUrl);
                }
            });

            editBtn.addEventListener("click", function () {
                if (!select.value) return;
                const cfg = routes.buildCrudUrls(relatedType, select.value, select.name);
                if (cfg && cfg.editUrl) {
                    relatedPopups.openRelatedPopup(cfg.editUrl);
                }
            });

            deleteBtn.addEventListener("click", function () {
                if (!select.value) return;
                const cfg = routes.buildCrudUrls(relatedType, select.value, select.name);
                if (cfg && cfg.deleteUrl) {
                    relatedPopups.openRelatedPopup(cfg.deleteUrl);
                }
            });

            select.addEventListener("change", refreshButtons);
            refreshButtons();
        }

        bindRelatedField("studente", "id_studente", "add-studente-btn", "edit-studente-btn", "delete-studente-btn");
        bindRelatedField(
            "anno_scolastico",
            "id_anno_scolastico",
            "add-anno-scolastico-btn",
            "edit-anno-scolastico-btn",
            "delete-anno-scolastico-btn"
        );
        bindRelatedField("classe", "id_classe", "add-classe-btn", "edit-classe-btn", "delete-classe-btn");
        bindRelatedField(
            "stato_iscrizione",
            "id_stato_iscrizione",
            "add-stato-iscrizione-btn",
            "edit-stato-iscrizione-btn",
            "delete-stato-iscrizione-btn"
        );
        bindRelatedField(
            "condizione_iscrizione",
            "id_condizione_iscrizione",
            "add-condizione-iscrizione-btn",
            "edit-condizione-iscrizione-btn",
            "delete-condizione-iscrizione-btn"
        );
        bindRelatedField(
            "agevolazione",
            "id_agevolazione",
            "add-agevolazione-btn",
            "edit-agevolazione-btn",
            "delete-agevolazione-btn"
        );

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
