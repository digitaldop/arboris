window.ArborisPrestazioneScambioRettaForm = (function () {
    function init() {
        const familiareSelect = document.getElementById("id_familiare");
        const studenteSelect = document.getElementById("id_studente");
        const dataInput = document.getElementById("id_data");
        const ingressoSelect = document.getElementById("id_ora_ingresso");
        const uscitaSelect = document.getElementById("id_ora_uscita");
        const oreInput = document.getElementById("id_ore_lavorate");
        const tariffaSelect = document.getElementById("id_tariffa_scambio_retta");
        const importoPreview = document.getElementById("prestazione-scambio-importo-preview");
        const annoPreview = document.getElementById("prestazione-anno-preview");
        const schoolYearsNode = document.getElementById("prestazione-scambio-school-years");

        if (
            !familiareSelect ||
            !studenteSelect ||
            !dataInput ||
            !ingressoSelect ||
            !uscitaSelect ||
            !oreInput ||
            !tariffaSelect ||
            !importoPreview
        ) {
            return;
        }

        let schoolYears = [];
        if (schoolYearsNode) {
            try {
                schoolYears = JSON.parse(schoolYearsNode.textContent || "[]");
            } catch (error) {
                schoolYears = [];
            }
        }

        function parseDecimal(value) {
            const parsed = parseFloat(String(value || "").replace(",", "."));
            return Number.isFinite(parsed) ? parsed : 0;
        }

        function formatDecimal(value) {
            return value.toLocaleString("it-IT", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
        }

        function getSelectedOption(select) {
            return select.options[select.selectedIndex] || null;
        }

        function parseTimeString(value) {
            if (!value || value.indexOf(":") === -1) {
                return null;
            }

            const [hours, minutes] = value.split(":").map(Number);
            if (!Number.isInteger(hours) || !Number.isInteger(minutes)) {
                return null;
            }

            return (hours * 60) + minutes;
        }

        function csvIncludes(csvValue, needle) {
            if (!csvValue || !needle) {
                return false;
            }
            return String(csvValue)
                .split(",")
                .map(value => value.trim())
                .filter(Boolean)
                .includes(String(needle));
        }

        function filterStudentiByFamiliare() {
            const selectedOption = getSelectedOption(familiareSelect);
            const selectedStudentIds = selectedOption ? selectedOption.dataset.studenteIds || "" : "";
            const hasDirectStudents = Boolean(selectedStudentIds);
            let hasSelectedVisibleOption = false;

            Array.from(studenteSelect.options).forEach(option => {
                if (!option.value) {
                    option.hidden = false;
                    option.disabled = false;
                    return;
                }

                const isVisible = hasDirectStudents && csvIncludes(selectedStudentIds, option.value);
                option.hidden = !isVisible;
                option.disabled = !isVisible;

                if (isVisible && option.selected) {
                    hasSelectedVisibleOption = true;
                }
            });

            if (studenteSelect.value && !hasSelectedVisibleOption) {
                studenteSelect.value = "";
            }
        }

        function refreshAnnoPreview() {
            if (!annoPreview) {
                return;
            }

            const selectedDate = dataInput.value || "";
            const matchedYear = schoolYears.find(item => {
                return item.data_inizio <= selectedDate && item.data_fine >= selectedDate;
            });

            annoPreview.textContent = matchedYear
                ? matchedYear.nome_anno_scolastico
                : "Verra ricavato automaticamente dalla data";
        }

        function refreshOreAndImporto() {
            const ingresso = parseTimeString(ingressoSelect.value);
            const uscita = parseTimeString(uscitaSelect.value);
            let oreValue = parseDecimal(oreInput.value);

            if (ingresso !== null && uscita !== null && uscita > ingresso) {
                oreValue = (uscita - ingresso) / 60;
                oreInput.value = formatDecimal(oreValue);
                oreInput.readOnly = true;
                oreInput.classList.add("is-auto-calculated");
            } else {
                oreInput.readOnly = false;
                oreInput.classList.remove("is-auto-calculated");
            }

            const selectedTariffa = getSelectedOption(tariffaSelect);
            const valoreOrario = selectedTariffa ? parseDecimal(selectedTariffa.dataset.valoreOrario) : 0;
            importoPreview.textContent = formatDecimal(oreValue * valoreOrario);
        }

        familiareSelect.addEventListener("change", function () {
            filterStudentiByFamiliare();
        });
        dataInput.addEventListener("change", refreshAnnoPreview);
        ingressoSelect.addEventListener("change", refreshOreAndImporto);
        uscitaSelect.addEventListener("change", refreshOreAndImporto);
        oreInput.addEventListener("input", refreshOreAndImporto);
        tariffaSelect.addEventListener("change", refreshOreAndImporto);

        filterStudentiByFamiliare();
        refreshAnnoPreview();
        refreshOreAndImporto();
    }

    return {
        init,
    };
})();
