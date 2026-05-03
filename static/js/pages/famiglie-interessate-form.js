window.ArborisFamiglieInteressateForm = (function () {
    const AUTO_AGE_ATTRIBUTE = "data-auto-age-value";

    function getManagementInput(prefix, suffix) {
        return document.getElementById("id_" + prefix + "-" + suffix);
    }

    function replaceFormIndex(value, prefix, index) {
        if (!value) {
            return value;
        }
        return value
            .replace(new RegExp(prefix + "-__prefix__-", "g"), prefix + "-" + index + "-")
            .replace(new RegExp(prefix + "-\\d+-", "g"), prefix + "-" + index + "-");
    }

    function updateElementIndex(element, prefix, index) {
        ["name", "id", "for", "aria-describedby"].forEach(function (attribute) {
            const value = element.getAttribute(attribute);
            if (value) {
                element.setAttribute(attribute, replaceFormIndex(value, prefix, index));
            }
        });
    }

    function resetNewRowFields(row) {
        row.querySelectorAll("input, select, textarea").forEach(function (field) {
            if (field.type === "hidden") {
                field.value = "";
                return;
            }
            if (field.type === "checkbox" || field.type === "radio") {
                field.checked = false;
                return;
            }
            field.value = "";
        });
    }

    function parseIsoDate(value) {
        const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
        if (!match) {
            return null;
        }

        const year = parseInt(match[1], 10);
        const month = parseInt(match[2], 10);
        const day = parseInt(match[3], 10);
        const date = new Date(year, month - 1, day);
        if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
            return null;
        }
        return date;
    }

    function formatAgeFromBirthDate(value) {
        const birthDate = parseIsoDate(value);
        if (!birthDate) {
            return "";
        }

        const today = new Date();
        today.setHours(0, 0, 0, 0);
        birthDate.setHours(0, 0, 0, 0);
        if (birthDate > today) {
            return "";
        }

        let months = (today.getFullYear() - birthDate.getFullYear()) * 12;
        months += today.getMonth() - birthDate.getMonth();
        if (today.getDate() < birthDate.getDate()) {
            months -= 1;
        }

        if (months <= 0) {
            return "Meno di 1 mese";
        }
        if (months < 24) {
            return months === 1 ? "1 mese" : months + " mesi";
        }

        const years = Math.floor(months / 12);
        const remainingMonths = months % 12;
        const yearsLabel = years === 1 ? "1 anno" : years + " anni";
        if (!remainingMonths) {
            return yearsLabel;
        }
        return yearsLabel + " e " + (remainingMonths === 1 ? "1 mese" : remainingMonths + " mesi");
    }

    function updateIndicativeAgeForRow(row) {
        const birthDateInput = row.querySelector('input[name$="-data_nascita"]');
        const ageInput = row.querySelector('input[name$="-eta_indicativa"]');
        if (!birthDateInput || !ageInput) {
            return;
        }

        const nextValue = formatAgeFromBirthDate(birthDateInput.value);
        const currentValue = (ageInput.value || "").trim();
        const previousAutoValue = ageInput.getAttribute(AUTO_AGE_ATTRIBUTE) || "";
        if (currentValue && currentValue !== previousAutoValue) {
            return;
        }

        ageInput.value = nextValue;
        if (nextValue) {
            ageInput.setAttribute(AUTO_AGE_ATTRIBUTE, nextValue);
        } else {
            ageInput.removeAttribute(AUTO_AGE_ATTRIBUTE);
        }
    }

    function wireIndicativeAge(root) {
        const scope = root || document;
        scope.querySelectorAll('[data-formset-row="minori"]').forEach(updateIndicativeAgeForRow);
        scope.addEventListener("change", function (event) {
            const birthDateInput = event.target.closest('input[name$="-data_nascita"]');
            if (!birthDateInput) {
                return;
            }
            const row = birthDateInput.closest('[data-formset-row="minori"]');
            if (row) {
                updateIndicativeAgeForRow(row);
            }
        });
    }

    function reindexDynamicRows(prefix) {
        const initialFormsInput = getManagementInput(prefix, "INITIAL_FORMS");
        const totalFormsInput = getManagementInput(prefix, "TOTAL_FORMS");
        const initialForms = parseInt(initialFormsInput ? initialFormsInput.value : "0", 10) || 0;
        const rows = Array.from(document.querySelectorAll('[data-formset-row="' + prefix + '"]'));

        rows.forEach(function (row, rowIndex) {
            const nextIndex = rowIndex;
            row.querySelectorAll("*").forEach(function (element) {
                updateElementIndex(element, prefix, nextIndex);
            });
            updateElementIndex(row, prefix, nextIndex);
        });

        if (totalFormsInput) {
            totalFormsInput.value = String(rows.length);
        }

        rows.forEach(function (row, rowIndex) {
            const removeButton = row.querySelector("[data-formset-remove]");
            if (removeButton) {
                removeButton.hidden = rowIndex < initialForms;
            }
        });
    }

    function addFormsetRow(prefix) {
        const list = document.querySelector('[data-formset-list="' + prefix + '"]');
        const template = document.querySelector('template[data-formset-empty="' + prefix + '"]');
        const totalFormsInput = getManagementInput(prefix, "TOTAL_FORMS");
        const maxFormsInput = getManagementInput(prefix, "MAX_NUM_FORMS");

        if (!list || !template || !totalFormsInput) {
            return;
        }

        const currentIndex = parseInt(totalFormsInput.value || "0", 10) || 0;
        const maxForms = parseInt(maxFormsInput ? maxFormsInput.value : "0", 10) || 0;
        if (maxForms && currentIndex >= maxForms) {
            return;
        }

        const fragment = template.content.cloneNode(true);
        const row = fragment.querySelector('[data-formset-row="' + prefix + '"]');
        if (!row) {
            return;
        }

        row.querySelectorAll("*").forEach(function (element) {
            updateElementIndex(element, prefix, currentIndex);
        });
        updateElementIndex(row, prefix, currentIndex);
        resetNewRowFields(row);
        list.appendChild(fragment);
        totalFormsInput.value = String(currentIndex + 1);
        updateIndicativeAgeForRow(list.lastElementChild);

        const focusTarget = list.lastElementChild ? list.lastElementChild.querySelector("input, select, textarea") : null;
        if (focusTarget) {
            focusTarget.focus();
        }
    }

    function wireRemoveButtons(root) {
        root.addEventListener("click", function (event) {
            const removeButton = event.target.closest("[data-formset-remove]");
            if (!removeButton) {
                return;
            }
            const row = removeButton.closest("[data-formset-row]");
            if (!row) {
                return;
            }
            const prefix = row.dataset.formsetRow;
            row.remove();
            reindexDynamicRows(prefix);
        });
    }

    function init(root) {
        const scope = root || document;
        scope.querySelectorAll("[data-formset-add]").forEach(function (button) {
            button.addEventListener("click", function () {
                addFormsetRow(button.dataset.formsetAdd);
            });
        });
        wireRemoveButtons(scope);
        wireIndicativeAge(scope);
    }

    return {
        init,
        formatAgeFromBirthDate,
    };
})();

document.addEventListener("DOMContentLoaded", function () {
    if (window.ArborisFamiglieInteressateForm) {
        window.ArborisFamiglieInteressateForm.init(document);
    }
});
