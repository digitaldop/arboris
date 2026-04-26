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
            return {
                refresh: function () {},
            };
        }

        var targetInputName = options.targetInputName || select.name;
        var bindKey = [relatedType, targetInputName].join(":");

        function defaultDisabledState(selectedId) {
            return Boolean(select.disabled || !selectedId);
        }

        function resolveDisabledState(kind, selectedId) {
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

            return defaultDisabledState(selectedId);
        }

        function refresh() {
            var selectedId = select.value || "";

            if (addBtn) {
                addBtn.disabled = resolveDisabledState("add", selectedId);
            }

            if (editBtn) {
                editBtn.disabled = resolveDisabledState("edit", selectedId);
            }

            if (deleteBtn) {
                deleteBtn.disabled = resolveDisabledState("delete", selectedId);
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

        refresh();

        return {
            refresh: refresh,
        };
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

    return {
        buildCrudUrls: buildCrudUrls,
        wireCrudButtons: wireCrudButtons,
        wireInlineRelatedButtons: wireInlineRelatedButtons,
        withPopupQuery: withPopupQuery,
        substituteId: substituteId,
    };
})();
