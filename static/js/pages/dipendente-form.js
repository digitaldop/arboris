window.ArborisDipendenteForm = (function () {
    function selectedOption(select) {
        if (!select || !select.selectedOptions || !select.selectedOptions.length) {
            return null;
        }
        return select.selectedOptions[0];
    }

    function syncNazionalitaFromLuogoNascita(options) {
        const luogoNascitaSelect = document.getElementById("id_luogo_nascita");
        const nazionalitaInput = document.getElementById("id_nazionalita");

        if (!luogoNascitaSelect || !nazionalitaInput) {
            return;
        }

        if (options && options.onlyIfEmpty && nazionalitaInput.value.trim()) {
            return;
        }

        const option = selectedOption(luogoNascitaSelect);
        const nazionalita = option && option.dataset ? option.dataset.nazionalitaLabel : "";
        const fallback = nazionalitaInput.dataset.defaultNazionalitaLabel || "";
        const nextValue = nazionalita || (luogoNascitaSelect.value ? fallback : "");

        if (nextValue && nazionalitaInput.value !== nextValue) {
            nazionalitaInput.value = nextValue;
            nazionalitaInput.dispatchEvent(new Event("input", { bubbles: true }));
            nazionalitaInput.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    function initBirthplaceNationalitySync() {
        const luogoNascitaSelect = document.getElementById("id_luogo_nascita");
        if (!luogoNascitaSelect) {
            return;
        }

        luogoNascitaSelect.addEventListener("change", function () {
            syncNazionalitaFromLuogoNascita();
        });
        syncNazionalitaFromLuogoNascita({ onlyIfEmpty: true });
    }

    function dispatchFieldEvents(field) {
        if (!field) {
            return;
        }
        field.dispatchEvent(new Event("input", { bubbles: true }));
        field.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function setFieldValue(fieldId, value) {
        const field = document.getElementById(fieldId);
        if (!field) {
            return;
        }
        field.value = value || "";
        dispatchFieldEvents(field);
    }

    function setSelectValue(fieldId, value) {
        setFieldValue(fieldId, value);
        if (window.ArborisFamigliaAutocomplete) {
            ArborisFamigliaAutocomplete.refresh(document);
        }
    }

    function setAnagraphicFieldLocked(field, locked) {
        if (!field) {
            return;
        }

        const container = field.closest(".fondo-plan-field");
        if (container) {
            container.classList.toggle("ga-linked-readonly", locked);
        }

        if (field instanceof HTMLSelectElement) {
            if (locked) {
                field.dataset.lockedValue = field.value;
                field.setAttribute("aria-disabled", "true");
                field.tabIndex = -1;
            } else {
                delete field.dataset.lockedValue;
                field.removeAttribute("aria-disabled");
                field.removeAttribute("tabindex");
            }
            if (window.ArborisFamigliaAutocomplete) {
                ArborisFamigliaAutocomplete.refresh(document);
            }
            return;
        }

        if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
            field.readOnly = locked;
            field.classList.toggle("ga-linked-readonly-control", locked);
        }
    }

    function initRoleDependentFields() {
        const roleSelect = document.getElementById("id_ruolo_aziendale");
        if (!roleSelect) {
            return;
        }

        const educatorField = document.querySelector("[data-role-field='educator-class']");
        const employeeField = document.querySelector("[data-role-field='employee-mansione']");

        const update = function () {
            const role = roleSelect.value || "";
            const educatorEnabled = role === "educatore";
            const employeeEnabled = role === "dipendente";
            if (educatorField) {
                educatorField.hidden = !educatorEnabled;
                educatorField.classList.toggle("is-hidden", !educatorEnabled);
            }
            if (employeeField) {
                employeeField.hidden = !employeeEnabled;
                employeeField.classList.toggle("is-hidden", !employeeEnabled);
            }
        };

        roleSelect.addEventListener("change", update);
        update();
    }

    function initFamiliareAutofill() {
        const personaSelect = document.getElementById("id_persona_collegata");
        if (!personaSelect) {
            return;
        }

        const lockedFieldIds = [
            "id_nome",
            "id_cognome",
            "id_data_nascita",
            "id_luogo_nascita",
            "id_nazionalita",
            "id_sesso",
            "id_codice_fiscale",
            "id_indirizzo",
            "id_telefono",
            "id_email",
        ];

        const sync = function () {
            const option = selectedOption(personaSelect);
            const locked = Boolean(option && option.value);

            if (locked) {
                setFieldValue("id_nome", option.dataset.nome);
                setFieldValue("id_cognome", option.dataset.cognome);
                setFieldValue("id_data_nascita", option.dataset.dataNascita);
                setSelectValue("id_luogo_nascita", option.dataset.luogoNascitaId);
                setFieldValue("id_nazionalita", option.dataset.nazionalitaLabel);
                setSelectValue("id_sesso", option.dataset.sesso);
                setFieldValue("id_codice_fiscale", option.dataset.codiceFiscale);
                setSelectValue("id_indirizzo", option.dataset.indirizzoId);
                setFieldValue("id_telefono", option.dataset.telefono);
                setFieldValue("id_email", option.dataset.email);
            }

            lockedFieldIds.forEach(function (fieldId) {
                setAnagraphicFieldLocked(document.getElementById(fieldId), locked);
            });
        };

        lockedFieldIds.forEach(function (fieldId) {
            const field = document.getElementById(fieldId);
            if (!(field instanceof HTMLSelectElement)) {
                return;
            }
            field.addEventListener("change", function () {
                if (field.getAttribute("aria-disabled") !== "true" || !field.dataset.lockedValue) {
                    return;
                }
                if (field.value !== field.dataset.lockedValue) {
                    field.value = field.dataset.lockedValue;
                    dispatchFieldEvents(field);
                    if (window.ArborisFamigliaAutocomplete) {
                        ArborisFamigliaAutocomplete.refresh(document);
                    }
                }
            });
        });

        personaSelect.addEventListener("change", sync);
        sync();
    }

    function init(config) {
        initBirthplaceNationalitySync();
        initRoleDependentFields();
        initFamiliareAutofill();

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
