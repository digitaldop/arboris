window.ArborisFamiliareForm = (function () {
    let refreshInlineEditScopeHandler = function () {};

    function init(config) {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineTabs = window.ArborisInlineTabs;
        const inlineFormsets = window.ArborisInlineFormsets;
        const personRules = window.ArborisPersonRules;
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;
        const formTools = window.ArborisAnagraficaFormTools;

        if (!routes || !relatedPopups || !collapsible || !tabs || !inlineTabs || !inlineFormsets || !personRules || !familyLinkedAddress || !formTools) {
            console.error("Arboris core JS non caricato correttamente.");
            return;
        }

        const targetInputId = "familiare-inline-target";
        const inlineLockContainerId = "familiare-inline-lock-container";
        const inlineEditButtonId = "enable-inline-edit-familiare-btn";

        function getFamiliareTabStorageKey() {
            return `arboris-familiare-form-active-tab-${config.familiareId || "new"}`;
        }

        function setInlineTarget(prefixOrTabId) {
            inlineTabs.setInlineTargetValue(targetInputId, prefixOrTabId);
        }

        function updateInlineEditButtonLabel(tabId) {
            inlineTabs.updateDefaultInlineEditButtonLabel({
                buttonId: inlineEditButtonId,
                containerId: inlineLockContainerId,
                tabId: tabId,
                getViewMode: function () {
                    return window.familiareViewMode;
                },
            });
        }

        const refreshLockedTabs = inlineTabs.createRefreshLockedTabs({
            formId: "familiare-detail-form",
            inlineLockContainerId: inlineLockContainerId,
            targetInputId: targetInputId,
            getViewMode: function () {
                return window.familiareViewMode;
            },
            inlineEditButtonId: inlineEditButtonId,
        });

        function refreshInlineEditScope() {
            refreshLockedTabs();
        }
        refreshInlineEditScopeHandler = refreshInlineEditScope;

        function activatePanelIfPresent(tabId) {
            const panel = document.getElementById(tabId);
            if (!panel) {
                return;
            }

            if (document.querySelector(`[data-tab-target="${tabId}"]`)) {
                setInlineTarget(tabId);
                tabs.activateTab(tabId, getFamiliareTabStorageKey());
                updateInlineEditButtonLabel(tabId);
                refreshInlineEditScope();
                return;
            }

            document.querySelectorAll(".tab-panel").forEach(existingPanel => existingPanel.classList.remove("is-active"));
            panel.classList.add("is-active");
            setInlineTarget(tabId);
            updateInlineEditButtonLabel(tabId);
            refreshInlineEditScope();
        }

        function bindStandaloneSexFromRelazioneFamiliare() {
            personRules.bindSexFromRelation({
                relationSelect: document.getElementById("id_relazione_familiare"),
                sexSelect: document.getElementById("id_sesso"),
                bindFlag: "familiareRelationSexBound",
            });
        }

        function updateMainButtons() {
            refreshFamigliaNavigation();
            refreshRelazioneButtons();
            refreshIndirizzoButtons();
        }

        function wireInlineRelatedButtons(container) {
            formTools.wireInlineRelatedButtons(container, {
                routes: routes,
                relatedPopups: relatedPopups,
                onRefresh(relatedType, select) {
                    if (relatedType === "indirizzo" && select && select.closest("#studenti-table")) {
                        studentiInlineAddressCollection.refreshSelectHelp(select);
                    }
                },
            });
        }

        function readFamiliareStudentiInlineDefaults() {
            const el = document.getElementById("familiare-studenti-inline-defaults");
            if (!el) {
                return { indirizzo_principale_id: "", cognome_famiglia: "" };
            }
            try {
                return JSON.parse(el.textContent);
            } catch (e) {
                return { indirizzo_principale_id: "", cognome_famiglia: "" };
            }
        }

        function getStudenteInlineFamigliaIndirizzoPrincipaleLabel() {
            const node = document.getElementById("familiare-famiglia-indirizzo-label");
            if (!node) {
                return "";
            }
            try {
                const v = JSON.parse(node.textContent);
                return typeof v === "string" ? v : "";
            } catch (e) {
                return "";
            }
        }

        const studentiInlineAddressConfig = {
            getFamilyAddressId: function () {
                return readFamiliareStudentiInlineDefaults().indirizzo_principale_id || "";
            },
            getFamilyAddressLabel: getStudenteInlineFamigliaIndirizzoPrincipaleLabel,
            emptyFamilyPrefix: "Ereditera: ",
        };

        const studentiInlineAddressTrackingConfig = Object.assign({
            selector: 'select[name$="-indirizzo"]',
            bindFlag: "familiareStudenteAddrBound",
        }, studentiInlineAddressConfig);

        const studentiInlineDefaultsConfig = Object.assign({
            rowSelector: "#studenti-table tbody .inline-form-row",
            surnameSelector: 'input[name$="-cognome"]',
            getFamilySurname: function () {
                return (readFamiliareStudentiInlineDefaults().cognome_famiglia || "").trim();
            },
            attivoSelector: 'input[type="checkbox"][name$="-attivo"]',
        }, studentiInlineAddressConfig);
        const studentiInlineAddressCollection = familyLinkedAddress.createInlineAddressCollection(studentiInlineAddressTrackingConfig);
        const studentiInlineAddressDefaults = familyLinkedAddress.createInlineAddressCollection(studentiInlineDefaultsConfig);

        function getFamiliareSubformRow(row) {
            return inlineFormsets.getPrimaryCompanionRow(row, { companionClasses: ["inline-subform-row"] });
        }

        function bindStudenteInlineSex(row) {
            const subformRow = getFamiliareSubformRow(row);
            personRules.bindTrackedSexFromFirstName({
                root: row,
                nameSelector: 'input[name$="-nome"]',
                sexSelect: subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null,
                bindFlag: "studenteInlineSexNameBound",
                sourceKey: "studente-inline-name",
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

        function countPersistedRows(tableId) {
            return inlineFormsets.countPersistedRows(tableId);
        }

        function refreshTabCounts() {
            const documentiRows = countPersistedRows("documenti-table");
            const tabDocumenti = document.querySelector('[data-tab-target="tab-documenti"]');
            if (tabDocumenti) tabDocumenti.textContent = `Documenti (${documentiRows})`;
            const studentiHeading = document.getElementById("familiare-studenti-heading");
            if (studentiHeading && document.getElementById("studenti-table")) {
                const n = countPersistedRows("studenti-table");
                const tabStudenti = document.querySelector('[data-tab-target="tab-studenti"]');
                if (tabStudenti) {
                    const tabLabel = inlineTabs.inlineLabelFromTabButton(tabStudenti);
                    tabStudenti.textContent = `${tabLabel} (${n})`;
                }
                const label = studentiHeading.dataset.baseLabel || studentiHeading.textContent.replace(/\s*\(\d+\)\s*$/, "").trim();
                studentiHeading.dataset.baseLabel = label;
                studentiHeading.textContent = `${label} (${n})`;
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

        function refreshFirstStudentAddMode() {
            const form = document.getElementById("familiare-detail-form");
            if (!form) {
                return;
            }

            form.classList.toggle(
                "is-inline-first-student-add-mode",
                Boolean(document.querySelector("#studenti-table .is-inline-first-student-add-row"))
            );
        }

        function markFirstStudentAddRows(mounted, enabled) {
            if (!mounted || !mounted.state || !mounted.state.bundle) {
                refreshFirstStudentAddMode();
                return;
            }

            mounted.state.bundle.forEach(function (node) {
                if (node) {
                    node.classList.toggle("is-inline-first-student-add-row", Boolean(enabled));
                }
            });
            refreshFirstStudentAddMode();
        }

        const inlineManagers = {
            studenti: createInlineManager("studenti", {
                prepareOptions: {
                    companionClasses: ["inline-subform-row"],
                    includeCompanionRowsInData: true,
                    ignoreSelects: true,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
                    appendOnly: function () {
                        return countPersistedRows("studenti-table") > 0;
                    },
                    enableInputs: true,
                    onReady: function (state) {
                        const row = state.row;
                        wireInlineRelatedButtons(row);
                        formTools.initSearchableSelects(row);
                        const subformRow = state.companionRows[0] || getFamiliareSubformRow(row);
                        if (subformRow) {
                            formTools.initSearchableSelects(subformRow);
                            formTools.initCodiceFiscale(subformRow);
                        }
                        studentiInlineAddressCollection.bindTracking(row);
                        formTools.initCodiceFiscale(row);
                        bindStudenteInlineSex(row);
                        studentiInlineAddressDefaults.syncRows();
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-subform-row"],
                },
            }),
            documenti: createInlineManager("documenti", {
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
                refreshFirstStudentAddMode();
                refreshTabCounts();
            }
        }

        function addManagedInlineForm(prefix) {
            const manager = inlineManagers[prefix];
            if (!manager) {
                return;
            }

            const form = document.getElementById("familiare-detail-form");
            const isAlreadyAddOnlyMode = Boolean(form && form.classList.contains("is-inline-add-only-mode"));
            const isFirstStudentAdd = prefix === "studenti" && countPersistedRows("studenti-table") === 0;
            const shouldUseAddOnlyMode = Boolean(
                window.familiareViewMode &&
                (!window.familiareViewMode.isEditing() || isAlreadyAddOnlyMode)
            );

            setInlineTarget(prefix);
            activatePanelIfPresent(`tab-${prefix}`);

            if (window.familiareViewMode && !window.familiareViewMode.isEditing()) {
                window.familiareViewMode.setInlineEditing(true);
            }

            const mounted = manager.add();

            if (!mounted) {
                return;
            }

            if (shouldUseAddOnlyMode && mounted.state) {
                inlineFormsets.markBundleForAddOnlyEdit(mounted.state, {
                    form: "familiare-detail-form",
                });
            }

            if (prefix === "studenti") {
                markFirstStudentAddRows(mounted, isFirstStudentAdd && mounted.revealed);
            }

            refreshTabCounts();
        }

        function bindScambioRettaNavigation() {
            const root = document.getElementById("scambio-retta-inline");
            if (!root) {
                return;
            }

            root.querySelectorAll(".scambio-view-btn, .scambio-calendar-nav a").forEach(link => {
                if (link.dataset.scambioNavigationBound === "1") {
                    return;
                }

                link.dataset.scambioNavigationBound = "1";
                link.addEventListener("click", function (event) {
                    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                        return;
                    }

                    event.preventDefault();
                    event.stopPropagation();

                    if (typeof window.ArborisArmLongWaitForNavigationUrl === "function") {
                        window.ArborisArmLongWaitForNavigationUrl(link.href);
                    }
                    window.location.assign(link.href);
                });
            });
        }

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
        let refreshFamigliaNavigation = function () {};
        let refreshRelazioneButtons = function () {};
        let refreshIndirizzoButtons = function () {};

        const famigliaNavigation = formTools.bindFamigliaNavigation({
            familySelect: famigliaSelect,
            addBtn: addFamigliaBtn,
            editBtn: editFamigliaBtn,
            createUrl: config.urls.creaFamiglia,
        });
        refreshFamigliaNavigation = famigliaNavigation.refresh;

        const relazioneCrud = routes.wireCrudButtonsById({
            select: relazioneSelect,
            relatedType: "relazione_familiare",
            addBtn: addRelazioneBtn,
            editBtn: editRelazioneBtn,
            deleteBtn: deleteRelazioneBtn,
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        refreshRelazioneButtons = relazioneCrud.refresh;

        const indirizzoCrud = routes.wireCrudButtonsById({
            select: indirizzoSelect,
            relatedType: "indirizzo",
            addBtn: addIndirizzoBtn,
            editBtn: editIndirizzoBtn,
            deleteBtn: deleteIndirizzoBtn,
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        refreshIndirizzoButtons = indirizzoCrud.refresh;
        refreshFamigliaNavigation();

        formTools.bindFamilyAddressController({
            familyLinkedAddress: familyLinkedAddress,
            familySelect: famigliaSelect,
            addressSelect: indirizzoSelect,
            helpElement: document.getElementById("familiare-address-help"),
            fallbackLabelScriptId: "familiare-famiglia-indirizzo-label",
            onRefreshButtons: updateMainButtons,
            unselectedFamilyPrefix: "Ereditera: ",
        });

        if (relazioneSelect) {
            relazioneSelect.addEventListener("change", function () {
                updateMainButtons();
            });
        }

        inlineManagers.documenti.prepare();
        inlineManagers.studenti.prepare();
        const inlineLockRoot = document.getElementById(inlineLockContainerId);
        if (inlineLockRoot) {
            tabs.bindTabButtons(getFamiliareTabStorageKey(), inlineLockRoot);
            inlineTabs.bindTabNavigationLock({
                containerId: inlineLockContainerId,
                targetInputId: targetInputId,
                getViewMode: function () {
                    return window.familiareViewMode;
                },
            });
        }
        document.querySelectorAll("#familiare-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
            btn.addEventListener("click", function () {
                setInlineTarget(btn.dataset.tabTarget);
                updateInlineEditButtonLabel(btn.dataset.tabTarget);
                refreshInlineEditScope();
            });
        });
        collapsible.initCollapsibleSections(document);
        wireInlineRelatedButtons(document);
        inlineFormsets.wireActionTriggers(document, {
            handlers: {
                add: function (prefix) {
                    addManagedInlineForm(prefix);
                },
                remove: function (_prefix, element) {
                    removeManagedInlineRow(element);
                },
            },
        });
        routes.wirePopupTriggerElements(document, {
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
            studentiInlineAddressCollection.bindTracking(row);
        });
        bindAllStudenteInlineSex();
        tabs.restoreActiveTab(getFamiliareTabStorageKey());
        const activeTab = inlineLockRoot ? inlineLockRoot.querySelector(".tab-btn.is-active") : null;
        if (activeTab && activeTab.dataset.tabTarget) {
            setInlineTarget(activeTab.dataset.tabTarget);
            updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
        }
        bindStandaloneSexFromRelazioneFamiliare();
        bindScambioRettaNavigation();
        studentiInlineAddressDefaults.syncRows();
        updateMainButtons();
        refreshTabCounts();
        refreshInlineEditScope();
    }

    return {
        init,
        refreshInlineEditScope: function () {
            refreshInlineEditScopeHandler();
        },
    };
})();
