(function () {
    function getUseHref(useNode) {
        return (
            useNode.getAttribute("href") ||
            useNode.getAttribute("xlink:href") ||
            (useNode.href && useNode.href.baseVal) ||
            ""
        );
    }

    function shouldNormalize(useNode) {
        var href = getUseHref(useNode);
        return href && (href.indexOf("arboris-ui-icons.svg") !== -1 || href.charAt(0) === "#");
    }

    function normalizeIconViewBoxes(root) {
        var scope = root && root.querySelectorAll ? root : document;
        var uses = scope.querySelectorAll("svg:not([viewBox]) > use");
        uses.forEach(function (useNode) {
            if (!shouldNormalize(useNode)) {
                return;
            }
            var svg = useNode.ownerSVGElement;
            if (svg && !svg.hasAttribute("viewBox")) {
                svg.setAttribute("viewBox", "0 0 24 24");
                svg.setAttribute("focusable", "false");
            }
        });
    }

    function startObserver() {
        if (!window.MutationObserver || !document.documentElement) {
            return;
        }

        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType !== 1) {
                        return;
                    }
                    if (node.matches && node.matches("svg:not([viewBox])")) {
                        normalizeIconViewBoxes(node.parentNode || node);
                        return;
                    }
                    normalizeIconViewBoxes(node);
                });
            });
        });

        observer.observe(document.documentElement, {
            childList: true,
            subtree: true
        });
    }

    function boot() {
        normalizeIconViewBoxes(document);
        startObserver();
    }

    window.ArborisNormalizeIconViewBoxes = normalizeIconViewBoxes;

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
