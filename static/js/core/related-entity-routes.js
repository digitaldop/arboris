window.ArborisRelatedEntityRoutes = (function () {
    var PLACEHOLDER = "__ID__";

    function getManifest() {
        var el = document.getElementById("arboris-popup-manifest");
        if (!el) {
            return {};
        }
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return {};
        }
    }

    function withPopupQuery(url, targetInputName) {
        if (!url) {
            return null;
        }
        var sep = url.indexOf("?") >= 0 ? "&" : "?";
        var qs = sep + "popup=1";
        if (targetInputName) {
            qs += "&target_input_name=" + encodeURIComponent(targetInputName);
        }
        return url + qs;
    }

    function substituteId(templateUrl, selectedId) {
        if (!templateUrl || !selectedId) {
            return null;
        }
        return templateUrl.split(PLACEHOLDER).join(String(selectedId));
    }

    /**
     * @param {string} relatedType - e.g. tipo_documento, indirizzo (see popup_manifest)
     * @param {string|null|undefined} selectedId
     * @param {string|null|undefined} targetInputName - select name for dismissRelatedPopup
     * @returns {{addUrl: string, editUrl: string|null, deleteUrl: string|null}|null}
     */
    function buildCrudUrls(relatedType, selectedId, targetInputName) {
        var m = getManifest()[relatedType];
        if (!m || !m.add) {
            return null;
        }
        return {
            addUrl: withPopupQuery(m.add, targetInputName),
            editUrl: selectedId ? withPopupQuery(substituteId(m.edit, selectedId), targetInputName) : null,
            deleteUrl: selectedId ? withPopupQuery(substituteId(m.delete, selectedId), targetInputName) : null,
        };
    }

    function createNoopBinding() {
        return {
            refresh: function () {},
        };
    }

    function resolveDisabledState(options, select, kind, selectedId) {
        var predicate = null;

        if (kind === "add") {
            predicate = options.isAddDisabled;
        } else if (kind === "edit") {
            predicate = options.isEditDisabled;
        } else if (kind === "delete") {
            predicate = options.isDeleteDisabled;
        }

        if (typeof predicate === "function") {
            return Boolean(predicate(select, selectedId));
        }

        if (kind === "add") {
            return Boolean(select.disabled);
        }

        return Boolean(select.disabled || !selectedId);
    }

    function resolveActionUrl(builder, selectedId, select) {
        if (!builder) {
            return null;
        }

        if (typeof builder === "function") {
            return builder(selectedId, select) || null;
        }

        return builder;
    }

    function resolveElement(elementOrId) {
        if (!elementOrId) {
            return null;
        }

        if (typeof elementOrId === "string") {
            return document.getElementById(elementOrId);
        }

        return elementOrId;
    }

    function bindStateRefresh(select, bindKey, refresh) {
        if (!select || typeof refresh !== "function") {
            return;
        }

        if (select.dataset.relatedCrudStateRefreshBound === bindKey) {
            return;
        }
        select.dataset.relatedCrudStateRefreshBound = bindKey;

        if (window.MutationObserver) {
            var observer = new MutationObserver(function () {
                refresh();
            });
            observer.observe(select, {
                attributes: true,
                attributeFilter: ["disabled", "aria-disabled", "class"],
            });
        }

        document.addEventListener("arboris:view-mode-change", function (event) {
            var form = event.detail && event.detail.form;
            if (!form || form.contains(select)) {
                refresh();
            }
        });
    }

    function initRelatedPopups() {
        var relatedPopups = window.ArborisRelatedPopups;
        if (!relatedPopups) {
            return null;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;
        return relatedPopups;
    }

    /**
     * @param {{
     *   select: HTMLSelectElement,
     *   relatedType: string,
     *   addBtn?: HTMLButtonElement | null,
     *   editBtn?: HTMLButtonElement | null,
     *   deleteBtn?: HTMLButtonElement | null,
     *   targetInputName?: string | null,
     *   openRelatedPopup?: function(string): void,
     *   onRefresh?: function(string, HTMLSelectElement): void,
     *   isAddDisabled?: function(HTMLSelectElement, string): boolean,
     *   isEditDisabled?: function(HTMLSelectElement, string): boolean,
     *   isDeleteDisabled?: function(HTMLSelectElement, string): boolean,
     * }} options
     * @returns {{refresh: function(): void}}
     */
    function wireCrudButtons(options) {
        options = options || {};

        var select = options.select;
        var relatedType = options.relatedType;
        var addBtn = options.addBtn || null;
        var editBtn = options.editBtn || null;
        var deleteBtn = options.deleteBtn || null;
        var openRelatedPopup =
            options.openRelatedPopup ||
            (window.ArborisRelatedPopups && window.ArborisRelatedPopups.openRelatedPopup);

        if (!select || !relatedType || !openRelatedPopup) {
            return createNoopBinding();
        }

        var targetInputName = options.targetInputName || select.name;
        var bindKey = [relatedType, targetInputName].join(":");

        function refresh() {
            var selectedId = select.value || "";

            if (addBtn) {
                addBtn.disabled = resolveDisabledState(options, select, "add", selectedId);
            }

            if (editBtn) {
                editBtn.disabled = resolveDisabledState(options, select, "edit", selectedId);
            }

            if (deleteBtn) {
                deleteBtn.disabled = resolveDisabledState(options, select, "delete", selectedId);
            }

            if (typeof options.onRefresh === "function") {
                options.onRefresh(relatedType, select);
            }
        }

        if (select.dataset.relatedCrudButtonsBound !== bindKey) {
            select.dataset.relatedCrudButtonsBound = bindKey;

            if (addBtn) {
                addBtn.addEventListener("click", function () {
                    var cfg = buildCrudUrls(relatedType, null, targetInputName);
                    if (cfg && cfg.addUrl) {
                        openRelatedPopup(cfg.addUrl);
                    }
                });
            }

            if (editBtn) {
                editBtn.addEventListener("click", function () {
                    var cfg = buildCrudUrls(relatedType, select.value, targetInputName);
                    if (cfg && cfg.editUrl) {
                        openRelatedPopup(cfg.editUrl);
                    }
                });
            }

            if (deleteBtn) {
                deleteBtn.addEventListener("click", function () {
                    var cfg = buildCrudUrls(relatedType, select.value, targetInputName);
                    if (cfg && cfg.deleteUrl) {
                        openRelatedPopup(cfg.deleteUrl);
                    }
                });
            }

            select.addEventListener("change", refresh);
        }

        bindStateRefresh(select, bindKey, refresh);
        refresh();

        return {
            refresh: refresh,
        };
    }

    /**
     * @param {{
     *   select: HTMLSelectElement,
     *   addBtn?: HTMLButtonElement | null,
     *   editBtn?: HTMLButtonElement | null,
     *   deleteBtn?: HTMLButtonElement | null,
     *   addUrl?: string | ((selectedId: string, select: HTMLSelectElement) => string | null),
     *   editUrl?: string | ((selectedId: string, select: HTMLSelectElement) => string | null),
     *   deleteUrl?: string | ((selectedId: string, select: HTMLSelectElement) => string | null),
     *   openRelatedPopup?: function(string): void,
     *   onRefresh?: function(HTMLSelectElement): void,
     *   isAddDisabled?: function(HTMLSelectElement, string): boolean,
     *   isEditDisabled?: function(HTMLSelectElement, string): boolean,
     *   isDeleteDisabled?: function(HTMLSelectElement, string): boolean,
     *   bindKey?: string | null,
     * }} options
     * @returns {{refresh: function(): void}}
     */
    function wireCustomCrudButtons(options) {
        options = options || {};

        var select = options.select;
        var addBtn = options.addBtn || null;
        var editBtn = options.editBtn || null;
        var deleteBtn = options.deleteBtn || null;
        var openRelatedPopup =
            options.openRelatedPopup ||
            (window.ArborisRelatedPopups && window.ArborisRelatedPopups.openRelatedPopup);

        if (!select || !openRelatedPopup) {
            return createNoopBinding();
        }

        var bindKey = options.bindKey || ["custom", select.name || select.id || "field"].join(":");

        function refresh() {
            var selectedId = select.value || "";

            if (addBtn) {
                addBtn.disabled = resolveDisabledState(options, select, "add", selectedId);
            }

            if (editBtn) {
                editBtn.disabled = resolveDisabledState(options, select, "edit", selectedId);
            }

            if (deleteBtn) {
                deleteBtn.disabled = resolveDisabledState(options, select, "delete", selectedId);
            }

            if (typeof options.onRefresh === "function") {
                options.onRefresh(select);
            }
        }

        if (select.dataset.relatedCustomCrudButtonsBound !== bindKey) {
            select.dataset.relatedCustomCrudButtonsBound = bindKey;

            if (addBtn) {
                addBtn.addEventListener("click", function () {
                    var url = resolveActionUrl(options.addUrl, "", select);
                    if (url) {
                        openRelatedPopup(url);
                    }
                });
            }

            if (editBtn) {
                editBtn.addEventListener("click", function () {
                    var url = resolveActionUrl(options.editUrl, select.value || "", select);
                    if (url) {
                        openRelatedPopup(url);
                    }
                });
            }

            if (deleteBtn) {
                deleteBtn.addEventListener("click", function () {
                    var url = resolveActionUrl(options.deleteUrl, select.value || "", select);
                    if (url) {
                        openRelatedPopup(url);
                    }
                });
            }

            select.addEventListener("change", refresh);
        }

        bindStateRefresh(select, bindKey, refresh);
        refresh();

        return {
            refresh: refresh,
        };
    }

    /**
     * @param {object} options
     * @returns {{refresh: function(): void}}
     */
    function wireCrudButtonsById(options) {
        options = options || {};

        return wireCrudButtons({
            select: resolveElement(options.select || options.selectId),
            relatedType: options.relatedType,
            addBtn: resolveElement(options.addBtn || options.addBtnId),
            editBtn: resolveElement(options.editBtn || options.editBtnId),
            deleteBtn: resolveElement(options.deleteBtn || options.deleteBtnId),
            targetInputName: options.targetInputName || null,
            openRelatedPopup: options.openRelatedPopup,
            onRefresh: options.onRefresh,
            isAddDisabled: options.isAddDisabled,
            isEditDisabled: options.isEditDisabled,
            isDeleteDisabled: options.isDeleteDisabled,
        });
    }

    /**
     * @param {Array<object>} configs
     * @param {{openRelatedPopup?: function(string): void, onRefresh?: function(string, HTMLSelectElement): void}|undefined} sharedOptions
     */
    function wireCrudButtonsGroup(configs, sharedOptions) {
        sharedOptions = sharedOptions || {};

        (configs || []).forEach(function (config) {
            wireCrudButtonsById({
                selectId: config.selectId,
                select: config.select,
                relatedType: config.relatedType,
                addBtnId: config.addBtnId,
                addBtn: config.addBtn,
                editBtnId: config.editBtnId,
                editBtn: config.editBtn,
                deleteBtnId: config.deleteBtnId,
                deleteBtn: config.deleteBtn,
                targetInputName: config.targetInputName,
                openRelatedPopup: config.openRelatedPopup || sharedOptions.openRelatedPopup,
                onRefresh: config.onRefresh || sharedOptions.onRefresh,
                isAddDisabled: config.isAddDisabled,
                isEditDisabled: config.isEditDisabled,
                isDeleteDisabled: config.isDeleteDisabled,
            });
        });
    }

    /**
     * @param {object} options
     * @returns {{refresh: function(): void}}
     */
    function wireCustomCrudButtonsById(options) {
        options = options || {};

        return wireCustomCrudButtons({
            select: resolveElement(options.select || options.selectId),
            addBtn: resolveElement(options.addBtn || options.addBtnId),
            editBtn: resolveElement(options.editBtn || options.editBtnId),
            deleteBtn: resolveElement(options.deleteBtn || options.deleteBtnId),
            addUrl: options.addUrl,
            editUrl: options.editUrl,
            deleteUrl: options.deleteUrl,
            openRelatedPopup: options.openRelatedPopup,
            onRefresh: options.onRefresh,
            isAddDisabled: options.isAddDisabled,
            isEditDisabled: options.isEditDisabled,
            isDeleteDisabled: options.isDeleteDisabled,
            bindKey: options.bindKey || null,
        });
    }

    /**
     * @param {Element} container
     * @param {{openRelatedPopup?: function(string): void, onRefresh?: function(string, HTMLSelectElement): void}|undefined} options
     */
    function wireInlineRelatedButtons(container, options) {
        options = options || {};
        var openRelatedPopup =
            options.openRelatedPopup ||
            (window.ArborisRelatedPopups && window.ArborisRelatedPopups.openRelatedPopup);
        if (!openRelatedPopup) {
            return;
        }
        var onRefresh = options.onRefresh;
        var rows = container.querySelectorAll(".inline-related-field");
        rows.forEach(function (fieldWrapper) {
            if (fieldWrapper.dataset.relatedBound === "1") {
                return;
            }
            fieldWrapper.dataset.relatedBound = "1";

            var select = fieldWrapper.querySelector("select");
            var addBtn = fieldWrapper.querySelector(".inline-related-add");
            var editBtn = fieldWrapper.querySelector(".inline-related-edit");
            var deleteBtn = fieldWrapper.querySelector(".inline-related-delete");

            if (!select || !addBtn || !editBtn || !deleteBtn) {
                return;
            }

            var relatedType = addBtn.dataset.relatedType;
            wireCrudButtons({
                select: select,
                relatedType: relatedType,
                addBtn: addBtn,
                editBtn: editBtn,
                deleteBtn: deleteBtn,
                targetInputName: select.name,
                openRelatedPopup: openRelatedPopup,
                onRefresh: onRefresh,
            });
        });
    }

    /**
     * @param {Element|Document} container
     * @param {{openRelatedPopup?: function(string): void, selector?: string}|undefined} options
     */
    function wirePopupTriggerElements(container, options) {
        options = options || {};
        var root = container || document;
        var selector = options.selector || '[data-related-popup-trigger="1"]';
        var openRelatedPopup =
            options.openRelatedPopup ||
            (window.ArborisRelatedPopups && window.ArborisRelatedPopups.openRelatedPopup);

        if (!root || !openRelatedPopup || typeof root.querySelectorAll !== "function") {
            return;
        }

        root.querySelectorAll(selector).forEach(function (element) {
            if (element.dataset.relatedPopupTriggerBound === "1") {
                return;
            }

            element.dataset.relatedPopupTriggerBound = "1";
            element.addEventListener("click", function (event) {
                var popupUrl = element.dataset.popupUrl;
                if (!popupUrl || element.disabled) {
                    return;
                }

                event.preventDefault();
                openRelatedPopup(popupUrl);
            });
        });
    }

    return {
        buildCrudUrls: buildCrudUrls,
        initRelatedPopups: initRelatedPopups,
        wireCrudButtons: wireCrudButtons,
        wireCrudButtonsById: wireCrudButtonsById,
        wireCrudButtonsGroup: wireCrudButtonsGroup,
        wireCustomCrudButtons: wireCustomCrudButtons,
        wireCustomCrudButtonsById: wireCustomCrudButtonsById,
        wireInlineRelatedButtons: wireInlineRelatedButtons,
        wirePopupTriggerElements: wirePopupTriggerElements,
        withPopupQuery: withPopupQuery,
        substituteId: substituteId,
    };
})();
