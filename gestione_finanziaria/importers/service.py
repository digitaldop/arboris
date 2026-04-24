"""
Orchestratore del processo di import di estratti conto.

Riceve in input:
- un parser concreto (CAMT.053, CSV, ...);
- i byte del file da elaborare;
- il conto bancario di destinazione;
- opzionalmente il provider di origine (per bookkeeping del campo ``origine``).

Si occupa di:
- scorrere i :class:`ParsedMovimento` prodotti dal parser;
- calcolare l'``hash_deduplica`` ed evitare i duplicati (stesso hash o
  stesso ``provider_transaction_id`` per il conto);
- persistere i nuovi :class:`MovimentoFinanziario` con
  ``origine = import_file`` e ``incide_su_saldo_banca = True``;
- applicare le regole di categorizzazione automatica;
- registrare un :class:`SincronizzazioneLog` con gli esiti;
- ricalcolare il saldo denormalizzato del conto.
"""

from __future__ import annotations

import time
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from ..models import (
    ContoBancario,
    EsitoSincronizzazione,
    MovimentoFinanziario,
    OrigineMovimento,
    ProviderBancario,
    SincronizzazioneLog,
    StatoRiconciliazione,
    TipoOperazioneSincronizzazione,
)
from ..services import (
    applica_regole_a_movimento,
    calcola_hash_deduplica_movimento,
    ricalcola_saldo_corrente_conto,
)
from .base import BaseParser, ParsedMovimento, RisultatoImport


@transaction.atomic
def importa_movimenti_da_file(
    *,
    parser: BaseParser,
    raw_bytes: bytes,
    conto: ContoBancario,
    provider: Optional[ProviderBancario] = None,
    nome_file: str = "",
) -> RisultatoImport:
    risultato = RisultatoImport()
    start = time.monotonic()

    try:
        parsed_iter: Iterable[ParsedMovimento] = parser.parse(raw_bytes)
    except Exception as exc:
        risultato.errori += 1
        risultato.aggiungi_messaggio(f"Errore di parsing: {exc}")
        _crea_log_import(
            conto=conto,
            risultato=risultato,
            durata_ms=int((time.monotonic() - start) * 1000),
            esito=EsitoSincronizzazione.ERRORE,
            messaggio_extra=f"File: {nome_file}" if nome_file else "",
        )
        return risultato

    movimenti_parsed = list(parsed_iter)
    risultato.totale_letti = len(movimenti_parsed)

    for parsed in movimenti_parsed:
        hash_dedup = calcola_hash_deduplica_movimento(
            conto_id=conto.id,
            data_contabile=parsed.data_contabile,
            importo=parsed.importo,
            descrizione=parsed.descrizione,
            controparte=parsed.controparte,
            iban_controparte=parsed.iban_controparte,
        )

        if _esiste_duplicato(conto, parsed, hash_dedup):
            risultato.duplicati += 1
            continue

        movimento = MovimentoFinanziario(
            conto=conto,
            origine=OrigineMovimento.IMPORT_FILE,
            data_contabile=parsed.data_contabile,
            data_valuta=parsed.data_valuta,
            importo=parsed.importo,
            valuta=parsed.valuta or conto.valuta or "EUR",
            descrizione=parsed.descrizione,
            controparte=parsed.controparte,
            iban_controparte=parsed.iban_controparte,
            provider_transaction_id=parsed.provider_transaction_id,
            hash_deduplica=hash_dedup,
            incide_su_saldo_banca=True,
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        applica_regole_a_movimento(movimento)
        movimento.save()

        risultato.inseriti += 1
        risultato.movimenti_ids.append(movimento.id)

    ricalcola_saldo_corrente_conto(conto)

    durata_ms = int((time.monotonic() - start) * 1000)
    esito = EsitoSincronizzazione.OK
    if risultato.errori:
        esito = EsitoSincronizzazione.ERRORE
    elif risultato.totale_letti and not risultato.inseriti:
        esito = EsitoSincronizzazione.PARZIALE

    _crea_log_import(
        conto=conto,
        risultato=risultato,
        durata_ms=durata_ms,
        esito=esito,
        messaggio_extra=(
            f"File: {nome_file}; parser: {parser.nome_formato}"
            if nome_file
            else f"Parser: {parser.nome_formato}"
        ),
    )

    conto.data_ultima_sincronizzazione = timezone.now()
    conto.save(update_fields=["data_ultima_sincronizzazione", "data_aggiornamento"])

    return risultato


def _esiste_duplicato(
    conto: ContoBancario, parsed: ParsedMovimento, hash_dedup: str
) -> bool:
    if parsed.provider_transaction_id:
        esiste_tx = MovimentoFinanziario.objects.filter(
            conto=conto,
            provider_transaction_id=parsed.provider_transaction_id,
        ).exists()
        if esiste_tx:
            return True

    esiste_hash = MovimentoFinanziario.objects.filter(
        conto=conto,
        hash_deduplica=hash_dedup,
    ).exists()
    return esiste_hash


def _crea_log_import(
    *,
    conto: ContoBancario,
    risultato: RisultatoImport,
    durata_ms: int,
    esito: str,
    messaggio_extra: str = "",
) -> SincronizzazioneLog:
    pezzi = []
    pezzi.append(
        f"Letti: {risultato.totale_letti}, inseriti: {risultato.inseriti}, "
        f"duplicati: {risultato.duplicati}, errori: {risultato.errori}"
    )
    if messaggio_extra:
        pezzi.append(messaggio_extra)
    if risultato.messaggi:
        pezzi.extend(risultato.messaggi[:10])

    return SincronizzazioneLog.objects.create(
        conto=conto,
        connessione=None,
        tipo_operazione=TipoOperazioneSincronizzazione.IMPORT_FILE,
        esito=esito,
        movimenti_inseriti=risultato.inseriti,
        movimenti_aggiornati=risultato.aggiornati,
        durata_millisecondi=durata_ms,
        messaggio="\n".join(pezzi),
    )
