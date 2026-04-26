window.ArborisPersonRules = (function () {
    function normalizeText(value) {
        return (value || "")
            .toString()
            .trim()
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "");
    }

    function inferSexFromFirstName(value) {
        const firstName = normalizeText(value).split(/\s+/)[0] || "";
        if (!firstName) {
            return "";
        }

        const commonMaleEndingInA = [
            "andrea",
            "luca",
            "nicola",
            "mattia",
            "elia",
            "tobia",
            "enea",
            "gianluca",
        ];

        if (commonMaleEndingInA.includes(firstName)) {
            return "M";
        }

        if (firstName.endsWith("a")) {
            return "F";
        }

        if (firstName.endsWith("o")) {
            return "M";
        }

        return "";
    }

    function inferSexFromRelationLabel(value) {
        const label = normalizeText(value);
        if (!label) {
            return "";
        }

        const maleTokens = [
            "padre",
            "nonno",
            "zio",
            "fratello",
            "marito",
            "compagno",
            "figlio",
            "patrigno",
            "suocero",
            "bisnonno",
            "cognato",
            "tutore",
        ];
        const femaleTokens = [
            "madre",
            "nonna",
            "zia",
            "sorella",
            "moglie",
            "compagna",
            "figlia",
            "matrigna",
            "suocera",
            "bisnonna",
            "cognata",
            "tutrice",
        ];

        if (maleTokens.some(function (token) { return label.includes(token); })) {
            return "M";
        }
        if (femaleTokens.some(function (token) { return label.includes(token); })) {
            return "F";
        }

        return "";
    }

    function resolveElement(elementOrSelector, root) {
        if (!elementOrSelector) {
            return null;
        }

        if (typeof elementOrSelector === "string") {
            return (root || document).querySelector(elementOrSelector);
        }

        return elementOrSelector;
    }

    function applyInferredSex(sexSelect, inferredSex, options) {
        options = options || {};

        if (!sexSelect || !inferredSex) {
            return false;
        }

        if (sexSelect.value) {
            if (sexSelect.value === inferredSex) {
                return false;
            }

            if (!options.overwriteExisting) {
                return false;
            }
        }

        sexSelect.value = inferredSex;
        sexSelect.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
    }

    function bindSexFromFirstName(options) {
        options = options || {};

        const root = options.root || document;
        const nameInput = resolveElement(options.nameInput || options.nameSelector, root);
        const sexSelect = resolveElement(options.sexSelect || options.sexSelector, root);
        const bindFlag = options.bindFlag || "personRulesFirstNameBound";
        const events = options.events || ["change", "input"];

        function sync() {
            if (!nameInput || !sexSelect) {
                return false;
            }

            return applyInferredSex(sexSelect, inferSexFromFirstName(nameInput.value), options);
        }

        if (!nameInput || !sexSelect) {
            return { sync: sync };
        }

        if (nameInput.dataset[bindFlag] !== "1") {
            nameInput.dataset[bindFlag] = "1";
            events.forEach(function (eventName) {
                nameInput.addEventListener(eventName, sync);
            });
        }

        sync();
        return { sync: sync };
    }

    function bindSexFromRelation(options) {
        options = options || {};

        const root = options.root || document;
        const relationSelect = resolveElement(options.relationSelect || options.relationSelector, root);
        const sexSelect = resolveElement(options.sexSelect || options.sexSelector, root);
        const bindFlag = options.bindFlag || "personRulesRelationBound";
        const events = options.events || ["change"];

        function sync() {
            if (!relationSelect || !sexSelect) {
                return false;
            }

            const selectedOption = relationSelect.options[relationSelect.selectedIndex];
            const relationLabel = selectedOption ? selectedOption.textContent : "";
            return applyInferredSex(sexSelect, inferSexFromRelationLabel(relationLabel), options);
        }

        if (!relationSelect || !sexSelect) {
            return { sync: sync };
        }

        if (relationSelect.dataset[bindFlag] !== "1") {
            relationSelect.dataset[bindFlag] = "1";
            events.forEach(function (eventName) {
                relationSelect.addEventListener(eventName, sync);
            });
        }

        sync();
        return { sync: sync };
    }

    return {
        applyInferredSex: applyInferredSex,
        bindSexFromFirstName: bindSexFromFirstName,
        bindSexFromRelation: bindSexFromRelation,
        normalizeText: normalizeText,
        inferSexFromFirstName: inferSexFromFirstName,
        inferSexFromRelationLabel: inferSexFromRelationLabel,
    };
})();
