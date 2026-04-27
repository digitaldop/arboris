window.ArborisFornitoreForm = (function () {
    function init() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!routes || !relatedPopups) {
            return;
        }

        routes.wireCrudButtonsById({
            selectId: "id_categoria_spesa",
            relatedType: "categoria_spesa",
            addBtnId: "add-categoria-spesa-btn",
            editBtnId: "edit-categoria-spesa-btn",
            deleteBtnId: "delete-categoria-spesa-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
    }

    return {
        init,
    };
})();
