window.ArborisStudenteForm = (function () {
    let refreshInlineEditScopeHandler = function () {};

    function init(config) {
        const routes = window.ArborisRelatedEntityRoutes || null;
        const relatedPopups = routes && typeof routes.initRelatedPopups === "function"
            ? (routes.initRelatedPopups() || window.ArborisRelatedPopups || null)
            : (window.ArborisRelatedPopups || null);
        const collapsible = window.ArborisCollapsible || {
            initCollapsibleSections: function () {},
        };
        const tabs = window.ArborisTabs || {
            activateTab: function (tabId) {
                document.querySelectorAll(".tab-btn").forEach(function (btn) {
                    btn.classList.remove("is-active");
                });
                document.querySelectorAll(".tab-panel").forEach(function (panel) {
                    panel.classList.remove("is-active");
                });
                const btn = document.querySelector('[data-tab-target="' + tabId + '"]');
                const panel = document.getElementById(tabId);
                if (btn) btn.classList.add("is-active");
                if (panel) panel.classList.add("is-active");
            },
            bindTabButtons: function () {},
            restoreActiveTab: function () {},
        };
        const inlineTabs = window.ArborisInlineTabs || {
            setInlineTargetValue: function (targetInputId, prefixOrTabId) {
                const input = document.getElementById(targetInputId);
                if (!input || !prefixOrTabId) {
                    return;
                }
                input.value = prefixOrTabId.replace(/^tab-/, "");
            },
            updateDefaultInlineEditButtonLabel: function () {},
            createRefreshLockedTabs: function (options) {
                return function () {
                    if (options && typeof options.onAfterRefresh === "function") {
                        options.onAfterRefresh();
                    }
                };
            },
            bindTabNavigationLock: function () {},
        };
        const inlineFormsets = window.ArborisInlineFormsets;
        const personRules = window.ArborisPersonRules || {
            bindSexFromFirstName: function () {},
        };
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress || null;
        const formTools = window.ArborisAnagraficaFormTools || null;

        if (!inlineFormsets) {
            console.error("Arboris inline formsets non caricati: impossibile inizializzare la scheda studente.");
            return;
        }

        const missingOptionalDeps = [];
        if (!routes) missingOptionalDeps.push("ArborisRelatedEntityRoutes");
        if (!relatedPopups) missingOptionalDeps.push("ArborisRelatedPopups");
        if (!window.ArborisTabs) missingOptionalDeps.push("ArborisTabs");
        if (!window.ArborisInlineTabs) missingOptionalDeps.push("ArborisInlineTabs");
        if (!window.ArborisPersonRules) missingOptionalDeps.push("ArborisPersonRules");
        if (!familyLinkedAddress) missingOptionalDeps.push("ArborisFamilyLinkedAddress");
        if (!formTools) missingOptionalDeps.push("ArborisAnagraficaFormTools");

        if (missingOptionalDeps.length) {
            console.warn("ArborisStudenteForm: dipendenze opzionali mancanti o non pronte:", missingOptionalDeps.join(", "));
        }

        function getStudenteTabStorageKey() {
            return `arboris-studente-form-active-tab-v2-${config.studenteId || "new"}`;
        }

        const studenteInlineRoot = () => document.getElementById("studente-inline-lock-container");
        const defaultInlineTab = config.defaultInlineTab || "iscrizioni";

        const targetInputId = "studente-inline-target";
        const inlineLockContainerId = "studente-inline-lock-container";
        const inlineEditButtonId = "enable-inline-edit-studente-btn";
        let inlineManagers = null;

        function normalizeTabId(tabId) {
            if (!tabId) {
                return "";
            }
            return tabId.startsWith("tab-") ? tabId : `tab-${tabId}`;
        }

        function syncActiveTabUrl(tabId) {
            const normalizedTab = normalizeTabId(tabId).replace(/^tab-/, "");
            if (!normalizedTab) {
                return;
            }

            const url = new URL(window.location.href);
            if (normalizedTab === defaultInlineTab) {
                url.searchParams.delete("tab");
            } else {
                url.searchParams.set("tab", normalizedTab);
            }

            const nextUrl = `${url.pathname}${url.search}${url.hash}`;
            const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
            if (nextUrl !== currentUrl) {
                window.history.replaceState({}, "", nextUrl);
            }
        }

        function setInlineTarget(prefixOrTabId) {
            inlineTabs.setInlineTargetValue(targetInputId, prefixOrTabId);
        }

        function refreshInlineEditScope() {
            refreshLockedTabs();
        }

        refreshInlineEditScopeHandler = refreshInlineEditScope;

        function updateInlineEditButtonLabel(tabId) {
            const inlineEditButton = document.getElementById(inlineEditButtonId);
            const scope = (tabId || "").replace(/^tab-/, "");
            if (inlineEditButton && scope === "parenti") {
                inlineEditButton.classList.add("is-hidden");
                return;
            }
            if (inlineEditButton && !(window.studenteViewMode && typeof window.studenteViewMode.isEditing === "function" && window.studenteViewMode.isEditing())) {
                inlineEditButton.classList.remove("is-hidden");
            }
            inlineTabs.updateDefaultInlineEditButtonLabel({
                buttonId: inlineEditButtonId,
                containerId: inlineLockContainerId,
                tabId: tabId,
                getViewMode: function () {
                    return window.studenteViewMode;
                },
            });
        }

        function activateInlineTab(tabId) {
            const normalizedTab = normalizeTabId(tabId);
            if (!normalizedTab) {
                return;
            }
            setInlineTarget(normalizedTab);
            updateInlineEditButtonLabel(normalizedTab);
            tabs.activateTab(normalizedTab, getStudenteTabStorageKey());
            syncActiveTabUrl(normalizedTab);
            refreshInlineEditScope();
        }

        function restoreActiveTab() {
            const requestedTabId = config.preferInitialActiveTab
                ? normalizeTabId(config.initialActiveTab || defaultInlineTab)
                : "";
            const requestedPanel = requestedTabId ? document.getElementById(requestedTabId) : null;

            if (requestedPanel) {
                activateInlineTab(requestedTabId);
                return;
            }

            tabs.restoreActiveTab(getStudenteTabStorageKey());
            const inlineRoot = studenteInlineRoot();
            const activeTab = inlineRoot ? inlineRoot.querySelector(".tab-btn.is-active[data-tab-target]") : null;
            if (activeTab && activeTab.dataset.tabTarget) {
                setInlineTarget(activeTab.dataset.tabTarget);
                updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
                syncActiveTabUrl(activeTab.dataset.tabTarget);
            }
            refreshInlineEditScope();
        }

        const refreshLockedTabs = inlineTabs.createRefreshLockedTabs({
            formId: "studente-detail-form",
            inlineLockContainerId: inlineLockContainerId,
            targetInputId: targetInputId,
            getViewMode: function () {
                return window.studenteViewMode;
            },
            inlineEditButtonId: inlineEditButtonId,
            onAfterRefresh: function () {
                const form = document.getElementById("studente-detail-form");
                const targetInput = document.getElementById(targetInputId);
                const target = targetInput ? targetInput.value : "";
                const isInlineEditing = Boolean(
                    window.studenteViewMode &&
                    typeof window.studenteViewMode.isInlineEditing === "function" &&
                    window.studenteViewMode.isInlineEditing()
                );

                if (form) {
                    form.classList.toggle("is-inline-iscrizioni-layout", isInlineEditing && target === "iscrizioni");
                }

                syncIscrizioniInlineDetails();
            },
        });

        function bindStandaloneSexFromNome() {
            personRules.bindSexFromFirstName({
                nameInput: document.getElementById("id_nome"),
                sexSelect: document.getElementById("id_sesso"),
                bindFlag: "sexBound",
            });
        }

        function updateMainButtons() {
            refreshFamigliaNavigation();
            refreshIndirizzoButtons();
        }

        function wireInlineRelatedButtons(container) {
            if (!formTools || typeof formTools.wireInlineRelatedButtons !== "function" || !routes || !relatedPopups) {
                return;
            }
            formTools.wireInlineRelatedButtons(container, {
                routes: routes,
                relatedPopups: relatedPopups,
            });
        }

        function getIscrizioneBundleState(row) {
            if (!row) {
                return null;
            }

            return inlineFormsets.getRowBundle(row, {
                companionClasses: ["inline-economic-row", "inline-notes-row"],
            });
        }

        function setInlineDetailsToggleState(toggle, isOpen) {
            if (!toggle) {
                return;
            }

            toggle.classList.toggle("is-open", isOpen);
            toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");

            const labelNode = toggle.querySelector("[data-collapsible-label]");
            if (!labelNode) {
                return;
            }

            labelNode.textContent = isOpen
                ? (toggle.dataset.labelOpen || labelNode.textContent)
                : (toggle.dataset.labelClosed || labelNode.textContent);
        }

        function syncIscrizioniInlineDetails() {
            const form = document.getElementById("studente-detail-form");
            const layoutEnabled = Boolean(form && form.classList.contains("is-inline-iscrizioni-layout"));
            const tabIscrizioni = document.getElementById("tab-iscrizioni");
            const detailsShouldBeOpen = layoutEnabled || Boolean(tabIscrizioni && tabIscrizioni.classList.contains("is-inline-edit-target"));

            document.querySelectorAll("#iscrizioni-table tbody .inline-form-row").forEach(function (row) {
                const state = getIscrizioneBundleState(row);
                if (!state || !state.companionRows.length) {
                    return;
                }

                const toggle = row.querySelector(".inline-details-toggle");

                state.companionRows.forEach(function (companionRow) {
                    const panel = companionRow.querySelector(".inline-details-panel");
                    if (!panel) {
                        return;
                    }

                    if (detailsShouldBeOpen) {
                        if (!row.classList.contains("is-hidden")) {
                            companionRow.classList.remove("inline-empty-row", "is-hidden");
                        }
                        panel.classList.add("is-open");
                        panel.dataset.inlineForcedOpen = "1";
                        setInlineDetailsToggleState(toggle, true);
                        return;
                    }

                    if (panel.dataset.inlineForcedOpen === "1") {
                        panel.classList.remove("is-open");
                        delete panel.dataset.inlineForcedOpen;
                        setInlineDetailsToggleState(toggle, false);
                    }
                });
            });
        }

        function wireIscrizioneBundle(state) {
            if (!state || !state.row) {
                return;
            }

            wireInlineRelatedButtons(state.row);
            state.companionRows.forEach(function (companionRow) {
                wireInlineRelatedButtons(companionRow);
            });
            wireIscrizioneRow(state.row);
            syncIscrizioniInlineDetails();
        }

        function refreshTabCounts() {
            const iscrizioniRows = inlineFormsets.countPersistedRows("iscrizioni-table");
            const tabIscrizioni = document.querySelector('[data-tab-target="tab-iscrizioni"]');
            const documentiRows = inlineFormsets.countPersistedRows("documenti-table");
            const tabDocumenti = document.querySelector('[data-tab-target="tab-documenti"]');
            const relativeList = getRelativeCardList();
            const parentiRows = relativeList
                ? relativeList.querySelectorAll("[data-relative-card], .family-student-card").length
                : inlineFormsets.countPersistedRows("parenti-table");
            const tabParenti = document.querySelector('[data-tab-target="tab-parenti"]');
            if (tabIscrizioni) tabIscrizioni.textContent = `Iscrizioni (${iscrizioniRows})`;
            if (tabDocumenti) tabDocumenti.textContent = `Documenti (${documentiRows})`;
            if (tabParenti) tabParenti.textContent = `Parenti (${parentiRows})`;
        }

        function getRateRecalcDialog() {
            let overlay = document.getElementById("rate-recalc-dialog-overlay");

            if (!overlay) {
                overlay = document.createElement("div");
                overlay.id = "rate-recalc-dialog-overlay";
                overlay.className = "app-dialog-overlay is-hidden";
                overlay.innerHTML = `
                    <div class="app-dialog" role="dialog" aria-modal="true" aria-labelledby="rate-recalc-dialog-title">
                        <div class="app-dialog-header">
                            <h2 class="app-dialog-title" id="rate-recalc-dialog-title">Conferma ricalcolo rate</h2>
                        </div>
                        <div class="app-dialog-body">
                            <p class="app-dialog-message">
                                Le rate senza pagamenti o movimenti potranno essere rigenerate.
                            </p>
                            <label class="app-dialog-field-label" for="rate-recalc-dialog-input">
                                Per confermare, digita <strong>RICALCOLA</strong>
                            </label>
                            <input
                                type="text"
                                id="rate-recalc-dialog-input"
                                class="app-dialog-input"
                                autocomplete="off"
                                spellcheck="false"
                            >
                            <label class="app-dialog-confirm-check" for="rate-recalc-dialog-second-confirm">
                                <input
                                    type="checkbox"
                                    id="rate-recalc-dialog-second-confirm"
                                >
                                <span>Confermo il ricalcolo del piano rate</span>
                            </label>
                        </div>
                        <div class="app-dialog-actions">
                            <button type="button" class="btn btn-secondary" data-rate-dialog-cancel="1">Annulla</button>
                            <button type="button" class="btn btn-rate-recalc" data-rate-dialog-confirm="1" disabled>Ricalcola rate</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(overlay);
            }

            const input = overlay.querySelector("#rate-recalc-dialog-input");
            const secondConfirm = overlay.querySelector("#rate-recalc-dialog-second-confirm");
            const confirmButton = overlay.querySelector('[data-rate-dialog-confirm="1"]');
            const cancelButton = overlay.querySelector('[data-rate-dialog-cancel="1"]');
            let resolver = null;

            function syncConfirmState() {
                confirmButton.disabled = (input.value || "").trim().toUpperCase() !== "RICALCOLA" || !secondConfirm.checked;
            }

            function closeDialog(confirmed) {
                if (!resolver) {
                    return;
                }

                overlay.classList.add("is-hidden");
                document.body.classList.remove("app-dialog-open");
                input.value = "";
                secondConfirm.checked = false;
                syncConfirmState();

                const resolve = resolver;
                resolver = null;
                resolve(Boolean(confirmed));
            }

            if (!overlay.dataset.boundRateDialog) {
                overlay.dataset.boundRateDialog = "1";

                input.addEventListener("input", syncConfirmState);
                secondConfirm.addEventListener("change", syncConfirmState);
                input.addEventListener("keydown", function (event) {
                    if (event.key === "Enter" && !confirmButton.disabled) {
                        event.preventDefault();
                        closeDialog(true);
                    }
                });

                cancelButton.addEventListener("click", function () {
                    closeDialog(false);
                });

                confirmButton.addEventListener("click", function () {
                    if (confirmButton.disabled) {
                        return;
                    }
                    closeDialog(true);
                });

                overlay.addEventListener("click", function (event) {
                    if (event.target === overlay) {
                        closeDialog(false);
                    }
                });

                document.addEventListener("keydown", function (event) {
                    if (overlay.classList.contains("is-hidden")) {
                        return;
                    }

                    if (event.key === "Escape") {
                        event.preventDefault();
                        closeDialog(false);
                    }
                });
            }

            return {
                open: function () {
                    input.value = "";
                    syncConfirmState();
                    overlay.classList.remove("is-hidden");
                    document.body.classList.add("app-dialog-open");

                    return new Promise(resolve => {
                        resolver = resolve;
                        window.setTimeout(function () {
                            input.focus();
                            input.select();
                        }, 0);
                    });
                },
            };
        }

        function submitRateRecalc(button) {
            const actionUrl = button.dataset.actionUrl;
            if (!actionUrl) {
                return;
            }

            const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
            const csrfToken = csrfInput ? csrfInput.value : "";

            const form = document.createElement("form");
            form.method = "post";
            form.action = actionUrl;
            form.style.display = "none";

            if (csrfToken) {
                const csrfField = document.createElement("input");
                csrfField.type = "hidden";
                csrfField.name = "csrfmiddlewaretoken";
                csrfField.value = csrfToken;
                form.appendChild(csrfField);
            }

            const nextUrl = button.dataset.nextUrl;
            if (nextUrl) {
                const nextField = document.createElement("input");
                nextField.type = "hidden";
                nextField.name = "next";
                nextField.value = nextUrl;
                form.appendChild(nextField);
            }

            document.body.appendChild(form);
            form.submit();
        }

        function bindRateRecalcForms() {
            const rateRecalcDialog = getRateRecalcDialog();

            document.querySelectorAll('[data-rate-recalc-form="1"]').forEach(button => {
                if (button.dataset.boundRateRecalc === "1") {
                    return;
                }

                button.dataset.boundRateRecalc = "1";
                button.addEventListener("click", function () {
                    rateRecalcDialog.open().then(function (confirmed) {
                        if (!confirmed) {
                            return;
                        }

                        submitRateRecalc(button);
                    });
                });
            });
        }

        const studentPageCardLockMessage = "Salva o annulla le modifiche in corso prima di usare altre funzioni della pagina.";

        function getMainCard() {
            return document.querySelector("[data-student-main-card]");
        }

        function getEnrollmentCardList() {
            return document.querySelector(".student-enrollment-card-list");
        }

        function getDocumentCardList() {
            return document.querySelector("[data-document-card-list]");
        }

        function getRelativeCardList() {
            return document.querySelector("[data-relative-card-list]");
        }

        function getActiveMainEditorCard() {
            return document.querySelector("[data-student-main-card].is-card-editing");
        }

        function getActiveEnrollmentEditingCard() {
            return document.querySelector("[data-enrollment-card].is-card-editing");
        }

        function getActiveDocumentEditingCard() {
            return document.querySelector("[data-document-card].is-card-editing");
        }

        function getActiveRelativeEditingCard() {
            return document.querySelector("[data-relative-card].is-card-editing");
        }

        function getActiveStudentPageEditContext() {
            const mainCard = getActiveMainEditorCard();
            if (mainCard) {
                return {
                    kind: "main",
                    target: "main",
                    card: mainCard,
                    editor: mainCard.querySelector(".student-main-card-editor"),
                };
            }

            const enrollmentCard = getActiveEnrollmentEditingCard();
            if (enrollmentCard) {
                return {
                    kind: "enrollment",
                    target: "iscrizioni",
                    card: enrollmentCard,
                    editor: enrollmentCard.querySelector(".student-enrollment-card-editor"),
                };
            }

            const documentCard = getActiveDocumentEditingCard();
            if (documentCard) {
                return {
                    kind: "document",
                    target: "documenti",
                    card: documentCard,
                    editor: documentCard.querySelector(".family-document-card-editor"),
                };
            }

            const relativeCard = getActiveRelativeEditingCard();
            if (relativeCard) {
                return {
                    kind: "relative",
                    target: "parenti",
                    card: relativeCard,
                    editor: relativeCard.querySelector(".family-relative-card-editor"),
                };
            }

            return null;
        }

        function setStudentCardLockElement(element, locked, message) {
            if (!element) {
                return;
            }

            if (locked) {
                if (element.dataset.cardLockOriginalTitleStored !== "1") {
                    element.dataset.cardLockOriginalTitleStored = "1";
                    element.dataset.cardLockOriginalTitle = element.getAttribute("title") || "";
                }
                element.classList.add("family-card-action-locked");
                element.dataset.studentPageCardLock = "1";
                element.dataset.cardLockMessage = message || studentPageCardLockMessage;
                element.setAttribute("title", message || studentPageCardLockMessage);
                return;
            }

            if (element.dataset.studentPageCardLock !== "1") {
                return;
            }

            delete element.dataset.studentPageCardLock;
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

        function showStudentCardLockMessage(element, message) {
            const target = element && element.closest
                ? element.closest("button, a, .tab-btn, .family-person-card, .family-document-card, .student-enrollment-card, [data-row-href]") || element
                : element;

            if (!target) {
                return;
            }

            setStudentCardLockElement(target, true, message || studentPageCardLockMessage);
            target.classList.remove("is-showing-lock");
            void target.offsetWidth;
            target.classList.add("is-showing-lock");

            window.clearTimeout(target.__studentPageCardLockTimer);
            target.__studentPageCardLockTimer = window.setTimeout(function () {
                target.classList.remove("is-showing-lock");
            }, 2200);
        }

        function isAllowedDuringStudentCardEdit(target, context) {
            if (!target || !context) {
                return true;
            }

            if (context.editor && context.editor.contains(target)) {
                return true;
            }

            if (target.closest && target.closest("#student-card-sticky-actions, .app-dialog, .app-dialog-overlay")) {
                return true;
            }

            return false;
        }

        function refreshStudentCardStickyActions() {
            const form = document.getElementById("studente-detail-form");
            const context = getActiveStudentPageEditContext();
            const shouldShow = Boolean(context);
            const menu = document.getElementById("student-card-sticky-actions");
            const spacer = document.getElementById("student-card-sticky-spacer");
            const title = menu ? menu.querySelector("[data-student-card-sticky-title]") : null;
            const saveButton = document.getElementById("student-card-sticky-save");

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
                form.classList.toggle("has-student-card-sticky-actions", shouldShow);
            }
            if (title && shouldShow) {
                const editorTitle = context && context.editor ? context.editor.querySelector("h3") : null;
                title.textContent = editorTitle && editorTitle.textContent.trim()
                    ? editorTitle.textContent.trim()
                    : "Modifica dati principali";
            }
            if (saveButton) {
                delete saveButton.dataset.studentMainSubmit;
                delete saveButton.dataset.cardInlineSubmit;
                if (shouldShow && context.kind === "main") {
                    saveButton.dataset.studentMainSubmit = "1";
                } else if (shouldShow && context.target) {
                    saveButton.dataset.cardInlineSubmit = context.target;
                }
            }
        }

        function bindStudentCardStickyActions() {
            const saveButton = document.getElementById("student-card-sticky-save");
            const cancelButton = document.getElementById("student-card-sticky-cancel");

            if (saveButton && saveButton.dataset.studentCardStickySaveBound !== "1") {
                saveButton.dataset.studentCardStickySaveBound = "1";
                saveButton.addEventListener("click", function () {
                    refreshStudentCardStickyActions();
                });
            }

            if (cancelButton && cancelButton.dataset.studentCardStickyCancelBound !== "1") {
                cancelButton.dataset.studentCardStickyCancelBound = "1";
                cancelButton.addEventListener("click", function (event) {
                    const context = getActiveStudentPageEditContext();
                    event.preventDefault();

                    if (!context || context.kind === "main") {
                        closeMainCardEditor({ restoreValues: true });
                    } else if (context.kind === "enrollment") {
                        cancelEnrollmentCardEditor(context.card);
                    } else if (context.kind === "document") {
                        cancelDocumentCardEditor(context.card);
                    } else if (context.kind === "relative") {
                        cancelRelativeCardEditor(context.card);
                    }
                });
            }
        }

        function bindStudentPageActionLock() {
            const form = document.getElementById("studente-detail-form");
            if (!form || form.dataset.studentPageActionLockBound === "1") {
                return;
            }

            form.dataset.studentPageActionLockBound = "1";

            document.addEventListener("click", function (event) {
                const context = getActiveStudentPageEditContext();
                if (!context) {
                    return;
                }

                const target = event.target && event.target.closest
                    ? event.target.closest("a, button, input[type='button'], input[type='submit'], .tab-btn, [data-row-href]")
                    : null;

                if (!target || isAllowedDuringStudentCardEdit(target, context)) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                showStudentCardLockMessage(target);
            }, true);

            const inlineRoot = studenteInlineRoot();
            if (inlineRoot && inlineRoot.dataset.studentPageTabLockBound !== "1") {
                inlineRoot.dataset.studentPageTabLockBound = "1";
                inlineRoot.addEventListener("arboris:before-tab-activate", function (event) {
                    const context = getActiveStudentPageEditContext();
                    if (!context) {
                        return;
                    }

                    const nextTarget = ((event.detail && event.detail.tabId) || "").replace(/^tab-/, "");
                    if (nextTarget && nextTarget === context.target) {
                        return;
                    }

                    event.preventDefault();
                    if (event.detail && event.detail.button) {
                        showStudentCardLockMessage(event.detail.button);
                    }
                });
            }
        }

        function refreshStudentPageActionLocks() {
            const context = getActiveStudentPageEditContext();
            const locked = Boolean(context);

            refreshStudentCardStickyActions();

            document.querySelectorAll(".page-head-actions a, .page-head-actions button, .student-dashboard-side a, .student-dashboard-side button, .student-main-card-stack a, .student-main-card-stack button, .student-stat-grid a, #studente-inline-lock-container .tab-btn, [data-enrollment-card-action], [data-document-card-action], [data-relative-card-action], [data-student-main-action], .family-related-list a, .student-rate-section a, .student-rate-section button").forEach(function (element) {
                if (context && isAllowedDuringStudentCardEdit(element, context)) {
                    setStudentCardLockElement(element, false);
                    return;
                }

                setStudentCardLockElement(element, locked, studentPageCardLockMessage);
            });
        }

        function getInlinePrefixFromRow(row) {
            const idInput = row ? row.querySelector('input[type="hidden"][name$="-id"]') : null;
            const name = idInput ? idInput.name || "" : "";
            return name.endsWith("-id") ? name.slice(0, -3) : "";
        }

        function getEnrollmentRowFromCard(card) {
            const prefix = card ? card.dataset.enrollmentFormPrefix || "" : "";
            if (!prefix) {
                return null;
            }

            const idInput = document.getElementById(`id_${prefix}-id`);
            return idInput ? idInput.closest("tr.inline-form-row") : null;
        }

        function getDocumentRowFromCard(card) {
            const prefix = card ? card.dataset.documentFormPrefix || "" : "";
            if (!prefix) {
                return null;
            }

            const idInput = document.getElementById(`id_${prefix}-id`);
            return idInput ? idInput.closest("tr.inline-form-row") : null;
        }

        function getRelativeRowFromCard(card) {
            const prefix = card ? card.dataset.relativeFormPrefix || "" : "";
            if (!prefix) {
                return null;
            }

            const idInput = document.getElementById(`id_${prefix}-id`);
            return idInput ? idInput.closest("tr.inline-form-row") : null;
        }

        function getFamiliareSubformRow(row) {
            let current = row ? row.nextElementSibling : null;
            while (current && !current.classList.contains("inline-form-row")) {
                if (current.classList.contains("inline-subform-row")) {
                    return current;
                }
                current = current.nextElementSibling;
            }
            return null;
        }

        function rememberEditorNode(editor, node) {
            if (!editor || !node) {
                return;
            }

            if (!node.__studentDetailRestore) {
                node.__studentDetailRestore = {
                    parent: node.parentNode,
                    nextSibling: node.nextSibling,
                    className: node.className,
                };
            }

            if (!editor.__studentDetailMovedNodes) {
                editor.__studentDetailMovedNodes = [];
            }
            if (!editor.__studentDetailMovedNodes.includes(node)) {
                editor.__studentDetailMovedNodes.push(node);
            }
        }

        function restoreEditorNodes(editor) {
            const movedNodes = editor && editor.__studentDetailMovedNodes ? editor.__studentDetailMovedNodes : [];

            movedNodes.slice().reverse().forEach(function (node) {
                const restore = node.__studentDetailRestore;
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
                delete node.__studentDetailRestore;
            });

            if (editor) {
                editor.__studentDetailMovedNodes = [];
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
            const sprite = (getDocumentCardList() && getDocumentCardList().dataset.uiIconsSprite) || config.uiIconsSprite || "/static/images/arboris-ui-icons.svg";
            return `<span class="btn-icon" aria-hidden="true"><svg><use href="${sprite}#${symbolName}"></use></svg></span><span class="btn-label">${label}</span>`;
        }

        function relatedIconHtml(symbolName) {
            const sprite = (getDocumentCardList() && getDocumentCardList().dataset.uiIconsSprite) || config.uiIconsSprite || "/static/images/arboris-ui-icons.svg";
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

        function createEditorField(labelText, contentNode, extraClass, editor) {
            if (!contentNode) {
                return null;
            }

            const field = document.createElement("div");
            field.className = `family-student-editor-field${extraClass ? " " + extraClass : ""}`;
            rememberEditorNode(editor, contentNode);

            if (labelText) {
                const label = document.createElement("label");
                const input = contentNode.matches && contentNode.matches("input, select, textarea")
                    ? contentNode
                    : contentNode.querySelector("input, select, textarea");
                label.textContent = labelText;
                if (input && input.id) {
                    label.setAttribute("for", input.id);
                }
                field.appendChild(label);
            }

            field.appendChild(contentNode);
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

        function appendRelatedField(grid, root, selector, labelText, extraClass, editor, relatedLabel) {
            const input = root ? root.querySelector(selector) : null;
            const relatedField = input ? input.closest(".inline-related-field, .related-field-row") : null;
            const field = createEditorField(labelText, relatedField || (input ? input.closest(".mode-edit-field") || input : null), extraClass, editor);

            if (relatedField) {
                relatedField.classList.add("family-card-editor-related-control");
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

        function appendRelativeAddressField(grid, row, editor) {
            const addressCell = row ? row.querySelector(".inline-family-address-cell") : null;
            const relatedField = addressCell ? addressCell.querySelector(".inline-related-field") : null;
            const helpNode = addressCell ? addressCell.querySelector('[data-role="address-help"]') : null;
            if (!relatedField) {
                return;
            }

            rememberEditorNode(editor, relatedField);
            if (helpNode) {
                rememberEditorNode(editor, helpNode);
            }

            const field = document.createElement("div");
            field.className = "family-student-editor-field family-student-editor-field-wide family-student-editor-address-field";

            const label = document.createElement("label");
            label.textContent = "Indirizzo";
            const input = relatedField.querySelector("select, input, textarea");
            if (input && input.id) {
                label.setAttribute("for", input.id);
            }
            field.appendChild(label);

            relatedField.classList.add("family-card-editor-related-control", "family-student-editor-address-control");
            decorateRelatedButtons(relatedField, "indirizzo");
            field.appendChild(relatedField);
            if (helpNode) {
                field.appendChild(helpNode);
            }
            grid.appendChild(field);
        }

        function setRelativeRowBundleEnabled(row, enabled) {
            inlineFormsets.setRowInputsEnabled(row, enabled, {
                includeCompanionRows: true,
                companionClasses: ["inline-subform-row"],
                skipHiddenInputs: false,
            });
        }

        function createPersonCardAvatar(list) {
            const avatar = document.createElement("span");
            const sprite = (list && list.dataset.avatarSprite) || config.avatarSprite || "/static/images/arboris-avatars.svg";
            avatar.className = "family-person-avatar family-person-avatar-relative";
            avatar.setAttribute("aria-hidden", "true");
            avatar.innerHTML = `<svg viewBox="0 0 96 96" focusable="false"><use href="${sprite}#avatar-man"></use></svg>`;
            return avatar;
        }

        function initEditorEnhancements(editor) {
            if (formTools && typeof formTools.initSearchableSelects === "function") {
                formTools.initSearchableSelects(editor);
            }
            if (formTools && typeof formTools.initCodiceFiscale === "function") {
                formTools.initCodiceFiscale(editor);
            }
            wireInlineRelatedButtons(editor);
            setFieldsEnabled(editor, true);
        }

        function syncEnrollmentCardEmptyState() {
            const list = getEnrollmentCardList();
            if (!list) {
                return;
            }

            const emptyState = list.querySelector(".family-card-empty");
            if (emptyState) {
                emptyState.hidden = Boolean(list.querySelector("[data-enrollment-card]"));
            }
        }

        function syncDocumentCardEmptyState() {
            const list = getDocumentCardList();
            if (!list) {
                return;
            }

            const emptyState = list.querySelector(".family-card-empty");
            if (emptyState) {
                emptyState.hidden = Boolean(list.querySelector("[data-document-card]"));
            }
        }

        function syncRelativeCardEmptyState() {
            const list = getRelativeCardList();
            if (!list) {
                return;
            }

            const emptyState = list.querySelector(".family-card-empty");
            if (emptyState) {
                emptyState.hidden = Boolean(list.querySelector("[data-relative-card]"));
            }
        }

        function getCurrentInlineTabForStudentNotes() {
            const activeTab = document.querySelector("#studente-inline-lock-container .tab-btn.is-active[data-tab-target]");
            const targetInput = document.getElementById("studente-inline-target");
            const rawValue = activeTab && activeTab.dataset.tabTarget
                ? activeTab.dataset.tabTarget
                : (targetInput ? targetInput.value : "");

            return (rawValue || "iscrizioni").replace(/^tab-/, "");
        }

        function refreshStudentNoteDialogEditor(overlay) {
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

        function setStudentNoteDialogValue(textarea, value, overlay) {
            if (!textarea) {
                return;
            }

            textarea.value = value || "";
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
            refreshStudentNoteDialogEditor(overlay);
        }

        function initStudentNoteDialog() {
            const openButton = document.getElementById("student-note-edit-shortcut");
            const overlay = document.getElementById("student-note-dialog-overlay");
            const dialog = document.getElementById("student-note-popup-form");
            const textarea = document.getElementById("id_student_note_popup");
            const activeTabInput = document.getElementById("student-note-active-tab");

            if (!openButton || !overlay || !dialog || !textarea || overlay.dataset.studentNoteDialogBound === "1") {
                return;
            }

            overlay.dataset.studentNoteDialogBound = "1";
            const initialValue = textarea.value || "";

            function focusEditor() {
                const editor = overlay.querySelector(".rich-note-editor:not([hidden])");
                if (editor) {
                    editor.focus();
                    return;
                }
                textarea.focus();
            }

            function openDialog() {
                if (activeTabInput) {
                    activeTabInput.value = getCurrentInlineTabForStudentNotes();
                }

                setStudentNoteDialogValue(textarea, initialValue, overlay);
                overlay.classList.remove("is-hidden");
                overlay.setAttribute("aria-hidden", "false");
                document.body.classList.add("app-dialog-open");
                window.setTimeout(focusEditor, 0);
            }

            function closeDialog() {
                setStudentNoteDialogValue(textarea, initialValue, overlay);
                overlay.classList.add("is-hidden");
                overlay.setAttribute("aria-hidden", "true");
                document.body.classList.remove("app-dialog-open");
                openButton.focus();
            }

            openButton.addEventListener("click", function (event) {
                event.preventDefault();
                openDialog();
            });

            overlay.querySelectorAll("[data-student-note-dialog-cancel]").forEach(function (button) {
                button.addEventListener("click", function () {
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
                    activeTabInput.value = getCurrentInlineTabForStudentNotes();
                }
            });

            refreshStudentNoteDialogEditor(overlay);
        }

        function getStudentMainCardStack() {
            return document.querySelector("[data-student-main-card-reorder]");
        }

        function getStudentMainStackCards(container) {
            return Array.from((container || document).querySelectorAll("[data-student-stack-card]"))
                .filter(function (card) {
                    return !container || card.parentElement === container;
                });
        }

        function prepareStudentMainCardStack() {
            const form = document.getElementById("studente-detail-form");
            const stack = getStudentMainCardStack();
            const inlineRoot = studenteInlineRoot();

            if (!form || !stack || !inlineRoot || !form.classList.contains("is-view-mode")) {
                return null;
            }

            if (inlineRoot.parentElement !== stack) {
                stack.appendChild(inlineRoot);
            }

            return stack;
        }

        function readStudentMainStoredKeys(storageKey) {
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

        function saveStudentMainCardOrder(storageKey, container) {
            if (!storageKey || !container) {
                return;
            }

            const orderedKeys = getStudentMainStackCards(container)
                .map(function (card) {
                    return card.dataset.studentStackCardKey;
                })
                .filter(Boolean);

            try {
                window.localStorage.setItem(storageKey, JSON.stringify(orderedKeys));
            } catch (error) {}
        }

        function applyStudentMainCardOrder(storageKey, container) {
            const orderedKeys = readStudentMainStoredKeys(storageKey);
            if (!orderedKeys.length || !container) {
                return;
            }

            const cardMap = new Map(
                getStudentMainStackCards(container).map(function (card) {
                    return [card.dataset.studentStackCardKey, card];
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

        function getStudentMainCollapseStorageKey(card) {
            const container = card.closest("[data-student-main-card-reorder]");
            return (container && container.dataset.studentMainCardCollapseKey) ||
                `arboris-student-main-card-collapsed-${config.studenteId || "new"}`;
        }

        function saveStudentMainCollapsedKeys(storageKey, container) {
            if (!storageKey || !container) {
                return;
            }

            const collapsedKeys = getStudentMainStackCards(container)
                .filter(function (card) {
                    return card.classList.contains("is-collapsed");
                })
                .map(function (card) {
                    return card.dataset.studentStackCardKey;
                })
                .filter(Boolean);

            try {
                window.localStorage.setItem(storageKey, JSON.stringify(collapsedKeys));
            } catch (error) {}
        }

        function getStudentMainCardTitle(card) {
            if (card && card.dataset.studentStackCardTitle) {
                return card.dataset.studentStackCardTitle;
            }

            const title = card ? card.querySelector("h2, .tab-btn.is-active, .admin-section-title") : null;
            return title ? title.textContent.replace(/\s+/g, " ").trim() : "card";
        }

        function setStudentMainCardCollapsed(card, collapsed) {
            if (!card) {
                return;
            }

            const body = card.querySelector("[data-student-main-card-body]");
            const toggle = card.querySelector("[data-student-main-card-collapse-toggle]");
            const title = getStudentMainCardTitle(card);

            card.classList.toggle("is-collapsed", collapsed);

            if (body) {
                if (!body.id && card.dataset.studentStackCardKey) {
                    body.id = `student-main-card-body-${card.dataset.studentStackCardKey}`;
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

            syncStudentViewSideHeight();
        }

        function initStudentMainCardCollapse(container) {
            if (!container) {
                return;
            }

            const storageKey = container.dataset.studentMainCardCollapseKey ||
                `arboris-student-main-card-collapsed-${config.studenteId || "new"}`;
            const collapsedKeys = readStudentMainStoredKeys(storageKey);

            getStudentMainStackCards(container).forEach(function (card) {
                setStudentMainCardCollapsed(card, collapsedKeys.includes(card.dataset.studentStackCardKey || ""));

                const toggle = card.querySelector("[data-student-main-card-collapse-toggle]");
                if (!toggle || toggle.dataset.studentMainCollapseBound === "1") {
                    return;
                }

                toggle.dataset.studentMainCollapseBound = "1";
                toggle.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    setStudentMainCardCollapsed(card, !card.classList.contains("is-collapsed"));
                    saveStudentMainCollapsedKeys(storageKey, container);
                });
            });
        }

        function initStudentMainCardReorder(container) {
            if (!container || container.dataset.studentMainReorderBound === "1") {
                return;
            }

            container.dataset.studentMainReorderBound = "1";
            const storageKey = container.dataset.studentMainCardOrderKey ||
                `arboris-student-main-card-order-${config.studenteId || "new"}`;
            let draggingCard = null;

            function clearDropState() {
                getStudentMainStackCards(container).forEach(function (card) {
                    card.classList.remove("is-drop-target");
                });
            }

            function bindCard(card) {
                if (card.dataset.studentMainDragBound === "1") {
                    return;
                }

                card.dataset.studentMainDragBound = "1";
                const handle = card.querySelector("[data-student-main-card-drag-handle]");
                if (!handle) {
                    return;
                }

                handle.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                });

                handle.addEventListener("dragstart", function (event) {
                    const context = getActiveStudentPageEditContext();
                    if (context && !isAllowedDuringStudentCardEdit(handle, context)) {
                        event.preventDefault();
                        showStudentCardLockMessage(handle);
                        return;
                    }

                    draggingCard = card;
                    card.classList.add("is-dragging");
                    container.classList.add("is-drag-active");

                    if (event.dataTransfer) {
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/plain", card.dataset.studentStackCardKey || "");
                    }
                });

                handle.addEventListener("dragend", function () {
                    if (draggingCard) {
                        draggingCard.classList.remove("is-dragging");
                    }
                    container.classList.remove("is-drag-active");
                    clearDropState();
                    draggingCard = null;
                    saveStudentMainCardOrder(storageKey, container);
                    syncStudentViewSideHeight();
                });
            }

            applyStudentMainCardOrder(storageKey, container);
            getStudentMainStackCards(container).forEach(bindCard);

            container.addEventListener("dragover", function (event) {
                if (!draggingCard) {
                    return;
                }

                event.preventDefault();
                const targetCard = event.target.closest("[data-student-stack-card]");
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
                saveStudentMainCardOrder(storageKey, container);
                syncStudentViewSideHeight();
            });
        }

        function initStudentMainCards() {
            const container = prepareStudentMainCardStack();
            if (!container) {
                return;
            }

            initStudentMainCardReorder(container);
            initStudentMainCardCollapse(container);
        }

        function getStudentSideCards(container) {
            return Array.from((container || document).querySelectorAll("[data-family-side-card]"));
        }

        function readStudentSideStoredKeys(storageKey) {
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

        function saveStudentSideCardOrder(storageKey, container) {
            if (!storageKey || !container) {
                return;
            }

            const orderedKeys = getStudentSideCards(container)
                .map(function (card) {
                    return card.dataset.familySideCardKey;
                })
                .filter(Boolean);

            try {
                window.localStorage.setItem(storageKey, JSON.stringify(orderedKeys));
            } catch (error) {}
        }

        function applyStudentSideCardOrder(storageKey, container) {
            const orderedKeys = readStudentSideStoredKeys(storageKey);
            if (!orderedKeys.length || !container) {
                return;
            }

            const cardMap = new Map(
                getStudentSideCards(container).map(function (card) {
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

        function syncStudentViewSideHeight() {
            const form = document.getElementById("studente-detail-form");
            if (!form) {
                return;
            }

            const side = form.querySelector(".student-dashboard-side");
            const isStacked = window.matchMedia && window.matchMedia("(max-width: 980px)").matches;
            if (!side || !form.classList.contains("is-view-mode") || isStacked) {
                form.style.removeProperty("--student-side-height");
                return;
            }

            form.style.setProperty("--student-side-height", `${Math.ceil(side.getBoundingClientRect().height)}px`);
        }

        function initStudentViewSideHeightSync() {
            const form = document.getElementById("studente-detail-form");
            const side = form ? form.querySelector(".student-dashboard-side") : null;
            if (!form || !side || form.dataset.studentSideHeightSyncBound === "1") {
                return;
            }

            form.dataset.studentSideHeightSyncBound = "1";
            let pendingFrame = null;
            const scheduleSync = function () {
                if (pendingFrame) {
                    window.cancelAnimationFrame(pendingFrame);
                }
                pendingFrame = window.requestAnimationFrame(function () {
                    pendingFrame = null;
                    syncStudentViewSideHeight();
                });
            };

            if (window.ResizeObserver) {
                const observer = new ResizeObserver(scheduleSync);
                observer.observe(side);
            }

            window.addEventListener("resize", scheduleSync);
            scheduleSync();
        }

        function getStudentSideCollapseStorageKey(card) {
            const container = card.closest("[data-family-side-reorder], .student-dashboard-side");
            return (container && container.dataset.familySideCollapseKey) ||
                `arboris-student-side-card-collapsed-${config.studenteId || "new"}`;
        }

        function saveStudentSideCollapsedKeys(storageKey) {
            if (!storageKey) {
                return;
            }

            const collapsedKeys = Array.from(document.querySelectorAll(".student-dashboard-side [data-family-side-card].is-collapsed"))
                .map(function (card) {
                    return card.dataset.familySideCardKey;
                })
                .filter(Boolean);

            try {
                window.localStorage.setItem(storageKey, JSON.stringify(collapsedKeys));
            } catch (error) {}
        }

        function getStudentSideCardTitle(card) {
            const title = card.querySelector(".family-side-card-head h2, h2");
            return title ? title.textContent.replace(/\s+/g, " ").trim() : "sidebar";
        }

        function setStudentSideCardCollapsed(card, collapsed) {
            const body = card.querySelector("[data-family-side-card-body]");
            const toggle = card.querySelector("[data-family-side-collapse-toggle]");
            const title = getStudentSideCardTitle(card);

            card.classList.toggle("is-collapsed", collapsed);

            if (body) {
                if (!body.id && card.dataset.familySideCardKey) {
                    body.id = `student-side-card-body-${card.dataset.familySideCardKey}`;
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

            syncStudentViewSideHeight();
        }

        function initStudentSideCardCollapse() {
            const storageGroups = new Map();

            getStudentSideCards(document).forEach(function (card) {
                const storageKey = getStudentSideCollapseStorageKey(card);
                if (!storageGroups.has(storageKey)) {
                    storageGroups.set(storageKey, readStudentSideStoredKeys(storageKey));
                }

                const collapsedKeys = storageGroups.get(storageKey);
                setStudentSideCardCollapsed(card, collapsedKeys.includes(card.dataset.familySideCardKey || ""));

                const toggle = card.querySelector("[data-family-side-collapse-toggle]");
                if (!toggle || toggle.dataset.studentSideCollapseBound === "1") {
                    return;
                }

                toggle.dataset.studentSideCollapseBound = "1";
                toggle.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    setStudentSideCardCollapsed(card, !card.classList.contains("is-collapsed"));
                    saveStudentSideCollapsedKeys(storageKey);
                });
            });
        }

        function initStudentSideCardReorder() {
            document.querySelectorAll(".student-dashboard-side[data-family-side-reorder]").forEach(function (container) {
                if (container.dataset.studentSideReorderBound === "1") {
                    return;
                }

                container.dataset.studentSideReorderBound = "1";
                const storageKey = container.dataset.familySideOrderKey || `arboris-student-side-card-order-${config.studenteId || "new"}`;
                let draggingCard = null;

                function clearDropState() {
                    container.querySelectorAll(".family-side-card.is-drop-target").forEach(function (card) {
                        card.classList.remove("is-drop-target");
                    });
                }

                function bindCard(card) {
                    if (card.dataset.studentSideDragBound === "1") {
                        return;
                    }

                    card.dataset.studentSideDragBound = "1";
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
                        saveStudentSideCardOrder(storageKey, container);
                        syncStudentViewSideHeight();
                    });
                }

                applyStudentSideCardOrder(storageKey, container);
                getStudentSideCards(container).forEach(bindCard);

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
                    saveStudentSideCardOrder(storageKey, container);
                    syncStudentViewSideHeight();
                });
            });
        }

        function initStudentRateYearSwitch() {
            document.querySelectorAll(".student-rate-summary-card").forEach(function (card) {
                if (card.dataset.studentRateYearSwitchBound === "1") {
                    return;
                }

                card.dataset.studentRateYearSwitchBound = "1";

                function activateYear(yearKey) {
                    card.querySelectorAll("[data-family-rate-year-tab]").forEach(function (button) {
                        const isActive = button.dataset.familyRateYearTab === yearKey;
                        button.classList.toggle("is-active", isActive);
                        button.setAttribute("aria-selected", isActive ? "true" : "false");
                    });

                    card.querySelectorAll("[data-family-rate-year-panel]").forEach(function (panel) {
                        const isActive = panel.dataset.familyRateYearPanel === yearKey;
                        panel.classList.toggle("is-active", isActive);
                        panel.hidden = !isActive;
                    });

                    card.querySelectorAll("[data-family-rate-year-actions]").forEach(function (actions) {
                        const isActive = actions.dataset.familyRateYearActions === yearKey;
                        actions.classList.toggle("is-active", isActive);
                        actions.hidden = !isActive;
                    });

                    syncStudentViewSideHeight();
                }

                card.querySelectorAll("[data-family-rate-year-tab]").forEach(function (button) {
                    button.addEventListener("click", function () {
                        activateYear(button.dataset.familyRateYearTab || "");
                    });
                });
            });
        }

        function initStudentStatCardLinks() {
            document.querySelectorAll(".student-stat-grid .family-stat-card[href^='#tab-']").forEach(function (link) {
                if (link.dataset.studentStatLinkBound === "1") {
                    return;
                }

                link.dataset.studentStatLinkBound = "1";
                link.addEventListener("click", function (event) {
                    event.preventDefault();
                    const context = getActiveStudentPageEditContext();
                    if (context) {
                        showStudentCardLockMessage(link);
                        return;
                    }

                    const tabId = (link.getAttribute("href") || "").replace(/^#/, "");
                    if (!tabId) {
                        return;
                    }

                    activateInlineTab(tabId);

                    const inlineRoot = studenteInlineRoot();
                    if (inlineRoot && typeof inlineRoot.scrollIntoView === "function") {
                        inlineRoot.scrollIntoView({ behavior: "smooth", block: "start" });
                    }
                });
            });
        }

        function initStudentSideCards() {
            initStudentMainCards();
            initStudentSideCardCollapse();
            initStudentSideCardReorder();
            initStudentRateYearSwitch();
            initStudentViewSideHeightSync();
        }

        function mountInlineForCard(prefix) {
            const manager = inlineManagers && inlineManagers[prefix];
            if (!manager) {
                return null;
            }

            setInlineTarget(prefix);
            tabs.activateTab(`tab-${prefix}`, getStudenteTabStorageKey());

            const mounted = manager.add();
            if (mounted && mounted.state) {
                inlineFormsets.markBundleForAddOnlyEdit(mounted.state, {
                    form: "studente-detail-form",
                });
            }
            refreshInlineEditScope();
            refreshTabCounts();
            return mounted;
        }

        function getEnrollmentBundle(row) {
            return inlineFormsets.getRowBundle(row, {
                companionClasses: ["inline-economic-row", "inline-notes-row"],
            });
        }

        function buildMainCardEditor(card) {
            const formRoot = document.getElementById("studente-lock-container");
            if (!card || !formRoot) {
                return null;
            }

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor student-main-card-editor";
            editor.__studentDetailFieldSnapshot = snapshotFields([formRoot]);

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = "Modifica dati principali";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            appendRelatedField(grid, formRoot, "#id_famiglia", "Famiglia", "family-student-editor-field-wide", editor, "famiglia");
            appendInputField(grid, formRoot, "#id_cognome", "Cognome", "family-student-editor-field-half", editor);
            appendInputField(grid, formRoot, "#id_nome", "Nome", "family-student-editor-field-half", editor);
            appendInputField(grid, formRoot, "#id_data_nascita", "Data nascita", "family-student-editor-field-half", editor);
            appendInputField(grid, formRoot, "#id_sesso", "Sesso", "family-student-editor-field-half", editor);
            appendInputField(grid, formRoot, "#id_luogo_nascita_search", "Luogo nascita", "family-student-editor-field-wide", editor);
            appendInputField(grid, formRoot, "#id_nazionalita", "Nazionalit\u00e0", "family-student-editor-field-third", editor);
            appendInputField(grid, formRoot, "#id_codice_fiscale", "Codice fiscale", "family-student-editor-field-third", editor);
            appendRelatedField(grid, formRoot, "#id_indirizzo", "Indirizzo", "family-student-editor-field-wide family-student-editor-address-field", editor, "indirizzo");
            appendCheckboxField(grid, formRoot, "#id_attivo", "Attivo", "", editor);

            editor.appendChild(grid);

            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.name = "_save";
            saveButton.className = "btn btn-save-soft btn-sm btn-icon-text";
            saveButton.dataset.studentMainSubmit = "1";
            saveButton.innerHTML = iconHtml("check", "Salva");

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.studentMainAction = "cancel";
            cancelButton.innerHTML = iconHtml("chevron-left", "Annulla");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            editor.appendChild(actions);

            card.appendChild(editor);
            card.classList.add("is-card-editing");
            initEditorEnhancements(editor);
            wireMainCardActions(editor);
            refreshStudentPageActionLocks();
            return editor;
        }

        function openMainCardEditor(trigger) {
            const card = getMainCard();
            if (!card) {
                return;
            }

            const context = getActiveStudentPageEditContext();
            if (context && context.kind !== "main") {
                showStudentCardLockMessage(trigger || card);
                return;
            }

            const existingEditor = card.querySelector(".student-main-card-editor");
            if (existingEditor) {
                const field = existingEditor.querySelector("#id_nome, #id_cognome, input[type='text']:not(.searchable-select-input), textarea");
                if (field) field.focus();
                return;
            }

            const editor = buildMainCardEditor(card);
            const field = editor ? editor.querySelector("#id_nome, #id_cognome, input[type='text']:not(.searchable-select-input), textarea") : null;
            if (field) field.focus();
        }

        function closeMainCardEditor(options) {
            const cfg = options || {};
            const card = getActiveMainEditorCard();
            const editor = card ? card.querySelector(".student-main-card-editor") : null;

            if (!card || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreFieldSnapshot(editor.__studentDetailFieldSnapshot);
            }

            restoreEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            if (window.studenteViewMode && typeof window.studenteViewMode.setEditing === "function") {
                window.studenteViewMode.setEditing(false);
            }
            refreshStudentPageActionLocks();
        }

        function buildEnrollmentCardEditor(card, row, options) {
            const cfg = options || {};
            const state = getEnrollmentBundle(row);
            const roots = state ? [state.row].concat(state.companionRows) : [row];

            inlineFormsets.setRowInputsEnabled(row, true, {
                includeCompanionRows: true,
                companionClasses: ["inline-economic-row", "inline-notes-row"],
                skipHiddenInputs: false,
            });

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor student-enrollment-card-editor";
            editor.__studentDetailFieldSnapshot = snapshotFields(roots);

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica iscrizione";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            appendRelatedField(grid, row, 'select[name$="-anno_scolastico"]', "Anno scolastico", "family-student-editor-field-third", editor, "anno scolastico");
            appendRelatedField(grid, row, 'select[name$="-classe"]', "Classe", "family-student-editor-field-third", editor, "classe");
            appendRelatedField(grid, row, 'select[name$="-gruppo_classe"]', "Pluriclasse", "family-student-editor-field-third", editor, "pluriclasse");
            appendInputField(grid, row, 'input[name$="-data_iscrizione"]', "Data iscrizione", "family-student-editor-field-third", editor);
            appendInputField(grid, row, 'input[name$="-data_fine_iscrizione"]', "Fine iscrizione", "family-student-editor-field-third", editor);
            appendRelatedField(grid, row, 'select[name$="-stato_iscrizione"]', "Stato", "family-student-editor-field-third", editor, "stato iscrizione");

            roots.forEach(function (currentRoot) {
                appendRelatedField(grid, currentRoot, 'select[name$="-condizione_iscrizione"]', "Tipo di retta", "family-student-editor-field-half", editor, "tipo di retta");
                appendRelatedField(grid, currentRoot, 'select[name$="-agevolazione"]', "Agevolazione", "family-student-editor-field-half", editor, "agevolazione");
                appendCheckboxField(grid, currentRoot, 'input[type="checkbox"][name$="-riduzione_speciale"]', "Riduzione speciale", "", editor);
                appendInputField(grid, currentRoot, 'input[name$="-importo_riduzione_speciale"]', "Importo riduzione speciale", "family-student-editor-field-third", editor);
                appendCheckboxField(grid, currentRoot, 'input[type="checkbox"][name$="-non_pagante"]', "Studente non pagante", "", editor);
                appendInputField(grid, currentRoot, 'select[name$="-modalita_pagamento_retta"]', "Pagamento retta", "family-student-editor-field-third", editor);
                appendInputField(grid, currentRoot, 'select[name$="-sconto_unica_soluzione_tipo"]', "Sconto unica soluzione", "family-student-editor-field-half", editor);
                appendInputField(grid, currentRoot, 'input[name$="-scadenza_pagamento_unica"]', "Scadenza pagamento unico", "family-student-editor-field-third", editor);
                appendCheckboxField(grid, currentRoot, 'input[type="checkbox"][name$="-attiva"]', "Iscrizione attiva", "", editor);
                appendInputField(grid, currentRoot, 'textarea[name$="-note_amministrative"]', "Note amministrative", "family-student-editor-field-wide", editor);
                appendInputField(grid, currentRoot, 'textarea[name$="-note"]', "Note generali", "family-student-editor-field-wide", editor);
            });

            editor.appendChild(grid);

            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.className = "btn btn-save-soft btn-sm btn-icon-text";
            saveButton.dataset.cardInlineSubmit = "iscrizioni";
            saveButton.innerHTML = iconHtml("check", "Salva");

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.enrollmentCardAction = "cancel";
            cancelButton.innerHTML = iconHtml("chevron-left", "Annulla modifiche");

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "btn btn-danger btn-sm btn-icon-text";
            removeButton.dataset.enrollmentCardAction = "remove";
            removeButton.innerHTML = iconHtml("trash", "Rimuovi");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            actions.appendChild(removeButton);
            editor.appendChild(actions);

            card.appendChild(editor);
            card.classList.add("is-card-editing");
            initEditorEnhancements(editor);
            editor.querySelectorAll('select[name$="-modalita_pagamento_retta"], select[name$="-sconto_unica_soluzione_tipo"]').forEach(function (select) {
                select.dispatchEvent(new Event("change", { bubbles: true }));
            });
            wireEnrollmentCardActions(editor);
            refreshStudentPageActionLocks();
            return editor;
        }

        function openEnrollmentCardEditor(card, options) {
            if (!card) {
                return;
            }

            const context = getActiveStudentPageEditContext();
            if (context && context.card !== card) {
                showStudentCardLockMessage(card);
                return;
            }

            const existingEditor = card.querySelector(".student-enrollment-card-editor");
            if (existingEditor) {
                const field = existingEditor.querySelector("input[type='text'], input[type='date'], select, textarea");
                if (field) field.focus();
                return;
            }

            const row = getEnrollmentRowFromCard(card);
            if (!row) {
                return;
            }

            const titleNode = card.querySelector(".student-enrollment-card-head h3");
            const editor = buildEnrollmentCardEditor(card, row, Object.assign({
                title: titleNode ? `Modifica ${titleNode.textContent.trim().toLowerCase()}` : "Modifica iscrizione",
            }, options || {}));
            const field = editor ? editor.querySelector("input[type='text'], input[type='date'], select, textarea") : null;
            if (field) field.focus();
        }

        function addEnrollmentCardFromView(trigger) {
            const list = getEnrollmentCardList();
            if (!list) {
                return;
            }

            const mounted = mountInlineForCard("iscrizioni");
            const row = mounted && mounted.state ? mounted.state.row : null;
            const prefix = getInlinePrefixFromRow(row);
            if (!row || !prefix) {
                return;
            }

            const card = document.createElement("article");
            card.className = "student-enrollment-card student-enrollment-card-new is-card-editing";
            card.dataset.enrollmentCard = "1";
            card.dataset.enrollmentFormPrefix = prefix;
            const addButton = list.querySelector(".family-dashed-add");
            list.insertBefore(card, addButton || null);
            const editor = buildEnrollmentCardEditor(card, row, { title: "Nuova iscrizione", isNew: true });
            wireEnrollmentCardActions(card);
            syncEnrollmentCardEmptyState();
            refreshStudentPageActionLocks();
            if (trigger && typeof card.scrollIntoView === "function") {
                card.scrollIntoView({ behavior: "smooth", block: "center" });
            }
            const field = editor ? editor.querySelector("input[type='text'], input[type='date'], select, textarea") : null;
            if (field) field.focus();
        }

        function closeEnrollmentCardEditor(card, row, options) {
            const cfg = options || {};
            const editor = card ? card.querySelector(".student-enrollment-card-editor") : null;
            if (!card || !row || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreFieldSnapshot(editor.__studentDetailFieldSnapshot);
            }

            restoreEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            inlineFormsets.setRowInputsEnabled(row, false, {
                includeCompanionRows: true,
                companionClasses: ["inline-economic-row", "inline-notes-row"],
                skipHiddenInputs: false,
            });
            refreshStudentPageActionLocks();
        }

        function cancelEnrollmentCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-enrollment-card]") : getActiveEnrollmentEditingCard();
            const row = getEnrollmentRowFromCard(card);
            if (!card || !row) {
                return;
            }

            if (!inlineFormsets.isRowPersisted(row)) {
                inlineManagers.iscrizioni.remove(row);
                card.remove();
                refreshTabCounts();
                syncEnrollmentCardEmptyState();
                refreshStudentPageActionLocks();
                return;
            }

            closeEnrollmentCardEditor(card, row, { restoreValues: true });
        }

        function removeEnrollmentCardEditor(button) {
            const card = button ? button.closest("[data-enrollment-card]") : null;
            const row = getEnrollmentRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const isPersisted = inlineFormsets.isRowPersisted(row);
            const message = isPersisted
                ? "Confermi la rimozione di questa iscrizione? La modifica sara applicata al salvataggio."
                : "Confermi l'annullamento della nuova iscrizione?";
            if (!window.confirm(message)) {
                return;
            }

            if (!isPersisted) {
                inlineManagers.iscrizioni.remove(row);
                card.remove();
                refreshTabCounts();
                syncEnrollmentCardEmptyState();
                refreshStudentPageActionLocks();
                return;
            }

            const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            if (deleteInput) {
                deleteInput.disabled = false;
                deleteInput.checked = true;
            }

            const saveButton = card.querySelector('[data-card-inline-submit="iscrizioni"]');
            if (saveButton && typeof saveButton.click === "function") {
                saveButton.formNoValidate = true;
                saveButton.setAttribute("formnovalidate", "formnovalidate");
                saveButton.click();
            }
        }

        function createRelativeCardActions() {
            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.className = "btn btn-save-soft btn-sm btn-icon-text";
            saveButton.dataset.cardInlineSubmit = "parenti";
            saveButton.innerHTML = iconHtml("check", "Salva");

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.relativeCardAction = "cancel";
            cancelButton.innerHTML = iconHtml("chevron-left", "Annulla modifiche");

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "btn btn-danger btn-sm btn-icon-text";
            removeButton.dataset.relativeCardAction = "remove";
            removeButton.innerHTML = iconHtml("trash", "Rimuovi");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            actions.appendChild(removeButton);
            return actions;
        }

        function buildRelativeCardEditor(card, row, options) {
            const cfg = options || {};
            const subformRow = getFamiliareSubformRow(row);
            const roots = [row, subformRow].filter(Boolean);

            setRelativeRowBundleEnabled(row, true);

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor family-relative-card-editor";
            editor.__studentDetailFieldSnapshot = snapshotFields(roots);

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica parente";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            appendInputField(grid, row, 'input[name$="-nome"]', "Nome", "family-student-editor-field-half", editor);
            appendInputField(grid, row, 'input[name$="-cognome"]', "Cognome", "family-student-editor-field-half", editor);
            appendRelatedField(grid, row, 'select[name$="-relazione_familiare"]', "Parentela", "family-student-editor-field-third", editor, "parentela");
            appendInputField(grid, row, 'input[name$="-telefono"]', "Telefono", "family-student-editor-field-third", editor);
            appendInputField(grid, row, 'input[name$="-email"]', "Email", "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'select[name$="-sesso"]', "Sesso", "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-data_nascita"]', "Data nascita", "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-luogo_nascita_search"]', "Luogo nascita", "family-student-editor-field-wide", editor);
            appendSubformField(grid, subformRow, 'select[name$="-nazionalita"]', "Nazionalit\u00e0", "family-student-editor-field-third", editor);
            appendSubformField(grid, subformRow, 'input[name$="-codice_fiscale"]', "Codice fiscale", "family-student-editor-field-third", editor);
            appendRelativeAddressField(grid, row, editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-convivente"]', "Convivente", "", editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-referente_principale"]', "Referente principale", "", editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-abilitato_scambio_retta"]', "Scambio retta", "", editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-attivo"]', "Attivo", "", editor);

            editor.appendChild(grid);
            editor.appendChild(createRelativeCardActions());
            card.appendChild(editor);
            card.classList.add("is-card-editing");
            initEditorEnhancements(editor);
            if (personRules && typeof personRules.bindSexFromRelation === "function") {
                personRules.bindSexFromRelation({
                    relationSelect: row.querySelector('select[name$="-relazione_familiare"]'),
                    sexSelect: subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null,
                    bindFlag: "studentParentiRelationSexBound",
                });
            }
            wireRelativeCardActions(editor);
            refreshStudentPageActionLocks();
            return editor;
        }

        function openRelativeCardEditor(card, options) {
            if (!card) {
                return;
            }

            const context = getActiveStudentPageEditContext();
            if (context && context.card !== card) {
                showStudentCardLockMessage(card);
                return;
            }

            const existingEditor = card.querySelector(".family-relative-card-editor");
            if (existingEditor) {
                const field = existingEditor.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea");
                if (field) field.focus();
                return;
            }

            const row = getRelativeRowFromCard(card);
            if (!row) {
                return;
            }

            const titleNode = card.querySelector(".family-person-heading h3");
            const editor = buildRelativeCardEditor(card, row, Object.assign({
                title: titleNode ? `Modifica ${titleNode.textContent.trim()}` : "Modifica parente",
            }, options || {}));
            const field = editor ? editor.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea") : null;
            if (field) field.focus();
        }

        function addRelativeCardFromView(trigger) {
            const list = getRelativeCardList();
            if (!list) {
                return;
            }

            const mounted = mountInlineForCard("parenti");
            const row = mounted && mounted.state ? mounted.state.row : null;
            const prefix = getInlinePrefixFromRow(row);
            if (!row || !prefix) {
                return;
            }

            const card = document.createElement("article");
            card.className = "family-person-card family-relative-card family-relative-card-new is-card-editing";
            card.dataset.relativeCard = "1";
            card.dataset.relativeFormPrefix = prefix;
            card.appendChild(createPersonCardAvatar(list));
            const addButton = list.querySelector(".family-dashed-add");
            list.insertBefore(card, addButton || null);
            const editor = buildRelativeCardEditor(card, row, {
                title: list.dataset.relativeNewTitle || "Nuovo parente",
                isNew: true,
            });
            wireRelativeCardActions(card);
            syncRelativeCardEmptyState();
            refreshStudentPageActionLocks();
            if (trigger && typeof card.scrollIntoView === "function") {
                card.scrollIntoView({ behavior: "smooth", block: "center" });
            }
            const field = editor ? editor.querySelector("input[type='text'], input[type='email'], input[type='date'], select, textarea") : null;
            if (field) field.focus();
        }

        function closeRelativeCardEditor(card, row, options) {
            const cfg = options || {};
            const editor = card ? card.querySelector(".family-relative-card-editor") : null;
            if (!card || !row || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreFieldSnapshot(editor.__studentDetailFieldSnapshot);
            }

            restoreEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            setRelativeRowBundleEnabled(row, false);
            refreshStudentPageActionLocks();
        }

        function cancelRelativeCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-relative-card]") : getActiveRelativeEditingCard();
            const row = getRelativeRowFromCard(card);
            if (!card || !row) {
                return;
            }

            if (!inlineFormsets.isRowPersisted(row)) {
                inlineManagers.parenti.remove(row);
                card.remove();
                refreshTabCounts();
                syncRelativeCardEmptyState();
                refreshStudentPageActionLocks();
                return;
            }

            closeRelativeCardEditor(card, row, { restoreValues: true });
        }

        function removeRelativeCardEditor(button) {
            const card = button ? button.closest("[data-relative-card]") : null;
            const row = getRelativeRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const isPersisted = inlineFormsets.isRowPersisted(row);
            const titleNode = card.querySelector(".family-person-heading h3, .family-student-card-editor-head h3");
            const label = titleNode ? titleNode.textContent.trim().replace(/^Modifica\s+/, "") : "questo parente";
            const message = isPersisted
                ? `Confermi la rimozione di ${label}? La modifica sara applicata al salvataggio.`
                : "Confermi l'annullamento del nuovo parente?";
            if (!window.confirm(message)) {
                return;
            }
            if (isPersisted && !window.confirm(`Seconda conferma: ${label} verra eliminato al salvataggio. Vuoi continuare?`)) {
                return;
            }

            if (!isPersisted) {
                inlineManagers.parenti.remove(row);
                card.remove();
                refreshTabCounts();
                syncRelativeCardEmptyState();
                refreshStudentPageActionLocks();
                return;
            }

            const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            if (deleteInput) {
                deleteInput.disabled = false;
                deleteInput.checked = true;
            }

            const saveButton = card.querySelector('[data-card-inline-submit="parenti"]');
            if (saveButton && typeof saveButton.click === "function") {
                saveButton.formNoValidate = true;
                saveButton.setAttribute("formnovalidate", "formnovalidate");
                saveButton.click();
            }
        }

        function createDocumentCardIcon(list) {
            const sprite = list ? list.dataset.uiIconsSprite || "" : "";
            const icon = document.createElement("span");
            icon.className = "family-document-icon";
            icon.setAttribute("aria-hidden", "true");

            const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
            use.setAttribute("href", `${sprite}#document`);
            svg.appendChild(use);
            icon.appendChild(svg);
            return icon;
        }

        function buildDocumentCardEditor(card, row, options) {
            const cfg = options || {};
            inlineFormsets.setRowInputsEnabled(row, true, { skipHiddenInputs: false });

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor family-document-card-editor";
            editor.__studentDetailFieldSnapshot = snapshotFields([row]);

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica documento";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";
            appendRelatedField(grid, row, 'select[name$="-tipo_documento"]', "Tipo documento", "family-student-editor-field-half", editor, "tipo documento");
            appendInputField(grid, row, 'input[type="file"][name$="-file"]', "File", "family-student-editor-field-wide", editor);
            appendInputField(grid, row, 'textarea[name$="-descrizione"]', "Descrizione", "family-student-editor-field-wide", editor);
            appendInputField(grid, row, 'input[name$="-scadenza"]', "Scadenza", "family-student-editor-field-third", editor);
            appendCheckboxField(grid, row, 'input[type="checkbox"][name$="-visibile"]', "Visibile", "", editor);
            appendInputField(grid, row, 'textarea[name$="-note"]', "Note", "family-student-editor-field-wide", editor);
            editor.appendChild(grid);

            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.className = "btn btn-save-soft btn-sm btn-icon-text";
            saveButton.dataset.cardInlineSubmit = "documenti";
            saveButton.innerHTML = iconHtml("check", "Salva");

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.documentCardAction = "cancel";
            cancelButton.innerHTML = iconHtml("chevron-left", "Annulla modifiche");

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "btn btn-danger btn-sm btn-icon-text";
            removeButton.dataset.documentCardAction = "remove";
            removeButton.innerHTML = iconHtml("trash", "Rimuovi");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            actions.appendChild(removeButton);
            editor.appendChild(actions);

            card.appendChild(editor);
            card.classList.add("is-card-editing");
            initEditorEnhancements(editor);
            wireDocumentCardActions(editor);
            refreshStudentPageActionLocks();
            return editor;
        }

        function openDocumentCardEditor(card, options) {
            if (!card) {
                return;
            }

            const context = getActiveStudentPageEditContext();
            if (context && context.card !== card) {
                showStudentCardLockMessage(card);
                return;
            }

            const existingEditor = card.querySelector(".family-document-card-editor");
            if (existingEditor) {
                const field = existingEditor.querySelector("input[type='text'], input[type='file'], input[type='date'], select, textarea");
                if (field) field.focus();
                return;
            }

            const row = getDocumentRowFromCard(card);
            if (!row) {
                return;
            }

            const titleNode = card.querySelector(".family-document-main h3");
            const editor = buildDocumentCardEditor(card, row, Object.assign({
                title: titleNode ? `Modifica ${titleNode.textContent.trim()}` : "Modifica documento",
            }, options || {}));
            const field = editor ? editor.querySelector("input[type='text'], input[type='file'], input[type='date'], select, textarea") : null;
            if (field) field.focus();
        }

        function addDocumentCardFromView(trigger) {
            const list = getDocumentCardList();
            if (!list) {
                return;
            }

            const mounted = mountInlineForCard("documenti");
            const row = mounted && mounted.state ? mounted.state.row : null;
            const prefix = getInlinePrefixFromRow(row);
            if (!row || !prefix) {
                return;
            }

            const card = document.createElement("article");
            card.className = "family-document-card family-document-card-new is-card-editing";
            card.dataset.documentCard = "1";
            card.dataset.documentFormPrefix = prefix;
            card.appendChild(createDocumentCardIcon(list));
            const addButton = list.querySelector(".family-dashed-add");
            list.insertBefore(card, addButton || null);
            const editor = buildDocumentCardEditor(card, row, { title: "Nuovo documento", isNew: true });
            wireDocumentCardActions(card);
            syncDocumentCardEmptyState();
            refreshStudentPageActionLocks();
            if (trigger && typeof card.scrollIntoView === "function") {
                card.scrollIntoView({ behavior: "smooth", block: "center" });
            }
            const field = editor ? editor.querySelector("input[type='text'], input[type='file'], input[type='date'], select, textarea") : null;
            if (field) field.focus();
        }

        function closeDocumentCardEditor(card, row, options) {
            const cfg = options || {};
            const editor = card ? card.querySelector(".family-document-card-editor") : null;
            if (!card || !row || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreFieldSnapshot(editor.__studentDetailFieldSnapshot);
            }

            restoreEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            inlineFormsets.setRowInputsEnabled(row, false, { skipHiddenInputs: false });
            refreshStudentPageActionLocks();
        }

        function cancelDocumentCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-document-card]") : getActiveDocumentEditingCard();
            const row = getDocumentRowFromCard(card);
            if (!card || !row) {
                return;
            }

            if (!inlineFormsets.isRowPersisted(row)) {
                inlineManagers.documenti.remove(row);
                card.remove();
                refreshTabCounts();
                syncDocumentCardEmptyState();
                refreshStudentPageActionLocks();
                return;
            }

            closeDocumentCardEditor(card, row, { restoreValues: true });
        }

        function removeDocumentCardEditor(button) {
            const card = button ? button.closest("[data-document-card]") : null;
            const row = getDocumentRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const isPersisted = inlineFormsets.isRowPersisted(row);
            const message = isPersisted
                ? "Confermi la rimozione di questo documento? La modifica sara applicata al salvataggio."
                : "Confermi l'annullamento del nuovo documento?";
            if (!window.confirm(message)) {
                return;
            }

            if (!isPersisted) {
                inlineManagers.documenti.remove(row);
                card.remove();
                refreshTabCounts();
                syncDocumentCardEmptyState();
                refreshStudentPageActionLocks();
                return;
            }

            const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            if (deleteInput) {
                deleteInput.disabled = false;
                deleteInput.checked = true;
            }

            const saveButton = card.querySelector('[data-card-inline-submit="documenti"]');
            if (saveButton && typeof saveButton.click === "function") {
                saveButton.formNoValidate = true;
                saveButton.setAttribute("formnovalidate", "formnovalidate");
                saveButton.click();
            }
        }

        function confirmDocumentCardDelete(button) {
            const popupUrl = button ? button.dataset.popupUrl || "" : "";
            if (!popupUrl) {
                return;
            }

            const label = (button.dataset.documentDeleteLabel || "questo documento").replace(/\s+/g, " ").trim();
            if (!window.confirm(`Vuoi eliminare ${label}? Si aprira un popup di conferma prima della cancellazione definitiva.`)) {
                return;
            }

            if (relatedPopups && typeof relatedPopups.openRelatedPopup === "function") {
                relatedPopups.openRelatedPopup(popupUrl);
                return;
            }

            window.location.href = popupUrl;
        }

        function wireMainCardActions(root) {
            const container = root || document;
            container.querySelectorAll("[data-student-main-action]").forEach(function (element) {
                if (element.dataset.studentMainActionBound === "1") {
                    return;
                }

                element.dataset.studentMainActionBound = "1";
                element.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    const action = element.dataset.studentMainAction || "";
                    if (action === "edit") {
                        openMainCardEditor(element);
                    } else if (action === "cancel") {
                        closeMainCardEditor({ restoreValues: true });
                    }
                });
            });
        }

        function wireEnrollmentCardActions(root) {
            const container = root || document;
            container.querySelectorAll("[data-enrollment-card-action]").forEach(function (element) {
                if (element.dataset.enrollmentCardActionBound === "1") {
                    return;
                }

                element.dataset.enrollmentCardActionBound = "1";
                element.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    const action = element.dataset.enrollmentCardAction || "";
                    if (action === "add") {
                        addEnrollmentCardFromView(element);
                    } else if (action === "edit") {
                        openEnrollmentCardEditor(element.closest("[data-enrollment-card]"));
                    } else if (action === "cancel") {
                        cancelEnrollmentCardEditor(element);
                    } else if (action === "remove") {
                        removeEnrollmentCardEditor(element);
                    }
                });
            });
        }

        function wireDocumentCardActions(root) {
            const container = root || document;
            container.querySelectorAll("[data-document-card-action]").forEach(function (element) {
                if (element.dataset.documentCardActionBound === "1") {
                    return;
                }

                element.dataset.documentCardActionBound = "1";
                element.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    const action = element.dataset.documentCardAction || "";
                    if (action === "add") {
                        addDocumentCardFromView(element);
                    } else if (action === "edit") {
                        openDocumentCardEditor(element.closest("[data-document-card]"));
                    } else if (action === "cancel") {
                        cancelDocumentCardEditor(element);
                    } else if (action === "remove") {
                        removeDocumentCardEditor(element);
                    } else if (action === "delete") {
                        confirmDocumentCardDelete(element);
                    }
                });
            });
        }

        function wireRelativeCardActions(root) {
            const container = root || document;
            if (!container || typeof container.querySelectorAll !== "function") {
                return;
            }

            container.querySelectorAll("[data-relative-card-action]").forEach(function (element) {
                if (element.dataset.relativeCardActionBound === "1") {
                    return;
                }

                element.dataset.relativeCardActionBound = "1";
                element.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();

                    const action = element.dataset.relativeCardAction || "";
                    if (action === "add") {
                        addRelativeCardFromView(element);
                    } else if (action === "edit") {
                        openRelativeCardEditor(element.closest("[data-relative-card]"));
                    } else if (action === "cancel") {
                        cancelRelativeCardEditor(element);
                    } else if (action === "remove") {
                        removeRelativeCardEditor(element);
                    }
                });
            });
        }

        function bindCardSubmitScope() {
            const form = document.getElementById("studente-detail-form");
            if (!form || form.dataset.studentCardSubmitScopeBound === "1") {
                return;
            }

            form.dataset.studentCardSubmitScopeBound = "1";
            form.addEventListener("submit", function (event) {
                const submitter = event.submitter;
                const modeInput = document.getElementById("studente-edit-scope");
                const targetInput = document.getElementById("studente-inline-target");
                const activeContext = getActiveStudentPageEditContext();
                const cardInlineSubmit = submitter && submitter.dataset ? submitter.dataset.cardInlineSubmit || "" : "";

                if (submitter && submitter.dataset && submitter.dataset.studentMainSubmit === "1") {
                    if (modeInput) modeInput.value = "full";
                    return;
                }

                if (cardInlineSubmit) {
                    if (modeInput) modeInput.value = "inline";
                    if (targetInput) targetInput.value = cardInlineSubmit;
                    return;
                }

                if (activeContext && activeContext.kind === "main") {
                    if (modeInput) modeInput.value = "full";
                    return;
                }

                if (activeContext && activeContext.target && activeContext.target !== "main") {
                    if (modeInput) modeInput.value = "inline";
                    if (targetInput) targetInput.value = activeContext.target;
                }
            });
        }

        function createInlineManager(prefix, options) {
            return inlineFormsets.createManager({
                prefix: prefix,
                prepareOptions: options && options.prepareOptions ? options.prepareOptions : {},
                mountOptions: options && options.mountOptions ? options.mountOptions : {},
                removeOptions: options && options.removeOptions ? options.removeOptions : {},
            });
        }

        inlineManagers = {
            iscrizioni: createInlineManager("iscrizioni", {
                prepareOptions: {
                    companionClasses: ["inline-economic-row", "inline-notes-row"],
                },
                mountOptions: {
                    companionClasses: ["inline-economic-row", "inline-notes-row"],
                    enableInputs: true,
                    onReady: function (state) {
                        wireIscrizioneBundle(state);
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-economic-row", "inline-notes-row"],
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
            parenti: createInlineManager("parenti", {
                prepareOptions: {
                    companionClasses: ["inline-subform-row"],
                    includeCompanionRowsInData: true,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
                    enableInputs: true,
                    onReady: function (state) {
                        wireInlineRelatedButtons(state.row);
                        state.companionRows.forEach(function (row) {
                            wireInlineRelatedButtons(row);
                        });
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-subform-row"],
                },
            }),
        };

        function removeManagedInlineRow(button) {
            const row = button && button.closest ? button.closest("tr") : null;
            const table = row ? row.closest("table") : null;
            const prefix = table ? table.id.replace("-table", "") : "";
            const manager = prefix ? inlineManagers[prefix] : null;
            const removed = manager ? manager.remove(button) : null;

            if (removed) {
                if (prefix === "iscrizioni") {
                    syncIscrizioniInlineDetails();
                }
                refreshTabCounts();
            }
        }

        function syncDependentSelect(select, matcher) {
            if (!select) return;

            let hasSelectedVisibleOption = false;

            Array.from(select.options).forEach(option => {
                if (!option.value) {
                    option.hidden = false;
                    option.disabled = false;
                    return;
                }

                const isVisible = matcher(option);
                option.hidden = !isVisible;
                option.disabled = !isVisible;

                if (isVisible && option.selected) {
                    hasSelectedVisibleOption = true;
                }
            });

            if (select.value && !hasSelectedVisibleOption) {
                select.value = "";
            }
        }

        function wireIscrizioneRow(row) {
            if (!row || row.dataset.iscrizioneBound === "1") {
                return;
            }

            const state = getIscrizioneBundleState(row);
            const searchRoots = state ? [state.row].concat(state.companionRows) : [row];

            function findInBundle(selector) {
                for (const root of searchRoots) {
                    const match = root ? root.querySelector(selector) : null;
                    if (match) {
                        return match;
                    }
                }
                return null;
            }

            function findAllInBundle(selector) {
                return searchRoots.reduce(function (items, root) {
                    if (!root) {
                        return items;
                    }
                    return items.concat(Array.from(root.querySelectorAll(selector)));
                }, []);
            }

            const annoSelect = findInBundle('select[name$="-anno_scolastico"]');
            const classeSelect = findInBundle('select[name$="-classe"]');
            const gruppoClasseSelect = findInBundle('select[name$="-gruppo_classe"]');
            const condizioneSelect = findInBundle('select[name$="-condizione_iscrizione"]');
            const agevolazioneSelect = findInBundle('select[name$="-agevolazione"]');
            const riduzioneCheckbox = findInBundle('input[type="checkbox"][name$="-riduzione_speciale"]');
            const importoRiduzioneInput = findInBundle('input[name$="-importo_riduzione_speciale"]');
            const dataIscrizioneInput = findInBundle('input[name$="-data_iscrizione"]');
            const dataFineInput = findInBundle('input[name$="-data_fine_iscrizione"]');
            const modalitaPagamentoSelect = findInBundle('select[name$="-modalita_pagamento_retta"]');
            const scontoUnicoTipoSelect = findInBundle('select[name$="-sconto_unica_soluzione_tipo"]');
            const scontoUnicoValoreInput = findInBundle('input[name$="-sconto_unica_soluzione_valore"]');
            const scadenzaUnicoInput = findInBundle('input[name$="-scadenza_pagamento_unica"]');

            if (!annoSelect || !classeSelect || !condizioneSelect) {
                return;
            }

            row.dataset.iscrizioneBound = "1";

            function refreshDependentChoices() {
                const annoScolasticoId = annoSelect.value;
                const classeId = classeSelect.value;

                if (gruppoClasseSelect) {
                    syncDependentSelect(gruppoClasseSelect, function (option) {
                        const sameYear = option.dataset.annoScolastico === annoScolasticoId;
                        const classIds = (option.dataset.classIds || "").split(",").filter(Boolean);
                        return sameYear && (!classeId || classIds.includes(classeId));
                    });
                }
                syncDependentSelect(condizioneSelect, option => option.dataset.annoScolastico === annoScolasticoId);
            }

            function selectedAnnoDate(datasetKey) {
                const selectedAnno = annoSelect.options[annoSelect.selectedIndex];
                return selectedAnno ? (selectedAnno.dataset[datasetKey] || "") : "";
            }

            function bindAutoManagedDate(input, datasetKey) {
                if (!input) {
                    return;
                }

                const currentDefault = selectedAnnoDate(datasetKey);
                if (!input.value || input.value === currentDefault) {
                    input.dataset.autoManaged = "1";
                }

                input.addEventListener("input", function () {
                    delete input.dataset.autoManaged;
                });
            }

            function syncAutoManagedDate(input, datasetKey) {
                if (!input) {
                    return;
                }

                const nextDate = selectedAnnoDate(datasetKey);
                if (!nextDate) {
                    return;
                }

                if (!input.value || input.dataset.autoManaged === "1") {
                    input.value = nextDate;
                    input.dataset.autoManaged = "1";
                }
            }

            function syncIscrizioneDates() {
                syncAutoManagedDate(dataIscrizioneInput, "dataInizio");
                syncAutoManagedDate(dataFineInput, "dataFine");
            }

            bindAutoManagedDate(dataIscrizioneInput, "dataInizio");
            bindAutoManagedDate(dataFineInput, "dataFine");

            annoSelect.addEventListener("change", function () {
                refreshDependentChoices();
                syncIscrizioneDates();
            });
            classeSelect.addEventListener("change", refreshDependentChoices);

            function syncRiduzioneSpecialeState() {
                if (!riduzioneCheckbox || !importoRiduzioneInput) {
                    return;
                }

                const selectedCondizione = condizioneSelect.options[condizioneSelect.selectedIndex];
                const riduzioniAmmesse = !selectedCondizione || selectedCondizione.dataset.riduzioneSpecialeAmmessa !== "0";
                const enabled = riduzioniAmmesse && riduzioneCheckbox.checked;
                const currencyGroup = importoRiduzioneInput.closest(".currency-input-group");
                const agevolazioneCells = findAllInBundle(".iscrizione-agevolazione-cell, .inline-details-field-agevolazione");
                const riduzioneCells = findAllInBundle(".iscrizione-riduzione-cell, .inline-details-field-riduzione");
                const importoCells = findAllInBundle(".iscrizione-importo-riduzione-cell, .inline-details-field-importo");

                agevolazioneCells.forEach(cell => cell.classList.remove("is-hidden"));
                riduzioneCells.forEach(cell => cell.classList.remove("is-hidden"));
                importoCells.forEach(cell => cell.classList.remove("is-hidden"));

                if (!riduzioniAmmesse) {
                    if (agevolazioneSelect) {
                        agevolazioneSelect.value = "";
                    }
                    riduzioneCheckbox.checked = false;
                }

                importoRiduzioneInput.readOnly = !enabled;
                importoRiduzioneInput.disabled = !enabled;
                importoRiduzioneInput.classList.toggle("is-readonly", !enabled);
                if (currencyGroup) {
                    currencyGroup.classList.toggle("is-disabled", !enabled || !riduzioniAmmesse);
                }

                if (!enabled) {
                    importoRiduzioneInput.value = "0.00";
                }
            }

            function setConditionalInputDisabled(input, disabled, options) {
                const cfg = options || {};
                if (!input) {
                    return;
                }

                input.disabled = disabled;
                if ("readOnly" in input) {
                    input.readOnly = disabled;
                }
                input.classList.toggle("is-conditional-disabled", disabled);
                input.classList.toggle("is-readonly", disabled);

                if (cfg.wrapperSelector) {
                    const wrapper = input.closest(cfg.wrapperSelector);
                    if (wrapper) {
                        wrapper.classList.toggle("is-conditional-disabled", disabled);
                    }
                }
            }

            function syncPagamentoUnicoState() {
                if (!modalitaPagamentoSelect || !scontoUnicoTipoSelect || !scontoUnicoValoreInput) {
                    return;
                }

                const pagamentoUnico = modalitaPagamentoSelect.value === "unica_soluzione";
                const scontoTipo = scontoUnicoTipoSelect.value || "nessuno";
                const scontoAttivo = pagamentoUnico && scontoTipo !== "nessuno";
                const currencyGroup = scontoUnicoValoreInput.closest(".currency-input-group");

                setConditionalInputDisabled(scontoUnicoValoreInput, !scontoAttivo);
                setConditionalInputDisabled(scadenzaUnicoInput, !pagamentoUnico, {
                    wrapperSelector: ".inline-details-field",
                });

                if (currencyGroup) {
                    currencyGroup.classList.toggle("is-disabled", !scontoAttivo);
                }
                if (!pagamentoUnico && scadenzaUnicoInput) {
                    scadenzaUnicoInput.value = "";
                }
                if (!scontoAttivo) {
                    scontoUnicoValoreInput.value = "0,00";
                }
            }

            if (modalitaPagamentoSelect && scontoUnicoTipoSelect && scontoUnicoValoreInput) {
                modalitaPagamentoSelect.addEventListener("change", syncPagamentoUnicoState);
                scontoUnicoTipoSelect.addEventListener("change", syncPagamentoUnicoState);
            }

            if (riduzioneCheckbox && importoRiduzioneInput) {
                riduzioneCheckbox.addEventListener("change", syncRiduzioneSpecialeState);
            }

            condizioneSelect.addEventListener("change", syncRiduzioneSpecialeState);
            refreshDependentChoices();
            syncIscrizioneDates();
            syncRiduzioneSpecialeState();
            syncPagamentoUnicoState();
            collapsible.initCollapsibleSections(row.parentElement);
        }

        function addManagedInlineForm(prefix) {
            const manager = inlineManagers[prefix];
            if (!manager) {
                return;
            }

            const form = document.getElementById("studente-detail-form");
            const isAlreadyAddOnlyMode = Boolean(form && form.classList.contains("is-inline-add-only-mode"));
            const shouldUseAddOnlyMode = Boolean(
                window.studenteViewMode &&
                (!window.studenteViewMode.isEditing() || isAlreadyAddOnlyMode)
            );
            let mounted = null;

            setInlineTarget(prefix);
            tabs.activateTab(`tab-${prefix}`, getStudenteTabStorageKey());

            if (window.studenteViewMode && !window.studenteViewMode.isEditing()) {
                window.studenteViewMode.setInlineEditing(true);
            }

            refreshInlineEditScope();
            updateInlineEditButtonLabel(`tab-${prefix}`);

            mounted = manager.add();

            if (!mounted) {
                return;
            }

            if (shouldUseAddOnlyMode && mounted.state) {
                inlineFormsets.markBundleForAddOnlyEdit(mounted.state, {
                    form: "studente-detail-form",
                });
            }

            refreshInlineEditScope();
            refreshTabCounts();
        }

        const famigliaSelect = document.getElementById("id_famiglia");
        const indirizzoSelect = document.getElementById("id_indirizzo");

        const addFamigliaBtn = document.getElementById("add-famiglia-btn");
        const editFamigliaBtn = document.getElementById("edit-famiglia-btn");
        let refreshFamigliaNavigation = function () {};

        const addIndirizzoBtn = document.getElementById("add-indirizzo-btn");
        const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
        const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");
        let refreshIndirizzoButtons = function () {};
        if (formTools && familyLinkedAddress && typeof formTools.bindFamilyAddressController === "function") {
            formTools.bindFamilyAddressController({
                familyLinkedAddress: familyLinkedAddress,
                familySelect: famigliaSelect,
                addressSelect: indirizzoSelect,
                surnameInput: document.getElementById("id_cognome"),
                helpElement: document.getElementById("studente-address-help"),
                fallbackLabelScriptId: "studente-famiglia-indirizzo-label",
                onRefreshButtons: updateMainButtons,
            });
        }

        if (formTools && typeof formTools.bindFamigliaNavigation === "function") {
            const famigliaNavigation = formTools.bindFamigliaNavigation({
                familySelect: famigliaSelect,
                addBtn: addFamigliaBtn,
                editBtn: editFamigliaBtn,
                createUrl: config.urls.creaFamiglia,
            });
            refreshFamigliaNavigation = famigliaNavigation.refresh;
        }

        if (routes && typeof routes.wireCrudButtonsById === "function" && relatedPopups && typeof relatedPopups.openRelatedPopup === "function") {
            const indirizzoCrud = routes.wireCrudButtonsById({
                select: indirizzoSelect,
                relatedType: "indirizzo",
                addBtn: addIndirizzoBtn,
                editBtn: editIndirizzoBtn,
                deleteBtn: deleteIndirizzoBtn,
                openRelatedPopup: relatedPopups.openRelatedPopup,
            });
            refreshIndirizzoButtons = indirizzoCrud.refresh;
        }
        refreshFamigliaNavigation();

        inlineManagers.iscrizioni.prepare();
        inlineManagers.documenti.prepare();
        inlineManagers.parenti.prepare();
        document.querySelectorAll("#iscrizioni-table tbody .inline-form-row").forEach(function (row) {
            wireIscrizioneBundle(getIscrizioneBundleState(row));
        });
        const inlineLockRoot = studenteInlineRoot();
        if (inlineLockRoot) {
            tabs.bindTabButtons(getStudenteTabStorageKey(), inlineLockRoot);
            inlineTabs.bindTabNavigationLock({
                containerId: inlineLockContainerId,
                targetInputId: targetInputId,
                getViewMode: function () {
                    return window.studenteViewMode;
                },
            });
        }
        document.querySelectorAll("#studente-inline-lock-container .tab-btn[data-tab-target]").forEach(btn => {
            btn.addEventListener("click", function () {
                setInlineTarget(btn.dataset.tabTarget);
                updateInlineEditButtonLabel(btn.dataset.tabTarget);
                syncActiveTabUrl(btn.dataset.tabTarget);
                refreshInlineEditScope();
            });
        });
        collapsible.initCollapsibleSections(document);
        wireInlineRelatedButtons(document);
        bindStudentPageActionLock();
        initStudentNoteDialog();
        initStudentSideCards();
        initStudentStatCardLinks();
        bindStudentCardStickyActions();
        wireMainCardActions(document);
        wireEnrollmentCardActions(document);
        wireDocumentCardActions(document);
        wireRelativeCardActions(document);
        bindCardSubmitScope();
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
        if (routes && typeof routes.wirePopupTriggerElements === "function" && relatedPopups && typeof relatedPopups.openRelatedPopup === "function") {
            routes.wirePopupTriggerElements(document, {
                openRelatedPopup: relatedPopups.openRelatedPopup,
            });
        }
        if (window.ArborisPopupWindowTriggers) {
            ArborisPopupWindowTriggers.wire(document);
        }
        restoreActiveTab();
        updateMainButtons();
        refreshTabCounts();
        syncEnrollmentCardEmptyState();
        syncDocumentCardEmptyState();
        syncRelativeCardEmptyState();
        refreshStudentPageActionLocks();
        bindRateRecalcForms();
        bindStandaloneSexFromNome();
    }

    return {
        init,
        refreshInlineEditScope: function () {
            refreshInlineEditScopeHandler();
        },
    };
})();
