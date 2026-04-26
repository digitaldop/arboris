window.ArborisDipendenteForm = (function () {
    function init(config) {
        const dipRoutes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = dipRoutes && dipRoutes.initRelatedPopups();
        if (!relatedPopups || !dipRoutes) {
            return;
        }

        const contrattoSelect = document.getElementById("id_contratto");

        dipRoutes.wireCrudButtonsById({
            selectId: "id_indirizzo",
            relatedType: "indirizzo",
            addBtnId: "add-indirizzo-btn",
            editBtnId: "edit-indirizzo-btn",
            deleteBtnId: "delete-indirizzo-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });

        dipRoutes.wireCustomCrudButtonsById({
            select: contrattoSelect,
            addBtnId: "add-contratto-btn",
            editBtnId: "edit-contratto-btn",
            deleteBtnId: "delete-contratto-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
            bindKey: contrattoSelect ? `contratto_dipendente:${contrattoSelect.name}` : "contratto_dipendente:id_contratto",
            addUrl: function () {
                let url = dipRoutes.withPopupQuery(config.urls.creaContratto, contrattoSelect ? contrattoSelect.name : "contratto");
                if (config.dipendenteId) {
                    url += `&dipendente=${encodeURIComponent(config.dipendenteId)}`;
                }
                return url;
            },
            editUrl: function (selectedId) {
                return dipRoutes.withPopupQuery(
                    dipRoutes.substituteId(config.urls.modificaContrattoTemplate, selectedId),
                    contrattoSelect ? contrattoSelect.name : "contratto"
                );
            },
            deleteUrl: function (selectedId) {
                return dipRoutes.withPopupQuery(
                    dipRoutes.substituteId(config.urls.eliminaContrattoTemplate, selectedId),
                    contrattoSelect ? contrattoSelect.name : "contratto"
                );
            },
        });
    }

    return { init };
})();
