(function () {
    function childRows(rowId) {
        return Array.prototype.slice.call(
            document.querySelectorAll('[data-report-category-parent="' + rowId + '"]')
        );
    }

    function setToggleState(toggle, open) {
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        toggle.classList.toggle("is-open", open);
        toggle.innerHTML = open ? "&#9662;" : "&#9656;";
    }

    function closeDescendants(rowId) {
        childRows(rowId).forEach(function (row) {
            row.classList.add("is-hidden");
            var childId = row.getAttribute("data-report-category-row");
            var childToggle = document.querySelector('[data-report-category-toggle="' + childId + '"]');
            if (childToggle) {
                setToggleState(childToggle, false);
            }
            closeDescendants(childId);
        });
    }

    function init() {
        document.querySelectorAll("[data-report-category-toggle]").forEach(function (toggle) {
            toggle.addEventListener("click", function () {
                var rowId = toggle.getAttribute("data-report-category-toggle");
                var open = toggle.getAttribute("aria-expanded") !== "true";
                setToggleState(toggle, open);
                childRows(rowId).forEach(function (row) {
                    row.classList.toggle("is-hidden", !open);
                });
                if (!open) {
                    closeDescendants(rowId);
                }
            });
        });
    }

    document.addEventListener("DOMContentLoaded", init);
})();
