window.ArborisInlineFormsets = (function () {
    function getCompanionRows(row, options) {
        const companionClasses = (options && options.companionClasses) || [];
        const companionRows = [];
        let current = row ? row.nextElementSibling : null;

        companionClasses.forEach(function (className) {
            if (current && current.classList.contains(className)) {
                companionRows.push(current);
                current = current.nextElementSibling;
            }
        });

        return companionRows;
    }

    function getErrorRow(row, options) {
        const errorRowClass = (options && options.errorRowClass) || "inline-errors-row";
        const companionRows = getCompanionRows(row, options);
        const lastRow = companionRows.length ? companionRows[companionRows.length - 1] : row;
        const candidate = lastRow ? lastRow.nextElementSibling : null;

        if (candidate && candidate.classList.contains(errorRowClass)) {
            return candidate;
        }

        return null;
    }

    function getRowBundle(row, options) {
        const companionRows = getCompanionRows(row, options);
        const errorRow = getErrorRow(row, options);
        const bundle = [row].concat(companionRows);

        if (errorRow) {
            bundle.push(errorRow);
        }

        return {
            row: row,
            companionRows: companionRows,
            errorRow: errorRow,
            bundle: bundle,
        };
    }

    function getPrimaryCompanionRow(row, options) {
        return getCompanionRows(row, options)[0] || null;
    }

    function isRowPersisted(row) {
        const hiddenIdInput = row ? row.querySelector('input[type="hidden"][name$="-id"]') : null;
        return Boolean(hiddenIdInput && hiddenIdInput.value);
    }

    function rowHasVisibleErrors(row, options) {
        return Boolean(getErrorRow(row, options));
    }

    function collectFields(rows) {
        const fields = [];

        rows.forEach(function (currentRow) {
            if (!currentRow) {
                return;
            }

            currentRow.querySelectorAll("input, textarea, select").forEach(function (field) {
                fields.push(field);
            });
        });

        return fields;
    }

    function rowHasUserData(row, options) {
        const cfg = options || {};
        const rows = [row];

        if (cfg.includeCompanionRowsInData) {
            rows.push.apply(rows, getCompanionRows(row, cfg));
        }

        const ignoreTypes = new Set((cfg.ignoreInputTypes || ["hidden", "checkbox"]).map(function (value) {
            return String(value).toLowerCase();
        }));
        const ignoreSelects = Boolean(cfg.ignoreSelects);

        return collectFields(rows).some(function (field) {
            const type = (field.type || "").toLowerCase();

            if (ignoreTypes.has(type)) {
                return false;
            }

            if (ignoreSelects && field.tagName && field.tagName.toLowerCase() === "select") {
                return false;
            }

            return (field.value || "").trim() !== "";
        });
    }

    function setRowInputsEnabled(row, enabled, options) {
        const cfg = options || {};
        const rows = [row];

        if (cfg.includeCompanionRows) {
            rows.push.apply(rows, getCompanionRows(row, cfg));
        }

        collectFields(rows).forEach(function (field) {
            const type = (field.type || "").toLowerCase();

            if (cfg.skipHiddenInputs !== false && type === "hidden") {
                return;
            }

            if (enabled) {
                field.disabled = false;
                field.readOnly = false;
                field.classList.remove("submit-safe-locked");
                field.removeAttribute("aria-disabled");
                field.removeAttribute("tabindex");
                return;
            }

            field.disabled = true;
            if (type !== "hidden") {
                field.readOnly = true;
            }
        });
    }

    function markRowHidden(row, options) {
        const state = getRowBundle(row, options);

        state.bundle.forEach(function (node) {
            if (!node || node === state.errorRow) {
                return;
            }
            node.classList.add("inline-empty-row", "is-hidden");
        });

        if (options && typeof options.onHide === "function") {
            options.onHide(state);
        }

        return state;
    }

    function prepareExistingEmptyRows(tableId, options) {
        const cfg = options || {};
        document.querySelectorAll("#" + tableId + " tbody .inline-form-row").forEach(function (row) {
            if (isRowPersisted(row) || rowHasVisibleErrors(row, cfg) || rowHasUserData(row, cfg)) {
                return;
            }

            markRowHidden(row, cfg);
        });
    }

    function revealHiddenEmptyRow(tableId, options) {
        const cfg = options || {};
        const row = document.querySelector("#" + tableId + " tbody .inline-form-row.inline-empty-row.is-hidden");

        if (!row) {
            return null;
        }

        const state = getRowBundle(row, cfg);

        [state.row].concat(state.companionRows).forEach(function (node) {
            node.classList.remove("is-hidden");
            node.classList.remove("inline-empty-row");
        });

        if (cfg.enableInputs) {
            setRowInputsEnabled(state.row, true, {
                includeCompanionRows: true,
                companionClasses: cfg.companionClasses,
                skipHiddenInputs: cfg.skipHiddenInputs,
            });
        }

        if (typeof cfg.onReveal === "function") {
            cfg.onReveal(state);
        }

        return state;
    }

    function appendInlineForm(prefix, options) {
        const cfg = options || {};
        const tableId = cfg.tableId || prefix + "-table";
        const totalFormsId = cfg.totalFormsId || "id_" + prefix + "-TOTAL_FORMS";
        const templateId = cfg.templateId || prefix + "-empty-form-template";
        const totalForms = document.getElementById(totalFormsId);

        if (!totalForms) {
            return null;
        }

        const currentIndex = parseInt(totalForms.value, 10);
        const template = document.getElementById(templateId);
        const tbody = document.querySelector("#" + tableId + " tbody");

        if (!template || !tbody) {
            return null;
        }

        const newRowHtml = template.innerHTML.replace(/__prefix__/g, currentIndex);
        tbody.insertAdjacentHTML("beforeend", newRowHtml);
        totalForms.value = currentIndex + 1;

        let row = tbody.lastElementChild;
        while (row && !row.classList.contains("inline-form-row")) {
            row = row.previousElementSibling;
        }
        if (!row) {
            return null;
        }

        const state = getRowBundle(row, cfg);

        if (cfg.enableInputs) {
            setRowInputsEnabled(state.row, true, {
                includeCompanionRows: true,
                companionClasses: cfg.companionClasses,
                skipHiddenInputs: cfg.skipHiddenInputs,
            });
        }

        if (typeof cfg.onAppend === "function") {
            cfg.onAppend(state);
        }

        return state;
    }

    function focusFirstField(row, selector) {
        if (!row) {
            return null;
        }

        const resolvedSelector =
            selector ||
            "input[type='text'], input[type='email'], input[type='date'], input[type='url'], input[type='number'], select, textarea";
        const field = row.querySelector(resolvedSelector);

        if (field && typeof field.focus === "function") {
            field.focus();
        }

        return field || null;
    }

    function mountInlineForm(prefix, options) {
        const cfg = options || {};
        const tableId = cfg.tableId || prefix + "-table";
        const revealOptions = Object.assign({}, cfg, { tableId: tableId });
        const appendOptions = Object.assign({}, cfg, { tableId: tableId });
        const revealedState = revealHiddenEmptyRow(tableId, revealOptions);
        const state = revealedState || appendInlineForm(prefix, appendOptions);

        if (!state) {
            return null;
        }

        const phase = revealedState ? "reveal" : "append";

        if (typeof cfg.onReady === "function") {
            cfg.onReady(state, phase);
        }

        if (typeof cfg.focus === "function") {
            cfg.focus(state, phase);
        } else if (cfg.focusSelector !== false) {
            focusFirstField(state.row, cfg.focusSelector);
        }

        if (typeof cfg.onAfterMount === "function") {
            cfg.onAfterMount(state, phase);
        }

        return {
            state: state,
            phase: phase,
            revealed: Boolean(revealedState),
        };
    }

    function markBundleForAddOnlyEdit(state, options) {
        const cfg = options || {};
        const form = typeof cfg.form === "string" ? document.getElementById(cfg.form) : cfg.form;

        if (form) {
            form.classList.add("is-inline-add-only-mode");
        }

        if (!state || !state.bundle) {
            return;
        }

        state.bundle.forEach(function (node) {
            if (node) {
                node.classList.add("is-inline-active-edit-row");
            }
        });
    }

    function removeInlineRow(buttonOrRow, options) {
        const row = buttonOrRow && buttonOrRow.closest ? buttonOrRow.closest("tr") : buttonOrRow;
        if (!row) {
            return null;
        }

        const state = getRowBundle(row, options);
        state.bundle.forEach(function (node) {
            if (node) {
                node.remove();
            }
        });
        return state;
    }

    function countPersistedRows(tableId) {
        let count = 0;

        document.querySelectorAll("#" + tableId + " tbody .inline-form-row").forEach(function (row) {
            if (row.classList.contains("inline-empty-row")) {
                return;
            }

            const deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            if (deleteCheckbox && deleteCheckbox.checked) {
                return;
            }

            if (isRowPersisted(row)) {
                count += 1;
            }
        });

        return count;
    }

    function createManager(config) {
        const cfg = Object.assign({}, config || {});

        function resolveTableId() {
            return cfg.tableId || (cfg.prefix ? cfg.prefix + "-table" : "");
        }

        function prepare() {
            const tableId = resolveTableId();
            if (!tableId) {
                return;
            }

            prepareExistingEmptyRows(tableId, cfg.prepareOptions || {});
        }

        function add() {
            if (!cfg.prefix) {
                return null;
            }

            const mountOptions = Object.assign({}, cfg.mountOptions || {});
            if (!mountOptions.tableId && cfg.tableId) {
                mountOptions.tableId = cfg.tableId;
            }
            if (!mountOptions.totalFormsId && cfg.totalFormsId) {
                mountOptions.totalFormsId = cfg.totalFormsId;
            }
            if (!mountOptions.templateId && cfg.templateId) {
                mountOptions.templateId = cfg.templateId;
            }

            return mountInlineForm(cfg.prefix, mountOptions);
        }

        function remove(buttonOrRow) {
            return removeInlineRow(buttonOrRow, cfg.removeOptions || {});
        }

        function count() {
            const tableId = resolveTableId();
            if (!tableId) {
                return 0;
            }

            return countPersistedRows(tableId);
        }

        return {
            add: add,
            count: count,
            prepare: prepare,
            remove: remove,
            tableId: resolveTableId(),
        };
    }

    function wireActionTriggers(container, options) {
        const root = container || document;
        const cfg = options || {};
        const selector = cfg.selector || "[data-inline-action]";
        const handlers = cfg.handlers || {};

        if (!root || typeof root.querySelectorAll !== "function") {
            return;
        }

        root.querySelectorAll(selector).forEach(function (element) {
            if (element.dataset.inlineActionTriggerBound === "1") {
                return;
            }

            element.dataset.inlineActionTriggerBound = "1";
            element.addEventListener("click", function (event) {
                const action = element.dataset.inlineAction || "";
                const handler = handlers[action];

                if (typeof handler !== "function") {
                    return;
                }

                event.preventDefault();
                handler(element.dataset.inlinePrefix || "", element);
            });
        });
    }

    return {
        getCompanionRows: getCompanionRows,
        getPrimaryCompanionRow: getPrimaryCompanionRow,
        getErrorRow: getErrorRow,
        getRowBundle: getRowBundle,
        isRowPersisted: isRowPersisted,
        rowHasVisibleErrors: rowHasVisibleErrors,
        rowHasUserData: rowHasUserData,
        setRowInputsEnabled: setRowInputsEnabled,
        markRowHidden: markRowHidden,
        prepareExistingEmptyRows: prepareExistingEmptyRows,
        revealHiddenEmptyRow: revealHiddenEmptyRow,
        appendInlineForm: appendInlineForm,
        focusFirstField: focusFirstField,
        mountInlineForm: mountInlineForm,
        markBundleForAddOnlyEdit: markBundleForAddOnlyEdit,
        removeInlineRow: removeInlineRow,
        countPersistedRows: countPersistedRows,
        createManager: createManager,
        wireActionTriggers: wireActionTriggers,
    };
})();
