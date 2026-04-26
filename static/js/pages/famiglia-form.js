window.ArborisFamigliaForm = (function () {
    let refreshInlineEditScopeHandler = function () {};
    let refreshLockedTabsHandler = function () {};

    function init(config) {
        const entityRoutes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = entityRoutes && entityRoutes.initRelatedPopups();
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineTabs = window.ArborisInlineTabs;
        const inlineFormsets = window.ArborisInlineFormsets;
        const personRules = window.ArborisPersonRules;
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;
        const formTools = window.ArborisAnagraficaFormTools;

        if (!entityRoutes || !relatedPopups || !collapsible || !tabs || !inlineTabs || !inlineFormsets || !personRules || !familyLinkedAddress || !formTools) {
            console.error("Arboris core JS non caricato correttamente.");
            return;
        }

        const openRelatedPopup = relatedPopups.openRelatedPopup;

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
            inlineTabs.refreshTabButtonLocks({
                containerId: inlineLockContainerId,
                targetInputId: targetInputId,
                getViewMode: function () {
                    return window.famigliaViewMode;
                },
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

        function getFamigliaCognome() {
            return document.getElementById("id_cognome_famiglia")?.value?.trim() || "";
        }

        const famigliaInlineAddressCollection = familyLinkedAddress.createInlineAddressCollection(
            Object.assign({ selector: 'select[name$="-indirizzo"]' }, famigliaInlineAddressTrackingConfig)
        );
        const familiariInlineAddressDefaults = familyLinkedAddress.createInlineAddressCollection(familiariInlineDefaultsConfig);
        const studentiInlineAddressDefaults = familyLinkedAddress.createInlineAddressCollection(studentiInlineDefaultsConfig);

        function wireInlineRelatedButtons(container) {
            formTools.wireInlineRelatedButtons(container, {
                routes: entityRoutes,
                relatedPopups: relatedPopups,
                onRefresh(relatedType, select) {
                    if (relatedType === "indirizzo") {
                        famigliaInlineAddressCollection.refreshSelectHelp(select);
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

        function createInlineManager(prefix, options) {
            return inlineFormsets.createManager({
                prefix: prefix,
                prepareOptions: options && options.prepareOptions ? options.prepareOptions : {},
                mountOptions: options && options.mountOptions ? options.mountOptions : {},
                removeOptions: options && options.removeOptions ? options.removeOptions : {},
            });
        }

        function hideInlineState(state) {
            [state.row].concat(state.companionRows).forEach(function (node) {
                clearRowData(node);
                setRowInputsEnabled(node, false);
            });
        }

        const inlineManagers = {
            familiari: createInlineManager("familiari", {
                prepareOptions: {
                    companionClasses: ["inline-subform-row"],
                    includeCompanionRowsInData: true,
                    ignoreSelects: true,
                    onHide: hideInlineState,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
                    enableInputs: true,
                    onReady: function (state) {
                        const row = state.row;
                        const subformRow = state.companionRows[0] || getFamiliareSubformRow(row);
                        primeNewFamiliareRow(row);
                        formTools.initSearchableSelects(row);
                        if (subformRow) {
                            formTools.initSearchableSelects(subformRow);
                            formTools.initCodiceFiscale(subformRow);
                        }
                        famigliaInlineAddressCollection.bindTracking(row);
                        formTools.initCodiceFiscale(row);
                        wireInlineRelatedButtons(row);
                        bindFamiliareInlineSex(row);
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-subform-row"],
                },
            }),
            studenti: createInlineManager("studenti", {
                prepareOptions: {
                    companionClasses: ["inline-subform-row"],
                    includeCompanionRowsInData: true,
                    ignoreSelects: true,
                    onHide: hideInlineState,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
                    enableInputs: true,
                    onReady: function (state) {
                        const row = state.row;
                        const subformRow = state.companionRows[0] || getFamiliareSubformRow(row);
                        formTools.initSearchableSelects(row);
                        if (subformRow) {
                            formTools.initSearchableSelects(subformRow);
                            formTools.initCodiceFiscale(subformRow);
                        }
                        famigliaInlineAddressCollection.bindTracking(row);
                        formTools.initCodiceFiscale(row);
                        wireInlineRelatedButtons(row);
                        bindStudenteInlineSex(row);
                        bindStudenteInlineBirthDateOrdering(row);
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-subform-row"],
                },
            }),
            documenti: createInlineManager("documenti", {
                prepareOptions: {
                    onHide: hideInlineState,
                },
                mountOptions: {
                    enableInputs: true,
                    onReady: function (state) {
                        wireInlineRelatedButtons(state.row);
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
            }),
        };

        function removeManagedInlineRow(button) {
            const row = button && button.closest ? button.closest("tr") : null;
            const table = row ? row.closest("table") : null;
            const manager = table ? inlineManagers[table.id.replace("-table", "")] : null;
            const removed = manager ? manager.remove(button) : null;

            if (removed) {
                refreshTabCounts();
            }
        }

        function getFamiliareSubformRow(row) {
            return inlineFormsets.getPrimaryCompanionRow(row, { companionClasses: ["inline-subform-row"] });
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

        function bindFamiliareInlineSex(row) {
            const subformRow = getFamiliareSubformRow(row);
            personRules.bindSexFromRelation({
                root: row,
                relationSelector: 'select[name$="-relazione_familiare"]',
                sexSelect: subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null,
                bindFlag: "sexBound",
            });
        }

        function bindAllFamiliareInlineSex() {
            document.querySelectorAll("#familiari-table tbody .inline-form-row").forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }
                bindFamiliareInlineSex(row);
            });
        }

        function bindStudenteInlineSex(row) {
            const subformRow = getFamiliareSubformRow(row);
            personRules.bindSexFromFirstName({
                root: row,
                nameSelector: 'input[name$="-nome"]',
                sexSelect: subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null,
                bindFlag: "sexBound",
            });
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

        function addManagedInlineForm(prefix) {
            const manager = inlineManagers[prefix];
            if (!manager) {
                return;
            }

            const mounted = manager.add();

            if (!mounted) {
                return;
            }

            const tabId = `tab-${prefix}`;
            activateTab(tabId);
            refreshTabCounts();
            if (prefix === "familiari") {
                familiariInlineAddressDefaults.syncRows();
            } else if (prefix === "studenti") {
                studentiInlineAddressDefaults.syncRows();
                sortStudentiInlineRows();
            }
            famigliaInlineAddressCollection.refreshCollectionHelp(document.getElementById("famiglia-inline-lock-container"));
        }

        function addInlineFormFromView(prefix) {
            if (window.famigliaViewMode && !window.famigliaViewMode.isEditing()) {
                window.famigliaViewMode.setInlineEditing(true);
            }

            addManagedInlineForm(prefix);
        }

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

        const statoCrud = entityRoutes.wireCrudButtonsById({
            select: statoSelect,
            relatedType: "stato_relazione_famiglia",
            addBtn: addStatoBtn,
            editBtn: editStatoBtn,
            deleteBtn: deleteStatoBtn,
            openRelatedPopup: openRelatedPopup,
        });
        refreshStatoButtons = statoCrud.refresh;

        const indirizzoCrud = entityRoutes.wireCrudButtonsById({
            select: indirizzoSelect,
            relatedType: "indirizzo",
            addBtn: addIndirizzoBtn,
            editBtn: editIndirizzoBtn,
            deleteBtn: deleteIndirizzoBtn,
            openRelatedPopup: openRelatedPopup,
        });
        refreshIndirizzoButtons = indirizzoCrud.refresh;

        if (statoSelect) {
            statoSelect.addEventListener("change", updateMainRelatedButtons);
        }

        if (indirizzoSelect) {
            indirizzoSelect.addEventListener("change", updateMainRelatedButtons);
            indirizzoSelect.addEventListener("change", function () {
                familiariInlineAddressDefaults.syncRows();
                studentiInlineAddressDefaults.syncRows();
                famigliaInlineAddressCollection.refreshCollectionHelp(document.getElementById("famiglia-inline-lock-container"));
            });
        }

        if (cognomeFamigliaInput) {
            cognomeFamigliaInput.addEventListener("input", function () {
                studentiInlineAddressDefaults.syncRows();
            });
            cognomeFamigliaInput.addEventListener("change", function () {
                studentiInlineAddressDefaults.syncRows();
            });
        }

        inlineManagers.familiari.prepare();
        inlineManagers.studenti.prepare();
        inlineManagers.documenti.prepare();
        const inlineLockRoot = famigliaInlineRoot();
        if (inlineLockRoot) {
            tabs.bindTabButtons(getFamigliaTabStorageKey(), inlineLockRoot);
            inlineTabs.bindTabNavigationLock({
                containerId: inlineLockContainerId,
                targetInputId: targetInputId,
                getViewMode: function () {
                    return window.famigliaViewMode;
                },
            });
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
        formTools.initSearchableSelects(document.getElementById("famiglia-lock-container"));
        famigliaInlineAddressCollection.bindTracking(document.getElementById("famiglia-inline-lock-container"));
        wireInlineRelatedButtons(document);
        inlineFormsets.wireActionTriggers(document, {
            handlers: {
                add: function (prefix) {
                    addManagedInlineForm(prefix);
                },
                "add-view": function (prefix) {
                    addInlineFormFromView(prefix);
                },
                remove: function (_prefix, element) {
                    removeManagedInlineRow(element);
                },
            },
        });
        entityRoutes.wirePopupTriggerElements(document, {
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        restoreActiveTab();
        familiariInlineAddressDefaults.syncRows();
        bindAllFamiliareInlineSex();
        bindAllStudenteInlineSex();
        bindAllStudenteInlineBirthDateOrdering();
        studentiInlineAddressDefaults.syncRows();
        sortStudentiInlineRows();
        formTools.initCodiceFiscale(document.getElementById("famiglia-inline-lock-container"));
        famigliaInlineAddressCollection.refreshCollectionHelp(document.getElementById("famiglia-inline-lock-container"));
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

