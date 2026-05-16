window.ArborisMovimentiList = (function () {
    let activeEdit = null;
    let lockOverlay = null;

    function getCookie(name) {
        const prefix = `${name}=`;
        return document.cookie
            .split(";")
            .map(part => part.trim())
            .find(part => part.startsWith(prefix))
            ?.slice(prefix.length) || "";
    }

    function csrfToken() {
        const field = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return field ? field.value : getCookie("csrftoken");
    }

    function ensureOverlay() {
        if (lockOverlay) {
            return lockOverlay;
        }
        lockOverlay = document.createElement("div");
        lockOverlay.className = "finance-category-edit-overlay";
        lockOverlay.setAttribute("aria-hidden", "true");
        ["click", "mousedown", "mouseup", "contextmenu"].forEach(eventName => {
            lockOverlay.addEventListener(eventName, function (event) {
                event.preventDefault();
                event.stopPropagation();
            });
        });
        document.body.appendChild(lockOverlay);
        return lockOverlay;
    }

    function optionTemplate() {
        return document.getElementById("movement-category-options-template");
    }

    function uiIconHref(iconName) {
        const existingUse = document.querySelector("svg use[href*='arboris-ui-icons.svg']");
        const existingHref = existingUse ? existingUse.getAttribute("href") : "";
        const spriteHref = existingHref && existingHref.includes("#")
            ? existingHref.split("#")[0]
            : "/static/images/arboris-ui-icons.svg";
        return `${spriteHref}#${iconName}`;
    }

    function appendIcon(button, iconName) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        svg.setAttribute("aria-hidden", "true");
        use.setAttribute("href", uiIconHref(iconName));
        svg.appendChild(use);
        button.appendChild(svg);
    }

    function updateDisplay(cell, data) {
        const name = cell.querySelector("[data-category-name]");
        const auto = cell.querySelector("[data-category-auto]");
        const categoryId = data.category_id || "";
        const label = data.category_label || "non categorizzato";

        cell.dataset.categoryId = categoryId;
        if (name) {
            name.textContent = label;
            name.classList.toggle("table-muted", !categoryId);
        }
        if (auto) {
            auto.hidden = true;
        }
    }

    function closeEditor() {
        if (!activeEdit) {
            return;
        }
        activeEdit.cell.classList.remove("is-editing");
        const editor = activeEdit.cell.querySelector("[data-category-editor]");
        if (editor) {
            editor.remove();
        }
        if (lockOverlay) {
            lockOverlay.remove();
            lockOverlay = null;
        }
        document.body.classList.remove("finance-category-editing");
        activeEdit = null;
    }

    function focusActiveEditor() {
        if (!activeEdit) {
            return;
        }
        const input = activeEdit.cell.querySelector(".searchable-select-input") || activeEdit.select;
        input?.focus();
    }

    function setStatus(message, tone) {
        if (!activeEdit || !activeEdit.status) {
            return;
        }
        activeEdit.status.textContent = message || "";
        activeEdit.status.dataset.tone = tone || "";
    }

    function setSavingState(saving) {
        if (!activeEdit) {
            return;
        }
        activeEdit.saving = saving;
        if (activeEdit.saveButton) {
            activeEdit.saveButton.disabled = saving;
        }
        if (activeEdit.cancelButton) {
            activeEdit.cancelButton.disabled = saving;
        }
        activeEdit.cell.classList.toggle("is-saving", saving);
    }

    function saveActiveEditor() {
        if (!activeEdit || activeEdit.saving) {
            return;
        }

        const { cell, select } = activeEdit;
        const formData = new FormData();
        formData.append("categoria", select.value || "");
        setSavingState(true);
        setStatus("Salvataggio...", "");

        fetch(cell.dataset.updateUrl, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: formData,
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error("Salvataggio non riuscito");
                }
                return response.json();
            })
            .then(data => {
                updateDisplay(cell, data);
                closeEditor();
            })
            .catch(error => {
                if (!activeEdit || activeEdit.cell !== cell) {
                    return;
                }
                setSavingState(false);
                setStatus(error.message || "Salvataggio non riuscito", "error");
            });
    }

    function startEditor(cell) {
        if (activeEdit) {
            return;
        }
        const template = optionTemplate();
        if (!template || !cell.dataset.updateUrl) {
            return;
        }

        ensureOverlay();
        document.body.classList.add("finance-category-editing");
        cell.classList.add("is-editing");

        const editor = document.createElement("div");
        editor.className = "finance-category-editor";
        editor.setAttribute("data-category-editor", "1");

        const fieldRow = document.createElement("div");
        fieldRow.className = "finance-category-editor-field";

        const select = document.createElement("select");
        select.setAttribute("data-searchable-select", "1");
        select.setAttribute("data-searchable-placeholder", "Cerca categoria...");
        select.setAttribute("data-searchable-variant", "category-tree");
        select.setAttribute("data-searchable-allow-empty", "1");
        select.className = "finance-category-editor-select";
        select.innerHTML = template.innerHTML;
        select.value = cell.dataset.categoryId || "";

        const actions = document.createElement("div");
        actions.className = "finance-category-editor-actions";

        const saveButton = document.createElement("button");
        saveButton.type = "button";
        saveButton.className = "table-icon-link finance-category-editor-btn finance-category-editor-save";
        saveButton.setAttribute("aria-label", "Salva categoria");
        saveButton.setAttribute("data-floating-text", "Salva");
        appendIcon(saveButton, "check");

        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.className = "table-icon-link table-icon-link-danger finance-category-editor-btn finance-category-editor-cancel";
        cancelButton.setAttribute("aria-label", "Annulla modifica categoria");
        cancelButton.setAttribute("data-floating-text", "Annulla");
        appendIcon(cancelButton, "x");

        saveButton.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            saveActiveEditor();
        });

        cancelButton.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            closeEditor();
        });

        const status = document.createElement("div");
        status.className = "finance-category-editor-status";
        status.setAttribute("aria-live", "polite");

        actions.appendChild(saveButton);
        actions.appendChild(cancelButton);
        fieldRow.appendChild(select);
        fieldRow.appendChild(actions);
        editor.appendChild(fieldRow);
        editor.appendChild(status);
        cell.appendChild(editor);

        activeEdit = { cell, select, status, saveButton, cancelButton, saving: false };

        if (window.ArborisFamigliaAutocomplete) {
            window.ArborisFamigliaAutocomplete.init(editor, { force: true });
        }

        const input = editor.querySelector(".searchable-select-input") || select;
        input.focus();
        input.select?.();
    }

    function bind(root) {
        const scope = root || document;
        if (scope.documentElement && scope.documentElement.dataset.movimentiListReady === "1") {
            return;
        }
        if (scope.documentElement) {
            scope.documentElement.dataset.movimentiListReady = "1";
        }

        document.addEventListener("contextmenu", function (event) {
            const cell = event.target.closest("[data-movement-category-cell]");
            if (activeEdit) {
                event.preventDefault();
                event.stopPropagation();
                if (cell === activeEdit.cell || activeEdit.cell.contains(event.target)) {
                    saveActiveEditor();
                }
                return;
            }
            if (!cell) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            startEditor(cell);
        }, true);

        document.addEventListener("click", function (event) {
            if (!activeEdit || activeEdit.cell.contains(event.target)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
        }, true);

        document.addEventListener("focusin", function (event) {
            if (!activeEdit || activeEdit.cell.contains(event.target)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            focusActiveEditor();
        }, true);

        document.addEventListener("keydown", function (event) {
            if (!activeEdit) {
                return;
            }
            if (event.key === "Escape") {
                event.preventDefault();
                closeEditor();
            }
        }, true);
    }

    return {
        init: bind,
    };
})();
