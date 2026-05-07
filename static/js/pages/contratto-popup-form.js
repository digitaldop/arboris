window.ArborisContrattoPopupForm = (function () {
    function init() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!relatedPopups || !routes) {
            return;
        }

        routes.wireCrudButtonsById({
            selectId: "id_tipo_contratto",
            relatedType: "tipo_contratto",
            addBtnId: "popup-add-tipo-contratto-btn",
            editBtnId: "popup-edit-tipo-contratto-btn",
            deleteBtnId: "popup-delete-tipo-contratto-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });

        routes.wireCrudButtonsById({
            selectId: "id_parametro_calcolo",
            relatedType: "parametro_calcolo",
            addBtnId: "popup-add-parametro-calcolo-btn",
            editBtnId: "popup-edit-parametro-calcolo-btn",
            deleteBtnId: "popup-delete-parametro-calcolo-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
    }

    return {
        init,
    };
})();
