window.ArborisRateRecalcActions = (function () {
    function getRateRecalcDialog() {
        let overlay = document.getElementById("rate-recalc-dialog-overlay");

        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = "rate-recalc-dialog-overlay";
            overlay.className = "app-dialog-overlay is-hidden";
            overlay.innerHTML = `
                <div class="app-dialog" role="dialog" aria-modal="true" aria-labelledby="rate-recalc-dialog-title">
                    <div class="app-dialog-header">
                        <h2 class="app-dialog-title" id="rate-recalc-dialog-title">Conferma ricalcolo rate</h2>
                    </div>
                    <div class="app-dialog-body">
                        <p class="app-dialog-message">
                            Le rate senza pagamenti o movimenti potranno essere rigenerate.
                        </p>
                        <label class="app-dialog-field-label" for="rate-recalc-dialog-input">
                            Per confermare, digita <strong>RICALCOLA</strong>
                        </label>
                        <input
                            type="text"
                            id="rate-recalc-dialog-input"
                            class="app-dialog-input"
                            autocomplete="off"
                            spellcheck="false"
                        >
                        <label class="app-dialog-confirm-check" for="rate-recalc-dialog-second-confirm">
                            <input
                                type="checkbox"
                                id="rate-recalc-dialog-second-confirm"
                            >
                            <span>Confermo il ricalcolo del piano rate</span>
                        </label>
                    </div>
                    <div class="app-dialog-actions">
                        <button type="button" class="btn btn-secondary" data-rate-dialog-cancel="1">Annulla</button>
                        <button type="button" class="btn btn-rate-recalc" data-rate-dialog-confirm="1" disabled>Ricalcola rate</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
        }

        const input = overlay.querySelector("#rate-recalc-dialog-input");
        const secondConfirm = overlay.querySelector("#rate-recalc-dialog-second-confirm");
        const confirmButton = overlay.querySelector('[data-rate-dialog-confirm="1"]');
        const cancelButton = overlay.querySelector('[data-rate-dialog-cancel="1"]');
        let resolver = null;

        function syncConfirmState() {
            confirmButton.disabled = (input.value || "").trim().toUpperCase() !== "RICALCOLA" || !secondConfirm.checked;
        }

        function closeDialog(confirmed) {
            if (!resolver) {
                return;
            }

            overlay.classList.add("is-hidden");
            document.body.classList.remove("app-dialog-open");
            input.value = "";
            secondConfirm.checked = false;
            syncConfirmState();

            const resolve = resolver;
            resolver = null;
            resolve(Boolean(confirmed));
        }

        if (!overlay.dataset.boundRateDialog) {
            overlay.dataset.boundRateDialog = "1";

            input.addEventListener("input", syncConfirmState);
            secondConfirm.addEventListener("change", syncConfirmState);
            input.addEventListener("keydown", function (event) {
                if (event.key === "Enter" && !confirmButton.disabled) {
                    event.preventDefault();
                    closeDialog(true);
                }
            });

            cancelButton.addEventListener("click", function () {
                closeDialog(false);
            });

            confirmButton.addEventListener("click", function () {
                if (confirmButton.disabled) {
                    return;
                }
                closeDialog(true);
            });

            overlay.addEventListener("click", function (event) {
                if (event.target === overlay) {
                    closeDialog(false);
                }
            });

            document.addEventListener("keydown", function (event) {
                if (overlay.classList.contains("is-hidden")) {
                    return;
                }

                if (event.key === "Escape") {
                    event.preventDefault();
                    closeDialog(false);
                }
            });
        }

        return {
            open: function () {
                input.value = "";
                syncConfirmState();
                overlay.classList.remove("is-hidden");
                document.body.classList.add("app-dialog-open");

                return new Promise(resolve => {
                    resolver = resolve;
                    window.setTimeout(function () {
                        input.focus();
                        input.select();
                    }, 0);
                });
            },
        };
    }

    function submitRateRecalc(button) {
        const actionUrl = button.dataset.actionUrl;
        if (!actionUrl) {
            return;
        }

        const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        const csrfToken = csrfInput ? csrfInput.value : "";

        const form = document.createElement("form");
        form.method = "post";
        form.action = actionUrl;
        form.style.display = "none";

        if (csrfToken) {
            const csrfField = document.createElement("input");
            csrfField.type = "hidden";
            csrfField.name = "csrfmiddlewaretoken";
            csrfField.value = csrfToken;
            form.appendChild(csrfField);
        }

        const nextUrl = button.dataset.nextUrl;
        if (nextUrl) {
            const nextField = document.createElement("input");
            nextField.type = "hidden";
            nextField.name = "next";
            nextField.value = nextUrl;
            form.appendChild(nextField);
        }

        document.body.appendChild(form);
        form.submit();
    }

    function init(container) {
        const rateRecalcDialog = getRateRecalcDialog();

        (container || document).querySelectorAll('[data-rate-recalc-form="1"]').forEach(button => {
            if (button.dataset.boundRateRecalc === "1") {
                return;
            }

            button.dataset.boundRateRecalc = "1";
            button.addEventListener("click", function () {
                rateRecalcDialog.open().then(function (confirmed) {
                    if (!confirmed) {
                        return;
                    }

                    submitRateRecalc(button);
                });
            });
        });
    }

    return {
        init,
    };
})();
