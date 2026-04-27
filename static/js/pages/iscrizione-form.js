window.ArborisIscrizioneForm = (function () {
    function init() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!relatedPopups || !routes) {
            return;
        }

        const relatedFieldConfigs = [
            {
                relatedType: "studente",
                selectId: "id_studente",
                addBtnId: "add-studente-btn",
                editBtnId: "edit-studente-btn",
                deleteBtnId: "delete-studente-btn",
            },
            {
                relatedType: "anno_scolastico",
                selectId: "id_anno_scolastico",
                addBtnId: "add-anno-scolastico-btn",
                editBtnId: "edit-anno-scolastico-btn",
                deleteBtnId: "delete-anno-scolastico-btn",
            },
            {
                relatedType: "classe",
                selectId: "id_classe",
                addBtnId: "add-classe-btn",
                editBtnId: "edit-classe-btn",
                deleteBtnId: "delete-classe-btn",
            },
            {
                relatedType: "stato_iscrizione",
                selectId: "id_stato_iscrizione",
                addBtnId: "add-stato-iscrizione-btn",
                editBtnId: "edit-stato-iscrizione-btn",
                deleteBtnId: "delete-stato-iscrizione-btn",
            },
            {
                relatedType: "condizione_iscrizione",
                selectId: "id_condizione_iscrizione",
                addBtnId: "add-condizione-iscrizione-btn",
                editBtnId: "edit-condizione-iscrizione-btn",
                deleteBtnId: "delete-condizione-iscrizione-btn",
            },
            {
                relatedType: "agevolazione",
                selectId: "id_agevolazione",
                addBtnId: "add-agevolazione-btn",
                editBtnId: "edit-agevolazione-btn",
                deleteBtnId: "delete-agevolazione-btn",
            },
        ];

        routes.wireCrudButtonsGroup(relatedFieldConfigs, {
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });

        const condizioneSelect = document.getElementById("id_condizione_iscrizione");
        const agevolazioneSelect = document.getElementById("id_agevolazione");
        const riduzioneCheckbox = document.getElementById("id_riduzione_speciale");
        const importoInput = document.getElementById("id_importo_riduzione_speciale");
        const agevolazioneRow = document.querySelector(".iscrizione-agevolazione-row");
        const riduzioneRow = document.querySelector(".iscrizione-riduzione-row");
        const importoRow = document.querySelector(".iscrizione-importo-riduzione-row");
        const detailForm = document.getElementById("iscrizione-detail-form");

        if (condizioneSelect && riduzioneCheckbox && importoInput) {
            function condizioneAmmetteRiduzioni() {
                const selected = condizioneSelect.options[condizioneSelect.selectedIndex];
                return !selected || selected.dataset.riduzioneSpecialeAmmessa !== "0";
            }

            function syncRiduzioneSpeciale() {
                const riduzioniAmmesse = condizioneAmmetteRiduzioni();
                const enabled = riduzioniAmmesse && riduzioneCheckbox.checked;
                const isViewMode = detailForm && detailForm.classList.contains("is-view-mode");
                const currencyGroup = importoInput.closest(".currency-input-group");

                if (isViewMode) {
                    if (agevolazioneRow) agevolazioneRow.classList.remove("is-hidden");
                    if (riduzioneRow) riduzioneRow.classList.remove("is-hidden");
                    if (importoRow) importoRow.classList.toggle("is-hidden", !riduzioneCheckbox.checked);
                    return;
                }

                if (agevolazioneRow) agevolazioneRow.classList.toggle("is-hidden", !riduzioniAmmesse);
                if (riduzioneRow) riduzioneRow.classList.toggle("is-hidden", !riduzioniAmmesse);
                if (importoRow) importoRow.classList.toggle("is-hidden", !riduzioniAmmesse || !enabled);

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
            ["enable-edit-iscrizione-btn", "cancel-edit-iscrizione-btn"].forEach(function (buttonId) {
                const button = document.getElementById(buttonId);
                if (button) {
                    button.addEventListener("click", function () {
                        window.setTimeout(syncRiduzioneSpeciale, 0);
                    });
                }
            });
            syncRiduzioneSpeciale();
        }
    }

    return {
        init,
    };
})();
