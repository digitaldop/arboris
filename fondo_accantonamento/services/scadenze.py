"""
Generazione scadenze di versamento periodico a partire da data e periodicità.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Tuple

from dateutil.relativedelta import relativedelta

from ..models import (
    MovimentoFondo,
    PeriodicitaVersamento,
    PianoAccantonamento,
    ScadenzaVersamento,
    StatoScadenza,
    TipoModalitaPiano,
    TipoMovimentoFondo,
)


def mesi_salto_da_periodicita(periodicita: str) -> int:
    m = {
        PeriodicitaVersamento.MENSILE: 1,
        PeriodicitaVersamento.BIMESTRALE: 2,
        PeriodicitaVersamento.TRIMESTRALE: 3,
        PeriodicitaVersamento.SEMESTRALE: 6,
        PeriodicitaVersamento.ANNUALE: 12,
    }
    return m.get(periodicita, 1)


def _limite_geneazione(piano: PianoAccantonamento) -> date:
    if piano.anno_scolastico and piano.anno_scolastico.data_fine:
        return piano.anno_scolastico.data_fine
    if piano.sempre_attivo and piano.data_primo_versamento:
        lim = piano.data_primo_versamento + relativedelta(years=10)
        return lim if lim < date(2099, 12, 31) else date(2099, 12, 31)
    return date(2099, 12, 31)


def genera_scadenze_periodiche(
    piano: PianoAccantonamento,
    *,
    rigenera_pianificati: bool = True,
) -> Tuple[int, str]:
    """
    Crea righe :class:`ScadenzaVersamento` fino al termine dell'anno scolastico.

    Ritorna (numero creato, messaggio).
    """
    if piano.modalita not in (
        TipoModalitaPiano.VERSAMENTI_PERIODICI,
        TipoModalitaPiano.MISTO,
    ):
        return 0, "La modalita' del piano non prevede versamenti periodici automatici."
    if not piano.data_primo_versamento or not piano.importo_versamento_periodico:
        return 0, "Imposta data del primo versamento, importo e periodicita' prima di generare le scadenze."
    if not piano.periodicita:
        return 0, "Seleziona la periodicita' (mensile, bimestrale, ...)."

    if rigenera_pianificati:
        piano.scadenze.filter(stato=StatoScadenza.PIANIFICATO).delete()

    mesi = mesi_salto_da_periodicita(piano.periodicita)
    limite = _limite_geneazione(piano)
    d = piano.data_primo_versamento
    importo = piano.importo_versamento_periodico or Decimal("0")
    creati = 0
    while d <= limite:
        _, was_created = ScadenzaVersamento.objects.get_or_create(
            piano=piano,
            data_scadenza=d,
            defaults={
                "importo_previsto": importo,
                "stato": StatoScadenza.PIANIFICATO,
            },
        )
        if was_created:
            creati += 1
        d = d + relativedelta(months=mesi)

    return creati, f"Scadenze generate/aggiornate: {creati} (fino a {limite})."


def soddisfa_scadenza_con_versamento(
    scadenza: ScadenzaVersamento,
    *,
    data_effettiva: date,
) -> MovimentoFondo:
    if scadenza.stato != StatoScadenza.PIANIFICATO:
        raise ValueError("La scadenza non e' in stato pianificato.")
    m = MovimentoFondo.objects.create(
        piano=scadenza.piano,
        tipo=TipoMovimentoFondo.VERSAMENTO,
        data=data_effettiva,
        importo=scadenza.importo_previsto,
        note="Versamento su scadenza periodica",
        scadenza_versamento=scadenza,
    )
    scadenza.stato = StatoScadenza.SODDISFATTO
    scadenza.movimento_versamento = m
    scadenza.save(update_fields=["stato", "movimento_versamento"])
    return m
