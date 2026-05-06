window.ArborisScambioRettaForm = (function () {
    function init() {
        const familiareSelect = document.getElementById("id_familiare");
        const famigliaSelect = document.getElementById("id_famiglia");
        const famigliaDisplay = document.getElementById("scambio-retta-famiglia-display");
        const studenteSelect = document.getElementById("id_studente");
        const oreInput = document.getElementById("id_ore_lavorate");
        const tariffaSelect = document.getElementById("id_tariffa_scambio_retta");
        const importoPreview = document.getElementById("scambio-retta-importo-preview");
        const form = document.getElementById("scambio-detail-form");

        if (!familiareSelect || !famigliaSelect || !famigliaDisplay || !studenteSelect || !oreInput || !tariffaSelect || !importoPreview) {
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

        function syncFamilyFromFamiliare() {
            const selectedOption = getSelectedOption(familiareSelect);
            const famigliaId = selectedOption ? selectedOption.dataset.famigliaId || "" : "";
            const famigliaLabel = selectedOption ? selectedOption.dataset.famigliaLabel || "" : "";

            if (famigliaSelect.value !== famigliaId) {
                famigliaSelect.value = famigliaId;
                notifySelectChanged(famigliaSelect);
            }

            famigliaDisplay.value = famigliaLabel;
        }

        function filterStudentiByFamiglia() {
            const famigliaId = famigliaSelect.value;
            const hasFamily = Boolean(famigliaId);
            let hasSelectedVisibleOption = false;

            Array.from(studenteSelect.options).forEach(option => {
                if (!option.value) {
                    option.hidden = false;
                    option.disabled = false;
                    return;
                }

                const isVisible = hasFamily && option.dataset.famigliaId === famigliaId;
                option.hidden = !isVisible;
                option.disabled = !isVisible;

                if (isVisible && option.selected) {
                    hasSelectedVisibleOption = true;
                }
            });

            if (studenteSelect.value && !hasSelectedVisibleOption) {
                studenteSelect.value = "";
            }

            studenteSelect.disabled = !hasFamily || isViewModeLocked();
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
            syncFamilyFromFamiliare();
            filterStudentiByFamiglia();
        });

        famigliaSelect.addEventListener("change", function () {
            filterStudentiByFamiglia();
        });
        oreInput.addEventListener("input", refreshImportoPreview);
        tariffaSelect.addEventListener("change", refreshImportoPreview);
        if (form) {
            form.addEventListener("arboris:view-mode-change", filterStudentiByFamiglia);
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

        syncFamilyFromFamiliare();
        filterStudentiByFamiglia();
        refreshImportoPreview();
    }

    return {
        init,
    };
})();
