window.ArborisBrowserAutofill = (function () {
    const FORM_SELECTOR = "form:not(.login-form)";
    const FIELD_SELECTOR = "input, textarea, select";
    const IGNORED_INPUT_TYPES = new Set(["hidden", "checkbox", "radio", "file", "submit", "button", "reset"]);

    function isLoginField(field) {
        return Boolean(field && field.closest(".login-form"));
    }

    function shouldHandleField(field) {
        if (!field || isLoginField(field) || field.dataset.allowBrowserAutocomplete === "true") {
            return false;
        }

        if (field.tagName === "INPUT" && IGNORED_INPUT_TYPES.has((field.type || "").toLowerCase())) {
            return false;
        }

        return true;
    }

    function applyFieldAttributes(field) {
        if (!shouldHandleField(field)) {
            return;
        }

        const tagName = field.tagName;
        const inputType = tagName === "INPUT" ? (field.type || "text").toLowerCase() : "";

        if (tagName === "INPUT") {
            if (inputType === "password") {
                field.setAttribute("autocomplete", "new-password");
            } else if (["date", "time", "month", "week", "datetime-local", "number"].includes(inputType)) {
                field.setAttribute("autocomplete", "off");
            } else {
                field.setAttribute("autocomplete", "new-password");
            }
        } else {
            field.setAttribute("autocomplete", "off");
        }

        field.setAttribute("data-lpignore", "true");
        field.setAttribute("data-1p-ignore", "true");
        field.setAttribute("data-bwignore", "true");
    }

    function applyFormAttributes(form) {
        if (!form || form.classList.contains("login-form")) {
            return;
        }

        form.setAttribute("autocomplete", "off");
        form.setAttribute("data-lpignore", "true");
        form.setAttribute("data-1p-ignore", "true");
        form.setAttribute("data-bwignore", "true");

        form.querySelectorAll(FIELD_SELECTOR).forEach(applyFieldAttributes);
    }

    function init(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll(FORM_SELECTOR).forEach(applyFormAttributes);
        scope.querySelectorAll(FIELD_SELECTOR).forEach(applyFieldAttributes);
    }

    function observe() {
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!node || node.nodeType !== 1) {
                        return;
                    }

                    if (node.matches(FORM_SELECTOR)) {
                        applyFormAttributes(node);
                    }

                    if (node.matches(FIELD_SELECTOR)) {
                        applyFieldAttributes(node);
                    }

                    init(node);
                });
            });
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    return {
        init: function (root) {
            init(root || document);
            if (!document.body.dataset.browserAutofillObserverReady) {
                document.body.dataset.browserAutofillObserverReady = "1";
                observe();
            }
        },
    };
})();
