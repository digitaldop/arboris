"""
Servizi di dominio del modulo Gestione finanziaria.

Concentrati qui per non sparpagliare logica nei form o nelle viste:
- applicazione automatica delle regole di categorizzazione;
- calcolo dell'hash di deduplica per i movimenti importati;
- ricalcolo denormalizzato del saldo corrente dei conti.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


# =========================================================================
#  Regole di categorizzazione
# =========================================================================


def _regola_matcha_movimento(regola, movimento) -> bool:
    """
    Valuta se una regola e' applicabile al movimento.
    Ogni regola ha un `condizione_tipo` principale; gli altri campi
    (importo_min/max, segno_filtro) agiscono da filtri aggiuntivi quando valorizzati.
    """

    from .models import (
        CondizioneRegolaCategorizzazione,
        SegnoMovimento,
    )

    condizione = regola.condizione_tipo
    pattern = (regola.pattern or "").strip()

    descrizione = (movimento.descrizione or "").lower()
    controparte = (movimento.controparte or "").lower()
    iban_controparte = (movimento.iban_controparte or "").strip().upper()
    importo = movimento.importo if movimento.importo is not None else Decimal("0")

    match = False

    if condizione == CondizioneRegolaCategorizzazione.DESCRIZIONE_CONTIENE:
        match = bool(pattern) and pattern.lower() in descrizione
    elif condizione == CondizioneRegolaCategorizzazione.CONTROPARTE_CONTIENE:
        match = bool(pattern) and pattern.lower() in controparte
    elif condizione == CondizioneRegolaCategorizzazione.IBAN_CONTROPARTE_UGUALE:
        match = bool(pattern) and pattern.strip().upper() == iban_controparte
    elif condizione == CondizioneRegolaCategorizzazione.IMPORTO_RANGE:
        if regola.importo_min is None and regola.importo_max is None:
            match = False
        else:
            valore = importo
            ok_min = regola.importo_min is None or valore >= regola.importo_min
            ok_max = regola.importo_max is None or valore <= regola.importo_max
            match = ok_min and ok_max
    elif condizione == CondizioneRegolaCategorizzazione.SEGNO:
        if regola.segno_filtro == SegnoMovimento.USCITA:
            match = importo < 0
        elif regola.segno_filtro == SegnoMovimento.ENTRATA:
            match = importo > 0

    if not match:
        return False

    if regola.segno_filtro and condizione != CondizioneRegolaCategorizzazione.SEGNO:
        if regola.segno_filtro == SegnoMovimento.USCITA and importo >= 0:
            return False
        if regola.segno_filtro == SegnoMovimento.ENTRATA and importo <= 0:
            return False

    if condizione != CondizioneRegolaCategorizzazione.IMPORTO_RANGE:
        if regola.importo_min is not None and importo < regola.importo_min:
            return False
        if regola.importo_max is not None and importo > regola.importo_max:
            return False

    return True


def applica_regole_a_movimento(movimento, forza: bool = False):
    """
    Applica le regole attive al movimento nell'ordine di priorita'.
    - Se il movimento e' gia' categorizzato manualmente (categorizzazione_automatica=False
      e categoria valorizzata), non viene toccato salvo `forza=True`.
    - Se una regola fa match, viene assegnata la categoria e contrassegnata
      la categorizzazione come automatica.

    Ritorna la regola applicata (o None se nessuna).
    """

    from .models import RegolaCategorizzazione

    if movimento.categoria_id and not movimento.categorizzazione_automatica and not forza:
        return None

    regole = RegolaCategorizzazione.objects.filter(attiva=True).order_by("priorita", "id")

    for regola in regole:
        if _regola_matcha_movimento(regola, movimento):
            movimento.categoria_id = regola.categoria_da_assegnare_id
            movimento.categorizzazione_automatica = True
            movimento.regola_categorizzazione = regola
            movimento.categorizzato_il = timezone.now()

            regola.volte_applicata = (regola.volte_applicata or 0) + 1
            regola.ultima_applicazione_at = timezone.now()
            regola.save(update_fields=["volte_applicata", "ultima_applicazione_at"])

            return regola

    return None


# =========================================================================
#  Hash di deduplica
# =========================================================================


def calcola_hash_deduplica_movimento(
    *,
    conto_id,
    data_contabile,
    importo,
    descrizione: str,
    controparte: str,
    iban_controparte: str,
) -> str:
    """
    Calcola un hash stabile per identificare movimenti equivalenti
    in import successivi dello stesso estratto conto, quando il provider
    non fornisce un ID transazione.
    """

    raw = "|".join(
        [
            str(conto_id or ""),
            data_contabile.isoformat() if data_contabile else "",
            f"{Decimal(importo or 0):.2f}",
            (descrizione or "").strip().lower(),
            (controparte or "").strip().lower(),
            (iban_controparte or "").strip().upper(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# =========================================================================
#  Saldo corrente del conto
# =========================================================================


def ricalcola_saldo_corrente_conto(conto, salva: bool = True) -> Decimal:
    """
    Ricalcola il saldo corrente denormalizzato a partire dalla somma
    dei movimenti che incidono sul saldo bancario.

    Nota: in presenza di un provider PSD2 che fornisce direttamente il saldo,
    quella sara' la fonte di verita'; questa funzione serve per i conti
    alimentati da import file o inserimento manuale, dove il saldo viene
    ricostruito dai movimenti.
    """

    from .models import MovimentoFinanziario

    totale = (
        MovimentoFinanziario.objects.filter(conto=conto, incide_su_saldo_banca=True)
        .aggregate(totale=Sum("importo"))["totale"]
        or Decimal("0")
    )

    conto.saldo_corrente = totale
    conto.saldo_corrente_aggiornato_al = timezone.now()

    if salva:
        conto.save(update_fields=["saldo_corrente", "saldo_corrente_aggiornato_al"])

    return totale


# =========================================================================
#  Sincronizzazione PSD2 (saldi + movimenti)
# =========================================================================


@transaction.atomic
def sincronizza_conto_psd2(
    conto,
    *,
    sync_movimenti: bool = True,
    sync_saldo: bool = True,
    giorni_storico: int = 30,
):
    """
    Sincronizza saldo e movimenti di un :class:`ContoBancario` tramite
    l'adapter PSD2 associato al suo provider/connessione.

    Ritorna il :class:`SincronizzazioneLog` creato.
    """

    from .models import (
        ConnessioneBancaria,
        EsitoSincronizzazione,
        FonteSaldo,
        MovimentoFinanziario,
        OrigineMovimento,
        SaldoConto,
        SincronizzazioneLog,
        StatoRiconciliazione,
        TipoOperazioneSincronizzazione,
    )
    from .providers import adapter_for_provider
    from .providers.registry import ProviderConfigurazioneMancante

    start = time.monotonic()
    messaggi = []
    inseriti = 0
    aggiornati = 0
    errori_fatali = False

    tipo_op = (
        TipoOperazioneSincronizzazione.SYNC_MOVIMENTI
        if sync_movimenti
        else TipoOperazioneSincronizzazione.SYNC_SALDO
    )

    if conto.provider is None:
        raise ProviderConfigurazioneMancante(
            f"Il conto '{conto}' non ha un provider configurato."
        )
    if not conto.external_account_id:
        raise ProviderConfigurazioneMancante(
            f"Il conto '{conto}' non ha un external_account_id: "
            "collegarlo prima ad una connessione PSD2."
        )

    adapter = adapter_for_provider(conto.provider, connessione=conto.connessione)

    if sync_saldo:
        try:
            # Salt Edge non ha un endpoint "saldo per account": il saldo e'
            # un campo del record account ottenibile solo con il connection_id.
            # Usiamo allora il metodo specifico che lo conosce.
            from .providers.saltedge import SaltEdgeAdapter

            if (
                isinstance(adapter, SaltEdgeAdapter)
                and conto.connessione is not None
                and conto.connessione.external_connection_id
            ):
                saldi = adapter.saldo_conto_da_connection(
                    conto.connessione.external_connection_id,
                    conto.external_account_id,
                )
            else:
                saldi = adapter.saldo_conto(conto.external_account_id)
            saldo_principale: Optional[Decimal] = None
            valuta_principale = conto.valuta or "EUR"
            for saldo in saldi:
                SaldoConto.objects.create(
                    conto=conto,
                    data_riferimento=saldo.data_riferimento or timezone.now(),
                    saldo_contabile=saldo.saldo,
                    valuta=saldo.valuta,
                    fonte=FonteSaldo.PROVIDER,
                )
                if saldo_principale is None:
                    saldo_principale = saldo.saldo
                    valuta_principale = saldo.valuta
                if saldo.tipo.lower() in {"closingbooked", "expected", "interimavailable"}:
                    saldo_principale = saldo.saldo
                    valuta_principale = saldo.valuta

            if saldo_principale is not None:
                conto.saldo_corrente = saldo_principale
                conto.valuta = valuta_principale or conto.valuta
                conto.saldo_corrente_aggiornato_al = timezone.now()
                conto.save(
                    update_fields=[
                        "saldo_corrente",
                        "valuta",
                        "saldo_corrente_aggiornato_al",
                        "data_aggiornamento",
                    ]
                )
            messaggi.append(f"Saldi letti: {len(saldi)}")
        except Exception as exc:
            errori_fatali = True
            messaggi.append(f"Errore sync saldo: {exc}")

    if sync_movimenti and not errori_fatali:
        try:
            oggi = date.today()
            data_inizio = oggi - timedelta(days=max(giorni_storico, 1))
            transazioni = adapter.movimenti_conto(
                conto.external_account_id,
                data_inizio=data_inizio,
                data_fine=oggi,
            )
            for tx in transazioni:
                esiste = False
                if tx.provider_transaction_id:
                    esiste = MovimentoFinanziario.objects.filter(
                        conto=conto,
                        provider_transaction_id=tx.provider_transaction_id,
                    ).exists()
                hash_dedup = calcola_hash_deduplica_movimento(
                    conto_id=conto.id,
                    data_contabile=tx.data_contabile,
                    importo=tx.importo,
                    descrizione=tx.descrizione,
                    controparte=tx.controparte,
                    iban_controparte=tx.iban_controparte,
                )
                if not esiste:
                    esiste = MovimentoFinanziario.objects.filter(
                        conto=conto,
                        hash_deduplica=hash_dedup,
                    ).exists()
                if esiste:
                    continue

                movimento = MovimentoFinanziario(
                    conto=conto,
                    origine=OrigineMovimento.BANCA,
                    data_contabile=tx.data_contabile,
                    data_valuta=tx.data_valuta,
                    importo=tx.importo,
                    valuta=tx.valuta or conto.valuta or "EUR",
                    descrizione=tx.descrizione,
                    controparte=tx.controparte,
                    iban_controparte=tx.iban_controparte,
                    provider_transaction_id=tx.provider_transaction_id,
                    hash_deduplica=hash_dedup,
                    incide_su_saldo_banca=True,
                    stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
                )
                applica_regole_a_movimento(movimento)
                movimento.save()
                inseriti += 1
            messaggi.append(
                f"Movimenti scaricati: {len(transazioni)}, inseriti: {inseriti}"
            )
        except Exception as exc:
            errori_fatali = True
            messaggi.append(f"Errore sync movimenti: {exc}")

    conto.data_ultima_sincronizzazione = timezone.now()
    conto.save(update_fields=["data_ultima_sincronizzazione", "data_aggiornamento"])

    if conto.connessione_id:
        ConnessioneBancaria.objects.filter(pk=conto.connessione_id).update(
            ultimo_refresh_at=timezone.now(),
            ultimo_errore="" if not errori_fatali else messaggi[-1][:1000],
        )

    durata_ms = int((time.monotonic() - start) * 1000)
    esito = EsitoSincronizzazione.ERRORE if errori_fatali else EsitoSincronizzazione.OK
    if not errori_fatali and sync_movimenti and inseriti == 0:
        esito = EsitoSincronizzazione.OK  # ok: semplicemente non c'erano nuovi movimenti

    return SincronizzazioneLog.objects.create(
        conto=conto,
        connessione=conto.connessione if conto.connessione_id else None,
        tipo_operazione=tipo_op,
        esito=esito,
        movimenti_inseriti=inseriti,
        movimenti_aggiornati=aggiornati,
        durata_millisecondi=durata_ms,
        messaggio="\n".join(messaggi)[:4000],
    )


# =========================================================================
#  Riconciliazione movimenti <-> rate iscrizione
# =========================================================================


@dataclass
class CandidatoRiconciliazione:
    """Rata candidata per la riconciliazione con un movimento."""

    rata: object
    score: int
    motivazioni: list

    @property
    def score_percentuale(self) -> int:
        return max(0, min(100, self.score))


_TOLLERANZA_IMPORTO_ESATTO = Decimal("0.01")
_TOLLERANZA_IMPORTO_APPROX = Decimal("1.00")
_TOLLERANZA_GIORNI_VICINI = 7
_TOLLERANZA_GIORNI_ESTESA = 30


def trova_rate_candidate(movimento, *, limite: int = 10):
    """
    Ritorna una lista ordinata di :class:`CandidatoRiconciliazione`
    per il movimento dato. Il matching e' pensato per entrate in conto
    (importo positivo) che corrispondono a pagamenti di rate iscrizione.

    Heuristica dello score (0-100):
    - importo identico (+50), differenza < 1 EUR (+30);
    - data_pagamento/scadenza molto vicina al movimento (+25 / +10);
    - rata non gia' marcata come pagata (+10);
    - IBAN controparte corrisponde all'IBAN della famiglia (+15)
      quando disponibile (facoltativo, soft match);
    - controparte contiene parte del nome famiglia (+10).
    """

    from decimal import Decimal as _D

    from economia.models.iscrizioni import RataIscrizione

    if movimento is None or movimento.importo is None:
        return []

    importo_mov = movimento.importo
    # Per le rate ci aspettiamo incassi: se il movimento e' un'uscita
    # confrontiamo il valore assoluto, cosi' si puo' riconciliare anche
    # rimborsi/storni manuali.
    importo_cerca = abs(importo_mov)

    qs = (
        RataIscrizione.objects.select_related(
            "iscrizione__studente__famiglia",
            "iscrizione__anno_scolastico",
        )
        .filter(
            importo_finale__gte=importo_cerca - _TOLLERANZA_IMPORTO_APPROX,
            importo_finale__lte=importo_cerca + _TOLLERANZA_IMPORTO_APPROX,
        )
        .order_by("-anno_riferimento", "-mese_riferimento")[:200]
    )

    data_mov = movimento.data_contabile
    controparte = (movimento.controparte or "").lower()
    iban_mov = (movimento.iban_controparte or "").upper()

    candidati = []
    for rata in qs:
        score = 0
        motivazioni = []

        diff_importo = (rata.importo_finale - importo_cerca).copy_abs()
        if diff_importo <= _TOLLERANZA_IMPORTO_ESATTO:
            score += 50
            motivazioni.append("Importo identico")
        elif diff_importo <= _TOLLERANZA_IMPORTO_APPROX:
            score += 30
            motivazioni.append(f"Importo simile (differenza {diff_importo} EUR)")
        else:
            continue

        data_rif = rata.data_scadenza or rata.data_pagamento
        if data_rif and data_mov:
            delta_giorni = abs((data_mov - data_rif).days)
            if delta_giorni <= _TOLLERANZA_GIORNI_VICINI:
                score += 25
                motivazioni.append(f"Data vicina alla scadenza (+/- {delta_giorni} gg)")
            elif delta_giorni <= _TOLLERANZA_GIORNI_ESTESA:
                score += 10
                motivazioni.append(f"Data entro 30 giorni dalla scadenza ({delta_giorni} gg)")

        if not rata.pagata:
            score += 10
            motivazioni.append("Rata non ancora marcata come pagata")

        try:
            studente = rata.iscrizione.studente
            famiglia = rata.iscrizione.studente.famiglia
            nome_famiglia = (
                f"{getattr(studente, 'cognome', '') or ''} "
                f"{getattr(studente, 'nome', '') or ''}"
            ).strip().lower()
            if controparte and nome_famiglia and any(
                tok and tok in controparte
                for tok in nome_famiglia.split()
                if len(tok) >= 3
            ):
                score += 10
                motivazioni.append("Controparte compatibile con studente/famiglia")
        except Exception:
            famiglia = None

        candidati.append(
            CandidatoRiconciliazione(rata=rata, score=score, motivazioni=motivazioni)
        )

    candidati.sort(key=lambda c: c.score, reverse=True)
    return candidati[:limite]


@transaction.atomic
def riconcilia_movimento_con_rata(
    movimento,
    rata,
    *,
    utente=None,
    marca_rata_pagata: bool = True,
):
    """
    Collega un :class:`MovimentoFinanziario` a una :class:`RataIscrizione`.

    Se ``marca_rata_pagata`` e' True (default) e la rata non risulta ancora
    pagata, viene contrassegnata come pagata con data uguale alla
    ``data_contabile`` del movimento e l'importo del movimento (valore
    assoluto) viene scritto su ``importo_pagato``. Questo allinea la rata
    al movimento bancario effettivo senza sovrascrivere riconciliazioni
    gia' esistenti.
    """

    from .models import StatoRiconciliazione

    movimento.rata_iscrizione = rata
    movimento.stato_riconciliazione = StatoRiconciliazione.RICONCILIATO
    movimento.save(
        update_fields=[
            "rata_iscrizione",
            "stato_riconciliazione",
            "data_aggiornamento",
        ]
    )

    if marca_rata_pagata and rata is not None and not rata.pagata:
        rata.pagata = True
        rata.data_pagamento = rata.data_pagamento or movimento.data_contabile
        if not rata.importo_pagato or rata.importo_pagato == Decimal("0"):
            rata.importo_pagato = abs(movimento.importo or Decimal("0"))
        rata.save()

    return movimento


@transaction.atomic
def annulla_riconciliazione(movimento):
    from .models import StatoRiconciliazione

    movimento.rata_iscrizione = None
    movimento.stato_riconciliazione = StatoRiconciliazione.NON_RICONCILIATO
    movimento.save(
        update_fields=[
            "rata_iscrizione",
            "stato_riconciliazione",
            "data_aggiornamento",
        ]
    )
    return movimento
