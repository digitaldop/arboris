window.ArborisStudentePopupForm = (function () {
    function init() {
        const relatedPopups = window.ArborisRelatedPopups;
        const familyLinkedAddress = window.ArborisFamilyLinkedAddress;
        if (!relatedPopups || !familyLinkedAddress) {
            return;
        }

        window.dismissRelatedPopup = relatedPopups.dismissRelatedPopup;
        window.dismissDeletedRelatedPopup = relatedPopups.dismissDeletedRelatedPopup;

        function updateButtons() {
            const famigliaSelect = document.getElementById("id_famiglia");
            const indirizzoSelect = document.getElementById("id_indirizzo");

            refreshFamigliaButtons();
            refreshIndirizzoButtons();
        }

        function bindPopupActions() {
            const famigliaSelect = document.getElementById("id_famiglia");
            const indirizzoSelect = document.getElementById("id_indirizzo");
            const routes = window.ArborisRelatedEntityRoutes;

            const addFamigliaBtn = document.getElementById("popup-add-famiglia-btn");
            const editFamigliaBtn = document.getElementById("popup-edit-famiglia-btn");
            const deleteFamigliaBtn = document.getElementById("popup-delete-famiglia-btn");
            const addIndirizzoBtn = document.getElementById("popup-add-indirizzo-btn");
            const editIndirizzoBtn = document.getElementById("popup-edit-indirizzo-btn");
            const deleteIndirizzoBtn = document.getElementById("popup-delete-indirizzo-btn");
            refreshFamigliaButtons = function () {};
            refreshIndirizzoButtons = function () {};

            if (!routes) {
                console.error("ArborisRelatedEntityRoutes non disponibile.");
                return;
            }

            if (famigliaSelect) {
                const famigliaCrud = routes.wireCrudButtons({
                    select: famigliaSelect,
                    relatedType: "famiglia",
                    addBtn: addFamigliaBtn,
                    editBtn: editFamigliaBtn,
                    deleteBtn: deleteFamigliaBtn,
                    openRelatedPopup: relatedPopups.openRelatedPopup,
                });
                refreshFamigliaButtons = famigliaCrud.refresh;
            }

            if (indirizzoSelect) {
                const indirizzoCrud = routes.wireCrudButtons({
                    select: indirizzoSelect,
                    relatedType: "indirizzo",
                    addBtn: addIndirizzoBtn,
                    editBtn: editIndirizzoBtn,
                    deleteBtn: deleteIndirizzoBtn,
                    openRelatedPopup: relatedPopups.openRelatedPopup,
                });
                refreshIndirizzoButtons = indirizzoCrud.refresh;
            }
        }

        const famigliaSelect = document.getElementById("id_famiglia");
        const indirizzoSelect = document.getElementById("id_indirizzo");
        let refreshFamigliaButtons = function () {};
        let refreshIndirizzoButtons = function () {};
        const familyLinkController = familyLinkedAddress.createController({
            familySelect: famigliaSelect,
            addressSelect: indirizzoSelect,
            surnameInput: document.getElementById("id_cognome"),
            helpElement: document.getElementById("popup-studente-address-help"),
            fallbackLabelScriptId: "popup-studente-famiglia-indirizzo-label",
            onRefreshButtons: updateButtons,
        });

        if (famigliaSelect) {
            famigliaSelect.addEventListener("change", function () {
                familyLinkController.syncFamigliaDefaults();
            });
        }

        if (indirizzoSelect) {
            indirizzoSelect.addEventListener("change", function () {
                familyLinkController.syncInheritedStateFromAddress();
            });
        }

        bindPopupActions();
        familyLinkController.syncFamigliaDefaults();
        familyLinkController.updateInheritedAddressPlaceholder();
        familyLinkController.refreshAddressHelp();
        updateButtons();
    }

    return {
        init,
    };
})();
