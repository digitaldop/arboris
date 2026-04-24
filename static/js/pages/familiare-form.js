window.ArborisFamiliareForm = (function () {
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

        function getFamiliareTabStorageKey() {
            return `arboris-familiare-form-active-tab-${config.familiareId || "new"}`;
        }

        function activatePanelIfPresent(tabId) {
            const panel = document.getElementById(tabId);
            if (!panel) {
                return;
            }

            if (document.querySelector(`[data-tab-target="${tabId}"]`)) {
                tabs.activateTab(tabId, getFamiliareTabStorageKey());
                return;
            }

            document.querySelectorAll(".tab-panel").forEach(existingPanel => existingPanel.classList.remove("is-active"));
            panel.classList.add("is-active");
        }

        function refreshAddressHelp() {
            const indirizzoSelect = document.getElementById("id_indirizzo");
            const help = document.getElementById("familiare-address-help");
            if (!indirizzoSelect || !help) return;

            if (indirizzoSelect.value) {
                help.textContent = "Indirizzo specifico";
                return;
            }

            const node = document.getElementById("familiare-famiglia-indirizzo-label");
            let label = "";

            if (node) {
                try {
                    label = JSON.parse(node.textContent);
                } catch (e) {}
            }

            if (label) {
                help.textContent = `Ereditera: ${label}`;
            } else {
                help.textContent = "Se lasci vuoto, verra usato l'indirizzo principale della famiglia";
            }
        }

        function getSelectedFamigliaOption() {
            const famigliaSelect = document.getElementById("id_famiglia");
            if (!famigliaSelect) {
                return null;
            }

            return famigliaSelect.options[famigliaSelect.selectedIndex] || null;
        }

        function normalizeRelationLabel(value) {
            return (value || "")
                .toString()
                .trim()
                .toLowerCase()
                .normalize("NFD")
                .replace(/[\u0300-\u036f]/g, "");
        }

        function inferSexFromRelationLabel(value) {
            const label = normalizeRelationLabel(value);
            if (!label) {
                return "";
            }

            const maleTokens = [
                "padre",
                "nonno",
                "zio",
                "fratello",
                "marito",
                "compagno",
                "figlio",
                "patrigno",
                "suocero",
                "bisnonno",
                "cognato",
                "tutore",
            ];
            const femaleTokens = [
                "madre",
                "nonna",
                "zia",
                "sorella",
                "moglie",
                "compagna",
                "figlia",
                "matrigna",
                "suocera",
                "bisnonna",
                "cognata",
                "tutrice",
            ];

            if (maleTokens.some(token => label.includes(token))) {
                return "M";
            }
            if (femaleTokens.some(token => label.includes(token))) {
                return "F";
            }

            return "";
        }

        function syncSexFromRelazioneFamiliare() {
            const relazioneSelect = document.getElementById("id_relazione_familiare");
            const sessoSelect = document.getElementById("id_sesso");

            if (!relazioneSelect || !sessoSelect) {
                return;
            }

            const selectedOption = relazioneSelect.options[relazioneSelect.selectedIndex];
            const inferredSex = inferSexFromRelationLabel(selectedOption ? selectedOption.textContent : "");

            if (!inferredSex || sessoSelect.value === inferredSex) {
                return;
            }

            sessoSelect.value = inferredSex;
            sessoSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }

        function syncInheritedAddressFromFamiglia() {
            const indirizzoSelect = document.getElementById("id_indirizzo");
            const selectedFamiglia = getSelectedFamigliaOption();

            if (!indirizzoSelect) {
                return;
            }

            if (!selectedFamiglia || !selectedFamiglia.value) {
                refreshAddressHelp();
                return;
            }

            const familyAddressId = selectedFamiglia.dataset.indirizzoFamigliaId || "";
            indirizzoSelect.value = familyAddressId || "";

            refreshAddressHelp();
            updateMainButtons();
        }

        function updateMainButtons() {
            const famigliaSelect = document.getElementById("id_famiglia");
            const relazioneSelect = document.getElementById("id_relazione_familiare");
            const indirizzoSelect = document.getElementById("id_indirizzo");

            const editFamigliaBtn = document.getElementById("edit-famiglia-btn");
            const editRelazioneBtn = document.getElementById("edit-relazione-btn");
            const deleteRelazioneBtn = document.getElementById("delete-relazione-btn");
            const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
            const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");

            if (editFamigliaBtn && famigliaSelect) editFamigliaBtn.disabled = !famigliaSelect.value;
            if (editRelazioneBtn && relazioneSelect) editRelazioneBtn.disabled = !relazioneSelect.value;
            if (deleteRelazioneBtn && relazioneSelect) deleteRelazioneBtn.disabled = !relazioneSelect.value;
            if (editIndirizzoBtn && indirizzoSelect) editIndirizzoBtn.disabled = !indirizzoSelect.value;
            if (deleteIndirizzoBtn && indirizzoSelect) deleteIndirizzoBtn.disabled = !indirizzoSelect.value;
        }

        function getRelatedConfig(relatedType, selectedId, targetInputName) {
            const suffix = targetInputName ? `&target_input_name=${encodeURIComponent(targetInputName)}` : "";

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
            const documentiRows = countPersistedRows("documenti-table");
            const tabDocumenti = document.querySelector('[data-tab-target="tab-documenti"]');
            if (tabDocumenti) tabDocumenti.textContent = `Documenti (${documentiRows})`;
        }

        function removeInlineRow(button) {
            const row = button.closest("tr");
            if (row) {
                row.remove();
                refreshTabCounts();
            }
        }

        function isRowPersisted(row) {
            const hiddenIdInput = row.querySelector('input[type="hidden"][name$="-id"]');
            return Boolean(hiddenIdInput && hiddenIdInput.value);
        }

        function rowHasVisibleErrors(row) {
            return row.nextElementSibling && row.nextElementSibling.classList.contains("inline-errors-row");
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
            });
        }

        function addInlineForm(prefix) {
            if (window.familiareViewMode && !window.familiareViewMode.isEditing()) {
                window.familiareViewMode.setInlineEditing(true);
            }

            const hiddenRow = document.querySelector(`#${prefix}-table tbody .inline-form-row.inline-empty-row.is-hidden`);
            if (hiddenRow) {
                hiddenRow.classList.remove("is-hidden");
                hiddenRow.classList.remove("inline-empty-row");

                wireInlineRelatedButtons(hiddenRow);

                const firstInput = hiddenRow.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea");
                if (firstInput) firstInput.focus();

                activatePanelIfPresent(`tab-${prefix}`);
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
                wireInlineRelatedButtons(newRow);

                const firstInput = newRow.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea");
                if (firstInput) firstInput.focus();
            }

            activatePanelIfPresent(`tab-${prefix}`);
            refreshTabCounts();
        }

        function bindFigliQuickActions() {
            document.querySelectorAll("[data-popup-url]").forEach(button => {
                if (button.dataset.popupBound === "1") {
                    return;
                }

                button.dataset.popupBound = "1";
                button.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    relatedPopups.openRelatedPopup(button.dataset.popupUrl);
                });
            });
        }

        window.removeInlineRow = removeInlineRow;
        window.addInlineForm = addInlineForm;

        const famigliaSelect = document.getElementById("id_famiglia");
        const relazioneSelect = document.getElementById("id_relazione_familiare");
        const indirizzoSelect = document.getElementById("id_indirizzo");

        const addFamigliaBtn = document.getElementById("add-famiglia-btn");
        const editFamigliaBtn = document.getElementById("edit-famiglia-btn");
        const addRelazioneBtn = document.getElementById("add-relazione-btn");
        const editRelazioneBtn = document.getElementById("edit-relazione-btn");
        const deleteRelazioneBtn = document.getElementById("delete-relazione-btn");
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

        if (addRelazioneBtn && relazioneSelect) {
            addRelazioneBtn.addEventListener("click", function () {
                relatedPopups.openRelatedPopup(`${config.urls.creaRelazioneFamiliare}?popup=1&target_input_name=${encodeURIComponent(relazioneSelect.name)}`);
            });
        }

        if (editRelazioneBtn && relazioneSelect) {
            editRelazioneBtn.addEventListener("click", function () {
                if (relazioneSelect.value) {
                    relatedPopups.openRelatedPopup(`/relazioni-familiari/${relazioneSelect.value}/modifica/?popup=1&target_input_name=${encodeURIComponent(relazioneSelect.name)}`);
                }
            });
        }

        if (deleteRelazioneBtn && relazioneSelect) {
            deleteRelazioneBtn.addEventListener("click", function () {
                if (relazioneSelect.value) {
                    relatedPopups.openRelatedPopup(`/relazioni-familiari/${relazioneSelect.value}/elimina/?popup=1&target_input_name=${encodeURIComponent(relazioneSelect.name)}`);
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
                syncInheritedAddressFromFamiglia();
                updateMainButtons();
                refreshAddressHelp();
            });
        }

        if (relazioneSelect) {
            relazioneSelect.addEventListener("change", function () {
                syncSexFromRelazioneFamiliare();
                updateMainButtons();
            });
        }

        if (indirizzoSelect) {
            indirizzoSelect.addEventListener("change", function () {
                updateMainButtons();
                refreshAddressHelp();
            });
        }

        prepareExistingEmptyRows("documenti-table");
        tabs.bindTabButtons(getFamiliareTabStorageKey());
        collapsible.initCollapsibleSections(document);
        wireInlineRelatedButtons(document);
        bindFigliQuickActions();
        tabs.restoreActiveTab(getFamiliareTabStorageKey());
        syncInheritedAddressFromFamiglia();
        syncSexFromRelazioneFamiliare();
        updateMainButtons();
        refreshAddressHelp();
        refreshTabCounts();
    }

    return {
        init,
    };
})();
