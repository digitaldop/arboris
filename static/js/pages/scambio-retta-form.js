window.ArborisScambioRettaForm = (function () {
    function init() {
        const familiareSelect = document.getElementById("id_familiare");
        const studenteSelect = document.getElementById("id_studente");
        const oreInput = document.getElementById("id_ore_lavorate");
        const tariffaSelect = document.getElementById("id_tariffa_scambio_retta");
        const importoPreview = document.getElementById("scambio-retta-importo-preview");
        const form = document.getElementById("scambio-detail-form");

        if (!familiareSelect || !studenteSelect || !oreInput || !tariffaSelect || !importoPreview) {
            return;
        }

        function parseDecimal(value) {
            const parsed = parseFloat(String(value || "").replace(",", "."));
            return Number.isFinite(parsed) ? parsed : 0;
        }

        function formatCurrency(value) {
            return value.toLocaleString("it-IT", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
        }

        function parseLastDecimalFromText(value) {
            const matches = String(value || "").match(/\d+(?:[.,]\d+)?/g);
            if (!matches || !matches.length) {
                return 0;
            }
            return parseDecimal(matches[matches.length - 1]);
        }

        function getSelectedOption(select) {
            return select.options[select.selectedIndex] || null;
        }

        function isViewModeLocked() {
            return Boolean(form && form.classList.contains("is-view-mode"));
        }

        function notifySelectChanged(select) {
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }

        function csvIncludes(csvValue, needle) {
            if (!csvValue || !needle) {
                return false;
            }
            return String(csvValue)
                .split(",")
                .map(value => value.trim())
                .filter(Boolean)
                .includes(String(needle));
        }

        function filterStudentiByFamiliare() {
            const selectedFamiliareOption = getSelectedOption(familiareSelect);
            const selectedStudentIds = selectedFamiliareOption ? selectedFamiliareOption.dataset.studenteIds || "" : "";
            const hasDirectStudents = Boolean(selectedStudentIds);
            let hasSelectedVisibleOption = false;

            Array.from(studenteSelect.options).forEach(option => {
                if (!option.value) {
                    option.hidden = false;
                    option.disabled = false;
                    return;
                }

                const isVisible = hasDirectStudents && csvIncludes(selectedStudentIds, option.value);
                option.hidden = !isVisible;
                option.disabled = !isVisible;

                if (isVisible && option.selected) {
                    hasSelectedVisibleOption = true;
                }
            });

            if (studenteSelect.value && !hasSelectedVisibleOption) {
                studenteSelect.value = "";
            }

            studenteSelect.disabled = !hasDirectStudents || isViewModeLocked();
            notifySelectChanged(studenteSelect);
        }

        function refreshImportoPreview() {
            const ore = parseDecimal(oreInput.value);
            const selectedTariffa = getSelectedOption(tariffaSelect);
            const valoreOrario = selectedTariffa
                ? parseDecimal(selectedTariffa.dataset.valoreOrario) || parseLastDecimalFromText(selectedTariffa.textContent)
                : 0;
            const importo = ore * valoreOrario;
            importoPreview.textContent = formatCurrency(importo);
        }

        familiareSelect.addEventListener("change", function () {
            filterStudentiByFamiliare();
        });
        oreInput.addEventListener("input", refreshImportoPreview);
        tariffaSelect.addEventListener("change", refreshImportoPreview);
        if (form) {
            form.addEventListener("arboris:view-mode-change", filterStudentiByFamiliare);
        }

        if (
            window.ArborisRelatedEntityRoutes &&
            typeof window.ArborisRelatedEntityRoutes.wireCrudButtonsById === "function"
        ) {
            window.ArborisRelatedEntityRoutes.wireCrudButtonsById({
                selectId: "id_tariffa_scambio_retta",
                relatedType: "tariffa_scambio_retta",
                addBtnId: "add-scambio-tariffa-btn",
                editBtnId: "edit-scambio-tariffa-btn",
                deleteBtnId: "delete-scambio-tariffa-btn",
            });
        }

        filterStudentiByFamiliare();
        refreshImportoPreview();
    }

    return {
        init,
    };
})();
