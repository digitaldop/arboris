"""URL paths for related-entity CRUD popups (single source of truth for JS)."""

from functools import lru_cache

from django.urls import reverse

# Must match placeholder used in static/js/core/related-entity-routes.js
ID_PLACEHOLDER = "__ID__"


def _crud_triplet(crea_name: str, modifica_name: str, elimina_name: str) -> dict[str, str]:
    return {
        "add": reverse(crea_name),
        "edit": reverse(modifica_name, kwargs={"pk": 0}).replace("/0/", f"/{ID_PLACEHOLDER}/"),
        "delete": reverse(elimina_name, kwargs={"pk": 0}).replace("/0/", f"/{ID_PLACEHOLDER}/"),
    }


@lru_cache(maxsize=1)
def build_popup_manifest() -> dict[str, dict[str, str]]:
    """Keys match data-related-type / logical entity names used in form JavaScript."""
    return {
        "relazione_familiare": _crud_triplet(
            "crea_relazione_familiare",
            "modifica_relazione_familiare",
            "elimina_relazione_familiare",
        ),
        "tipo_documento": _crud_triplet(
            "crea_tipo_documento",
            "modifica_tipo_documento",
            "elimina_tipo_documento",
        ),
        "indirizzo": _crud_triplet(
            "crea_indirizzo",
            "modifica_indirizzo",
            "elimina_indirizzo",
        ),
        "anno_scolastico": _crud_triplet(
            "crea_anno_scolastico",
            "modifica_anno_scolastico",
            "elimina_anno_scolastico",
        ),
        "classe": _crud_triplet(
            "crea_classe",
            "modifica_classe",
            "elimina_classe",
        ),
        "stato_iscrizione": _crud_triplet(
            "crea_stato_iscrizione",
            "modifica_stato_iscrizione",
            "elimina_stato_iscrizione",
        ),
        "condizione_iscrizione": _crud_triplet(
            "crea_condizione_iscrizione",
            "modifica_condizione_iscrizione",
            "elimina_condizione_iscrizione",
        ),
        "agevolazione": _crud_triplet(
            "crea_agevolazione",
            "modifica_agevolazione",
            "elimina_agevolazione",
        ),
        "metodo_pagamento": _crud_triplet(
            "crea_metodo_pagamento",
            "modifica_metodo_pagamento",
            "elimina_metodo_pagamento",
        ),
        "studente": _crud_triplet(
            "crea_studente",
            "modifica_studente",
            "elimina_studente",
        ),
        "famiglia": _crud_triplet(
            "crea_famiglia",
            "modifica_famiglia",
            "elimina_famiglia",
        ),
        "stato_relazione_famiglia": _crud_triplet(
            "crea_stato_relazione_famiglia",
            "modifica_stato_relazione_famiglia",
            "elimina_stato_relazione_famiglia",
        ),
        "parametro_calcolo": _crud_triplet(
            "crea_parametro_calcolo_stipendio",
            "modifica_parametro_calcolo_stipendio",
            "elimina_parametro_calcolo_stipendio",
        ),
    }
