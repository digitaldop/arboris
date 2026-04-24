window.ArborisStudentePopupForm = (function () {
    function init() {
        const relatedPopups = window.ArborisRelatedPopups;
        if (!relatedPopups) {
            return;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        function getSelectedFamigliaOption() {
            const famigliaSelect = document.getElementById("id_famiglia");
            if (!famigliaSelect) {
                return null;
            }

            return famigliaSelect.options[famigliaSelect.selectedIndex] || null;
        }

        function getSelectedFamigliaAddressId() {
            const selectedOption = getSelectedFamigliaOption();
            return selectedOption ? (selectedOption.dataset.indirizzoFamigliaId || "") : "";
        }

        function updateInheritedAddressPlaceholder() {
            const indirizzoSelect = document.getElementById("id_indirizzo");
            if (!indirizzoSelect || !indirizzoSelect.options.length) return;

            const emptyOption = indirizzoSelect.options[0];
            if (!emptyOption) return;

            if (!indirizzoSelect.dataset.defaultEmptyLabel) {
                indirizzoSelect.dataset.defaultEmptyLabel = emptyOption.textContent;
            }

            const selectedFamily = getSelectedFamigliaOption();
            const familyAddress = selectedFamily ? selectedFamily.dataset.indirizzoFamiglia || "" : "";

            emptyOption.textContent = familyAddress || indirizzoSelect.dataset.defaultEmptyLabel;
        }

        function refreshAddressHelp() {
            const indirizzoSelect = document.getElementById("id_indirizzo");
            const help = document.getElementById("popup-studente-address-help");
            if (!indirizzoSelect || !help) return;

            const familyAddressId = getSelectedFamigliaAddressId();
            const selectedFamily = getSelectedFamigliaOption();

            if (indirizzoSelect.value && familyAddressId && indirizzoSelect.value === familyAddressId) {
                const familyAddress = selectedFamily ? selectedFamily.dataset.indirizzoFamiglia || "" : "";
                help.textContent = familyAddress
                    ? `Indirizzo famiglia: ${familyAddress}`
                    : "Indirizzo famiglia";
                return;
            }

            if (indirizzoSelect.value) {
                help.textContent = "Indirizzo specifico";
                return;
            }

            if (selectedFamily) {
                const familyAddress = selectedFamily.dataset.indirizzoFamiglia || "";
                if (familyAddress) {
                    help.textContent = `Usa indirizzo famiglia: ${familyAddress}`;
                    return;
                }
            }

            const node = document.getElementById("popup-studente-famiglia-indirizzo-label");
            let label = "";

            if (node) {
                try {
                    label = JSON.parse(node.textContent);
                } catch (e) {}
            }

            help.textContent = label
                ? `Usa indirizzo famiglia: ${label}`
                : "Se lasci vuoto, verra usato l'indirizzo principale della famiglia";
        }

        function updateButtons() {
            const famigliaSelect = document.getElementById("id_famiglia");
            const indirizzoSelect = document.getElementById("id_indirizzo");

            const editFamigliaBtn = document.getElementById("popup-edit-famiglia-btn");
            const deleteFamigliaBtn = document.getElementById("popup-delete-famiglia-btn");
            const editIndirizzoBtn = document.getElementById("popup-edit-indirizzo-btn");
            const deleteIndirizzoBtn = document.getElementById("popup-delete-indirizzo-btn");

            if (editFamigliaBtn && famigliaSelect) editFamigliaBtn.disabled = !famigliaSelect.value;
            if (deleteFamigliaBtn && famigliaSelect) deleteFamigliaBtn.disabled = !famigliaSelect.value;
            if (editIndirizzoBtn && indirizzoSelect) editIndirizzoBtn.disabled = !indirizzoSelect.value;
            if (deleteIndirizzoBtn && indirizzoSelect) deleteIndirizzoBtn.disabled = !indirizzoSelect.value;
        }

        function markInheritedAddress(indirizzoSelect, enabled) {
            if (!indirizzoSelect) {
                return;
            }

            if (enabled) {
                indirizzoSelect.dataset.inheritedAddress = "1";
            } else {
                delete indirizzoSelect.dataset.inheritedAddress;
            }
        }

        function syncFamigliaDefaults() {
            const cognomeInput = document.getElementById("id_cognome");
            const indirizzoSelect = document.getElementById("id_indirizzo");
            const selectedOption = getSelectedFamigliaOption();
            const familyAddressId = selectedOption ? (selectedOption.dataset.indirizzoFamigliaId || "") : "";
            const previousValue = indirizzoSelect ? (indirizzoSelect.value || "") : "";

            if (!selectedOption || !selectedOption.value) {
                if (indirizzoSelect && indirizzoSelect.dataset.inheritedAddress === "1" && previousValue) {
                    indirizzoSelect.value = "";
                    markInheritedAddress(indirizzoSelect, false);
                    indirizzoSelect.dispatchEvent(new Event("change", { bubbles: true }));
                }
                updateInheritedAddressPlaceholder();
                refreshAddressHelp();
                updateButtons();
                return;
            }

            if (cognomeInput) {
                cognomeInput.value = selectedOption.dataset.cognomeFamiglia || "";
            }

            if (indirizzoSelect) {
                const isInherited = indirizzoSelect.dataset.inheritedAddress === "1";
                if ((!indirizzoSelect.value || isInherited) && familyAddressId) {
                    indirizzoSelect.value = familyAddressId;
                    markInheritedAddress(indirizzoSelect, true);
                } else if (!familyAddressId && isInherited) {
                    indirizzoSelect.value = "";
                    markInheritedAddress(indirizzoSelect, false);
                }

                if ((indirizzoSelect.value || "") !== previousValue) {
                    indirizzoSelect.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }

            updateInheritedAddressPlaceholder();
            refreshAddressHelp();
            updateButtons();
        }

        function bindPopupActions() {
            const famigliaSelect = document.getElementById("id_famiglia");
            const indirizzoSelect = document.getElementById("id_indirizzo");

            const addFamigliaBtn = document.getElementById("popup-add-famiglia-btn");
            const editFamigliaBtn = document.getElementById("popup-edit-famiglia-btn");
            const deleteFamigliaBtn = document.getElementById("popup-delete-famiglia-btn");
            const addIndirizzoBtn = document.getElementById("popup-add-indirizzo-btn");
            const editIndirizzoBtn = document.getElementById("popup-edit-indirizzo-btn");
            const deleteIndirizzoBtn = document.getElementById("popup-delete-indirizzo-btn");

            if (addFamigliaBtn && famigliaSelect) {
                addFamigliaBtn.addEventListener("click", function () {
                    relatedPopups.openRelatedPopup(`/famiglie/nuovo/?popup=1&target_input_name=${encodeURIComponent(famigliaSelect.name)}`);
                });
            }

            if (editFamigliaBtn && famigliaSelect) {
                editFamigliaBtn.addEventListener("click", function () {
                    if (!famigliaSelect.value) return;
                    relatedPopups.openRelatedPopup(`/famiglie/${famigliaSelect.value}/modifica/?popup=1&target_input_name=${encodeURIComponent(famigliaSelect.name)}`);
                });
            }

            if (deleteFamigliaBtn && famigliaSelect) {
                deleteFamigliaBtn.addEventListener("click", function () {
                    if (!famigliaSelect.value) return;
                    relatedPopups.openRelatedPopup(`/famiglie/${famigliaSelect.value}/elimina/?popup=1&target_input_name=${encodeURIComponent(famigliaSelect.name)}`);
                });
            }

            if (addIndirizzoBtn && indirizzoSelect) {
                addIndirizzoBtn.addEventListener("click", function () {
                    relatedPopups.openRelatedPopup(`/indirizzi/nuovo/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
                });
            }

            if (editIndirizzoBtn && indirizzoSelect) {
                editIndirizzoBtn.addEventListener("click", function () {
                    if (!indirizzoSelect.value) return;
                    relatedPopups.openRelatedPopup(`/indirizzi/${indirizzoSelect.value}/modifica/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
                });
            }

            if (deleteIndirizzoBtn && indirizzoSelect) {
                deleteIndirizzoBtn.addEventListener("click", function () {
                    if (!indirizzoSelect.value) return;
                    relatedPopups.openRelatedPopup(`/indirizzi/${indirizzoSelect.value}/elimina/?popup=1&target_input_name=${encodeURIComponent(indirizzoSelect.name)}`);
                });
            }
        }

        const famigliaSelect = document.getElementById("id_famiglia");
        const indirizzoSelect = document.getElementById("id_indirizzo");

        if (famigliaSelect) {
            famigliaSelect.addEventListener("change", syncFamigliaDefaults);
        }

        if (indirizzoSelect) {
            indirizzoSelect.addEventListener("change", function () {
                const familyAddressId = getSelectedFamigliaAddressId();
                markInheritedAddress(indirizzoSelect, Boolean(familyAddressId && indirizzoSelect.value === familyAddressId));
                refreshAddressHelp();
                updateButtons();
            });
        }

        bindPopupActions();
        syncFamigliaDefaults();
        updateInheritedAddressPlaceholder();
        refreshAddressHelp();
        updateButtons();
    }

    return {
        init,
    };
})();
