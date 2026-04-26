window.ArborisScuolaForm = (function () {
    let refreshLockedTabsHandler = function () {};

    function init(config) {
        const relatedPopups = window.ArborisRelatedPopups;
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineTabs = window.ArborisInlineTabs;
        const inlineFormsets = window.ArborisInlineFormsets;

        if (!relatedPopups || !collapsible || !tabs || !inlineTabs || !inlineFormsets) {
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

        const refreshLockedTabs = inlineTabs.createRefreshLockedTabs({
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
            const rowOperativo = document.getElementById("row-indirizzo-operativo");

            const operativoEnabled = isOperativoEnabled();

            if (rowOperativo) {
                rowOperativo.classList.toggle("is-muted-row", !operativoEnabled);
            }

            setDisabledState(operativo, !operativoEnabled);

            if (!operativoEnabled && operativo) {
                operativo.value = "";
            }

            refreshLegaleButtons();
            refreshOperativoButtons();
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
                    button.textContent = item.label + " (" + inlineFormsets.countPersistedRows(item.table) + ")";
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
            if (inlineFormsets.removeInlineRow(button)) {
                refreshTabCounts();
            }
        }

        function addInlineForm(prefix) {
            if (window.scuolaViewMode && !window.scuolaViewMode.isEditing()) {
                window.scuolaViewMode.setInlineEditing(true);
            }

            setInlineTarget(prefix);
            updateInlineEditButtonLabel("tab-" + prefix);

            const mounted = inlineFormsets.mountInlineForm(prefix, {
                enableInputs: true,
                focusSelector: "input[type='text'], input[type='url'], input[type='number'], input[type='email']",
            });

            if (!mounted) {
                return;
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
        let refreshLegaleButtons = function () {};
        let refreshOperativoButtons = function () {};

        const relatedRoutes = window.ArborisRelatedEntityRoutes;
        if (!relatedRoutes) {
            console.error("ArborisRelatedEntityRoutes non disponibile.");
        }

        if (legale && relatedRoutes) {
            const legaleCrud = relatedRoutes.wireCrudButtons({
                select: legale,
                relatedType: "indirizzo",
                addBtn: addLegale,
                editBtn: editLegale,
                deleteBtn: deleteLegale,
                openRelatedPopup: relatedPopups.openRelatedPopup,
            });
            refreshLegaleButtons = legaleCrud.refresh;
        }

        if (operativo && relatedRoutes) {
            const operativoCrud = relatedRoutes.wireCrudButtons({
                select: operativo,
                relatedType: "indirizzo",
                addBtn: addOperativo,
                editBtn: editOperativo,
                deleteBtn: deleteOperativo,
                openRelatedPopup: relatedPopups.openRelatedPopup,
                isAddDisabled: function () {
                    return !isOperativoEnabled();
                },
                isEditDisabled: function (select, selectedId) {
                    return !isOperativoEnabled() || select.disabled || !selectedId;
                },
                isDeleteDisabled: function (select, selectedId) {
                    return !isOperativoEnabled() || select.disabled || !selectedId;
                },
            });
            refreshOperativoButtons = operativoCrud.refresh;
        }

        if (checkboxOperativo) checkboxOperativo.addEventListener("change", updateAddressButtons);
        if (legale) legale.addEventListener("change", updateAddressButtons);
        if (operativo) operativo.addEventListener("change", updateAddressButtons);

        inlineFormsets.prepareExistingEmptyRows("socials-table");
        inlineFormsets.prepareExistingEmptyRows("telefoni-table");
        inlineFormsets.prepareExistingEmptyRows("email-table");
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
