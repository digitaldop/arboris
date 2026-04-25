window.ArborisCurrencyFields = (function () {
    const FIELD_SELECTOR = "input[data-currency]";
    const IGNORED_INPUT_TYPES = new Set(["hidden", "checkbox", "radio", "file", "submit", "button", "reset"]);

    function shouldEnhance(input) {
        if (!input || input.dataset.currencyEnhanced === "1") {
            return false;
        }

        if (IGNORED_INPUT_TYPES.has((input.type || "").toLowerCase())) {
            return false;
        }

        return Boolean((input.dataset.currency || "").trim());
    }

    function buildCurrencyBadge(code) {
        const badge = document.createElement("span");
        badge.className = "currency-suffix";
        badge.textContent = code;
        return badge;
    }

    function enhanceInput(input) {
        if (!shouldEnhance(input)) {
            return;
        }

        const currencyCode = (input.dataset.currency || "").trim();
        const existingGroup = input.closest(".currency-input-group");

        if (existingGroup) {
            if (input.classList.contains("currency-field-compact")) {
                existingGroup.classList.add("currency-input-group-compact");
            }
            if (
                input.dataset.currencyDisplay === "suffix"
                && !existingGroup.querySelector(".currency-suffix")
                && !existingGroup.querySelector(".currency-prefix")
            ) {
                existingGroup.classList.add("currency-input-group-suffix");
                existingGroup.appendChild(buildCurrencyBadge(currencyCode));
            }
            input.dataset.currencyEnhanced = "1";
            return;
        }

        const wrapper = document.createElement("div");
        wrapper.className = "currency-input-group currency-input-group-suffix";
        if (input.classList.contains("currency-field-compact")) {
            wrapper.classList.add("currency-input-group-compact");
        }

        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
        wrapper.appendChild(buildCurrencyBadge(currencyCode));
        input.dataset.currencyEnhanced = "1";
    }

    function init(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll(FIELD_SELECTOR).forEach(enhanceInput);
    }

    function observe() {
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!node || node.nodeType !== 1) {
                        return;
                    }

                    if (node.matches(FIELD_SELECTOR)) {
                        enhanceInput(node);
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
            if (!document.body.dataset.currencyFieldsObserverReady) {
                document.body.dataset.currencyFieldsObserverReady = "1";
                observe();
            }
        },
    };
})();
