(function () {
    function extractConsonants(value) {
        return (value || "").toUpperCase().replace(/[^A-Z]/g, "").replace(/[AEIOU]/g, "");
    }

    function extractVowels(value) {
        return (value || "").toUpperCase().replace(/[^AEIOU]/g, "");
    }

    function codeFromSurname(value) {
        const consonants = extractConsonants(value);
        const vowels = extractVowels(value);
        return (consonants + vowels + "XXX").slice(0, 3);
    }

    function codeFromName(value) {
        const consonants = extractConsonants(value);
        const vowels = extractVowels(value);
        if (consonants.length >= 4) {
            return `${consonants[0]}${consonants[2]}${consonants[3]}`;
        }
        return (consonants + vowels + "XXX").slice(0, 3);
    }

    function codeFromDate(dateValue, sex) {
        if (!dateValue || !sex) return "";
        // Campi <input type="date"> usano YYYY-MM-DD: va interpretato come data di calendario locale,
        // non come UTC, altrimenti giorno/mese possono slittare in alcuni fusi.
        const raw = String(dateValue).trim();
        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
        let y;
        let monthIndex0;
        let day;
        if (m) {
            y = parseInt(m[1], 10);
            const mo = parseInt(m[2], 10);
            day = parseInt(m[3], 10);
            if (mo < 1 || mo > 12 || day < 1 || day > 31) return "";
            monthIndex0 = mo - 1;
        } else {
            const date = new Date(dateValue);
            if (Number.isNaN(date.getTime())) return "";
            y = date.getFullYear();
            monthIndex0 = date.getMonth();
            day = date.getDate();
        }

        const months = "ABCDEHLMPRST";
        const year = String(y).slice(-2);
        const month = months[monthIndex0] || "";
        let d = day;
        if (sex === "F") d += 40;
        return `${year}${month}${String(d).padStart(2, "0")}`;
    }

    function controlCharacter(partialCode) {
        const oddMap = {
            "0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17, "8": 19, "9": 21,
            A: 1, B: 0, C: 5, D: 7, E: 9, F: 13, G: 15, H: 17, I: 19, J: 21,
            K: 2, L: 4, M: 18, N: 20, O: 11, P: 3, Q: 6, R: 8, S: 12, T: 14,
            U: 16, V: 10, W: 22, X: 25, Y: 24, Z: 23,
        };
        const evenMap = {
            "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
            A: 0, B: 1, C: 2, D: 3, E: 4, F: 5, G: 6, H: 7, I: 8, J: 9,
            K: 10, L: 11, M: 12, N: 13, O: 14, P: 15, Q: 16, R: 17, S: 18, T: 19,
            U: 20, V: 21, W: 22, X: 23, Y: 24, Z: 25,
        };

        let sum = 0;
        for (let i = 0; i < partialCode.length; i += 1) {
            const char = partialCode[i];
            sum += (i % 2 === 0 ? oddMap[char] : evenMap[char]) || 0;
        }
        return String.fromCharCode(65 + (sum % 26));
    }

    function generateCodiceFiscale(data) {
        const surnameCode = codeFromSurname(data.cognome);
        const nameCode = codeFromName(data.nome);
        const dateCode = codeFromDate(data.dataNascita, data.sesso);
        const comuneCode = (data.codiceCatastale || "").toUpperCase();

        if (!surnameCode || !nameCode || !dateCode || comuneCode.length !== 4) {
            return "";
        }

        const partial = `${surnameCode}${nameCode}${dateCode}${comuneCode}`;
        return `${partial}${controlCharacter(partial)}`;
    }

    function shouldIgnoreContainer(container) {
        return Boolean(
            !container ||
            container.closest("template") ||
            (container.classList && container.classList.contains("inline-empty-row") && container.classList.contains("is-hidden"))
        );
    }

    function bindContainer(container) {
        if (!container || container.dataset.cfReady === "1" || shouldIgnoreContainer(container)) return;

        function resolveField(selector) {
            let field = container.querySelector(selector);
            if (field) return field;

            if (container.classList && container.classList.contains("inline-form-row")) {
                const subformRow = container.nextElementSibling;
                if (subformRow && subformRow.classList.contains("inline-subform-row")) {
                    field = subformRow.querySelector(selector);
                    if (field) return field;
                }
            }

            if (container.classList && container.classList.contains("inline-subform-row")) {
                const mainRow = container.previousElementSibling;
                if (mainRow && mainRow.classList.contains("inline-form-row")) {
                    field = mainRow.querySelector(selector);
                    if (field) return field;
                }
            }

            return null;
        }

        const nome = resolveField("[data-cf-nome]");
        const cognome = resolveField("[data-cf-cognome]");
        const dataNascita = resolveField("[data-cf-data-nascita]");
        const sesso = resolveField("[data-cf-sesso]");
        const luogoId = resolveField("[data-cf-luogo-id]");
        const output = resolveField("[data-cf-output]");

        if (!nome || !cognome || !dataNascita || !sesso || !luogoId || !output) return;

        container.dataset.cfReady = "1";

        function refresh() {
            const selectedLuogoOption = luogoId.options ? luogoId.options[luogoId.selectedIndex] : null;
            const codiceCatastale = (
                luogoId.dataset.codiceCatastale ||
                (selectedLuogoOption ? selectedLuogoOption.dataset.codiceCatastale : "") ||
                ""
            );
            const nextValue = generateCodiceFiscale({
                nome: nome.value,
                cognome: cognome.value,
                dataNascita: dataNascita.value,
                sesso: sesso.value,
                codiceCatastale,
            });

            const previousGenerated = output.dataset.generatedValue || "";
            const currentValue = (output.value || "").trim().toUpperCase();

            if (!nextValue) {
                if (!currentValue || currentValue === previousGenerated) {
                    output.value = "";
                    output.dataset.generatedValue = "";
                }
                return;
            }

            if (!currentValue || currentValue === previousGenerated) {
                output.value = nextValue;
                output.dataset.generatedValue = nextValue;
            }
        }

        [nome, cognome, dataNascita, sesso, luogoId].forEach((field) => {
            field.addEventListener("change", refresh);
            field.addEventListener("input", refresh);
        });

        output.addEventListener("input", function () {
            const currentValue = (output.value || "").trim().toUpperCase();
            const generatedValue = output.dataset.generatedValue || "";
            if (currentValue !== generatedValue) {
                output.dataset.generatedValue = generatedValue;
            }
        });

        refresh();
    }

    function init(root) {
        const scope = root || document;
        const hosts = new Set();

        scope.querySelectorAll("[data-cf-output]").forEach(output => {
            const host = output.closest(".inline-form-row, .inline-subform-row, form, .panel-body, .content-card");
            if (host) {
                hosts.add(host);
            }
        });

        hosts.forEach(bindContainer);
    }

    function rebind(root) {
        const scope = root || document;
        scope.querySelectorAll("[data-cf-output]").forEach(output => {
            const host = output.closest(".inline-form-row, .inline-subform-row, form, .panel-body, .content-card");
            if (host) {
                host.removeAttribute("data-cf-ready");
            }
        });
        init(scope);
    }

    window.ArborisCodiceFiscale = { init, rebind };

    document.addEventListener("DOMContentLoaded", function () {
        init(document);

        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!(node instanceof HTMLElement)) return;
                    init(node);
                });
            });
        });

        observer.observe(document.body, { childList: true, subtree: true });
    });
})();
