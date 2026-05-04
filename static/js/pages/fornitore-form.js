window.ArborisFornitoreForm = (function () {
    function initViewMode() {
        const viewMode = window.ArborisViewMode;
        const modeInput = document.getElementById("fornitore-edit-scope");
        const editButton = document.getElementById("enable-edit-fornitore-btn");

        if (!viewMode || !modeInput || !editButton) {
            return;
        }

        viewMode.init({
            formId: "fornitore-detail-form",
            lockContainerId: "fornitore-main-fields",
            editButtonId: "enable-edit-fornitore-btn",
            modeInputId: "fornitore-edit-scope",
            startMode: modeInput.value || "view",
            reloadOnCancel: true,
        });
    }

    function init() {
        initViewMode();

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
