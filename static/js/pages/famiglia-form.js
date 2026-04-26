window.ArborisFamigliaForm = (function () {
    let refreshInlineEditScopeHandler = function () {};
    let refreshLockedTabsHandler = function () {};

    function init(config) {
        const relatedPopups = window.ArborisRelatedPopups;
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineTabs = window.ArborisInlineTabs;
        const inlineFormsets = window.ArborisInlineFormsets;
        const personRules = window.ArborisPersonRules;
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;

        if (!relatedPopups || !collapsible || !tabs || !inlineTabs || !inlineFormsets || !personRules || !familyLinkedAddress) {
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

        const inlineLockContainerId = "famiglia-inline-lock-container";
        const targetInputId = "famiglia-inline-target";
        const inlineEditButtonId = "enable-inline-edit-famiglia-btn";
        const famigliaInlineRoot = () => document.getElementById(inlineLockContainerId);
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
            inlineTabs.setInlineTargetValue(targetInputId, tabId);
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
            inlineTabs.updateDefaultInlineEditButtonLabel({
                buttonId: inlineEditButtonId,
                containerId: inlineLockContainerId,
                tabId: tabId,
                getViewMode: function () {
                    return window.famigliaViewMode;
                },
            });
        }

        function refreshLockedTabs() {
            inlineTabs.clearTabButtonLockClasses(inlineLockContainerId);
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

        const famigliaInlineAddressConfig = {
            getFamilyAddressId: function () {
                return document.getElementById("id_indirizzo_principale")?.value || "";
            },
            getFamilyAddressLabel: getFamigliaIndirizzoPrincipaleLabel,
            emptyFamilyPrefix: "Ereditera: ",
        };

        const famigliaInlineAddressTrackingConfig = Object.assign({
            bindFlag: "inheritedTrackingBound",
        }, famigliaInlineAddressConfig);

        const familiariInlineDefaultsConfig = Object.assign({
            rowSelector: "#familiari-table tbody .inline-form-row",
            attivoSelector: 'input[type="checkbox"][name$="-attivo"]',
        }, famigliaInlineAddressConfig);

        const studentiInlineDefaultsConfig = Object.assign({
            rowSelector: "#studenti-table tbody .inline-form-row",
            surnameSelector: 'input[name$="-cognome"]',
            getFamilySurname: getFamigliaCognome,
            attivoSelector: 'input[type="checkbox"][name$="-attivo"]',
        }, famigliaInlineAddressConfig);

        function refreshInlineAddressHelp(select) {
            familyLinkedAddress.refreshInlineAddressHelp(select, famigliaInlineAddressConfig);
        }
        function refreshAllInlineAddressHelp() {
            familyLinkedAddress.refreshInlineAddressHelpForCollection(
                document.getElementById("famiglia-inline-lock-container"),
                Object.assign({ selector: 'select[name$="-indirizzo"]' }, famigliaInlineAddressConfig)
            );
        }

        function initSearchableSelects(root) {
            if (window.ArborisFamigliaAutocomplete && typeof window.ArborisFamigliaAutocomplete.init === "function") {
                window.ArborisFamigliaAutocomplete.init(root || document);
            }
            if (window.ArborisFamigliaAutocomplete && typeof window.ArborisFamigliaAutocomplete.refresh === "function") {
                window.ArborisFamigliaAutocomplete.refresh(root || document);
            }
        }

        function initCodiceFiscale(root) {
            if (window.ArborisCodiceFiscale && typeof window.ArborisCodiceFiscale.rebind === "function") {
                window.ArborisCodiceFiscale.rebind(root || document);
                return;
            }

            if (window.ArborisCodiceFiscale && typeof window.ArborisCodiceFiscale.init === "function") {
                window.ArborisCodiceFiscale.init(root || document);
            }
        }

        function syncFamiliareInlineAddresses() {
            familyLinkedAddress.syncInlineRows("#familiari-table tbody .inline-form-row", familiariInlineDefaultsConfig);
        }


        function getFamigliaCognome() {
            return document.getElementById("id_cognome_famiglia")?.value?.trim() || "";
        }

        function syncStudenteInlineDefaults() {
            familyLinkedAddress.syncInlineRows("#studenti-table tbody .inline-form-row", studentiInlineDefaultsConfig);
        }


        function wireInlineRelatedButtons(container) {
            const routes = window.ArborisRelatedEntityRoutes;
            if (!routes) {
                console.error("ArborisRelatedEntityRoutes non disponibile.");
                return;
            }
            routes.wireInlineRelatedButtons(container, {
                openRelatedPopup: openRelatedPopup,
                onRefresh(relatedType, select) {
                    if (relatedType === "indirizzo") {
                        familyLinkedAddress.refreshInlineAddressHelp(select, famigliaInlineAddressConfig);
                    }
                },
            });
        }

        // Funzione per aggiornare i contatori nei titoli delle tab
        function countPersistedRows(tableId) {
            return inlineFormsets.countPersistedRows(tableId);
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
                tabFamiliari.textContent = `${inlineTabs.inlineLabelFromTabButton(tabFamiliari)} (${familiariRows})`;
            }
            if (tabStudenti) {
                tabStudenti.textContent = `${inlineTabs.inlineLabelFromTabButton(tabStudenti)} (${studentiRows})`;
            }
            if (tabDocumenti) {
                tabDocumenti.textContent = `${inlineTabs.inlineLabelFromTabButton(tabDocumenti)} (${documentiRows + relatedDocumentCount})`;
            }
        }

        function removeInlineRow(button) {
            if (inlineFormsets.removeInlineRow(button, { companionClasses: ["inline-subform-row"] })) {
                refreshTabCounts();
            }
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
            if (row) {
                inlineFormsets.setRowInputsEnabled(row, isEnabled, {
                    includeCompanionRows: false,
                    skipHiddenInputs: false,
                });
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
            const inferredSex = personRules.inferSexFromRelationLabel(selectedOption ? selectedOption.textContent : "");

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

            const inferredSex = personRules.inferSexFromFirstName(nomeInput.value);
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

        function parseInlineDateValue(value) {
            if (!value) {
                return null;
            }

            const parsed = new Date(`${value}T00:00:00`);
            if (Number.isNaN(parsed.getTime())) {
                return null;
            }

            return parsed;
        }

        function getStudentRowBundle(row) {
            return inlineFormsets.getRowBundle(row, { companionClasses: ["inline-subform-row"] }).bundle;
        }

        function compareStudentRowsByAge(leftRow, rightRow) {
            const leftDateValue = getFamiliareSubformRow(leftRow)?.querySelector('input[name$="-data_nascita"]')?.value || "";
            const rightDateValue = getFamiliareSubformRow(rightRow)?.querySelector('input[name$="-data_nascita"]')?.value || "";
            const leftDate = parseInlineDateValue(leftDateValue);
            const rightDate = parseInlineDateValue(rightDateValue);

            if (leftDate && rightDate) {
                const dateDiff = leftDate.getTime() - rightDate.getTime();
                if (dateDiff !== 0) {
                    return dateDiff;
                }
            } else if (leftDate) {
                return -1;
            } else if (rightDate) {
                return 1;
            }

            const leftCognome = (leftRow.querySelector('input[name$="-cognome"]')?.value || "").trim().toLowerCase();
            const rightCognome = (rightRow.querySelector('input[name$="-cognome"]')?.value || "").trim().toLowerCase();
            if (leftCognome !== rightCognome) {
                return leftCognome.localeCompare(rightCognome, "it");
            }

            const leftNome = (leftRow.querySelector('input[name$="-nome"]')?.value || "").trim().toLowerCase();
            const rightNome = (rightRow.querySelector('input[name$="-nome"]')?.value || "").trim().toLowerCase();
            return leftNome.localeCompare(rightNome, "it");
        }

        function sortStudentiInlineRows() {
            const tbody = document.querySelector("#studenti-table tbody");
            if (!tbody) {
                return;
            }

            const bundles = [];
            let currentRow = tbody.firstElementChild;

            while (currentRow) {
                if (!currentRow.classList.contains("inline-form-row")) {
                    currentRow = currentRow.nextElementSibling;
                    continue;
                }

                const bundle = getStudentRowBundle(currentRow);
                bundles.push(bundle);
                currentRow = bundle[bundle.length - 1].nextElementSibling;
            }

            const visibleBundles = [];
            const hiddenBundles = [];

            bundles.forEach(bundle => {
                const mainRow = bundle[0];
                if (mainRow.classList.contains("inline-empty-row") && mainRow.classList.contains("is-hidden")) {
                    hiddenBundles.push(bundle);
                    return;
                }
                visibleBundles.push(bundle);
            });

            visibleBundles.sort((leftBundle, rightBundle) => compareStudentRowsByAge(leftBundle[0], rightBundle[0]));

            [...visibleBundles, ...hiddenBundles].forEach(bundle => {
                bundle.forEach(node => tbody.appendChild(node));
            });
        }

        function bindStudenteInlineBirthDateOrdering(row) {
            const dataNascitaInput = getFamiliareSubformRow(row)?.querySelector('input[name$="-data_nascita"]');
            if (!dataNascitaInput || dataNascitaInput.dataset.orderingBound === "1") {
                return;
            }

            dataNascitaInput.dataset.orderingBound = "1";
            dataNascitaInput.addEventListener("change", sortStudentiInlineRows);
            dataNascitaInput.addEventListener("input", sortStudentiInlineRows);
        }

        function bindAllStudenteInlineBirthDateOrdering() {
            document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }
                bindStudenteInlineBirthDateOrdering(row);
            });
        }

        function prepareExistingEmptyRows(tableId) {
            inlineFormsets.prepareExistingEmptyRows(tableId, {
                companionClasses: ["inline-subform-row"],
                includeCompanionRowsInData: true,
                ignoreSelects: true,
                onHide: function (state) {
                    [state.row].concat(state.companionRows).forEach(function (node) {
                        clearRowData(node);
                        setRowInputsEnabled(node, false);
                    });
                },
            });
        }

        function addInlineForm(prefix) {
            const mounted = inlineFormsets.mountInlineForm(prefix, {
                companionClasses: ["inline-subform-row"],
                enableInputs: true,
                onReady: function (state) {
                    const row = state.row;
                    const subformRow = state.companionRows[0] || getFamiliareSubformRow(row);
                    if (prefix === "familiari") {
                        primeNewFamiliareRow(row);
                    }
                    initSearchableSelects(row);
                    if (subformRow) {
                        initSearchableSelects(subformRow);
                        initCodiceFiscale(subformRow);
                    }
                    familyLinkedAddress.bindInlineAddressTracking(row, famigliaInlineAddressTrackingConfig);
                    initCodiceFiscale(row);
                    wireInlineRelatedButtons(row);
                    if (prefix === "familiari") {
                        bindFamiliareInlineSex(row);
                    } else if (prefix === "studenti") {
                        bindStudenteInlineSex(row);
                        bindStudenteInlineBirthDateOrdering(row);
                    }
                },
                focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
            });

            if (!mounted) {
                return;
            }

            const tabId = `tab-${prefix}`;
            activateTab(tabId);
            refreshTabCounts();
            if (prefix === "familiari") {
                syncFamiliareInlineAddresses();
            } else if (prefix === "studenti") {
                syncStudenteInlineDefaults();
                sortStudentiInlineRows();
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
        let refreshStatoButtons = function () {};
        let refreshIndirizzoButtons = function () {};

        function updateMainRelatedButtons() {
            refreshStatoButtons();
            refreshIndirizzoButtons();
        }

        const entityRoutes = window.ArborisRelatedEntityRoutes;
        if (!entityRoutes) {
            console.error("ArborisRelatedEntityRoutes non disponibile.");
        }

        if (statoSelect && entityRoutes) {
            const statoCrud = entityRoutes.wireCrudButtons({
                select: statoSelect,
                relatedType: "stato_relazione_famiglia",
                addBtn: addStatoBtn,
                editBtn: editStatoBtn,
                deleteBtn: deleteStatoBtn,
                openRelatedPopup: openRelatedPopup,
            });
            refreshStatoButtons = statoCrud.refresh;
        }

        if (indirizzoSelect && entityRoutes) {
            const indirizzoCrud = entityRoutes.wireCrudButtons({
                select: indirizzoSelect,
                relatedType: "indirizzo",
                addBtn: addIndirizzoBtn,
                editBtn: editIndirizzoBtn,
                deleteBtn: deleteIndirizzoBtn,
                openRelatedPopup: openRelatedPopup,
            });
            refreshIndirizzoButtons = indirizzoCrud.refresh;
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
        document.querySelectorAll("#" + inlineLockContainerId + " .tab-btn[data-tab-target]").forEach(btn => {
            btn.addEventListener("click", function () {
                setInlineTarget(btn.dataset.tabTarget);
                updateInlineEditButtonLabel(btn.dataset.tabTarget);
                syncActiveTabUrl(btn.dataset.tabTarget);
                refreshInlineEditScope();
            });
        });
        updateMainRelatedButtons();
        collapsible.initCollapsibleSections(document);
        bindNotesSectionState();
        initSearchableSelects(document.getElementById("famiglia-lock-container"));
        familyLinkedAddress.bindInlineAddressTracking(document.getElementById("famiglia-inline-lock-container"), famigliaInlineAddressTrackingConfig);
        wireInlineRelatedButtons(document);
        restoreActiveTab();
        syncFamiliareInlineAddresses();
        bindAllFamiliareInlineSex();
        bindAllStudenteInlineSex();
        bindAllStudenteInlineBirthDateOrdering();
        syncStudenteInlineDefaults();
        sortStudentiInlineRows();
        initCodiceFiscale(document.getElementById("famiglia-inline-lock-container"));
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

