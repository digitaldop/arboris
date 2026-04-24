window.ArborisFamigliaForm = (function () {
    let refreshInlineEditScopeHandler = function () {};
    let refreshLockedTabsHandler = function () {};

    function init(config) {
        const relatedPopups = window.ArborisRelatedPopups;
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;

        if (!relatedPopups || !collapsible || !tabs) {
            console.error("Arboris core JS non caricato correttamente.");
            return;
        }

        const openRelatedPopup = relatedPopups.openRelatedPopup;
        const dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        const dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        window.dismissRelatedPopup = dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = dismissDeletedRelatedPopup;

        // Funzione per gestire la persistenza della tab attiva
        function getFamigliaTabStorageKey() {
            return `arboris-famiglia-form-active-tab-${config.famigliaId || "new"}`;
        }

        const famigliaInlineRoot = () => document.getElementById("famiglia-inline-lock-container");
        const defaultInlineTab = config.defaultInlineTab || "familiari";

        function normalizeTabId(tabId) {
            if (!tabId) {
                return "";
            }

            return tabId.startsWith("tab-") ? tabId : `tab-${tabId}`;
        }

        function syncActiveTabUrl(tabId) {
            const normalizedTab = normalizeTabId(tabId).replace(/^tab-/, "");
            if (!normalizedTab) {
                return;
            }

            const url = new URL(window.location.href);

            if (normalizedTab === defaultInlineTab) {
                url.searchParams.delete("tab");
            } else {
                url.searchParams.set("tab", normalizedTab);
            }

            const nextUrl = `${url.pathname}${url.search}${url.hash}`;
            const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;

            if (nextUrl !== currentUrl) {
                window.history.replaceState({}, "", nextUrl);
            }
        }

        function setInlineTarget(tabId) {
            const input = document.getElementById("famiglia-inline-target");
            if (!input || !tabId) {
                return;
            }

            input.value = tabId.replace(/^tab-/, "");
        }

        function tabTitleForInlineEditLabel(tabButton) {
            if (!tabButton) {
                return "";
            }

            const baseLabel = (tabButton.dataset.tabBaseLabel || "").trim();
            if (baseLabel) {
                return baseLabel;
            }

            return tabButton.textContent.replace(/\s*\([^)]*\)\s*$/, "").replace(/\s+/g, " ").trim();
        }

        function refreshInlineEditScope() {
            const form = document.getElementById("famiglia-detail-form");
            const panels = document.querySelectorAll('#famiglia-inline-lock-container .tab-panel[data-inline-scope]');
            const targetInput = document.getElementById("famiglia-inline-target");
            const target = targetInput ? targetInput.value : "";
            const isEditing = Boolean(
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.isEditing === "function" &&
                window.famigliaViewMode.isEditing()
            );
            const isInlineEditing = Boolean(
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.isInlineEditing === "function" &&
                window.famigliaViewMode.isInlineEditing()
            );

            if (form) {
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
                const root = famigliaInlineRoot();
                const activeTab = root ? root.querySelector(".tab-btn.is-active") : null;
                if (activeTab && activeTab.dataset.tabTarget) {
                    updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
                }
            }
        }

        refreshInlineEditScopeHandler = refreshInlineEditScope;

        function updateInlineEditButtonLabel(tabId) {
            const button = document.getElementById("enable-inline-edit-famiglia-btn");
            if (!button) {
                return;
            }
            if (
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.isInlineEditing === "function" &&
                window.famigliaViewMode.isInlineEditing()
            ) {
                return;
            }

            const root = famigliaInlineRoot();
            const tabBtn = root && tabId ? root.querySelector(`.tab-btn[data-tab-target="${tabId}"]`) : null;
            const tabTitle = tabTitleForInlineEditLabel(tabBtn);

            button.textContent = tabTitle ? `Modifica ${tabTitle}` : "Modifica";
        }

        function refreshLockedTabs() {
            const input = document.getElementById("famiglia-inline-target");
            const target = input ? input.value : "";
            const isInlineEditing = Boolean(
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.isInlineEditing === "function" &&
                window.famigliaViewMode.isInlineEditing()
            );
            const lockMessage = "Non è possibile cambiare tab finché non si salvano o annullano le modifiche correnti.";

            document.querySelectorAll("#famiglia-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
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

        refreshLockedTabsHandler = refreshLockedTabs;

        function activateTab(tabId) {
            setInlineTarget(tabId);
            updateInlineEditButtonLabel(tabId);
            tabs.activateTab(tabId, getFamigliaTabStorageKey());
            syncActiveTabUrl(tabId);
            refreshInlineEditScope();
        }

        function restoreActiveTab() {
            const requestedTabId = config.preferInitialActiveTab
                ? normalizeTabId(config.initialActiveTab || defaultInlineTab)
                : "";
            const requestedPanel = requestedTabId ? document.getElementById(requestedTabId) : null;

            if (requestedPanel) {
                activateTab(requestedTabId);
                return;
            }

            tabs.restoreActiveTab(getFamigliaTabStorageKey());
            const root = famigliaInlineRoot();
            const activeTab = root ? root.querySelector(".tab-btn.is-active") : null;
            if (activeTab && activeTab.dataset.tabTarget) {
                setInlineTarget(activeTab.dataset.tabTarget);
                updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
                syncActiveTabUrl(activeTab.dataset.tabTarget);
            }
            refreshInlineEditScope();
        }

        function syncNotesSectionState() {
            const notesSection = document.getElementById("family-notes-section");
            const notesPanel = document.getElementById("section-note");

            if (!notesSection || !notesPanel) {
                return;
            }

            notesSection.classList.toggle("is-expanded", notesPanel.classList.contains("is-open"));
        }

        function bindNotesSectionState() {
            const notesToggle = document.querySelector('#family-notes-section [data-target="section-note"]');
            if (!notesToggle || notesToggle.dataset.notesLayoutBound === "1") {
                syncNotesSectionState();
                return;
            }

            notesToggle.dataset.notesLayoutBound = "1";
            notesToggle.addEventListener("click", function () {
                window.requestAnimationFrame(syncNotesSectionState);
            });

            syncNotesSectionState();
        }

        function getFamigliaIndirizzoPrincipaleLabel() {
            const select = document.getElementById("id_indirizzo_principale");

            if (select && select.value) {
                const selectedOption = select.options[select.selectedIndex];
                if (selectedOption) {
                    return selectedOption.textContent.trim();
                }
            }

            const node = document.getElementById("famiglia-indirizzo-principale-label");
            if (!node) return "";

            try {
                return JSON.parse(node.textContent);
            } catch (e) {
                return "";
            }
        }

        function refreshInlineAddressHelp(select) {
            const wrapperCell = select.closest("td");
            if (!wrapperCell) return;

            const help = wrapperCell.querySelector('[data-role="address-help"]');
            if (!help) return;

            const famigliaIndirizzoLabel = getFamigliaIndirizzoPrincipaleLabel();

            if (select.value) {
                help.textContent = "Indirizzo specifico";
            } else if (famigliaIndirizzoLabel) {
                help.textContent = `Erediterà: ${famigliaIndirizzoLabel}`;
            } else {
                help.textContent = "Se lasci vuoto, verrà usato l'indirizzo principale della famiglia";
            }
        }

        function refreshAllInlineAddressHelp() {
            const selects = document.querySelectorAll('select[name$="-indirizzo"]');
            selects.forEach(select => refreshInlineAddressHelp(select));
        }

        function initSearchableSelects(root) {
            if (window.ArborisFamigliaAutocomplete && typeof window.ArborisFamigliaAutocomplete.init === "function") {
                window.ArborisFamigliaAutocomplete.init(root || document);
            }
            if (window.ArborisFamigliaAutocomplete && typeof window.ArborisFamigliaAutocomplete.refresh === "function") {
                window.ArborisFamigliaAutocomplete.refresh(root || document);
            }
        }

        function syncFamiliareInlineAddresses() {
            const famigliaIndirizzoId = document.getElementById("id_indirizzo_principale")?.value || "";
            const rows = document.querySelectorAll("#familiari-table tbody .inline-form-row");

            rows.forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }

                const hiddenIdInput = row.querySelector('input[type="hidden"][name$="-id"]');
                const indirizzoSelect = row.querySelector('select[name$="-indirizzo"]');

                if (!indirizzoSelect) {
                    return;
                }

                const isPersisted = Boolean(hiddenIdInput && hiddenIdInput.value);
                if (isPersisted) {
                    refreshInlineAddressHelp(indirizzoSelect);
                    return;
                }

                indirizzoSelect.value = famigliaIndirizzoId || "";
                refreshInlineAddressHelp(indirizzoSelect);
            });
        }

        function getFamigliaCognome() {
            return document.getElementById("id_cognome_famiglia")?.value?.trim() || "";
        }

        function syncStudenteInlineDefaults() {
            const famigliaIndirizzoId = document.getElementById("id_indirizzo_principale")?.value || "";
            const famigliaCognome = getFamigliaCognome();
            const rows = document.querySelectorAll("#studenti-table tbody .inline-form-row");

            rows.forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }

                const hiddenIdInput = row.querySelector('input[type="hidden"][name$="-id"]');
                const cognomeInput = row.querySelector('input[name$="-cognome"]');
                const indirizzoSelect = row.querySelector('select[name$="-indirizzo"]');
                const attivoCheckbox = row.querySelector('input[type="checkbox"][name$="-attivo"]');
                const isPersisted = Boolean(hiddenIdInput && hiddenIdInput.value);

                if (isPersisted) {
                    if (indirizzoSelect) {
                        refreshInlineAddressHelp(indirizzoSelect);
                    }
                    return;
                }

                if (cognomeInput) {
                    cognomeInput.value = famigliaCognome;
                }

                if (indirizzoSelect) {
                    indirizzoSelect.value = famigliaIndirizzoId || "";
                    refreshInlineAddressHelp(indirizzoSelect);
                }

                if (attivoCheckbox) {
                    attivoCheckbox.checked = true;
                }
            });
        }

        function getRelatedConfig(relatedType, selectedId, targetInputName) {
            const suffix = targetInputName ? `&target_input_name=${encodeURIComponent(targetInputName)}` : "";

            if (relatedType === "relazione_familiare") {
                return {
                    addUrl: `${config.urls.creaRelazioneFamiliare}?popup=1${suffix}`,
                    editUrl: selectedId ? `/relazioni-familiari/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/relazioni-familiari/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            if (relatedType === "tipo_documento") {
                return {
                    addUrl: `${config.urls.creaTipoDocumento}?popup=1${suffix}`,
                    editUrl: selectedId ? `/tipi-documento/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/tipi-documento/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            if (relatedType === "indirizzo") {
                return {
                    addUrl: `${config.urls.creaIndirizzo}?popup=1${suffix}`,
                    editUrl: selectedId ? `/indirizzi/${selectedId}/modifica/?popup=1${suffix}` : null,
                    deleteUrl: selectedId ? `/indirizzi/${selectedId}/elimina/?popup=1${suffix}` : null,
                };
            }

            return null;
        }

        function wireInlineRelatedButtons(container) {
            const rows = container.querySelectorAll(".inline-related-field");

            rows.forEach(fieldWrapper => {
                if (fieldWrapper.dataset.relatedBound === "1") {
                    return;
                }

                fieldWrapper.dataset.relatedBound = "1";

                const select = fieldWrapper.querySelector("select");
                const addBtn = fieldWrapper.querySelector(".inline-related-add");
                const editBtn = fieldWrapper.querySelector(".inline-related-edit");
                const deleteBtn = fieldWrapper.querySelector(".inline-related-delete");

                if (!select || !addBtn || !editBtn || !deleteBtn) {
                    return;
                }

                const relatedType = addBtn.dataset.relatedType;
                const targetInputName = select.name;

                function refreshButtons() {
                    const selectedId = select.value;
                    editBtn.disabled = !selectedId;
                    deleteBtn.disabled = !selectedId;

                    if (relatedType === "indirizzo") {
                        refreshInlineAddressHelp(select);
                    }
                }

                addBtn.onclick = function () {
                    const cfg = getRelatedConfig(relatedType, null, targetInputName);
                    if (cfg && cfg.addUrl) {
                        openRelatedPopup(cfg.addUrl);
                    }
                };

                editBtn.onclick = function () {
                    const selectedId = select.value;
                    const cfg = getRelatedConfig(relatedType, selectedId, targetInputName);
                    if (cfg && cfg.editUrl) {
                        openRelatedPopup(cfg.editUrl);
                    }
                };

                deleteBtn.onclick = function () {
                    const selectedId = select.value;
                    const cfg = getRelatedConfig(relatedType, selectedId, targetInputName);
                    if (cfg && cfg.deleteUrl) {
                        openRelatedPopup(cfg.deleteUrl);
                    }
                };

                select.addEventListener("change", refreshButtons);
                refreshButtons();
            });
        }

        // Funzione per aggiornare i contatori nei titoli delle tab
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
            const familiariRows = countPersistedRows("familiari-table");
            const studentiRows = countPersistedRows("studenti-table");
            const documentiRows = countPersistedRows("documenti-table");

            const tabFamiliari = document.querySelector('[data-tab-target="tab-familiari"]');
            const tabStudenti = document.querySelector('[data-tab-target="tab-studenti"]');
            const tabDocumenti = document.querySelector('[data-tab-target="tab-documenti"]');
            const relatedDocumentCount = tabDocumenti
                ? parseInt(tabDocumenti.dataset.relatedDocumentCount || "0", 10) || 0
                : 0;

            if (tabFamiliari) {
                tabFamiliari.textContent = `${tabTitleForInlineEditLabel(tabFamiliari)} (${familiariRows})`;
            }
            if (tabStudenti) {
                tabStudenti.textContent = `${tabTitleForInlineEditLabel(tabStudenti)} (${studentiRows})`;
            }
            if (tabDocumenti) {
                tabDocumenti.textContent = `${tabTitleForInlineEditLabel(tabDocumenti)} (${documentiRows + relatedDocumentCount})`;
            }
        }

        function removeInlineRow(button) {
            const row = button.closest("tr");
            if (row) {
                const subformRow = row.nextElementSibling;
                if (subformRow && subformRow.classList.contains("inline-subform-row")) {
                    subformRow.remove();
                }
                row.remove();
                refreshTabCounts();
            }
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

        function getFamiliareSubformRow(row) {
            const subformRow = row.nextElementSibling;
            if (subformRow && subformRow.classList.contains("inline-subform-row")) {
                return subformRow;
            }
            return null;
        }

        function clearRowData(row) {
            if (!row) {
                return;
            }

            row.querySelectorAll("input, textarea, select").forEach(field => {
                const type = (field.type || "").toLowerCase();
                const name = field.name || "";

                if (type === "hidden" && /-id$/.test(name)) {
                    return;
                }

                if (type === "hidden") {
                    field.value = "";
                    return;
                }

                if (type === "checkbox") {
                    field.checked = false;
                    return;
                }

                if (field.tagName.toLowerCase() === "select") {
                    field.value = "";
                    return;
                }

                field.value = "";
            });
        }

        function setRowInputsEnabled(row, isEnabled) {
            if (!row) {
                return;
            }

            row.querySelectorAll("input, textarea, select").forEach(field => {
                if (!isEnabled) {
                    field.disabled = true;
                    if (field.type !== "hidden") {
                        field.readOnly = true;
                    }
                } else if (!field.classList.contains("submit-safe-locked")) {
                    field.disabled = false;
                    field.readOnly = false;
                }
            });
        }

        function prepareHiddenEmptyRow(row) {
            row.classList.add("inline-empty-row", "is-hidden");
            clearRowData(row);
            setRowInputsEnabled(row, false);

            const subformRow = getFamiliareSubformRow(row);
            if (subformRow) {
                subformRow.classList.add("inline-empty-row", "is-hidden");
                clearRowData(subformRow);
                setRowInputsEnabled(subformRow, false);
            }
        }

        function primeNewFamiliareRow(row) {
            const relazioneSelect = row.querySelector('select[name$="-relazione_familiare"]');
            if (!relazioneSelect || relazioneSelect.value) {
                return;
            }

            const firstOption = Array.from(relazioneSelect.options).find(option => option.value);
            if (firstOption) {
                relazioneSelect.value = firstOption.value;
            }
        }

        function syncFamiliareInlineSex(row) {
            const relazioneSelect = row.querySelector('select[name$="-relazione_familiare"]');
            const subformRow = getFamiliareSubformRow(row);
            const sessoSelect = subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null;

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

        function bindFamiliareInlineSex(row) {
            const relazioneSelect = row.querySelector('select[name$="-relazione_familiare"]');
            if (!relazioneSelect || relazioneSelect.dataset.sexBound === "1") {
                return;
            }

            relazioneSelect.dataset.sexBound = "1";
            relazioneSelect.addEventListener("change", function () {
                syncFamiliareInlineSex(row);
            });
            syncFamiliareInlineSex(row);
        }

        function bindAllFamiliareInlineSex() {
            document.querySelectorAll("#familiari-table tbody .inline-form-row").forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }
                bindFamiliareInlineSex(row);
            });
        }

        function syncStudenteInlineSex(row) {
            const nomeInput = row.querySelector('input[name$="-nome"]');
            const subformRow = getFamiliareSubformRow(row);
            const sessoSelect = subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null;

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

        function bindStudenteInlineSex(row) {
            const nomeInput = row.querySelector('input[name$="-nome"]');
            if (!nomeInput || nomeInput.dataset.sexBound === "1") {
                return;
            }

            nomeInput.dataset.sexBound = "1";
            nomeInput.addEventListener("change", function () {
                syncStudenteInlineSex(row);
            });
            nomeInput.addEventListener("input", function () {
                syncStudenteInlineSex(row);
            });
            syncStudenteInlineSex(row);
        }

        function bindAllStudenteInlineSex() {
            document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }
                bindStudenteInlineSex(row);
            });
        }

        function isRowPersisted(row) {
            const hiddenIdInput = row.querySelector('input[type="hidden"][name$="-id"]');
            return Boolean(hiddenIdInput && hiddenIdInput.value);
        }

        function rowHasVisibleErrors(row) {
            let nextRow = row.nextElementSibling;

            if (nextRow && nextRow.classList.contains("inline-subform-row")) {
                nextRow = nextRow.nextElementSibling;
            }

            return Boolean(nextRow && nextRow.classList.contains("inline-errors-row"));
        }

        function rowHasUserData(row) {
            const fields = row.querySelectorAll("input, textarea, select");
            const subformRow = getFamiliareSubformRow(row);
            const subformFields = subformRow ? subformRow.querySelectorAll("input, textarea, select") : [];

            for (const field of [...fields, ...subformFields]) {
                const type = (field.type || "").toLowerCase();
                if (type === "hidden" || type === "checkbox") {
                    continue;
                }
                if (field.tagName.toLowerCase() === "select") {
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

                prepareHiddenEmptyRow(row);
            });
        }

        function addInlineForm(prefix) {
            const hiddenRow = document.querySelector(`#${prefix}-table tbody .inline-form-row.inline-empty-row.is-hidden`);
            if (hiddenRow) {
                hiddenRow.classList.remove("is-hidden");
                hiddenRow.classList.remove("inline-empty-row");
                setRowInputsEnabled(hiddenRow, true);

                const hiddenSubformRow = hiddenRow.nextElementSibling;
                if (hiddenSubformRow && hiddenSubformRow.classList.contains("inline-subform-row")) {
                    hiddenSubformRow.classList.remove("is-hidden");
                    hiddenSubformRow.classList.remove("inline-empty-row");
                    setRowInputsEnabled(hiddenSubformRow, true);
                }

                if (prefix === "familiari") {
                    primeNewFamiliareRow(hiddenRow);
                }
                initSearchableSelects(hiddenRow);
                const visibleSubformRow = getFamiliareSubformRow(hiddenRow);
                if (visibleSubformRow) {
                    initSearchableSelects(visibleSubformRow);
                }
                wireInlineRelatedButtons(hiddenRow);
                if (prefix === "familiari") {
                    bindFamiliareInlineSex(hiddenRow);
                } else if (prefix === "studenti") {
                    bindStudenteInlineSex(hiddenRow);
                }

                const firstInput = hiddenRow.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea");
                if (firstInput) {
                    firstInput.focus();
                }

                const tabId = `tab-${prefix}`;
                activateTab(tabId);
                refreshTabCounts();
                if (prefix === "familiari") {
                    syncFamiliareInlineAddresses();
                } else if (prefix === "studenti") {
                    syncStudenteInlineDefaults();
                }
                refreshAllInlineAddressHelp();
                return;
            }

            const totalForms = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
            const currentIndex = parseInt(totalForms.value, 10);

            const template = document.getElementById(`${prefix}-empty-form-template`).innerHTML;
            const newRowHtml = template.replace(/__prefix__/g, currentIndex);

            const tbody = document.querySelector(`#${prefix}-table tbody`);
            tbody.insertAdjacentHTML("beforeend", newRowHtml);

            totalForms.value = currentIndex + 1;

            let newRow = tbody.lastElementChild;
            if (newRow && newRow.classList.contains("inline-subform-row")) {
                newRow = newRow.previousElementSibling;
            }
            if (newRow) {
                setRowInputsEnabled(newRow, true);
                const subformRow = getFamiliareSubformRow(newRow);
                if (subformRow) {
                    setRowInputsEnabled(subformRow, true);
                }
                if (prefix === "familiari") {
                    primeNewFamiliareRow(newRow);
                }
                initSearchableSelects(newRow);
                if (subformRow) {
                    initSearchableSelects(subformRow);
                }
                wireInlineRelatedButtons(newRow);
                if (prefix === "familiari") {
                    bindFamiliareInlineSex(newRow);
                } else if (prefix === "studenti") {
                    bindStudenteInlineSex(newRow);
                }

                const firstInput = newRow.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea");
                if (firstInput) {
                    firstInput.focus();
                }
            }

            const tabId = `tab-${prefix}`;
            activateTab(tabId);
            refreshTabCounts();
            if (prefix === "familiari") {
                syncFamiliareInlineAddresses();
            } else if (prefix === "studenti") {
                syncStudenteInlineDefaults();
            }
            refreshAllInlineAddressHelp();
        }

        function addInlineFormFromView(prefix) {
            if (window.famigliaViewMode && !window.famigliaViewMode.isEditing()) {
                window.famigliaViewMode.setInlineEditing(true);
            }

            addInlineForm(prefix);
        }

        window.removeInlineRow = removeInlineRow;
        window.addInlineForm = addInlineForm;
        window.addFamigliaInlineForm = addInlineFormFromView;

        const statoSelect = document.getElementById("id_stato_relazione_famiglia");
        const indirizzoSelect = document.getElementById("id_indirizzo_principale");
        const cognomeFamigliaInput = document.getElementById("id_cognome_famiglia");

        const addStatoBtn = document.getElementById("add-stato-btn");
        const editStatoBtn = document.getElementById("edit-stato-btn");
        const deleteStatoBtn = document.getElementById("delete-stato-btn");

        const addIndirizzoBtn = document.getElementById("add-indirizzo-btn");
        const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
        const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");

        function updateMainRelatedButtons() {
            if (editStatoBtn && statoSelect) editStatoBtn.disabled = !statoSelect.value;
            if (deleteStatoBtn && statoSelect) deleteStatoBtn.disabled = !statoSelect.value;

            if (editIndirizzoBtn && indirizzoSelect) editIndirizzoBtn.disabled = !indirizzoSelect.value;
            if (deleteIndirizzoBtn && indirizzoSelect) deleteIndirizzoBtn.disabled = !indirizzoSelect.value;
        }

        if (addStatoBtn && statoSelect) {
            addStatoBtn.addEventListener("click", function () {
                openRelatedPopup(`${config.urls.creaStatoRelazioneFamiglia}?popup=1&target_input_name=${encodeURIComponent(statoSelect.name)}`);
            });
        }

        if (editStatoBtn && statoSelect) {
            editStatoBtn.addEventListener("click", function () {
                if (statoSelect.value) {
                    openRelatedPopup(`/stati-relazione-famiglia/${statoSelect.value}/modifica/?popup=1&target_input_name=${encodeURIComponent(statoSelect.name)}`);
                }
            });
        }

        if (deleteStatoBtn && statoSelect) {
            deleteStatoBtn.addEventListener("click", function () {
                if (statoSelect.value) {
                    openRelatedPopup(`/stati-relazione-famiglia/${statoSelect.value}/elimina/?popup=1&target_input_name=${encodeURIComponent(statoSelect.name)}`);
                }
            });
        }

        if (addIndirizzoBtn && indirizzoSelect) {
            addIndirizzoBtn.addEventListener("click", function () {
                openRelatedPopup(`${config.urls.creaIndirizzo}?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
            });
        }

        if (editIndirizzoBtn && indirizzoSelect) {
            editIndirizzoBtn.addEventListener("click", function () {
                if (indirizzoSelect.value) {
                    openRelatedPopup(`/indirizzi/${indirizzoSelect.value}/modifica/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
                }
            });
        }

        if (deleteIndirizzoBtn && indirizzoSelect) {
            deleteIndirizzoBtn.addEventListener("click", function () {
                if (indirizzoSelect.value) {
                    openRelatedPopup(`/indirizzi/${indirizzoSelect.value}/elimina/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
                }
            });
        }

        if (statoSelect) {
            statoSelect.addEventListener("change", updateMainRelatedButtons);
        }

        if (indirizzoSelect) {
            indirizzoSelect.addEventListener("change", updateMainRelatedButtons);
            indirizzoSelect.addEventListener("change", function () {
                syncFamiliareInlineAddresses();
                syncStudenteInlineDefaults();
                refreshAllInlineAddressHelp();
            });
        }

        if (cognomeFamigliaInput) {
            cognomeFamigliaInput.addEventListener("input", syncStudenteInlineDefaults);
            cognomeFamigliaInput.addEventListener("change", syncStudenteInlineDefaults);
        }

        prepareExistingEmptyRows("familiari-table");
        prepareExistingEmptyRows("studenti-table");
        prepareExistingEmptyRows("documenti-table");
        const inlineLockRoot = famigliaInlineRoot();
        if (inlineLockRoot) {
            tabs.bindTabButtons(getFamigliaTabStorageKey(), inlineLockRoot);
        }
        document.querySelectorAll("#famiglia-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
            btn.addEventListener("arboris:before-tab-activate", function (event) {
                if (btn.classList.contains("is-tab-locked")) {
                    event.preventDefault();
                }
            });

            btn.addEventListener("click", function () {
                const isInlineEditing = Boolean(
                    window.famigliaViewMode &&
                    typeof window.famigliaViewMode.isInlineEditing === "function" &&
                    window.famigliaViewMode.isInlineEditing()
                );

                if (btn.classList.contains("is-tab-locked")) {
                    refreshInlineEditScope();
                    return;
                }

                if (!isInlineEditing) {
                    setInlineTarget(btn.dataset.tabTarget);
                    updateInlineEditButtonLabel(btn.dataset.tabTarget);
                }

                syncActiveTabUrl(btn.dataset.tabTarget);
                refreshInlineEditScope();
            });
        });
        updateMainRelatedButtons();
        collapsible.initCollapsibleSections(document);
        bindNotesSectionState();
        initSearchableSelects(document.getElementById("famiglia-lock-container"));
        wireInlineRelatedButtons(document);
        restoreActiveTab();
        syncFamiliareInlineAddresses();
        bindAllFamiliareInlineSex();
        bindAllStudenteInlineSex();
        syncStudenteInlineDefaults();
        refreshAllInlineAddressHelp();
        refreshTabCounts();
        refreshInlineEditScope();
        syncNotesSectionState();
    }

    return {
        init,
        refreshLockedTabs: function () {
            refreshLockedTabsHandler();
        },
        refreshInlineEditScope: function () {
            refreshInlineEditScopeHandler();
        },
    };
})();
