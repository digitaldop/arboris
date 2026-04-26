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
                        refreshStudenteInlineAddressHelp(select);
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

        function refreshStudenteInlineAddressHelp(select) {
            const wrapperCell = select.closest("td");
            if (!wrapperCell) {
                return;
            }
            const help = wrapperCell.querySelector('[data-role="address-help"]');
            if (!help) {
                return;
            }
            const principaleId = readFamiliareStudentiInlineDefaults().indirizzo_principale_id || "";
            const label = getStudenteInlineFamigliaIndirizzoPrincipaleLabel();
            if (select.value && principaleId && select.value === principaleId && label) {
                help.textContent = `Indirizzo famiglia: ${label}`;
            } else if (select.value) {
                help.textContent = "Indirizzo specifico";
            } else if (label) {
                help.textContent = `Erediterà: ${label}`;
            } else {
                help.textContent = "Se lasci vuoto, verrà usato l'indirizzo principale della famiglia";
            }
        }

        function markInheritedAddress(select, enabled) {
            if (!select) {
                return;
            }
            if (enabled) {
                select.dataset.inheritedAddress = "1";
            } else {
                delete select.dataset.inheritedAddress;
            }
        }

        function syncStudenteRowAddressToFamiglia(select, famigliaIndirizzoId) {
            if (!select) {
                return;
            }
            const isInherited = select.dataset.inheritedAddress === "1";
            const previousValue = select.value || "";
            if (!famigliaIndirizzoId) {
                if (isInherited) {
                    select.value = "";
                    markInheritedAddress(select, false);
                    if (previousValue) {
                        select.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }
                refreshStudenteInlineAddressHelp(select);
                return;
            }
            if (!select.value || isInherited) {
                select.value = famigliaIndirizzoId;
                markInheritedAddress(select, true);
                if (select.value !== previousValue) {
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }
            refreshStudenteInlineAddressHelp(select);
        }

        function bindStudenteIndirizzoTracking(row) {
            const select = row.querySelector('select[name$="-indirizzo"]');
            if (!select || select.dataset.familiareStudenteAddrBound === "1") {
                return;
            }
            select.dataset.familiareStudenteAddrBound = "1";
            select.addEventListener("change", function () {
                const fid = readFamiliareStudentiInlineDefaults().indirizzo_principale_id || "";
                markInheritedAddress(select, Boolean(fid && select.value === fid));
                refreshStudenteInlineAddressHelp(select);
            });
        }

        function getFamiliareSubformRow(row) {
            const subformRow = row.nextElementSibling;
            if (subformRow && subformRow.classList.contains("inline-subform-row")) {
                return subformRow;
            }
            return null;
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
            const commonMaleEndingInA = ["andrea", "luca", "nicola", "mattia", "elia", "tobia", "enea", "gianluca"];
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
            const defaults = readFamiliareStudentiInlineDefaults();
            const famigliaIndirizzoId = defaults.indirizzo_principale_id || "";
            const famigliaCognome = (defaults.cognome_famiglia || "").trim();
            document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }
                const hiddenIdInput = row.querySelector('input[type="hidden"][name$="-id"]');
                const cognomeInput = row.querySelector('input[name$="-cognome"]');
                const indirizzoSelect = row.querySelector('select[name$="-indirizzo"]');
                const attivoCheckbox = row.querySelector('input[type="checkbox"][name$="-attivo"]');
                const isPersisted = Boolean(hiddenIdInput && hiddenIdInput.value);
                if (!isPersisted && cognomeInput) {
                    cognomeInput.value = famigliaCognome;
                }
                if (indirizzoSelect) {
                    if (!isPersisted && !indirizzoSelect.value) {
                        markInheritedAddress(indirizzoSelect, true);
                    }
                    syncStudenteRowAddressToFamiglia(indirizzoSelect, famigliaIndirizzoId);
                }
                if (!isPersisted && attivoCheckbox) {
                    attivoCheckbox.checked = true;
                }
            });
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

        function rowHasStudentiVisibleErrors(row) {
            let nextRow = row.nextElementSibling;
            if (nextRow && nextRow.classList.contains("inline-subform-row")) {
                nextRow = nextRow.nextElementSibling;
            }
            return Boolean(nextRow && nextRow.classList.contains("inline-errors-row"));
        }

        function rowHasUserDataIncludingSubform(row) {
            const subformRow = getFamiliareSubformRow(row);
            const fields = row.querySelectorAll("input, textarea, select");
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

        function prepareExistingStudentiEmptyRows() {
            const table = document.getElementById("studenti-table");
            if (!table) {
                return;
            }
            table.querySelectorAll("tbody .inline-form-row").forEach(row => {
                if (isRowPersisted(row) || rowHasStudentiVisibleErrors(row) || rowHasUserDataIncludingSubform(row)) {
                    return;
                }
                row.classList.add("inline-empty-row", "is-hidden");
                const sub = row.nextElementSibling;
                if (sub && sub.classList.contains("inline-subform-row")) {
                    sub.classList.add("inline-empty-row", "is-hidden");
                }
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
            const studentiHeading = document.getElementById("familiare-studenti-heading");
            if (studentiHeading && document.getElementById("studenti-table")) {
                const n = countPersistedRows("studenti-table");
                const label = studentiHeading.dataset.baseLabel || studentiHeading.textContent.replace(/\s*\(\d+\)\s*$/, "").trim();
                studentiHeading.dataset.baseLabel = label;
                studentiHeading.textContent = `${label} (${n})`;
            }
        }

        function removeInlineRow(button) {
            const row = button.closest("tr");
            if (!row) {
                return;
            }
            let next = row.nextElementSibling;
            if (next && next.classList.contains("inline-subform-row")) {
                const sub = next;
                next = next.nextElementSibling;
                sub.remove();
            }
            if (next && next.classList.contains("inline-errors-row")) {
                next.remove();
            }
            row.remove();
            refreshTabCounts();
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

                const hiddenSub = hiddenRow.nextElementSibling;
                if (prefix === "studenti" && hiddenSub && hiddenSub.classList.contains("inline-subform-row")) {
                    hiddenSub.classList.remove("is-hidden");
                    hiddenSub.classList.remove("inline-empty-row");
                }

                wireInlineRelatedButtons(hiddenRow);
                if (prefix === "studenti") {
                    initSearchableSelects(hiddenRow);
                    const sub = getFamiliareSubformRow(hiddenRow);
                    if (sub) {
                        initSearchableSelects(sub);
                        initCodiceFiscale(sub);
                    }
                    bindStudenteIndirizzoTracking(hiddenRow);
                    initCodiceFiscale(hiddenRow);
                    bindStudenteInlineSex(hiddenRow);
                    syncFamiliareStudenteInlineDefaults();
                }

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

            let newRow = tbody.lastElementChild;
            if (newRow && newRow.classList.contains("inline-subform-row")) {
                newRow = newRow.previousElementSibling;
            }
            if (newRow) {
                wireInlineRelatedButtons(newRow);
                if (prefix === "studenti") {
                    initSearchableSelects(newRow);
                    const subformRow = getFamiliareSubformRow(newRow);
                    if (subformRow) {
                        initSearchableSelects(subformRow);
                        initCodiceFiscale(subformRow);
                    }
                    bindStudenteIndirizzoTracking(newRow);
                    initCodiceFiscale(newRow);
                    bindStudenteInlineSex(newRow);
                    syncFamiliareStudenteInlineDefaults();
                }

                const firstInput = newRow.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea");
                if (firstInput) firstInput.focus();
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

        if (addRelazioneBtn && relazioneSelect && famRoutes) {
            addRelazioneBtn.addEventListener("click", function () {
                const cfg = famRoutes.buildCrudUrls("relazione_familiare", null, relazioneSelect.name);
                if (cfg && cfg.addUrl) {
                    relatedPopups.openRelatedPopup(cfg.addUrl);
                }
            });
        }

        if (editRelazioneBtn && relazioneSelect && famRoutes) {
            editRelazioneBtn.addEventListener("click", function () {
                if (!relazioneSelect.value) {
                    return;
                }
                const cfg = famRoutes.buildCrudUrls("relazione_familiare", relazioneSelect.value, relazioneSelect.name);
                if (cfg && cfg.editUrl) {
                    relatedPopups.openRelatedPopup(cfg.editUrl);
                }
            });
        }

        if (deleteRelazioneBtn && relazioneSelect && famRoutes) {
            deleteRelazioneBtn.addEventListener("click", function () {
                if (!relazioneSelect.value) {
                    return;
                }
                const cfg = famRoutes.buildCrudUrls("relazione_familiare", relazioneSelect.value, relazioneSelect.name);
                if (cfg && cfg.deleteUrl) {
                    relatedPopups.openRelatedPopup(cfg.deleteUrl);
                }
            });
        }

        if (addIndirizzoBtn && indirizzoSelect && famRoutes) {
            addIndirizzoBtn.addEventListener("click", function () {
                const cfg = famRoutes.buildCrudUrls("indirizzo", null, indirizzoSelect.name);
                if (cfg && cfg.addUrl) {
                    relatedPopups.openRelatedPopup(cfg.addUrl);
                }
            });
        }

        if (editIndirizzoBtn && indirizzoSelect && famRoutes) {
            editIndirizzoBtn.addEventListener("click", function () {
                if (!indirizzoSelect.value) {
                    return;
                }
                const cfg = famRoutes.buildCrudUrls("indirizzo", indirizzoSelect.value, indirizzoSelect.name);
                if (cfg && cfg.editUrl) {
                    relatedPopups.openRelatedPopup(cfg.editUrl);
                }
            });
        }

        if (deleteIndirizzoBtn && indirizzoSelect && famRoutes) {
            deleteIndirizzoBtn.addEventListener("click", function () {
                if (!indirizzoSelect.value) {
                    return;
                }
                const cfg = famRoutes.buildCrudUrls("indirizzo", indirizzoSelect.value, indirizzoSelect.name);
                if (cfg && cfg.deleteUrl) {
                    relatedPopups.openRelatedPopup(cfg.deleteUrl);
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
        prepareExistingStudentiEmptyRows();
        tabs.bindTabButtons(getFamiliareTabStorageKey());
        collapsible.initCollapsibleSections(document);
        wireInlineRelatedButtons(document);
        document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
            bindStudenteIndirizzoTracking(row);
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
