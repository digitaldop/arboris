window.ArborisFamiliareForm = (function () {
    let refreshInlineEditScopeHandler = function () {};

    function init(config) {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineTabs = window.ArborisInlineTabs;
        const inlineFormsets = window.ArborisInlineFormsets;
        const personRules = window.ArborisPersonRules;
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;
        const formTools = window.ArborisAnagraficaFormTools;

        if (!routes || !relatedPopups || !collapsible || !tabs || !inlineTabs || !inlineFormsets || !personRules || !familyLinkedAddress || !formTools) {
            console.error("Arboris core JS non caricato correttamente.");
            return;
        }

        const targetInputId = "familiare-inline-target";
        const inlineLockContainerId = "familiare-inline-lock-container";
        const inlineEditButtonId = "enable-inline-edit-familiare-btn";

        function getFamiliareTabStorageKey() {
            return `arboris-familiare-form-active-tab-${config.familiareId || "new"}`;
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
                    return window.familiareViewMode;
                },
            });
        }

        const refreshLockedTabs = inlineTabs.createRefreshLockedTabs({
            formId: "familiare-detail-form",
            inlineLockContainerId: inlineLockContainerId,
            targetInputId: targetInputId,
            getViewMode: function () {
                return window.familiareViewMode;
            },
            inlineEditButtonId: inlineEditButtonId,
        });

        function refreshInlineEditScope() {
            refreshLockedTabs();
        }
        refreshInlineEditScopeHandler = refreshInlineEditScope;

        function activatePanelIfPresent(tabId) {
            const panel = document.getElementById(tabId);
            if (!panel) {
                return;
            }

            if (document.querySelector(`[data-tab-target="${tabId}"]`)) {
                setInlineTarget(tabId);
                tabs.activateTab(tabId, getFamiliareTabStorageKey());
                updateInlineEditButtonLabel(tabId);
                refreshInlineEditScope();
                return;
            }

            document.querySelectorAll(".tab-panel").forEach(existingPanel => existingPanel.classList.remove("is-active"));
            panel.classList.add("is-active");
            setInlineTarget(tabId);
            updateInlineEditButtonLabel(tabId);
            refreshInlineEditScope();
        }

        function bindStandaloneSexFromRelazioneFamiliare() {
            personRules.bindSexFromRelation({
                relationSelect: document.getElementById("id_relazione_familiare"),
                sexSelect: document.getElementById("id_sesso"),
                bindFlag: "familiareRelationSexBound",
            });
        }

        function updateMainButtons() {
            refreshFamigliaNavigation();
            refreshRelazioneButtons();
            refreshIndirizzoButtons();
        }

        function wireInlineRelatedButtons(container) {
            formTools.wireInlineRelatedButtons(container, {
                routes: routes,
                relatedPopups: relatedPopups,
                onRefresh(relatedType, select) {
                    if (relatedType === "indirizzo" && select && select.closest("#studenti-table")) {
                        studentiInlineAddressCollection.refreshSelectHelp(select);
                    }
                },
            });
        }

        function readFamiliareStudentiInlineDefaults() {
            const el = document.getElementById("familiare-studenti-inline-defaults");
            if (!el) {
                return { indirizzo_principale_id: "", cognome_famiglia: "" };
            }
            try {
                return JSON.parse(el.textContent);
            } catch (e) {
                return { indirizzo_principale_id: "", cognome_famiglia: "" };
            }
        }

        function getStudenteInlineFamigliaIndirizzoPrincipaleLabel() {
            const node = document.getElementById("familiare-famiglia-indirizzo-label");
            if (!node) {
                return "";
            }
            try {
                const v = JSON.parse(node.textContent);
                return typeof v === "string" ? v : "";
            } catch (e) {
                return "";
            }
        }

        const studentiInlineAddressConfig = {
            getFamilyAddressId: function () {
                return readFamiliareStudentiInlineDefaults().indirizzo_principale_id || "";
            },
            getFamilyAddressLabel: getStudenteInlineFamigliaIndirizzoPrincipaleLabel,
            emptyFamilyPrefix: "Ereditera: ",
        };

        const studentiInlineAddressTrackingConfig = Object.assign({
            selector: 'select[name$="-indirizzo"]',
            bindFlag: "familiareStudenteAddrBound",
        }, studentiInlineAddressConfig);

        const studentiInlineDefaultsConfig = Object.assign({
            rowSelector: "#studenti-table tbody .inline-form-row",
            surnameSelector: 'input[name$="-cognome"]',
            getFamilySurname: function () {
                return (readFamiliareStudentiInlineDefaults().cognome_famiglia || "").trim();
            },
            attivoSelector: 'input[type="checkbox"][name$="-attivo"]',
        }, studentiInlineAddressConfig);
        const studentiInlineAddressCollection = familyLinkedAddress.createInlineAddressCollection(studentiInlineAddressTrackingConfig);
        const studentiInlineAddressDefaults = familyLinkedAddress.createInlineAddressCollection(studentiInlineDefaultsConfig);

        function getFamiliareSubformRow(row) {
            return inlineFormsets.getPrimaryCompanionRow(row, { companionClasses: ["inline-subform-row"] });
        }

        function bindStudenteInlineSex(row) {
            const subformRow = getFamiliareSubformRow(row);
            personRules.bindTrackedSexFromFirstName({
                root: row,
                nameSelector: 'input[name$="-nome"]',
                sexSelect: subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null,
                bindFlag: "studenteInlineSexNameBound",
                sourceKey: "studente-inline-name",
            });
        }

        function bindAllStudenteInlineSex() {
            document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }
                bindStudenteInlineSex(row);
            });
        }

        function countPersistedRows(tableId) {
            return inlineFormsets.countPersistedRows(tableId);
        }

        function refreshTabCounts() {
            const documentiRows = countPersistedRows("documenti-table");
            const tabDocumenti = document.querySelector('[data-tab-target="tab-documenti"]');
            if (tabDocumenti) tabDocumenti.textContent = `Documenti (${documentiRows})`;
            const tabParenti = document.querySelector('[data-tab-target="tab-parenti"]');
            if (tabParenti) {
                const parentiCards = document.querySelectorAll("[data-relative-card-list] [data-relative-card]").length;
                const tabLabel = inlineTabs.inlineLabelFromTabButton(tabParenti);
                tabParenti.textContent = `${tabLabel} (${parentiCards})`;
            }
            const studentiHeading = document.getElementById("familiare-studenti-heading");
            if (studentiHeading && document.getElementById("studenti-table")) {
                const n = countPersistedRows("studenti-table");
                const tabStudenti = document.querySelector('[data-tab-target="tab-studenti"]');
                if (tabStudenti) {
                    const tabLabel = inlineTabs.inlineLabelFromTabButton(tabStudenti);
                    tabStudenti.textContent = `${tabLabel} (${n})`;
                }
                const label = studentiHeading.dataset.baseLabel || studentiHeading.textContent.replace(/\s*\(\d+\)\s*$/, "").trim();
                studentiHeading.dataset.baseLabel = label;
                studentiHeading.textContent = `${label} (${n})`;
            }
        }

        function createInlineManager(prefix, options) {
            return inlineFormsets.createManager({
                prefix: prefix,
                prepareOptions: options && options.prepareOptions ? options.prepareOptions : {},
                mountOptions: options && options.mountOptions ? options.mountOptions : {},
                removeOptions: options && options.removeOptions ? options.removeOptions : {},
            });
        }

        function refreshFirstStudentAddMode() {
            const form = document.getElementById("familiare-detail-form");
            if (!form) {
                return;
            }

            form.classList.toggle(
                "is-inline-first-student-add-mode",
                Boolean(document.querySelector("#studenti-table .is-inline-first-student-add-row"))
            );
        }

        function markFirstStudentAddRows(mounted, enabled) {
            if (!mounted || !mounted.state || !mounted.state.bundle) {
                refreshFirstStudentAddMode();
                return;
            }

            mounted.state.bundle.forEach(function (node) {
                if (node) {
                    node.classList.toggle("is-inline-first-student-add-row", Boolean(enabled));
                }
            });
            refreshFirstStudentAddMode();
        }

        const inlineManagers = {
            parenti: createInlineManager("parenti", {
                prepareOptions: {
                    companionClasses: ["inline-subform-row"],
                    includeCompanionRowsInData: true,
                    ignoreSelects: true,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
                    appendOnly: false,
                    enableInputs: true,
                    onReady: function (state) {
                        const row = state.row;
                        const subformRow = getFamiliareSubformRow(row);
                        wireInlineRelatedButtons(row);
                        formTools.initSearchableSelects(row);
                        formTools.initCodiceFiscale(row);
                        if (subformRow) {
                            formTools.initSearchableSelects(subformRow);
                            formTools.initCodiceFiscale(subformRow);
                        }
                        personRules.bindSexFromRelation({
                            relationSelect: row.querySelector('select[name$="-relazione_familiare"]'),
                            sexSelect: subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null,
                            bindFlag: "parentiRelationSexBound",
                        });
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-subform-row"],
                },
            }),
            studenti: createInlineManager("studenti", {
                prepareOptions: {
                    companionClasses: ["inline-subform-row"],
                    includeCompanionRowsInData: true,
                    ignoreSelects: true,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
                    appendOnly: function () {
                        return countPersistedRows("studenti-table") > 0;
                    },
                    enableInputs: true,
                    onReady: function (state) {
                        const row = state.row;
                        wireInlineRelatedButtons(row);
                        formTools.initSearchableSelects(row);
                        const subformRow = state.companionRows[0] || getFamiliareSubformRow(row);
                        if (subformRow) {
                            formTools.initSearchableSelects(subformRow);
                            formTools.initCodiceFiscale(subformRow);
                        }
                        studentiInlineAddressCollection.bindTracking(row);
                        formTools.initCodiceFiscale(row);
                        bindStudenteInlineSex(row);
                        studentiInlineAddressDefaults.syncRows();
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-subform-row"],
                },
            }),
            documenti: createInlineManager("documenti", {
                mountOptions: {
                    enableInputs: true,
                    onReady: function (state) {
                        wireInlineRelatedButtons(state.row);
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
            }),
        };

        const relativePageLockMessage = "Salva o annulla le modifiche in corso prima di usare altre funzioni della pagina.";

        function getFamiliareForm() {
            return document.getElementById("familiare-detail-form");
        }

        function getMainCard() {
            return document.querySelector("[data-relative-main-card]");
        }

        function getActiveMainEditorCard() {
            return document.querySelector("[data-relative-main-card].is-card-editing");
        }

        function getActiveRelativePageEditContext() {
            const mainCard = getActiveMainEditorCard();
            if (mainCard) {
                return {
                    kind: "main",
                    target: "main",
                    card: mainCard,
                    editor: mainCard.querySelector(".relative-main-card-editor"),
                    message: relativePageLockMessage,
                };
            }

            const studentCard = document.querySelector("[data-student-card].is-card-editing");
            if (studentCard) {
                return {
                    kind: "student-card",
                    target: "studenti",
                    card: studentCard,
                    editor: studentCard.querySelector(".family-student-card-editor"),
                    message: relativePageLockMessage,
                };
            }

            const relativeCard = document.querySelector("[data-relative-card].is-card-editing");
            if (relativeCard) {
                return {
                    kind: "relative-card",
                    target: "parenti",
                    card: relativeCard,
                    editor: relativeCard.querySelector(".family-relative-card-editor"),
                    message: relativePageLockMessage,
                };
            }

            const documentCard = document.querySelector("[data-document-card].is-card-editing");
            if (documentCard) {
                return {
                    kind: "document-card",
                    target: "documenti",
                    card: documentCard,
                    editor: documentCard.querySelector(".family-document-card-editor"),
                    message: relativePageLockMessage,
                };
            }

            return null;
        }

        function setRelativeCardLockElement(element, locked, message) {
            if (!element) {
                return;
            }

            if (locked) {
                if (element.dataset.cardLockOriginalTitleStored !== "1") {
                    element.dataset.cardLockOriginalTitleStored = "1";
                    element.dataset.cardLockOriginalTitle = element.getAttribute("title") || "";
                }
                element.classList.add("family-card-action-locked");
                element.dataset.relativePageCardLock = "1";
                element.dataset.cardLockMessage = message || relativePageLockMessage;
                element.setAttribute("title", message || relativePageLockMessage);
                return;
            }

            if (element.dataset.relativePageCardLock !== "1") {
                return;
            }

            delete element.dataset.relativePageCardLock;
            element.classList.remove("family-card-action-locked", "is-showing-lock");
            delete element.dataset.cardLockMessage;

            if (element.dataset.cardLockOriginalTitleStored === "1") {
                if (element.dataset.cardLockOriginalTitle) {
                    element.setAttribute("title", element.dataset.cardLockOriginalTitle);
                } else {
                    element.removeAttribute("title");
                }
                delete element.dataset.cardLockOriginalTitle;
                delete element.dataset.cardLockOriginalTitleStored;
            } else {
                element.removeAttribute("title");
            }
        }

        function showRelativeCardLockMessage(element, message) {
            const target = element && element.closest
                ? element.closest("button, a, .tab-btn, .family-person-card, .family-document-card, [data-row-href]") || element
                : element;

            if (!target) {
                return;
            }

            setRelativeCardLockElement(target, true, message || relativePageLockMessage);
            target.classList.remove("is-showing-lock");
            void target.offsetWidth;
            target.classList.add("is-showing-lock");

            window.clearTimeout(target.__relativePageCardLockTimer);
            target.__relativePageCardLockTimer = window.setTimeout(function () {
                target.classList.remove("is-showing-lock");
            }, 2200);
        }

        function isAllowedDuringRelativeCardEdit(target, context) {
            if (!target || !context) {
                return true;
            }

            if (context.editor && context.editor.contains(target)) {
                return true;
            }

            if (target.closest && target.closest("#relative-card-sticky-actions, .app-dialog, .app-dialog-overlay")) {
                return true;
            }

            return false;
        }

        function resolveRelativeCardLockTrigger(target) {
            return target && target.closest
                ? target.closest("a[href], button, input[type='submit'], input[type='button'], [role='button'], summary, .tab-btn, [data-row-href]")
                : null;
        }

        function refreshRelativeCardStickyActions() {
            const form = getFamiliareForm();
            const context = getActiveRelativePageEditContext();
            const shouldShow = Boolean(context);
            const menu = document.getElementById("relative-card-sticky-actions");
            const spacer = document.getElementById("relative-card-sticky-spacer");
            const title = menu ? menu.querySelector("[data-relative-card-sticky-title]") : null;
            const saveButton = document.getElementById("relative-card-sticky-save");

            if (!menu) {
                return;
            }

            menu.hidden = !shouldShow;
            menu.classList.toggle("is-hidden", !shouldShow);
            if (spacer) {
                spacer.hidden = !shouldShow;
                spacer.classList.toggle("is-hidden", !shouldShow);
            }
            if (form) {
                form.classList.toggle("has-relative-card-sticky-actions", shouldShow);
            }
            if (title && shouldShow) {
                const editorTitle = context && context.editor ? context.editor.querySelector("h3") : null;
                title.textContent = editorTitle && editorTitle.textContent.trim()
                    ? editorTitle.textContent.trim()
                    : "Modifica dati principali";
            }
            if (saveButton) {
                delete saveButton.dataset.relativeMainSubmit;
                delete saveButton.dataset.cardInlineSubmit;
                if (shouldShow && context.kind === "main") {
                    saveButton.dataset.relativeMainSubmit = "1";
                } else if (shouldShow && context.target) {
                    saveButton.dataset.cardInlineSubmit = context.target;
                }
            }
        }

        function refreshRelativePageActionLocks() {
            const context = getActiveRelativePageEditContext();
            const locked = Boolean(context);

            refreshRelativeCardStickyActions();

            document.querySelectorAll(".family-card-action-locked[data-relative-page-card-lock='1']").forEach(function (element) {
                setRelativeCardLockElement(element, false);
            });

            if (!locked) {
                return;
            }

            document.querySelectorAll("a[href], button, input[type='submit'], input[type='button'], [role='button'], summary, .tab-btn, [data-row-href]").forEach(function (element) {
                if (isAllowedDuringRelativeCardEdit(element, context)) {
                    return;
                }

                setRelativeCardLockElement(element, true, context.message);
            });
        }

        function bindRelativePageActionLock() {
            const form = getFamiliareForm();
            if (!form || form.dataset.relativePageActionLockBound === "1") {
                return;
            }

            form.dataset.relativePageActionLockBound = "1";

            document.addEventListener("click", function (event) {
                const context = getActiveRelativePageEditContext();
                const trigger = resolveRelativeCardLockTrigger(event.target);

                if (!context || !trigger || isAllowedDuringRelativeCardEdit(trigger, context)) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                showRelativeCardLockMessage(trigger, context.message);
            }, true);

            document.addEventListener("keydown", function (event) {
                if (event.key !== "Enter" && event.key !== " ") {
                    return;
                }

                const context = getActiveRelativePageEditContext();
                const trigger = resolveRelativeCardLockTrigger(event.target);

                if (!context || !trigger || isAllowedDuringRelativeCardEdit(trigger, context)) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                showRelativeCardLockMessage(trigger, context.message);
            }, true);
        }

        function rememberEditorNode(editor, node) {
            if (!editor || !node) {
                return;
            }

            if (!node.__relativeDetailRestore) {
                node.__relativeDetailRestore = {
                    parent: node.parentNode,
                    nextSibling: node.nextSibling,
                    className: node.className,
                };
            }

            if (!editor.__relativeDetailMovedNodes) {
                editor.__relativeDetailMovedNodes = [];
            }
            if (!editor.__relativeDetailMovedNodes.includes(node)) {
                editor.__relativeDetailMovedNodes.push(node);
            }
        }

        function restoreEditorNodes(editor) {
            const movedNodes = editor && editor.__relativeDetailMovedNodes ? editor.__relativeDetailMovedNodes : [];

            movedNodes.slice().reverse().forEach(function (node) {
                const restore = node.__relativeDetailRestore;
                if (!restore || !restore.parent) {
                    return;
                }

                const nextSibling = restore.nextSibling && restore.nextSibling.parentNode === restore.parent
                    ? restore.nextSibling
                    : null;
                restore.parent.insertBefore(node, nextSibling);
                if (typeof restore.className === "string") {
                    node.className = restore.className;
                }
                delete node.__relativeDetailRestore;
            });

            if (editor) {
                editor.__relativeDetailMovedNodes = [];
            }
        }

        function snapshotFields(roots) {
            return (roots || []).filter(Boolean).flatMap(function (root) {
                return Array.from(root.querySelectorAll("input, select, textarea")).map(function (field) {
                    const type = (field.type || "").toLowerCase();
                    return {
                        field: field,
                        checked: type === "checkbox" || type === "radio" ? field.checked : null,
                        value: field.value,
                    };
                });
            });
        }

        function restoreFieldSnapshot(snapshot) {
            (snapshot || []).forEach(function (item) {
                const field = item.field;
                if (!field) {
                    return;
                }

                const type = (field.type || "").toLowerCase();
                if (type === "checkbox" || type === "radio") {
                    field.checked = Boolean(item.checked);
                } else {
                    field.value = item.value;
                }

                field.dispatchEvent(new Event("input", { bubbles: true }));
                field.dispatchEvent(new Event("change", { bubbles: true }));
            });
        }

        function setFieldsEnabled(root, enabled) {
            if (!root) {
                return;
            }

            root.querySelectorAll("input, textarea, select").forEach(function (field) {
                const type = (field.type || "").toLowerCase();
                field.disabled = !enabled;
                if (type !== "hidden") {
                    field.readOnly = !enabled;
                }
                if (enabled) {
                    field.classList.remove("submit-safe-locked");
                    field.removeAttribute("aria-disabled");
                    field.removeAttribute("tabindex");
                }
            });
        }

        function iconHtml(symbolName, label) {
            const sprite = config.uiIconsSprite || "/static/images/arboris-ui-icons.svg";
            return `<span class="btn-icon" aria-hidden="true"><svg><use href="${sprite}#${symbolName}"></use></svg></span><span class="btn-label">${label}</span>`;
        }

        function relatedIconHtml(symbolName) {
            const sprite = config.uiIconsSprite || "/static/images/arboris-ui-icons.svg";
            return `<span class="related-btn-icon" aria-hidden="true"><svg><use href="${sprite}#${symbolName}"></use></svg></span>`;
        }

        function decorateRelatedButtons(root, label) {
            const noun = label || "valore";
            if (!root) {
                return;
            }

            root.querySelectorAll(".related-btn").forEach(function (button) {
                const isAdd = button.classList.contains("related-btn-add");
                const isEdit = button.classList.contains("related-btn-edit");
                const actionLabel = isAdd ? `Nuovo ${noun}` : isEdit ? `Modifica ${noun}` : `Elimina ${noun}`;
                const iconName = isAdd ? "plus" : isEdit ? "edit" : "trash";
                button.setAttribute("aria-label", actionLabel);
                button.setAttribute("title", actionLabel);
                button.dataset.floatingText = actionLabel;
                button.innerHTML = relatedIconHtml(iconName);
            });
        }

        function createEditorField(labelText, nodes, extraClass, editor) {
            const resolvedNodes = Array.isArray(nodes) ? nodes.filter(Boolean) : [nodes].filter(Boolean);
            if (!resolvedNodes.length) {
                return null;
            }

            const field = document.createElement("div");
            field.className = `family-student-editor-field${extraClass ? " " + extraClass : ""}`;

            if (labelText) {
                const label = document.createElement("label");
                const input = resolvedNodes
                    .map(function (node) {
                        return node.matches && node.matches("input, select, textarea")
                            ? node
                            : node.querySelector && node.querySelector("input, select, textarea");
                    })
                    .find(Boolean);
                label.textContent = labelText;
                if (input && input.id) {
                    label.setAttribute("for", input.id);
                }
                field.appendChild(label);
            }

            resolvedNodes.forEach(function (node) {
                rememberEditorNode(editor, node);
                field.appendChild(node);
            });
            return field;
        }

        function appendInputField(grid, root, selector, labelText, extraClass, editor) {
            const input = root ? root.querySelector(selector) : null;
            const content = input ? input.closest(".mode-edit-field") || input.closest(".inline-details-field") || input : null;
            const field = createEditorField(labelText, content, extraClass, editor);

            if (field) {
                grid.appendChild(field);
            }
        }

        function appendRelatedField(grid, root, selector, labelText, extraClass, editor, relatedLabel, options) {
            const cfg = options || {};
            const input = root ? root.querySelector(selector) : null;
            const relatedField = input ? input.closest(".inline-related-field, .related-field-row") : null;
            const helpNode = cfg.helpSelector && root ? root.querySelector(cfg.helpSelector) : null;
            const field = createEditorField(
                labelText,
                relatedField ? [relatedField, helpNode] : (input ? input.closest(".mode-edit-field") || input : null),
                extraClass,
                editor
            );

            if (relatedField) {
                relatedField.classList.add("family-card-editor-related-control");
                if (cfg.addressControl) {
                    relatedField.classList.add("family-student-editor-address-control");
                }
                decorateRelatedButtons(relatedField, relatedLabel || labelText.toLowerCase());
            }

            if (field) {
                grid.appendChild(field);
            }
        }

        function appendCheckboxField(grid, root, selector, labelText, extraClass, editor) {
            const input = root ? root.querySelector(selector) : null;
            if (!input) {
                return;
            }

            rememberEditorNode(editor, input);
            const field = document.createElement("div");
            field.className = `family-student-editor-field family-student-editor-field-check${extraClass ? " " + extraClass : ""}`;

            const label = document.createElement("label");
            label.className = "family-student-editor-check";
            label.appendChild(input);
            const text = document.createElement("span");
            text.textContent = labelText;
            label.appendChild(text);

            field.appendChild(label);
            grid.appendChild(field);
        }

        function initEditorEnhancements(editor) {
            if (formTools && typeof formTools.initSearchableSelects === "function") {
                formTools.initSearchableSelects(editor);
            }
            if (formTools && typeof formTools.initCodiceFiscale === "function") {
                formTools.initCodiceFiscale(editor);
            }
            wireInlineRelatedButtons(editor);
            bindStandaloneSexFromRelazioneFamiliare();
            setFieldsEnabled(editor, true);
            updateMainButtons();
        }

        function markRelativeMainSubmitPending() {
            const form = getFamiliareForm();
            const modeInput = document.getElementById("familiare-edit-scope");

            if (form) {
                form.dataset.pendingRelativeMainSubmit = "1";
            }
            if (modeInput) {
                modeInput.value = "full";
            }
        }

        function buildRelativeMainCardEditor(card) {
            const formRoot = document.getElementById("familiare-lock-container");
            if (!card || !formRoot) {
                return null;
            }

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor relative-main-card-editor";
            editor.__relativeDetailFieldSnapshot = snapshotFields([formRoot]);

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = "Modifica dati principali";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            appendRelatedField(grid, formRoot, "#id_famiglia", "Famiglia", "family-student-editor-field-half relative-main-family-field", editor, "famiglia");
            appendRelatedField(grid, formRoot, "#id_relazione_familiare", "Parentela", "family-student-editor-field-third relative-main-parentela-field", editor, "parentela");
            appendInputField(grid, formRoot, "#id_nome", "Nome", "family-student-editor-field-half", editor);
            appendInputField(grid, formRoot, "#id_cognome", "Cognome", "family-student-editor-field-half", editor);
            appendInputField(grid, formRoot, "#id_telefono", "Telefono", "family-student-editor-field-third", editor);
            appendInputField(grid, formRoot, "#id_email", "Email", "family-student-editor-field-half", editor);
            appendInputField(grid, formRoot, "#id_data_nascita", "Data nascita", "family-student-editor-field-third", editor);
            appendInputField(grid, formRoot, "#id_sesso", "Sesso", "family-student-editor-field-third", editor);
            appendInputField(grid, formRoot, "#id_luogo_nascita_search", "Luogo nascita", "family-student-editor-field-wide", editor);
            appendInputField(grid, formRoot, "#id_nazionalita", "Nazionalita", "family-student-editor-field-third", editor);
            appendInputField(grid, formRoot, "#id_codice_fiscale", "Codice fiscale", "family-student-editor-field-third", editor);
            appendRelatedField(grid, formRoot, "#id_indirizzo", "Indirizzo", "family-student-editor-field-wide family-student-editor-address-field", editor, "indirizzo", {
                helpSelector: "#familiare-address-help",
                addressControl: true,
            });
            appendCheckboxField(grid, formRoot, "#id_convivente", "Convivente", "", editor);
            appendCheckboxField(grid, formRoot, "#id_referente_principale", "Referente principale", "", editor);
            appendCheckboxField(grid, formRoot, "#id_abilitato_scambio_retta", "Scambio retta", "", editor);
            appendCheckboxField(grid, formRoot, "#id_attivo", "Attivo", "", editor);

            editor.appendChild(grid);

            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.name = "_save";
            saveButton.className = "btn btn-save-soft btn-sm btn-icon-text";
            saveButton.dataset.relativeMainSubmit = "1";
            saveButton.innerHTML = iconHtml("check", "Salva");
            saveButton.addEventListener("click", markRelativeMainSubmitPending);

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.relativeMainAction = "cancel";
            cancelButton.innerHTML = iconHtml("chevron-left", "Annulla modifiche");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            editor.appendChild(actions);

            card.appendChild(editor);
            card.classList.add("is-card-editing");
            card.dataset.relativeMainEditing = "1";
            initEditorEnhancements(editor);
            wireRelativeMainCardActions(editor);
            refreshRelativePageActionLocks();
            syncRelativeViewSideHeight();
            return editor;
        }

        function openRelativeMainCardEditor(trigger) {
            const card = getMainCard();
            if (!card) {
                return;
            }

            const context = getActiveRelativePageEditContext();
            if (context && context.kind !== "main") {
                showRelativeCardLockMessage(trigger || card, context.message);
                return;
            }

            const existingEditor = card.querySelector(".relative-main-card-editor");
            if (existingEditor) {
                const field = existingEditor.querySelector("#id_nome, input[type='text']:not(.searchable-select-input), input[type='email'], textarea");
                if (field) field.focus();
                return;
            }

            const editor = buildRelativeMainCardEditor(card);
            const field = editor ? editor.querySelector("#id_nome, input[type='text']:not(.searchable-select-input), input[type='email'], textarea") : null;
            if (field) field.focus();
        }

        function closeRelativeMainCardEditor(options) {
            const cfg = options || {};
            const card = getActiveMainEditorCard();
            const editor = card ? card.querySelector(".relative-main-card-editor") : null;

            if (!card || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreFieldSnapshot(editor.__relativeDetailFieldSnapshot);
            }

            restoreEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            delete card.dataset.relativeMainEditing;
            const form = getFamiliareForm();
            if (form) {
                delete form.dataset.pendingRelativeMainSubmit;
            }
            setFieldsEnabled(document.getElementById("familiare-lock-container"), false);
            refreshRelativePageActionLocks();
            updateMainButtons();
            syncRelativeViewSideHeight();
        }

        function wireRelativeMainCardActions(root) {
            const container = root || document;
            if (!container || typeof container.querySelectorAll !== "function") {
                return;
            }

            container.querySelectorAll("[data-relative-main-action]").forEach(function (element) {
                if (element.dataset.relativeMainActionBound === "1") {
                    return;
                }

                element.dataset.relativeMainActionBound = "1";
                element.addEventListener("click", function (event) {
                    const action = element.dataset.relativeMainAction || "";

                    event.preventDefault();
                    event.stopPropagation();

                    if (action === "edit") {
                        openRelativeMainCardEditor(element);
                    } else if (action === "cancel") {
                        closeRelativeMainCardEditor({ restoreValues: true });
                    }
                });
            });
        }

        function bindRelativeCardStickyActions() {
            const saveButton = document.getElementById("relative-card-sticky-save");
            const cancelButton = document.getElementById("relative-card-sticky-cancel");

            if (saveButton && saveButton.dataset.relativeCardStickySaveBound !== "1") {
                saveButton.dataset.relativeCardStickySaveBound = "1";
                saveButton.addEventListener("click", function () {
                    const context = getActiveRelativePageEditContext();
                    const modeInput = document.getElementById("familiare-edit-scope");
                    const targetInput = document.getElementById("familiare-inline-target");

                    if (!context) {
                        return;
                    }

                    if (context.kind === "main") {
                        markRelativeMainSubmitPending();
                        return;
                    }

                    if (modeInput) {
                        modeInput.value = "inline";
                    }
                    if (targetInput && context.target) {
                        targetInput.value = context.target;
                    }
                });
            }

            if (cancelButton && cancelButton.dataset.relativeCardStickyCancelBound !== "1") {
                cancelButton.dataset.relativeCardStickyCancelBound = "1";
                cancelButton.addEventListener("click", function (event) {
                    const context = getActiveRelativePageEditContext();
                    event.preventDefault();

                    if (!context || context.kind === "main") {
                        closeRelativeMainCardEditor({ restoreValues: true });
                    } else if (context.kind === "student-card") {
                        cancelStudentCardEditor(context.card);
                    } else if (context.kind === "relative-card") {
                        cancelRelativeCardEditor(context.card);
                    } else if (context.kind === "document-card") {
                        cancelDocumentCardEditor(context.card);
                    }
                });
            }
        }

        function bindRelativeMainSubmitScope() {
            const form = getFamiliareForm();
            if (!form || form.dataset.relativeMainSubmitScopeBound === "1") {
                return;
            }

            form.dataset.relativeMainSubmitScopeBound = "1";
            window.setTimeout(function () {
                form.addEventListener("submit", function (event) {
                    const submitter = event.submitter;
                    const activeEditor = document.activeElement && document.activeElement.closest
                        ? document.activeElement.closest(".relative-main-card-editor, .family-student-card-editor")
                        : null;
                    const inlineCardSubmitTarget =
                        (submitter && submitter.dataset.cardInlineSubmit) ||
                        (
                            activeEditor && !activeEditor.classList.contains("relative-main-card-editor")
                                ? (
                                    activeEditor.classList.contains("family-relative-card-editor")
                                        ? "parenti"
                                        : activeEditor.classList.contains("family-document-card-editor")
                                            ? "documenti"
                                            : "studenti"
                                )
                                : ""
                        );
                    const shouldUseMainScope = Boolean(
                        (submitter && (
                            submitter.dataset.relativeMainSubmit === "1"
                        )) ||
                        form.dataset.pendingRelativeMainSubmit === "1" ||
                        (activeEditor && activeEditor.classList.contains("relative-main-card-editor"))
                    );

                    if (!shouldUseMainScope) {
                        if (!inlineCardSubmitTarget) {
                            return;
                        }

                        const modeInput = document.getElementById("familiare-edit-scope");
                        const targetInput = document.getElementById("familiare-inline-target");
                        if (modeInput) {
                            modeInput.value = "inline";
                        }
                        if (targetInput) {
                            targetInput.value = inlineCardSubmitTarget;
                        }
                        return;
                    }

                    const modeInput = document.getElementById("familiare-edit-scope");
                    if (modeInput) {
                        modeInput.value = "full";
                    }
                    delete form.dataset.pendingRelativeMainSubmit;
                });
            }, 0);
        }

        function getStudentCardList() {
            return document.querySelector("[data-student-card-list]");
        }

        function getRelativeCardList() {
            return document.querySelector("[data-relative-card-list]");
        }

        function getDocumentCardList() {
            return document.querySelector("[data-document-card-list]");
        }

        function getRowFromCard(card, prefixName) {
            const prefix = card ? card.dataset[prefixName] || "" : "";
            if (!prefix) {
                return null;
            }

            const idInput = document.getElementById(`id_${prefix}-id`);
            return idInput ? idInput.closest("tr.inline-form-row") : null;
        }

        function getStudentRowFromCard(card) {
            return getRowFromCard(card, "studentFormPrefix");
        }

        function getRelativeRowFromCard(card) {
            return getRowFromCard(card, "relativeFormPrefix");
        }

        function getDocumentRowFromCard(card) {
            return getRowFromCard(card, "documentFormPrefix");
        }

        function getInlinePrefixFromRow(row) {
            const idInput = row ? row.querySelector('input[type="hidden"][name$="-id"]') : null;
            const name = idInput ? idInput.name || "" : "";
            return name.endsWith("-id") ? name.slice(0, -3) : "";
        }

        function focusCardEditor(editor) {
            const field = editor ? editor.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea") : null;
            if (field && typeof field.focus === "function") {
                field.focus();
            }
        }

        function appendSubformField(grid, subformRow, selector, extraClass, editor) {
            const input = subformRow ? subformRow.querySelector(selector) : null;
            const field = input ? input.closest(".inline-subform-field") : null;
            if (!field) {
                return;
            }

            rememberEditorNode(editor, field);
            field.classList.add("family-student-editor-field");
            if (extraClass) {
                field.classList.add(extraClass);
            }
            grid.appendChild(field);
        }

        function appendCardAddressField(grid, row, editor, selector) {
            const addressCell = row ? row.querySelector(selector || ".inline-studente-address-cell, .inline-family-address-cell") : null;
            const relatedField = addressCell ? addressCell.querySelector(".inline-related-field") : null;
            const helpNode = addressCell ? addressCell.querySelector('[data-role="address-help"]') : null;

            if (!relatedField) {
                return;
            }

            const field = createEditorField("Indirizzo", [relatedField, helpNode], "family-student-editor-field-wide family-student-editor-address-field", editor);
            relatedField.classList.add("family-card-editor-related-control", "family-student-editor-address-control");
            decorateRelatedButtons(relatedField, "indirizzo");
            if (field) {
                grid.appendChild(field);
            }
        }

        function setRowBundleEnabled(row, enabled) {
            inlineFormsets.setRowInputsEnabled(row, enabled, {
                includeCompanionRows: true,
                companionClasses: ["inline-subform-row"],
                skipHiddenInputs: false,
            });
        }

        function createPersonCardAvatar(list, kind) {
            const avatar = document.createElement("span");
            const sprite = list ? list.dataset.avatarSprite || "" : "";
            const symbol = kind === "relative" ? "avatar-man" : "avatar-child";
            avatar.className = kind === "relative"
                ? "family-person-avatar family-person-avatar-relative"
                : "family-person-avatar family-person-avatar-student";
            avatar.setAttribute("aria-hidden", "true");
            avatar.innerHTML = `<svg viewBox="0 0 96 96" focusable="false"><use href="${sprite}#${symbol}"></use></svg>`;
            return avatar;
        }

        function createDocumentCardIcon(list) {
            const icon = document.createElement("span");
            const sprite = list ? list.dataset.uiIconsSprite || config.uiIconsSprite || "/static/images/arboris-ui-icons.svg" : config.uiIconsSprite || "/static/images/arboris-ui-icons.svg";
            icon.className = "family-document-icon";
            icon.setAttribute("aria-hidden", "true");
            icon.innerHTML = `<svg><use href="${sprite}#document"></use></svg>`;
            return icon;
        }

        function buildStudentCardEditor(card, row, options) {
            const cfg = options || {};
            const subformRow = getFamiliareSubformRow(row);

            setRowBundleEnabled(row, true);

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor";
            editor.__relativeDetailFieldSnapshot = snapshotFields([row, subformRow]);

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica studente";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            appendInputField(grid, row, 'input[name$="-nome"]', "Nome", "family-student-editor-field-half", editor);
            appendInputField(grid, row, 'input[name$="-cognome"]', "Cognome", "family-student-editor-field-half", editor);
            appendSubformField(grid, subformRow, 'select[name$="-sesso"]', "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-data_nascita"]', "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-luogo_nascita_search"]', "family-student-editor-field-wide", editor);
            appendSubformField(grid, subformRow, 'select[name$="-nazionalita"]', "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-codice_fiscale"]', "family-student-editor-field-third", editor);
            appendCardAddressField(grid, row, editor, ".inline-studente-address-cell");
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-attivo"]', "Attivo", "", editor);

            editor.appendChild(grid);
            editor.appendChild(createCardActions("studenti", "student"));
            card.appendChild(editor);
            card.classList.add("is-card-editing");
            initEditorEnhancements(editor);
            wireStudentCardActions(editor);
            refreshRelativePageActionLocks();
            return editor;
        }

        function buildRelativeCardEditor(card, row, options) {
            const cfg = options || {};
            const subformRow = getFamiliareSubformRow(row);

            setRowBundleEnabled(row, true);

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor family-relative-card-editor";
            editor.__relativeDetailFieldSnapshot = snapshotFields([row, subformRow]);

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica familiare";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            appendInputField(grid, row, 'input[name$="-nome"]', "Nome", "family-student-editor-field-half", editor);
            appendInputField(grid, row, 'input[name$="-cognome"]', "Cognome", "family-student-editor-field-half", editor);
            appendRelatedField(grid, row, 'select[name$="-relazione_familiare"]', "Parentela", "family-student-editor-field-third", editor, "parentela");
            appendInputField(grid, row, 'input[name$="-telefono"]', "Telefono", "family-student-editor-field-third", editor);
            appendInputField(grid, row, 'input[name$="-email"]', "Email", "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'select[name$="-sesso"]', "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-data_nascita"]', "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-luogo_nascita_search"]', "family-student-editor-field-wide", editor);
            appendSubformField(grid, subformRow, 'select[name$="-nazionalita"]', "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-codice_fiscale"]', "family-student-editor-field-third", editor);
            appendCardAddressField(grid, row, editor, ".inline-family-address-cell");
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-convivente"]', "Convivente", "", editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-referente_principale"]', "Referente principale", "", editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-abilitato_scambio_retta"]', "Scambio retta", "", editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-attivo"]', "Attivo", "", editor);

            editor.appendChild(grid);
            editor.appendChild(createCardActions("parenti", "relative"));
            card.appendChild(editor);
            card.classList.add("is-card-editing");
            initEditorEnhancements(editor);
            personRules.bindSexFromRelation({
                relationSelect: row.querySelector('select[name$="-relazione_familiare"]'),
                sexSelect: subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null,
                bindFlag: "parentiRelationSexBound",
            });
            wireRelativeCardActions(editor);
            refreshRelativePageActionLocks();
            return editor;
        }

        function buildDocumentCardEditor(card, row, options) {
            const cfg = options || {};
            inlineFormsets.setRowInputsEnabled(row, true, { skipHiddenInputs: false });

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor family-document-card-editor";
            editor.__relativeDetailFieldSnapshot = snapshotFields([row]);

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica documento";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            appendRelatedField(grid, row, 'select[name$="-tipo_documento"]', "Tipo documento", "family-student-editor-field-half", editor, "tipo documento");
            appendInputField(grid, row, 'textarea[name$="-descrizione"]', "Descrizione", "family-student-editor-field-wide", editor);
            appendInputField(grid, row, 'input[type="file"][name$="-file"]', "File", "family-student-editor-field-wide", editor);
            appendInputField(grid, row, 'input[name$="-scadenza"]', "Scadenza", "family-student-editor-field-third", editor);
            appendInputField(grid, row, 'textarea[name$="-note"]', "Note", "family-student-editor-field-wide", editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-visibile"]', "Visibile", "", editor);

            editor.appendChild(grid);
            editor.appendChild(createCardActions("documenti", "document"));
            card.appendChild(editor);
            card.classList.add("is-card-editing");
            initEditorEnhancements(editor);
            wireDocumentCardActions(editor);
            refreshRelativePageActionLocks();
            return editor;
        }

        function createCardActions(target, kind) {
            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.name = "_save";
            saveButton.className = "btn btn-save-soft btn-sm btn-icon-text";
            saveButton.dataset.cardInlineSubmit = target;
            saveButton.innerHTML = iconHtml("check", "Salva");

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset[`${kind}CardAction`] = "cancel";
            cancelButton.innerHTML = iconHtml("chevron-left", "Annulla modifiche");

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "btn btn-danger btn-sm btn-icon-text family-student-card-remove";
            removeButton.dataset[`${kind}CardAction`] = "remove";
            removeButton.innerHTML = iconHtml("trash", "Rimuovi");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            actions.appendChild(removeButton);
            return actions;
        }

        function addCardInlineForm(prefix) {
            const manager = inlineManagers[prefix];
            if (!manager) {
                return null;
            }

            setInlineTarget(prefix);
            activatePanelIfPresent(`tab-${prefix}`);
            const mounted = manager.add();
            if (mounted && mounted.state) {
                inlineFormsets.markBundleForAddOnlyEdit(mounted.state, {
                    form: "familiare-detail-form",
                });
            }
            refreshTabCounts();
            return mounted;
        }

        function openStudentCardEditor(card) {
            if (!card) return;
            const existingEditor = card.querySelector(".family-student-card-editor");
            if (existingEditor) {
                focusCardEditor(existingEditor);
                return;
            }
            const row = getStudentRowFromCard(card);
            const titleNode = card.querySelector(".family-person-heading h3");
            const title = titleNode ? `Modifica ${titleNode.textContent.trim()}` : "Modifica studente";
            focusCardEditor(buildStudentCardEditor(card, row, { title: title }));
        }

        function openRelativeCardEditor(card) {
            if (!card) return;
            const existingEditor = card.querySelector(".family-relative-card-editor");
            if (existingEditor) {
                focusCardEditor(existingEditor);
                return;
            }
            const row = getRelativeRowFromCard(card);
            const titleNode = card.querySelector(".family-person-heading h3");
            const title = titleNode ? `Modifica ${titleNode.textContent.trim()}` : "Modifica familiare";
            focusCardEditor(buildRelativeCardEditor(card, row, { title: title }));
        }

        function openDocumentCardEditor(card) {
            if (!card) return;
            const existingEditor = card.querySelector(".family-document-card-editor");
            if (existingEditor) {
                focusCardEditor(existingEditor);
                return;
            }
            const row = getDocumentRowFromCard(card);
            const titleNode = card.querySelector(".family-document-main h3");
            const title = titleNode ? `Modifica ${titleNode.textContent.trim()}` : "Modifica documento";
            focusCardEditor(buildDocumentCardEditor(card, row, { title: title }));
        }

        function addStudentCardFromView(trigger) {
            const list = getStudentCardList();
            const mounted = addCardInlineForm("studenti");
            const row = mounted && mounted.state ? mounted.state.row : null;
            const prefix = getInlinePrefixFromRow(row);
            if (!list || !row || !prefix) return;

            const card = document.createElement("article");
            card.className = "family-person-card family-student-card family-student-card-new is-card-editing";
            card.dataset.studentCard = "1";
            card.dataset.studentFormPrefix = prefix;
            card.appendChild(createPersonCardAvatar(list, "student"));
            list.insertBefore(card, list.querySelector(".family-dashed-add") || null);
            focusCardEditor(buildStudentCardEditor(card, row, { title: list.dataset.studentNewTitle || "Nuovo studente" }));
            syncCardEmptyStates();
            if (trigger && card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "center" });
        }

        function addRelativeCardFromView(trigger) {
            const list = getRelativeCardList();
            const mounted = addCardInlineForm("parenti");
            const row = mounted && mounted.state ? mounted.state.row : null;
            const prefix = getInlinePrefixFromRow(row);
            if (!list || !row || !prefix) return;

            const card = document.createElement("article");
            card.className = "family-person-card family-relative-card family-relative-card-new is-card-editing";
            card.dataset.relativeCard = "1";
            card.dataset.relativeFormPrefix = prefix;
            card.appendChild(createPersonCardAvatar(list, "relative"));
            list.insertBefore(card, list.querySelector(".family-dashed-add") || null);
            focusCardEditor(buildRelativeCardEditor(card, row, { title: "Nuovo familiare" }));
            syncCardEmptyStates();
            if (trigger && card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "center" });
        }

        function addDocumentCardFromView(trigger) {
            const list = getDocumentCardList();
            const mounted = addCardInlineForm("documenti");
            const row = mounted && mounted.state ? mounted.state.row : null;
            const prefix = getInlinePrefixFromRow(row);
            if (!list || !row || !prefix) return;

            const card = document.createElement("article");
            card.className = "family-document-card family-document-card-new is-card-editing";
            card.dataset.documentCard = "1";
            card.dataset.documentFormPrefix = prefix;
            card.appendChild(createDocumentCardIcon(list));
            list.insertBefore(card, list.querySelector(".family-dashed-add") || null);
            focusCardEditor(buildDocumentCardEditor(card, row, { title: "Nuovo documento" }));
            syncCardEmptyStates();
            if (trigger && card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "center" });
        }

        function closeCardEditor(card, row, editorSelector, restoreValues) {
            const editor = card ? card.querySelector(editorSelector) : null;
            if (!card || !row || !editor) {
                return;
            }

            if (restoreValues) {
                restoreFieldSnapshot(editor.__relativeDetailFieldSnapshot);
            }

            restoreEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            if (editorSelector === ".family-document-card-editor") {
                inlineFormsets.setRowInputsEnabled(row, false, { skipHiddenInputs: false });
            } else {
                setRowBundleEnabled(row, false);
            }
            refreshRelativePageActionLocks();
        }

        function cancelStudentCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-student-card]") : document.querySelector("[data-student-card].is-card-editing");
            const row = getStudentRowFromCard(card);
            if (!card || !row) return;
            if (!inlineFormsets.isRowPersisted(row)) {
                inlineManagers.studenti.remove(row);
                card.remove();
                syncCardEmptyStates();
                refreshTabCounts();
                refreshRelativePageActionLocks();
                return;
            }
            closeCardEditor(card, row, ".family-student-card-editor", true);
        }

        function cancelRelativeCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-relative-card]") : document.querySelector("[data-relative-card].is-card-editing");
            const row = getRelativeRowFromCard(card);
            if (!card || !row) return;
            if (!inlineFormsets.isRowPersisted(row)) {
                inlineManagers.parenti.remove(row);
                card.remove();
                syncCardEmptyStates();
                refreshTabCounts();
                refreshRelativePageActionLocks();
                return;
            }
            closeCardEditor(card, row, ".family-relative-card-editor", true);
        }

        function cancelDocumentCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-document-card]") : document.querySelector("[data-document-card].is-card-editing");
            const row = getDocumentRowFromCard(card);
            if (!card || !row) return;
            if (!inlineFormsets.isRowPersisted(row)) {
                inlineManagers.documenti.remove(row);
                card.remove();
                syncCardEmptyStates();
                refreshTabCounts();
                refreshRelativePageActionLocks();
                return;
            }
            closeCardEditor(card, row, ".family-document-card-editor", true);
        }

        function removeCardEditor(button, options) {
            const cfg = options || {};
            const card = button ? button.closest(cfg.cardSelector) : null;
            const row = cfg.getRow(card);
            if (!card || !row) return;

            const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            const isPersisted = inlineFormsets.isRowPersisted(row);
            const titleNode = card.querySelector(".family-person-heading h3, .family-document-main h3, .family-student-card-editor-head h3");
            const label = titleNode ? titleNode.textContent.trim().replace(/^Modifica\s+/, "") : cfg.fallbackLabel;

            if (!window.confirm(`Confermi la rimozione di ${label}?`)) return;
            if (isPersisted && !window.confirm(`Seconda conferma: ${label} verra eliminato al salvataggio. Vuoi continuare?`)) return;

            if (!isPersisted) {
                cfg.manager.remove(row);
                card.remove();
                syncCardEmptyStates();
                refreshTabCounts();
                refreshRelativePageActionLocks();
                return;
            }

            if (deleteInput) {
                deleteInput.disabled = false;
                deleteInput.checked = true;
            }

            const saveButton = card.querySelector(`[data-card-inline-submit="${cfg.target}"]`);
            if (saveButton && typeof saveButton.click === "function") {
                saveButton.formNoValidate = true;
                saveButton.setAttribute("formnovalidate", "formnovalidate");
                saveButton.click();
            }
        }

        function confirmDocumentCardDelete(button) {
            const popupUrl = button ? button.dataset.popupUrl || "" : "";
            const card = button ? button.closest(".family-document-card") : null;
            const titleNode = card ? card.querySelector(".family-document-main h3") : null;
            const label = (button.dataset.documentDeleteLabel || (titleNode ? titleNode.textContent : "") || "questo documento").replace(/\s+/g, " ").trim();

            if (!popupUrl) return;
            if (!window.confirm(`Vuoi eliminare ${label}? Si aprira un popup di conferma prima della cancellazione definitiva.`)) return;

            relatedPopups.openRelatedPopup(popupUrl);
        }

        function syncCardEmptyStates() {
            const studentList = getStudentCardList();
            const relativeList = getRelativeCardList();
            const documentList = getDocumentCardList();

            if (studentList) {
                const empty = studentList.querySelector(".family-card-empty");
                if (empty) empty.hidden = Boolean(studentList.querySelector("[data-student-card]"));
            }
            if (relativeList) {
                const empty = relativeList.querySelector(".family-card-empty");
                if (empty) empty.hidden = Boolean(relativeList.querySelector("[data-relative-card]"));
            }
            if (documentList) {
                const empty = documentList.querySelector(".family-card-empty");
                if (empty) empty.hidden = Boolean(documentList.querySelector("[data-document-card]"));
            }
        }

        function wireStudentCardActions(root) {
            const container = root || document;
            if (!container || typeof container.querySelectorAll !== "function") return;

            container.querySelectorAll("[data-student-card-action]").forEach(function (element) {
                if (element.dataset.studentCardActionBound === "1") return;
                element.dataset.studentCardActionBound = "1";
                element.addEventListener("click", function (event) {
                    const action = element.dataset.studentCardAction || "";
                    const context = getActiveRelativePageEditContext();
                    event.preventDefault();
                    event.stopPropagation();
                    if (context && !isAllowedDuringRelativeCardEdit(element, context)) {
                        showRelativeCardLockMessage(element, context.message);
                        return;
                    }
                    if (action === "add") addStudentCardFromView(element);
                    if (action === "edit") openStudentCardEditor(element.closest("[data-student-card]"));
                    if (action === "cancel") cancelStudentCardEditor(element);
                    if (action === "remove") removeCardEditor(element, { cardSelector: "[data-student-card]", getRow: getStudentRowFromCard, manager: inlineManagers.studenti, target: "studenti", fallbackLabel: "questo studente" });
                });
            });
        }

        function wireRelativeCardActions(root) {
            const container = root || document;
            if (!container || typeof container.querySelectorAll !== "function") return;

            container.querySelectorAll("[data-relative-card-action]").forEach(function (element) {
                if (element.dataset.relativeCardActionBound === "1") return;
                element.dataset.relativeCardActionBound = "1";
                element.addEventListener("click", function (event) {
                    const action = element.dataset.relativeCardAction || "";
                    const context = getActiveRelativePageEditContext();
                    event.preventDefault();
                    event.stopPropagation();
                    if (context && !isAllowedDuringRelativeCardEdit(element, context)) {
                        showRelativeCardLockMessage(element, context.message);
                        return;
                    }
                    if (action === "add") addRelativeCardFromView(element);
                    if (action === "edit") openRelativeCardEditor(element.closest("[data-relative-card]"));
                    if (action === "cancel") cancelRelativeCardEditor(element);
                    if (action === "remove") removeCardEditor(element, { cardSelector: "[data-relative-card]", getRow: getRelativeRowFromCard, manager: inlineManagers.parenti, target: "parenti", fallbackLabel: "questo familiare" });
                });
            });
        }

        function wireDocumentCardActions(root) {
            const container = root || document;
            if (!container || typeof container.querySelectorAll !== "function") return;

            container.querySelectorAll("[data-document-card-action]").forEach(function (element) {
                if (element.dataset.documentCardActionBound === "1") return;
                element.dataset.documentCardActionBound = "1";
                element.addEventListener("click", function (event) {
                    const action = element.dataset.documentCardAction || "";
                    const context = getActiveRelativePageEditContext();
                    event.preventDefault();
                    event.stopPropagation();
                    if (context && !isAllowedDuringRelativeCardEdit(element, context)) {
                        showRelativeCardLockMessage(element, context.message);
                        return;
                    }
                    if (action === "add") addDocumentCardFromView(element);
                    if (action === "edit") openDocumentCardEditor(element.closest("[data-document-card]"));
                    if (action === "cancel") cancelDocumentCardEditor(element);
                    if (action === "remove") removeCardEditor(element, { cardSelector: "[data-document-card]", getRow: getDocumentRowFromCard, manager: inlineManagers.documenti, target: "documenti", fallbackLabel: "questo documento" });
                    if (action === "delete") confirmDocumentCardDelete(element);
                });
            });
        }

        function removeManagedInlineRow(button) {
            const row = button && button.closest ? button.closest("tr") : null;
            const table = row ? row.closest("table") : null;
            const manager = table ? inlineManagers[table.id.replace("-table", "")] : null;
            const removed = manager ? manager.remove(button) : null;

            if (removed) {
                refreshFirstStudentAddMode();
                refreshTabCounts();
            }
        }

        function addManagedInlineForm(prefix) {
            const manager = inlineManagers[prefix];
            if (!manager) {
                return;
            }

            const form = document.getElementById("familiare-detail-form");
            const isAlreadyAddOnlyMode = Boolean(form && form.classList.contains("is-inline-add-only-mode"));
            const isFirstStudentAdd = prefix === "studenti" && countPersistedRows("studenti-table") === 0;
            const shouldUseAddOnlyMode = Boolean(
                window.familiareViewMode &&
                (!window.familiareViewMode.isEditing() || isAlreadyAddOnlyMode)
            );

            setInlineTarget(prefix);
            activatePanelIfPresent(`tab-${prefix}`);

            if (window.familiareViewMode && !window.familiareViewMode.isEditing()) {
                window.familiareViewMode.setInlineEditing(true);
            }

            const mounted = manager.add();

            if (!mounted) {
                return;
            }

            if (shouldUseAddOnlyMode && mounted.state) {
                inlineFormsets.markBundleForAddOnlyEdit(mounted.state, {
                    form: "familiare-detail-form",
                });
            }

            if (prefix === "studenti") {
                markFirstStudentAddRows(mounted, isFirstStudentAdd && mounted.revealed);
            }

            refreshTabCounts();
        }

        function bindScambioRettaNavigation() {
            const root = document.getElementById("scambio-retta-inline");
            if (!root) {
                return;
            }

            root.querySelectorAll(".scambio-view-btn, .scambio-calendar-nav a").forEach(link => {
                if (link.dataset.scambioNavigationBound === "1") {
                    return;
                }

                link.dataset.scambioNavigationBound = "1";
                link.addEventListener("click", function (event) {
                    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                        return;
                    }

                    event.preventDefault();
                    event.stopPropagation();

                    if (typeof window.ArborisArmLongWaitForNavigationUrl === "function") {
                        window.ArborisArmLongWaitForNavigationUrl(link.href);
                    }
                    window.location.assign(link.href);
                });
            });
        }

        function getCurrentInlineTabForRelativeNotes() {
            const activeButton = document.querySelector("#familiare-inline-lock-container .tab-btn.is-active[data-tab-target]");
            if (activeButton && activeButton.dataset.tabTarget) {
                return activeButton.dataset.tabTarget;
            }

            const activePanel = document.querySelector("#familiare-inline-lock-container .tab-panel.is-active[id]");
            if (activePanel) {
                return activePanel.id;
            }

            return "tab-studenti";
        }

        function refreshRelativeNoteDialogEditor(overlay) {
            if (!window.ArborisRichNotes || !overlay) {
                return;
            }
            if (typeof window.ArborisRichNotes.init === "function") {
                window.ArborisRichNotes.init(overlay);
            }
            if (typeof window.ArborisRichNotes.refresh === "function") {
                window.ArborisRichNotes.refresh(overlay);
            }
        }

        function initRelativeNoteDialog() {
            const openButton = document.getElementById("relative-note-edit-shortcut");
            const overlay = document.getElementById("relative-note-dialog-overlay");
            const dialog = document.getElementById("relative-note-popup-form");
            const activeTabInput = document.getElementById("relative-note-active-tab");

            if (!openButton || !overlay || !dialog) {
                return;
            }

            const closeDialog = function () {
                overlay.classList.add("is-hidden");
                overlay.setAttribute("aria-hidden", "true");
            };

            const openDialog = function () {
                if (activeTabInput) {
                    activeTabInput.value = getCurrentInlineTabForRelativeNotes();
                }
                overlay.classList.remove("is-hidden");
                overlay.setAttribute("aria-hidden", "false");
                refreshRelativeNoteDialogEditor(overlay);
                const editor = overlay.querySelector(".rich-note-editor:not([hidden])");
                const textarea = overlay.querySelector("textarea");
                window.setTimeout(function () {
                    if (editor) {
                        editor.focus();
                    } else if (textarea) {
                        textarea.focus();
                    }
                }, 50);
            };

            openButton.addEventListener("click", function (event) {
                event.preventDefault();
                openDialog();
            });

            overlay.querySelectorAll("[data-family-note-dialog-cancel]").forEach(function (button) {
                button.addEventListener("click", function (event) {
                    event.preventDefault();
                    closeDialog();
                });
            });

            overlay.addEventListener("click", function (event) {
                if (event.target === overlay) {
                    closeDialog();
                }
            });

            document.addEventListener("keydown", function (event) {
                if (event.key === "Escape" && !overlay.classList.contains("is-hidden")) {
                    closeDialog();
                }
            });

            dialog.addEventListener("submit", function () {
                if (activeTabInput) {
                    activeTabInput.value = getCurrentInlineTabForRelativeNotes();
                }
            });

            refreshRelativeNoteDialogEditor(overlay);
        }

        function getRelativeSideCards(container) {
            return Array.from((container || document).querySelectorAll("[data-family-side-card]"));
        }

        function readRelativeSideStoredKeys(storageKey) {
            if (!storageKey) {
                return [];
            }

            try {
                const parsed = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
                return Array.isArray(parsed) ? parsed : [];
            } catch (error) {
                return [];
            }
        }

        function saveRelativeSideCardOrder(storageKey, container) {
            if (!storageKey || !container) {
                return;
            }

            const orderedKeys = getRelativeSideCards(container)
                .map(function (card) {
                    return card.dataset.familySideCardKey;
                })
                .filter(Boolean);

            try {
                window.localStorage.setItem(storageKey, JSON.stringify(orderedKeys));
            } catch (error) {}
        }

        function applyRelativeSideCardOrder(storageKey, container) {
            const orderedKeys = readRelativeSideStoredKeys(storageKey);
            if (!orderedKeys.length || !container) {
                return;
            }

            const cardMap = new Map(
                getRelativeSideCards(container).map(function (card) {
                    return [card.dataset.familySideCardKey, card];
                })
            );

            orderedKeys.forEach(function (cardKey) {
                const card = cardMap.get(cardKey);
                if (card) {
                    container.appendChild(card);
                    cardMap.delete(cardKey);
                }
            });

            cardMap.forEach(function (card) {
                container.appendChild(card);
            });
        }

        function syncRelativeViewSideHeight() {
            const form = document.getElementById("familiare-detail-form");
            if (!form) {
                return;
            }

            const side = form.querySelector(".relative-dashboard-side");
            const isStacked = window.matchMedia && window.matchMedia("(max-width: 980px)").matches;
            if (!side || !form.classList.contains("is-view-mode") || isStacked) {
                form.style.removeProperty("--relative-side-height");
                return;
            }

            form.style.setProperty("--relative-side-height", `${Math.ceil(side.getBoundingClientRect().height)}px`);
        }

        function initRelativeViewSideHeightSync() {
            const form = document.getElementById("familiare-detail-form");
            const side = form ? form.querySelector(".relative-dashboard-side") : null;
            if (!form || !side || form.dataset.relativeSideHeightSyncBound === "1") {
                return;
            }

            form.dataset.relativeSideHeightSyncBound = "1";
            let pendingFrame = null;
            const scheduleSync = function () {
                if (pendingFrame) {
                    window.cancelAnimationFrame(pendingFrame);
                }
                pendingFrame = window.requestAnimationFrame(function () {
                    pendingFrame = null;
                    syncRelativeViewSideHeight();
                });
            };

            if (window.ResizeObserver) {
                const observer = new ResizeObserver(scheduleSync);
                observer.observe(side);
            }

            window.addEventListener("resize", scheduleSync);
            scheduleSync();
        }

        function getRelativeSideCollapseStorageKey(card) {
            const container = card.closest("[data-family-side-reorder], .relative-dashboard-side");
            return (container && container.dataset.familySideCollapseKey) ||
                `arboris-relative-side-card-collapsed-${config.familiareId || "new"}`;
        }

        function saveRelativeSideCollapsedKeys(storageKey) {
            if (!storageKey) {
                return;
            }

            const collapsedKeys = Array.from(document.querySelectorAll(".relative-dashboard-side [data-family-side-card].is-collapsed"))
                .map(function (card) {
                    return card.dataset.familySideCardKey;
                })
                .filter(Boolean);

            try {
                window.localStorage.setItem(storageKey, JSON.stringify(collapsedKeys));
            } catch (error) {}
        }

        function getRelativeSideCardTitle(card) {
            const title = card.querySelector(".family-side-card-head h2, h2");
            return title ? title.textContent.replace(/\s+/g, " ").trim() : "sidebar";
        }

        function setRelativeSideCardCollapsed(card, collapsed) {
            const body = card.querySelector("[data-family-side-card-body]");
            const toggle = card.querySelector("[data-family-side-collapse-toggle]");
            const title = getRelativeSideCardTitle(card);

            card.classList.toggle("is-collapsed", collapsed);

            if (body) {
                if (!body.id && card.dataset.familySideCardKey) {
                    body.id = `relative-side-card-body-${card.dataset.familySideCardKey}`;
                }
                body.hidden = collapsed;
            }

            if (toggle) {
                toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
                toggle.setAttribute("aria-label", `${collapsed ? "Espandi" : "Comprimi"} card ${title}`);
                toggle.setAttribute("title", collapsed ? "Espandi card" : "Comprimi card");
                if (body && body.id) {
                    toggle.setAttribute("aria-controls", body.id);
                }
            }

            syncRelativeViewSideHeight();
        }

        function initRelativeSideCardCollapse() {
            const storageGroups = new Map();

            getRelativeSideCards(document).forEach(function (card) {
                const storageKey = getRelativeSideCollapseStorageKey(card);
                if (!storageGroups.has(storageKey)) {
                    storageGroups.set(storageKey, readRelativeSideStoredKeys(storageKey));
                }

                const collapsedKeys = storageGroups.get(storageKey);
                setRelativeSideCardCollapsed(card, collapsedKeys.includes(card.dataset.familySideCardKey || ""));

                const toggle = card.querySelector("[data-family-side-collapse-toggle]");
                if (!toggle || toggle.dataset.relativeSideCollapseBound === "1") {
                    return;
                }

                toggle.dataset.relativeSideCollapseBound = "1";
                toggle.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    setRelativeSideCardCollapsed(card, !card.classList.contains("is-collapsed"));
                    saveRelativeSideCollapsedKeys(storageKey);
                });
            });
        }

        function initRelativeSideCardReorder() {
            document.querySelectorAll(".relative-dashboard-side[data-family-side-reorder]").forEach(function (container) {
                if (container.dataset.relativeSideReorderBound === "1") {
                    return;
                }

                container.dataset.relativeSideReorderBound = "1";
                const storageKey = container.dataset.familySideOrderKey || `arboris-relative-side-card-order-${config.familiareId || "new"}`;
                let draggingCard = null;

                function clearDropState() {
                    container.querySelectorAll(".family-side-card.is-drop-target").forEach(function (card) {
                        card.classList.remove("is-drop-target");
                    });
                }

                function bindCard(card) {
                    if (card.dataset.relativeSideDragBound === "1") {
                        return;
                    }

                    card.dataset.relativeSideDragBound = "1";
                    const handle = card.querySelector("[data-family-side-drag-handle]");
                    if (!handle) {
                        return;
                    }

                    handle.addEventListener("click", function (event) {
                        event.preventDefault();
                        event.stopPropagation();
                    });

                    handle.addEventListener("dragstart", function (event) {
                        draggingCard = card;
                        card.classList.add("is-dragging");
                        container.classList.add("is-drag-active");

                        if (event.dataTransfer) {
                            event.dataTransfer.effectAllowed = "move";
                            event.dataTransfer.setData("text/plain", card.dataset.familySideCardKey || "");
                        }
                    });

                    handle.addEventListener("dragend", function () {
                        if (draggingCard) {
                            draggingCard.classList.remove("is-dragging");
                        }
                        container.classList.remove("is-drag-active");
                        clearDropState();
                        draggingCard = null;
                        saveRelativeSideCardOrder(storageKey, container);
                        syncRelativeViewSideHeight();
                    });
                }

                applyRelativeSideCardOrder(storageKey, container);
                getRelativeSideCards(container).forEach(bindCard);

                container.addEventListener("dragover", function (event) {
                    if (!draggingCard) {
                        return;
                    }

                    event.preventDefault();
                    const targetCard = event.target.closest("[data-family-side-card]");
                    clearDropState();

                    if (!targetCard || targetCard === draggingCard || targetCard.parentElement !== container) {
                        return;
                    }

                    const rect = targetCard.getBoundingClientRect();
                    const insertAfter = event.clientY > rect.top + (rect.height / 2);
                    targetCard.classList.add("is-drop-target");

                    if (insertAfter) {
                        container.insertBefore(draggingCard, targetCard.nextSibling);
                    } else {
                        container.insertBefore(draggingCard, targetCard);
                    }
                });

                container.addEventListener("drop", function (event) {
                    if (!draggingCard) {
                        return;
                    }

                    event.preventDefault();
                    clearDropState();
                    saveRelativeSideCardOrder(storageKey, container);
                    syncRelativeViewSideHeight();
                });
            });
        }

        function initRelativeStatCardLinks() {
            document.querySelectorAll(".relative-stat-grid .family-stat-card[href^='#']").forEach(function (link) {
                if (link.dataset.relativeStatLinkBound === "1") {
                    return;
                }

                link.dataset.relativeStatLinkBound = "1";
                link.addEventListener("click", function (event) {
                    const targetId = (link.getAttribute("href") || "").replace(/^#/, "");
                    if (!targetId) {
                        return;
                    }

                    const target = document.getElementById(targetId);
                    if (!target) {
                        return;
                    }

                    event.preventDefault();
                    if (targetId.startsWith("tab-")) {
                        setInlineTarget(targetId);
                        updateInlineEditButtonLabel(targetId);
                        tabs.activateTab(targetId, getFamiliareTabStorageKey());
                        refreshInlineEditScope();
                    }

                    target.scrollIntoView({ behavior: "smooth", block: "start" });
                });
            });
        }

        function initRelativeSideCards() {
            initRelativeSideCardCollapse();
            initRelativeSideCardReorder();
            initRelativeViewSideHeightSync();
        }

        const famigliaSelect = document.getElementById("id_famiglia");
        const relazioneSelect = document.getElementById("id_relazione_familiare");
        const indirizzoSelect = document.getElementById("id_indirizzo");

        const addFamigliaBtn = document.getElementById("add-famiglia-btn");
        const editFamigliaBtn = document.getElementById("edit-famiglia-btn");
        const addRelazioneBtn = document.getElementById("add-relazione-btn");
        const editRelazioneBtn = document.getElementById("edit-relazione-btn");
        const deleteRelazioneBtn = document.getElementById("delete-relazione-btn");
        const addIndirizzoBtn = document.getElementById("add-indirizzo-btn");
        const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
        const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");
        let refreshFamigliaNavigation = function () {};
        let refreshRelazioneButtons = function () {};
        let refreshIndirizzoButtons = function () {};

        const famigliaNavigation = formTools.bindFamigliaNavigation({
            familySelect: famigliaSelect,
            addBtn: addFamigliaBtn,
            editBtn: editFamigliaBtn,
            createUrl: config.urls.creaFamiglia,
        });
        refreshFamigliaNavigation = famigliaNavigation.refresh;

        const relazioneCrud = routes.wireCrudButtonsById({
            select: relazioneSelect,
            relatedType: "relazione_familiare",
            addBtn: addRelazioneBtn,
            editBtn: editRelazioneBtn,
            deleteBtn: deleteRelazioneBtn,
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        refreshRelazioneButtons = relazioneCrud.refresh;

        const indirizzoCrud = routes.wireCrudButtonsById({
            select: indirizzoSelect,
            relatedType: "indirizzo",
            addBtn: addIndirizzoBtn,
            editBtn: editIndirizzoBtn,
            deleteBtn: deleteIndirizzoBtn,
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        refreshIndirizzoButtons = indirizzoCrud.refresh;
        refreshFamigliaNavigation();

        formTools.bindFamilyAddressController({
            familyLinkedAddress: familyLinkedAddress,
            familySelect: famigliaSelect,
            addressSelect: indirizzoSelect,
            helpElement: document.getElementById("familiare-address-help"),
            fallbackLabelScriptId: "familiare-famiglia-indirizzo-label",
            onRefreshButtons: updateMainButtons,
            unselectedFamilyPrefix: "Ereditera: ",
        });

        if (relazioneSelect) {
            relazioneSelect.addEventListener("change", function () {
                updateMainButtons();
            });
        }

        inlineManagers.parenti.prepare();
        inlineManagers.documenti.prepare();
        inlineManagers.studenti.prepare();
        const inlineLockRoot = document.getElementById(inlineLockContainerId);
        if (inlineLockRoot) {
            tabs.bindTabButtons(getFamiliareTabStorageKey(), inlineLockRoot);
            inlineTabs.bindTabNavigationLock({
                containerId: inlineLockContainerId,
                targetInputId: targetInputId,
                getViewMode: function () {
                    return window.familiareViewMode;
                },
            });
        }
        document.querySelectorAll("#familiare-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
            btn.addEventListener("click", function () {
                setInlineTarget(btn.dataset.tabTarget);
                updateInlineEditButtonLabel(btn.dataset.tabTarget);
                refreshInlineEditScope();
            });
        });
        collapsible.initCollapsibleSections(document);
        if (window.ArborisRichNotes && typeof window.ArborisRichNotes.init === "function") {
            window.ArborisRichNotes.init(document);
        }
        wireInlineRelatedButtons(document);
        wireStudentCardActions(document);
        wireRelativeCardActions(document);
        wireDocumentCardActions(document);
        inlineFormsets.wireActionTriggers(document, {
            handlers: {
                add: function (prefix) {
                    addManagedInlineForm(prefix);
                },
                remove: function (_prefix, element) {
                    removeManagedInlineRow(element);
                },
            },
        });
        routes.wirePopupTriggerElements(document, {
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
            studentiInlineAddressCollection.bindTracking(row);
        });
        bindAllStudenteInlineSex();
        tabs.restoreActiveTab(getFamiliareTabStorageKey());
        const activeTab = inlineLockRoot ? inlineLockRoot.querySelector(".tab-btn.is-active") : null;
        if (activeTab && activeTab.dataset.tabTarget) {
            setInlineTarget(activeTab.dataset.tabTarget);
            updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
        }
        bindStandaloneSexFromRelazioneFamiliare();
        bindScambioRettaNavigation();
        initRelativeNoteDialog();
        wireRelativeMainCardActions(document);
        bindRelativePageActionLock();
        bindRelativeCardStickyActions();
        bindRelativeMainSubmitScope();
        initRelativeStatCardLinks();
        initRelativeSideCards();
        studentiInlineAddressDefaults.syncRows();
        updateMainButtons();
        refreshTabCounts();
        refreshInlineEditScope();
        syncCardEmptyStates();
        refreshRelativePageActionLocks();
    }

    return {
        init,
        refreshInlineEditScope: function () {
            refreshInlineEditScopeHandler();
        },
    };
})();
