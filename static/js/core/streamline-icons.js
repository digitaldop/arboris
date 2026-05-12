(function () {
    var EMOTIONAL_ICON_SELECTORS = [
        ".page-head-icon",
        ".settings-hero-icon",
        ".settings-card-icon",
        ".settings-module-icon",
        ".dashboard-info-icon",
        ".family-stat-icon",
        ".family-system-icon",
        ".family-meta-icon",
        ".interested-page-hero-icon",
        ".interested-summary-icon",
        ".interested-record-icon",
        ".interested-timeline-icon",
        ".interested-card-icon",
        ".finance-guide-icon",
        ".supplier-document-summary-icon",
        ".supplier-payment-hero-icon",
        ".rate-detail-hero-icon",
        ".rate-payment-hero-icon",
        ".rate-reconcile-page-hero-icon",
        ".rate-detail-summary-icon",
        ".calendar-event-hero-icon",
        ".calendar-category-hero-icon",
        ".related-status-icon-tile",
        ".archive-record-icon",
        ".archive-empty-icon",
        ".feedback-admin-summary-icon",
        ".audit-log-title-icon",
        ".audit-log-kpi-icon",
        ".audit-log-card-icon",
        ".audit-log-warning-icon",
        ".audit-log-empty-icon",
        ".database-backup-empty-icon",
        ".fondo-plans-status-icon",
        ".fondo-plan-summary-hero-icon",
        ".fondo-plan-empty-icon",
        ".fondo-movement-hero-icon",
        ".ga-admin-dashboard-title-icon",
        ".ga-admin-dashboard-workflow-icon"
    ];

    var SUPPORTED_IDS = {
        alert: true,
        archive: true,
        bank: true,
        bell: true,
        briefcase: true,
        calendar: true,
        check: true,
        child: true,
        clock: true,
        coins: true,
        document: true,
        edit: true,
        eye: true,
        family: true,
        "family-heart": true,
        finance: true,
        "hands-heart": true,
        home: true,
        lightbulb: true,
        list: true,
        mail: true,
        menu: true,
        message: true,
        printer: true,
        refresh: true,
        search: true,
        settings: true,
        shield: true,
        student: true,
        supplier: true,
        timer: true,
        user: true
    };

    function getUseHref(useNode) {
        return (
            useNode.getAttribute("href") ||
            useNode.getAttribute("xlink:href") ||
            (useNode.href && useNode.href.baseVal) ||
            ""
        );
    }

    function getSymbolId(href) {
        var hashIndex = href.lastIndexOf("#");
        return hashIndex >= 0 ? href.slice(hashIndex + 1) : "";
    }

    function getActiveIconStyle() {
        if (!document.body) {
            return null;
        }

        if (document.body.classList.contains("ui-iconscout-3d-icons")) {
            return {
                spriteUrl: document.body.getAttribute("data-iconscout-3d-icons-url"),
                svgClass: "iconscout-3d-emotional-svg"
            };
        }

        if (document.body.classList.contains("ui-streamline-icons")) {
            return {
                spriteUrl: document.body.getAttribute("data-streamline-icons-url"),
                svgClass: "streamline-emotional-svg"
            };
        }

        return null;
    }

    function replaceUse(useNode, iconStyle) {
        var href = getUseHref(useNode);
        if (
            !href ||
            (
                href.indexOf("arboris-ui-icons.svg") === -1 &&
                href.indexOf("arboris-streamline-icons.svg") === -1 &&
                href.indexOf("arboris-iconscout-3d-icons.svg") === -1
            )
        ) {
            return;
        }

        var symbolId = getSymbolId(href);
        if (!SUPPORTED_IDS[symbolId]) {
            return;
        }

        var nextHref = iconStyle.spriteUrl + "#" + symbolId;
        useNode.setAttribute("href", nextHref);
        useNode.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", nextHref);

        var svg = useNode.ownerSVGElement;
        if (svg) {
            svg.setAttribute("viewBox", "0 0 24 24");
            svg.setAttribute("focusable", "false");
            svg.classList.remove("streamline-emotional-svg", "iconscout-3d-emotional-svg");
            svg.classList.add(iconStyle.svgClass);
        }
    }

    function applyStreamlineIcons(root) {
        var iconStyle = getActiveIconStyle();
        if (!iconStyle || !iconStyle.spriteUrl) {
            return;
        }

        var scope = root && root.querySelectorAll ? root : document;
        var selector = EMOTIONAL_ICON_SELECTORS.join(", ") + " svg > use";
        scope.querySelectorAll(selector).forEach(function (useNode) {
            replaceUse(useNode, iconStyle);
        });
    }

    function startObserver() {
        if (!window.MutationObserver || !document.documentElement) {
            return;
        }

        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType === 1) {
                        applyStreamlineIcons(node);
                    }
                });
            });
        });

        observer.observe(document.documentElement, {
            childList: true,
            subtree: true
        });
    }

    function boot() {
        applyStreamlineIcons(document);
        startObserver();
    }

    window.ArborisApplyStreamlineIcons = applyStreamlineIcons;
    window.ArborisApplyVisualIcons = applyStreamlineIcons;

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
