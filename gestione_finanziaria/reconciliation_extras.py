"""Unpaid extra-service installments offered on the bank reconciliation page."""

from servizi_extra.models import RataServizioExtra

from .services import trova_rate_candidate


def trova_quote_servizi_extra_candidate(movimento):
    if movimento.importo is None or movimento.importo <= 0:
        return []
    rate = RataServizioExtra.objects.filter(pagata=False, importo_finale__gt=0).select_related(
        "iscrizione__studente", "iscrizione__servizio__anno_scolastico",
    ).prefetch_related("iscrizione__studente__relazioni_familiari__familiare__persona")
    return trova_rate_candidate(movimento, rate_pool=rate, tutte_rate_aperte=True, limite=None)
