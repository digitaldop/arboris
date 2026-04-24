window.ArborisStudenteForm = (function () {
    let refreshInlineEditScopeHandler = function () {};

    function init(config) {
        const relatedPopups = window.ArborisRelatedPopups;
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;

        if (!relatedPopups || !collapsible || !tabs) {
            console.error("Arboris core JS non caricato correttamente.");
            return;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        function getStudenteTabStorageKey() {
            return `arboris-studente-form-active-tab-v2-${config.studenteId || "new"}`;
        }

        const studenteInlineRoot = () => document.getElementById("studente-inline-lock-container");

        function setInlineTarget(prefixOrTabId) {
            const input = document.getElementById("studente-inline-target");
            if (!input || !prefixOrTabId) {
                return;
            }

            input.value = prefixOrTabId.replace(/^tab-/, "");
        }

        function tabTitleForInlineEditLabel(tabButton) {
            if (!tabButton) {
                return "";
            }

            return tabButton.textContent.replace(/\s*\([^)]*\)\s*$/, "").replace(/\s+/g, " ").trim();
        }

        function refreshInlineEditScope() {
            const form = document.getElementById("studente-detail-form");
            const panels = document.querySelectorAll('#studente-inline-lock-container .tab-panel[data-inline-scope]');
            const targetInput = document.getElementById("studente-inline-target");
            const target = targetInput ? targetInput.value : "";
            const isEditing = Boolean(
                window.studenteViewMode &&
                typeof window.studenteViewMode.isEditing === "function" &&
                window.studenteViewMode.isEditing()
            );
            const isInlineEditing = Boolean(
                window.studenteViewMode &&
                typeof window.studenteViewMode.isInlineEditing === "function" &&
                window.studenteViewMode.isInlineEditing()
            );

            if (form) {
                form.classList.toggle("is-inline-iscrizioni-layout", isEditing && target === "iscrizioni");

                if (isEditing && target) {
                    form.dataset.inlineEditTarget = target;
                } else {
                    delete form.dataset.inlineEditTarget;
                }
            }

            panels.forEach(panel => {
                const isTarget = isEditing && panel.dataset.inlineScope === target;
                panel.classList.toggle("is-inline-edit-target", isTarget);
            });

            refreshLockedTabs();

            if (!isInlineEditing) {
                const root = studenteInlineRoot();
                const activeTab = root ? root.querySelector(".tab-btn.is-active") : null;
                if (activeTab && activeTab.dataset.tabTarget) {
                    updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
                }
            }
        }

        refreshInlineEditScopeHandler = refreshInlineEditScope;

        function updateInlineEditButtonLabel(tabId) {
            const button = document.getElementById("enable-inline-edit-studente-btn");
            if (!button) {
                return;
            }
            if (
                window.studenteViewMode &&
                typeof window.studenteViewMode.isInlineEditing === "function" &&
                window.studenteViewMode.isInlineEditing()
            ) {
                return;
            }

            const root = studenteInlineRoot();
            const tabBtn = root && tabId ? root.querySelector(`.tab-btn[data-tab-target="${tabId}"]`) : null;
            const tabTitle = tabTitleForInlineEditLabel(tabBtn);

            button.textContent = tabTitle ? `Modifica ${tabTitle}` : "Modifica";
        }

        function refreshLockedTabs() {
            const targetInput = document.getElementById("studente-inline-target");
            const target = targetInput ? targetInput.value : "";
            const isInlineEditing = Boolean(
                window.studenteViewMode &&
                typeof window.studenteViewMode.isInlineEditing === "function" &&
                window.studenteViewMode.isInlineEditing()
            );
            const lockMessage = "Non è possibile cambiare tab finché non si salvano o annullano le modifiche correnti.";

            document.querySelectorAll("#studente-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
                const btnTarget = (btn.dataset.tabTarget || "").replace(/^tab-/, "");
                const locked = isInlineEditing && target && btnTarget !== target;
                btn.classList.toggle("is-tab-locked", locked);

                if (locked) {
                    btn.setAttribute("data-tab-lock-message", lockMessage);
                } else {
                    btn.removeAttribute("data-tab-lock-message");
                }
            });
        }

        function getSelectedFamigliaOption() {
            const famigliaSelect = document.getElementById("id_famiglia");
            if (!famigliaSelect) {
                return null;
            }

            return famigliaSelect.options[famigliaSelect.selectedIndex] || null;
        }

        function normalizePersonName(value) {
            return (value || "")
                .toString()
                .trim()
                .toLowerCase()
                .normalize("NFD")
                .replace(/[\u0300-\u036f]/g, "");
        }

        function inferSexFromFirstName(value) {
            const firstName = normalizePersonName(value).split(/\s+/)[0] || "";
            if (!firstName) {
                return "";
            }

            const commonMaleEndingInA = [
                "andrea",
                "luca",
                "nicola",
                "mattia",
                "elia",
                "tobia",
                "enea",
                "gianluca",
            ];

            if (commonMaleEndingInA.includes(firstName)) {
                return "M";
            }

            if (firstName.endsWith("a")) {
                return "F";
            }

            if (firstName.endsWith("o")) {
                return "M";
            }

            return "";
        }

        function syncStandaloneSexFromNome() {
            const nomeInput = document.getElementById("id_nome");
            const sessoSelect = document.getElementById("id_sesso");

            if (!nomeInput || !sessoSelect || sessoSelect.value) {
                return;
            }

            const inferredSex = inferSexFromFirstName(nomeInput.value);
            if (!inferredSex) {
                return;
            }

            sessoSelect.value = inferredSex;
            sessoSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }

        function bindStandaloneSexFromNome() {
            const nomeInput = document.getElementById("id_nome");
            if (!nomeInput || nomeInput.dataset.sexBound === "1") {
                return;
            }

            nomeInput.dataset.sexBound = "1";
            nomeInput.addEventListener("change", syncStandaloneSexFromNome);
            nomeInput.addEventListener("input", syncStandaloneSexFromNome);
            syncStandaloneSexFromNome();
        }

        function updateInheritedAddressPlaceholder() {
            const indirizzoSelect = document.getElementById("id_indirizzo");
            if (!indirizzoSelect || !indirizzoSelect.options.length) return;

            const emptyOption = indirizzoSelect.options[0];
            if (!emptyOption) return;

            if (!indirizzoSelect.dataset.defaultEmptyLabel) {
                indirizzoSelect.dataset.defaultEmptyLabel = emptyOption.textContent;
            }

            const selectedFamily = getSelectedFamigliaOption();
            const familyAddress = selectedFamily ? selectedFamily.dataset.indirizzoFamiglia || "" : "";

            emptyOption.textContent = familyAddress || indirizzoSelect.dataset.defaultEmptyLabel;
        }

        function refreshAddressHelp() {
            const indirizzoSelect = document.getElementById("id_indirizzo");
            const help = document.getElementById("studente-address-help");
            if (!indirizzoSelect || !help) return;

            if (indirizzoSelect.value) {
                help.textContent = "Indirizzo specifico";
                return;
            }

            const famigliaSelect = document.getElementById("id_famiglia");
            if (famigliaSelect) {
                const selectedOption = famigliaSelect.options[famigliaSelect.selectedIndex];
                const familyAddress = selectedOption ? selectedOption.dataset.indirizzoFamiglia : "";
                if (familyAddress) {
                    help.textContent = `Usa indirizzo famiglia: ${familyAddress}`;
                    return;
                }
            }

            const node = document.getElementById("studente-famiglia-indirizzo-label");
            let label = "";

            if (node) {
                try {
                    label = JSON.parse(node.textContent);
                } catch (e) {}
            }

            help.textContent = label
                ? `Usa indirizzo famiglia: ${label}`
                : "Se lasci vuoto, verra usato l'indirizzo principale della famiglia";
        }

        function updateMainButtons() {
            const famigliaSelect = document.getElementById("id_famiglia");
            const indirizzoSelect = document.getElementById("id_indirizzo");

            const editFamigliaBtn = document.getElementById("edit-famiglia-btn");
            const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
            const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");

            if (editFamigliaBtn && famigliaSelect) editFamigliaBtn.disabled = !famigliaSelect.value;
            if (editIndirizzoBtn && indirizzoSelect) editIndirizzoBtn.disabled = !indirizzoSelect.value;
            if (deleteIndirizzoBtn && indirizzoSelect) deleteIndirizzoBtn.disabled = !indirizzoSelect.value;
        }

        function syncFamigliaDefaults() {
            const cognomeInput = document.getElementById("id_cognome");
            const indirizzoSelect = document.getElementById("id_indirizzo");
            const selectedOption = getSelectedFamigliaOption();
            if (!selectedOption || !selectedOption.value) {
                updateInheritedAddressPlaceholder();
                return;
            }

            if (cognomeInput) {
                cognomeInput.value = selectedOption.dataset.cognomeFamiglia || "";
            }

            if (indirizzoSelect) {
                indirizzoSelect.value = "";
            }

            updateInheritedAddressPlaceholder();
            refreshAddressHelp();
            updateMainButtons();
        }

        function getRelatedConfig(relatedType, selectedId, targetInputName) {
            const suffix = targetInputName ? `&target_input_name=${encodeURIComponent(targetInputName)}` : "";

            if (relatedType === "anno_scolastico") {
                return {
                    addUrl: `/scuola/anni-scolastici/nuovo/?popup=1${suffix}`,
                    editUrl: selectedId ? `/scuola/anni-scolastici/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/scuola/anni-scolastici/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            if (relatedType === "classe") {
                return {
                    addUrl: `/scuola/classi/nuova/?popup=1${suffix}`,
                    editUrl: selectedId ? `/scuola/classi/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/scuola/classi/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            if (relatedType === "stato_iscrizione") {
                return {
                    addUrl: `/economia/stati-iscrizione/nuovo/?popup=1${suffix}`,
                    editUrl: selectedId ? `/economia/stati-iscrizione/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/economia/stati-iscrizione/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            if (relatedType === "condizione_iscrizione") {
                return {
                    addUrl: `/economia/condizioni-iscrizione/nuova/?popup=1${suffix}`,
                    editUrl: selectedId ? `/economia/condizioni-iscrizione/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/economia/condizioni-iscrizione/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            if (relatedType === "agevolazione") {
                return {
                    addUrl: `/economia/agevolazioni/nuova/?popup=1${suffix}`,
                    editUrl: selectedId ? `/economia/agevolazioni/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/economia/agevolazioni/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            if (relatedType === "tipo_documento") {
                return {
                    addUrl: `${config.urls.creaTipoDocumento}?popup=1${suffix}`,
                    editUrl: selectedId ? `/tipi-documento/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/tipi-documento/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            return null;
        }

        function wireInlineRelatedButtons(container) {
            const rows = container.querySelectorAll(".inline-related-field");

            rows.forEach(fieldWrapper => {
                if (fieldWrapper.dataset.relatedBound === "1") return;
                fieldWrapper.dataset.relatedBound = "1";

                const select = fieldWrapper.querySelector("select");
                const addBtn = fieldWrapper.querySelector(".inline-related-add");
                const editBtn = fieldWrapper.querySelector(".inline-related-edit");
                const deleteBtn = fieldWrapper.querySelector(".inline-related-delete");

                if (!select || !addBtn || !editBtn || !deleteBtn) return;

                const relatedType = addBtn.dataset.relatedType;
                const targetInputName = select.name;

                function refreshButtons() {
                    const selectedId = select.value;
                    editBtn.disabled = !selectedId;
                    deleteBtn.disabled = !selectedId;
                }

                addBtn.onclick = function () {
                    const cfg = getRelatedConfig(relatedType, null, targetInputName);
                    if (cfg && cfg.addUrl) relatedPopups.openRelatedPopup(cfg.addUrl);
                };

                editBtn.onclick = function () {
                    const cfg = getRelatedConfig(relatedType, select.value, targetInputName);
                    if (cfg && cfg.editUrl) relatedPopups.openRelatedPopup(cfg.editUrl);
                };

                deleteBtn.onclick = function () {
                    const cfg = getRelatedConfig(relatedType, select.value, targetInputName);
                    if (cfg && cfg.deleteUrl) relatedPopups.openRelatedPopup(cfg.deleteUrl);
                };

                select.addEventListener("change", refreshButtons);
                refreshButtons();
            });
        }

        function countPersistedRows(tableId) {
            const rows = document.querySelectorAll(`#${tableId} tbody .inline-form-row`);
            let count = 0;

            rows.forEach(row => {
                if (row.classList.contains("inline-empty-row")) {
                    return;
                }
                const deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
                if (deleteCheckbox && deleteCheckbox.checked) {
                    return;
                }
                const hiddenIdInput = row.querySelector('input[type="hidden"][name$="-id"]');
                if (hiddenIdInput && hiddenIdInput.value) {
                    count += 1;
                }
            });

            return count;
        }

        function refreshTabCounts() {
            const iscrizioniRows = countPersistedRows("iscrizioni-table");
            const tabIscrizioni = document.querySelector('[data-tab-target="tab-iscrizioni"]');
            const documentiRows = countPersistedRows("documenti-table");
            const tabDocumenti = document.querySelector('[data-tab-target="tab-documenti"]');
            if (tabIscrizioni) tabIscrizioni.textContent = `Iscrizioni (${iscrizioniRows})`;
            if (tabDocumenti) tabDocumenti.textContent = `Documenti (${documentiRows})`;
        }

        function getRateRecalcDialog() {
            let overlay = document.getElementById("rate-recalc-dialog-overlay");

            if (!overlay) {
                overlay = document.createElement("div");
                overlay.id = "rate-recalc-dialog-overlay";
                overlay.className = "app-dialog-overlay is-hidden";
                overlay.innerHTML = `
                    <div class="app-dialog" role="dialog" aria-modal="true" aria-labelledby="rate-recalc-dialog-title">
                        <div class="app-dialog-header">
                            <h2 class="app-dialog-title" id="rate-recalc-dialog-title">Conferma ricalcolo rate</h2>
                        </div>
                        <div class="app-dialog-body">
                            <p class="app-dialog-message">
                                Le rate senza pagamenti o movimenti potranno essere rigenerate.
                            </p>
                            <label class="app-dialog-field-label" for="rate-recalc-dialog-input">
                                Per confermare, digita <strong>RICALCOLA</strong>
                            </label>
                            <input
                                type="text"
                                id="rate-recalc-dialog-input"
                                class="app-dialog-input"
                                autocomplete="off"
                                spellcheck="false"
                            >
                        </div>
                        <div class="app-dialog-actions">
                            <button type="button" class="btn btn-secondary" data-rate-dialog-cancel="1">Annulla</button>
                            <button type="button" class="btn btn-rate-recalc" data-rate-dialog-confirm="1" disabled>Ricalcola rate</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(overlay);
            }

            const input = overlay.querySelector("#rate-recalc-dialog-input");
            const confirmButton = overlay.querySelector('[data-rate-dialog-confirm="1"]');
            const cancelButton = overlay.querySelector('[data-rate-dialog-cancel="1"]');
            let resolver = null;

            function syncConfirmState() {
                confirmButton.disabled = (input.value || "").trim().toUpperCase() !== "RICALCOLA";
            }

            function closeDialog(confirmed) {
                if (!resolver) {
                    return;
                }

                overlay.classList.add("is-hidden");
                document.body.classList.remove("app-dialog-open");
                input.value = "";
                syncConfirmState();

                const resolve = resolver;
                resolver = null;
                resolve(Boolean(confirmed));
            }

            if (!overlay.dataset.boundRateDialog) {
                overlay.dataset.boundRateDialog = "1";

                input.addEventListener("input", syncConfirmState);
                input.addEventListener("keydown", function (event) {
                    if (event.key === "Enter" && !confirmButton.disabled) {
                        event.preventDefault();
                        closeDialog(true);
                    }
                });

                cancelButton.addEventListener("click", function () {
                    closeDialog(false);
                });

                confirmButton.addEventListener("click", function () {
                    if (confirmButton.disabled) {
                        return;
                    }
                    closeDialog(true);
                });

                overlay.addEventListener("click", function (event) {
                    if (event.target === overlay) {
                        closeDialog(false);
                    }
                });

                document.addEventListener("keydown", function (event) {
                    if (overlay.classList.contains("is-hidden")) {
                        return;
                    }

                    if (event.key === "Escape") {
                        event.preventDefault();
                        closeDialog(false);
                    }
                });
            }

            return {
                open: function () {
                    input.value = "";
                    syncConfirmState();
                    overlay.classList.remove("is-hidden");
                    document.body.classList.add("app-dialog-open");

                    return new Promise(resolve => {
                        resolver = resolve;
                        window.setTimeout(function () {
                            input.focus();
                            input.select();
                        }, 0);
                    });
                },
            };
        }

        function submitRateRecalc(button) {
            const actionUrl = button.dataset.actionUrl;
            if (!actionUrl) {
                return;
            }

            const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
            const csrfToken = csrfInput ? csrfInput.value : "";

            const form = document.createElement("form");
            form.method = "post";
            form.action = actionUrl;
            form.style.display = "none";

            if (csrfToken) {
                const csrfField = document.createElement("input");
                csrfField.type = "hidden";
                csrfField.name = "csrfmiddlewaretoken";
                csrfField.value = csrfToken;
                form.appendChild(csrfField);
            }

            const nextUrl = button.dataset.nextUrl;
            if (nextUrl) {
                const nextField = document.createElement("input");
                nextField.type = "hidden";
                nextField.name = "next";
                nextField.value = nextUrl;
                form.appendChild(nextField);
            }

            document.body.appendChild(form);
            form.submit();
        }

        function bindRateRecalcForms() {
            const rateRecalcDialog = getRateRecalcDialog();

            document.querySelectorAll('[data-rate-recalc-form="1"]').forEach(button => {
                if (button.dataset.boundRateRecalc === "1") {
                    return;
                }

                button.dataset.boundRateRecalc = "1";
                button.addEventListener("click", function () {
                    rateRecalcDialog.open().then(function (confirmed) {
                        if (!confirmed) {
                            return;
                        }

                        submitRateRecalc(button);
                    });
                });
            });
        }

        function bindRatePaymentPopups() {
            document.querySelectorAll('[data-rate-payment-popup="1"]').forEach(button => {
                if (button.dataset.boundRatePayment === "1") {
                    return;
                }

                button.dataset.boundRatePayment = "1";
                button.addEventListener("click", function () {
                    const popupUrl = button.dataset.popupUrl;
                    if (!popupUrl) {
                        return;
                    }

                    window.open(
                        popupUrl,
                        "arboris-rate-payment-popup",
                        "width=760,height=680,resizable=yes,scrollbars=yes"
                    );
                });
            });
        }

        function bindWithdrawalPopups() {
            document.querySelectorAll('[data-withdrawal-popup="1"]').forEach(button => {
                if (button.dataset.boundWithdrawalPopup === "1") {
                    return;
                }

                button.dataset.boundWithdrawalPopup = "1";
                button.addEventListener("click", function () {
                    const popupUrl = button.dataset.popupUrl;
                    if (!popupUrl) {
                        return;
                    }

                    window.open(
                        popupUrl,
                        "arboris-withdrawal-popup",
                        "width=760,height=720,resizable=yes,scrollbars=yes"
                    );
                });
            });
        }

        function removeInlineRow(button) {
            const row = button.closest("tr");
            if (row) {
                const detailsRow = row.nextElementSibling;
                if (detailsRow && detailsRow.classList.contains("inline-details-row")) {
                    detailsRow.remove();
                }

                const errorsRow = row.nextElementSibling;
                if (errorsRow && errorsRow.classList.contains("inline-errors-row")) {
                    errorsRow.remove();
                }

                row.remove();
                refreshTabCounts();
            }
        }

        function isRowPersisted(row) {
            const hiddenIdInput = row.querySelector('input[type="hidden"][name$="-id"]');
            return Boolean(hiddenIdInput && hiddenIdInput.value);
        }

        function rowHasVisibleErrors(row) {
            let nextRow = row.nextElementSibling;

            if (nextRow && nextRow.classList.contains("inline-details-row")) {
                nextRow = nextRow.nextElementSibling;
            }

            return Boolean(nextRow && nextRow.classList.contains("inline-errors-row"));
        }

        function rowHasUserData(row) {
            const fields = row.querySelectorAll("input, textarea, select");

            for (const field of fields) {
                const type = (field.type || "").toLowerCase();
                if (type === "hidden" || type === "checkbox") {
                    continue;
                }
                if ((field.value || "").trim() !== "") {
                    return true;
                }
            }

            return false;
        }

        function prepareExistingEmptyRows(tableId) {
            document.querySelectorAll(`#${tableId} tbody .inline-form-row`).forEach(row => {
                if (isRowPersisted(row) || rowHasVisibleErrors(row) || rowHasUserData(row)) {
                    return;
                }

                row.classList.add("inline-empty-row", "is-hidden");

                const detailsRow = row.nextElementSibling;
                if (detailsRow && detailsRow.classList.contains("inline-details-row")) {
                    detailsRow.classList.add("inline-empty-row", "is-hidden");
                }
            });
        }

        function setRowInputsEnabled(row, enabled) {
            if (!row) {
                return;
            }

            row.querySelectorAll("input, textarea, select").forEach(field => {
                if (field.type === "hidden") {
                    return;
                }

                if (enabled) {
                    field.disabled = false;
                    field.readOnly = false;
                    field.classList.remove("submit-safe-locked");
                    field.removeAttribute("aria-disabled");
                    field.removeAttribute("tabindex");
                } else {
                    field.disabled = true;
                    field.readOnly = true;
                }
            });
        }

        function syncDependentSelect(select, matcher) {
            if (!select) return;

            let hasSelectedVisibleOption = false;

            Array.from(select.options).forEach(option => {
                if (!option.value) {
                    option.hidden = false;
                    option.disabled = false;
                    return;
                }

                const isVisible = matcher(option);
                option.hidden = !isVisible;
                option.disabled = !isVisible;

                if (isVisible && option.selected) {
                    hasSelectedVisibleOption = true;
                }
            });

            if (select.value && !hasSelectedVisibleOption) {
                select.value = "";
            }
        }

        function wireIscrizioneRow(row) {
            if (!row || row.dataset.iscrizioneBound === "1") {
                return;
            }

            const annoSelect = row.querySelector('select[name$="-anno_scolastico"]');
            const classeSelect = row.querySelector('select[name$="-classe"]');
            const condizioneSelect = row.querySelector('select[name$="-condizione_iscrizione"]');
            const agevolazioneSelect = row.querySelector('select[name$="-agevolazione"]');
            const riduzioneCheckbox = row.querySelector('input[type="checkbox"][name$="-riduzione_speciale"]');
            const importoRiduzioneInput = row.querySelector('input[name$="-importo_riduzione_speciale"]');
            const dataFineInput = row.querySelector('input[name$="-data_fine_iscrizione"]');

            if (!annoSelect || !classeSelect || !condizioneSelect) {
                return;
            }

            row.dataset.iscrizioneBound = "1";

            function refreshDependentChoices() {
                const annoScolasticoId = annoSelect.value;

                syncDependentSelect(classeSelect, option => option.dataset.annoScolastico === annoScolasticoId);
                syncDependentSelect(condizioneSelect, option => option.dataset.annoScolastico === annoScolasticoId);
            }

            function syncDataFineIscrizione() {
                if (!annoSelect || !dataFineInput) {
                    return;
                }

                const selectedAnno = annoSelect.options[annoSelect.selectedIndex];
                const dataFineAnno = selectedAnno ? (selectedAnno.dataset.dataFine || "") : "";

                if (!dataFineAnno) {
                    return;
                }

                if (!dataFineInput.value || dataFineInput.dataset.autoManaged === "1") {
                    dataFineInput.value = dataFineAnno;
                    dataFineInput.dataset.autoManaged = "1";
                }
            }

            annoSelect.addEventListener("change", function () {
                refreshDependentChoices();
                syncDataFineIscrizione();
            });

            function syncRiduzioneSpecialeState() {
                if (!riduzioneCheckbox || !importoRiduzioneInput) {
                    return;
                }

                const selectedCondizione = condizioneSelect.options[condizioneSelect.selectedIndex];
                const riduzioniAmmesse = !selectedCondizione || selectedCondizione.dataset.riduzioneSpecialeAmmessa !== "0";
                const enabled = riduzioniAmmesse && riduzioneCheckbox.checked;
                const currencyGroup = importoRiduzioneInput.closest(".currency-input-group");
                const agevolazioneCell = row.querySelector(".iscrizione-agevolazione-cell");
                const riduzioneCell = row.querySelector(".iscrizione-riduzione-cell");
                const importoCell = row.querySelector(".iscrizione-importo-riduzione-cell");

                if (agevolazioneCell) agevolazioneCell.classList.toggle("is-hidden", !riduzioniAmmesse);
                if (riduzioneCell) riduzioneCell.classList.toggle("is-hidden", !riduzioniAmmesse);
                if (importoCell) importoCell.classList.toggle("is-hidden", !riduzioniAmmesse);

                if (!riduzioniAmmesse) {
                    if (agevolazioneSelect) {
                        agevolazioneSelect.value = "";
                    }
                    riduzioneCheckbox.checked = false;
                }

                importoRiduzioneInput.readOnly = !enabled;
                importoRiduzioneInput.disabled = !enabled;
                importoRiduzioneInput.classList.toggle("is-readonly", !enabled);
                if (currencyGroup) {
                    currencyGroup.classList.toggle("is-disabled", !enabled || !riduzioniAmmesse);
                }

                if (!enabled) {
                    importoRiduzioneInput.value = "0.00";
                }
            }

            if (riduzioneCheckbox && importoRiduzioneInput) {
                riduzioneCheckbox.addEventListener("change", syncRiduzioneSpecialeState);
            }

            condizioneSelect.addEventListener("change", syncRiduzioneSpecialeState);
            refreshDependentChoices();
            syncDataFineIscrizione();
            syncRiduzioneSpecialeState();
            collapsible.initCollapsibleSections(row.parentElement);
        }

        function addInlineForm(prefix) {
            if (window.studenteViewMode && !window.studenteViewMode.isEditing()) {
                window.studenteViewMode.setInlineEditing(true);
            }

            setInlineTarget(prefix);
            refreshInlineEditScope();
            updateInlineEditButtonLabel(`tab-${prefix}`);

            const hiddenRow = document.querySelector(`#${prefix}-table tbody .inline-form-row.inline-empty-row.is-hidden`);
            if (hiddenRow) {
                hiddenRow.classList.remove("is-hidden");
                hiddenRow.classList.remove("inline-empty-row");
                setRowInputsEnabled(hiddenRow, true);

                const detailsRow = hiddenRow.nextElementSibling;
                if (detailsRow && detailsRow.classList.contains("inline-details-row")) {
                    detailsRow.classList.remove("is-hidden");
                    detailsRow.classList.remove("inline-empty-row");
                    setRowInputsEnabled(detailsRow, true);
                }

                wireInlineRelatedButtons(hiddenRow);
                if (prefix === "iscrizioni") {
                    wireIscrizioneRow(hiddenRow);
                }

                const firstInput = hiddenRow.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea");
                if (firstInput) firstInput.focus();

                tabs.activateTab(`tab-${prefix}`, getStudenteTabStorageKey());
                refreshInlineEditScope();
                refreshTabCounts();
                return;
            }

            const totalForms = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
            const currentIndex = parseInt(totalForms.value, 10);

            const template = document.getElementById(`${prefix}-empty-form-template`).innerHTML;
            const newRowHtml = template.replace(/__prefix__/g, currentIndex);

            const tbody = document.querySelector(`#${prefix}-table tbody`);
            tbody.insertAdjacentHTML("beforeend", newRowHtml);

            totalForms.value = currentIndex + 1;

            const newRow = tbody.lastElementChild;
            if (newRow) {
                const mainRow = newRow.classList.contains("inline-details-row")
                    ? newRow.previousElementSibling
                    : newRow;
                const detailsRow = mainRow ? mainRow.nextElementSibling : null;

                setRowInputsEnabled(mainRow, true);
                if (detailsRow && detailsRow.classList.contains("inline-details-row")) {
                    setRowInputsEnabled(detailsRow, true);
                }

                wireInlineRelatedButtons(mainRow);
                if (prefix === "iscrizioni") {
                    wireIscrizioneRow(mainRow);
                }

                const firstInput = mainRow.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea");
                if (firstInput) firstInput.focus();
            }

            tabs.activateTab(`tab-${prefix}`, getStudenteTabStorageKey());
            refreshInlineEditScope();
            refreshTabCounts();
        }

        window.removeInlineRow = removeInlineRow;
        window.addInlineForm = addInlineForm;

        const famigliaSelect = document.getElementById("id_famiglia");
        const indirizzoSelect = document.getElementById("id_indirizzo");

        const addFamigliaBtn = document.getElementById("add-famiglia-btn");
        const editFamigliaBtn = document.getElementById("edit-famiglia-btn");

        const addIndirizzoBtn = document.getElementById("add-indirizzo-btn");
        const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
        const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");

        if (addFamigliaBtn && famigliaSelect) {
            addFamigliaBtn.addEventListener("click", function () {
                window.location.href = config.urls.creaFamiglia;
            });
        }

        if (editFamigliaBtn && famigliaSelect) {
            editFamigliaBtn.addEventListener("click", function () {
                if (famigliaSelect.value) {
                    window.location.href = `/famiglie/${famigliaSelect.value}/modifica/`;
                }
            });
        }

        if (addIndirizzoBtn && indirizzoSelect) {
            addIndirizzoBtn.addEventListener("click", function () {
                relatedPopups.openRelatedPopup(`${config.urls.creaIndirizzo}?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
            });
        }

        if (editIndirizzoBtn && indirizzoSelect) {
            editIndirizzoBtn.addEventListener("click", function () {
                if (indirizzoSelect.value) {
                    relatedPopups.openRelatedPopup(`/indirizzi/${indirizzoSelect.value}/modifica/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
                }
            });
        }

        if (deleteIndirizzoBtn && indirizzoSelect) {
            deleteIndirizzoBtn.addEventListener("click", function () {
                if (indirizzoSelect.value) {
                    relatedPopups.openRelatedPopup(`/indirizzi/${indirizzoSelect.value}/elimina/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
                }
            });
        }

        if (famigliaSelect) {
            famigliaSelect.addEventListener("change", function () {
                syncFamigliaDefaults();
                updateMainButtons();
                refreshAddressHelp();
            });
        }

        if (indirizzoSelect) {
            indirizzoSelect.addEventListener("change", function () {
                updateMainButtons();
                refreshAddressHelp();
            });
        }

        prepareExistingEmptyRows("iscrizioni-table");
        prepareExistingEmptyRows("documenti-table");
        document.querySelectorAll("#iscrizioni-table tbody .inline-form-row").forEach(wireIscrizioneRow);
        const inlineLockRoot = studenteInlineRoot();
        if (inlineLockRoot) {
            tabs.bindTabButtons(getStudenteTabStorageKey(), inlineLockRoot);
        }
        document.querySelectorAll("#studente-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
            btn.addEventListener("arboris:before-tab-activate", function (event) {
                if (btn.classList.contains("is-tab-locked")) {
                    event.preventDefault();
                }
            });

            btn.addEventListener("click", function () {
                const isInlineEditing = Boolean(
                    window.studenteViewMode &&
                    typeof window.studenteViewMode.isInlineEditing === "function" &&
                    window.studenteViewMode.isInlineEditing()
                );

                if (!isInlineEditing) {
                    setInlineTarget(btn.dataset.tabTarget);
                    updateInlineEditButtonLabel(btn.dataset.tabTarget);
                }

                refreshInlineEditScope();
            });
        });
        collapsible.initCollapsibleSections(document);
        wireInlineRelatedButtons(document);
        tabs.restoreActiveTab(getStudenteTabStorageKey());
        const activeTab = inlineLockRoot ? inlineLockRoot.querySelector(".tab-btn.is-active") : null;
        if (activeTab && activeTab.dataset.tabTarget) {
            setInlineTarget(activeTab.dataset.tabTarget);
            updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
        }
        refreshInlineEditScope();
        updateInheritedAddressPlaceholder();
        updateMainButtons();
        refreshAddressHelp();
        refreshTabCounts();
        bindRateRecalcForms();
        bindRatePaymentPopups();
        bindWithdrawalPopups();
        bindStandaloneSexFromNome();
    }

    return {
        init,
        refreshInlineEditScope: function () {
            refreshInlineEditScopeHandler();
        },
    };
})();
