(function () {
    function setDisabled(input, disabled) {
        if (!input) {
            return;
        }
        input.disabled = disabled;
        input.closest("td")?.classList.toggle("is-disabled-field", disabled);
    }

    function initMovementForm(form) {
        const channel = form.querySelector("#id_canale");
        const affectsBalance = form.querySelector("#id_incide_su_saldo_banca");
        const thirdParty = form.querySelector("#id_sostenuta_da_terzi");
        const thirdPartyRows = form.querySelectorAll("[data-third-party-row], [data-third-party-detail-row]");

        if (!channel || !thirdParty) {
            return;
        }

        function updateState() {
            const isPersonal = channel.value === "personale";
            const showThirdPartyDetails = isPersonal || thirdParty.checked;

            if (isPersonal) {
                thirdParty.checked = true;
                if (affectsBalance) {
                    affectsBalance.checked = false;
                }
            }

            setDisabled(affectsBalance, isPersonal);
            thirdPartyRows.forEach(function (row) {
                row.hidden = !showThirdPartyDetails;
            });
        }

        channel.addEventListener("change", updateState);
        thirdParty.addEventListener("change", updateState);
        updateState();
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-movement-manual-form]").forEach(initMovementForm);
    });
})();
