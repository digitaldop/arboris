window.ArborisViewMode = (function () {
    function reloadPageAfterCancel() {
        if (typeof window.ArborisReloadWithLongWait === "function") {
            window.ArborisReloadWithLongWait();
        } else {
            window.location.reload();
        }
    }

    function getScopeFields(container, excludedContainer) {
        if (!container) {
            return [];
        }

        return Array.from(container.querySelectorAll("input, textarea, select")).filter(field => {
            if (field.type === "hidden") {
                return false;
            }
            if (excludedContainer && excludedContainer.contains(field)) {
                return false;
            }
            return true;
        });
    }

    function lockFields(fields, keepSubmittedWhenLocked) {
        fields.forEach(field => {
            if (field.closest(".inline-empty-row.is-hidden")) {
                field.disabled = true;
                field.readOnly = true;
                return;
            }

            const tag = field.tagName.toLowerCase();
            const type = (field.type || "").toLowerCase();
            const lockByDisable = tag === "select" || type === "checkbox" || type === "radio" || type === "file";

            field.classList.remove("submit-safe-locked");
            field.removeAttribute("aria-disabled");
            field.removeAttribute("tabindex");

            if (lockByDisable) {
                if (keepSubmittedWhenLocked) {
                    field.disabled = false;
                    field.classList.add("submit-safe-locked");
                    field.setAttribute("aria-disabled", "true");
                    field.setAttribute("tabindex", "-1");
                } else {
                    field.disabled = true;
                }
            } else {
                field.readOnly = true;
            }
        });
    }

    function keepFieldSubmittedButLocked(field) {
        field.disabled = false;
        field.classList.add("submit-safe-locked");
        field.setAttribute("aria-disabled", "true");
        field.setAttribute("tabindex", "-1");
    }

    function unlockFields(fields) {
        fields.forEach(field => {
            if (field.closest(".inline-empty-row.is-hidden")) {
                field.disabled = true;
                field.readOnly = true;
                return;
            }

            if (field.dataset.keepSubmittedLocked === "1") {
                keepFieldSubmittedButLocked(field);
                return;
            }

            field.classList.remove("submit-safe-locked");
            field.removeAttribute("aria-disabled");
            field.removeAttribute("tabindex");
            field.disabled = false;
            field.readOnly = false;
        });
    }

    function enableDisabledFieldsForSubmit(container) {
        if (!container) return;

        container.querySelectorAll("input, textarea, select").forEach(field => {
            if (field.closest(".inline-empty-row.is-hidden")) {
                return;
            }
            if (field.disabled) {
                field.disabled = false;
            }
        });
    }

    function getModalHost() {
        try {
            if (window.parent && window.parent !== window && window.parent.ArborisModalPopups) {
                return window.parent.ArborisModalPopups;
            }
            if (window.top && window.top !== window && window.top.ArborisModalPopups) {
                return window.top.ArborisModalPopups;
            }
        } catch (error) {
            return null;
        }
        return null;
    }

    function requestModalResize() {
        const modalHost = getModalHost();
        if (!modalHost || typeof modalHost.requestResizeForWindow !== "function") {
            return;
        }

        modalHost.requestResizeForWindow(window);
    }

    function emitViewModeChange(form, mode) {
        if (!form || typeof CustomEvent !== "function") {
            return;
        }

        form.dispatchEvent(new CustomEvent("arboris:view-mode-change", {
            bubbles: true,
            detail: {
                form: form,
                mode: mode,
                isEditing: mode !== "view",
            },
        }));
    }

    function getButtonLabel(button, fallback) {
        if (!button) {
            return fallback || "";
        }

        const labelElement = button.querySelector("[data-btn-label], .btn-label");
        const label = labelElement ? labelElement.textContent.trim() : button.textContent.trim();
        return label || fallback || "";
    }

    function setButtonLabel(button, label) {
        if (!button) {
            return;
        }

        const labelElement = button.querySelector("[data-btn-label], .btn-label");
        if (labelElement) {
            labelElement.textContent = label;
            return;
        }

        const iconElement = button.querySelector(".btn-icon");
        if (!iconElement) {
            button.textContent = label;
            return;
        }

        Array.from(button.childNodes).forEach(node => {
            if (node !== iconElement && node.nodeType === Node.TEXT_NODE) {
                node.remove();
            }
        });

        const createdLabel = document.createElement("span");
        createdLabel.className = "btn-label";
        createdLabel.textContent = label;
        button.appendChild(createdLabel);
    }

    function clearInlineAddOnlyMode(form) {
        if (!form) return;

        form.classList.remove("is-inline-add-only-mode");
        form.classList.remove("is-inline-first-student-add-mode");
        form.querySelectorAll(".is-inline-active-edit-row").forEach(row => {
            row.classList.remove("is-inline-active-edit-row");
        });
    }

    function init(config) {
        const form = document.getElementById(config.formId);
        const mainContainer = document.getElementById(config.lockContainerId);
        const inlineContainer = config.inlineLockContainerId
            ? document.getElementById(config.inlineLockContainerId)
            : null;
        const editButton = document.getElementById(config.editButtonId);
        const inlineEditButton = config.inlineEditButtonId
            ? document.getElementById(config.inlineEditButtonId)
            : null;
        const cancelButton = document.getElementById(config.cancelButtonId);
        const modeInput = config.modeInputId ? document.getElementById(config.modeInputId) : null;
        const externalEditOnlyElements = Array.from(
            document.querySelectorAll(`[data-edit-mode-for="${config.formId}"]`)
        );

        if (!form || !mainContainer) {
            return;
        }

        if (mainContainer.tagName.toLowerCase() === "fieldset") {
            mainContainer.disabled = false;
        }

        const editButtonDefaultLabel = getButtonLabel(editButton, "Modifica");
        const mainFields = getScopeFields(mainContainer, inlineContainer);
        const inlineFields = getScopeFields(inlineContainer, null);

        let currentMode = config.startMode || (Boolean(config.startInEditMode) ? "full" : "view");
        if (!["view", "inline", "full"].includes(currentMode)) {
            currentMode = Boolean(config.startInEditMode) ? "full" : "view";
        }

        function applyMode(nextMode) {
            currentMode = nextMode;
            const isFullEditing = currentMode === "full";
            const isInlineEditing = currentMode === "inline";

            form.classList.toggle("is-view-mode", currentMode === "view");
            form.classList.toggle("is-edit-mode", isFullEditing);
            form.classList.toggle("is-inline-edit-mode", isInlineEditing);
            form.classList.toggle("is-inline-readonly-mode", isFullEditing);

            if (inlineContainer) {
                inlineContainer.classList.toggle("is-inline-readonly-view", isFullEditing);
            }

            if (!isInlineEditing) {
                clearInlineAddOnlyMode(form);
            }

            if (isFullEditing) {
                unlockFields(mainFields);
                lockFields(inlineFields, true);
            } else if (isInlineEditing) {
                lockFields(mainFields, true);
                unlockFields(inlineFields);
            } else {
                lockFields(mainFields, false);
                lockFields(inlineFields, false);
            }

            if (editButton) {
                setButtonLabel(editButton, isFullEditing ? "Annulla modifiche" : editButtonDefaultLabel);
                editButton.classList.toggle("is-hidden", isInlineEditing);
            }

            if (cancelButton) {
                cancelButton.classList.add("is-hidden");
            }

            if (modeInput) {
                modeInput.value = currentMode;
            }

            externalEditOnlyElements.forEach(element => {
                element.classList.toggle("is-hidden", currentMode === "view");
            });

            if (typeof config.onModeChange === "function") {
                config.onModeChange(currentMode, currentMode !== "view");
            }

            emitViewModeChange(form, currentMode);
            requestModalResize();

            if (inlineEditButton) {
                if (isInlineEditing) {
                    setButtonLabel(inlineEditButton, "Annulla modifiche");
                } else if (typeof config.onModeChange !== "function") {
                    setButtonLabel(inlineEditButton, "Modifica");
                }
                inlineEditButton.classList.toggle("is-hidden", isFullEditing);
            }
        }

        if (editButton) {
            editButton.addEventListener("click", function () {
                if (currentMode === "full") {
                    if (config.reloadOnCancel) {
                        reloadPageAfterCancel();
                        return;
                    }
                    applyMode("view");
                    return;
                }

                applyMode("full");
            });
        }

        if (inlineEditButton) {
            inlineEditButton.addEventListener("click", function () {
                if (currentMode === "inline") {
                    if (config.reloadOnCancel) {
                        reloadPageAfterCancel();
                        return;
                    }
                    applyMode("view");
                    return;
                }

                applyMode("inline");
            });
        }

        if (cancelButton) {
            cancelButton.addEventListener("click", function () {
                if (config.reloadOnCancel) {
                    reloadPageAfterCancel();
                    return;
                }
                applyMode("view");
            });
        }

        form.addEventListener("submit", function () {
            if (modeInput) {
                modeInput.value = currentMode;
            }
            enableDisabledFieldsForSubmit(mainContainer);
            enableDisabledFieldsForSubmit(inlineContainer);
        });

        applyMode(currentMode);

        function returnToView() {
            if (config.reloadOnCancel) {
                reloadPageAfterCancel();
            } else {
                applyMode("view");
            }
        }

        return {
            isEditing: function () {
                return currentMode !== "view";
            },
            isInlineEditing: function () {
                return currentMode === "inline";
            },
            setEditing: function (isEditing) {
                applyMode(isEditing ? "full" : "view");
            },
            setInlineEditing: function (isEditing) {
                applyMode(isEditing ? "inline" : "view");
            },
            returnToView: returnToView,
        };
    }

    return {
        init,
    };
})();
