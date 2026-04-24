window.ArborisTerminology = (function () {
    let terminology = null;
    let observer = null;
    const skipSelector = '[data-terminology-skip="true"]';
    const attributeNames = ["placeholder", "title", "aria-label"];
    const skippedTagNames = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA"]);

    function escapeRegExp(value) {
        return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function getConfig() {
        const node = document.getElementById("student-terminology-data");
        if (!node) {
            return null;
        }

        try {
            return JSON.parse(node.textContent || "{}");
        } catch (error) {
            return null;
        }
    }

    function hasSkipAncestor(node) {
        if (!node) {
            return false;
        }

        const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
        return Boolean(element && element.closest(skipSelector));
    }

    function replaceTerminology(text) {
        if (!text || !terminology || !Array.isArray(terminology.replacements)) {
            return text;
        }

        let updated = text;

        terminology.replacements.forEach((item) => {
            if (!item || !item.from || item.from === item.to) {
                return;
            }

            const pattern = new RegExp(`\\b${escapeRegExp(item.from)}\\b`, "g");
            updated = updated.replace(pattern, item.to);
        });

        return updated;
    }

    function processTextNode(node) {
        if (!node || !node.nodeValue || hasSkipAncestor(node)) {
            return;
        }

        const parent = node.parentElement;
        if (parent && skippedTagNames.has(parent.tagName)) {
            return;
        }

        const updated = replaceTerminology(node.nodeValue);
        if (updated !== node.nodeValue) {
            node.nodeValue = updated;
        }
    }

    function processElementAttributes(element) {
        if (!element || hasSkipAncestor(element) || skippedTagNames.has(element.tagName)) {
            return;
        }

        attributeNames.forEach((attributeName) => {
            const currentValue = element.getAttribute(attributeName);
            if (!currentValue) {
                return;
            }

            const updated = replaceTerminology(currentValue);
            if (updated !== currentValue) {
                element.setAttribute(attributeName, updated);
            }
        });
    }

    function processNode(node) {
        if (!node) {
            return;
        }

        if (node.nodeType === Node.TEXT_NODE) {
            processTextNode(node);
            return;
        }

        if (node.nodeType !== Node.ELEMENT_NODE) {
            return;
        }

        processElementAttributes(node);

        if (skippedTagNames.has(node.tagName)) {
            return;
        }

        const textWalker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
        let currentTextNode = textWalker.nextNode();
        while (currentTextNode) {
            processTextNode(currentTextNode);
            currentTextNode = textWalker.nextNode();
        }

        node.querySelectorAll("*").forEach((element) => {
            processElementAttributes(element);
        });
    }

    function startObserver() {
        if (observer) {
            return;
        }

        observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === "characterData") {
                    processTextNode(mutation.target);
                    return;
                }

                if (mutation.type === "attributes") {
                    processElementAttributes(mutation.target);
                    return;
                }

                mutation.addedNodes.forEach((node) => {
                    processNode(node);
                });
            });
        });

        observer.observe(document.documentElement, {
            subtree: true,
            childList: true,
            characterData: true,
            attributes: true,
            attributeFilter: attributeNames,
        });
    }

    function init() {
        terminology = getConfig();
        if (!terminology || !Array.isArray(terminology.replacements)) {
            return;
        }

        const hasVisualOverride = terminology.replacements.some((item) => item && item.from !== item.to);
        if (!hasVisualOverride) {
            return;
        }

        processNode(document.documentElement);
        startObserver();
    }

    return {
        init: init,
    };
})();
