window.ArborisStudentePopupForm = (function () {
    function init() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;
        const formTools = window.ArborisAnagraficaFormTools;
        if (!relatedPopups || !familyLinkedAddress || !routes || !formTools) {
            return;
        }

        function updateButtons() {
            refreshFamigliaButtons();
            refreshIndirizzoButtons();
        }

        function bindPopupActions() {
            refreshFamigliaButtons = function () {};
            refreshIndirizzoButtons = function () {};

            const famigliaCrud = routes.wireCrudButtonsById({
                selectId: "id_famiglia",
                relatedType: "famiglia",
                addBtnId: "popup-add-famiglia-btn",
                editBtnId: "popup-edit-famiglia-btn",
                deleteBtnId: "popup-delete-famiglia-btn",
                openRelatedPopup: relatedPopups.openRelatedPopup,
            });
            refreshFamigliaButtons = famigliaCrud.refresh;

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

        const famigliaSelect = document.getElementById("id_famiglia");
        const indirizzoSelect = document.getElementById("id_indirizzo");
        let refreshFamigliaButtons = function () {};
        let refreshIndirizzoButtons = function () {};
        formTools.bindFamilyAddressController({
            familyLinkedAddress: familyLinkedAddress,
            familySelect: famigliaSelect,
            addressSelect: indirizzoSelect,
            surnameInput: document.getElementById("id_cognome"),
            helpElement: document.getElementById("popup-studente-address-help"),
            fallbackLabelScriptId: "popup-studente-famiglia-indirizzo-label",
            onRefreshButtons: updateButtons,
        });

        bindPopupActions();
        updateButtons();
    }

    return {
        init,
    };
})();
