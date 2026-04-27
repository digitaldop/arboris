window.ArborisCurrencyFields = (function () {
    const FIELD_SELECTOR = "input[data-currency]";
    const IGNORED_INPUT_TYPES = new Set(["hidden", "checkbox", "radio", "file", "submit", "button", "reset"]);
    const itFormatter = new Intl.NumberFormat("it-IT", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });

    function parseNumber(value) {
        const raw = String(value || "").trim().replace(/\s/g, "");
        if (!raw) {
            return null;
        }

        let normalized = raw;
        const hasComma = normalized.includes(",");
        const hasDot = normalized.includes(".");

        if (hasComma) {
            normalized = normalized.replace(/\./g, "").replace(",", ".");
        } else if (hasDot) {
            const parts = normalized.split(".");
            const lastPart = parts[parts.length - 1] || "";
            if (parts.length > 2 || lastPart.length === 3) {
                normalized = normalized.replace(/\./g, "");
            }
        }

        const parsed = Number.parseFloat(normalized);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function formatValue(value) {
        const parsed = typeof value === "number" ? value : parseNumber(value);
        if (!Number.isFinite(parsed)) {
            return "";
        }
        const intlValue = itFormatter.format(parsed);
        if (intlValue.includes(".") || Math.abs(parsed) < 1000) {
            return intlValue;
        }

        const negative = parsed < 0;
        const fixed = Math.abs(parsed).toFixed(2);
        const parts = fixed.split(".");
        const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
        return `${negative ? "-" : ""}${integerPart},${parts[1] || "00"}`;
    }

    function normalizeValue(value) {
        const parsed = parseNumber(value);
        if (!Number.isFinite(parsed)) {
            return "";
        }
        return parsed.toFixed(2);
    }

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

        input.type = "text";
        const currencyCode = (input.dataset.currency || "").trim();
        const existingGroup = input.closest(".currency-input-group");
        input.addEventListener("blur", function () {
            input.value = formatValue(input.value);
        });
        if ((input.value || "").trim()) {
            input.value = formatValue(input.value);
        }

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

    function normalizeFormFields(form) {
        if (!form) {
            return;
        }
        form.querySelectorAll(FIELD_SELECTOR).forEach(function (input) {
            input.value = normalizeValue(input.value);
        });
    }

    function bindFormSubmit(form) {
        if (!form || form.dataset.currencyNormalizeBound === "1") {
            return;
        }
        form.dataset.currencyNormalizeBound = "1";
        form.addEventListener("submit", function () {
            normalizeFormFields(form);
        });
    }

    function init(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll(FIELD_SELECTOR).forEach(enhanceInput);
        scope.querySelectorAll("form").forEach(bindFormSubmit);
        if (scope.tagName && scope.tagName.toLowerCase() === "form") {
            bindFormSubmit(scope);
        }
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
        parseNumber,
        formatValue,
        normalizeValue,
        normalizeFormFields,
    };
})();
