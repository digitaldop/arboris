window.ArborisBulkActions = (function () {
    function init(root) {
        const scope = root || document;
        const forms = scope.querySelectorAll("[data-bulk-form]");

        forms.forEach(form => {
            const checkboxes = Array.from(form.querySelectorAll("[data-bulk-checkbox]"));
            const selectAll = form.querySelector("[data-bulk-select-all]");
            const countNode = form.querySelector("[data-bulk-count]");
            const submitButtons = Array.from(form.querySelectorAll("[data-bulk-submit]"));
            const toolbar = form.querySelector("[data-bulk-toolbar]");

            function selectedCount() {
                return checkboxes.filter(checkbox => checkbox.checked).length;
            }

            function refresh() {
                const count = selectedCount();
                if (countNode) {
                    countNode.textContent = String(count);
                }
                submitButtons.forEach(button => {
                    button.disabled = count === 0;
                    button.classList.toggle("is-disabled", count === 0);
                });
                if (toolbar) {
                    toolbar.classList.toggle("is-empty", count === 0);
                }
                if (selectAll) {
                    selectAll.checked = count > 0 && count === checkboxes.length;
                    selectAll.indeterminate = count > 0 && count < checkboxes.length;
                }
                checkboxes.forEach(checkbox => {
                    const row = checkbox.closest("tr");
                    if (row) {
                        row.classList.toggle("finance-bulk-selected-row", checkbox.checked);
                    }
                });
            }

            if (selectAll) {
                selectAll.addEventListener("change", () => {
                    checkboxes.forEach(checkbox => {
                        checkbox.checked = selectAll.checked;
                    });
                    refresh();
                });
            }

            checkboxes.forEach(checkbox => {
                checkbox.addEventListener("change", refresh);
            });

            refresh();
        });
    }

    return {
        init,
    };
})();
