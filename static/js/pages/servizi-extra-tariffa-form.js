window.ArborisServiziExtraTariffaForm = (function () {
    function removeInlineRow(button) {
        const row = button.closest("tr");
        if (row) {
            row.remove();
        }
    }

    function addInlineForm() {
        const totalForms = document.getElementById("id_rate-TOTAL_FORMS");
        const template = document.getElementById("rate-config-empty-form-template");
        const tbody = document.querySelector("#rate-config-table tbody");

        if (!totalForms || !template || !tbody) {
            return;
        }

        const currentIndex = parseInt(totalForms.value, 10);
        const newRowHtml = template.innerHTML.replace(/__prefix__/g, currentIndex);
        tbody.insertAdjacentHTML("beforeend", newRowHtml);
        totalForms.value = currentIndex + 1;
    }

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
        const addButton = document.getElementById("add-rate-config-btn");
        const checkbox = document.getElementById("id_rateizzata");

        if (addButton) {
            addButton.addEventListener("click", addInlineForm);
        }

        if (checkbox) {
            checkbox.addEventListener("change", updateModeHelp);
        }

        document.addEventListener("click", function (event) {
            const removeButton = event.target.closest(".js-remove-rate-row");
            if (!removeButton) {
                return;
            }

            removeInlineRow(removeButton);
        });

        updateModeHelp();
    }

    return {
        init,
    };
})();

