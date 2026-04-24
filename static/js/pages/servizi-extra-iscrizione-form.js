window.ArborisServiziExtraIscrizioneForm = (function () {
    function cloneOption(option) {
        const clonedOption = document.createElement("option");
        clonedOption.value = option.value;
        clonedOption.textContent = option.textContent;

        Array.from(option.attributes).forEach(function (attribute) {
            if (attribute.name.startsWith("data-")) {
                clonedOption.setAttribute(attribute.name, attribute.value);
            }
        });

        return clonedOption;
    }

    function init() {
        const servizioSelect = document.getElementById("id_servizio");
        const tariffaSelect = document.getElementById("id_tariffa");
        if (!servizioSelect || !tariffaSelect) {
            return;
        }

        const sourceOptions = Array.from(tariffaSelect.options).map(cloneOption);

        function renderTariffe() {
            const servizioId = servizioSelect.value;
            const currentTariffaId = tariffaSelect.value;
            const filteredOptions = sourceOptions.filter(function (option) {
                const optionServiceId = option.getAttribute("data-servizio-id") || "";
                return !servizioId || !option.value || optionServiceId === servizioId;
            });

            tariffaSelect.innerHTML = "";
            filteredOptions.forEach(function (option) {
                tariffaSelect.appendChild(cloneOption(option));
            });

            const stillAvailable = Array.from(tariffaSelect.options).some(function (option) {
                return option.value === currentTariffaId;
            });

            if (stillAvailable) {
                tariffaSelect.value = currentTariffaId;
                return;
            }

            const firstSelectable = Array.from(tariffaSelect.options).find(function (option) {
                return Boolean(option.value);
            });

            if (firstSelectable) {
                tariffaSelect.value = firstSelectable.value;
            }
        }

        servizioSelect.addEventListener("change", renderTariffe);
        renderTariffe();
    }

    return {
        init,
    };
})();
