window.ArborisContrattoPopupForm = (function () {
    const tipoContrattoFieldMap = {
        "parametro_calcolo": "parametroCalcolo",
        "ccnl": "ccnl",
        "livello": "livello",
        "qualifica": "qualifica",
        "mansione": "mansione",
        "regime_orario": "regimeOrario",
        "ore_settimanali": "oreSettimanali",
        "percentuale_part_time": "percentualePartTime",
        "retribuzione_lorda_mensile": "retribuzioneLordaMensile",
        "tariffa_oraria": "tariffaOraria",
        "superminimo_mensile": "superminimoMensile",
        "indennita_fisse_mensili": "indennitaFisseMensili",
        "mensilita_annue": "mensilitaAnnue",
        "costo_azienda_ipotizzato": "costoAziendaIpotizzato",
        "lordo_ipotizzato": "lordoIpotizzato",
        "netto_ipotizzato": "nettoIpotizzato",
        "contributi_mensili_ipotizzati": "contributiMensiliIpotizzati",
        "valuta": "valuta",
    };

    function findField(fieldName) {
        return document.querySelector(`[name="${fieldName}"]`);
    }

    function markEditableFields() {
        Object.keys(tipoContrattoFieldMap).forEach(function (fieldName) {
            const field = findField(fieldName);
            if (!field) {
                return;
            }
            ["input", "change"].forEach(function (eventName) {
                field.addEventListener(eventName, function () {
                    if (field.dataset.contractProgrammatic === "1") {
                        return;
                    }
                    field.dataset.contractUserEdited = "1";
                });
            });
        });
    }

    function setFieldFromTipo(fieldName, value) {
        if (value === undefined || value === null || value === "") {
            return;
        }

        const field = findField(fieldName);
        if (!field || field.dataset.contractUserEdited === "1") {
            return;
        }

        if (field.tagName === "SELECT") {
            const hasOption = Array.from(field.options || []).some(function (option) {
                return option.value === String(value);
            });
            if (!hasOption) {
                return;
            }
        }

        field.dataset.contractProgrammatic = "1";
        field.value = String(value);
        field.dispatchEvent(new Event("change", { bubbles: true }));
        delete field.dataset.contractProgrammatic;
    }

    function applySelectedTipoDefaults(select) {
        if (!select) {
            return;
        }
        const option = select.options[select.selectedIndex];
        if (!option) {
            return;
        }

        Object.keys(tipoContrattoFieldMap).forEach(function (fieldName) {
            setFieldFromTipo(fieldName, option.dataset[tipoContrattoFieldMap[fieldName]]);
        });
    }

    function initTipoContrattoDefaults() {
        const select = document.getElementById("id_tipo_contratto");
        if (!select) {
            return;
        }

        markEditableFields();
        select.addEventListener("change", function () {
            applySelectedTipoDefaults(select);
        });
    }

    function init() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!relatedPopups || !routes) {
            initTipoContrattoDefaults();
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

        initTipoContrattoDefaults();
    }

    return {
        init,
    };
})();
