window.ArborisFamiliareForm = (function () {
    function init(config) {
        const relatedPopups = window.ArborisRelatedPopups;
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineFormsets = window.ArborisInlineFormsets;
        const personRules = window.ArborisPersonRules;
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;

        if (!relatedPopups || !collapsible || !tabs || !inlineFormsets || !personRules || !familyLinkedAddress) {
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

        function syncSexFromRelazioneFamiliare() {
            const relazioneSelect = document.getElementById("id_relazione_familiare");
            const sessoSelect = document.getElementById("id_sesso");

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

            if (editFamigliaBtn && famigliaSelect) editFamigliaBtn.disabled = !famigliaSelect.value;
            refreshRelazioneButtons();
            refreshIndirizzoButtons();
        }

        function wireInlineRelatedButtons(container) {
            const routes = window.ArborisRelatedEntityRoutes;
            if (!routes) {
                console.error("ArborisRelatedEntityRoutes non disponibile.");
                return;
            }
            routes.wireInlineRelatedButtons(container, {
                openRelatedPopup: relatedPopups.openRelatedPopup.bind(relatedPopups),
                onRefresh(relatedType, select) {
                    if (relatedType === "indirizzo" && select && select.closest("#studenti-table")) {
                        familyLinkedAddress.refreshInlineAddressHelp(select, studentiInlineAddressConfig);
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

        function getFamiliareSubformRow(row) {
            const subformRow = row.nextElementSibling;
            if (subformRow && subformRow.classList.contains("inline-subform-row")) {
                return subformRow;
            }
            return null;
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
            if (!nomeInput || nomeInput.dataset.familiareSexBound === "1") {
                return;
            }
            nomeInput.dataset.familiareSexBound = "1";
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

        function syncFamiliareStudenteInlineDefaults() {
            if (!document.getElementById("studenti-table")) {
                return;
            }
            familyLinkedAddress.syncInlineRows("#studenti-table tbody .inline-form-row", studentiInlineDefaultsConfig);
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

        function prepareExistingStudentiEmptyRows() {
            if (!document.getElementById("studenti-table")) {
                return;
            }
            inlineFormsets.prepareExistingEmptyRows("studenti-table", {
                companionClasses: ["inline-subform-row"],
                includeCompanionRowsInData: true,
                ignoreSelects: true,
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

        function removeInlineRow(button) {
            if (inlineFormsets.removeInlineRow(button, { companionClasses: ["inline-subform-row"] })) {
                refreshTabCounts();
            }
        }

        function prepareExistingEmptyRows(tableId) {
            inlineFormsets.prepareExistingEmptyRows(tableId, {
                companionClasses: [],
            });
        }

        function addInlineForm(prefix) {
            if (window.familiareViewMode && !window.familiareViewMode.isEditing()) {
                window.familiareViewMode.setInlineEditing(true);
            }

            const companionClasses = prefix === "studenti" ? ["inline-subform-row"] : [];
            const mounted = inlineFormsets.mountInlineForm(prefix, {
                companionClasses: companionClasses,
                enableInputs: true,
                onReady: function (state) {
                    const row = state.row;
                    wireInlineRelatedButtons(row);
                    if (prefix === "studenti") {
                        initSearchableSelects(row);
                        const subformRow = state.companionRows[0] || getFamiliareSubformRow(row);
                        if (subformRow) {
                            initSearchableSelects(subformRow);
                            initCodiceFiscale(subformRow);
                        }
                        familyLinkedAddress.bindInlineAddressTracking(row, studentiInlineAddressTrackingConfig);
                        initCodiceFiscale(row);
                        bindStudenteInlineSex(row);
                        syncFamiliareStudenteInlineDefaults();
                    }
                },
                focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
            });

            if (!mounted) {
                return;
            }

            activatePanelIfPresent(`tab-${prefix}`);
            refreshTabCounts();
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
        let refreshRelazioneButtons = function () {};
        let refreshIndirizzoButtons = function () {};

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

        const famRoutes = window.ArborisRelatedEntityRoutes;

        if (relazioneSelect && famRoutes) {
            const relazioneCrud = famRoutes.wireCrudButtons({
                select: relazioneSelect,
                relatedType: "relazione_familiare",
                addBtn: addRelazioneBtn,
                editBtn: editRelazioneBtn,
                deleteBtn: deleteRelazioneBtn,
                openRelatedPopup: relatedPopups.openRelatedPopup,
            });
            refreshRelazioneButtons = relazioneCrud.refresh;
        }

        if (indirizzoSelect && famRoutes) {
            const indirizzoCrud = famRoutes.wireCrudButtons({
                select: indirizzoSelect,
                relatedType: "indirizzo",
                addBtn: addIndirizzoBtn,
                editBtn: editIndirizzoBtn,
                deleteBtn: deleteIndirizzoBtn,
                openRelatedPopup: relatedPopups.openRelatedPopup,
            });
            refreshIndirizzoButtons = indirizzoCrud.refresh;
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
        prepareExistingStudentiEmptyRows();
        tabs.bindTabButtons(getFamiliareTabStorageKey());
        collapsible.initCollapsibleSections(document);
        wireInlineRelatedButtons(document);
        document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
            familyLinkedAddress.bindInlineAddressTracking(row, studentiInlineAddressTrackingConfig);
        });
        bindAllStudenteInlineSex();
        tabs.restoreActiveTab(getFamiliareTabStorageKey());
        syncInheritedAddressFromFamiglia();
        syncSexFromRelazioneFamiliare();
        syncFamiliareStudenteInlineDefaults();
        updateMainButtons();
        refreshAddressHelp();
        refreshTabCounts();
    }

    return {
        init,
    };
})();
