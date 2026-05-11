window.ArborisFamilyLinkedAddress = (function () {
    function readJsonScriptText(scriptId) {
        const node = scriptId ? document.getElementById(scriptId) : null;
        if (!node) {
            return "";
        }

        try {
            const value = JSON.parse(node.textContent);
            return typeof value === "string" ? value : "";
        } catch (e) {
            return "";
        }
    }

    function getSelectedOption(select) {
        if (!select) {
            return null;
        }

        return select.options[select.selectedIndex] || null;
    }

    function markInheritedAddress(addressSelect, enabled) {
        if (!addressSelect) {
            return;
        }

        if (enabled) {
            addressSelect.dataset.inheritedAddress = "1";
        } else {
            delete addressSelect.dataset.inheritedAddress;
        }
    }

    function getFamilyAddressId(config, addressSelect) {
        const cfg = config || {};
        return typeof cfg.getFamilyAddressId === "function"
            ? (cfg.getFamilyAddressId(addressSelect) || "")
            : (cfg.familyAddressId || "");
    }

    function getFamilyAddressLabel(config, addressSelect) {
        const cfg = config || {};
        return typeof cfg.getFamilyAddressLabel === "function"
            ? (cfg.getFamilyAddressLabel(addressSelect) || "")
            : (cfg.familyAddressLabel || "");
    }

    function collectElements(root, selector) {
        if (typeof root === "string") {
            return Array.from(document.querySelectorAll(root));
        }

        if (!root) {
            return Array.from(document.querySelectorAll(selector));
        }

        if (Array.isArray(root)) {
            return root.filter(Boolean);
        }

        if (typeof root.length === "number" && typeof root !== "string" && !root.nodeType) {
            return Array.from(root).filter(Boolean);
        }

        if (typeof root.querySelectorAll === "function") {
            return Array.from(root.querySelectorAll(selector));
        }

        return [];
    }

    function isHiddenEmptyInlineRow(row) {
        return Boolean(
            row &&
            row.classList &&
            row.classList.contains("inline-empty-row") &&
            row.classList.contains("is-hidden")
        );
    }

    function isPersistedInlineRow(row, idSelector) {
        const hiddenIdInput = row ? row.querySelector(idSelector || 'input[type="hidden"][name$="-id"]') : null;
        return Boolean(hiddenIdInput && hiddenIdInput.value);
    }

    function refreshInlineAddressHelp(addressSelect, config) {
        if (!addressSelect) {
            return;
        }

        const cfg = config || {};
        const wrapperCell = addressSelect.closest(cfg.wrapperSelector || "td");
        if (!wrapperCell) {
            return;
        }

        const help = wrapperCell.querySelector(cfg.helpSelector || '[data-role="address-help"]');
        if (!help) {
            return;
        }

        const familyAddressId = getFamilyAddressId(cfg, addressSelect);
        const familyAddressLabel = getFamilyAddressLabel(cfg, addressSelect);
        const specificHelpText = cfg.specificHelpText || "Indirizzo specifico";
        const selectedFamilyPrefix = cfg.selectedFamilyPrefix || "Indirizzo impostato come ";
        const emptyFamilyPrefix = cfg.emptyFamilyPrefix || "Imposta l'indirizzo come ";
        const emptyHelpText = cfg.emptyHelpText || "Nessun indirizzo principale disponibile";

        wrapperCell
            .querySelectorAll(cfg.applyActionSelector || '[data-inline-address-action="apply-family-address"]')
            .forEach(function (button) {
                button.disabled = !familyAddressId;
                button.classList.toggle("is-disabled", !familyAddressId);
            });

        if (addressSelect.value && familyAddressId && addressSelect.value === familyAddressId && familyAddressLabel) {
            help.textContent = selectedFamilyPrefix + familyAddressLabel;
            return;
        }

        if (addressSelect.value) {
            if (familyAddressId && familyAddressLabel) {
                help.textContent = emptyFamilyPrefix + familyAddressLabel;
                return;
            }
            help.textContent = specificHelpText;
            return;
        }

        if (familyAddressLabel) {
            help.textContent = emptyFamilyPrefix + familyAddressLabel;
            return;
        }

        help.textContent = emptyHelpText;
    }

    function applyFamilyAddressToSelect(addressSelect, config) {
        if (!addressSelect) {
            return false;
        }

        const cfg = config || {};
        const familyAddressId = getFamilyAddressId(cfg, addressSelect);
        if (!familyAddressId) {
            refreshInlineAddressHelp(addressSelect, cfg);
            return false;
        }

        const previousValue = addressSelect.value || "";
        addressSelect.value = familyAddressId;
        markInheritedAddress(addressSelect, true);
        if (addressSelect.value !== previousValue) {
            addressSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }
        refreshInlineAddressHelp(addressSelect, cfg);
        return true;
    }

    function getAddressPriorityIds(root, config) {
        const cfg = config || {};
        const ids = new Set();
        const familyAddressId = getFamilyAddressId(cfg);
        if (familyAddressId) {
            ids.add(String(familyAddressId));
        }

        const scope = typeof cfg.relatedAddressScope === "function"
            ? cfg.relatedAddressScope()
            : (cfg.relatedAddressScope || root || document);

        collectElements(scope, cfg.relatedAddressSelector || 'select[name$="-indirizzo"]').forEach(function (select) {
            if (select && select.value) {
                ids.add(String(select.value));
            }
        });

        return ids;
    }

    function refreshRelatedAddressPriorities(root, config) {
        const cfg = config || {};
        const ids = getAddressPriorityIds(root, cfg);

        collectElements(root || cfg.root || document, cfg.selector || 'select[name$="-indirizzo"]').forEach(function (select) {
            Array.from(select.options || []).forEach(function (option) {
                const isPriority = option.value && ids.has(String(option.value));
                if (isPriority) {
                    option.dataset.searchablePriority = "1";
                    option.dataset.searchablePrioritySource = "family-linked-address";
                    option.dataset.searchableGroup = cfg.priorityGroupLabel || "Indirizzi collegati";
                } else if (option.dataset.searchablePrioritySource === "family-linked-address") {
                    delete option.dataset.searchablePriority;
                    delete option.dataset.searchablePrioritySource;
                    delete option.dataset.searchableGroup;
                }
            });
        });
    }

    function bindFamilyAddressApplyActions(root, config) {
        const cfg = config || {};
        collectElements(root || document, cfg.applyActionSelector || '[data-inline-address-action="apply-family-address"]').forEach(function (button) {
            const bindFlag = cfg.applyActionBindFlag || "familyAddressApplyBound";
            if (button.dataset[bindFlag] === "1") {
                return;
            }

            button.dataset[bindFlag] = "1";
            button.addEventListener("click", function () {
                const wrapperCell = button.closest(cfg.wrapperSelector || "td");
                const addressSelect = wrapperCell
                    ? wrapperCell.querySelector(cfg.addressSelector || 'select[name$="-indirizzo"]')
                    : null;
                applyFamilyAddressToSelect(addressSelect, cfg);
                refreshRelatedAddressPriorities(cfg.root || document, cfg);
            });
        });
    }

    function syncInlineAddressToFamily(addressSelect, config) {
        if (!addressSelect) {
            return;
        }

        const cfg = config || {};
        const familyAddressId = getFamilyAddressId(cfg, addressSelect);
        const isInherited = addressSelect.dataset.inheritedAddress === "1";
        const previousValue = addressSelect.value || "";

        if (!familyAddressId) {
            if (isInherited) {
                addressSelect.value = "";
                markInheritedAddress(addressSelect, false);
                if (previousValue) {
                    addressSelect.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }
            refreshInlineAddressHelp(addressSelect, cfg);
            return;
        }

        if (cfg.syncFamilyAddressAutomatically === false) {
            if (!addressSelect.value && isInherited) {
                markInheritedAddress(addressSelect, false);
            }
            refreshInlineAddressHelp(addressSelect, cfg);
            return;
        }

        if (!addressSelect.value || isInherited) {
            addressSelect.value = familyAddressId;
            markInheritedAddress(addressSelect, true);
            if (addressSelect.value !== previousValue) {
                addressSelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }

        refreshInlineAddressHelp(addressSelect, cfg);
    }

    function bindInlineAddressTracking(root, config) {
        const cfg = config || {};
        collectElements(root || document, cfg.selector || 'select[name$="-indirizzo"]').forEach(function (select) {
            const bindFlag = cfg.bindFlag || "familyInlineAddressBound";
            if (select.dataset[bindFlag] === "1") {
                return;
            }

            select.dataset[bindFlag] = "1";
            select.addEventListener("change", function () {
                const familyAddressId = getFamilyAddressId(cfg, select);
                markInheritedAddress(select, Boolean(familyAddressId && select.value === familyAddressId));
                refreshInlineAddressHelp(select, cfg);
                refreshRelatedAddressPriorities(cfg.root || document, cfg);
            });
        });

        bindFamilyAddressApplyActions(root || document, cfg);
        refreshRelatedAddressPriorities(root || document, cfg);
    }

    function applyInlineRowDefaults(row, config) {
        if (!row || isHiddenEmptyInlineRow(row)) {
            return;
        }

        const cfg = config || {};
        const isPersisted = isPersistedInlineRow(row, cfg.idSelector);
        const surnameInput = cfg.surnameSelector ? row.querySelector(cfg.surnameSelector) : null;
        const addressSelect = row.querySelector(cfg.addressSelector || 'select[name$="-indirizzo"]');
        const attivoCheckbox = cfg.attivoSelector ? row.querySelector(cfg.attivoSelector) : null;
        const familySurname = typeof cfg.getFamilySurname === "function"
            ? (cfg.getFamilySurname(row) || "").trim()
            : (typeof cfg.familySurname === "string" ? cfg.familySurname.trim() : "");

        if (!isPersisted && surnameInput) {
            surnameInput.value = familySurname;
        }

        if (!isPersisted && attivoCheckbox) {
            attivoCheckbox.checked = true;
        }

        if (!addressSelect) {
            return;
        }

        if (
            !isPersisted &&
            !addressSelect.value &&
            cfg.markInheritedWhenEmpty !== false &&
            cfg.syncFamilyAddressAutomatically !== false
        ) {
            markInheritedAddress(addressSelect, true);
        }

        syncInlineAddressToFamily(addressSelect, cfg);
    }

    function syncInlineRows(root, config) {
        const cfg = config || {};
        collectElements(root, cfg.rowSelector || ".inline-form-row").forEach(function (row) {
            applyInlineRowDefaults(row, cfg);
        });
        const priorityRoot = typeof root === "string" ? (cfg.root || document) : (root || cfg.root || document);
        refreshRelatedAddressPriorities(priorityRoot, cfg);
        bindFamilyAddressApplyActions(priorityRoot, cfg);
    }

    function refreshInlineAddressHelpForCollection(root, config) {
        const cfg = config || {};
        refreshRelatedAddressPriorities(root || cfg.root || document, cfg);
        bindFamilyAddressApplyActions(root || cfg.root || document, cfg);
        collectElements(root, cfg.selector || 'select[name$="-indirizzo"]').forEach(function (select) {
            refreshInlineAddressHelp(select, cfg);
        });
    }

    function createInlineAddressCollection(config) {
        const cfg = Object.assign({}, config || {});

        function bindTracking(root) {
            bindInlineAddressTracking(root || cfg.root || document, cfg);
        }

        function syncRows(root) {
            syncInlineRows(root || cfg.rowSelector || cfg.root, cfg);
        }

        function refreshSelectHelp(select) {
            refreshInlineAddressHelp(select, cfg);
        }

        function applyFamilyAddress(select) {
            return applyFamilyAddressToSelect(select, cfg);
        }

        function refreshCollectionHelp(root) {
            refreshInlineAddressHelpForCollection(root || cfg.root || document, cfg);
        }

        return {
            config: cfg,
            bindTracking: bindTracking,
            syncRows: syncRows,
            refreshSelectHelp: refreshSelectHelp,
            applyFamilyAddress: applyFamilyAddress,
            refreshCollectionHelp: refreshCollectionHelp,
        };
    }

    function createController(config) {
        const familySelect = config.familySelect;
        const addressSelect = config.addressSelect;
        const surnameInput = config.surnameInput || null;
        const helpElement = config.helpElement || null;
        const fallbackLabelScriptId = config.fallbackLabelScriptId || "";
        const onRefreshButtons = typeof config.onRefreshButtons === "function" ? config.onRefreshButtons : function () {};
        const familyAddressIdKey = config.familyAddressIdKey || "indirizzoFamigliaId";
        const familyAddressLabelKey = config.familyAddressLabelKey || "indirizzoFamiglia";
        const familySurnameKey = config.familySurnameKey || "cognomeFamiglia";
        const emptyHelpText = config.emptyHelpText || "Se lasci vuoto, verra usato l'indirizzo principale della famiglia";
        const specificHelpText = config.specificHelpText || "Indirizzo specifico";
        const selectedFamilyPrefix = config.selectedFamilyPrefix || "Indirizzo famiglia: ";
        const unselectedFamilyPrefix = config.unselectedFamilyPrefix || "Usa indirizzo famiglia: ";

        function getSelectedFamigliaOption() {
            return getSelectedOption(familySelect);
        }

        function getSelectedFamigliaAddressId() {
            const option = getSelectedFamigliaOption();
            return option ? (option.dataset[familyAddressIdKey] || "") : "";
        }

        function getSelectedFamigliaAddressLabel() {
            const option = getSelectedFamigliaOption();
            return option ? (option.dataset[familyAddressLabelKey] || "") : "";
        }

        function updateInheritedAddressPlaceholder() {
            if (!addressSelect || !addressSelect.options.length) {
                return;
            }

            const emptyOption = addressSelect.options[0];
            if (!emptyOption) {
                return;
            }

            if (!addressSelect.dataset.defaultEmptyLabel) {
                addressSelect.dataset.defaultEmptyLabel = emptyOption.textContent;
            }

            emptyOption.textContent = getSelectedFamigliaAddressLabel() || addressSelect.dataset.defaultEmptyLabel;
        }

        function refreshAddressHelp() {
            if (!addressSelect || !helpElement) {
                return;
            }

            const familyAddressId = getSelectedFamigliaAddressId();
            const familyAddressLabel = getSelectedFamigliaAddressLabel();

            if (addressSelect.value && familyAddressId && addressSelect.value === familyAddressId) {
                helpElement.textContent = familyAddressLabel
                    ? selectedFamilyPrefix + familyAddressLabel
                    : "Indirizzo famiglia";
                return;
            }

            if (addressSelect.value) {
                helpElement.textContent = specificHelpText;
                return;
            }

            if (familyAddressLabel) {
                helpElement.textContent = unselectedFamilyPrefix + familyAddressLabel;
                return;
            }

            const fallbackLabel = readJsonScriptText(fallbackLabelScriptId);
            helpElement.textContent = fallbackLabel
                ? unselectedFamilyPrefix + fallbackLabel
                : emptyHelpText;
        }

        function syncFamigliaDefaults() {
            const selectedOption = getSelectedFamigliaOption();
            const familyAddressId = getSelectedFamigliaAddressId();
            const previousValue = addressSelect ? (addressSelect.value || "") : "";

            if (!selectedOption || !selectedOption.value) {
                if (addressSelect && addressSelect.dataset.inheritedAddress === "1" && previousValue) {
                    addressSelect.value = "";
                    markInheritedAddress(addressSelect, false);
                    addressSelect.dispatchEvent(new Event("change", { bubbles: true }));
                }
                updateInheritedAddressPlaceholder();
                refreshAddressHelp();
                onRefreshButtons();
                return;
            }

            if (surnameInput) {
                surnameInput.value = selectedOption.dataset[familySurnameKey] || "";
            }

            if (addressSelect) {
                const isInherited = addressSelect.dataset.inheritedAddress === "1";
                if ((!addressSelect.value || isInherited) && familyAddressId) {
                    addressSelect.value = familyAddressId;
                    markInheritedAddress(addressSelect, true);
                } else if (!familyAddressId && isInherited) {
                    addressSelect.value = "";
                    markInheritedAddress(addressSelect, false);
                }

                if ((addressSelect.value || "") !== previousValue) {
                    addressSelect.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }

            updateInheritedAddressPlaceholder();
            refreshAddressHelp();
            onRefreshButtons();
        }

        function syncInheritedStateFromAddress() {
            if (!addressSelect) {
                return;
            }

            const familyAddressId = getSelectedFamigliaAddressId();
            markInheritedAddress(addressSelect, Boolean(familyAddressId && addressSelect.value === familyAddressId));
            refreshAddressHelp();
            onRefreshButtons();
        }

        return {
            getSelectedFamigliaOption: getSelectedFamigliaOption,
            getSelectedFamigliaAddressId: getSelectedFamigliaAddressId,
            getSelectedFamigliaAddressLabel: getSelectedFamigliaAddressLabel,
            markInheritedAddress: function (enabled) {
                markInheritedAddress(addressSelect, enabled);
            },
            updateInheritedAddressPlaceholder: updateInheritedAddressPlaceholder,
            refreshAddressHelp: refreshAddressHelp,
            syncFamigliaDefaults: syncFamigliaDefaults,
            syncInheritedStateFromAddress: syncInheritedStateFromAddress,
        };
    }

    return {
        readJsonScriptText: readJsonScriptText,
        getSelectedOption: getSelectedOption,
        markInheritedAddress: markInheritedAddress,
        refreshInlineAddressHelp: refreshInlineAddressHelp,
        syncInlineAddressToFamily: syncInlineAddressToFamily,
        bindInlineAddressTracking: bindInlineAddressTracking,
        applyInlineRowDefaults: applyInlineRowDefaults,
        syncInlineRows: syncInlineRows,
        refreshInlineAddressHelpForCollection: refreshInlineAddressHelpForCollection,
        createInlineAddressCollection: createInlineAddressCollection,
        createController: createController,
    };
})();
