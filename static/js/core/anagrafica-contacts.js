window.ArborisAnagraficaContacts = (function () {
    function getTotalInput(section) {
        var prefix = section.dataset.contactPrefix;
        if (!prefix) {
            return null;
        }
        return section.querySelector('input[name="' + prefix + '-TOTAL_FORMS"]');
    }

    function nextIndex(totalInput) {
        var value = parseInt(totalInput.value || "0", 10);
        return Number.isNaN(value) ? 0 : value;
    }

    function wireRelatedButtons(container) {
        if (!window.ArborisRelatedEntityRoutes || typeof window.ArborisRelatedEntityRoutes.wireInlineRelatedButtons !== "function") {
            return;
        }
        window.ArborisRelatedEntityRoutes.wireInlineRelatedButtons(container, {
            openRelatedPopup: window.ArborisRelatedPopups && window.ArborisRelatedPopups.openRelatedPopup,
        });
    }

    function refreshEnhancements(container) {
        wireRelatedButtons(container);
        if (window.ArborisFloatingTooltips && typeof window.ArborisFloatingTooltips.init === "function") {
            window.ArborisFloatingTooltips.init(container);
        }
    }

    function addRow(section) {
        var totalInput = getTotalInput(section);
        var rows = section.querySelector("[data-contact-rows]");
        var template = section.querySelector("template[data-contact-empty-template]");
        if (!totalInput || !rows || !template) {
            return;
        }

        var index = nextIndex(totalInput);
        var html = template.innerHTML.split("__prefix__").join(String(index));
        var wrapper = document.createElement("div");
        wrapper.innerHTML = html.trim();
        var row = wrapper.firstElementChild;
        if (!row) {
            return;
        }

        rows.appendChild(row);
        totalInput.value = String(index + 1);
        refreshEnhancements(row);
    }

    function deleteRow(button) {
        var row = button.closest("[data-contact-row]");
        if (!row) {
            return;
        }
        var deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (deleteInput) {
            deleteInput.checked = true;
        }
        var primaryInput = row.querySelector('input[type="checkbox"][name$="-principale"], .contact-primary-input');
        if (primaryInput) {
            primaryInput.checked = false;
        }
        row.classList.add("is-contact-row-deleted");
        row.setAttribute("aria-hidden", "true");
    }

    function enforceSinglePrimary(input) {
        if (!input.checked) {
            return;
        }
        var section = input.closest("[data-contact-formset]");
        if (!section) {
            return;
        }
        section.querySelectorAll('input[type="checkbox"][name$="-principale"], .contact-primary-input').forEach(function (other) {
            if (other !== input) {
                other.checked = false;
            }
        });
    }

    function wireSection(section) {
        if (!section || section.dataset.contactFormsetBound === "1") {
            return;
        }
        section.dataset.contactFormsetBound = "1";

        var addButton = section.querySelector("[data-contact-add-row]");
        if (addButton) {
            addButton.addEventListener("click", function () {
                addRow(section);
            });
        }

        section.addEventListener("click", function (event) {
            var deleteButton = event.target.closest("[data-contact-delete-row]");
            if (!deleteButton) {
                return;
            }
            event.preventDefault();
            deleteRow(deleteButton);
        });

        section.addEventListener("change", function (event) {
            var target = event.target;
            if (!target || !target.matches('input[type="checkbox"][name$="-principale"], .contact-primary-input')) {
                return;
            }
            enforceSinglePrimary(target);
        });

        refreshEnhancements(section);
    }

    function init(container) {
        var root = container || document;
        if (!root || typeof root.querySelectorAll !== "function") {
            return;
        }
        root.querySelectorAll("[data-contact-formset]").forEach(wireSection);
    }

    return {
        init: init,
    };
})();
