/**
 * Comportamento condiviso per sezioni inline a tab (form dettaglio + _inline_target).
 * Le pagine (scuola, studente, …) forniscono id e riferimenti a ArborisViewMode.
 */
window.ArborisInlineTabs = (function () {
    const DEFAULT_TAB_LOCK_MESSAGE = "Salva o annulla le modifiche della tab corrente prima di cambiare sezione.";

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

    function normalizeTabTarget(prefixOrTabId) {
        return (prefixOrTabId || "").replace(/^tab-/, "");
    }

    function isInlineEditing(getViewMode) {
        const vm = getViewMode && getViewMode();
        return Boolean(vm && typeof vm.isInlineEditing === "function" && vm.isInlineEditing());
    }

    function currentInlineTarget(targetInputId) {
        const input = document.getElementById(targetInputId);
        return normalizeTabTarget(input ? input.value : "");
    }

    function clearTabButtonLockClasses(containerId) {
        const root = document.getElementById(containerId);
        if (!root) {
            return;
        }
        root.querySelectorAll(".tab-btn[data-tab-target]").forEach(function (btn) {
            btn.classList.remove("is-tab-locked");
            btn.removeAttribute("data-tab-lock-message");
            btn.removeAttribute("title");
        });
    }

    function refreshTabButtonLocks(o) {
        const root = document.getElementById(o.containerId);
        if (!root) {
            return;
        }

        const activeTarget = currentInlineTarget(o.targetInputId);
        const locked = isInlineEditing(o.getViewMode);
        const message = o.message || DEFAULT_TAB_LOCK_MESSAGE;

        root.querySelectorAll(".tab-btn[data-tab-target]").forEach(function (btn) {
            const isLocked = locked && normalizeTabTarget(btn.dataset.tabTarget) !== activeTarget;
            btn.classList.toggle("is-tab-locked", isLocked);

            if (isLocked) {
                btn.dataset.tabLockMessage = message;
                btn.setAttribute("title", message);
            } else {
                btn.removeAttribute("data-tab-lock-message");
                btn.removeAttribute("title");
            }
        });
    }

    function bindTabNavigationLock(o) {
        const root = document.getElementById(o.containerId);
        if (!root || root.dataset.inlineTabLockBound === "1") {
            return;
        }

        root.dataset.inlineTabLockBound = "1";
        root.addEventListener("arboris:before-tab-activate", function (event) {
            const nextTarget = normalizeTabTarget(event.detail && event.detail.tabId);
            const activeTarget = currentInlineTarget(o.targetInputId);

            if (!isInlineEditing(o.getViewMode) || !nextTarget || nextTarget === activeTarget) {
                return;
            }

            event.preventDefault();
            refreshTabButtonLocks(o);

            if (event.detail && event.detail.button) {
                const message = o.message || DEFAULT_TAB_LOCK_MESSAGE;
                event.detail.button.classList.add("is-tab-locked");
                event.detail.button.dataset.tabLockMessage = message;
                event.detail.button.setAttribute("title", message);
            }
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
    function createRefreshLockedTabs(o) {
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

            refreshTabButtonLocks({
                containerId: o.inlineLockContainerId,
                targetInputId: o.targetInputId,
                getViewMode: o.getViewMode,
                message: o.tabLockMessage,
            });

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
        refreshTabButtonLocks: refreshTabButtonLocks,
        bindTabNavigationLock: bindTabNavigationLock,
        createRefreshLockedTabs: createRefreshLockedTabs,
        createScuolaRefreshLockedTabs: createRefreshLockedTabs,
        updateDefaultInlineEditButtonLabel: updateDefaultInlineEditButtonLabel,
    };
})();
