(function () {
    const STOP_WORDS = new Set([
        "al",
        "allo",
        "alla",
        "ai",
        "agli",
        "alle",
        "da",
        "dal",
        "dalla",
        "dei",
        "degli",
        "del",
        "dell",
        "della",
        "delle",
        "di",
        "e",
        "ed",
        "file",
        "il",
        "i",
        "la",
        "le",
        "lo",
        "modulo",
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "scansione",
        "scheda",
        "un",
        "una",
    ]);

    function normalizeText(value) {
        return String(value || "")
            .replace(/\.[^.\\/]+$/, " ")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, " ")
            .trim()
            .replace(/\s+/g, " ");
    }

    function tokenize(value) {
        const normalized = normalizeText(value);
        if (!normalized) {
            return [];
        }

        return normalized
            .split(" ")
            .filter(function (token) {
                return token.length >= 3 && !STOP_WORDS.has(token);
            });
    }

    function selectedFileName(input) {
        if (!input) {
            return "";
        }

        if (input.files && input.files.length && input.files[0].name) {
            return input.files[0].name;
        }

        const value = input.value || "";
        return value.split(/[\\/]/).pop();
    }

    function findTipoDocumentoSelect(input) {
        const selectors = [
            'select[name$="-tipo_documento"]',
            'select[name="tipo_documento"]',
            'select[id$="tipo_documento"]',
        ];
        const containers = [
            input.closest("tr"),
            input.closest(".inline-form-row"),
            input.closest(".panel"),
            input.closest("form"),
        ].filter(Boolean);

        for (const container of containers) {
            for (const selector of selectors) {
                const select = container.querySelector(selector);
                if (select) {
                    return select;
                }
            }
        }

        return null;
    }

    function scoreOption(fileName, optionLabel) {
        const fileNormalized = normalizeText(fileName);
        const optionNormalized = normalizeText(optionLabel);
        const fileTokens = tokenize(fileName);
        const optionTokens = tokenize(optionLabel);

        if (!fileNormalized || !optionNormalized || !optionTokens.length) {
            return 0;
        }

        let score = 0;
        let matchedTokens = 0;

        if (fileNormalized.includes(optionNormalized)) {
            score += 80;
        }

        optionTokens.forEach(function (optionToken) {
            const exactMatch = fileTokens.includes(optionToken);
            const partialMatch = !exactMatch && fileTokens.some(function (fileToken) {
                return (
                    optionToken.length >= 4 &&
                    fileToken.length >= 4 &&
                    (fileToken.includes(optionToken) || optionToken.includes(fileToken))
                );
            });

            if (exactMatch) {
                matchedTokens += 1;
                score += 12 + Math.min(optionToken.length, 12);
            } else if (partialMatch) {
                matchedTokens += 1;
                score += 7 + Math.min(optionToken.length, 8);
            }
        });

        if (!matchedTokens) {
            return 0;
        }

        score += Math.round((matchedTokens / optionTokens.length) * 20);
        return score;
    }

    function bestTipoDocumentoOption(fileName, select) {
        let bestOption = null;
        let bestScore = 0;

        Array.from(select.options || []).forEach(function (option) {
            if (!option.value) {
                return;
            }

            const score = scoreOption(fileName, option.textContent || "");
            if (score > bestScore) {
                bestScore = score;
                bestOption = option;
            }
        });

        return bestScore >= 18 ? bestOption : null;
    }

    function applyDocumentTypeFromFile(input) {
        const fileName = selectedFileName(input);
        if (!fileName) {
            return false;
        }

        const select = findTipoDocumentoSelect(input);
        if (!select || select.disabled || (select.dataset.documentTypeManual === "1" && select.value)) {
            return false;
        }

        const option = bestTipoDocumentoOption(fileName, select);
        if (!option || select.value === option.value) {
            return false;
        }

        select.dataset.documentTypeAutoselecting = "1";
        select.value = option.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        delete select.dataset.documentTypeAutoselecting;
        select.dataset.documentTypeAutoselected = "1";
        return true;
    }

    function isDocumentFileInput(input) {
        if (!input || input.type !== "file") {
            return false;
        }

        return Boolean(findTipoDocumentoSelect(input));
    }

    function init(root) {
        const targetRoot = root || document;
        if (!targetRoot || targetRoot.dataset?.documentTypeAutoselectReady === "1") {
            return;
        }

        if (targetRoot.dataset) {
            targetRoot.dataset.documentTypeAutoselectReady = "1";
        }

        targetRoot.addEventListener("change", function (event) {
            const target = event.target;

            if (target && target.matches && target.matches('select[name$="-tipo_documento"], select[name="tipo_documento"], select[id$="tipo_documento"]')) {
                if (target.dataset.documentTypeAutoselecting === "1") {
                    return;
                }
                target.dataset.documentTypeManual = "1";
                return;
            }

            if (isDocumentFileInput(target)) {
                applyDocumentTypeFromFile(target);
            }
        });
    }

    window.ArborisDocumentTypeAutoselect = {
        init: init,
        normalizeText: normalizeText,
        tokenize: tokenize,
        scoreOption: scoreOption,
        bestTipoDocumentoOption: bestTipoDocumentoOption,
        applyDocumentTypeFromFile: applyDocumentTypeFromFile,
    };

    document.addEventListener("DOMContentLoaded", function () {
        init(document);
    });
})();
