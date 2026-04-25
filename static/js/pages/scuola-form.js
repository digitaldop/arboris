window.ArborisScuolaForm = (function () {
    let refreshLockedTabsHandler = function () {};

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

        function getScuolaTabStorageKey() {
            return `arboris-scuola-form-active-tab-v2-${config.scuolaId || "new"}`;
        }

        function setInlineTarget(prefixOrTabId) {
            const input = document.getElementById("scuola-inline-target");
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

        function updateInlineEditButtonLabel(tabId) {
            const button = document.getElementById("enable-inline-edit-scuola-btn");
            if (!button) {
                return;
            }
            if (
                window.scuolaViewMode &&
                typeof window.scuolaViewMode.isInlineEditing === "function" &&
                window.scuolaViewMode.isInlineEditing()
            ) {
                return;
            }

            const root = document.getElementById("scuola-inline-lock-container");
            const tabBtn = root && tabId ? root.querySelector(`.tab-btn[data-tab-target="${tabId}"]`) : null;
            const tabTitle = tabTitleForInlineEditLabel(tabBtn);

            button.textContent = tabTitle ? `Modifica ${tabTitle}` : "Modifica";
        }

        function getPanelFields(panel) {
            if (!panel) {
                return [];
            }

            return Array.from(panel.querySelectorAll("input, textarea, select")).filter(field => field.type !== "hidden");
        }

        function lockPanelFields(fields, keepSubmittedWhenLocked) {
            fields.forEach(field => {
                if (field.closest(".inline-empty-row.is-hidden")) {
                    field.disabled = true;
                    field.readOnly = true;
                    return;
                }

                const tag = field.tagName.toLowerCase();
                const type = (field.type || "").toLowerCase();
                const lockByDisable = tag === "select" || type === "checkbox" || type === "radio" || type === "file";

                field.classList.remove("submit-safe-locked");
                field.removeAttribute("aria-disabled");
                field.removeAttribute("tabindex");

                if (lockByDisable) {
                    if (keepSubmittedWhenLocked) {
                        field.disabled = false;
                        field.classList.add("submit-safe-locked");
                        field.setAttribute("aria-disabled", "true");
                        field.setAttribute("tabindex", "-1");
                    } else {
                        field.disabled = true;
                    }
                } else {
                    field.readOnly = true;
                }
            });
        }

        function unlockPanelFields(fields) {
            fields.forEach(field => {
                if (field.closest(".inline-empty-row.is-hidden")) {
                    field.disabled = true;
                    field.readOnly = true;
                    return;
                }

                field.classList.remove("submit-safe-locked");
                field.removeAttribute("aria-disabled");
                field.removeAttribute("tabindex");
                field.disabled = false;
                field.readOnly = false;
            });
        }

        function refreshLockedTabs() {
            const form = document.getElementById("scuola-detail-form");
            const panels = document.querySelectorAll("#scuola-inline-lock-container .tab-panel[data-inline-scope]");
            const input = document.getElementById("scuola-inline-target");
            const target = input ? input.value : "";
            const isEditing = Boolean(
                window.scuolaViewMode &&
                typeof window.scuolaViewMode.isEditing === "function" &&
                window.scuolaViewMode.isEditing()
            );
            const isInlineEditing = Boolean(
                window.scuolaViewMode &&
                typeof window.scuolaViewMode.isInlineEditing === "function" &&
                window.scuolaViewMode.isInlineEditing()
            );
            const lockMessage = "Non è possibile cambiare tab finché non si salvano o annullano le modifiche correnti.";

            if (form) {
                if (isEditing && target) {
                    form.dataset.inlineEditTarget = target;
                } else {
                    delete form.dataset.inlineEditTarget;
                }
            }

            panels.forEach(panel => {
                const isTarget = isInlineEditing && panel.dataset.inlineScope === target;
                panel.classList.toggle("is-inline-edit-target", isTarget);

                const panelFields = getPanelFields(panel);
                if (isInlineEditing) {
                    if (isTarget) {
                        unlockPanelFields(panelFields);
                    } else {
                        lockPanelFields(panelFields, true);
                    }
                } else if (isEditing) {
                    unlockPanelFields(panelFields);
                } else {
                    lockPanelFields(panelFields, false);
                }
            });

            document.querySelectorAll("#scuola-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
                const btnTarget = (btn.dataset.tabTarget || "").replace(/^tab-/, "");
                const locked = isInlineEditing && target && btnTarget !== target;
                btn.classList.toggle("is-tab-locked", locked);

                if (locked) {
                    btn.setAttribute("data-tab-lock-message", lockMessage);
                } else {
                    btn.removeAttribute("data-tab-lock-message");
                }
            });

            if (!isInlineEditing) {
                const root = document.getElementById("scuola-inline-lock-container");
                const activeTab = root ? root.querySelector(".tab-btn.is-active") : null;
                if (activeTab && activeTab.dataset.tabTarget) {
                    updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
                }
            }
        }

        function isOperativoEnabled() {
            const checkbox = document.getElementById("id_indirizzo_operativo_diverso");
            return checkbox ? checkbox.checked : false;
        }

        function setDisabledState(element, disabled) {
            if (!element) return;
            element.disabled = disabled;
        }

        function updateAddressButtons() {
            const legale = document.getElementById("id_indirizzo_sede_legale");
            const operativo = document.getElementById("id_indirizzo_operativo");

            const editLegale = document.getElementById("edit-indirizzo-legale-btn");
            const deleteLegale = document.getElementById("delete-indirizzo-legale-btn");
            const addOperativo = document.getElementById("add-indirizzo-operativo-btn");
            const editOperativo = document.getElementById("edit-indirizzo-operativo-btn");
            const deleteOperativo = document.getElementById("delete-indirizzo-operativo-btn");
            const rowOperativo = document.getElementById("row-indirizzo-operativo");

            if (editLegale && legale) editLegale.disabled = !legale.value;
            if (deleteLegale && legale) deleteLegale.disabled = !legale.value;

            const operativoEnabled = isOperativoEnabled();

            if (rowOperativo) {
                rowOperativo.classList.toggle("is-muted-row", !operativoEnabled);
            }

            setDisabledState(operativo, !operativoEnabled);
            setDisabledState(addOperativo, !operativoEnabled);
            setDisabledState(editOperativo, !operativoEnabled || !operativo.value);
            setDisabledState(deleteOperativo, !operativoEnabled || !operativo.value);

            if (!operativoEnabled && operativo) {
                operativo.value = "";
            }
        }

        function openAddressPopup(mode, select) {
            if (!select || select.disabled) return;
            const target = encodeURIComponent(select.name);

            if (mode === "add") {
                relatedPopups.openRelatedPopup(`${config.urls.creaIndirizzo}?popup=1&target_input_name=${target}`);
                return;
            }

            if (!select.value) return;

            if (mode === "edit") {
                relatedPopups.openRelatedPopup(`${config.urls.modificaIndirizzoBase}${select.value}/modifica/?popup=1&target_input_name=${target}`);
            }

            if (mode === "delete") {
                relatedPopups.openRelatedPopup(`${config.urls.eliminaIndirizzoBase}${select.value}/elimina/?popup=1&target_input_name=${target}`);
            }
        }

        function countActiveRows(tableId) {
            let count = 0;
            document.querySelectorAll(`#${tableId} tbody .inline-form-row`).forEach(row => {
                if (row.classList.contains("inline-empty-row")) {
                    return;
                }
                const deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
                if (deleteCheckbox && deleteCheckbox.checked) {
                    return;
                }
                const hiddenIdInput = row.querySelector('input[type="hidden"][name$="-id"]');
                if (!hiddenIdInput || !hiddenIdInput.value) {
                    return;
                }
                count += 1;
            });
            return count;
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

        function refreshTabCounts() {
            const map = [
                { tab: "tab-socials", table: "socials-table", label: "Social" },
                { tab: "tab-telefoni", table: "telefoni-table", label: "Telefoni" },
                { tab: "tab-email", table: "email-table", label: "Email" },
            ];

            map.forEach(item => {
                const button = document.querySelector(`[data-tab-target="${item.tab}"]`);
                if (button) {
                    button.textContent = `${item.label} (${countActiveRows(item.table)})`;
                }
            });
        }

        function bindDeleteCheckboxCounters() {
            document.querySelectorAll(
                '#socials-table input[type="checkbox"][name$="-DELETE"], #telefoni-table input[type="checkbox"][name$="-DELETE"], #email-table input[type="checkbox"][name$="-DELETE"]'
            ).forEach(input => {
                if (input.dataset.countBound === "1") return;
                input.dataset.countBound = "1";
                input.addEventListener("change", refreshTabCounts);
            });
        }

        function removeInlineRow(button) {
            const row = button.closest("tr");
            if (row) {
                row.remove();
                refreshTabCounts();
            }
        }

        function addInlineForm(prefix) {
            if (window.scuolaViewMode && !window.scuolaViewMode.isEditing()) {
                window.scuolaViewMode.setInlineEditing(true);
            }

            setInlineTarget(prefix);
            updateInlineEditButtonLabel(`tab-${prefix}`);

            const hiddenRow = document.querySelector(`#${prefix}-table tbody .inline-form-row.inline-empty-row.is-hidden`);
            if (hiddenRow) {
                hiddenRow.classList.remove("is-hidden");
                hiddenRow.classList.remove("inline-empty-row");

                const firstInput = hiddenRow.querySelector("input[type='text'], input[type='url'], input[type='number'], input[type='email']");
                if (firstInput) firstInput.focus();

                tabs.activateTab(`tab-${prefix}`, getScuolaTabStorageKey());
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
                const firstInput = newRow.querySelector("input[type='text'], input[type='url'], input[type='number'], input[type='email']");
                if (firstInput) firstInput.focus();
            }

            bindDeleteCheckboxCounters();
            tabs.activateTab(`tab-${prefix}`, getScuolaTabStorageKey());
            refreshLockedTabs();
            refreshTabCounts();
        }

        window.removeInlineRow = removeInlineRow;
        window.addInlineForm = addInlineForm;

        const checkboxOperativo = document.getElementById("id_indirizzo_operativo_diverso");
        const legale = document.getElementById("id_indirizzo_sede_legale");
        const operativo = document.getElementById("id_indirizzo_operativo");
        const inlineLockRoot = document.getElementById("scuola-inline-lock-container");

        const addLegale = document.getElementById("add-indirizzo-legale-btn");
        const editLegale = document.getElementById("edit-indirizzo-legale-btn");
        const deleteLegale = document.getElementById("delete-indirizzo-legale-btn");
        const addOperativo = document.getElementById("add-indirizzo-operativo-btn");
        const editOperativo = document.getElementById("edit-indirizzo-operativo-btn");
        const deleteOperativo = document.getElementById("delete-indirizzo-operativo-btn");

        if (addLegale) addLegale.addEventListener("click", function () { openAddressPopup("add", legale); });
        if (editLegale) editLegale.addEventListener("click", function () { openAddressPopup("edit", legale); });
        if (deleteLegale) deleteLegale.addEventListener("click", function () { openAddressPopup("delete", legale); });
        if (addOperativo) addOperativo.addEventListener("click", function () { openAddressPopup("add", operativo); });
        if (editOperativo) editOperativo.addEventListener("click", function () { openAddressPopup("edit", operativo); });
        if (deleteOperativo) deleteOperativo.addEventListener("click", function () { openAddressPopup("delete", operativo); });

        if (checkboxOperativo) checkboxOperativo.addEventListener("change", updateAddressButtons);
        if (legale) legale.addEventListener("change", updateAddressButtons);
        if (operativo) operativo.addEventListener("change", updateAddressButtons);

        prepareExistingEmptyRows("socials-table");
        prepareExistingEmptyRows("telefoni-table");
        prepareExistingEmptyRows("email-table");
        tabs.bindTabButtons(getScuolaTabStorageKey(), inlineLockRoot || document);
        (inlineLockRoot || document).querySelectorAll(".tab-btn[data-tab-target]").forEach(btn => {
            btn.addEventListener("arboris:before-tab-activate", function (event) {
                if (btn.classList.contains("is-tab-locked")) {
                    event.preventDefault();
                }
            });

            btn.addEventListener("click", function () {
                const isInlineEditing = Boolean(
                    window.scuolaViewMode &&
                    typeof window.scuolaViewMode.isInlineEditing === "function" &&
                    window.scuolaViewMode.isInlineEditing()
                );

                if (!isInlineEditing) {
                    setInlineTarget(btn.dataset.tabTarget);
                    updateInlineEditButtonLabel(btn.dataset.tabTarget);
                }

                refreshLockedTabs();
            });
        });
        tabs.restoreActiveTab(getScuolaTabStorageKey());
        const activeTab = inlineLockRoot ? inlineLockRoot.querySelector(".tab-btn.is-active") : document.querySelector(".tab-btn.is-active");
        if (activeTab) {
            setInlineTarget(activeTab.dataset.tabTarget);
            updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
        }
        collapsible.initCollapsibleSections(document);
        bindDeleteCheckboxCounters();
        updateAddressButtons();
        refreshTabCounts();
        refreshLockedTabs();
        refreshLockedTabsHandler = refreshLockedTabs;
    }

    return {
        init,
        refreshLockedTabs: function () {
            refreshLockedTabsHandler();
        },
    };
})();
