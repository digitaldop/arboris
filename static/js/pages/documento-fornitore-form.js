window.ArborisDocumentoFornitoreForm = (function () {
    const MONEY_FIELDS = {
        imponibile: "id_imponibile",
        aliquotaIva: "id_aliquota_iva",
        iva: "id_iva",
        totale: "id_totale",
        imponibileRitenuta: "id_imponibile_ritenuta_acconto",
        aliquotaRitenuta: "id_aliquota_ritenuta_acconto",
        ritenuta: "id_ritenuta_acconto",
    };

    function parseNumber(value) {
        if (window.ArborisCurrencyFields && typeof ArborisCurrencyFields.parseNumber === "function") {
            return ArborisCurrencyFields.parseNumber(value);
        }
        const raw = String(value || "").trim().replace(/\s/g, "");
        let normalized = raw;
        if (normalized.includes(",")) {
            normalized = normalized.replace(/\./g, "").replace(",", ".");
        } else if (normalized.includes(".")) {
            const parts = normalized.split(".");
            const lastPart = parts[parts.length - 1] || "";
            if (parts.length > 2 || lastPart.length === 3) {
                normalized = normalized.replace(/\./g, "");
            }
        }
        const parsed = Number.parseFloat(normalized);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function formatMoney(value) {
        if (window.ArborisCurrencyFields && typeof ArborisCurrencyFields.formatValue === "function") {
            return ArborisCurrencyFields.formatValue(value);
        }
        if (!Number.isFinite(value)) {
            return "";
        }
        return value.toFixed(2);
    }

    function setValue(field, value) {
        if (!field) {
            return;
        }
        field.value = formatMoney(value);
        field.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function computeNetPayable() {
        const totale = document.getElementById(MONEY_FIELDS.totale);
        const ritenuta = document.getElementById(MONEY_FIELDS.ritenuta);
        const gross = parseNumber(totale?.value) || 0;
        const withholding = parseNumber(ritenuta?.value) || 0;
        return Math.max(gross - withholding, 0);
    }

    function updateNetPayablePreview() {
        document.querySelectorAll("[data-supplier-net-payable-preview]").forEach(function (node) {
            node.textContent = `EUR ${formatMoney(computeNetPayable())}`;
        });
    }

    function syncFirstDeadlineWithNetPayable() {
        const field = document.querySelector("#scadenze-fornitore-table tbody .inline-form-row [name$='-importo_previsto']");
        if (!field || field.dataset.userEdited === "1") {
            return;
        }
        const currentValue = (field.value || "").trim();
        if (currentValue && field.dataset.autoNetPayable !== "1") {
            return;
        }
        const netPayable = computeNetPayable();
        if (netPayable <= 0) {
            return;
        }
        field.dataset.autoNetPayable = "1";
        setValue(field, netPayable);
    }

    function refreshNetPayable() {
        updateNetPayablePreview();
        syncFirstDeadlineWithNetPayable();
    }

    function initDocumentTotals() {
        const imponibile = document.getElementById(MONEY_FIELDS.imponibile);
        const aliquotaIva = document.getElementById(MONEY_FIELDS.aliquotaIva);
        const iva = document.getElementById(MONEY_FIELDS.iva);
        const totale = document.getElementById(MONEY_FIELDS.totale);
        const imponibileRitenuta = document.getElementById(MONEY_FIELDS.imponibileRitenuta);
        const aliquotaRitenuta = document.getElementById(MONEY_FIELDS.aliquotaRitenuta);
        const ritenuta = document.getElementById(MONEY_FIELDS.ritenuta);

        if (!imponibile || !aliquotaIva || !iva || !totale) {
            return;
        }

        function getAliquota() {
            return parseNumber(aliquotaIva.value) || 0;
        }

        function calculateFromNet() {
            const net = parseNumber(imponibile.value);
            if (net === null) {
                return;
            }
            const tax = net * getAliquota() / 100;
            setValue(iva, tax);
            setValue(totale, net + tax);
            refreshNetPayable();
        }

        function calculateFromGross() {
            const gross = parseNumber(totale.value);
            if (gross === null) {
                return;
            }
            const multiplier = 1 + (getAliquota() / 100);
            const net = multiplier === 0 ? gross : gross / multiplier;
            const tax = gross - net;
            setValue(imponibile, net);
            setValue(iva, tax);
            refreshNetPayable();
        }

        function calculateWithholding() {
            if (!imponibileRitenuta || !aliquotaRitenuta || !ritenuta) {
                refreshNetPayable();
                return;
            }
            const withholdingBase = parseNumber(imponibileRitenuta.value);
            if (withholdingBase === null) {
                refreshNetPayable();
                return;
            }
            const withholdingRate = parseNumber(aliquotaRitenuta.value) || 0;
            setValue(ritenuta, withholdingBase * withholdingRate / 100);
            refreshNetPayable();
        }

        imponibile.addEventListener("input", calculateFromNet);
        aliquotaIva.addEventListener("input", function () {
            if ((imponibile.value || "").trim()) {
                calculateFromNet();
            } else if ((totale.value || "").trim()) {
                calculateFromGross();
            }
        });
        totale.addEventListener("input", calculateFromGross);
        totale.addEventListener("change", refreshNetPayable);
        if (imponibileRitenuta) {
            imponibileRitenuta.addEventListener("input", calculateWithholding);
        }
        if (aliquotaRitenuta) {
            aliquotaRitenuta.addEventListener("input", calculateWithholding);
        }
        if (ritenuta) {
            ritenuta.addEventListener("input", refreshNetPayable);
        }
        refreshNetPayable();
    }

    function isoToday() {
        const now = new Date();
        const month = String(now.getMonth() + 1).padStart(2, "0");
        const day = String(now.getDate()).padStart(2, "0");
        return `${now.getFullYear()}-${month}-${day}`;
    }

    function computeDeadlineStatus(row) {
        const previsto = parseNumber(row.querySelector('[name$="-importo_previsto"]')?.value) || 0;
        const pagato = parseNumber(row.querySelector('[name$="-importo_pagato"]')?.value) || 0;
        const dataScadenza = row.querySelector('[name$="-data_scadenza"]')?.value || "";

        if (previsto > 0 && pagato >= previsto) {
            return "pagata";
        }
        if (pagato > 0) {
            return "parzialmente_pagata";
        }
        if (dataScadenza && dataScadenza < isoToday()) {
            return "scaduta";
        }
        return "prevista";
    }

    function bindDeadlineStatus(row) {
        if (!row || row.dataset.deadlineStatusBound === "1") {
            return;
        }
        row.dataset.deadlineStatusBound = "1";

        const status = row.querySelector('[name$="-stato"]');
        if (!status) {
            return;
        }

        let internalChange = false;
        function applyAutoStatus() {
            if (status.dataset.userOverride === "1") {
                return;
            }
            const nextStatus = computeDeadlineStatus(row);
            if (status.value !== nextStatus) {
                internalChange = true;
                status.value = nextStatus;
                status.dispatchEvent(new Event("change", { bubbles: true }));
                internalChange = false;
            }
        }

        status.addEventListener("change", function () {
            if (!internalChange) {
                status.dataset.userOverride = "1";
            }
        });

        row.querySelectorAll('[name$="-data_scadenza"], [name$="-importo_previsto"], [name$="-importo_pagato"]').forEach(function (field) {
            field.addEventListener("input", applyAutoStatus);
            field.addEventListener("change", applyAutoStatus);
        });

        const importoPrevisto = row.querySelector('[name$="-importo_previsto"]');
        if (importoPrevisto) {
            importoPrevisto.addEventListener("input", function () {
                importoPrevisto.dataset.userEdited = "1";
            });
        }
    }

    function rowBundleFromButton(button) {
        const row = button.closest(".inline-form-row");
        if (!row) {
            return [];
        }
        const rows = [row];
        const next = row.nextElementSibling;
        if (next && next.classList.contains("supplier-deadline-note-row")) {
            rows.push(next);
        }
        return rows;
    }

    function bindRemoveButtons(root) {
        (root || document).querySelectorAll("[data-inline-remove], [data-inline-delete-existing]").forEach(function (button) {
            if (button.dataset.deadlineRemoveBound === "1") {
                return;
            }
            button.dataset.deadlineRemoveBound = "1";
            button.addEventListener("click", function () {
                const rows = rowBundleFromButton(button);
                if (button.dataset.inlineDeleteExisting === "1") {
                    const checkbox = rows[0]?.querySelector('input[type="checkbox"][name$="-DELETE"]');
                    if (checkbox) {
                        checkbox.checked = true;
                    }
                    rows.forEach(function (row) {
                        row.classList.add("is-hidden");
                    });
                    return;
                }
                rows.forEach(function (row) {
                    row.remove();
                });
            });
        });
    }

    function refreshDynamicControls(root) {
        if (window.ArborisCurrencyFields) {
            ArborisCurrencyFields.init(root || document);
        }
        if (window.ArborisFamigliaAutocomplete) {
            ArborisFamigliaAutocomplete.init(root || document);
            ArborisFamigliaAutocomplete.refresh(root || document);
        }
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (routes && relatedPopups) {
            routes.wireInlineRelatedButtons(root || document, {
                openRelatedPopup: relatedPopups.openRelatedPopup,
            });
        }
        (root || document).querySelectorAll("#scadenze-fornitore-table tbody .inline-form-row").forEach(bindDeadlineStatus);
        bindRemoveButtons(root || document);
        syncFirstDeadlineWithNetPayable();
    }

    function initRelatedPopups() {
        const routes = window.ArborisRelatedEntityRoutes;
        const relatedPopups = routes && routes.initRelatedPopups();
        if (!routes || !relatedPopups) {
            return;
        }

        routes.wireCrudButtonsById({
            selectId: "id_fornitore",
            relatedType: "fornitore",
            addBtnId: "add-fornitore-btn",
            editBtnId: "edit-fornitore-btn",
            deleteBtnId: "delete-fornitore-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
        routes.wireCrudButtonsById({
            selectId: "id_categoria_spesa",
            relatedType: "categoria_spesa",
            addBtnId: "add-documento-categoria-spesa-btn",
            editBtnId: "edit-documento-categoria-spesa-btn",
            deleteBtnId: "delete-documento-categoria-spesa-btn",
            openRelatedPopup: relatedPopups.openRelatedPopup,
        });
    }

    function initInlineFormset() {
        const addButton = document.getElementById("add-scadenza-fornitore");
        if (addButton && window.ArborisInlineFormsets) {
            addButton.addEventListener("click", function (event) {
                event.preventDefault();
                const result = ArborisInlineFormsets.mountInlineForm("scadenze", {
                    tableId: "scadenze-fornitore-table",
                    templateId: "scadenze-fornitore-empty-form-template",
                    companionClasses: ["supplier-deadline-note-row"],
                    onAfterMount: function (state) {
                        state.bundle.forEach(function (row) {
                            refreshDynamicControls(row);
                        });
                    },
                });
                if (!result) {
                    refreshDynamicControls(document);
                }
            });
        }
    }

    function init() {
        initDocumentTotals();
        initRelatedPopups();
        initInlineFormset();
        refreshDynamicControls(document);
    }

    return {
        init,
    };
})();
