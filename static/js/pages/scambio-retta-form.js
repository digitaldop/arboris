window.ArborisScambioRettaForm = (function () {
    function init() {
        const familiareSelect = document.getElementById("id_familiare");
        const famigliaSelect = document.getElementById("id_famiglia");
        const studenteSelect = document.getElementById("id_studente");
        const oreInput = document.getElementById("id_ore_lavorate");
        const tariffaSelect = document.getElementById("id_tariffa_scambio_retta");
        const importoPreview = document.getElementById("scambio-retta-importo-preview");

        if (!familiareSelect || !famigliaSelect || !studenteSelect || !oreInput || !tariffaSelect || !importoPreview) {
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

        function getSelectedOption(select) {
            return select.options[select.selectedIndex] || null;
        }

        function syncFamilyFromFamiliare() {
            const selectedOption = getSelectedOption(familiareSelect);
            const famigliaId = selectedOption ? selectedOption.dataset.famigliaId || "" : "";

            if (famigliaId) {
                famigliaSelect.value = famigliaId;
            }
        }

        function filterFamiliariByFamiglia() {
            const famigliaId = famigliaSelect.value;
            let hasSelectedVisibleOption = false;

            Array.from(familiareSelect.options).forEach(option => {
                if (!option.value) {
                    option.hidden = false;
                    option.disabled = false;
                    return;
                }

                const isVisible = !famigliaId || option.dataset.famigliaId === famigliaId;
                option.hidden = !isVisible;
                option.disabled = !isVisible;

                if (isVisible && option.selected) {
                    hasSelectedVisibleOption = true;
                }
            });

            if (familiareSelect.value && !hasSelectedVisibleOption) {
                familiareSelect.value = "";
            }
        }

        function filterStudentiByFamiglia() {
            const famigliaId = famigliaSelect.value;
            let hasSelectedVisibleOption = false;

            Array.from(studenteSelect.options).forEach(option => {
                if (!option.value) {
                    option.hidden = false;
                    option.disabled = false;
                    return;
                }

                const isVisible = !famigliaId || option.dataset.famigliaId === famigliaId;
                option.hidden = !isVisible;
                option.disabled = !isVisible;

                if (isVisible && option.selected) {
                    hasSelectedVisibleOption = true;
                }
            });

            if (studenteSelect.value && !hasSelectedVisibleOption) {
                studenteSelect.value = "";
            }
        }

        function refreshImportoPreview() {
            const ore = parseDecimal(oreInput.value);
            const selectedTariffa = getSelectedOption(tariffaSelect);
            const valoreOrario = selectedTariffa ? parseDecimal(selectedTariffa.dataset.valoreOrario) : 0;
            const importo = ore * valoreOrario;
            importoPreview.textContent = formatCurrency(importo);
        }

        familiareSelect.addEventListener("change", function () {
            syncFamilyFromFamiliare();
            filterFamiliariByFamiglia();
            filterStudentiByFamiglia();
        });

        famigliaSelect.addEventListener("change", function () {
            filterFamiliariByFamiglia();
            filterStudentiByFamiglia();
        });
        oreInput.addEventListener("input", refreshImportoPreview);
        tariffaSelect.addEventListener("change", refreshImportoPreview);

        syncFamilyFromFamiliare();
        filterFamiliariByFamiglia();
        filterStudentiByFamiglia();
        refreshImportoPreview();
    }

    return {
        init,
    };
})();
