window.ArborisFamiliareForm = (function () {
    function init(config) {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineFormsets = window.ArborisInlineFormsets;
        const personRules = window.ArborisPersonRules;
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;
        const formTools = window.ArborisAnagraficaFormTools;

        if (!routes || !relatedPopups || !collapsible || !tabs || !inlineFormsets || !personRules || !familyLinkedAddress || !formTools) {
            console.error("Arboris core JS non caricato correttamente.");
            return;
        }

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
            personRules.bindSexFromFirstName({
                root: row,
                nameSelector: 'input[name$="-nome"]',
                sexSelect: subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null,
                bindFlag: "familiareSexBound",
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

        const inlineManagers = {
            studenti: createInlineManager("studenti", {
                prepareOptions: {
                    companionClasses: ["inline-subform-row"],
                    includeCompanionRowsInData: true,
                    ignoreSelects: true,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
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
                refreshTabCounts();
            }
        }

        function addManagedInlineForm(prefix) {
            const manager = inlineManagers[prefix];
            if (!manager) {
                return;
            }

            if (window.familiareViewMode && !window.familiareViewMode.isEditing()) {
                window.familiareViewMode.setInlineEditing(true);
            }

            const mounted = manager.add();

            if (!mounted) {
                return;
            }

            activatePanelIfPresent(`tab-${prefix}`);
            refreshTabCounts();
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
        tabs.bindTabButtons(getFamiliareTabStorageKey());
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
        bindStandaloneSexFromRelazioneFamiliare();
        studentiInlineAddressDefaults.syncRows();
        updateMainButtons();
        refreshTabCounts();
    }

    return {
        init,
    };
})();
