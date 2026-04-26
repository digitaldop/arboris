window.ArborisRataIscrizionePagamentoRapidoForm = (function () {
    function init() {
        const integrale = document.getElementById("id_pagamento_integrale");
        const parzialeRow = document.getElementById("pagamento-parziale-row");
        const importoInput = document.getElementById("id_importo_pagato_personalizzato");

        function refreshState() {
            const isFull = !integrale || integrale.checked;
            if (parzialeRow) {
                parzialeRow.classList.toggle("is-hidden", isFull);
            }
            if (importoInput) {
                importoInput.disabled = isFull;
                if (isFull) {
                    importoInput.value = "";
                }
            }
        }

        if (integrale) {
            integrale.addEventListener("change", refreshState);
        }
        refreshState();

        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!routes || !relatedPopups) {
            return;
        }

        routes.wireCrudButtonsById({
            selectId: "id_metodo_pagamento",
            relatedType: "metodo_pagamento",
            addBtnId: "add-metodo-pagamento-btn",
            editBtnId: "edit-metodo-pagamento-btn",
            deleteBtnId: "delete-metodo-pagamento-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
    }

    return {
        init,
    };
})();
