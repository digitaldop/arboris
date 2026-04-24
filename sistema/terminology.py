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


def get_student_terminology(choice=None):
    selected_key = choice if choice in STUDENT_TERM_OPTIONS else DEFAULT_STUDENT_TERM
    selected = STUDENT_TERM_OPTIONS[selected_key]

    return {
        "selected_key": selected_key,
        "selected_singular": selected["singular"],
        "selected_plural": selected["plural"],
        "selected_singular_lower": selected["singular"].lower(),
        "selected_plural_lower": selected["plural"].lower(),
        "selected_singular_upper": selected["singular"].upper(),
        "selected_plural_upper": selected["plural"].upper(),
        "replacements": [
            {"from": "STUDENTI", "to": selected["plural"].upper()},
            {"from": "STUDENTE", "to": selected["singular"].upper()},
            {"from": "Studenti", "to": selected["plural"]},
            {"from": "Studente", "to": selected["singular"]},
            {"from": "studenti", "to": selected["plural"].lower()},
            {"from": "studente", "to": selected["singular"].lower()},
        ],
    }
