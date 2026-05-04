window.ArborisImportEstrattoConto = (function () {
    function initSearchableSelects() {
        if (window.ArborisFamigliaAutocomplete && typeof ArborisFamigliaAutocomplete.init === "function") {
            ArborisFamigliaAutocomplete.init(document);
        }
    }

    function initRelatedPopups() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!routes || !relatedPopups) {
            return;
        }

        routes.wireCrudButtonsGroup(
            [
                {
                    selectId: "id_conto",
                    relatedType: "conto_bancario",
                    addBtnId: "add-import-conto-btn",
                    editBtnId: "edit-import-conto-btn",
                    deleteBtnId: "delete-import-conto-btn",
                },
                {
                    selectId: "confirm-import-conto",
                    relatedType: "conto_bancario",
                    addBtnId: "add-confirm-import-conto-btn",
                    editBtnId: "edit-confirm-import-conto-btn",
                    deleteBtnId: "delete-confirm-import-conto-btn",
                    targetInputName: "confirm-import-conto",
                },
            ],
            {
                openRelatedPopup: relatedPopups.openRelatedPopup,
            }
        );
    }

    function init() {
        initSearchableSelects();
        initRelatedPopups();
    }

    return {
        init,
    };
})();
