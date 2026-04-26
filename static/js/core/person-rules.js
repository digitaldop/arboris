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

    return {
        normalizeText: normalizeText,
        inferSexFromFirstName: inferSexFromFirstName,
        inferSexFromRelationLabel: inferSexFromRelationLabel,
    };
})();
