/**
 * Comportamento condiviso per sezioni inline a tab (form dettaglio + _inline_target).
 * Le pagine (scuola, studente, …) forniscono id e riferimenti a ArborisViewMode.
 */
window.ArborisInlineTabs = (function () {
    function titleFromTabButtonText(tabButton) {
        if (!tabButton) {
            return "";
        }
        return tabButton.textContent.replace(/\s*\([^)]*\)\s*$/, "").replace(/\s+/g, " ").trim();
    }

    function inlineLabelFromTabButton(tabButton) {
        if (!tabButton) {
            return "";
        }
        const base = (tabButton.dataset.tabBaseLabel || "").trim();
        if (base) {
            return base;
        }
        return titleFromTabButtonText(tabButton);
    }

    function getPanelFields(panel) {
        if (!panel) {
            return [];
        }
        return Array.from(panel.querySelectorAll("input, textarea, select")).filter(function (field) {
            return field.type !== "hidden";
        });
    }

    function lockPanelFields(fields, keepSubmittedWhenLocked) {
        fields.forEach(function (field) {
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
        fields.forEach(function (field) {
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

    function setInlineTargetValue(targetInputId, prefixOrTabId) {
        const input = document.getElementById(targetInputId);
        if (!input || !prefixOrTabId) {
            return;
        }
        input.value = prefixOrTabId.replace(/^tab-/, "");
    }

    function clearTabButtonLockClasses(containerId) {
        const root = document.getElementById(containerId);
        if (!root) {
            return;
        }
        root.querySelectorAll(".tab-btn[data-tab-target]").forEach(function (btn) {
            btn.classList.remove("is-tab-locked");
            btn.removeAttribute("data-tab-lock-message");
        });
    }

    /**
     * @param {object} o
     * @param {string} o.formId
     * @param {string} o.inlineLockContainerId
     * @param {string} o.targetInputId
     * @param {() => { isEditing?: function, isInlineEditing?: function } | undefined} o.getViewMode
     * @param {string} o.inlineEditButtonId
     * @param {function} [o.onAfterRefresh] chiamata dopo l'aggiornamento pannelli
     */
    function createScuolaRefreshLockedTabs(o) {
        return function refreshLockedTabs() {
            const form = document.getElementById(o.formId);
            const panels = document.querySelectorAll("#" + o.inlineLockContainerId + " .tab-panel[data-inline-scope]");
            const input = document.getElementById(o.targetInputId);
            const target = input ? input.value : "";
            const vm = o.getViewMode && o.getViewMode();
            const isEditing = Boolean(vm && typeof vm.isEditing === "function" && vm.isEditing());
            const isInlineEditing = Boolean(vm && typeof vm.isInlineEditing === "function" && vm.isInlineEditing());

            if (form) {
                if (isEditing && target) {
                    form.dataset.inlineEditTarget = target;
                } else {
                    delete form.dataset.inlineEditTarget;
                }
            }

            panels.forEach(function (panel) {
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

            clearTabButtonLockClasses(o.inlineLockContainerId);

            if (!isInlineEditing) {
                const root = document.getElementById(o.inlineLockContainerId);
                const activeTab = root ? root.querySelector(".tab-btn.is-active") : null;
                if (activeTab && activeTab.dataset.tabTarget) {
                    updateDefaultInlineEditButtonLabel({
                        buttonId: o.inlineEditButtonId,
                        containerId: o.inlineLockContainerId,
                        tabId: activeTab.dataset.tabTarget,
                        getViewMode: o.getViewMode,
                    });
                }
            }
            if (typeof o.onAfterRefresh === "function") {
                o.onAfterRefresh();
            }
        };
    }

    function updateDefaultInlineEditButtonLabel(cfg) {
        const button = document.getElementById(cfg.buttonId);
        if (!button) {
            return;
        }
        const vm = cfg.getViewMode && cfg.getViewMode();
        if (vm && typeof vm.isInlineEditing === "function" && vm.isInlineEditing()) {
            return;
        }
        const root = document.getElementById(cfg.containerId);
        const tabBtn = root && cfg.tabId ? root.querySelector('.tab-btn[data-tab-target="' + cfg.tabId + '"]') : null;
        const tabTitle = inlineLabelFromTabButton(tabBtn);
        button.textContent = tabTitle ? "Modifica " + tabTitle : "Modifica";
    }

    return {
        titleFromTabButtonText: titleFromTabButtonText,
        inlineLabelFromTabButton: inlineLabelFromTabButton,
        getPanelFields: getPanelFields,
        lockPanelFields: lockPanelFields,
        unlockPanelFields: unlockPanelFields,
        setInlineTargetValue: setInlineTargetValue,
        clearTabButtonLockClasses: clearTabButtonLockClasses,
        createScuolaRefreshLockedTabs: createScuolaRefreshLockedTabs,
        updateDefaultInlineEditButtonLabel: updateDefaultInlineEditButtonLabel,
    };
})();
