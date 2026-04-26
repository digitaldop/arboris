window.ArborisAnagraficaFormTools = (function () {
    function resolveElement(elementOrId) {
        if (!elementOrId) {
            return null;
        }

        if (typeof elementOrId === "string") {
            return document.getElementById(elementOrId);
        }

        return elementOrId;
    }

    function initSearchableSelects(root) {
        var targetRoot = root || document;
        var autocomplete = window.ArborisFamigliaAutocomplete;

        if (!autocomplete) {
            return;
        }

        if (typeof autocomplete.init === "function") {
            autocomplete.init(targetRoot);
        }

        if (typeof autocomplete.refresh === "function") {
            autocomplete.refresh(targetRoot);
        }
    }

    function initCodiceFiscale(root) {
        var targetRoot = root || document;
        var codiceFiscale = window.ArborisCodiceFiscale;

        if (!codiceFiscale) {
            return;
        }

        if (typeof codiceFiscale.rebind === "function") {
            codiceFiscale.rebind(targetRoot);
            return;
        }

        if (typeof codiceFiscale.init === "function") {
            codiceFiscale.init(targetRoot);
        }
    }

    function defaultFamigliaEditUrlBuilder(selectedId) {
        if (!selectedId) {
            return "";
        }

        return "/famiglie/" + encodeURIComponent(selectedId) + "/modifica/";
    }

    function bindFamigliaNavigation(options) {
        options = options || {};

        var familySelect = resolveElement(options.familySelect || options.familySelectId);
        var addBtn = resolveElement(options.addBtn || options.addBtnId);
        var editBtn = resolveElement(options.editBtn || options.editBtnId);
        var createUrl = options.createUrl || "";
        var editUrlBuilder = options.editUrlBuilder || defaultFamigliaEditUrlBuilder;

        function refresh() {
            if (editBtn && familySelect) {
                editBtn.disabled = !familySelect.value;
            }
        }

        if (addBtn && addBtn.dataset.familyNavBound !== "1") {
            addBtn.dataset.familyNavBound = "1";
            addBtn.addEventListener("click", function () {
                if (createUrl) {
                    window.location.href = createUrl;
                }
            });
        }

        if (editBtn && editBtn.dataset.familyNavBound !== "1") {
            editBtn.dataset.familyNavBound = "1";
            editBtn.addEventListener("click", function () {
                if (!familySelect || !familySelect.value) {
                    return;
                }

                var editUrl = typeof editUrlBuilder === "function"
                    ? editUrlBuilder(familySelect.value, familySelect)
                    : editUrlBuilder;

                if (editUrl) {
                    window.location.href = editUrl;
                }
            });
        }

        if (familySelect && familySelect.dataset.familyNavRefreshBound !== "1") {
            familySelect.dataset.familyNavRefreshBound = "1";
            familySelect.addEventListener("change", refresh);
        }

        refresh();

        return {
            refresh: refresh,
        };
    }

    function bindFamilyAddressController(options) {
        options = options || {};

        var familyLinkedAddress = options.familyLinkedAddress || window.ArborisFamilyLinkedAddress;
        var familySelect = resolveElement(options.familySelect || options.familySelectId);
        var addressSelect = resolveElement(options.addressSelect || options.addressSelectId);
        var bindKey = options.bindKey || [
            familySelect ? (familySelect.id || familySelect.name || "famiglia") : "famiglia",
            addressSelect ? (addressSelect.id || addressSelect.name || "indirizzo") : "indirizzo",
        ].join(":");

        if (!familyLinkedAddress) {
            return null;
        }

        var controller = familyLinkedAddress.createController({
            familySelect: familySelect,
            addressSelect: addressSelect,
            surnameInput: resolveElement(options.surnameInput || options.surnameInputId),
            helpElement: resolveElement(options.helpElement || options.helpElementId),
            fallbackLabelScriptId: options.fallbackLabelScriptId || "",
            onRefreshButtons: options.onRefreshButtons,
            familyAddressIdKey: options.familyAddressIdKey,
            familyAddressLabelKey: options.familyAddressLabelKey,
            familySurnameKey: options.familySurnameKey,
            emptyHelpText: options.emptyHelpText,
            specificHelpText: options.specificHelpText,
            selectedFamilyPrefix: options.selectedFamilyPrefix,
            unselectedFamilyPrefix: options.unselectedFamilyPrefix,
        });

        if (familySelect && familySelect.dataset.familyAddressControllerBound !== bindKey) {
            familySelect.dataset.familyAddressControllerBound = bindKey;
            familySelect.addEventListener("change", function () {
                controller.syncFamigliaDefaults();
            });
        }

        if (addressSelect && addressSelect.dataset.familyAddressControllerBound !== bindKey) {
            addressSelect.dataset.familyAddressControllerBound = bindKey;
            addressSelect.addEventListener("change", function () {
                controller.syncInheritedStateFromAddress();
            });
        }

        if (options.performInitialSync !== false) {
            controller.syncFamigliaDefaults();
            controller.updateInheritedAddressPlaceholder();
            controller.refreshAddressHelp();
        }

        return controller;
    }

    function wireInlineRelatedButtons(container, options) {
        options = options || {};

        var routes = options.routes || window.ArborisRelatedEntityRoutes;
        var relatedPopups = options.relatedPopups || window.ArborisRelatedPopups;

        if (!routes || !relatedPopups || typeof routes.wireInlineRelatedButtons !== "function") {
            return;
        }

        routes.wireInlineRelatedButtons(container, {
            openRelatedPopup: typeof relatedPopups.openRelatedPopup === "function"
                ? relatedPopups.openRelatedPopup.bind(relatedPopups)
                : null,
            onRefresh: options.onRefresh,
        });
    }

    return {
        bindFamilyAddressController: bindFamilyAddressController,
        initSearchableSelects: initSearchableSelects,
        initCodiceFiscale: initCodiceFiscale,
        bindFamigliaNavigation: bindFamigliaNavigation,
        wireInlineRelatedButtons: wireInlineRelatedButtons,
    };
})();
