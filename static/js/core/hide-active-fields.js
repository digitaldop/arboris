(function () {
    function isActiveCheckbox(input) {
        if (!(input instanceof HTMLInputElement) || input.type !== "checkbox") {
            return false;
        }

        const name = input.name || "";
        return /(^|[-_])(attivo|attiva)$/.test(name);
    }

    function shouldRemainVisible(input) {
        return Boolean(
            input.dataset.activeFieldVisible === "1" ||
            input.closest(".active-field-visible, [data-active-field-visible='1']")
        );
    }

    function getCellIndex(cell) {
        if (!cell || !cell.parentElement) {
            return -1;
        }

        const rowCells = Array.from(cell.parentElement.children).filter((item) =>
            item instanceof HTMLTableCellElement
        );
        return rowCells.indexOf(cell);
    }

    function hideHeaderForCell(cell) {
        const index = getCellIndex(cell);
        if (index < 0) {
            return;
        }

        const table = cell.closest("table");
        const headerRow = table ? table.querySelector("thead tr") : null;
        if (!headerRow) {
            return;
        }

        const headerCells = Array.from(headerRow.children).filter((item) =>
            item instanceof HTMLTableCellElement
        );
        const headerCell = headerCells[index];
        if (headerCell) {
            headerCell.style.display = "none";
        }
    }

    function hideField(input) {
        const detailsField = input.closest(".inline-details-field");
        if (detailsField) {
            detailsField.style.display = "none";
        }

        const td = input.closest("td");
        if (td) {
            td.style.display = "none";
            hideHeaderForCell(td);
        }

        const tr = input.closest("tr");
        if (tr && tr.closest(".form-table")) {
            tr.style.display = "none";
        }

        const wrapper = input.closest(".mode-edit-field, .readonly-display, label");
        if (wrapper && wrapper !== td && wrapper !== tr && !detailsField) {
            const rowLike = wrapper.closest(".form-row, .field-row");
            if (rowLike) {
                rowLike.style.display = "none";
            }
        }
    }

    function scan(root) {
        (root || document).querySelectorAll('input[type="checkbox"]').forEach((input) => {
            if (isActiveCheckbox(input) && !shouldRemainVisible(input)) {
                hideField(input);
            }
        });
    }

    window.ArborisHideActiveFields = {
        init: scan,
    };

    document.addEventListener("DOMContentLoaded", function () {
        scan(document);

        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!(node instanceof HTMLElement)) {
                        return;
                    }

                    if (node.matches('input[type="checkbox"]')) {
                        if (isActiveCheckbox(node) && !shouldRemainVisible(node)) {
                            hideField(node);
                        }
                        return;
                    }

                    scan(node);
                });
            });
        });

        observer.observe(document.body, { childList: true, subtree: true });
    });
})();
