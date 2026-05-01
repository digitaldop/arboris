"""Contesto template riutilizzabile per sezioni inline a tab (form dettaglio)."""

from sistema.models import SistemaImpostazioniGenerali
from sistema.terminology import get_student_terminology


def scuola_inline_head(*, inline_target, count_telefoni, count_email, count_socials):
    valid = {"telefoni", "email", "socials"}
    active = inline_target if inline_target in valid else "telefoni"
    tabs = [
        {
            "tab_id": "tab-telefoni",
            "scope": "telefoni",
            "label": "Telefoni",
            "count": count_telefoni,
        },
        {
            "tab_id": "tab-email",
            "scope": "email",
            "label": "Email",
            "count": count_email,
        },
        {
            "tab_id": "tab-socials",
            "scope": "socials",
            "label": "Social",
            "count": count_socials,
        },
    ]
    for t in tabs:
        t["is_active"] = t["scope"] == active
    label_map = {
        "telefoni": "Modifica Telefoni",
        "email": "Modifica Email",
        "socials": "Modifica Social",
    }
    return {
        "scuola_inline_tabs": tabs,
        "scuola_inline_edit_label": label_map.get(active, "Modifica Telefoni"),
    }


def studente_inline_head(*, inline_target, count_iscrizioni, count_documenti, count_parenti=0):
    valid = {"iscrizioni", "documenti", "parenti"}
    active = inline_target if inline_target in valid else "iscrizioni"
    tabs = [
        {
            "tab_id": "tab-iscrizioni",
            "scope": "iscrizioni",
            "label": "Iscrizioni",
            "count": count_iscrizioni,
            "base_label": "Iscrizioni",
        },
        {
            "tab_id": "tab-parenti",
            "scope": "parenti",
            "label": "Parenti",
            "count": count_parenti,
            "base_label": "Parenti",
        },
        {
            "tab_id": "tab-documenti",
            "scope": "documenti",
            "label": "Documenti",
            "count": count_documenti,
            "base_label": "Documenti",
        },
    ]
    for t in tabs:
        t["is_active"] = t["scope"] == active
    if active == "documenti":
        edit_label = "Modifica Documenti"
    elif active == "parenti":
        edit_label = "Parenti"
    else:
        edit_label = "Modifica Iscrizioni"
    return {
        "studente_inline_tabs": tabs,
        "studente_inline_edit_label": edit_label,
    }


def famiglia_inline_head(
    *,
    active_inline_tab,
    count_familiari,
    count_studenti,
    count_documenti,
    related_famiglia_studenti_doc_count,
):
    """Tab inline scheda famiglia (studenti / familiari / documenti)."""
    valid = {"familiari", "studenti", "documenti"}
    active = active_inline_tab if active_inline_tab in valid else "studenti"

    imp = SistemaImpostazioniGenerali.objects.first()
    studenti_plural = get_student_terminology(getattr(imp, "terminologia_studente", None))["selected_plural"]

    tabs = [
        {
            "tab_id": "tab-studenti",
            "scope": "studenti",
            "label": studenti_plural,
            "count": count_studenti,
            "base_label": studenti_plural,
        },
        {
            "tab_id": "tab-familiari",
            "scope": "familiari",
            "label": "Familiari",
            "count": count_familiari,
            "base_label": "Familiari",
        },
        {
            "tab_id": "tab-documenti",
            "scope": "documenti",
            "label": "Documenti",
            "count": count_documenti,
            "base_label": "Documenti",
            "show_related_doc_count": True,
            "related_document_count": related_famiglia_studenti_doc_count,
        },
    ]
    for t in tabs:
        t["is_active"] = t["scope"] == active

    if active == "studenti":
        edit_label = f"Modifica {studenti_plural}"
    elif active == "documenti":
        edit_label = "Modifica Documenti"
    else:
        edit_label = "Modifica Familiari"

    return {
        "famiglia_inline_tabs": tabs,
        "famiglia_inline_edit_label": edit_label,
    }
