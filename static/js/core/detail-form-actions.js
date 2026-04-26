(function () {
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
        (container || document).querySelectorAll(".js-page-back-btn[data-fallback-url]").forEach(button => {
            if (button.dataset.backBound === "1") {
                return;
            }

            button.dataset.backBound = "1";
            button.addEventListener("click", function () {
                const fallback = button.dataset.fallbackUrl || "/";

                if (window.history.length > 1 && document.referrer) {
                    try {
                        const refUrl = new URL(document.referrer, window.location.origin);
                        if (refUrl.origin === window.location.origin) {
                            window.history.back();
                            return;
                        }
                    } catch (e) {}
                }

                window.location.assign(fallback);
            });
        });
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

        bindBackButtons(document);
    });
})();
