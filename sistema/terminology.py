STUDENT_TERM_OPTIONS = {
    "studente": {
        "singular": "Studente",
        "plural": "Studenti",
    },
    "alunno": {
        "singular": "Alunno",
        "plural": "Alunni",
    },
    "bambino": {
        "singular": "Bambino",
        "plural": "Bambini",
    },
}

DEFAULT_STUDENT_TERM = "studente"

FAMILY_MEMBER_TERM_OPTIONS = {
    "familiare": {
        "singular": "Familiare",
        "plural": "Familiari",
    },
    "genitore": {
        "singular": "Genitore",
        "plural": "Genitori",
    },
    "parente": {
        "singular": "Parente",
        "plural": "Parenti",
    },
}

DEFAULT_FAMILY_MEMBER_TERM = "familiare"

EDUCATOR_TERM_OPTIONS = {
    "educatore": {
        "singular": "Educatore",
        "plural": "Educatori",
    },
    "maestro": {
        "singular": "Maestro",
        "plural": "Maestri",
    },
    "insegnante": {
        "singular": "Insegnante",
        "plural": "Insegnanti",
    },
}

DEFAULT_EDUCATOR_TERM = "educatore"


def _terminology_payload(options, default_key, choice):
    selected_key = choice if choice in options else default_key
    selected = options[selected_key]

    return {
        "selected_key": selected_key,
        "selected_singular": selected["singular"],
        "selected_plural": selected["plural"],
        "selected_singular_lower": selected["singular"].lower(),
        "selected_plural_lower": selected["plural"].lower(),
        "selected_singular_upper": selected["singular"].upper(),
        "selected_plural_upper": selected["plural"].upper(),
    }


def get_student_terminology(choice=None):
    payload = _terminology_payload(STUDENT_TERM_OPTIONS, DEFAULT_STUDENT_TERM, choice)

    payload["replacements"] = [
        {"from": "STUDENTI", "to": payload["selected_plural_upper"]},
        {"from": "STUDENTE", "to": payload["selected_singular_upper"]},
        {"from": "Studenti", "to": payload["selected_plural"]},
        {"from": "Studente", "to": payload["selected_singular"]},
        {"from": "studenti", "to": payload["selected_plural_lower"]},
        {"from": "studente", "to": payload["selected_singular_lower"]},
    ]
    return payload


def get_family_member_terminology(choice=None):
    return _terminology_payload(FAMILY_MEMBER_TERM_OPTIONS, DEFAULT_FAMILY_MEMBER_TERM, choice)


def get_educator_terminology(choice=None):
    return _terminology_payload(EDUCATOR_TERM_OPTIONS, DEFAULT_EDUCATOR_TERM, choice)
