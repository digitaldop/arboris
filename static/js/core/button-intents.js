window.ArborisButtonIntents = (function () {
    const SAVE_PATTERN = /\bsalva\b/i;
    const DANGER_PATTERN = /\b(elimina|eliminazione|rimuovi)\b/i;
    const PROFILE_PATTERN = /\bvedi\s+profilo\b/i;
    const EDIT_PATTERN = /\bmodifica\b/i;
    const BUTTON_SELECTOR = [
        ".btn",
        ".inline-remove-btn",
        ".admin-section-title-btn",
        "button",
    ].join(",");

    let observer = null;
    let refreshQueued = false;

    function normalizeLabel(value) {
        return (value || "").replace(/\s+/g, " ").trim();
    }

    function getButtonLabel(button) {
        const explicitLabel = button.getAttribute("data-button-intent-label");
        if (explicitLabel) {
            return normalizeLabel(explicitLabel);
        }

        const labelElement = button.querySelector("[data-btn-label], .btn-label");
        if (labelElement) {
            return normalizeLabel(labelElement.textContent);
        }

        return normalizeLabel(button.textContent || button.getAttribute("aria-label") || button.title || "");
    }

    function resolveIntent(button) {
        const explicitIntent = (button.getAttribute("data-button-intent") || "").trim().toLowerCase();
        if (["save", "danger", "profile", "edit"].includes(explicitIntent)) {
            return explicitIntent;
        }

        const label = getButtonLabel(button);
        if (!label) {
            return "";
        }

        if (DANGER_PATTERN.test(label)) {
            return "danger";
        }

        if (SAVE_PATTERN.test(label)) {
            return "save";
        }

        if (PROFILE_PATTERN.test(label)) {
            return "profile";
        }

        if (EDIT_PATTERN.test(label)) {
            return "edit";
        }

        return "";
    }

    function applyIntent(button) {
        if (!button || button.dataset.buttonIntentSkip === "1") {
            return;
        }

        const intent = resolveIntent(button);
        button.classList.toggle("btn-intent-save", intent === "save");
        button.classList.toggle("btn-intent-danger", intent === "danger");
        button.classList.toggle("btn-intent-profile", intent === "profile");
        button.classList.toggle("btn-intent-edit", intent === "edit");
    }

    function refresh(root) {
        const scope = root || document;
        if (scope.matches && scope.matches(BUTTON_SELECTOR)) {
            applyIntent(scope);
        }

        scope.querySelectorAll(BUTTON_SELECTOR).forEach(applyIntent);
    }

    function queueRefresh() {
        if (refreshQueued) {
            return;
        }

        refreshQueued = true;
        window.requestAnimationFrame(function () {
            refreshQueued = false;
            refresh(document);
        });
    }

    function startObserver() {
        if (observer || !document.body) {
            return;
        }

        observer = new MutationObserver(queueRefresh);
        observer.observe(document.body, {
            subtree: true,
            childList: true,
            characterData: true,
            attributes: true,
            attributeFilter: ["class", "title", "aria-label", "data-button-intent", "data-button-intent-label"],
        });
    }

    function init(root) {
        refresh(root || document);
        startObserver();
    }

    return {
        init,
        refresh,
    };
})();
