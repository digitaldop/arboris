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
            var targetInputName = select.name;

            function refreshButtons() {
                var sid = select.value;
                editBtn.disabled = !sid;
                deleteBtn.disabled = !sid;
                if (onRefresh) {
                    onRefresh(relatedType, select);
                }
            }

            addBtn.onclick = function () {
                var cfg = buildCrudUrls(relatedType, null, targetInputName);
                if (cfg && cfg.addUrl) {
                    openRelatedPopup(cfg.addUrl);
                }
            };

            editBtn.onclick = function () {
                var cfg = buildCrudUrls(relatedType, select.value, targetInputName);
                if (cfg && cfg.editUrl) {
                    openRelatedPopup(cfg.editUrl);
                }
            };

            deleteBtn.onclick = function () {
                var cfg = buildCrudUrls(relatedType, select.value, targetInputName);
                if (cfg && cfg.deleteUrl) {
                    openRelatedPopup(cfg.deleteUrl);
                }
            };

            select.addEventListener("change", refreshButtons);
            refreshButtons();
        });
    }

    return {
        buildCrudUrls: buildCrudUrls,
        wireInlineRelatedButtons: wireInlineRelatedButtons,
        withPopupQuery: withPopupQuery,
        substituteId: substituteId,
    };
})();
