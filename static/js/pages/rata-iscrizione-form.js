window.ArborisRataIscrizioneForm = (function () {
    function initSearchableSelects() {
        if (!window.ArborisFamigliaAutocomplete || typeof ArborisFamigliaAutocomplete.init !== "function") {
            return;
        }

        ArborisFamigliaAutocomplete.init(document);

        if (typeof ArborisFamigliaAutocomplete.refresh === "function") {
            ArborisFamigliaAutocomplete.refresh(document);
        }
    }

    function initRelatedPopups() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!routes || !relatedPopups) {
            return;
        }

        routes.wireCrudButtonsById({
            selectId: "id_metodo_pagamento",
            relatedType: "metodo_pagamento",
            addBtnId: "detail-add-metodo-pagamento-btn",
            editBtnId: "detail-edit-metodo-pagamento-btn",
            deleteBtnId: "detail-delete-metodo-pagamento-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
            onRefresh: function () {
                if (
                    window.ArborisFamigliaAutocomplete &&
                    typeof ArborisFamigliaAutocomplete.refresh === "function"
                ) {
                    ArborisFamigliaAutocomplete.refresh(document);
                }
            },
        });
    }

    function init() {
        initSearchableSelects();
        initRelatedPopups();
    }

    return {
        init,
    };
})();
