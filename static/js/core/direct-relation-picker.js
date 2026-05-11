window.ArborisDirectRelationPicker = (function () {
    const DEFAULT_MIN_CHARS = 3;

    function normalizeText(value) {
        return (value || "")
            .toString()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim();
    }

    function createIcon(name, spritePath) {
        if (!spritePath) {
            return document.createTextNode("");
        }

        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("aria-hidden", "true");
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        use.setAttribute("href", `${spritePath}#${name}`);
        svg.appendChild(use);
        return svg;
    }

    function getMode(select) {
        if (select.dataset.parentSurnameSuggestions) {
            return {
                type: "parent",
                minChars: Number(select.dataset.parentSurnameMinChars || DEFAULT_MIN_CHARS),
                placeholder: "Cerca e seleziona familiari...",
                automaticMessage: "Digita almeno tre lettere del cognome oppure cerca manualmente un familiare.",
                emptyMessage: "Nessun familiare trovato.",
                selectedLabel: "selezionati",
                surnameHelpAttr: "data-parent-surname-help",
            };
        }

        if (select.dataset.studentSurnameSuggestions) {
            return {
                type: "student",
                minChars: Number(select.dataset.studentSurnameMinChars || DEFAULT_MIN_CHARS),
                placeholder: "Cerca e seleziona bambini o studenti...",
                automaticMessage: "Digita almeno tre lettere del cognome oppure cerca manualmente uno studente.",
                emptyMessage: "Nessuno studente trovato.",
                selectedLabel: "selezionati",
                surnameHelpAttr: "data-student-surname-help",
            };
        }

        return {
            type: "generic",
            minChars: 0,
            placeholder: "Cerca e seleziona...",
            automaticMessage: "Cerca e seleziona uno o piu elementi.",
            emptyMessage: "Nessun elemento trovato.",
            selectedLabel: "selezionati",
            surnameHelpAttr: "",
        };
    }

    function optionLabel(option) {
        return (option.dataset.pickerLabel || option.textContent || "").trim();
    }

    function optionSearchText(option) {
        return normalizeText([
            option.textContent,
            option.dataset.search,
            option.dataset.nome,
            option.dataset.cognome,
            option.dataset.codiceFiscale,
        ].filter(Boolean).join(" "));
    }

    function optionInitials(option) {
        const fromDataset = (option.dataset.initials || "").trim();
        if (fromDataset) {
            return fromDataset.slice(0, 2).toUpperCase();
        }

        const parts = optionLabel(option).replace(/[()]/g, " ").split(/\s+/).filter(Boolean);
        return (parts[0]?.[0] || "?").toUpperCase() + (parts[1]?.[0] || "").toUpperCase();
    }

    function selectedOptions(select) {
        return Array.from(select.options).filter(option => option.value && option.selected);
    }

    function dispatchNativeChange(select) {
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function findHelpElement(select, mode) {
        if (mode.surnameHelpAttr) {
            const siblingHelp = select.parentElement?.querySelector(`[${mode.surnameHelpAttr}]`);
            if (siblingHelp) {
                return siblingHelp;
            }
        }
        return select.parentElement?.querySelector(".field-help") || null;
    }

    function buildPicker(select, mode, spritePath) {
        const picker = document.createElement("div");
        picker.className = "direct-relation-picker";
        picker.innerHTML = `
            <div class="direct-relation-picker-toolbar">
                <label class="direct-relation-picker-search">
                    <span class="sr-only">Cerca</span>
                    <input type="search" autocomplete="off">
                </label>
                <span class="direct-relation-picker-count">0 selezionati</span>
                <button type="button" class="direct-relation-picker-toggle" aria-label="Mostra o nascondi risultati" aria-expanded="true"></button>
            </div>
            <div class="direct-relation-picker-chips"></div>
            <div class="direct-relation-picker-list"></div>
        `;

        const searchInput = picker.querySelector("input[type='search']");
        searchInput.placeholder = mode.placeholder;

        const searchLabel = picker.querySelector(".direct-relation-picker-search");
        searchLabel.insertBefore(createIcon("search", spritePath), searchInput);

        const toggle = picker.querySelector(".direct-relation-picker-toggle");
        toggle.appendChild(createIcon("chevron-up", spritePath));

        select.insertAdjacentElement("afterend", picker);
        select.classList.add("is-enhanced-native");

        return {
            picker,
            searchInput,
            count: picker.querySelector(".direct-relation-picker-count"),
            toggle,
            chips: picker.querySelector(".direct-relation-picker-chips"),
            list: picker.querySelector(".direct-relation-picker-list"),
        };
    }

    function enhanceSelect(select, config) {
        if (!select || select.dataset.directRelationPickerBound === "1") {
            if (select?.__directRelationPicker) {
                select.__directRelationPicker.render();
            }
            return;
        }

        const mode = getMode(select);
        const root = config.root || document;
        const surnameInput = config.surnameInput || root.querySelector(config.surnameInputSelector || "#id_cognome");
        const spritePath = config.uiIconsSprite || "";
        const help = findHelpElement(select, mode);
        const ui = buildPicker(select, mode, spritePath);

        function isVisibleOption(option) {
            if (!option.value) {
                return false;
            }

            const manualQuery = normalizeText(ui.searchInput.value);
            const surnameQuery = normalizeText(surnameInput?.value || "");

            if (option.selected) {
                return true;
            }

            if (manualQuery) {
                return optionSearchText(option).includes(manualQuery);
            }

            if (mode.type !== "generic" && surnameQuery.length >= mode.minChars) {
                return optionSearchText(option).includes(surnameQuery);
            }

            return mode.type === "generic";
        }

        function renderChips() {
            ui.chips.innerHTML = "";
            selectedOptions(select).forEach(function (option) {
                const chip = document.createElement("span");
                chip.className = "direct-relation-picker-chip";

                const chipLabel = document.createElement("span");
                chipLabel.className = "direct-relation-picker-chip-label";
                chipLabel.textContent = optionLabel(option);
                chip.appendChild(chipLabel);

                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "direct-relation-picker-chip-icon";
                remove.setAttribute("aria-label", `Rimuovi ${optionLabel(option)}`);
                remove.appendChild(createIcon("x", spritePath));
                remove.addEventListener("click", function () {
                    option.selected = false;
                    dispatchNativeChange(select);
                    render();
                });
                chip.appendChild(remove);

                ui.chips.appendChild(chip);
            });
        }

        function renderList() {
            ui.list.innerHTML = "";
            const visibleOptions = Array.from(select.options).filter(isVisibleOption);

            if (!visibleOptions.length) {
                const empty = document.createElement("div");
                empty.className = "direct-relation-picker-empty";
                const hasManualQuery = normalizeText(ui.searchInput.value).length > 0;
                empty.textContent = hasManualQuery || mode.type === "generic" ? mode.emptyMessage : mode.automaticMessage;
                ui.list.appendChild(empty);
                return;
            }

            visibleOptions.forEach(function (option) {
                const row = document.createElement("label");
                row.className = "direct-relation-picker-row";
                row.classList.toggle("is-selected", option.selected);

                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.checked = option.selected;
                checkbox.addEventListener("change", function () {
                    option.selected = checkbox.checked;
                    dispatchNativeChange(select);
                    render();
                });
                row.appendChild(checkbox);

                const avatar = document.createElement("span");
                avatar.className = "direct-relation-picker-avatar";
                avatar.textContent = optionInitials(option);
                row.appendChild(avatar);

                const label = document.createElement("span");
                label.className = "direct-relation-picker-name";
                label.textContent = optionLabel(option);
                row.appendChild(label);

                ui.list.appendChild(row);
            });
        }

        function updateHelp() {
            if (!help || mode.type === "generic") {
                return;
            }

            const query = normalizeText(surnameInput?.value || "");
            if (!query) {
                help.textContent = mode.automaticMessage;
                return;
            }

            if (query.length < mode.minChars) {
                help.textContent = `Digita almeno ${mode.minChars} lettere del cognome oppure usa la ricerca manuale.`;
                return;
            }

            help.textContent = `Suggerimenti filtrati per cognome. Puoi comunque cercare manualmente altri collegamenti.`;
        }

        function render() {
            const selectedCount = selectedOptions(select).length;
            ui.count.textContent = `${selectedCount} ${mode.selectedLabel}`;
            renderChips();
            renderList();
            updateHelp();
        }

        ui.searchInput.addEventListener("input", render);
        select.addEventListener("change", render);

        if (surnameInput) {
            surnameInput.addEventListener("input", render);
            surnameInput.addEventListener("change", render);
        }

        ui.toggle.addEventListener("click", function () {
            const collapsed = ui.picker.classList.toggle("is-collapsed");
            ui.toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
        });

        select.dataset.directRelationPickerBound = "1";
        select.__directRelationPicker = { render };
        render();
    }

    function init(root, config) {
        const scope = root || document;
        const settings = Object.assign({}, config || {}, { root: scope });
        scope.querySelectorAll(".direct-relation-select").forEach(select => enhanceSelect(select, settings));
    }

    return {
        init,
    };
})();
