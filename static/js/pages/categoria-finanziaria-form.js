(function () {
    function isHexColor(value) {
        return /^#[0-9a-fA-F]{6}$/.test((value || "").trim());
    }

    function initColorPicker() {
        var picker = document.getElementById("id_colore_picker");
        var input = document.getElementById("id_colore");
        if (!picker || !input) {
            return;
        }

        picker.addEventListener("input", function () {
            input.value = picker.value.toUpperCase();
        });

        input.addEventListener("input", function () {
            var value = input.value.trim();
            if (value && value.charAt(0) !== "#") {
                value = "#" + value;
            }
            if (isHexColor(value)) {
                picker.value = value;
            }
        });
    }

    function initIconPicker() {
        document.querySelectorAll("[data-category-icon-picker]").forEach(function (picker) {
            var inputId = picker.getAttribute("data-icon-field-id");
            var input = document.getElementById(inputId);
            var preview = picker.querySelector("[data-selected-icon-preview]");
            var label = picker.querySelector("[data-selected-icon-label]");
            var clearButton = picker.querySelector("[data-clear-icon]");
            var buttons = Array.prototype.slice.call(picker.querySelectorAll("[data-icon-value]"));

            if (!input || !preview || !label) {
                return;
            }

            function setSelected(value) {
                var selectedButton = null;
                buttons.forEach(function (button) {
                    var isSelected = button.getAttribute("data-icon-value") === value;
                    button.classList.toggle("is-selected", isSelected);
                    button.setAttribute("aria-selected", isSelected ? "true" : "false");
                    if (isSelected) {
                        selectedButton = button;
                    }
                });

                input.value = value || "";
                if (selectedButton) {
                    preview.textContent = selectedButton.getAttribute("data-icon-symbol") || "-";
                    label.textContent = selectedButton.getAttribute("data-icon-label") || value;
                } else {
                    preview.textContent = "-";
                    label.textContent = "Nessuna icona selezionata";
                }
            }

            buttons.forEach(function (button) {
                button.addEventListener("click", function () {
                    setSelected(button.getAttribute("data-icon-value"));
                });
            });

            if (clearButton) {
                clearButton.addEventListener("click", function () {
                    setSelected("");
                });
            }

            setSelected(input.value);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initColorPicker();
        initIconPicker();
    });
})();
