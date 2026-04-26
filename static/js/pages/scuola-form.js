window.ArborisScuolaForm = (function () {
    let refreshLockedTabsHandler = function () {};

    function init(config) {
        const relatedPopups = window.ArborisRelatedPopups;
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineTabs = window.ArborisInlineTabs;

        if (!relatedPopups || !collapsible || !tabs || !inlineTabs) {
            console.error("Arboris core JS non caricato correttamente.");
            return;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        const targetInputId = "scuola-inline-target";
        const inlineLockContainerId = "scuola-inline-lock-container";
        const formId = "scuola-detail-form";
        const inlineEditButtonId = "enable-inline-edit-scuola-btn";

        function getScuolaTabStorageKey() {
            return "arboris-scuola-form-active-tab-v2-" + (config.scuolaId || "new");
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
                    return window.scuolaViewMode;
                },
            });
        }

        const refreshLockedTabs = inlineTabs.createScuolaRefreshLockedTabs({
            formId: formId,
            inlineLockContainerId: inlineLockContainerId,
            targetInputId: targetInputId,
            getViewMode: function () {
                return window.scuolaViewMode;
            },
            inlineEditButtonId: inlineEditButtonId,
        });

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
            const routes = window.ArborisRelatedEntityRoutes;
            if (!routes) {
                console.error("ArborisRelatedEntityRoutes non disponibile.");
                return;
            }
            const targetInputName = select.name;

            if (mode === "add") {
                const cfg = routes.buildCrudUrls("indirizzo", null, targetInputName);
                if (cfg && cfg.addUrl) {
                    relatedPopups.openRelatedPopup(cfg.addUrl);
                }
                return;
            }

            if (!select.value) return;

            const cfg = routes.buildCrudUrls("indirizzo", select.value, targetInputName);
            if (mode === "edit" && cfg && cfg.editUrl) {
                relatedPopups.openRelatedPopup(cfg.editUrl);
            }
            if (mode === "delete" && cfg && cfg.deleteUrl) {
                relatedPopups.openRelatedPopup(cfg.deleteUrl);
            }
        }

        function countActiveRows(tableId) {
            let count = 0;
            document.querySelectorAll("#" + tableId + " tbody .inline-form-row").forEach(function (row) {
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

            for (let i = 0; i < fields.length; i++) {
                const field = fields[i];
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
            document.querySelectorAll("#" + tableId + " tbody .inline-form-row").forEach(function (row) {
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

            map.forEach(function (item) {
                const button = document.querySelector('[data-tab-target="' + item.tab + '"]');
                if (button) {
                    button.textContent = item.label + " (" + countActiveRows(item.table) + ")";
                }
            });
        }

        function bindDeleteCheckboxCounters() {
            document
                .querySelectorAll(
                    '#socials-table input[type="checkbox"][name$="-DELETE"], #telefoni-table input[type="checkbox"][name$="-DELETE"], #email-table input[type="checkbox"][name$="-DELETE"]'
                )
                .forEach(function (input) {
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
            updateInlineEditButtonLabel("tab-" + prefix);

            const hiddenRow = document.querySelector("#" + prefix + "-table tbody .inline-form-row.inline-empty-row.is-hidden");
            if (hiddenRow) {
                hiddenRow.classList.remove("is-hidden");
                hiddenRow.classList.remove("inline-empty-row");

                const firstInput = hiddenRow.querySelector(
                    "input[type='text'], input[type='url'], input[type='number'], input[type='email']"
                );
                if (firstInput) firstInput.focus();

                tabs.activateTab("tab-" + prefix, getScuolaTabStorageKey());
                refreshTabCounts();
                return;
            }

            const totalForms = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
            const currentIndex = parseInt(totalForms.value, 10);

            const template = document.getElementById(prefix + "-empty-form-template").innerHTML;
            const newRowHtml = template.replace(/__prefix__/g, currentIndex);

            const tbody = document.querySelector("#" + prefix + "-table tbody");
            tbody.insertAdjacentHTML("beforeend", newRowHtml);
            totalForms.value = currentIndex + 1;

            const newRow = tbody.lastElementChild;
            if (newRow) {
                const firstInput = newRow.querySelector(
                    "input[type='text'], input[type='url'], input[type='number'], input[type='email']"
                );
                if (firstInput) firstInput.focus();
            }

            bindDeleteCheckboxCounters();
            tabs.activateTab("tab-" + prefix, getScuolaTabStorageKey());
            refreshLockedTabs();
            refreshTabCounts();
        }

        window.removeInlineRow = removeInlineRow;
        window.addInlineForm = addInlineForm;

        const checkboxOperativo = document.getElementById("id_indirizzo_operativo_diverso");
        const legale = document.getElementById("id_indirizzo_sede_legale");
        const operativo = document.getElementById("id_indirizzo_operativo");
        const inlineLockRoot = document.getElementById(inlineLockContainerId);

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
        (inlineLockRoot || document).querySelectorAll(".tab-btn[data-tab-target]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                setInlineTarget(btn.dataset.tabTarget);
                updateInlineEditButtonLabel(btn.dataset.tabTarget);
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
        init: init,
        refreshLockedTabs: function () {
            refreshLockedTabsHandler();
        },
    };
})();
