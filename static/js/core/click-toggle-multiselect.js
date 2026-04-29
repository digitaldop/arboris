window.ArborisClickToggleMultiselect = (function () {
    function isManagedSelect(select) {
        return Boolean(
            select &&
            select.matches &&
            select.matches('select[multiple][data-click-toggle-multiple="1"]')
        );
    }

    function dispatchSelectEvents(select) {
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function toggleOption(option) {
        const select = option.parentElement;
        if (!isManagedSelect(select) || select.disabled) {
            return false;
        }

        option.selected = !option.selected;
        if (select.focus) {
            select.focus({ preventScroll: true });
        }
        dispatchSelectEvents(select);
        return true;
    }

    function bind(root) {
        const scope = root || document;
        if (scope.documentElement && scope.documentElement.dataset.clickToggleMultiselectBound === "1") {
            return;
        }
        if (scope.documentElement) {
            scope.documentElement.dataset.clickToggleMultiselectBound = "1";
        }

        scope.addEventListener(
            "mousedown",
            function (event) {
                const option = event.target && event.target.closest ? event.target.closest("option") : null;
                if (!option || !toggleOption(option)) {
                    return;
                }
                event.preventDefault();
            },
            true
        );
    }

    function init(root) {
        bind(root || document);
    }

    return {
        init,
    };
})();
