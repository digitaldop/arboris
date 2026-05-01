window.ArborisFamigliaForm = (function () {
    let refreshInlineEditScopeHandler = function () {};
    let refreshLockedTabsHandler = function () {};

    function init(config) {
        const entityRoutes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = entityRoutes && entityRoutes.initRelatedPopups();
        const collapsible = window.ArborisCollapsible;
        const tabs = window.ArborisTabs;
        const inlineTabs = window.ArborisInlineTabs;
        const inlineFormsets = window.ArborisInlineFormsets;
        const personRules = window.ArborisPersonRules;
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;
        const formTools = window.ArborisAnagraficaFormTools;

        if (!entityRoutes || !relatedPopups || !collapsible || !tabs || !inlineTabs || !inlineFormsets || !personRules || !familyLinkedAddress || !formTools) {
            console.error("Arboris core JS non caricato correttamente.");
            return;
        }

        const openRelatedPopup = relatedPopups.openRelatedPopup;

        // Funzione per gestire la persistenza della tab attiva
        function getFamigliaTabStorageKey() {
            return `arboris-famiglia-form-active-tab-${config.famigliaId || "new"}`;
        }

        const inlineLockContainerId = "famiglia-inline-lock-container";
        const targetInputId = "famiglia-inline-target";
        const inlineEditButtonId = "enable-inline-edit-famiglia-btn";
        const famigliaInlineRoot = () => document.getElementById(inlineLockContainerId);
        const defaultInlineTab = config.defaultInlineTab || "familiari";
        const studentCardLockMessage = "Salva o annulla le modifiche dello studente corrente prima di continuare.";
        const familyCardPageLockMessage = "Salva, annulla o rimuovi la card corrente prima di continuare.";
        const cardStickyActionsId = "family-card-sticky-actions";
        const cardStickySpacerId = "family-card-sticky-spacer";

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

        function setInlineTarget(tabId) {
            inlineTabs.setInlineTargetValue(targetInputId, tabId);
        }

        function refreshInlineEditScope() {
            const form = document.getElementById("famiglia-detail-form");
            const panels = document.querySelectorAll('#famiglia-inline-lock-container .tab-panel[data-inline-scope]');
            const targetInput = document.getElementById("famiglia-inline-target");
            const target = targetInput ? targetInput.value : "";
            const isInlineEditing = Boolean(
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.isInlineEditing === "function" &&
                window.famigliaViewMode.isInlineEditing()
            );

            if (form) {
                if (isInlineEditing && target) {
                    form.dataset.inlineEditTarget = target;
                } else {
                    delete form.dataset.inlineEditTarget;
                }
            }

            panels.forEach(panel => {
                const isTarget = isInlineEditing && panel.dataset.inlineScope === target;
                panel.classList.toggle("is-inline-edit-target", isTarget);
            });

            refreshLockedTabs();

            if (!isInlineEditing) {
                const root = famigliaInlineRoot();
                const activeTab = root ? root.querySelector(".tab-btn.is-active") : null;
                if (activeTab && activeTab.dataset.tabTarget) {
                    updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
                }
            }
        }

        refreshInlineEditScopeHandler = refreshInlineEditScope;

        function updateInlineEditButtonLabel(tabId) {
            inlineTabs.updateDefaultInlineEditButtonLabel({
                buttonId: inlineEditButtonId,
                containerId: inlineLockContainerId,
                tabId: tabId,
                getViewMode: function () {
                    return window.famigliaViewMode;
                },
            });
        }

        function refreshLockedTabs() {
            inlineTabs.refreshTabButtonLocks({
                containerId: inlineLockContainerId,
                targetInputId: targetInputId,
                getViewMode: function () {
                    return window.famigliaViewMode;
                },
            });
            refreshStudentCardInteractionLocks();
            refreshCardPageInteractionLocks();
        }

        refreshLockedTabsHandler = refreshLockedTabs;

        function activateTab(tabId) {
            setInlineTarget(tabId);
            updateInlineEditButtonLabel(tabId);
            tabs.activateTab(tabId, getFamigliaTabStorageKey());
            syncActiveTabUrl(tabId);
            refreshInlineEditScope();
        }

        function restoreActiveTab() {
            const requestedTabId = config.preferInitialActiveTab
                ? normalizeTabId(config.initialActiveTab || defaultInlineTab)
                : "";
            const requestedPanel = requestedTabId ? document.getElementById(requestedTabId) : null;

            if (requestedPanel) {
                activateTab(requestedTabId);
                return;
            }

            tabs.restoreActiveTab(getFamigliaTabStorageKey());
            const root = famigliaInlineRoot();
            const activeTab = root ? root.querySelector(".tab-btn.is-active") : null;
            if (activeTab && activeTab.dataset.tabTarget) {
                setInlineTarget(activeTab.dataset.tabTarget);
                updateInlineEditButtonLabel(activeTab.dataset.tabTarget);
                syncActiveTabUrl(activeTab.dataset.tabTarget);
            }
            refreshInlineEditScope();
        }

        function syncNotesSectionState() {
            const notesSection = document.getElementById("family-notes-section");
            const notesPanel = document.getElementById("section-note");

            if (!notesSection || !notesPanel) {
                return;
            }

            notesSection.classList.toggle("is-expanded", notesPanel.classList.contains("is-open"));
        }

        function bindNotesSectionState() {
            const notesToggle = document.querySelector('#family-notes-section [data-target="section-note"]');
            if (!notesToggle || notesToggle.dataset.notesLayoutBound === "1") {
                syncNotesSectionState();
                return;
            }

            notesToggle.dataset.notesLayoutBound = "1";
            notesToggle.addEventListener("click", function () {
                window.requestAnimationFrame(syncNotesSectionState);
            });

            syncNotesSectionState();
        }

        function getCurrentInlineTabForNotes() {
            const activeTab = document.querySelector("#famiglia-inline-lock-container .tab-btn.is-active[data-tab-target]");
            const targetInput = document.getElementById("famiglia-inline-target");
            const rawValue = activeTab && activeTab.dataset.tabTarget
                ? activeTab.dataset.tabTarget
                : (targetInput ? targetInput.value : "");

            return (rawValue || "studenti").replace(/^tab-/, "");
        }

        function refreshFamilyNoteDialogEditor(overlay) {
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

        function setFamilyNoteDialogValue(textarea, value, overlay) {
            if (!textarea) {
                return;
            }

            textarea.value = value || "";
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
            refreshFamilyNoteDialogEditor(overlay);
        }

        function initFamilyNoteDialog() {
            const openButton = document.getElementById("family-note-edit-shortcut");
            const overlay = document.getElementById("family-note-dialog-overlay");
            const dialog = document.getElementById("family-note-popup-form");
            const textarea = document.getElementById("id_family_note_popup");
            const activeTabInput = document.getElementById("family-note-active-tab");

            if (!openButton || !overlay || !dialog || !textarea || overlay.dataset.familyNoteDialogBound === "1") {
                return;
            }

            overlay.dataset.familyNoteDialogBound = "1";
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
                    activeTabInput.value = getCurrentInlineTabForNotes();
                }

                setFamilyNoteDialogValue(textarea, initialValue, overlay);
                overlay.classList.remove("is-hidden");
                overlay.setAttribute("aria-hidden", "false");
                document.body.classList.add("app-dialog-open");
                window.setTimeout(focusEditor, 0);
            }

            function closeDialog() {
                setFamilyNoteDialogValue(textarea, initialValue, overlay);
                overlay.classList.add("is-hidden");
                overlay.setAttribute("aria-hidden", "true");
                document.body.classList.remove("app-dialog-open");
                openButton.focus();
            }

            openButton.addEventListener("click", function (event) {
                event.preventDefault();
                openDialog();
            });

            overlay.querySelectorAll("[data-family-note-dialog-cancel]").forEach(function (button) {
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
                    activeTabInput.value = getCurrentInlineTabForNotes();
                }
            });

            refreshFamilyNoteDialogEditor(overlay);
        }

        function readFamilySideCardOrder(storageKey) {
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

        function getFamilySideCards(container) {
            return Array.from(container.querySelectorAll("[data-family-side-card]"));
        }

        function saveFamilySideCardOrder(storageKey, container) {
            if (!storageKey) {
                return;
            }

            const orderedKeys = getFamilySideCards(container)
                .map((card) => card.dataset.familySideCardKey)
                .filter(Boolean);

            try {
                window.localStorage.setItem(storageKey, JSON.stringify(orderedKeys));
            } catch (error) {}
        }

        function applyFamilySideCardOrder(storageKey, container) {
            const orderedKeys = readFamilySideCardOrder(storageKey);
            if (!orderedKeys.length) {
                return;
            }

            const cardMap = new Map(
                getFamilySideCards(container).map((card) => [card.dataset.familySideCardKey, card])
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

        function syncFamilyViewSideHeight() {
            const form = document.getElementById("famiglia-detail-form");
            if (!form) {
                return;
            }

            const side = form.querySelector(".family-dashboard-side");
            const isStacked = window.matchMedia && window.matchMedia("(max-width: 980px)").matches;
            if (!side || !form.classList.contains("is-view-mode") || isStacked) {
                form.style.removeProperty("--family-side-height");
                return;
            }

            form.style.setProperty("--family-side-height", `${Math.ceil(side.getBoundingClientRect().height)}px`);
        }

        function initFamilyViewSideHeightSync() {
            const form = document.getElementById("famiglia-detail-form");
            const side = form ? form.querySelector(".family-dashboard-side") : null;
            if (!form || !side || form.dataset.familySideHeightSyncBound === "1") {
                return;
            }

            form.dataset.familySideHeightSyncBound = "1";
            let pendingFrame = null;
            const scheduleSync = function () {
                if (pendingFrame) {
                    window.cancelAnimationFrame(pendingFrame);
                }

                pendingFrame = window.requestAnimationFrame(function () {
                    pendingFrame = null;
                    syncFamilyViewSideHeight();
                });
            };

            if (window.ResizeObserver) {
                const observer = new ResizeObserver(scheduleSync);
                observer.observe(side);
            }

            window.addEventListener("resize", scheduleSync);
            scheduleSync();
        }

        function getFamilySideCollapseStorageKey(card) {
            const container = card.closest("[data-family-side-reorder], .family-dashboard-side");
            return (container && container.dataset.familySideCollapseKey) ||
                `arboris-family-side-card-collapsed-${config.famigliaId || "new"}`;
        }

        function readFamilySideCollapsedKeys(storageKey) {
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

        function saveFamilySideCollapsedKeys(storageKey) {
            if (!storageKey) {
                return;
            }

            const collapsedKeys = Array.from(document.querySelectorAll("[data-family-side-card].is-collapsed"))
                .map((card) => card.dataset.familySideCardKey)
                .filter(Boolean);

            try {
                window.localStorage.setItem(storageKey, JSON.stringify(collapsedKeys));
            } catch (error) {}
        }

        function getFamilySideCardTitle(card) {
            const title = card.querySelector(".family-side-card-head h2, h2");
            return title ? title.textContent.replace(/\s+/g, " ").trim() : "sidebar";
        }

        function setFamilySideCardCollapsed(card, collapsed) {
            const body = card.querySelector("[data-family-side-card-body]");
            const toggle = card.querySelector("[data-family-side-collapse-toggle]");
            const title = getFamilySideCardTitle(card);

            card.classList.toggle("is-collapsed", collapsed);

            if (body) {
                if (!body.id && card.dataset.familySideCardKey) {
                    body.id = `family-side-card-body-${card.dataset.familySideCardKey}`;
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

            syncFamilyViewSideHeight();
        }

        function initFamilySideCardCollapse() {
            const cards = Array.from(document.querySelectorAll("[data-family-side-card]"));
            const storageGroups = new Map();

            cards.forEach(function (card) {
                const storageKey = getFamilySideCollapseStorageKey(card);
                if (!storageGroups.has(storageKey)) {
                    storageGroups.set(storageKey, readFamilySideCollapsedKeys(storageKey));
                }

                const collapsedKeys = storageGroups.get(storageKey);
                const isCollapsed = collapsedKeys.includes(card.dataset.familySideCardKey || "");
                setFamilySideCardCollapsed(card, isCollapsed);

                const toggle = card.querySelector("[data-family-side-collapse-toggle]");
                if (!toggle || toggle.dataset.familySideCollapseBound === "1") {
                    return;
                }

                toggle.dataset.familySideCollapseBound = "1";
                toggle.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    setFamilySideCardCollapsed(card, !card.classList.contains("is-collapsed"));
                    saveFamilySideCollapsedKeys(storageKey);
                });
            });
        }

        function initFamilySideCardReorder() {
            document.querySelectorAll("[data-family-side-reorder]").forEach(function (container) {
                if (container.dataset.familySideReorderBound === "1") {
                    return;
                }

                container.dataset.familySideReorderBound = "1";
                const storageKey = container.dataset.familySideOrderKey || "arboris-family-side-card-order";
                let draggingCard = null;

                function clearDropState() {
                    container.querySelectorAll(".family-side-card.is-drop-target").forEach(function (card) {
                        card.classList.remove("is-drop-target");
                    });
                }

                function bindCard(card) {
                    if (card.dataset.familySideDragBound === "1") {
                        return;
                    }

                    card.dataset.familySideDragBound = "1";
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
                        saveFamilySideCardOrder(storageKey, container);
                    });
                }

                applyFamilySideCardOrder(storageKey, container);
                getFamilySideCards(container).forEach(bindCard);

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
                    saveFamilySideCardOrder(storageKey, container);
                });
            });
        }

        function initFamilyRateYearSwitch() {
            document.querySelectorAll(".family-rate-summary-card").forEach(function (card) {
                if (card.dataset.familyRateYearSwitchBound === "1") {
                    return;
                }

                card.dataset.familyRateYearSwitchBound = "1";

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

                    syncFamilyViewSideHeight();
                }

                card.querySelectorAll("[data-family-rate-year-tab]").forEach(function (button) {
                    button.addEventListener("click", function () {
                        activateYear(button.dataset.familyRateYearTab || "");
                    });
                });
            });
        }

        function getFamigliaIndirizzoPrincipaleLabel() {
            const select = document.getElementById("id_indirizzo_principale");

            if (select && select.value) {
                const selectedOption = select.options[select.selectedIndex];
                if (selectedOption) {
                    return selectedOption.textContent.trim();
                }
            }

            const node = document.getElementById("famiglia-indirizzo-principale-label");
            if (!node) return "";

            try {
                return JSON.parse(node.textContent);
            } catch (e) {
                return "";
            }
        }

        const famigliaInlineAddressConfig = {
            getFamilyAddressId: function () {
                return document.getElementById("id_indirizzo_principale")?.value || "";
            },
            getFamilyAddressLabel: getFamigliaIndirizzoPrincipaleLabel,
            emptyFamilyPrefix: "Ereditera: ",
        };

        const famigliaInlineAddressTrackingConfig = Object.assign({
            bindFlag: "inheritedTrackingBound",
        }, famigliaInlineAddressConfig);

        const familiariInlineDefaultsConfig = Object.assign({
            rowSelector: "#familiari-table tbody .inline-form-row",
            attivoSelector: 'input[type="checkbox"][name$="-attivo"]',
        }, famigliaInlineAddressConfig);

        const studentiInlineDefaultsConfig = Object.assign({
            rowSelector: "#studenti-table tbody .inline-form-row",
            surnameSelector: 'input[name$="-cognome"]',
            getFamilySurname: getFamigliaCognome,
            attivoSelector: 'input[type="checkbox"][name$="-attivo"]',
        }, famigliaInlineAddressConfig);

        function getFamigliaCognome() {
            return document.getElementById("id_cognome_famiglia")?.value?.trim() || "";
        }

        const famigliaInlineAddressCollection = familyLinkedAddress.createInlineAddressCollection(
            Object.assign({ selector: 'select[name$="-indirizzo"]' }, famigliaInlineAddressTrackingConfig)
        );
        const familiariInlineAddressDefaults = familyLinkedAddress.createInlineAddressCollection(familiariInlineDefaultsConfig);
        const studentiInlineAddressDefaults = familyLinkedAddress.createInlineAddressCollection(studentiInlineDefaultsConfig);

        function wireInlineRelatedButtons(container) {
            formTools.wireInlineRelatedButtons(container, {
                routes: entityRoutes,
                relatedPopups: relatedPopups,
                onRefresh(relatedType, select) {
                    if (relatedType === "indirizzo") {
                        famigliaInlineAddressCollection.refreshSelectHelp(select);
                    }
                },
            });
        }

        // Funzione per aggiornare i contatori nei titoli delle tab
        function countPersistedRows(tableId) {
            return inlineFormsets.countPersistedRows(tableId);
        }

        function refreshTabCounts() {
            const familiariRows = countPersistedRows("familiari-table");
            const studentiRows = countPersistedRows("studenti-table");
            const documentiRows = countPersistedRows("documenti-table");

            const tabFamiliari = document.querySelector('[data-tab-target="tab-familiari"]');
            const tabStudenti = document.querySelector('[data-tab-target="tab-studenti"]');
            const tabDocumenti = document.querySelector('[data-tab-target="tab-documenti"]');
            const relatedDocumentCount = tabDocumenti
                ? parseInt(tabDocumenti.dataset.relatedDocumentCount || "0", 10) || 0
                : 0;

            if (tabFamiliari) {
                tabFamiliari.textContent = `${inlineTabs.inlineLabelFromTabButton(tabFamiliari)} (${familiariRows})`;
            }
            if (tabStudenti) {
                tabStudenti.textContent = `${inlineTabs.inlineLabelFromTabButton(tabStudenti)} (${studentiRows})`;
            }
            if (tabDocumenti) {
                tabDocumenti.textContent = `${inlineTabs.inlineLabelFromTabButton(tabDocumenti)} (${documentiRows + relatedDocumentCount})`;
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

        function wireFamigliaInlineActionTriggers(root) {
            inlineFormsets.wireActionTriggers(root || document, {
                handlers: {
                    add: function (prefix, element) {
                        const activeContext = getActiveFamilyCardEditContext();
                        if (activeContext && !isAllowedDuringFamilyCardEdit(element, activeContext)) {
                            showFamilyCardLockMessage(element, activeContext.message);
                            return;
                        }
                        addManagedInlineForm(prefix);
                    },
                    "add-view": function (prefix, element) {
                        const activeContext = getActiveFamilyCardEditContext();
                        if (activeContext && !isAllowedDuringFamilyCardEdit(element, activeContext)) {
                            showFamilyCardLockMessage(element, activeContext.message);
                            return;
                        }
                        addInlineFormFromView(prefix);
                    },
                    remove: function (_prefix, element) {
                        const activeContext = getActiveFamilyCardEditContext();
                        if (activeContext && !isAllowedDuringFamilyCardEdit(element, activeContext)) {
                            showFamilyCardLockMessage(element, activeContext.message);
                            return;
                        }
                        removeManagedInlineRow(element);
                    },
                },
            });
        }

        function refreshFirstStudentAddMode() {
            const form = document.getElementById("famiglia-detail-form");
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

        function hideInlineState(state) {
            [state.row].concat(state.companionRows).forEach(function (node) {
                clearRowData(node);
                setRowInputsEnabled(node, false);
            });
        }

        const inlineManagers = {
            familiari: createInlineManager("familiari", {
                prepareOptions: {
                    companionClasses: ["inline-subform-row"],
                    includeCompanionRowsInData: true,
                    ignoreSelects: true,
                    onHide: hideInlineState,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
                    appendOnly: function () {
                        return countPersistedRows("studenti-table") > 0;
                    },
                    enableInputs: true,
                    onReady: function (state) {
                        const row = state.row;
                        const subformRow = state.companionRows[0] || getFamiliareSubformRow(row);
                        primeNewFamiliareRow(row);
                        formTools.initSearchableSelects(row);
                        if (subformRow) {
                            formTools.initSearchableSelects(subformRow);
                            formTools.initCodiceFiscale(subformRow);
                        }
                        famigliaInlineAddressCollection.bindTracking(row);
                        formTools.initCodiceFiscale(row);
                        wireInlineRelatedButtons(row);
                        bindFamiliareInlineSex(row);
                        bindFamiliareConviventeAddress(row);
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
                    onHide: hideInlineState,
                },
                mountOptions: {
                    companionClasses: ["inline-subform-row"],
                    appendOnly: true,
                    enableInputs: true,
                    onReady: function (state) {
                        const row = state.row;
                        const subformRow = state.companionRows[0] || getFamiliareSubformRow(row);
                        formTools.initSearchableSelects(row);
                        if (subformRow) {
                            formTools.initSearchableSelects(subformRow);
                            formTools.initCodiceFiscale(subformRow);
                        }
                        famigliaInlineAddressCollection.bindTracking(row);
                        formTools.initCodiceFiscale(row);
                        wireInlineRelatedButtons(row);
                        bindStudenteInlineSex(row);
                        bindStudenteInlineBirthDateOrdering(row);
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
                removeOptions: {
                    companionClasses: ["inline-subform-row"],
                },
            }),
            documenti: createInlineManager("documenti", {
                prepareOptions: {
                    onHide: hideInlineState,
                },
                mountOptions: {
                    enableInputs: true,
                    onReady: function (state) {
                        wireInlineRelatedButtons(state.row);
                    },
                    focusSelector: "input[type='text'], input[type='email'], input[type='date'], select, textarea",
                },
            }),
        };

        function removeManagedInlineRow(button) {
            const row = button && button.closest ? button.closest("tr") : null;
            const table = row ? row.closest("table") : null;
            const manager = table ? inlineManagers[table.id.replace("-table", "")] : null;
            const wasActiveCardRow = Boolean(row && row.classList.contains("is-inline-active-edit-row"));
            const removed = manager ? manager.remove(button) : null;

            if (removed) {
                refreshFirstStudentAddMode();
                refreshTabCounts();
                if (
                    wasActiveCardRow &&
                    !document.querySelector("#famiglia-inline-lock-container .is-inline-active-edit-row") &&
                    document.getElementById("famiglia-detail-form")?.classList.contains("is-inline-add-only-mode") &&
                    window.famigliaViewMode &&
                    typeof window.famigliaViewMode.setInlineEditing === "function"
                ) {
                    window.famigliaViewMode.setInlineEditing(false);
                }
                refreshCardPageInteractionLocks();
            }
        }

        function getFamilyGeneralFields() {
            return [
                document.getElementById("id_cognome_famiglia"),
                document.getElementById("id_stato_relazione_famiglia"),
                document.getElementById("id_indirizzo_principale"),
                document.getElementById("id_attiva"),
            ].filter(Boolean);
        }

        function snapshotFamilyGeneralFields() {
            return getFamilyGeneralFields().map(function (field) {
                return {
                    field: field,
                    value: field.value,
                    checked: field.checked,
                };
            });
        }

        function restoreFamilyGeneralFieldSnapshot(snapshot) {
            (snapshot || []).forEach(function (item) {
                if (!item || !item.field) {
                    return;
                }

                item.field.value = item.value;
                if ((item.field.type || "").toLowerCase() === "checkbox") {
                    item.field.checked = Boolean(item.checked);
                }
                item.field.dispatchEvent(new Event("change", { bubbles: true }));
            });
        }

        function rememberFamilyGeneralEditorNode(editor, node) {
            if (!editor || !node) {
                return;
            }

            if (!node.__familyGeneralRestore) {
                node.__familyGeneralRestore = {
                    parent: node.parentNode,
                    nextSibling: node.nextSibling,
                };
            }

            if (!editor.__familyGeneralMovedNodes) {
                editor.__familyGeneralMovedNodes = [];
            }
            if (!editor.__familyGeneralMovedNodes.includes(node)) {
                editor.__familyGeneralMovedNodes.push(node);
            }
        }

        function restoreFamilyGeneralEditorNodes(editor) {
            const movedNodes = editor && editor.__familyGeneralMovedNodes ? editor.__familyGeneralMovedNodes : [];

            movedNodes.forEach(function (node) {
                const restore = node.__familyGeneralRestore;
                if (!restore || !restore.parent) {
                    return;
                }

                if (restore.nextSibling && restore.nextSibling.parentNode === restore.parent) {
                    restore.parent.insertBefore(node, restore.nextSibling);
                } else {
                    restore.parent.appendChild(node);
                }
                delete node.__familyGeneralRestore;
            });

            if (editor) {
                editor.__familyGeneralMovedNodes = [];
            }
        }

        function setFamilyGeneralFieldsEnabled(editor, enabled) {
            if (!editor) {
                return;
            }

            const root = editor;
            root.querySelectorAll("input, textarea, select").forEach(function (field) {
                const type = (field.type || "").toLowerCase();

                if (enabled) {
                    field.disabled = false;
                    field.readOnly = false;
                    field.classList.remove("submit-safe-locked");
                    field.removeAttribute("aria-disabled");
                    field.removeAttribute("tabindex");
                    return;
                }

                if (type === "hidden") {
                    return;
                }
                if (field.tagName.toLowerCase() === "select" || type === "checkbox" || type === "radio" || type === "file") {
                    field.disabled = true;
                } else {
                    field.readOnly = true;
                }
            });

            formTools.initSearchableSelects(root);
        }

        function createFamilyGeneralEditorField(labelText, nodes, extraClass, editor) {
            const resolvedNodes = Array.isArray(nodes) ? nodes.filter(Boolean) : [nodes].filter(Boolean);
            if (!resolvedNodes.length) {
                return null;
            }

            const field = document.createElement("div");
            field.className = `family-general-editor-field${extraClass ? " " + extraClass : ""}`;

            const label = document.createElement("label");
            label.textContent = labelText;
            field.appendChild(label);

            const control = document.createElement("div");
            control.className = "family-general-editor-control";
            resolvedNodes.forEach(function (node) {
                rememberFamilyGeneralEditorNode(editor, node);
                control.appendChild(node);
            });
            field.appendChild(control);

            return field;
        }

        function enhanceFamilyGeneralRelatedControls(editor) {
            if (!editor) {
                return;
            }

            editor.querySelectorAll(".related-field-row").forEach(function (row) {
                row.classList.add("family-general-editor-related-control");
            });

            editor.querySelectorAll(".related-btn").forEach(function (button) {
                const isAdd = button.classList.contains("related-btn-add");
                const isEdit = button.classList.contains("related-btn-edit");
                const actionLabel = isAdd ? "Nuovo valore" : isEdit ? "Modifica valore" : "Elimina valore";
                const iconName = isAdd ? "plus" : isEdit ? "edit" : "trash";
                button.setAttribute("aria-label", actionLabel);
                button.setAttribute("title", actionLabel);
                button.dataset.floatingText = actionLabel;
                button.innerHTML = studentCardRelatedIconHtml(iconName);
            });
        }

        function markFamilyGeneralSubmitPending() {
            const form = document.getElementById("famiglia-detail-form");
            const modeInput = document.getElementById("famiglia-edit-scope");

            if (form) {
                form.dataset.pendingFamilyGeneralSubmit = "1";
            }
            if (modeInput) {
                modeInput.value = "full";
            }
        }

        function focusFamilyGeneralEditor(editor) {
            const field = editor ? editor.querySelector("input[type='text'], select, textarea") : null;
            if (field && typeof field.focus === "function") {
                field.focus();
            }
        }

        function buildFamilyGeneralEditor(card) {
            const content = card ? card.querySelector(".family-overview-content") : null;
            if (!card || !content) {
                return null;
            }

            const editor = document.createElement("div");
            editor.className = "family-general-card-editor";
            editor.__familyGeneralFieldSnapshot = snapshotFamilyGeneralFields();

            const head = document.createElement("div");
            head.className = "family-general-card-editor-head";
            const title = document.createElement("h3");
            title.textContent = "Modifica dati generali";
            head.appendChild(title);
            editor.appendChild(head);

            const grid = document.createElement("div");
            grid.className = "family-general-editor-grid";

            const cognomeInput = document.getElementById("id_cognome_famiglia");
            const statoSelect = document.getElementById("id_stato_relazione_famiglia");
            const indirizzoSelect = document.getElementById("id_indirizzo_principale");
            const attivaInput = document.getElementById("id_attiva");
            const cognomeNode = cognomeInput ? cognomeInput.closest(".mode-edit-field") || cognomeInput : null;
            const statoNode = statoSelect ? statoSelect.closest(".related-field-row") || statoSelect : null;
            const indirizzoNode = indirizzoSelect ? indirizzoSelect.closest(".related-field-row") || indirizzoSelect : null;
            const indirizzoHelp = indirizzoNode && indirizzoNode.parentElement
                ? indirizzoNode.parentElement.querySelector(".help-text.mode-edit-field")
                : null;

            [
                createFamilyGeneralEditorField("Cognome famiglia", cognomeNode, "family-general-editor-field-half", editor),
                createFamilyGeneralEditorField("Stato relazione", statoNode, "family-general-editor-field-half family-general-editor-field-related family-general-editor-field-state", editor),
                createFamilyGeneralEditorField("Indirizzo principale", [indirizzoNode, indirizzoHelp], "family-general-editor-field-wide family-general-editor-field-related family-general-editor-field-address", editor),
            ].forEach(function (field) {
                if (field) {
                    grid.appendChild(field);
                }
            });

            if (attivaInput) {
                rememberFamilyGeneralEditorNode(editor, attivaInput);
                const field = document.createElement("div");
                field.className = "family-general-editor-field family-general-editor-field-check";
                const checkLabel = document.createElement("label");
                checkLabel.className = "family-general-editor-check";
                checkLabel.appendChild(attivaInput);
                const text = document.createElement("span");
                text.textContent = "Famiglia attiva";
                checkLabel.appendChild(text);
                field.appendChild(checkLabel);
                grid.appendChild(field);
            }

            editor.appendChild(grid);

            const actions = document.createElement("div");
            actions.className = "family-general-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.name = "_save";
            saveButton.className = "btn btn-save-soft btn-sm btn-icon-text";
            saveButton.dataset.familyGeneralSubmit = "1";
            saveButton.innerHTML = studentCardIconHtml("check", "Salva");
            saveButton.addEventListener("click", markFamilyGeneralSubmitPending);

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.familyGeneralAction = "cancel";
            cancelButton.innerHTML = studentCardIconHtml("chevron-left", "Annulla");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            editor.appendChild(actions);

            card.appendChild(editor);
            card.classList.add("is-card-editing");
            card.dataset.familyGeneralEditing = "1";

            enhanceFamilyGeneralRelatedControls(editor);
            setFamilyGeneralFieldsEnabled(editor, true);
            wireInlineRelatedButtons(editor);
            wireFamilyGeneralCardActions(editor);
            updateMainRelatedButtons();
            refreshCardPageInteractionLocks();

            return editor;
        }

        function openFamilyGeneralEditor(trigger) {
            const card = getFamilyGeneralCard();
            if (!card) {
                return;
            }

            const existingEditor = card.querySelector(".family-general-card-editor");
            if (existingEditor) {
                focusFamilyGeneralEditor(existingEditor);
                return;
            }

            const context = getActiveFamilyCardEditContext();
            if (context && context.kind !== "family-general-card") {
                showFamilyCardLockMessage(trigger || card, context.message);
                return;
            }

            const editor = buildFamilyGeneralEditor(card);
            focusFamilyGeneralEditor(editor);
        }

        function closeFamilyGeneralEditor(options) {
            const cfg = options || {};
            const card = getActiveFamilyGeneralEditingCard();
            const editor = card ? card.querySelector(".family-general-card-editor") : null;

            if (!card || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreFamilyGeneralFieldSnapshot(editor.__familyGeneralFieldSnapshot);
            }

            restoreFamilyGeneralEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            delete card.dataset.familyGeneralEditing;
            setFamilyGeneralFieldsEnabled(document.getElementById("famiglia-lock-container"), false);
            refreshCardPageInteractionLocks();
        }

        function cancelFamilyGeneralEditor() {
            closeFamilyGeneralEditor({
                restoreValues: true,
            });
        }

        function wireFamilyGeneralCardActions(root) {
            const container = root || document;
            if (!container || typeof container.querySelectorAll !== "function") {
                return;
            }

            container.querySelectorAll("[data-family-general-action]").forEach(function (element) {
                if (element.dataset.familyGeneralActionBound === "1") {
                    return;
                }

                element.dataset.familyGeneralActionBound = "1";
                element.addEventListener("click", function (event) {
                    const action = element.dataset.familyGeneralAction || "";

                    event.preventDefault();
                    event.stopPropagation();

                    if (action === "edit") {
                        openFamilyGeneralEditor(element);
                    } else if (action === "cancel") {
                        cancelFamilyGeneralEditor();
                    }
                });
            });
        }

        function cancelActiveInlineCardEdit(context) {
            const row = getInlineRowFromContext(context);

            if (!row) {
                if (
                    window.famigliaViewMode &&
                    typeof window.famigliaViewMode.setInlineEditing === "function"
                ) {
                    window.famigliaViewMode.setInlineEditing(false);
                }
                refreshCardPageInteractionLocks();
                return;
            }

            if (inlineFormsets.isRowPersisted(row)) {
                reloadFamilyPage();
                return;
            }

            removeManagedInlineRow(row);
            if (
                !document.querySelector("#famiglia-inline-lock-container .is-inline-active-edit-row") &&
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.setInlineEditing === "function"
            ) {
                window.famigliaViewMode.setInlineEditing(false);
            }
            refreshInlineEditScope();
            refreshCardPageInteractionLocks();
        }

        function cancelActiveFamilyCardEdit() {
            const context = getActiveFamilyCardEditContext();

            if (!context) {
                refreshCardPageInteractionLocks();
                return;
            }

            if (context.kind === "family-general-card") {
                cancelFamilyGeneralEditor();
                return;
            }

            if (context.kind === "student-card") {
                cancelStudentCardEditor(null);
                return;
            }

            if (context.kind === "relative-card") {
                cancelRelativeCardEditor(null);
                return;
            }

            if (context.kind === "document-card") {
                cancelDocumentCardEditor(null);
                return;
            }

            if (context.kind === "inline-card") {
                cancelActiveInlineCardEdit(context);
            }
        }

        function getFamiliareSubformRow(row) {
            return inlineFormsets.getPrimaryCompanionRow(row, { companionClasses: ["inline-subform-row"] });
        }

        function clearRowData(row) {
            if (!row) {
                return;
            }

            row.querySelectorAll("input, textarea, select").forEach(field => {
                const type = (field.type || "").toLowerCase();
                const name = field.name || "";

                if (type === "hidden" && /-id$/.test(name)) {
                    return;
                }

                if (type === "hidden") {
                    field.value = "";
                    return;
                }

                if (type === "checkbox") {
                    field.checked = false;
                    return;
                }

                if (field.tagName.toLowerCase() === "select") {
                    field.value = "";
                    return;
                }

                field.value = "";
            });
        }

        function setRowInputsEnabled(row, isEnabled) {
            if (row) {
                inlineFormsets.setRowInputsEnabled(row, isEnabled, {
                    includeCompanionRows: false,
                    skipHiddenInputs: false,
                });
            }
        }

        function primeNewFamiliareRow(row) {
            const relazioneSelect = row.querySelector('select[name$="-relazione_familiare"]');
            if (!relazioneSelect || relazioneSelect.value) {
                return;
            }

            const firstOption = Array.from(relazioneSelect.options).find(option => option.value);
            if (firstOption) {
                relazioneSelect.value = firstOption.value;
            }
        }

        function isHiddenEmptyInlineRow(row) {
            return Boolean(
                row &&
                row.classList &&
                row.classList.contains("inline-empty-row") &&
                row.classList.contains("is-hidden")
            );
        }

        function isPersistedInlineRow(row) {
            const idInput = row ? row.querySelector('input[type="hidden"][name$="-id"]') : null;
            return Boolean(idInput && idInput.value);
        }

        function familiareAddressMatchesFamily(addressSelect) {
            const familyAddressId = document.getElementById("id_indirizzo_principale")?.value || "";
            if (!familyAddressId || !addressSelect) {
                return false;
            }

            const selectedAddressId = addressSelect.value || "";
            return !selectedAddressId || selectedAddressId === familyAddressId;
        }

        function syncFamiliareConviventeFromAddress(row) {
            if (!row || isHiddenEmptyInlineRow(row)) {
                return;
            }

            const addressSelect = row.querySelector('select[name$="-indirizzo"]');
            const conviventeCheckbox = row.querySelector('input[type="checkbox"][name$="-convivente"]');
            if (!addressSelect || !conviventeCheckbox || conviventeCheckbox.disabled) {
                return;
            }

            conviventeCheckbox.checked = familiareAddressMatchesFamily(addressSelect);
        }

        function bindFamiliareConviventeAddress(row) {
            if (!row || isHiddenEmptyInlineRow(row)) {
                return;
            }

            const addressSelect = row.querySelector('select[name$="-indirizzo"]');
            if (!addressSelect || addressSelect.dataset.conviventeAddressBound === "1") {
                return;
            }

            addressSelect.dataset.conviventeAddressBound = "1";
            addressSelect.addEventListener("change", function () {
                syncFamiliareConviventeFromAddress(row);
            });
        }

        function bindAllFamiliareConviventeAddress() {
            document.querySelectorAll("#familiari-table tbody .inline-form-row").forEach(bindFamiliareConviventeAddress);
        }

        function syncFamiliareConviventeRows(options) {
            const cfg = options || {};
            document.querySelectorAll("#familiari-table tbody .inline-form-row").forEach(function (row) {
                if (cfg.onlyNew && isPersistedInlineRow(row)) {
                    return;
                }
                syncFamiliareConviventeFromAddress(row);
            });
        }

        function bindFamiliareInlineSex(row) {
            const subformRow = getFamiliareSubformRow(row);
            const nameInput = row ? row.querySelector('input[name$="-nome"]') : null;
            const relationSelect = row ? row.querySelector('select[name$="-relazione_familiare"]') : null;
            const sexSelect = subformRow ? subformRow.querySelector('select[name$="-sesso"]') : null;

            if (!sexSelect) {
                return;
            }

            if (sexSelect.dataset.familiareInlineSexManualBound !== "1") {
                sexSelect.dataset.familiareInlineSexManualBound = "1";
                sexSelect.addEventListener("change", function () {
                    if (sexSelect.dataset.familiareInlineSexSyncing === "1") {
                        return;
                    }
                    sexSelect.dataset.familiareInlineSexManual = "1";
                    delete sexSelect.dataset.familiareInlineSexSource;
                });
            }

            function selectedRelationLabel() {
                if (!relationSelect) {
                    return "";
                }
                const option = relationSelect.options[relationSelect.selectedIndex];
                return option ? option.textContent : "";
            }

            function inferFromName() {
                return personRules.inferSexFromFirstName(nameInput ? nameInput.value : "");
            }

            function inferFromRelation() {
                return personRules.inferSexFromRelationLabel(selectedRelationLabel());
            }

            function setAutoSex(value, source, force) {
                if (!value || sexSelect.dataset.familiareInlineSexManual === "1") {
                    return false;
                }

                const currentValue = sexSelect.value || "";
                const currentSource = sexSelect.dataset.familiareInlineSexSource || "";
                const canOverwrite = force || !currentValue || currentSource === "relation" || currentSource === "name";

                if (currentValue && currentValue !== value && !canOverwrite) {
                    return false;
                }

                if (currentValue === value) {
                    sexSelect.dataset.familiareInlineSexSource = source;
                    return false;
                }

                sexSelect.dataset.familiareInlineSexSyncing = "1";
                sexSelect.value = value;
                sexSelect.dispatchEvent(new Event("change", { bubbles: true }));
                delete sexSelect.dataset.familiareInlineSexSyncing;
                sexSelect.dataset.familiareInlineSexSource = source;
                return true;
            }

            function syncFromName() {
                const currentSource = sexSelect.dataset.familiareInlineSexSource || "";
                return setAutoSex(
                    inferFromName(),
                    "name",
                    !sexSelect.value || currentSource === "relation" || currentSource === "name"
                );
            }

            function syncFromRelation() {
                if (inferFromName()) {
                    return syncFromName();
                }
                return setAutoSex(inferFromRelation(), "relation", false);
            }

            if (nameInput && nameInput.dataset.familiareInlineSexNameBound !== "1") {
                nameInput.dataset.familiareInlineSexNameBound = "1";
                ["input", "change"].forEach(function (eventName) {
                    nameInput.addEventListener(eventName, syncFromName);
                });
            }

            if (relationSelect && relationSelect.dataset.familiareInlineSexRelationBound !== "1") {
                relationSelect.dataset.familiareInlineSexRelationBound = "1";
                relationSelect.addEventListener("change", syncFromRelation);
            }

            if (!syncFromName()) {
                syncFromRelation();
            }
        }

        function bindAllFamiliareInlineSex() {
            document.querySelectorAll("#familiari-table tbody .inline-form-row").forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }
                bindFamiliareInlineSex(row);
            });
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

        function parseInlineDateValue(value) {
            if (!value) {
                return null;
            }

            const parsed = new Date(`${value}T00:00:00`);
            if (Number.isNaN(parsed.getTime())) {
                return null;
            }

            return parsed;
        }

        function getStudentRowBundle(row) {
            return inlineFormsets.getRowBundle(row, { companionClasses: ["inline-subform-row"] }).bundle;
        }

        function compareStudentRowsByAge(leftRow, rightRow) {
            const leftDateValue = getFamiliareSubformRow(leftRow)?.querySelector('input[name$="-data_nascita"]')?.value || "";
            const rightDateValue = getFamiliareSubformRow(rightRow)?.querySelector('input[name$="-data_nascita"]')?.value || "";
            const leftDate = parseInlineDateValue(leftDateValue);
            const rightDate = parseInlineDateValue(rightDateValue);

            if (leftDate && rightDate) {
                const dateDiff = leftDate.getTime() - rightDate.getTime();
                if (dateDiff !== 0) {
                    return dateDiff;
                }
            } else if (leftDate) {
                return -1;
            } else if (rightDate) {
                return 1;
            }

            const leftCognome = (leftRow.querySelector('input[name$="-cognome"]')?.value || "").trim().toLowerCase();
            const rightCognome = (rightRow.querySelector('input[name$="-cognome"]')?.value || "").trim().toLowerCase();
            if (leftCognome !== rightCognome) {
                return leftCognome.localeCompare(rightCognome, "it");
            }

            const leftNome = (leftRow.querySelector('input[name$="-nome"]')?.value || "").trim().toLowerCase();
            const rightNome = (rightRow.querySelector('input[name$="-nome"]')?.value || "").trim().toLowerCase();
            return leftNome.localeCompare(rightNome, "it");
        }

        function sortStudentiInlineRows() {
            const tbody = document.querySelector("#studenti-table tbody");
            if (!tbody) {
                return;
            }

            const bundles = [];
            let currentRow = tbody.firstElementChild;

            while (currentRow) {
                if (!currentRow.classList.contains("inline-form-row")) {
                    currentRow = currentRow.nextElementSibling;
                    continue;
                }

                const bundle = getStudentRowBundle(currentRow);
                bundles.push(bundle);
                currentRow = bundle[bundle.length - 1].nextElementSibling;
            }

            const visibleBundles = [];
            const hiddenBundles = [];

            bundles.forEach(bundle => {
                const mainRow = bundle[0];
                if (mainRow.classList.contains("inline-empty-row") && mainRow.classList.contains("is-hidden")) {
                    hiddenBundles.push(bundle);
                    return;
                }
                visibleBundles.push(bundle);
            });

            visibleBundles.sort((leftBundle, rightBundle) => compareStudentRowsByAge(leftBundle[0], rightBundle[0]));

            [...visibleBundles, ...hiddenBundles].forEach(bundle => {
                bundle.forEach(node => tbody.appendChild(node));
            });
        }

        function bindStudenteInlineBirthDateOrdering(row) {
            const dataNascitaInput = getFamiliareSubformRow(row)?.querySelector('input[name$="-data_nascita"]');
            if (!dataNascitaInput || dataNascitaInput.dataset.orderingBound === "1") {
                return;
            }

            dataNascitaInput.dataset.orderingBound = "1";
            dataNascitaInput.addEventListener("change", sortStudentiInlineRows);
            dataNascitaInput.addEventListener("input", sortStudentiInlineRows);
        }

        function bindAllStudenteInlineBirthDateOrdering() {
            document.querySelectorAll("#studenti-table tbody .inline-form-row").forEach(row => {
                if (row.classList.contains("inline-empty-row") && row.classList.contains("is-hidden")) {
                    return;
                }
                bindStudenteInlineBirthDateOrdering(row);
            });
        }

        function addManagedInlineForm(prefix) {
            const manager = inlineManagers[prefix];
            if (!manager) {
                return null;
            }
            const isFirstStudentAdd = prefix === "studenti" && countPersistedRows("studenti-table") === 0;

            const mounted = manager.add();

            if (!mounted) {
                return null;
            }

            const tabId = `tab-${prefix}`;
            activateTab(tabId);
            refreshTabCounts();
            if (mounted.state && mounted.state.bundle) {
                mounted.state.bundle.forEach(function (node) {
                    wireFamigliaInlineActionTriggers(node);
                });
            }
            if (prefix === "familiari") {
                familiariInlineAddressDefaults.syncRows();
                bindAllFamiliareConviventeAddress();
                if (mounted.state && mounted.state.row) {
                    syncFamiliareConviventeFromAddress(mounted.state.row);
                }
            } else if (prefix === "studenti") {
                markFirstStudentAddRows(mounted, isFirstStudentAdd && mounted.revealed);
                studentiInlineAddressDefaults.syncRows();
                sortStudentiInlineRows();
            }
            famigliaInlineAddressCollection.refreshCollectionHelp(document.getElementById("famiglia-inline-lock-container"));
            refreshCardPageInteractionLocks();

            return mounted;
        }

        function addInlineFormFromView(prefix) {
            const form = document.getElementById("famiglia-detail-form");
            const isAlreadyAddOnlyMode = Boolean(form && form.classList.contains("is-inline-add-only-mode"));
            const shouldUseAddOnlyMode = Boolean(
                window.famigliaViewMode &&
                (!window.famigliaViewMode.isEditing() || isAlreadyAddOnlyMode)
            );

            if (window.famigliaViewMode && !window.famigliaViewMode.isEditing()) {
                window.famigliaViewMode.setInlineEditing(true);
            }

            const mounted = addManagedInlineForm(prefix);

            if (shouldUseAddOnlyMode && mounted && mounted.state) {
                inlineFormsets.markBundleForAddOnlyEdit(mounted.state, {
                    form: "famiglia-detail-form",
                });
                refreshFirstStudentAddMode();
                refreshCardPageInteractionLocks();
            }
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

        function getActiveStudentEditingCard() {
            return document.querySelector("[data-student-card].is-card-editing");
        }

        function getActiveRelativeEditingCard() {
            return document.querySelector("[data-relative-card].is-card-editing");
        }

        function getActiveDocumentEditingCard() {
            return document.querySelector("[data-document-card].is-card-editing");
        }

        function isStudentCardEditing() {
            return Boolean(getActiveStudentEditingCard());
        }

        function isAnyInlineVisualCardEditing() {
            return Boolean(
                getActiveStudentEditingCard() ||
                getActiveRelativeEditingCard() ||
                getActiveDocumentEditingCard()
            );
        }

        function isCreateModeForm() {
            const form = document.getElementById("famiglia-detail-form");
            return Boolean(form && form.classList.contains("is-create-mode"));
        }

        function enterCreateInlineCardMode(target) {
            if (!isCreateModeForm()) {
                return;
            }

            const targetInput = document.getElementById("famiglia-inline-target");
            if (targetInput && target) {
                targetInput.value = target;
            }

            if (
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.setInlineEditing === "function" &&
                !window.famigliaViewMode.isInlineEditing()
            ) {
                window.famigliaViewMode.setInlineEditing(true);
            }
        }

        function restoreCreateFullEditModeIfIdle() {
            if (!isCreateModeForm() || isAnyInlineVisualCardEditing()) {
                return;
            }

            if (
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.setEditing === "function" &&
                window.famigliaViewMode.isInlineEditing()
            ) {
                window.famigliaViewMode.setEditing(true);
            }
        }

        function setFamilyCardLockElement(element, locked, message, flagName) {
            if (!element) {
                return;
            }

            const flag = flagName || "familyPageCardLock";
            if (locked) {
                if (element.dataset.cardLockOriginalTitleStored !== "1") {
                    element.dataset.cardLockOriginalTitleStored = "1";
                    element.dataset.cardLockOriginalTitle = element.getAttribute("title") || "";
                }
                element.classList.add("family-card-action-locked");
                element.dataset[flag] = "1";
                element.dataset.cardLockMessage = message || familyCardPageLockMessage;
                element.setAttribute("title", message || familyCardPageLockMessage);
                return;
            }

            if (element.dataset[flag] === "1") {
                delete element.dataset[flag];
            }

            if (element.dataset.studentCardLock === "1" || element.dataset.familyPageCardLock === "1") {
                return;
            }

            if (element.classList.contains("family-card-action-locked")) {
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
        }

        function setStudentCardLockElement(element, locked) {
            setFamilyCardLockElement(element, locked, studentCardLockMessage, "studentCardLock");
        }

        function showFamilyCardLockMessage(element, message) {
            const target = element && element.closest
                ? element.closest("button, a, .tab-btn, .family-person-card, .family-document-card, [data-row-href]") || element
                : element;

            if (!target) {
                return;
            }

            setFamilyCardLockElement(target, true, message || familyCardPageLockMessage, "familyPageCardLock");
            target.classList.remove("is-showing-lock");
            void target.offsetWidth;
            target.classList.add("is-showing-lock");

            window.clearTimeout(target.__studentCardLockTimer);
            target.__studentCardLockTimer = window.setTimeout(function () {
                target.classList.remove("is-showing-lock");
            }, 2200);
        }

        function showStudentCardLockMessage(element) {
            showFamilyCardLockMessage(element, studentCardLockMessage);
        }

        function getFamilyCardPageLockScope() {
            return document.querySelector(".content-area") || document.body || document;
        }

        function getActiveInlineTarget() {
            const targetInput = document.getElementById(targetInputId);
            return (targetInput ? targetInput.value : "").replace(/^tab-/, "");
        }

        function getActiveInlinePanel() {
            const target = getActiveInlineTarget();
            return target ? document.getElementById(`tab-${target}`) : null;
        }

        function getFamilyGeneralCard() {
            return document.querySelector("[data-family-general-card]");
        }

        function getActiveFamilyGeneralEditingCard() {
            return document.querySelector("[data-family-general-card].is-card-editing");
        }

        function isFamilyGeneralCardEditing() {
            return Boolean(getActiveFamilyGeneralEditingCard());
        }

        function reloadFamilyPage() {
            if (typeof window.ArborisReloadWithLongWait === "function") {
                window.ArborisReloadWithLongWait();
                return;
            }

            window.location.reload();
        }

        function getInlineRowFromContext(context) {
            const roots = context && context.roots ? context.roots : [];
            let resolvedRow = null;

            roots.some(function (root) {
                if (!root) {
                    return false;
                }

                if (root.matches && root.matches("tr.inline-form-row")) {
                    resolvedRow = root;
                    return true;
                }

                if (root.closest) {
                    const closestRow = root.closest("tr.inline-form-row");
                    if (closestRow) {
                        resolvedRow = closestRow;
                        return true;
                    }
                }

                if (root.querySelector) {
                    const nestedRow = root.querySelector("tr.inline-form-row");
                    if (nestedRow) {
                        resolvedRow = nestedRow;
                        return true;
                    }
                }

                return false;
            });

            return resolvedRow;
        }

        function getFamilyCardStickyElements() {
            const menu = document.getElementById(cardStickyActionsId);
            return {
                menu: menu,
                spacer: document.getElementById(cardStickySpacerId),
                title: menu ? menu.querySelector("[data-family-card-sticky-title]") : null,
                saveButton: document.getElementById("family-card-sticky-save"),
                cancelButton: document.getElementById("family-card-sticky-cancel"),
            };
        }

        function getFamilyCardStickyTitle(context) {
            if (!context) {
                return "Modifica card";
            }

            if (context.kind === "student-card") {
                const card = context.roots && context.roots[0];
                const title = card ? card.querySelector(".family-student-card-editor-head h3") : null;
                return title && title.textContent.trim() ? title.textContent.trim() : "Modifica studente";
            }

            if (context.kind === "relative-card") {
                const card = context.roots && context.roots[0];
                const title = card ? card.querySelector(".family-student-card-editor-head h3") : null;
                return title && title.textContent.trim() ? title.textContent.trim() : "Modifica familiare";
            }

            if (context.kind === "document-card") {
                const card = context.roots && context.roots[0];
                const title = card ? card.querySelector(".family-student-card-editor-head h3") : null;
                return title && title.textContent.trim() ? title.textContent.trim() : "Modifica documento";
            }

            if (context.kind === "family-general-card") {
                return "Modifica dati generali";
            }

            const row = getInlineRowFromContext(context);
            const isPersisted = inlineFormsets.isRowPersisted(row);
            const labels = {
                familiari: {
                    add: "Nuovo familiare",
                    edit: "Modifica familiare",
                },
                studenti: {
                    add: "Nuovo studente",
                    edit: "Modifica studente",
                },
                documenti: {
                    add: "Nuovo documento",
                    edit: "Modifica documento",
                },
            };
            const targetLabels = labels[context.target] || {
                add: "Nuova card",
                edit: "Modifica card",
            };

            return isPersisted ? targetLabels.edit : targetLabels.add;
        }

        function shouldShowFamilyCardStickyActions(context) {
            return Boolean(context && (
                context.kind === "family-general-card" ||
                context.kind === "student-card" ||
                context.kind === "relative-card" ||
                context.kind === "document-card" ||
                context.kind === "inline-card"
            ));
        }

        function getActiveFamilyCardEditContext() {
            const activeFamilyGeneralCard = getActiveFamilyGeneralEditingCard();
            if (activeFamilyGeneralCard) {
                return {
                    kind: "family-general-card",
                    target: "famiglia",
                    roots: [activeFamilyGeneralCard],
                    message: familyCardPageLockMessage,
                };
            }

            const activeStudentCard = getActiveStudentEditingCard();
            if (activeStudentCard) {
                return {
                    kind: "student-card",
                    target: "studenti",
                    roots: [activeStudentCard],
                    message: familyCardPageLockMessage,
                };
            }

            const activeRelativeCard = getActiveRelativeEditingCard();
            if (activeRelativeCard) {
                return {
                    kind: "relative-card",
                    target: "familiari",
                    roots: [activeRelativeCard],
                    message: familyCardPageLockMessage,
                };
            }

            const activeDocumentCard = getActiveDocumentEditingCard();
            if (activeDocumentCard) {
                return {
                    kind: "document-card",
                    target: "documenti",
                    roots: [activeDocumentCard],
                    message: familyCardPageLockMessage,
                };
            }

            const isInlineEditing = Boolean(
                window.famigliaViewMode &&
                typeof window.famigliaViewMode.isInlineEditing === "function" &&
                window.famigliaViewMode.isInlineEditing()
            );

            if (!isInlineEditing) {
                return null;
            }

            const activePanel = getActiveInlinePanel();
            const activeRows = activePanel
                ? Array.from(activePanel.querySelectorAll(".is-inline-active-edit-row"))
                : [];

            return {
                kind: activeRows.length ? "inline-card" : "inline-tab",
                target: getActiveInlineTarget(),
                roots: activeRows.length ? activeRows : [activePanel].filter(Boolean),
                message: familyCardPageLockMessage,
            };
        }

        function syncFamilyCardStickyActions(context) {
            const elements = getFamilyCardStickyElements();
            const form = document.getElementById("famiglia-detail-form");
            const shouldShow = shouldShowFamilyCardStickyActions(context);

            if (!elements.menu) {
                return;
            }

            elements.menu.hidden = !shouldShow;
            elements.menu.classList.toggle("is-hidden", !shouldShow);
            if (elements.spacer) {
                elements.spacer.hidden = !shouldShow;
                elements.spacer.classList.toggle("is-hidden", !shouldShow);
            }
            if (form) {
                form.classList.toggle("has-family-card-sticky-actions", shouldShow);
            }

            if (!shouldShow) {
                if (elements.saveButton) {
                    delete elements.saveButton.dataset.studentCardSubmit;
                    delete elements.saveButton.dataset.familyCardStickyTarget;
                    delete elements.saveButton.dataset.familyGeneralSubmit;
                    delete elements.saveButton.dataset.cardInlineSubmit;
                }
                return;
            }

            if (elements.title) {
                elements.title.textContent = getFamilyCardStickyTitle(context);
            }

            if (elements.saveButton) {
                elements.saveButton.dataset.familyCardStickyTarget = context.target || "";
                if (context.kind === "student-card") {
                    elements.saveButton.dataset.studentCardSubmit = "studenti";
                } else {
                    delete elements.saveButton.dataset.studentCardSubmit;
                }
                if (context.kind === "family-general-card") {
                    elements.saveButton.dataset.familyGeneralSubmit = "1";
                } else {
                    delete elements.saveButton.dataset.familyGeneralSubmit;
                }
                if (context.kind === "relative-card" || context.kind === "document-card" || context.kind === "inline-card") {
                    elements.saveButton.dataset.cardInlineSubmit = context.target || "";
                } else {
                    delete elements.saveButton.dataset.cardInlineSubmit;
                }
            }
        }

        function isElementInsideAnyRoot(element, roots) {
            return Boolean(element && roots && roots.some(function (root) {
                return root && (root === element || root.contains(element));
            }));
        }

        function getElementLabel(element) {
            if (!element) {
                return "";
            }

            const label = element.querySelector && element.querySelector("[data-btn-label], .btn-label");
            return (label ? label.textContent : element.textContent || element.getAttribute("aria-label") || element.title || "")
                .replace(/\s+/g, " ")
                .trim();
        }

        function isFamilyFormSubmitControl(element) {
            if (!element || !element.matches || !element.matches("button, input")) {
                return false;
            }

            const type = (element.getAttribute("type") || (element.tagName.toLowerCase() === "button" ? "submit" : "")).toLowerCase();
            if (type !== "submit") {
                return false;
            }

            const targetFormId = element.getAttribute("form") || (element.form ? element.form.id : "");
            return targetFormId === "famiglia-detail-form";
        }

        function isSaveControl(element) {
            return isFamilyFormSubmitControl(element) && /\bsalva\b/i.test(getElementLabel(element));
        }

        function isCancelControl(element, context) {
            if (!element || !element.matches) {
                return false;
            }

            if (element.id === "sticky-cancel-edit-famiglia-btn") {
                return true;
            }

            if (element.dataset.familyCardStickyCancel === "1") {
                return true;
            }

            if (
                element.id === inlineEditButtonId &&
                context &&
                (context.kind === "inline-card" || context.kind === "inline-tab")
            ) {
                return true;
            }

            return false;
        }

        function isCurrentInlineTabButton(element, context) {
            if (!element || !context || !element.matches || !element.matches(".tab-btn[data-tab-target]")) {
                return false;
            }

            return (element.dataset.tabTarget || "").replace(/^tab-/, "") === context.target;
        }

        function isAllowedDuringFamilyCardEdit(element, context) {
            if (!element || !context) {
                return true;
            }

            if (isElementInsideAnyRoot(element, context.roots)) {
                return true;
            }

            if (isSaveControl(element) || isCancelControl(element, context) || isCurrentInlineTabButton(element, context)) {
                return true;
            }

            return false;
        }

        function resolveFamilyCardPageLockTrigger(target) {
            return target && target.closest
                ? target.closest("a[href], button, input[type='submit'], input[type='button'], [role='button'], summary, .tab-btn, [data-row-href]")
                : null;
        }

        function refreshCardPageInteractionLocks() {
            const context = getActiveFamilyCardEditContext();
            const scope = getFamilyCardPageLockScope();

            syncFamilyCardStickyActions(context);

            scope.querySelectorAll(".family-card-action-locked[data-family-page-card-lock='1']").forEach(function (element) {
                setFamilyCardLockElement(element, false, "", "familyPageCardLock");
            });

            if (!context) {
                return;
            }

            scope.querySelectorAll("a[href], button, input[type='submit'], input[type='button'], [role='button'], summary, .tab-btn, [data-row-href]").forEach(function (element) {
                if (isAllowedDuringFamilyCardEdit(element, context)) {
                    return;
                }

                setFamilyCardLockElement(element, true, context.message, "familyPageCardLock");
            });
        }

        function bindFamilyCardPageInteractionLock() {
            const scope = getFamilyCardPageLockScope();
            if (!scope || (scope.dataset && scope.dataset.familyCardPageLockBound === "1")) {
                return;
            }

            if (scope.dataset) {
                scope.dataset.familyCardPageLockBound = "1";
            }

            scope.addEventListener("click", function (event) {
                const context = getActiveFamilyCardEditContext();
                const trigger = resolveFamilyCardPageLockTrigger(event.target);

                if (!context || !trigger || isAllowedDuringFamilyCardEdit(trigger, context)) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                showFamilyCardLockMessage(trigger, context.message);
            }, true);

            scope.addEventListener("keydown", function (event) {
                if (event.key !== "Enter" && event.key !== " ") {
                    return;
                }

                const context = getActiveFamilyCardEditContext();
                const trigger = resolveFamilyCardPageLockTrigger(event.target);

                if (!context || !trigger || isAllowedDuringFamilyCardEdit(trigger, context)) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                showFamilyCardLockMessage(trigger, context.message);
            }, true);
        }

        function bindFamilyCardStickyActions() {
            const elements = getFamilyCardStickyElements();

            if (elements.saveButton && elements.saveButton.dataset.familyCardStickySaveBound !== "1") {
                elements.saveButton.dataset.familyCardStickySaveBound = "1";
                elements.saveButton.addEventListener("click", function () {
                    const context = getActiveFamilyCardEditContext();
                    const modeInput = document.getElementById("famiglia-edit-scope");
                    const targetInput = document.getElementById("famiglia-inline-target");

                    if (!context) {
                        return;
                    }

                    if (context.kind === "student-card") {
                        markStudentCardSubmitPending();
                    }

                    if (context.kind === "family-general-card") {
                        markFamilyGeneralSubmitPending();
                        if (modeInput) {
                            modeInput.value = "full";
                        }
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

            if (elements.cancelButton && elements.cancelButton.dataset.familyCardStickyCancelBound !== "1") {
                elements.cancelButton.dataset.familyCardStickyCancelBound = "1";
                elements.cancelButton.addEventListener("click", function (event) {
                    event.preventDefault();
                    cancelActiveFamilyCardEdit();
                });
            }
        }

        function refreshStudentCardInteractionLocks() {
            const activeCard = getActiveStudentEditingCard();
            const list = getStudentCardList();
            const locked = Boolean(activeCard);
            const inlineRoot = famigliaInlineRoot();

            if (inlineRoot) {
                inlineRoot.querySelectorAll(".tab-btn[data-tab-target]").forEach(function (button) {
                    const isStudentTab = (button.dataset.tabTarget || "").replace(/^tab-/, "") === "studenti";
                    if (locked && !isStudentTab) {
                        button.classList.add("is-tab-locked");
                        button.dataset.tabLockMessage = studentCardLockMessage;
                        button.setAttribute("title", studentCardLockMessage);
                        button.dataset.studentCardTabLock = "1";
                    } else if (button.dataset.studentCardTabLock === "1") {
                        button.classList.remove("is-tab-locked");
                        button.removeAttribute("data-tab-lock-message");
                        button.removeAttribute("title");
                        delete button.dataset.studentCardTabLock;
                    }
                });
            }

            document.querySelectorAll('[data-student-card-action="add"]').forEach(function (button) {
                setStudentCardLockElement(button, locked);
            });

            if (!list) {
                return;
            }

            list.classList.toggle("has-student-card-editing", locked);
            list.querySelectorAll("[data-student-card]").forEach(function (card) {
                const isCurrentCard = card === activeCard;
                const lockCard = locked && !isCurrentCard;

                card.classList.toggle("is-student-card-locked", lockCard);
                card.querySelectorAll('[data-student-card-action], .family-person-avatar, .family-person-actions a').forEach(function (element) {
                    setStudentCardLockElement(element, lockCard);
                });
            });

            refreshCardPageInteractionLocks();
        }

        function bindStudentCardNavigationLock() {
            const list = getStudentCardList();
            if (!list || list.dataset.studentCardNavigationLockBound === "1") {
                return;
            }

            list.dataset.studentCardNavigationLockBound = "1";
            list.addEventListener("click", function (event) {
                const activeCard = getActiveStudentEditingCard();
                if (!activeCard) {
                    return;
                }

                const trigger = event.target.closest("a, button");
                const card = trigger ? trigger.closest("[data-student-card]") : null;

                if (!trigger || !card || card === activeCard) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                showStudentCardLockMessage(trigger);
            }, true);
        }

        function bindStudentCardTabNavigationLock() {
            const root = famigliaInlineRoot();
            if (!root || root.dataset.studentCardTabLockBound === "1") {
                return;
            }

            root.dataset.studentCardTabLockBound = "1";
            root.addEventListener("arboris:before-tab-activate", function (event) {
                if (!isStudentCardEditing()) {
                    return;
                }

                const nextTarget = ((event.detail && event.detail.tabId) || "").replace(/^tab-/, "");
                if (!nextTarget || nextTarget === "studenti") {
                    return;
                }

                event.preventDefault();
                if (event.detail && event.detail.button) {
                    showStudentCardLockMessage(event.detail.button);
                    event.detail.button.classList.add("is-tab-locked");
                    event.detail.button.dataset.tabLockMessage = studentCardLockMessage;
                    event.detail.button.setAttribute("title", studentCardLockMessage);
                }
            });
        }

        function getStudentPrefixFromRow(row) {
            const idInput = row ? row.querySelector('input[type="hidden"][name$="-id"]') : null;
            const name = idInput ? idInput.name || "" : "";
            return name.endsWith("-id") ? name.slice(0, -3) : "";
        }

        function getStudentRowFromCard(card) {
            const prefix = card ? card.dataset.studentFormPrefix || "" : "";
            if (!prefix) {
                return null;
            }

            const idInput = document.getElementById(`id_${prefix}-id`);
            return idInput ? idInput.closest("tr.inline-form-row") : null;
        }

        function syncStudentCardEmptyState() {
            const list = getStudentCardList();
            if (!list) {
                return;
            }

            const emptyState = list.querySelector(".family-card-empty");
            if (emptyState) {
                emptyState.hidden = Boolean(list.querySelector("[data-student-card]"));
            }
        }

        function createStudentCardAvatar(list) {
            const sprite = list ? list.dataset.avatarSprite || "" : "";
            const avatar = document.createElement("div");
            avatar.className = "family-person-avatar family-person-avatar-student";
            avatar.setAttribute("aria-hidden", "true");

            const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            svg.setAttribute("viewBox", "0 0 96 96");
            svg.setAttribute("focusable", "false");

            const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
            use.setAttribute("href", `${sprite}#avatar-child`);
            svg.appendChild(use);
            avatar.appendChild(svg);

            return avatar;
        }

        function studentCardIconHtml(symbolName, label) {
            const list = getStudentCardList();
            const sprite = list ? list.dataset.uiIconsSprite || "" : "";
            return `<span class="btn-icon" aria-hidden="true"><svg><use href="${sprite}#${symbolName}"></use></svg></span><span>${label}</span>`;
        }

        function studentCardRelatedIconHtml(symbolName) {
            const list = getStudentCardList();
            const sprite = list ? list.dataset.uiIconsSprite || "" : "";
            return `<span class="related-btn-icon" aria-hidden="true"><svg><use href="${sprite}#${symbolName}"></use></svg></span>`;
        }

        function rememberStudentEditorNode(editor, node) {
            if (!editor || !node) {
                return;
            }

            if (!node.__studentCardRestore) {
                node.__studentCardRestore = {
                    parent: node.parentNode,
                    nextSibling: node.nextSibling,
                    className: node.className,
                };
            }

            if (!editor.__studentCardMovedNodes) {
                editor.__studentCardMovedNodes = [];
            }
            if (!editor.__studentCardMovedNodes.includes(node)) {
                editor.__studentCardMovedNodes.push(node);
            }
        }

        function restoreStudentEditorNodes(editor) {
            const movedNodes = editor && editor.__studentCardMovedNodes ? editor.__studentCardMovedNodes : [];

            movedNodes.slice().reverse().forEach(function (node) {
                const restore = node.__studentCardRestore;
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
                delete node.__studentCardRestore;
            });

            if (editor) {
                editor.__studentCardMovedNodes = [];
            }
        }

        function snapshotStudentCardFields(row) {
            const subformRow = getFamiliareSubformRow(row);
            const rows = [row, subformRow].filter(Boolean);

            return rows.flatMap(function (currentRow) {
                return Array.from(currentRow.querySelectorAll("input, select, textarea")).map(function (field) {
                    const type = (field.type || "").toLowerCase();
                    return {
                        field: field,
                        checked: type === "checkbox" || type === "radio" ? field.checked : null,
                        value: field.value,
                    };
                });
            });
        }

        function restoreStudentCardFieldSnapshot(snapshot) {
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

        function createStudentEditorField(labelText, contentNode, extraClass, editor) {
            if (!contentNode) {
                return null;
            }

            const field = document.createElement("div");
            field.className = `family-student-editor-field${extraClass ? " " + extraClass : ""}`;
            rememberStudentEditorNode(editor, contentNode);

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

        function appendStudentInputField(grid, row, selector, labelText, extraClass, editor) {
            const input = row ? row.querySelector(selector) : null;
            const content = input ? input.closest(".mode-edit-field") || input : null;
            const field = createStudentEditorField(labelText, content, extraClass, editor);

            if (field) {
                grid.appendChild(field);
            }
        }

        function appendStudentSubformField(grid, subformRow, selector, extraClass, editor) {
            const input = subformRow ? subformRow.querySelector(selector) : null;
            const field = input ? input.closest(".inline-subform-field") : null;

            if (!field) {
                return;
            }

            rememberStudentEditorNode(editor, field);
            field.classList.add("family-student-editor-field");
            if (extraClass) {
                field.classList.add(extraClass);
            }
            grid.appendChild(field);
        }

        function appendStudentAddressField(grid, row, editor) {
            const addressCell = row ? row.querySelector(".inline-studente-address-cell") : null;
            const relatedField = addressCell ? addressCell.querySelector(".inline-related-field") : null;

            if (!relatedField) {
                return;
            }

            const field = createStudentEditorField("Indirizzo", relatedField, "family-student-editor-field-wide", editor);
            const help = addressCell.querySelector('[data-role="address-help"]');
            field.classList.add("family-student-editor-address-field");
            relatedField.classList.add("family-card-editor-related-control", "family-student-editor-address-control");
            relatedField.querySelectorAll(".related-btn").forEach(function (button) {
                const isAdd = button.classList.contains("related-btn-add");
                const isEdit = button.classList.contains("related-btn-edit");
                const actionLabel = isAdd ? "Nuovo indirizzo" : isEdit ? "Modifica indirizzo" : "Elimina indirizzo";
                const iconName = isAdd ? "plus" : isEdit ? "edit" : "trash";
                button.setAttribute("aria-label", actionLabel);
                button.setAttribute("title", actionLabel);
                button.dataset.floatingText = actionLabel;
                button.innerHTML = studentCardRelatedIconHtml(iconName);
            });

            if (help) {
                rememberStudentEditorNode(editor, help);
                field.appendChild(help);
            }

            grid.appendChild(field);
        }

        function appendStudentActiveField(grid, row, editor) {
            const activeInput = row ? row.querySelector('input[type="checkbox"][name$="-attivo"]') : null;
            if (!activeInput) {
                return;
            }

            rememberStudentEditorNode(editor, activeInput);
            const field = document.createElement("div");
            field.className = "family-student-editor-field family-student-editor-field-check";

            const label = document.createElement("label");
            label.className = "family-student-editor-check";
            label.appendChild(activeInput);
            const text = document.createElement("span");
            text.textContent = "Attivo";
            label.appendChild(text);

            field.appendChild(label);
            grid.appendChild(field);
        }

        function setStudentCardFieldsEnabled(editor) {
            if (!editor) {
                return;
            }

            editor.querySelectorAll("input, textarea, select").forEach(function (field) {
                field.disabled = false;
                field.readOnly = false;
                field.classList.remove("submit-safe-locked");
                field.removeAttribute("aria-disabled");
                field.removeAttribute("tabindex");
            });
        }

        function markStudentCardSubmitPending() {
            const form = document.getElementById("famiglia-detail-form");
            if (form) {
                form.dataset.pendingStudentCardSubmit = "1";
            }
        }

        function focusStudentCardEditor(editor) {
            const field = editor ? editor.querySelector("input[type='text'], input[type='date'], select, textarea") : null;
            if (field && typeof field.focus === "function") {
                field.focus();
            }
        }

        function buildStudentCardEditor(card, row, options) {
            const cfg = options || {};
            const subformRow = getFamiliareSubformRow(row);
            const snapshot = snapshotStudentCardFields(row);

            inlineFormsets.setRowInputsEnabled(row, true, {
                includeCompanionRows: true,
                companionClasses: ["inline-subform-row"],
                skipHiddenInputs: false,
            });

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor";

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";

            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica studente";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            editor.__studentCardFieldSnapshot = snapshot;
            appendStudentInputField(grid, row, 'input[name$="-nome"]', "Nome", "family-student-editor-field-half", editor);
            appendStudentInputField(grid, row, 'input[name$="-cognome"]', "Cognome", "family-student-editor-field-half", editor);
            appendStudentSubformField(grid, subformRow, 'select[name$="-sesso"]', "family-student-editor-field-third", editor);
            appendStudentSubformField(grid, subformRow, 'input[name$="-data_nascita"]', "family-student-editor-field-third", editor);
            appendStudentSubformField(grid, subformRow, 'input[name$="-luogo_nascita_search"]', "family-student-editor-field-wide", editor);
            appendStudentSubformField(grid, subformRow, 'select[name$="-nazionalita"]', "family-student-editor-field-third", editor);
            appendStudentSubformField(grid, subformRow, 'input[name$="-codice_fiscale"]', "family-student-editor-field-third", editor);
            appendStudentAddressField(grid, row, editor);
            appendStudentActiveField(grid, row, editor);

            editor.appendChild(grid);

            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.className = "btn btn-primary btn-sm btn-icon-text";
            saveButton.dataset.studentCardSubmit = "studenti";
            saveButton.innerHTML = studentCardIconHtml("check", "Salva");
            saveButton.addEventListener("click", markStudentCardSubmitPending);

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.studentCardAction = "cancel";
            cancelButton.innerHTML = studentCardIconHtml("chevron-left", "Annulla modifiche");

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "btn btn-secondary btn-sm btn-icon-text family-student-card-remove";
            removeButton.dataset.studentCardAction = "remove";
            removeButton.innerHTML = studentCardIconHtml("trash", "Rimuovi");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            actions.appendChild(removeButton);
            editor.appendChild(actions);

            card.appendChild(editor);
            card.classList.add("is-card-editing");
            card.dataset.studentCardEditing = "1";
            refreshStudentCardInteractionLocks();

            formTools.initSearchableSelects(editor);
            formTools.initCodiceFiscale(editor);
            wireInlineRelatedButtons(editor);
            setStudentCardFieldsEnabled(editor);
            wireStudentCardActions(editor);

            return editor;
        }

        function openStudentCardEditor(card, options) {
            if (!card) {
                return;
            }

            const existingEditor = card.querySelector(".family-student-card-editor");
            if (existingEditor) {
                focusStudentCardEditor(existingEditor);
                return;
            }

            const row = getStudentRowFromCard(card);
            if (!row) {
                return;
            }

            const titleNode = card.querySelector(".family-person-heading h3");
            const title = titleNode ? `Modifica ${titleNode.textContent.trim()}` : "Modifica studente";
            const editor = buildStudentCardEditor(card, row, Object.assign({ title: title }, options || {}));
            focusStudentCardEditor(editor);
        }

        function addStudentCardFromView(trigger) {
            const form = document.getElementById("famiglia-detail-form");
            if (
                form &&
                !form.classList.contains("is-view-mode") &&
                (!form.classList.contains("is-create-mode") || form.classList.contains("has-form-errors"))
            ) {
                addInlineFormFromView("studenti");
                return;
            }

            const list = getStudentCardList();
            if (!list) {
                return;
            }

            enterCreateInlineCardMode("studenti");
            const mounted = addManagedInlineForm("studenti");
            const row = mounted && mounted.state ? mounted.state.row : null;
            const prefix = getStudentPrefixFromRow(row);

            if (!row || !prefix) {
                return;
            }

            const card = document.createElement("article");
            card.className = "family-person-card family-student-card family-student-card-new is-card-editing";
            card.dataset.studentCard = "1";
            card.dataset.studentFormPrefix = prefix;
            card.appendChild(createStudentCardAvatar(list));

            const addButton = list.querySelector(".family-dashed-add");
            list.insertBefore(card, addButton || null);

            const title = list.dataset.studentNewTitle || `Nuovo ${list.dataset.studentSingular || "studente"}`;
            const editor = buildStudentCardEditor(card, row, {
                title: title,
                isNew: true,
            });

            wireStudentCardActions(card);
            syncStudentCardEmptyState();
            refreshStudentCardInteractionLocks();
            focusStudentCardEditor(editor);

            if (trigger && typeof card.scrollIntoView === "function") {
                card.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        }

        function closeStudentCardEditor(card, row, options) {
            const cfg = options || {};
            const editor = card ? card.querySelector(".family-student-card-editor") : null;
            if (!card || !row || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreStudentCardFieldSnapshot(editor.__studentCardFieldSnapshot);
            }

            restoreStudentEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            delete card.dataset.studentCardEditing;

            inlineFormsets.setRowInputsEnabled(row, false, {
                includeCompanionRows: true,
                companionClasses: ["inline-subform-row"],
                skipHiddenInputs: false,
            });
            refreshStudentCardInteractionLocks();
        }

        function cancelStudentCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-student-card]") : getActiveStudentEditingCard();
            const row = getStudentRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const isPersisted = inlineFormsets.isRowPersisted(row);

            if (!isPersisted) {
                inlineManagers.studenti.remove(row);
                card.remove();
                refreshTabCounts();
                syncStudentCardEmptyState();
                refreshStudentCardInteractionLocks();
                restoreCreateFullEditModeIfIdle();
                return;
            }

            closeStudentCardEditor(card, row, {
                restoreValues: true,
            });
        }

        function removeStudentCardEditor(button) {
            const card = button ? button.closest("[data-student-card]") : null;
            const row = getStudentRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            const isPersisted = inlineFormsets.isRowPersisted(row);
            const nameNode = card.querySelector(".family-person-heading h3, .family-student-card-editor-head h3");
            const studentName = nameNode ? nameNode.textContent.trim().replace(/^Modifica\s+/, "") : "questo studente";
            const message = isPersisted
                ? `Confermi la rimozione di ${studentName}?`
                : `Confermi l'annullamento dell'inserimento di ${studentName}?`;

            if (!window.confirm(message)) {
                return;
            }

            if (!isPersisted) {
                inlineManagers.studenti.remove(row);
                card.remove();
                refreshTabCounts();
                syncStudentCardEmptyState();
                refreshStudentCardInteractionLocks();
                restoreCreateFullEditModeIfIdle();
                return;
            }

            if (deleteInput) {
                deleteInput.disabled = false;
                deleteInput.checked = true;
            }

            const saveButton = card.querySelector('[data-student-card-submit="studenti"]');
            if (saveButton && typeof saveButton.click === "function") {
                saveButton.formNoValidate = true;
                saveButton.setAttribute("formnovalidate", "formnovalidate");
                saveButton.click();
            }
        }

        function wireStudentCardActions(root) {
            const container = root || document;
            if (!container || typeof container.querySelectorAll !== "function") {
                return;
            }

            container.querySelectorAll("[data-student-card-action]").forEach(function (element) {
                if (element.dataset.studentCardActionBound === "1") {
                    return;
                }

                element.dataset.studentCardActionBound = "1";
                element.addEventListener("click", function (event) {
                    const action = element.dataset.studentCardAction || "";

                    event.preventDefault();
                    event.stopPropagation();

                    const activeCard = getActiveStudentEditingCard();
                    const actionCard = element.closest("[data-student-card]");
                    const isCurrentCardAction = Boolean(activeCard && actionCard === activeCard);
                    if (
                        activeCard &&
                        (
                            action === "add" ||
                            (actionCard && !isCurrentCardAction) ||
                            (!actionCard && action !== "cancel")
                        )
                    ) {
                        showStudentCardLockMessage(element);
                        return;
                    }

                    if (action === "add") {
                        addStudentCardFromView(element);
                    } else if (action === "edit") {
                        openStudentCardEditor(element.closest("[data-student-card]"));
                    } else if (action === "cancel") {
                        cancelStudentCardEditor(element);
                    } else if (action === "remove") {
                        removeStudentCardEditor(element);
                    }
                });
            });
        }

        function getInlinePrefixFromRow(row) {
            const idInput = row ? row.querySelector('input[type="hidden"][name$="-id"]') : null;
            const name = idInput ? idInput.name || "" : "";
            return name.endsWith("-id") ? name.slice(0, -3) : "";
        }

        function getRelativeRowFromCard(card) {
            const prefix = card ? card.dataset.relativeFormPrefix || "" : "";
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

        function getFamilyCardUiIconsSprite() {
            const holder = getStudentCardList() || getRelativeCardList() || getDocumentCardList();
            return holder ? holder.dataset.uiIconsSprite || "" : "";
        }

        function familyCardIconHtml(symbolName, label) {
            const sprite = getFamilyCardUiIconsSprite();
            return `<span class="btn-icon" aria-hidden="true"><svg><use href="${sprite}#${symbolName}"></use></svg></span><span>${label}</span>`;
        }

        function familyCardRelatedIconHtml(symbolName) {
            const sprite = getFamilyCardUiIconsSprite();
            return `<span class="related-btn-icon" aria-hidden="true"><svg><use href="${sprite}#${symbolName}"></use></svg></span>`;
        }

        function decorateCardRelatedButtons(root, label) {
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
                button.innerHTML = familyCardRelatedIconHtml(iconName);
            });
        }

        function appendCardInputField(grid, row, selector, labelText, extraClass, editor) {
            appendStudentInputField(grid, row, selector, labelText, extraClass, editor);
        }

        function appendCardRelatedField(grid, row, selector, labelText, extraClass, editor, relatedLabel) {
            const input = row ? row.querySelector(selector) : null;
            const relatedField = input ? input.closest(".inline-related-field") : null;
            appendStudentInputField(grid, row, selector, labelText, extraClass, editor);
            if (relatedField) {
                relatedField.classList.add("family-card-editor-related-control");
            }
            decorateCardRelatedButtons(relatedField, relatedLabel || labelText.toLowerCase());
        }

        function appendCardCheckboxField(grid, row, selector, labelText, extraClass, editor) {
            const input = row ? row.querySelector(selector) : null;
            if (!input) {
                return;
            }

            rememberStudentEditorNode(editor, input);
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

        function appendRelativeAddressField(grid, row, editor) {
            const addressCell = row
                ? row.querySelector(".inline-family-address-cell") || row.querySelector(".inline-family-editor-address")
                : null;
            const relatedField = addressCell ? addressCell.querySelector(".inline-related-field") : null;

            if (!relatedField) {
                return;
            }

            const field = createStudentEditorField("Indirizzo", relatedField, "family-student-editor-field-wide", editor);
            const help = addressCell.querySelector('[data-role="address-help"]');
            field.classList.add("family-student-editor-address-field");
            relatedField.classList.add("family-card-editor-related-control", "family-student-editor-address-control");
            decorateCardRelatedButtons(relatedField, "indirizzo");

            if (help) {
                rememberStudentEditorNode(editor, help);
                field.appendChild(help);
            }

            grid.appendChild(field);
        }

        function createRelativeCardAvatar(list) {
            const sprite = list ? list.dataset.avatarSprite || "" : "";
            const avatar = document.createElement("div");
            avatar.className = "family-person-avatar family-person-avatar-relative";
            avatar.setAttribute("aria-hidden", "true");

            const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            svg.setAttribute("viewBox", "0 0 96 96");
            svg.setAttribute("focusable", "false");

            const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
            use.setAttribute("href", `${sprite}#avatar-woman`);
            svg.appendChild(use);
            avatar.appendChild(svg);

            return avatar;
        }

        function createDocumentCardIcon(list) {
            const sprite = list ? list.dataset.uiIconsSprite || getFamilyCardUiIconsSprite() : getFamilyCardUiIconsSprite();
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

        function syncDocumentCardEmptyState() {
            const list = getDocumentCardList();
            if (!list) {
                return;
            }

            const emptyState = list.querySelector(".family-card-empty");
            if (emptyState) {
                emptyState.hidden = Boolean(list.querySelector(".family-document-card"));
            }
        }

        function buildRelativeCardEditor(card, row, options) {
            const cfg = options || {};
            const subformRow = getFamiliareSubformRow(row);
            const snapshot = snapshotStudentCardFields(row);

            inlineFormsets.setRowInputsEnabled(row, true, {
                includeCompanionRows: true,
                companionClasses: ["inline-subform-row"],
                skipHiddenInputs: false,
            });

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor family-relative-card-editor";

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";

            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica familiare";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            editor.__studentCardFieldSnapshot = snapshot;
            appendCardInputField(grid, row, 'input[name$="-nome"]', "Nome", "family-student-editor-field-half", editor);
            appendCardInputField(grid, row, 'input[name$="-cognome"]', "Cognome", "family-student-editor-field-half", editor);
            appendCardRelatedField(grid, row, 'select[name$="-relazione_familiare"]', "Parentela", "family-student-editor-field-third", editor, "parentela");
            appendCardInputField(grid, row, 'input[name$="-telefono"]', "Telefono", "family-student-editor-field-third", editor);
            appendCardInputField(grid, row, 'input[name$="-email"]', "Email", "family-student-editor-field-third", editor);
            appendStudentSubformField(grid, subformRow, 'select[name$="-sesso"]', "family-student-editor-field-third", editor);
            appendStudentSubformField(grid, subformRow, 'input[name$="-data_nascita"]', "family-student-editor-field-third", editor);
            appendStudentSubformField(grid, subformRow, 'input[name$="-luogo_nascita_search"]', "family-student-editor-field-wide", editor);
            appendStudentSubformField(grid, subformRow, 'select[name$="-nazionalita"]', "family-student-editor-field-third", editor);
            appendStudentSubformField(grid, subformRow, 'input[name$="-codice_fiscale"]', "family-student-editor-field-third", editor);
            appendRelativeAddressField(grid, row, editor);
            appendCardCheckboxField(grid, row, 'input[type="checkbox"][name$="-convivente"]', "Convivente", "", editor);
            appendCardCheckboxField(grid, row, 'input[type="checkbox"][name$="-referente_principale"]', "Referente principale", "", editor);
            appendCardCheckboxField(grid, row, 'input[type="checkbox"][name$="-abilitato_scambio_retta"]', "Scambio retta", "", editor);
            appendCardCheckboxField(grid, row, 'input[type="checkbox"][name$="-attivo"]', "Attivo", "", editor);

            editor.appendChild(grid);

            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.className = "btn btn-primary btn-sm btn-icon-text";
            saveButton.dataset.cardInlineSubmit = "familiari";
            saveButton.innerHTML = familyCardIconHtml("check", "Salva");

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.relativeCardAction = "cancel";
            cancelButton.innerHTML = familyCardIconHtml("chevron-left", "Annulla modifiche");

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "btn btn-secondary btn-sm btn-icon-text family-student-card-remove";
            removeButton.dataset.relativeCardAction = "remove";
            removeButton.innerHTML = familyCardIconHtml("trash", "Rimuovi");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            actions.appendChild(removeButton);
            editor.appendChild(actions);

            card.appendChild(editor);
            card.classList.add("is-card-editing");
            card.dataset.relativeCardEditing = "1";

            formTools.initSearchableSelects(editor);
            formTools.initCodiceFiscale(editor);
            wireInlineRelatedButtons(editor);
            setStudentCardFieldsEnabled(editor);
            wireRelativeCardActions(editor);
            refreshCardPageInteractionLocks();

            return editor;
        }

        function openRelativeCardEditor(card, options) {
            if (!card) {
                return;
            }

            const existingEditor = card.querySelector(".family-relative-card-editor");
            if (existingEditor) {
                focusStudentCardEditor(existingEditor);
                return;
            }

            const row = getRelativeRowFromCard(card);
            if (!row) {
                return;
            }

            const titleNode = card.querySelector(".family-person-heading h3");
            const title = titleNode ? `Modifica ${titleNode.textContent.trim()}` : "Modifica familiare";
            const editor = buildRelativeCardEditor(card, row, Object.assign({ title: title }, options || {}));
            focusStudentCardEditor(editor);
        }

        function addRelativeCardFromView(trigger) {
            const form = document.getElementById("famiglia-detail-form");
            if (
                form &&
                !form.classList.contains("is-view-mode") &&
                (!form.classList.contains("is-create-mode") || form.classList.contains("has-form-errors"))
            ) {
                addInlineFormFromView("familiari");
                return;
            }

            const list = getRelativeCardList();
            if (!list) {
                return;
            }

            enterCreateInlineCardMode("familiari");
            const mounted = addManagedInlineForm("familiari");
            const row = mounted && mounted.state ? mounted.state.row : null;
            const prefix = getInlinePrefixFromRow(row);

            if (!row || !prefix) {
                return;
            }

            const card = document.createElement("article");
            card.className = "family-person-card family-relative-card family-relative-card-new is-card-editing";
            card.dataset.relativeCard = "1";
            card.dataset.relativeFormPrefix = prefix;
            card.appendChild(createRelativeCardAvatar(list));

            const addButton = list.querySelector(".family-dashed-add");
            list.insertBefore(card, addButton || null);

            const editor = buildRelativeCardEditor(card, row, {
                title: "Nuovo familiare",
                isNew: true,
            });

            wireRelativeCardActions(card);
            syncRelativeCardEmptyState();
            refreshCardPageInteractionLocks();
            focusStudentCardEditor(editor);

            if (trigger && typeof card.scrollIntoView === "function") {
                card.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        }

        function closeRelativeCardEditor(card, row, options) {
            const cfg = options || {};
            const editor = card ? card.querySelector(".family-relative-card-editor") : null;
            if (!card || !row || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreStudentCardFieldSnapshot(editor.__studentCardFieldSnapshot);
            }

            restoreStudentEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            delete card.dataset.relativeCardEditing;

            inlineFormsets.setRowInputsEnabled(row, false, {
                includeCompanionRows: true,
                companionClasses: ["inline-subform-row"],
                skipHiddenInputs: false,
            });
            refreshCardPageInteractionLocks();
        }

        function cancelRelativeCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-relative-card]") : getActiveRelativeEditingCard();
            const row = getRelativeRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const isPersisted = inlineFormsets.isRowPersisted(row);

            if (!isPersisted) {
                inlineManagers.familiari.remove(row);
                card.remove();
                refreshTabCounts();
                syncRelativeCardEmptyState();
                refreshCardPageInteractionLocks();
                restoreCreateFullEditModeIfIdle();
                return;
            }

            closeRelativeCardEditor(card, row, {
                restoreValues: true,
            });
        }

        function removeRelativeCardEditor(button) {
            const card = button ? button.closest("[data-relative-card]") : null;
            const row = getRelativeRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            const isPersisted = inlineFormsets.isRowPersisted(row);
            const nameNode = card.querySelector(".family-person-heading h3, .family-student-card-editor-head h3");
            const relativeName = nameNode ? nameNode.textContent.trim().replace(/^Modifica\s+/, "") : "questo familiare";
            const message = isPersisted
                ? `Confermi la rimozione di ${relativeName}?`
                : `Confermi l'annullamento dell'inserimento di ${relativeName}?`;
            const secondMessage = isPersisted
                ? `Seconda conferma: ${relativeName} verra eliminato al salvataggio. Vuoi continuare?`
                : `Seconda conferma: la nuova card di ${relativeName} verra rimossa. Vuoi continuare?`;

            if (!window.confirm(message)) {
                return;
            }
            if (!window.confirm(secondMessage)) {
                return;
            }

            if (!isPersisted) {
                inlineManagers.familiari.remove(row);
                card.remove();
                refreshTabCounts();
                syncRelativeCardEmptyState();
                refreshCardPageInteractionLocks();
                restoreCreateFullEditModeIfIdle();
                return;
            }

            if (deleteInput) {
                deleteInput.disabled = false;
                deleteInput.checked = true;
            }

            const saveButton = card.querySelector('[data-card-inline-submit="familiari"]');
            if (saveButton && typeof saveButton.click === "function") {
                saveButton.formNoValidate = true;
                saveButton.setAttribute("formnovalidate", "formnovalidate");
                saveButton.click();
            }
        }

        function buildDocumentCardEditor(card, row, options) {
            const cfg = options || {};
            const snapshot = snapshotStudentCardFields(row);

            inlineFormsets.setRowInputsEnabled(row, true, {
                skipHiddenInputs: false,
            });

            const editor = document.createElement("div");
            editor.className = "family-student-card-editor family-document-card-editor";

            const heading = document.createElement("div");
            heading.className = "family-student-card-editor-head";

            const title = document.createElement("h3");
            title.textContent = cfg.title || "Modifica documento";
            heading.appendChild(title);
            editor.appendChild(heading);

            const grid = document.createElement("div");
            grid.className = "family-student-editor-grid";

            editor.__studentCardFieldSnapshot = snapshot;
            appendCardRelatedField(grid, row, 'select[name$="-tipo_documento"]', "Tipo documento", "family-student-editor-field-half", editor, "tipo documento");
            appendCardInputField(grid, row, 'textarea[name$="-descrizione"]', "Descrizione", "family-student-editor-field-wide", editor);
            appendCardInputField(grid, row, 'input[type="file"][name$="-file"]', "File", "family-student-editor-field-wide", editor);
            appendCardInputField(grid, row, 'input[name$="-scadenza"]', "Scadenza", "family-student-editor-field-third", editor);
            appendCardCheckboxField(grid, row, 'input[type="checkbox"][name$="-visibile"]', "Visibile", "", editor);
            appendCardInputField(grid, row, 'textarea[name$="-note"]', "Note", "family-student-editor-field-wide", editor);

            editor.appendChild(grid);

            const actions = document.createElement("div");
            actions.className = "family-student-card-editor-actions";

            const saveButton = document.createElement("button");
            saveButton.type = "submit";
            saveButton.className = "btn btn-primary btn-sm btn-icon-text";
            saveButton.dataset.cardInlineSubmit = "documenti";
            saveButton.innerHTML = familyCardIconHtml("check", "Salva");

            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary btn-sm btn-icon-text";
            cancelButton.dataset.documentCardAction = "cancel";
            cancelButton.innerHTML = familyCardIconHtml("chevron-left", "Annulla modifiche");

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "btn btn-secondary btn-sm btn-icon-text family-student-card-remove";
            removeButton.dataset.documentCardAction = "remove";
            removeButton.innerHTML = familyCardIconHtml("trash", "Rimuovi");

            actions.appendChild(saveButton);
            actions.appendChild(cancelButton);
            actions.appendChild(removeButton);
            editor.appendChild(actions);

            card.appendChild(editor);
            card.classList.add("is-card-editing");
            card.dataset.documentCardEditing = "1";

            formTools.initSearchableSelects(editor);
            wireInlineRelatedButtons(editor);
            setStudentCardFieldsEnabled(editor);
            wireDocumentCardActions(editor);
            refreshCardPageInteractionLocks();

            return editor;
        }

        function openDocumentCardEditor(card, options) {
            if (!card) {
                return;
            }

            const existingEditor = card.querySelector(".family-document-card-editor");
            if (existingEditor) {
                focusStudentCardEditor(existingEditor);
                return;
            }

            const row = getDocumentRowFromCard(card);
            if (!row) {
                return;
            }

            const titleNode = card.querySelector(".family-document-main h3");
            const title = titleNode ? `Modifica ${titleNode.textContent.trim()}` : "Modifica documento";
            const editor = buildDocumentCardEditor(card, row, Object.assign({ title: title }, options || {}));
            focusStudentCardEditor(editor);
        }

        function addDocumentCardFromView(trigger) {
            const form = document.getElementById("famiglia-detail-form");
            if (
                form &&
                !form.classList.contains("is-view-mode") &&
                (!form.classList.contains("is-create-mode") || form.classList.contains("has-form-errors"))
            ) {
                addInlineFormFromView("documenti");
                return;
            }

            const list = getDocumentCardList();
            if (!list) {
                return;
            }

            enterCreateInlineCardMode("documenti");
            const mounted = addManagedInlineForm("documenti");
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

            const editor = buildDocumentCardEditor(card, row, {
                title: "Nuovo documento",
                isNew: true,
            });

            wireDocumentCardActions(card);
            syncDocumentCardEmptyState();
            refreshCardPageInteractionLocks();
            focusStudentCardEditor(editor);

            if (trigger && typeof card.scrollIntoView === "function") {
                card.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        }

        function closeDocumentCardEditor(card, row, options) {
            const cfg = options || {};
            const editor = card ? card.querySelector(".family-document-card-editor") : null;
            if (!card || !row || !editor) {
                return;
            }

            if (cfg.restoreValues) {
                restoreStudentCardFieldSnapshot(editor.__studentCardFieldSnapshot);
            }

            restoreStudentEditorNodes(editor);
            editor.remove();
            card.classList.remove("is-card-editing");
            delete card.dataset.documentCardEditing;

            inlineFormsets.setRowInputsEnabled(row, false, {
                skipHiddenInputs: false,
            });
            refreshCardPageInteractionLocks();
        }

        function cancelDocumentCardEditor(button) {
            const card = button && button.closest ? button.closest("[data-document-card]") : getActiveDocumentEditingCard();
            const row = getDocumentRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const isPersisted = inlineFormsets.isRowPersisted(row);

            if (!isPersisted) {
                inlineManagers.documenti.remove(row);
                card.remove();
                refreshTabCounts();
                syncDocumentCardEmptyState();
                refreshCardPageInteractionLocks();
                restoreCreateFullEditModeIfIdle();
                return;
            }

            closeDocumentCardEditor(card, row, {
                restoreValues: true,
            });
        }

        function removeDocumentCardEditor(button) {
            const card = button ? button.closest("[data-document-card]") : null;
            const row = getDocumentRowFromCard(card);
            if (!card || !row) {
                return;
            }

            const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            const isPersisted = inlineFormsets.isRowPersisted(row);
            const nameNode = card.querySelector(".family-document-main h3, .family-student-card-editor-head h3");
            const documentName = nameNode ? nameNode.textContent.trim().replace(/^Modifica\s+/, "") : "questo documento";
            const message = isPersisted
                ? `Confermi la rimozione di ${documentName}?`
                : `Confermi l'annullamento dell'inserimento di ${documentName}?`;

            if (!window.confirm(message)) {
                return;
            }

            if (!isPersisted) {
                inlineManagers.documenti.remove(row);
                card.remove();
                refreshTabCounts();
                syncDocumentCardEmptyState();
                refreshCardPageInteractionLocks();
                restoreCreateFullEditModeIfIdle();
                return;
            }

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
            if (!button) {
                return;
            }

            const popupUrl = button.dataset.popupUrl || "";
            const card = button.closest(".family-document-card");
            const titleNode = card ? card.querySelector(".family-document-main h3") : null;
            const label = (button.dataset.documentDeleteLabel || (titleNode ? titleNode.textContent : "") || "questo documento")
                .replace(/\s+/g, " ")
                .trim();

            if (!popupUrl) {
                return;
            }

            const message = `Vuoi eliminare ${label}? Si aprira un popup di conferma prima della cancellazione definitiva.`;
            if (!window.confirm(message)) {
                return;
            }

            if (typeof openRelatedPopup === "function") {
                openRelatedPopup(popupUrl);
                return;
            }

            window.location.href = popupUrl;
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
                    const action = element.dataset.relativeCardAction || "";
                    const activeContext = getActiveFamilyCardEditContext();

                    event.preventDefault();
                    event.stopPropagation();

                    if (activeContext && !isAllowedDuringFamilyCardEdit(element, activeContext)) {
                        showFamilyCardLockMessage(element, activeContext.message);
                        return;
                    }

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

        function wireDocumentCardActions(root) {
            const container = root || document;
            if (!container || typeof container.querySelectorAll !== "function") {
                return;
            }

            container.querySelectorAll("[data-document-card-action]").forEach(function (element) {
                if (element.dataset.documentCardActionBound === "1") {
                    return;
                }

                element.dataset.documentCardActionBound = "1";
                element.addEventListener("click", function (event) {
                    const action = element.dataset.documentCardAction || "";
                    const activeContext = getActiveFamilyCardEditContext();

                    event.preventDefault();
                    event.stopPropagation();

                    if (activeContext && !isAllowedDuringFamilyCardEdit(element, activeContext)) {
                        showFamilyCardLockMessage(element, activeContext.message);
                        return;
                    }

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

        function bindStudentCardSubmitScope() {
            const form = document.getElementById("famiglia-detail-form");
            if (!form || form.dataset.studentCardSubmitScopeBound === "1") {
                return;
            }

            form.dataset.studentCardSubmitScopeBound = "1";
            window.setTimeout(function () {
                form.addEventListener("submit", function (event) {
                    const submitter = event.submitter;
                    const activeEditor = document.activeElement && document.activeElement.closest
                        ? document.activeElement.closest(".family-student-card-editor")
                        : null;
                    const activeFamilyGeneralEditor = document.activeElement && document.activeElement.closest
                        ? document.activeElement.closest(".family-general-card-editor")
                        : null;
                    const activeInlineCardSubmitTarget = activeEditor
                        ? (
                            activeEditor.classList.contains("family-relative-card-editor")
                                ? "familiari"
                                : activeEditor.classList.contains("family-document-card-editor")
                                    ? "documenti"
                                    : ""
                        )
                        : "";
                    const shouldUseFamilyGeneralScope = Boolean(
                        (submitter && submitter.dataset.familyGeneralSubmit === "1") ||
                        form.dataset.pendingFamilyGeneralSubmit === "1" ||
                        activeFamilyGeneralEditor
                    );
                    const inlineCardSubmitTarget =
                        (submitter && submitter.dataset.cardInlineSubmit) ||
                        activeInlineCardSubmitTarget ||
                        "";
                    const shouldUseStudentScope = Boolean(
                        (submitter && submitter.dataset.studentCardSubmit === "studenti") ||
                        form.dataset.pendingStudentCardSubmit === "1" ||
                        (activeEditor && !activeInlineCardSubmitTarget)
                    );

                    if (shouldUseFamilyGeneralScope) {
                        const modeInput = document.getElementById("famiglia-edit-scope");

                        if (modeInput) {
                            modeInput.value = "full";
                        }
                        delete form.dataset.pendingFamilyGeneralSubmit;
                        return;
                    }

                    if (inlineCardSubmitTarget) {
                        const modeInput = document.getElementById("famiglia-edit-scope");
                        const targetInput = document.getElementById("famiglia-inline-target");

                        if (modeInput) {
                            modeInput.value = "inline";
                        }
                        if (targetInput) {
                            targetInput.value = inlineCardSubmitTarget;
                        }
                        return;
                    }

                    if (!shouldUseStudentScope) {
                        return;
                    }

                    const modeInput = document.getElementById("famiglia-edit-scope");
                    const targetInput = document.getElementById("famiglia-inline-target");

                    if (modeInput) {
                        modeInput.value = "inline";
                    }
                    if (targetInput) {
                        targetInput.value = "studenti";
                    }
                    delete form.dataset.pendingStudentCardSubmit;
                });
            }, 0);
        }

        const statoSelect = document.getElementById("id_stato_relazione_famiglia");
        const indirizzoSelect = document.getElementById("id_indirizzo_principale");
        const cognomeFamigliaInput = document.getElementById("id_cognome_famiglia");

        const addStatoBtn = document.getElementById("add-stato-btn");
        const editStatoBtn = document.getElementById("edit-stato-btn");
        const deleteStatoBtn = document.getElementById("delete-stato-btn");

        const addIndirizzoBtn = document.getElementById("add-indirizzo-btn");
        const editIndirizzoBtn = document.getElementById("edit-indirizzo-btn");
        const deleteIndirizzoBtn = document.getElementById("delete-indirizzo-btn");
        let refreshStatoButtons = function () {};
        let refreshIndirizzoButtons = function () {};

        function updateMainRelatedButtons() {
            refreshStatoButtons();
            refreshIndirizzoButtons();
        }

        const statoCrud = entityRoutes.wireCrudButtonsById({
            select: statoSelect,
            relatedType: "stato_relazione_famiglia",
            addBtn: addStatoBtn,
            editBtn: editStatoBtn,
            deleteBtn: deleteStatoBtn,
            openRelatedPopup: openRelatedPopup,
        });
        refreshStatoButtons = statoCrud.refresh;

        const indirizzoCrud = entityRoutes.wireCrudButtonsById({
            select: indirizzoSelect,
            relatedType: "indirizzo",
            addBtn: addIndirizzoBtn,
            editBtn: editIndirizzoBtn,
            deleteBtn: deleteIndirizzoBtn,
            openRelatedPopup: openRelatedPopup,
        });
        refreshIndirizzoButtons = indirizzoCrud.refresh;

        if (statoSelect) {
            statoSelect.addEventListener("change", updateMainRelatedButtons);
        }

        if (indirizzoSelect) {
            indirizzoSelect.addEventListener("change", updateMainRelatedButtons);
            indirizzoSelect.addEventListener("change", function () {
                familiariInlineAddressDefaults.syncRows();
                syncFamiliareConviventeRows();
                studentiInlineAddressDefaults.syncRows();
                famigliaInlineAddressCollection.refreshCollectionHelp(document.getElementById("famiglia-inline-lock-container"));
            });
        }

        if (cognomeFamigliaInput) {
            cognomeFamigliaInput.addEventListener("input", function () {
                studentiInlineAddressDefaults.syncRows();
            });
            cognomeFamigliaInput.addEventListener("change", function () {
                studentiInlineAddressDefaults.syncRows();
            });
        }

        inlineManagers.familiari.prepare();
        inlineManagers.studenti.prepare();
        inlineManagers.documenti.prepare();
        const inlineLockRoot = famigliaInlineRoot();
        if (inlineLockRoot) {
            tabs.bindTabButtons(getFamigliaTabStorageKey(), inlineLockRoot);
            inlineTabs.bindTabNavigationLock({
                containerId: inlineLockContainerId,
                targetInputId: targetInputId,
                getViewMode: function () {
                    return window.famigliaViewMode;
                },
            });
            bindStudentCardTabNavigationLock();
        }
        document.querySelectorAll("#" + inlineLockContainerId + " .tab-btn[data-tab-target]").forEach(btn => {
            btn.addEventListener("click", function () {
                setInlineTarget(btn.dataset.tabTarget);
                updateInlineEditButtonLabel(btn.dataset.tabTarget);
                syncActiveTabUrl(btn.dataset.tabTarget);
                refreshInlineEditScope();
            });
        });
        updateMainRelatedButtons();
        collapsible.initCollapsibleSections(document);
        bindNotesSectionState();
        formTools.initSearchableSelects(document.getElementById("famiglia-lock-container"));
        initFamilyNoteDialog();
        famigliaInlineAddressCollection.bindTracking(document.getElementById("famiglia-inline-lock-container"));
        wireInlineRelatedButtons(document);
        bindFamilyCardPageInteractionLock();
        bindFamilyCardStickyActions();
        wireFamilyGeneralCardActions(document);
        wireFamigliaInlineActionTriggers(document);
        wireStudentCardActions(document);
        wireRelativeCardActions(document);
        wireDocumentCardActions(document);
        bindStudentCardNavigationLock();
        bindStudentCardSubmitScope();
        entityRoutes.wirePopupTriggerElements(document, {
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        restoreActiveTab();
        familiariInlineAddressDefaults.syncRows();
        bindAllFamiliareConviventeAddress();
        syncFamiliareConviventeRows({ onlyNew: true });
        bindAllFamiliareInlineSex();
        bindAllStudenteInlineSex();
        bindAllStudenteInlineBirthDateOrdering();
        studentiInlineAddressDefaults.syncRows();
        sortStudentiInlineRows();
        formTools.initCodiceFiscale(document.getElementById("famiglia-inline-lock-container"));
        famigliaInlineAddressCollection.refreshCollectionHelp(document.getElementById("famiglia-inline-lock-container"));
        syncStudentCardEmptyState();
        syncRelativeCardEmptyState();
        syncDocumentCardEmptyState();
        refreshTabCounts();
        refreshInlineEditScope();
        initFamilySideCardCollapse();
        initFamilySideCardReorder();
        initFamilyRateYearSwitch();
        initFamilyViewSideHeightSync();
        refreshStudentCardInteractionLocks();
        refreshCardPageInteractionLocks();
        syncNotesSectionState();
    }

    return {
        init,
        refreshLockedTabs: function () {
            refreshLockedTabsHandler();
        },
        refreshInlineEditScope: function () {
            refreshInlineEditScopeHandler();
        },
    };
})();

