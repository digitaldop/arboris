window.ArborisStudenteForm = (function () {
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

        function getStudenteTabStorageKey() {
            return `arboris-studente-form-active-tab-v2-${config.studenteId || "new"}`;
        }

        const studenteInlineRoot = () => document.getElementById("studente-inline-lock-container");

        const targetInputId = "studente-inline-target";
        const inlineLockContainerId = "studente-inline-lock-container";
        const inlineEditButtonId = "enable-inline-edit-studente-btn";

        function setInlineTarget(prefixOrTabId) {
            inlineTabs.setInlineTargetValue(targetInputId, prefixOrTabId);
        }

        function refreshInlineEditScope() {
            refreshLockedTabs();
        }

        refreshInlineEditScopeHandler = refreshInlineEditScope;

        function updateInlineEditButtonLabel(tabId) {
            inlineTabs.updateDefaultInlineEditButtonLabel({
                buttonId: inlineEditButtonId,
                containerId: inlineLockContainerId,
                tabId: tabId,
                getViewMode: function () {
                    return window.studenteViewMode;
                },
            });
        }

        const refreshLockedTabs = inlineTabs.createRefreshLockedTabs({
            formId: "studente-detail-form",
            inlineLockContainerId: inlineLockContainerId,
            targetInputId: targetInputId,
            getViewMode: function () {
                return window.studenteViewMode;
            },
            inlineEditButtonId: inlineEditButtonId,
            onAfterRefresh: function () {
                const form = document.getElementById("studente-detail-form");
                const targetInput = document.getElementById(targetInputId);
                const target = targetInput ? targetInput.value : "";
                const isInlineEditing = Boolean(
                    window.studenteViewMode &&
                    typeof window.studenteViewMode.isInlineEditing === "function" &&
                    window.studenteViewMode.isInlineEditing()
                );

                if (form) {
                    form.classList.toggle("is-inline-iscrizioni-layout", isInlineEditing && target === "iscrizioni");
                }
            },
        });

        function bindStandaloneSexFromNome() {
            personRules.bindSexFromFirstName({
                nameInput: document.getElementById("id_nome"),
                sexSelect: document.getElementById("id_sesso"),
                bindFlag: "sexBound",
            });
        }

        function updateMainButtons() {
            refreshFamigliaNavigation();
            refreshIndirizzoButtons();
        }

        function wireInlineRelatedButtons(container) {
            formTools.wireInlineRelatedButtons(container, {
                routes: routes,
                relatedPopups: relatedPopups,
            });
        }

        function refreshTabCounts() {
            const iscrizioniRows = inlineFormsets.countPersistedRows("iscrizioni-table");
            const tabIscrizioni = document.querySelector('[data-tab-target="tab-iscrizioni"]');
            const documentiRows = inlineFormsets.countPersistedRows("documenti-table");
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

        function createInlineManager(prefix, options) {
            return inlineFormsets.createManager({
                prefix: prefix,
                prepareOptions: options && options.prepareOptions ? options.prepareOptions : {},
                mountOptions: options && options.mountOptions ? options.mountOptions : {},
                removeOptions: options && options.removeOptions ? options.removeOptions : {},
            });
        }

        const inlineManagers = {
            iscrizioni: createInlineManager("iscrizioni", {
                prepareOptions: {
                    companionClasses: ["inline-details-row"],
                },
                mountOptions: {
                    companionClasses: ["inline-details-row"],
                    enableInputs: true,
                    onReady: function (state) {
                        wireInlineRelatedButtons(state.row);
                        wireIscrizioneRow(state.row);
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-details-row"],
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

        function addManagedInlineForm(prefix) {
            const manager = inlineManagers[prefix];
            if (!manager) {
                return;
            }

            if (window.studenteViewMode && !window.studenteViewMode.isEditing()) {
                window.studenteViewMode.setInlineEditing(true);
            }

            setInlineTarget(prefix);
            refreshInlineEditScope();
            updateInlineEditButtonLabel(`tab-${prefix}`);

            const mounted = manager.add();

            if (!mounted) {
                return;
            }

            tabs.activateTab(`tab-${prefix}`, getStudenteTabStorageKey());
            refreshInlineEditScope();
            refreshTabCounts();
        }

        const famigliaSelect = document.getElementById("id_famiglia");
        const indirizzoSelect = document.getElementById("id_indirizzo");

        const addFamigliaBtn = document.getElementById("add-famiglia-btn");
        const editFamigliaBtn = document.getElementById("edit-famiglia-btn");
        let refreshFamigliaNavigation = function () {};

        const addIndirizzoBtn = document.getElementById("add-indirizzo-btn");
        const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
        const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");
        let refreshIndirizzoButtons = function () {};
        formTools.bindFamilyAddressController({
            familyLinkedAddress: familyLinkedAddress,
            familySelect: famigliaSelect,
            addressSelect: indirizzoSelect,
            surnameInput: document.getElementById("id_cognome"),
            helpElement: document.getElementById("studente-address-help"),
            fallbackLabelScriptId: "studente-famiglia-indirizzo-label",
            onRefreshButtons: updateMainButtons,
        });

        const famigliaNavigation = formTools.bindFamigliaNavigation({
            familySelect: famigliaSelect,
            addBtn: addFamigliaBtn,
            editBtn: editFamigliaBtn,
            createUrl: config.urls.creaFamiglia,
        });
        refreshFamigliaNavigation = famigliaNavigation.refresh;

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

        inlineManagers.iscrizioni.prepare();
        inlineManagers.documenti.prepare();
        document.querySelectorAll("#iscrizioni-table tbody .inline-form-row").forEach(wireIscrizioneRow);
        const inlineLockRoot = studenteInlineRoot();
        if (inlineLockRoot) {
            tabs.bindTabButtons(getStudenteTabStorageKey(), inlineLockRoot);
        }
        document.querySelectorAll("#studente-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
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
        if (window.ArborisPopupWindowTriggers) {
            ArborisPopupWindowTriggers.wire(document);
        }
        tabs.restoreActiveTab(getStudenteTabStorageKey());
        const activeTab = inlineLockRoot ? inlineLockRoot.querySelector(".tab-btn.is-active") : null;
        if (activeTab && activeTab.dataset.tabTarget) {
            setInlineTarget(activeTab.dataset.tabTarget);
            updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
        }
        refreshInlineEditScope();
        updateMainButtons();
        refreshTabCounts();
        bindRateRecalcForms();
        bindStandaloneSexFromNome();
    }

    return {
        init,
        refreshInlineEditScope: function () {
            refreshInlineEditScopeHandler();
        },
    };
})();
