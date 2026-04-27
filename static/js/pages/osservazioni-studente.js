(function () {
    function initCreateObservationMode() {
        var section = document.getElementById("osservazioni-create-section");
        var form = document.getElementById("osservazione-create-form");
        var toggleButton = document.getElementById("osservazioni-create-toggle");
        var cancelButton = document.getElementById("osservazioni-create-cancel");

        if (!section || !form || !toggleButton) {
            return;
        }

        var addLabel = toggleButton.dataset.addLabel || "AGGIUNGI UN'OSSERVAZIONE";
        var saveLabel = toggleButton.dataset.saveLabel || "SALVA LE MODIFICHE";
        var isEditing = toggleButton.dataset.active === "1";

        function refreshRichNotes() {
            if (window.ArborisRichNotes) {
                if (typeof window.ArborisRichNotes.init === "function") {
                    window.ArborisRichNotes.init(section);
                }
                if (typeof window.ArborisRichNotes.refresh === "function") {
                    window.ArborisRichNotes.refresh(section);
                }
            }
        }

        function focusFirstField() {
            var firstField = section.querySelector("input:not([type='hidden']), textarea, .rich-note-editor");
            if (firstField && typeof firstField.focus === "function") {
                firstField.focus();
            }
        }

        function applyMode() {
            section.classList.toggle("is-hidden", !isEditing);
            toggleButton.classList.toggle("btn-primary", !isEditing);
            toggleButton.classList.toggle("btn-save-soft", isEditing);
            toggleButton.textContent = isEditing ? saveLabel : addLabel;
            toggleButton.dataset.active = isEditing ? "1" : "0";
            toggleButton.setAttribute("aria-expanded", isEditing ? "true" : "false");

            if (cancelButton) {
                cancelButton.classList.toggle("is-hidden", !isEditing);
            }

            if (isEditing) {
                refreshRichNotes();
            }
        }

        toggleButton.addEventListener("click", function () {
            if (isEditing) {
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
                return;
            }

            isEditing = true;
            applyMode();
            window.setTimeout(focusFirstField, 0);
        });

        if (cancelButton) {
            cancelButton.addEventListener("click", function () {
                var destination = window.location.pathname + window.location.search;
                window.location.assign(destination);
            });
        }

        applyMode();
    }

    document.addEventListener("DOMContentLoaded", initCreateObservationMode);
})();
