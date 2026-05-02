(function () {
    const APP_STACK_KEY = "arboris:application-navigation-stack:v1";
    const APP_STACK_MAX_LENGTH = 80;
    const TRANSIENT_QUERY_PARAMS = [
        "popup",
        "return_to",
        "next",
        "_edit_scope",
        "_inline_target",
    ];
    const TRANSIENT_PATH_PARTS = [
        "popup",
        "confirm_delete",
        "confirm-delete",
        "conferma_elimina",
        "conferma-elimina",
        "elimina",
        "delete",
        "ritiro_anticipato",
        "pagamento_rapido",
    ];

    function ensureFormId(form, index) {
        if (!form.id) {
            form.id = "auto-detail-form-" + index;
        }
        return form.id;
    }

    function findPageHeadActionsForForm(form) {
        const pageHeadActions = Array.from(document.querySelectorAll(".page-head .page-head-actions"));
        let matchedActions = null;

        pageHeadActions.forEach(actions => {
            if (actions.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING) {
                matchedActions = actions;
            }
        });

        return matchedActions;
    }

    function findPrimaryActionBar(form) {
        const actionBars = Array.from(form.querySelectorAll(".form-actions"));
        return actionBars.reverse().find(actionBar =>
            actionBar.querySelector('button[type="submit"], input[type="submit"]')
        ) || null;
    }

    function ensureStickyActionBar(actionBar) {
        if (!actionBar || actionBar.dataset.skipAutoSticky === "1") {
            return;
        }

        if (!actionBar.classList.contains("sticky-form-actions")) {
            actionBar.classList.add("sticky-form-actions");
        }

        const nextElement = actionBar.nextElementSibling;
        if (nextElement && nextElement.classList.contains("sticky-actions-spacer")) {
            return;
        }

        const spacer = document.createElement("div");
        spacer.className = "sticky-actions-spacer";
        actionBar.insertAdjacentElement("afterend", spacer);
    }

    function copySubmitAttributes(sourceButton, targetButton) {
        [
            "name",
            "value",
            "formaction",
            "formenctype",
            "formmethod",
            "formnovalidate",
            "formtarget",
        ].forEach(attributeName => {
            const attributeValue = sourceButton.getAttribute(attributeName);
            if (attributeValue !== null) {
                targetButton.setAttribute(attributeName, attributeValue);
            }
        });
    }

    function ensureHeaderSaveButton(form, actionBar, pageHeadActions) {
        if (!pageHeadActions || pageHeadActions.querySelector(`[data-auto-save-for="${form.id}"]`)) {
            return;
        }

        const sourceSubmitButton = actionBar.querySelector('button[type="submit"], input[type="submit"]');
        if (!sourceSubmitButton) {
            return;
        }

        const saveButton = document.createElement("button");
        saveButton.type = "submit";
        saveButton.className = "btn btn-save-soft page-head-save-btn";
        saveButton.textContent = "Salva le modifiche";
        saveButton.setAttribute("form", form.id);
        saveButton.dataset.autoSaveFor = form.id;

        copySubmitAttributes(sourceSubmitButton, saveButton);

        if (form.classList.contains("detail-form")) {
            saveButton.dataset.editModeFor = form.id;
            if (form.classList.contains("is-view-mode")) {
                saveButton.classList.add("is-hidden");
            }
        }

        pageHeadActions.insertAdjacentElement("afterbegin", saveButton);
    }

    function bindBackButtons(container) {
        getApplicationBackButtons(container || document).forEach(button => {
            if (button.dataset.backBound === "1") {
                return;
            }

            const fallback = getBackButtonFallback(button);
            const stableBackUrl = resolveApplicationBackUrl(fallback, { commit: false });
            if (stableBackUrl) {
                button.dataset.stableBackUrl = stableBackUrl;
                if (button.tagName.toLowerCase() === "a") {
                    button.setAttribute("href", stableBackUrl);
                }
            }
            button.dataset.backBound = "1";

            button.addEventListener("click", function (event) {
                const targetUrl = resolveApplicationBackUrl(getBackButtonFallback(button), { commit: true });

                event.preventDefault();
                window.location.assign(targetUrl || fallback || "/");
            });
        });
    }

    function getStableBackStorage() {
        try {
            return window.sessionStorage || null;
        } catch (e) {
            return null;
        }
    }

    function normalizeInternalUrl(value) {
        if (!value) {
            return null;
        }

        try {
            const url = new URL(value, window.location.origin);
            if (url.origin !== window.location.origin) {
                return null;
            }
            return url;
        } catch (e) {
            return null;
        }
    }

    function getNormalizedApplicationUrl(value) {
        const url = normalizeInternalUrl(value);
        if (!url) {
            return null;
        }

        TRANSIENT_QUERY_PARAMS.forEach(paramName => {
            url.searchParams.delete(paramName);
        });
        url.hash = "";

        return url.pathname + url.search;
    }

    function getCurrentApplicationUrl() {
        return getNormalizedApplicationUrl(window.location.href);
    }

    function readApplicationStack() {
        const storage = getStableBackStorage();
        if (!storage) {
            return [];
        }

        try {
            const parsed = JSON.parse(storage.getItem(APP_STACK_KEY) || "[]");
            if (!Array.isArray(parsed)) {
                return [];
            }

            return parsed
                .filter(entry => entry && typeof entry.url === "string")
                .map(entry => ({
                    url: entry.url,
                    title: typeof entry.title === "string" ? entry.title : "",
                    timestamp: Number(entry.timestamp) || Date.now(),
                }));
        } catch (e) {
            return [];
        }
    }

    function writeApplicationStack(stack) {
        const storage = getStableBackStorage();
        if (!storage) {
            return;
        }

        try {
            storage.setItem(APP_STACK_KEY, JSON.stringify(stack.slice(-APP_STACK_MAX_LENGTH)));
        } catch (e) {}
    }

    function getCurrentPageTitle() {
        const titleNode = document.querySelector(".page-title, h1");
        const title = titleNode ? titleNode.textContent : document.title;
        return (title || "").replace(/\s+/g, " ").trim();
    }

    function getNavigationType() {
        if (!window.performance || typeof window.performance.getEntriesByType !== "function") {
            return "";
        }

        const entries = window.performance.getEntriesByType("navigation");
        const entry = entries && entries.length ? entries[0] : null;
        return entry && entry.type ? entry.type : "";
    }

    function hasTransientPathPart(pathname) {
        const normalizedPath = (pathname || "").toLowerCase();
        return TRANSIENT_PATH_PARTS.some(part => normalizedPath.includes(part));
    }

    function isPopupPage() {
        return document.body.classList.contains("popup-page") ||
            window.location.search.includes("popup=1") ||
            window.name.indexOf("arboris-") === 0;
    }

    function isViewModeDetailPage() {
        const detailForms = Array.from(document.querySelectorAll("main .detail-form"));
        if (!detailForms.length) {
            return false;
        }

        return detailForms.some(form => form.classList.contains("is-view-mode"));
    }

    function hasNonViewDetailForm() {
        return Array.from(document.querySelectorAll("main .detail-form")).some(form =>
            !form.classList.contains("is-view-mode")
        );
    }

    function isApplicationStackPage() {
        const currentUrl = normalizeInternalUrl(window.location.href);
        if (!currentUrl || isPopupPage() || hasTransientPathPart(currentUrl.pathname)) {
            return false;
        }

        if (isViewModeDetailPage()) {
            return true;
        }

        if (hasNonViewDetailForm()) {
            return false;
        }

        return Boolean(document.querySelector("main.content-area"));
    }

    function normalizeStack(stack) {
        const seen = new Set();
        const normalized = [];

        stack.slice().reverse().forEach(entry => {
            if (!entry || !entry.url || seen.has(entry.url)) {
                return;
            }
            seen.add(entry.url);
            normalized.unshift(entry);
        });

        return normalized;
    }

    function recordCurrentApplicationPage() {
        const currentUrl = getCurrentApplicationUrl();
        if (!currentUrl || !isApplicationStackPage()) {
            return;
        }

        let stack = normalizeStack(readApplicationStack());
        const currentEntry = {
            url: currentUrl,
            title: getCurrentPageTitle(),
            timestamp: Date.now(),
        };
        const currentIndex = stack.findIndex(entry => entry.url === currentUrl);

        if (getNavigationType() === "back_forward" && currentIndex >= 0) {
            stack = stack.slice(0, currentIndex + 1);
            stack[stack.length - 1] = currentEntry;
            writeApplicationStack(stack);
            return;
        }

        if (currentIndex === stack.length - 1) {
            stack[stack.length - 1] = currentEntry;
            writeApplicationStack(stack);
            return;
        }

        if (currentIndex >= 0) {
            stack.splice(currentIndex, 1);
        }

        stack.push(currentEntry);
        writeApplicationStack(stack);
    }

    function getBackButtonFallback(button) {
        if (!button) {
            return "/";
        }

        if (button.dataset.fallbackUrl) {
            return button.dataset.fallbackUrl;
        }

        if (button.tagName.toLowerCase() === "a") {
            return button.getAttribute("href") || "/";
        }

        return "/";
    }

    function isImplicitApplicationBackLink(element) {
        if (!element || element.tagName.toLowerCase() !== "a" || !element.matches(".page-head-actions .btn[href]")) {
            return false;
        }

        const label = (element.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
        return label === "indietro";
    }

    function getApplicationBackButtons(container) {
        const explicitButtons = Array.from(container.querySelectorAll(".js-page-back-btn"));
        const implicitLinks = Array.from(container.querySelectorAll(".page-head-actions a.btn[href]"))
            .filter(isImplicitApplicationBackLink);
        return Array.from(new Set(explicitButtons.concat(implicitLinks)));
    }

    function buildFallbackBackUrl(fallback) {
        const fallbackUrl = normalizeInternalUrl(fallback) || normalizeInternalUrl("/");
        return fallbackUrl ? fallbackUrl.pathname + fallbackUrl.search + fallbackUrl.hash : "/";
    }

    function getExplicitBackUrl() {
        const currentUrl = normalizeInternalUrl(window.location.href);
        if (!currentUrl) {
            return "";
        }

        const nextValue = currentUrl.searchParams.get("next");
        const nextUrl = normalizeInternalUrl(nextValue);
        return nextUrl ? nextUrl.pathname + nextUrl.search + nextUrl.hash : "";
    }

    function resolveApplicationBackUrl(fallback, options) {
        const cfg = options || {};
        const currentUrl = getCurrentApplicationUrl();
        const fallbackUrl = buildFallbackBackUrl(fallback);
        const explicitBackUrl = getExplicitBackUrl();
        let stack = normalizeStack(readApplicationStack());
        let target = null;

        if (explicitBackUrl) {
            if (cfg.commit && currentUrl) {
                stack = stack.filter(entry => entry.url !== currentUrl);
                writeApplicationStack(stack);
            }
            return explicitBackUrl;
        }

        if (currentUrl) {
            const currentIndex = stack.findIndex(entry => entry.url === currentUrl);

            if (currentIndex > 0) {
                target = stack[currentIndex - 1];
                if (cfg.commit) {
                    stack = stack.slice(0, currentIndex);
                }
            } else if (currentIndex === 0) {
                if (cfg.commit) {
                    stack = stack.slice(0, 1);
                }
            } else if (stack.length) {
                target = stack[stack.length - 1];
            }
        } else if (stack.length) {
            target = stack[stack.length - 1];
        }

        if (cfg.commit) {
            writeApplicationStack(stack);
        }

        return target && target.url ? target.url : fallbackUrl;
    }

    document.addEventListener("DOMContentLoaded", function () {
        const detailForms = Array.from(document.querySelectorAll("main .detail-form"));

        detailForms.forEach((form, index) => {
            ensureFormId(form, index + 1);

            const actionBar = findPrimaryActionBar(form);
            if (!actionBar) {
                return;
            }

            ensureStickyActionBar(actionBar);
            ensureHeaderSaveButton(form, actionBar, findPageHeadActionsForForm(form));
        });

        recordCurrentApplicationPage();
        bindBackButtons(document);
    });

    window.ArborisAppNavigation = {
        recordCurrentPage: recordCurrentApplicationPage,
        resolveBackUrl: function (fallback) {
            return resolveApplicationBackUrl(fallback, { commit: false });
        },
        getStack: function () {
            return readApplicationStack().slice();
        },
        clearStack: function () {
            writeApplicationStack([]);
        },
    };
})();
