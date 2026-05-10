window.ArborisStudentePopupForm = (function () {
    function init() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!relatedPopups || !routes) {
            return;
        }

        function updateButtons() {
            refreshIndirizzoButtons();
        }

        function bindPopupActions() {
            refreshIndirizzoButtons = function () {};

            const indirizzoCrud = routes.wireCrudButtonsById({
                selectId: "id_indirizzo",
                relatedType: "indirizzo",
                addBtnId: "popup-add-indirizzo-btn",
                editBtnId: "popup-edit-indirizzo-btn",
                deleteBtnId: "popup-delete-indirizzo-btn",
                openRelatedPopup: relatedPopups.openRelatedPopup,
            });
            refreshIndirizzoButtons = indirizzoCrud.refresh;
        }

        let refreshIndirizzoButtons = function () {};

        bindPopupActions();
        updateButtons();
    }

    return {
        init,
    };
})();
