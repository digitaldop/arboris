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
from django.db.models import F
from django.utils import timezone

from ..models import (
    ContoBancario,
    EsitoSincronizzazione,
    MovimentoFinanziario,
    OrigineMovimento,
    ProviderBancario,
    RegolaCategorizzazione,
    SincronizzazioneLog,
    StatoRiconciliazione,
    TipoOperazioneSincronizzazione,
)
from ..services import (
    calcola_hash_deduplica_movimento,
    ricalcola_saldo_corrente_conto,
    riconcilia_movimento_automaticamente,
    _regola_matcha_movimento,
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
    riconcilia_automaticamente: bool = True,
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
    parsed_con_hash = [
        (
            parsed,
            calcola_hash_deduplica_movimento(
                conto_id=conto.id,
                data_contabile=parsed.data_contabile,
                importo=parsed.importo,
                descrizione=parsed.descrizione,
                controparte=parsed.controparte,
                iban_controparte=parsed.iban_controparte,
            ),
        )
        for parsed in movimenti_parsed
    ]
    existing_hashes, existing_tx_ids = _duplicati_esistenti(conto, parsed_con_hash)
    imported_hashes = set()
    imported_tx_ids = set()
    regole_categorizzazione = list(
        RegolaCategorizzazione.objects.filter(attiva=True).order_by("priorita", "id")
    )
    regole_applicate = {}

    for parsed, hash_dedup in parsed_con_hash:
        provider_tx_id = parsed.provider_transaction_id or ""
        if (
            hash_dedup in existing_hashes
            or hash_dedup in imported_hashes
            or (provider_tx_id and provider_tx_id in existing_tx_ids)
            or (provider_tx_id and provider_tx_id in imported_tx_ids)
        ):
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

        regola_applicata = _applica_regole_precaricate(
            movimento,
            regole_categorizzazione,
        )
        if regola_applicata is not None:
            regole_applicate[regola_applicata.pk] = regole_applicate.get(regola_applicata.pk, 0) + 1
        movimento.save()
        if riconcilia_automaticamente:
            candidato_riconciliazione = riconcilia_movimento_automaticamente(movimento)
            if candidato_riconciliazione is not None:
                risultato.riconciliati += 1

        risultato.inseriti += 1
        risultato.movimenti_ids.append(movimento.id)
        imported_hashes.add(hash_dedup)
        if provider_tx_id:
            imported_tx_ids.add(provider_tx_id)

    ricalcola_saldo_corrente_conto(conto)
    _aggiorna_statistiche_regole(regole_applicate)

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
            f"File: {nome_file}; parser: {parser.nome_formato}; "
            f"riconciliazione automatica: {'attiva' if riconcilia_automaticamente else 'disattivata'}"
            if nome_file
            else (
                f"Parser: {parser.nome_formato}; "
                f"riconciliazione automatica: {'attiva' if riconcilia_automaticamente else 'disattivata'}"
            )
        ),
    )

    conto.data_ultima_sincronizzazione = timezone.now()
    conto.save(update_fields=["data_ultima_sincronizzazione", "data_aggiornamento"])

    return risultato


def _applica_regole_precaricate(
    movimento: MovimentoFinanziario,
    regole: list[RegolaCategorizzazione],
) -> Optional[RegolaCategorizzazione]:
    if movimento.categoria_id and not movimento.categorizzazione_automatica:
        return None

    for regola in regole:
        if _regola_matcha_movimento(regola, movimento):
            movimento.categoria_id = regola.categoria_da_assegnare_id
            movimento.categorizzazione_automatica = True
            movimento.regola_categorizzazione = regola
            movimento.categorizzato_il = timezone.now()
            return regola

    return None


def _aggiorna_statistiche_regole(regole_applicate: dict[int, int]) -> None:
    if not regole_applicate:
        return

    now = timezone.now()
    for regola_id, count in regole_applicate.items():
        RegolaCategorizzazione.objects.filter(pk=regola_id).update(
            volte_applicata=F("volte_applicata") + count,
            ultima_applicazione_at=now,
        )


def _duplicati_esistenti(
    conto: ContoBancario, parsed_con_hash: list[tuple[ParsedMovimento, str]]
) -> tuple[set[str], set[str]]:
    hashes = {hash_dedup for _parsed, hash_dedup in parsed_con_hash if hash_dedup}
    provider_tx_ids = {
        parsed.provider_transaction_id
        for parsed, _hash_dedup in parsed_con_hash
        if parsed.provider_transaction_id
    }

    existing_hashes = set()
    if hashes:
        existing_hashes = set(
            MovimentoFinanziario.objects.filter(
                conto=conto,
                hash_deduplica__in=hashes,
            ).values_list("hash_deduplica", flat=True)
        )

    existing_tx_ids = set()
    if provider_tx_ids:
        existing_tx_ids = set(
            MovimentoFinanziario.objects.filter(
                conto=conto,
                provider_transaction_id__in=provider_tx_ids,
            ).values_list("provider_transaction_id", flat=True)
        )

    return existing_hashes, existing_tx_ids


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
        f"riconciliati: {risultato.riconciliati}, duplicati: {risultato.duplicati}, errori: {risultato.errori}"
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
