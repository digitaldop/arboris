window.ArborisServiziExtraTariffaForm = (function () {
    function updateModeHelp() {
        const checkbox = document.getElementById("id_rateizzata");
        const helpNode = document.getElementById("tariffa-rate-mode-help");
        if (!checkbox || !helpNode) {
            return;
        }

        helpNode.textContent = checkbox.checked
            ? "Modalita rateizzata attiva: aggiungi tutte le scadenze necessarie nel piano qui sotto."
            : "Modalita una tantum: lascia una sola riga nel piano rate.";
    }

    function init() {
        const inlineFormsets = window.ArborisInlineFormsets;
        const addButton = document.getElementById("add-rate-config-btn");
        const checkbox = document.getElementById("id_rateizzata");
        const rateManager = inlineFormsets && inlineFormsets.createManager({
            prefix: "rate",
            tableId: "rate-config-table",
            totalFormsId: "id_rate-TOTAL_FORMS",
            templateId: "rate-config-empty-form-template",
        });

        if (!inlineFormsets || !rateManager) {
            return;
        }

        if (addButton) {
            addButton.addEventListener("click", function () {
                rateManager.add();
            });
        }

        if (checkbox) {
            checkbox.addEventListener("change", updateModeHelp);
        }

        document.addEventListener("click", function (event) {
            const removeButton = event.target.closest(".js-remove-rate-row");
            if (!removeButton) {
                return;
            }

            rateManager.remove(removeButton);
        });

        updateModeHelp();
    }

    return {
        init,
    };
})();
