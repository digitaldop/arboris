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
        "gruppo_classe": _crud_triplet(
            "crea_gruppo_classe",
            "modifica_gruppo_classe",
            "elimina_gruppo_classe",
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
        "tariffa_scambio_retta": _crud_triplet(
            "crea_tariffa_scambio_retta",
            "modifica_tariffa_scambio_retta",
            "elimina_tariffa_scambio_retta",
        ),
        "ruolo_permessi": _crud_triplet(
            "crea_ruolo_utente",
            "modifica_ruolo_utente",
            "elimina_ruolo_utente",
        ),
        "categoria_spesa": _crud_triplet(
            "crea_categoria_spesa",
            "modifica_categoria_spesa",
            "elimina_categoria_spesa",
        ),
        "categoria_finanziaria": _crud_triplet(
            "crea_categoria_finanziaria",
            "modifica_categoria_finanziaria",
            "elimina_categoria_finanziaria",
        ),
        "fornitore": _crud_triplet(
            "crea_fornitore",
            "modifica_fornitore",
            "elimina_fornitore",
        ),
        "conto_bancario": _crud_triplet(
            "crea_conto_bancario",
            "modifica_conto_bancario",
            "elimina_conto_bancario",
        ),
        "movimento_finanziario": _crud_triplet(
            "crea_movimento_manuale",
            "modifica_movimento_finanziario",
            "elimina_movimento_finanziario",
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
        "tipo_contratto": _crud_triplet(
            "crea_tipo_contratto_dipendente",
            "modifica_tipo_contratto_dipendente",
            "elimina_tipo_contratto_dipendente",
        ),
    }
