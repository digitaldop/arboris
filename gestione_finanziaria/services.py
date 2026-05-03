"""
Servizi di dominio del modulo Gestione finanziaria.

Concentrati qui per non sparpagliare logica nei form o nelle viste:
- applicazione automatica delle regole di categorizzazione;
- calcolo dell'hash di deduplica per i movimenti importati;
- ricalcolo denormalizzato del saldo corrente dei conti.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone


MONTH_SHORT_LABELS = {
    1: "Gen",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "Mag",
    6: "Giu",
    7: "Lug",
    8: "Ago",
    9: "Set",
    10: "Ott",
    11: "Nov",
    12: "Dic",
}

MONTH_FULL_LABELS = {
    1: "Gennaio",
    2: "Febbraio",
    3: "Marzo",
    4: "Aprile",
    5: "Maggio",
    6: "Giugno",
    7: "Luglio",
    8: "Agosto",
    9: "Settembre",
    10: "Ottobre",
    11: "Novembre",
    12: "Dicembre",
}


def _empty_financial_series(labels):
    return {
        "labels": list(labels),
        "entrate": [0.0 for _ in labels],
        "uscite": [0.0 for _ in labels],
        "totale_entrate": Decimal("0.00"),
        "totale_uscite": Decimal("0.00"),
        "saldo": Decimal("0.00"),
        "movimenti": 0,
    }


def _serializable_financial_series(series, period_label):
    return {
        "periodLabel": period_label,
        "labels": series["labels"],
        "entrate": series["entrate"],
        "uscite": series["uscite"],
        "totaleEntrate": float(series["totale_entrate"]),
        "totaleUscite": float(series["totale_uscite"]),
        "saldo": float(series["saldo"]),
        "movimenti": series["movimenti"],
    }


def _build_movimenti_series(start_date, end_date, labels, bucket_for_date):
    from .models import MovimentoFinanziario

    series = _empty_financial_series(labels)
    movimenti = MovimentoFinanziario.objects.filter(
        data_contabile__gte=start_date,
        data_contabile__lte=end_date,
    ).values("data_contabile", "importo")

    for movimento in movimenti:
        importo = movimento["importo"] or Decimal("0.00")
        bucket_index = bucket_for_date(movimento["data_contabile"])
        if bucket_index is None or bucket_index < 0 or bucket_index >= len(labels):
            continue

        if importo >= 0:
            series["entrate"][bucket_index] += float(importo)
            series["totale_entrate"] += importo
        else:
            valore_uscita = abs(importo)
            series["uscite"][bucket_index] += float(valore_uscita)
            series["totale_uscite"] += valore_uscita
        series["movimenti"] += 1

    series["saldo"] = series["totale_entrate"] - series["totale_uscite"]
    return series


def build_home_financial_dashboard_data(today=None):
    """
    Riepilogo sintetico per la dashboard generale.

    La dashboard completa del modulo resta separata; qui prepariamo solo
    dati leggeri per una lettura mensile/annuale dei movimenti.
    """

    from .models import ContoBancario, MovimentoFinanziario, StatoRiconciliazione

    today = today or timezone.localdate()
    monthly_start = today.replace(day=1)
    monthly_end = today.replace(day=monthrange(today.year, today.month)[1])
    annual_start = date(today.year, 1, 1)
    annual_end = date(today.year, 12, 31)

    monthly_labels = [str(day) for day in range(1, monthly_end.day + 1)]
    annual_labels = [MONTH_SHORT_LABELS[month] for month in range(1, 13)]

    monthly = _build_movimenti_series(
        monthly_start,
        monthly_end,
        monthly_labels,
        lambda movement_date: movement_date.day - 1,
    )
    annual = _build_movimenti_series(
        annual_start,
        annual_end,
        annual_labels,
        lambda movement_date: movement_date.month - 1,
    )

    conti_attivi = ContoBancario.objects.filter(attivo=True)
    saldo_totale = conti_attivi.aggregate(totale=Sum("saldo_corrente"))["totale"] or Decimal("0.00")
    movimenti_senza_categoria = MovimentoFinanziario.objects.filter(categoria__isnull=True).count()
    movimenti_da_riconciliare = MovimentoFinanziario.objects.filter(
        stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO
    ).count()
    current_month_label = f"{MONTH_FULL_LABELS[today.month]} {today.year}"
    current_year_label = str(today.year)

    return {
        "current_month_label": current_month_label,
        "current_year_label": current_year_label,
        "saldo_totale": saldo_totale,
        "conti_attivi": conti_attivi.count(),
        "movimenti_senza_categoria": movimenti_senza_categoria,
        "movimenti_da_riconciliare": movimenti_da_riconciliare,
        "monthly": monthly,
        "annual": annual,
        "chart_data": {
            "monthly": _serializable_financial_series(monthly, current_month_label),
            "annual": _serializable_financial_series(annual, current_year_label),
        },
    }


# =========================================================================
#  Regole di categorizzazione
# =========================================================================


def _normalizza_testo_match_legacy(value: str) -> str:
    testo = (value or "").lower()
    replacements = {
        "à": "a",
        "è": "e",
        "é": "e",
        "ì": "i",
        "ò": "o",
        "ù": "u",
    }
    for source, target in replacements.items():
        testo = testo.replace(source, target)
    testo = re.sub(r"[^a-z0-9]+", " ", testo)
    return " ".join(testo.split())


def _normalizza_testo_match(value: str) -> str:
    testo = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    testo = re.sub(r"[^a-z0-9]+", " ", testo)
    return " ".join(testo.split())


def _split_pattern_or_groups(pattern: str) -> list[str]:
    parti = []
    for line in (pattern or "").splitlines():
        parti.extend(re.split(r"\s*(?:\||\bOR\b|\bOPPURE\b|\bO\b)\s*", line, flags=re.IGNORECASE))
    return [parte.strip() for parte in parti if parte and parte.strip()]


def _split_pattern_and_terms(group: str) -> list[str]:
    return [
        termine.strip()
        for termine in re.split(r"\s*(?:\+|&&|\bAND\b|\bE\b)\s*", group, flags=re.IGNORECASE)
        if termine and termine.strip()
    ]


def _pattern_testuale_match(pattern: str, testo: str) -> bool:
    testo_normalizzato = _normalizza_testo_match(testo)
    if not testo_normalizzato:
        return False

    for group in _split_pattern_or_groups(pattern):
        termini = [_normalizza_testo_match(termine) for termine in _split_pattern_and_terms(group)]
        termini = [termine for termine in termini if termine]
        if termini and all(termine in testo_normalizzato for termine in termini):
            return True
    return False


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

    descrizione = movimento.descrizione or ""
    controparte = movimento.controparte or ""
    iban_controparte = (movimento.iban_controparte or "").strip().upper()
    importo = movimento.importo if movimento.importo is not None else Decimal("0")

    match = False

    if condizione == CondizioneRegolaCategorizzazione.DESCRIZIONE_CONTIENE:
        match = _pattern_testuale_match(pattern, descrizione)
    elif condizione == CondizioneRegolaCategorizzazione.CONTROPARTE_CONTIENE:
        match = _pattern_testuale_match(pattern, controparte)
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


def calcola_saldo_conto_alla_data(conto, data_riferimento=None) -> Decimal:
    """
    Ricostruisce il saldo di un conto a una certa data.

    Se esiste uno snapshot in `SaldoConto`, parte dall'ultimo saldo noto
    precedente o uguale alla data e somma solo i movimenti successivi che
    incidono sul saldo. In assenza di snapshot, somma i movimenti da zero.
    """

    from .models import MovimentoFinanziario, SaldoConto

    target_date = data_riferimento or timezone.localdate()
    if isinstance(target_date, datetime):
        target_dt = target_date
        if timezone.is_naive(target_dt):
            target_dt = timezone.make_aware(target_dt)
        target_day = timezone.localtime(target_dt).date()
    else:
        target_day = target_date
        target_dt = timezone.make_aware(datetime.combine(target_day, time.max.replace(microsecond=0)))

    ultimo_saldo = (
        SaldoConto.objects.filter(conto=conto, data_riferimento__lte=target_dt)
        .order_by("-data_riferimento", "-id")
        .first()
    )

    movimenti = MovimentoFinanziario.objects.filter(
        conto=conto,
        incide_su_saldo_banca=True,
        data_contabile__lte=target_day,
    )
    saldo_base = Decimal("0")
    if ultimo_saldo:
        saldo_base = ultimo_saldo.saldo_contabile or Decimal("0")
        movimenti = movimenti.filter(data_contabile__gt=ultimo_saldo.data_riferimento.date())

    totale_movimenti = movimenti.aggregate(totale=Sum("importo"))["totale"] or Decimal("0")
    return saldo_base + totale_movimenti


def ricalcola_saldo_corrente_conto(conto, salva: bool = True) -> Decimal:
    """
    Ricalcola il saldo corrente denormalizzato a partire dall'ultimo snapshot
    di saldo e dai movimenti successivi che incidono sul conto.

    Nota: in presenza di un provider PSD2 che fornisce direttamente il saldo,
    quella sara' la fonte di verita'; questa funzione serve per i conti
    alimentati da import file o inserimento manuale, dove il saldo viene
    ricostruito dai movimenti.
    """

    totale = calcola_saldo_conto_alla_data(conto)

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


@dataclass
class CandidatoRiconciliazioneCumulativa:
    """Gruppo di rate candidate per un pagamento cumulativo."""

    rate: list
    allocazioni: list
    score: int
    motivazioni: list

    @property
    def score_percentuale(self) -> int:
        return max(0, min(100, self.score))


@dataclass
class CandidatoMovimentoRiconciliazione:
    movimento: object
    importo_disponibile: Decimal
    score: int
    motivazioni: list

    @property
    def score_percentuale(self) -> int:
        return max(0, min(100, self.score))


@dataclass
class CandidatoScadenzaFornitoreRiconciliazione:
    scadenza: object
    importo_residuo: Decimal
    score: int
    motivazioni: list

    @property
    def score_percentuale(self) -> int:
        return max(0, min(100, self.score))


_TOLLERANZA_IMPORTO_ESATTO = Decimal("0.01")
_TOLLERANZA_IMPORTO_APPROX = Decimal("1.00")
_TOLLERANZA_GIORNI_VICINI = 7
_TOLLERANZA_GIORNI_ESTESA = 30


def _importo_movimento_assoluto(movimento):
    return abs(movimento.importo or Decimal("0.00"))


def _importo_movimento_riconciliato(movimento):
    if movimento is None or not getattr(movimento, "pk", None):
        return Decimal("0.00")
    return movimento.riconciliazioni_rate.aggregate(totale=Sum("importo"))["totale"] or Decimal("0.00")


def importo_movimento_disponibile(movimento):
    return max(_importo_movimento_assoluto(movimento) - _importo_movimento_riconciliato(movimento), Decimal("0.00"))


def importo_rata_residuo(rata):
    return max((rata.importo_finale or Decimal("0.00")) - (rata.importo_pagato or Decimal("0.00")), Decimal("0.00"))


def _testo_contiene_parola(testo: str, parola: str) -> bool:
    return bool(parola and f" {parola} " in f" {testo or ''} ")


def _testo_contiene_frase(testo: str, frase: str) -> bool:
    return bool(frase and f" {frase} " in f" {testo or ''} ")


def _persona_presente_in_testo(testo: str, nome: str, cognome: str, *, accetta_solo_cognome: bool = True) -> str:
    nome = _normalizza_testo_match(nome or "")
    cognome = _normalizza_testo_match(cognome or "")
    if nome and cognome:
        nome_cognome = f"{nome} {cognome}"
        cognome_nome = f"{cognome} {nome}"
        if (
            _testo_contiene_frase(testo, nome_cognome)
            or _testo_contiene_frase(testo, cognome_nome)
            or (_testo_contiene_parola(testo, nome) and _testo_contiene_parola(testo, cognome))
        ):
            return "completo"
    if accetta_solo_cognome and cognome and len(cognome) >= 4 and _testo_contiene_parola(testo, cognome):
        return "cognome"
    return ""


def _label_persona(nome: str, cognome: str) -> str:
    return " ".join(part for part in [nome or "", cognome or ""] if part).strip()


def _match_familiari_in_testo(famiglia, testo: str) -> tuple[list[str], list[str]]:
    if famiglia is None:
        return [], []

    try:
        familiari = famiglia.familiari.all()
    except Exception:
        return [], []

    match_completi = []
    match_cognomi = []
    for familiare in familiari:
        livello = _persona_presente_in_testo(
            testo,
            getattr(familiare, "nome", "") or "",
            getattr(familiare, "cognome", "") or "",
        )
        if not livello:
            continue
        label = _label_persona(getattr(familiare, "nome", ""), getattr(familiare, "cognome", ""))
        if livello == "completo":
            match_completi.append(label)
        elif livello == "cognome":
            match_cognomi.append(label)
    return match_completi, match_cognomi


def _famiglia_ha_familiari(famiglia) -> bool:
    if famiglia is None:
        return False
    try:
        return famiglia.familiari.exists()
    except Exception:
        return False


def _valuta_identita_famiglia_in_causale(famiglia, studente, testo_movimento: str) -> tuple[bool, int, list[str]]:
    return _valuta_identita_famiglia_studenti_in_causale(
        famiglia,
        [studente] if studente is not None else [],
        testo_movimento,
    )


def _valuta_identita_famiglia_studenti_in_causale(famiglia, studenti, testo_movimento: str) -> tuple[bool, int, list[str]]:
    score = 0
    motivazioni = []
    ha_match = False

    familiari_completi, familiari_cognome = _match_familiari_in_testo(famiglia, testo_movimento)
    familiari_registrati = bool(familiari_completi or familiari_cognome) or _famiglia_ha_familiari(famiglia)
    if familiari_completi:
        score += 42
        ha_match = True
        label = ", ".join(familiari_completi[:2])
        motivazioni.append(f"Genitore/familiare presente nella causale: {label}")
    elif familiari_cognome:
        score += 8
        label = ", ".join(familiari_cognome[:2])
        motivazioni.append(f"Cognome di un familiare presente nella causale: {label}")

    studenti = [studente for studente in (studenti or []) if studente is not None]
    studenti_completi = []
    studenti_cognome = []
    for studente in studenti:
        livello_studente = _persona_presente_in_testo(
            testo_movimento,
            getattr(studente, "nome", "") or "",
            getattr(studente, "cognome", "") or "",
        )
        if livello_studente == "completo":
            studenti_completi.append(_label_persona(getattr(studente, "nome", ""), getattr(studente, "cognome", "")))
        elif livello_studente == "cognome" and not familiari_registrati:
            studenti_cognome.append(_label_persona(getattr(studente, "nome", ""), getattr(studente, "cognome", "")))

    if studenti_completi:
        score += 30
        ha_match = True
        label = ", ".join(studenti_completi[:2])
        motivazioni.append(f"Nome e cognome studente presenti nella causale: {label}")
    elif studenti_cognome:
        score += 12
        ha_match = True
        label = ", ".join(studenti_cognome[:2])
        motivazioni.append(f"Cognome studente presente nella causale: {label}")

    cognome_famiglia = _normalizza_testo_match(getattr(famiglia, "cognome_famiglia", "") or "")
    if (
        not familiari_registrati
        and cognome_famiglia
        and len(cognome_famiglia) >= 3
        and _testo_contiene_frase(testo_movimento, cognome_famiglia)
    ):
        score += 14
        ha_match = True
        motivazioni.append("Cognome famiglia presente nella causale")

    return ha_match, score, motivazioni


def _testo_movimento_per_identita(movimento) -> str:
    return _normalizza_testo_match(f"{getattr(movimento, 'descrizione', '') or ''} {getattr(movimento, 'controparte', '') or ''}")


def _famiglia_label_sicurezza(famiglia) -> str:
    return getattr(famiglia, "cognome_famiglia", "") or "selezionata"


def _valida_identita_movimento_rate(movimento, rate):
    testo_movimento = _testo_movimento_per_identita(movimento)
    gruppi = {}
    for rata in rate or []:
        studente = getattr(getattr(rata, "iscrizione", None), "studente", None)
        famiglia = getattr(studente, "famiglia", None) or getattr(rata, "famiglia", None)
        chiave = getattr(famiglia, "pk", None) or id(famiglia) or id(rata)
        if chiave not in gruppi:
            gruppi[chiave] = {"famiglia": famiglia, "studenti": []}
        if studente is not None:
            gruppi[chiave]["studenti"].append(studente)

    for gruppo in gruppi.values():
        famiglia = gruppo["famiglia"]
        ha_match_identita, _score_identita, _motivazioni_identita = _valuta_identita_famiglia_studenti_in_causale(
            famiglia,
            gruppo["studenti"],
            testo_movimento,
        )
        if not ha_match_identita:
            raise ValidationError(
                "Controllo di sicurezza: la causale o la controparte del movimento non contiene "
                f"un nominativo compatibile con la famiglia {_famiglia_label_sicurezza(famiglia)}. "
                "Verifica il movimento bancario prima di riconciliare."
            )


def _decimal_close(a, b, tolleranza=_TOLLERANZA_IMPORTO_APPROX):
    return abs((a or Decimal("0.00")) - (b or Decimal("0.00"))) <= tolleranza


def _esiste_somma_compatibile(importo, rate_residue, *, max_items=12):
    residui = [item for item in rate_residue if item > 0][:max_items]
    somme = {Decimal("0.00")}
    for residuo in residui:
        somme.update({somma + residuo for somma in list(somme)})
    return any(_decimal_close(somma, importo) for somma in somme if somma > 0)


def _decimal_to_cents(value) -> int:
    return int(((value or Decimal("0.00")) * Decimal("100")).quantize(Decimal("1")))


def _giorni_distanza_rata_movimento(rata, movimento) -> int:
    if not getattr(movimento, "data_contabile", None) or not getattr(rata, "data_scadenza", None):
        return 9999
    return abs((movimento.data_contabile - rata.data_scadenza).days)


def _qualita_sottoinsieme_rate(rate, movimento):
    distanze = [_giorni_distanza_rata_movimento(rata, movimento) for rata in rate]
    max_distanza = max(distanze) if distanze else 9999
    totale_distanza = sum(distanze)
    studenti = {
        getattr(getattr(rata.iscrizione, "studente", None), "pk", None)
        for rata in rate
        if getattr(getattr(rata, "iscrizione", None), "studente", None) is not None
    }
    periodi = {(rata.anno_riferimento, rata.mese_riferimento) for rata in rate}
    return (
        -max_distanza,
        -totale_distanza,
        len(studenti),
        -len(periodi),
        -len(rate),
    )


def _trova_sottoinsieme_rate_per_importo(rate, importo_target, movimento):
    target_cents = _decimal_to_cents(importo_target)
    tolleranza_cents = _decimal_to_cents(_TOLLERANZA_IMPORTO_ESATTO)
    if target_cents <= 0:
        return []

    dp = {0: []}
    rate_ordinate = sorted(
        rate,
        key=lambda rata: (
            _giorni_distanza_rata_movimento(rata, movimento),
            rata.data_scadenza or date.max,
            rata.pk or 0,
        ),
    )[:18]

    for rata in rate_ordinate:
        residuo_cents = _decimal_to_cents(importo_rata_residuo(rata))
        if residuo_cents <= 0 or residuo_cents > target_cents + tolleranza_cents:
            continue
        for somma, sottoinsieme in list(dp.items()):
            nuova_somma = somma + residuo_cents
            if nuova_somma > target_cents + tolleranza_cents:
                continue
            nuovo_sottoinsieme = sottoinsieme + [rata]
            if len(nuovo_sottoinsieme) > 10:
                continue
            esistente = dp.get(nuova_somma)
            if (
                esistente is None
                or _qualita_sottoinsieme_rate(nuovo_sottoinsieme, movimento)
                > _qualita_sottoinsieme_rate(esistente, movimento)
            ):
                dp[nuova_somma] = nuovo_sottoinsieme

    somme_compatibili = [
        somma
        for somma, sottoinsieme in dp.items()
        if len(sottoinsieme) >= 2 and abs(somma - target_cents) <= tolleranza_cents
    ]
    if not somme_compatibili:
        return []

    somma_migliore = max(
        somme_compatibili,
        key=lambda somma: _qualita_sottoinsieme_rate(dp[somma], movimento),
    )
    return dp[somma_migliore]


def _studenti_unici_da_rate(rate):
    studenti = []
    visti = set()
    for rata in rate or []:
        studente = getattr(getattr(rata, "iscrizione", None), "studente", None)
        if studente is None:
            continue
        chiave = getattr(studente, "pk", None) or id(studente)
        if chiave in visti:
            continue
        visti.add(chiave)
        studenti.append(studente)
    return studenti


def _rata_disponibile_per_auto(rata, include_rata=None, *, controlla_collegamenti: bool = True):
    if rata is None or getattr(rata, "pagata", False):
        return False
    if include_rata is not None and not include_rata(rata):
        return False
    if controlla_collegamenti:
        try:
            if rata.movimenti_finanziari.exists() or rata.riconciliazioni_movimenti.exists():
                return False
        except Exception:
            return False
    return importo_rata_residuo(rata) > Decimal("0.00")


def trova_rate_candidate(movimento, *, limite: int = 10, solo_disponibili: bool = False):
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
        .prefetch_related("iscrizione__studente__famiglia__familiari")
        .filter(
            importo_finale__gte=importo_cerca - _TOLLERANZA_IMPORTO_APPROX,
            importo_finale__lte=importo_cerca + _TOLLERANZA_IMPORTO_APPROX,
        )
        .order_by("-anno_riferimento", "-mese_riferimento")
    )
    if solo_disponibili:
        qs = qs.filter(
            pagata=False,
            movimenti_finanziari__isnull=True,
            riconciliazioni_movimenti__isnull=True,
        ).distinct()
    qs = qs[:200]

    data_mov = movimento.data_contabile
    testo_movimento = _normalizza_testo_match(f"{movimento.descrizione or ''} {movimento.controparte or ''}")
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

        studente = getattr(getattr(rata, "iscrizione", None), "studente", None)
        famiglia = getattr(studente, "famiglia", None)
        ha_match_identita, score_identita, motivazioni_identita = _valuta_identita_famiglia_in_causale(
            famiglia,
            studente,
            testo_movimento,
        )
        if not ha_match_identita:
            continue
        score += score_identita
        motivazioni.extend(motivazioni_identita)

        candidati.append(
            CandidatoRiconciliazione(rata=rata, score=score, motivazioni=motivazioni)
        )

    candidati.sort(key=lambda c: c.score, reverse=True)
    return candidati[:limite]


def trova_rate_cumulative_candidate(movimento, *, limite: int = 5, include_rata=None, rate_pool=None):
    """
    Ritorna gruppi di rate della stessa famiglia compatibili con un unico
    movimento bancario. E' usata dalla riconciliazione automatica per i
    bonifici cumulativi, quindi resta volutamente conservativa: almeno due
    rate aperte, somma esatta e identita' familiare riconoscibile in causale.
    """

    from economia.models.iscrizioni import RataIscrizione

    if movimento is None or movimento.importo is None or movimento.importo <= 0:
        return []

    importo_cerca = importo_movimento_disponibile(movimento)
    if importo_cerca <= _TOLLERANZA_IMPORTO_ESATTO:
        return []
    testo_movimento = _testo_movimento_per_identita(movimento)

    if rate_pool is None:
        qs = (
            RataIscrizione.objects.select_related(
                "famiglia",
                "iscrizione__studente__famiglia",
                "iscrizione__anno_scolastico",
            )
            .prefetch_related("iscrizione__studente__famiglia__familiari")
            .filter(
                pagata=False,
                importo_finale__gt=0,
                importo_finale__lte=importo_cerca + _TOLLERANZA_IMPORTO_ESATTO,
                movimenti_finanziari__isnull=True,
                riconciliazioni_movimenti__isnull=True,
            )
            .distinct()
            .order_by("famiglia_id", "anno_riferimento", "mese_riferimento", "numero_rata")[:600]
        )
        controlla_collegamenti = False
    else:
        qs = [
            rata
            for rata in rate_pool
            if importo_rata_residuo(rata) <= importo_cerca + _TOLLERANZA_IMPORTO_ESATTO
        ]
        controlla_collegamenti = False

    gruppi = {}
    for rata in qs:
        if not _rata_disponibile_per_auto(
            rata,
            include_rata,
            controlla_collegamenti=controlla_collegamenti,
        ):
            continue
        famiglia = getattr(rata, "famiglia", None) or getattr(getattr(rata.iscrizione, "studente", None), "famiglia", None)
        if famiglia is None:
            continue
        chiave = getattr(famiglia, "pk", None) or id(famiglia)
        gruppi.setdefault(chiave, {"famiglia": famiglia, "rate": []})["rate"].append(rata)

    candidati = []
    for gruppo in gruppi.values():
        rate_gruppo = gruppo["rate"]
        if len(rate_gruppo) < 2:
            continue

        sottoinsieme = _trova_sottoinsieme_rate_per_importo(rate_gruppo, importo_cerca, movimento)
        if len(sottoinsieme) < 2:
            continue

        famiglia = gruppo["famiglia"]
        studenti = _studenti_unici_da_rate(sottoinsieme)
        ha_match_identita, score_identita, motivazioni_identita = _valuta_identita_famiglia_studenti_in_causale(
            famiglia,
            studenti,
            testo_movimento,
        )
        if not ha_match_identita:
            continue

        score = score_identita + 50 + 10
        motivazioni = list(motivazioni_identita)
        motivazioni.append("Importo identico alla somma di piu rate aperte")
        motivazioni.append("Rate non ancora pagate")

        distanze = [
            _giorni_distanza_rata_movimento(rata, movimento)
            for rata in sottoinsieme
            if getattr(rata, "data_scadenza", None)
        ]
        if distanze:
            max_distanza = max(distanze)
            if max_distanza <= _TOLLERANZA_GIORNI_VICINI:
                score += 25
                motivazioni.append(f"Scadenze vicine al movimento (+/- {max_distanza} gg)")
            elif max_distanza <= _TOLLERANZA_GIORNI_ESTESA:
                score += 10
                motivazioni.append(f"Scadenze entro 30 giorni dal movimento ({max_distanza} gg)")

        if len(studenti) >= 2:
            score += 12
            motivazioni.append("Pagamento cumulativo per piu studenti della stessa famiglia")
        else:
            score += 6
            motivazioni.append("Pagamento cumulativo su piu rate della stessa iscrizione")

        periodi = {(rata.anno_riferimento, rata.mese_riferimento) for rata in sottoinsieme}
        if len(periodi) == 1:
            score += 8
            motivazioni.append("Le rate appartengono allo stesso periodo")

        allocazioni = [(rata, importo_rata_residuo(rata)) for rata in sottoinsieme]
        candidati.append(
            CandidatoRiconciliazioneCumulativa(
                rate=sottoinsieme,
                allocazioni=allocazioni,
                score=score,
                motivazioni=motivazioni,
            )
        )

    candidati.sort(key=lambda candidato: (candidato.score, _qualita_sottoinsieme_rate(candidato.rate, movimento)), reverse=True)
    return candidati[:limite]


def trova_movimenti_candidati_per_rate(rata_principale, rate_aperte, *, limite: int = 12):
    from .models import MovimentoFinanziario, StatoRiconciliazione

    if rata_principale is None:
        return []

    rate_aperte = list(rate_aperte or [])
    residuo_principale = importo_rata_residuo(rata_principale)
    residui_rate = [importo_rata_residuo(rata) for rata in rate_aperte]
    totale_residui = sum(residui_rate, Decimal("0.00"))

    famiglia = getattr(getattr(rata_principale, "iscrizione", None), "studente", None)
    famiglia = getattr(famiglia, "famiglia", None)
    studente = getattr(rata_principale.iscrizione, "studente", None)
    studenti_rate_aperte = []
    for rata in rate_aperte:
        studente_rata = getattr(getattr(rata, "iscrizione", None), "studente", None)
        if studente_rata is not None:
            studenti_rate_aperte.append(studente_rata)
    if studente is not None and studente not in studenti_rate_aperte:
        studenti_rate_aperte.insert(0, studente)
    queryset = (
        MovimentoFinanziario.objects.select_related("conto", "categoria")
        .exclude(stato_riconciliazione=StatoRiconciliazione.IGNORATO)
        .filter(importo__gt=0)
        .order_by("-data_contabile", "-id")[:300]
    )

    candidati = []
    for movimento in queryset:
        if movimento.rata_iscrizione_id and not movimento.riconciliazioni_rate.exists():
            continue

        disponibile = importo_movimento_disponibile(movimento)
        if disponibile <= _TOLLERANZA_IMPORTO_ESATTO:
            continue

        testo_movimento = _normalizza_testo_match(f"{movimento.descrizione or ''} {movimento.controparte or ''}")
        ha_match_identita, score_identita, motivazioni_identita = _valuta_identita_famiglia_studenti_in_causale(
            famiglia,
            studenti_rate_aperte,
            testo_movimento,
        )
        if not ha_match_identita:
            continue

        score = score_identita
        motivazioni = list(motivazioni_identita)

        if residuo_principale > 0 and _decimal_close(disponibile, residuo_principale, _TOLLERANZA_IMPORTO_ESATTO):
            score += 45
            motivazioni.append("Importo identico al residuo della rata selezionata")
        elif residuo_principale > 0 and _decimal_close(disponibile, residuo_principale):
            score += 32
            motivazioni.append("Importo simile al residuo della rata selezionata")

        if totale_residui > 0 and _decimal_close(disponibile, totale_residui, _TOLLERANZA_IMPORTO_ESATTO):
            score += 35
            motivazioni.append("Copre tutte le rate aperte della famiglia per l'anno")
        elif _esiste_somma_compatibile(disponibile, residui_rate):
            score += 30
            motivazioni.append("Compatibile con una combinazione di rate aperte della famiglia")
        elif totale_residui > 0 and disponibile < totale_residui:
            score += 8
            motivazioni.append("Importo utilizzabile come pagamento parziale o cumulativo")

        data_rif = rata_principale.data_scadenza or rata_principale.data_pagamento
        if data_rif and movimento.data_contabile:
            delta_giorni = abs((movimento.data_contabile - data_rif).days)
            if delta_giorni <= _TOLLERANZA_GIORNI_VICINI:
                score += 18
                motivazioni.append(f"Data vicina alla scadenza della rata (+/- {delta_giorni} gg)")
            elif delta_giorni <= _TOLLERANZA_GIORNI_ESTESA:
                score += 8
                motivazioni.append(f"Data entro 30 giorni dalla scadenza ({delta_giorni} gg)")

        if not motivazioni:
            score += 1
            motivazioni.append("Movimento disponibile per riconciliazione manuale")

        candidati.append(
            CandidatoMovimentoRiconciliazione(
                movimento=movimento,
                importo_disponibile=disponibile,
                score=score,
                motivazioni=motivazioni,
            )
        )

    candidati.sort(key=lambda candidato: (candidato.score, candidato.movimento.data_contabile), reverse=True)
    return candidati[:limite]


def riconcilia_movimento_automaticamente(
    movimento,
    *,
    utente=None,
    punteggio_minimo: int = 85,
    include_rata=None,
):
    if movimento is None or movimento.importo is None or movimento.importo <= 0:
        return None
    if movimento.rata_iscrizione_id or movimento.riconciliazioni_rate.exists():
        return None

    opzioni = []
    for candidato in trova_rate_candidate(movimento, limite=10, solo_disponibili=True):
        if _rata_disponibile_per_auto(candidato.rata, include_rata, controlla_collegamenti=False):
            opzioni.append(("singola", candidato.score, candidato))

    for candidato in trova_rate_cumulative_candidate(movimento, limite=5, include_rata=include_rata):
        opzioni.append(("cumulativa", candidato.score, candidato))

    if not opzioni:
        return None

    top_score = max(score for _tipo, score, _candidato in opzioni)
    migliori = [(tipo, candidato) for tipo, score, candidato in opzioni if score == top_score]
    if top_score < punteggio_minimo or len(migliori) != 1:
        return None

    tipo, candidato = migliori[0]
    if tipo == "cumulativa":
        riconcilia_movimento_con_rate(movimento, candidato.allocazioni, utente=utente)
        return candidato

    riconcilia_movimento_con_rata(movimento, candidato.rata, utente=utente, marca_rata_pagata=True)
    return candidato


@transaction.atomic
def riconcilia_movimento_con_rate(
    movimento,
    allocazioni,
    *,
    utente=None,
):
    from .models import RiconciliazioneRataMovimento, StatoRiconciliazione

    allocazioni = [
        (rata, importo)
        for rata, importo in (allocazioni or [])
        if rata is not None and importo and importo > 0
    ]
    if not allocazioni:
        raise ValidationError("Seleziona almeno una rata e indica l'importo da riconciliare.")

    _valida_identita_movimento_rate(movimento, [rata for rata, _importo in allocazioni])

    disponibile = importo_movimento_disponibile(movimento)
    totale_allocato = sum((importo for _rata, importo in allocazioni), Decimal("0.00"))
    if totale_allocato > disponibile + _TOLLERANZA_IMPORTO_ESATTO:
        raise ValidationError("L'importo assegnato supera il residuo disponibile del movimento bancario.")

    for rata, importo in allocazioni:
        residuo_rata = importo_rata_residuo(rata)
        if importo > residuo_rata + _TOLLERANZA_IMPORTO_ESATTO:
            raise ValidationError(f"L'importo assegnato a {rata.display_label} supera il residuo della rata.")

    for rata, importo in allocazioni:
        link, created = RiconciliazioneRataMovimento.objects.get_or_create(
            movimento=movimento,
            rata=rata,
            defaults={
                "importo": importo,
                "creato_da": utente if getattr(utente, "is_authenticated", False) else None,
            },
        )
        if not created:
            link.importo += importo
            if utente and getattr(utente, "is_authenticated", False) and not link.creato_da_id:
                link.creato_da = utente
            link.save(update_fields=["importo", "creato_da"])

        importo_finale = rata.importo_finale or Decimal("0.00")
        rata.importo_pagato = min((rata.importo_pagato or Decimal("0.00")) + importo, importo_finale)
        rata.pagata = importo_finale <= 0 or rata.importo_pagato >= importo_finale - _TOLLERANZA_IMPORTO_ESATTO
        rata.data_pagamento = rata.data_pagamento or movimento.data_contabile
        rata.save(update_fields=["importo_pagato", "pagata", "data_pagamento", "importo_finale"])

    residuo_movimento = importo_movimento_disponibile(movimento)
    links = list(movimento.riconciliazioni_rate.select_related("rata"))
    movimento.rata_iscrizione = links[0].rata if residuo_movimento <= _TOLLERANZA_IMPORTO_ESATTO and len(links) == 1 else None
    movimento.stato_riconciliazione = (
        StatoRiconciliazione.RICONCILIATO
        if residuo_movimento <= _TOLLERANZA_IMPORTO_ESATTO
        else StatoRiconciliazione.NON_RICONCILIATO
    )
    movimento.save(
        update_fields=[
            "rata_iscrizione",
            "stato_riconciliazione",
            "data_aggiornamento",
        ]
    )
    return movimento


@transaction.atomic
def riconcilia_movimento_con_rata(
    movimento,
    rata,
    *,
    utente=None,
    marca_rata_pagata: bool = True,
):
    """
    Collega un movimento a una rata. Per i nuovi flussi crea anche il legame
    analitico con importo, così rimangono gestibili pagamenti cumulativi o
    parziali.
    """

    from .models import StatoRiconciliazione

    if marca_rata_pagata:
        riconcilia_movimento_con_rate(
            movimento,
            [(rata, _importo_movimento_assoluto(movimento))],
            utente=utente,
        )
        return movimento

    _valida_identita_movimento_rate(movimento, [rata])

    movimento.rata_iscrizione = rata
    movimento.stato_riconciliazione = StatoRiconciliazione.RICONCILIATO
    movimento.save(update_fields=["rata_iscrizione", "stato_riconciliazione", "data_aggiornamento"])
    return movimento


@transaction.atomic
def annulla_riconciliazione(movimento):
    from .models import StatoRiconciliazione

    links = list(movimento.riconciliazioni_rate.select_related("rata"))
    for link in links:
        rata = link.rata
        rata.importo_pagato = max((rata.importo_pagato or Decimal("0.00")) - link.importo, Decimal("0.00"))
        importo_finale = rata.importo_finale or Decimal("0.00")
        rata.pagata = importo_finale <= 0 or rata.importo_pagato >= importo_finale - _TOLLERANZA_IMPORTO_ESATTO
        if rata.importo_pagato <= 0:
            rata.data_pagamento = None
        rata.save(update_fields=["importo_pagato", "pagata", "data_pagamento", "importo_finale"])

    if links:
        movimento.riconciliazioni_rate.all().delete()

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


# =========================================================================
#  Documenti e pagamenti fornitori
# =========================================================================


def aggiorna_stato_documento_da_scadenze(documento):
    from .models import StatoDocumentoFornitore, StatoScadenzaFornitore

    if documento.stato == StatoDocumentoFornitore.ANNULLATO:
        return documento

    scadenze = documento.scadenze.exclude(stato=StatoScadenzaFornitore.ANNULLATA)
    if not scadenze.exists():
        return documento

    pagato = scadenze.aggregate(totale=Sum("importo_pagato"))["totale"] or Decimal("0.00")
    totale = documento.totale or Decimal("0.00")
    if totale > Decimal("0.00") and pagato >= totale - _TOLLERANZA_IMPORTO_ESATTO:
        nuovo_stato = StatoDocumentoFornitore.PAGATO
    elif pagato > Decimal("0.00"):
        nuovo_stato = StatoDocumentoFornitore.PARZIALMENTE_PAGATO
    else:
        nuovo_stato = StatoDocumentoFornitore.DA_PAGARE

    if documento.stato != nuovo_stato:
        documento.stato = nuovo_stato
        documento.save(update_fields=["stato", "data_aggiornamento"])
    return documento


def aggiorna_scadenza_da_pagamenti(scadenza):
    from .models import StatoScadenzaFornitore

    totale_pagato = scadenza.pagamenti.aggregate(totale=Sum("importo"))["totale"] or Decimal("0.00")
    scadenza.importo_pagato = min(totale_pagato, scadenza.importo_previsto or Decimal("0.00"))
    if scadenza.importo_pagato > Decimal("0.00"):
        scadenza.data_pagamento = (
            scadenza.pagamenti.order_by("-data_pagamento", "-id")
            .values_list("data_pagamento", flat=True)
            .first()
        )
    else:
        scadenza.data_pagamento = None
    scadenza.stato = scadenza.calcola_stato_automatico()
    scadenza.save(update_fields=["importo_pagato", "data_pagamento", "stato", "data_aggiornamento"])

    documento = scadenza.documento
    aggiorna_stato_documento_da_scadenze(documento)
    return scadenza


def importo_scadenza_fornitore_residuo(scadenza):
    return max((scadenza.importo_previsto or Decimal("0.00")) - (scadenza.importo_pagato or Decimal("0.00")), Decimal("0.00"))


def _importo_movimento_fornitori_riconciliato(movimento):
    if movimento is None or not getattr(movimento, "pk", None):
        return Decimal("0.00")
    return movimento.pagamenti_fornitori.aggregate(totale=Sum("importo"))["totale"] or Decimal("0.00")


def importo_movimento_disponibile_fornitori(movimento):
    return max(
        _importo_movimento_assoluto(movimento) - _importo_movimento_fornitori_riconciliato(movimento),
        Decimal("0.00"),
    )


def crea_notifica_finanziaria(
    *,
    titolo,
    messaggio="",
    tipo="integrazione",
    livello="info",
    url="",
    documento=None,
    scadenza=None,
    movimento_finanziario=None,
    chiave_deduplica="",
    richiede_gestione=False,
    payload=None,
):
    from .models import NotificaFinanziaria

    defaults = {
        "titolo": titolo,
        "messaggio": messaggio,
        "tipo": tipo,
        "livello": livello,
        "url": url,
        "documento": documento,
        "scadenza": scadenza,
        "movimento_finanziario": movimento_finanziario,
        "richiede_gestione": richiede_gestione,
        "payload": payload or {},
    }
    if chiave_deduplica:
        notifica, created = NotificaFinanziaria.objects.get_or_create(
            chiave_deduplica=chiave_deduplica,
            defaults=defaults,
        )
        return notifica, created
    return NotificaFinanziaria.objects.create(**defaults), True


def applica_categoria_documento_a_movimento_fornitore(movimento, scadenza, *, utente=None):
    if movimento is None or scadenza is None:
        return False

    documento = getattr(scadenza, "documento", None)
    categoria = getattr(documento, "categoria_spesa", None)
    if categoria is None:
        return False

    categoria_manuale = movimento.categoria_id and not movimento.categorizzazione_automatica
    if categoria_manuale:
        return False

    if movimento.categoria_id == categoria.pk and movimento.categorizzazione_automatica:
        return False

    movimento.categoria = categoria
    movimento.categorizzazione_automatica = True
    movimento.regola_categorizzazione = None
    movimento.categorizzato_da = utente if getattr(utente, "is_authenticated", False) else None
    movimento.categorizzato_il = timezone.now()
    movimento.save(
        update_fields=[
            "categoria",
            "categorizzazione_automatica",
            "regola_categorizzazione",
            "categorizzato_da",
            "categorizzato_il",
            "data_aggiornamento",
        ]
    )
    return True


@transaction.atomic
def registra_pagamento_fornitore(
    scadenza,
    *,
    importo,
    data_pagamento=None,
    movimento=None,
    metodo="manuale",
    conto=None,
    note="",
    utente=None,
):
    from .models import PagamentoFornitore

    importo = Decimal(importo or Decimal("0.00"))
    if importo <= Decimal("0.00"):
        raise ValidationError("L'importo del pagamento deve essere maggiore di zero.")

    residuo_scadenza = importo_scadenza_fornitore_residuo(scadenza)
    if importo > residuo_scadenza + _TOLLERANZA_IMPORTO_ESATTO:
        raise ValidationError("L'importo supera il residuo della scadenza.")

    if movimento is not None:
        residuo_movimento = importo_movimento_disponibile_fornitori(movimento)
        if importo > residuo_movimento + _TOLLERANZA_IMPORTO_ESATTO:
            raise ValidationError("L'importo supera il residuo disponibile del movimento bancario.")

    pagamento = PagamentoFornitore.objects.create(
        scadenza=scadenza,
        movimento_finanziario=movimento,
        data_pagamento=data_pagamento or timezone.localdate(),
        importo=importo,
        metodo=metodo,
        conto_bancario=conto or getattr(movimento, "conto", None),
        note=note,
        creato_da=utente if getattr(utente, "is_authenticated", False) else None,
    )
    applica_categoria_documento_a_movimento_fornitore(movimento, scadenza, utente=utente)
    aggiorna_scadenza_da_pagamenti(scadenza)
    return pagamento


@transaction.atomic
def annulla_pagamento_fornitore(pagamento):
    scadenza = pagamento.scadenza
    pagamento.delete()
    aggiorna_scadenza_da_pagamenti(scadenza)
    return scadenza


def _supplier_match_score(fornitore, testo_movimento):
    score = 0
    motivazioni = []
    denominazione = _normalizza_testo_match(getattr(fornitore, "denominazione", "") or "")
    if denominazione and _testo_contiene_frase(testo_movimento, denominazione):
        score += 38
        motivazioni.append("Denominazione fornitore presente nella causale")
    else:
        parole = [p for p in denominazione.split() if len(p) >= 4]
        match = [p for p in parole if _testo_contiene_parola(testo_movimento, p)]
        if match:
            score += min(26, 8 * len(match))
            motivazioni.append("Causale compatibile con il nome del fornitore")

    partita_iva = _normalizza_testo_match(getattr(fornitore, "partita_iva", "") or "")
    codice_fiscale = _normalizza_testo_match(getattr(fornitore, "codice_fiscale", "") or "")
    if partita_iva and partita_iva in testo_movimento:
        score += 28
        motivazioni.append("Partita IVA presente nel movimento")
    elif codice_fiscale and codice_fiscale in testo_movimento:
        score += 24
        motivazioni.append("Codice fiscale presente nel movimento")
    return score, motivazioni


def trova_scadenze_fornitori_candidate(movimento, *, limite: int = 10):
    from .models import ScadenzaPagamentoFornitore, StatoScadenzaFornitore

    if movimento is None or movimento.importo is None or movimento.importo >= 0:
        return []

    disponibile = importo_movimento_disponibile_fornitori(movimento)
    if disponibile <= _TOLLERANZA_IMPORTO_ESATTO:
        return []

    testo_movimento = _normalizza_testo_match(
        f"{movimento.descrizione or ''} {movimento.controparte or ''} {movimento.iban_controparte or ''}"
    )

    scadenze = (
        ScadenzaPagamentoFornitore.objects.select_related(
            "documento",
            "documento__fornitore",
            "documento__categoria_spesa",
        )
        .exclude(stato__in=[StatoScadenzaFornitore.PAGATA, StatoScadenzaFornitore.ANNULLATA])
        .order_by("data_scadenza", "id")[:300]
    )
    candidati = []
    for scadenza in scadenze:
        residuo = importo_scadenza_fornitore_residuo(scadenza)
        if residuo <= _TOLLERANZA_IMPORTO_ESATTO:
            continue

        score = 0
        motivazioni = []
        differenza = abs(disponibile - residuo)
        if differenza <= _TOLLERANZA_IMPORTO_ESATTO:
            score += 45
            motivazioni.append("Importo identico al residuo della scadenza")
        elif differenza <= _TOLLERANZA_IMPORTO_APPROX:
            score += 30
            motivazioni.append("Importo molto vicino al residuo della scadenza")
        elif disponibile < residuo:
            score += 10
            motivazioni.append("Movimento utilizzabile come pagamento parziale")
        else:
            continue

        if movimento.data_contabile and scadenza.data_scadenza:
            delta_giorni = abs((movimento.data_contabile - scadenza.data_scadenza).days)
            if delta_giorni <= _TOLLERANZA_GIORNI_VICINI:
                score += 22
                motivazioni.append(f"Data vicina alla scadenza (+/- {delta_giorni} gg)")
            elif delta_giorni <= _TOLLERANZA_GIORNI_ESTESA:
                score += 8
                motivazioni.append(f"Data entro 30 giorni dalla scadenza ({delta_giorni} gg)")

        supplier_score, supplier_motivazioni = _supplier_match_score(scadenza.documento.fornitore, testo_movimento)
        score += supplier_score
        motivazioni.extend(supplier_motivazioni)

        iban_fornitore = _normalizza_testo_match(getattr(scadenza.documento.fornitore, "iban", "") or "")
        iban_movimento = _normalizza_testo_match(getattr(movimento, "iban_controparte", "") or "")
        if iban_fornitore and iban_movimento and iban_fornitore == iban_movimento:
            score += 24
            motivazioni.append("IBAN fornitore corrispondente")

        if score < 30:
            continue
        candidati.append(
            CandidatoScadenzaFornitoreRiconciliazione(
                scadenza=scadenza,
                importo_residuo=residuo,
                score=score,
                motivazioni=motivazioni or ["Scadenza compatibile"],
            )
        )

    candidati.sort(key=lambda candidato: (candidato.score, candidato.scadenza.data_scadenza), reverse=True)
    return candidati[:limite]


@transaction.atomic
def riconcilia_movimento_con_scadenza_fornitore(
    movimento,
    scadenza,
    *,
    importo=None,
    utente=None,
    note="",
):
    from .models import MetodoPagamentoFornitore, StatoRiconciliazione

    if movimento.importo is None or movimento.importo >= 0:
        raise ValidationError("La riconciliazione fornitori richiede un movimento in uscita.")

    disponibile = importo_movimento_disponibile_fornitori(movimento)
    residuo_scadenza = importo_scadenza_fornitore_residuo(scadenza)
    importo = Decimal(importo if importo is not None else min(disponibile, residuo_scadenza))
    pagamento = registra_pagamento_fornitore(
        scadenza,
        importo=importo,
        data_pagamento=movimento.data_contabile,
        movimento=movimento,
        metodo=MetodoPagamentoFornitore.BANCA,
        conto=movimento.conto,
        note=note,
        utente=utente,
    )

    residuo_movimento = importo_movimento_disponibile_fornitori(movimento)
    if residuo_movimento <= _TOLLERANZA_IMPORTO_ESATTO:
        movimento.stato_riconciliazione = StatoRiconciliazione.RICONCILIATO
        movimento.save(update_fields=["stato_riconciliazione", "data_aggiornamento"])

    crea_notifica_finanziaria(
        titolo="Pagamento fornitore riconciliato",
        messaggio=f"{scadenza.documento.fornitore} - {scadenza.documento.numero_documento}",
        tipo="riconciliazione",
        url=reverse("modifica_documento_fornitore", kwargs={"pk": scadenza.documento_id}),
        documento=scadenza.documento,
        scadenza=scadenza,
        movimento_finanziario=movimento,
        chiave_deduplica=f"pagamento-fornitore-{pagamento.pk}",
        payload={"pagamento_id": pagamento.pk},
    )
    return pagamento


def riconcilia_fornitori_automaticamente(*, utente=None, punteggio_minimo: int = 85, limite_movimenti: int = 100):
    from .models import MovimentoFinanziario, StatoRiconciliazione

    riconciliati = []
    movimenti = (
        MovimentoFinanziario.objects.select_related("conto")
        .exclude(stato_riconciliazione=StatoRiconciliazione.IGNORATO)
        .filter(importo__lt=0)
        .order_by("-data_contabile", "-id")[:limite_movimenti]
    )
    for movimento in movimenti:
        if importo_movimento_disponibile_fornitori(movimento) <= _TOLLERANZA_IMPORTO_ESATTO:
            continue
        candidati = trova_scadenze_fornitori_candidate(movimento, limite=3)
        if not candidati:
            continue
        top_score = candidati[0].score
        migliori = [candidato for candidato in candidati if candidato.score == top_score]
        if top_score < punteggio_minimo or len(migliori) != 1:
            continue
        pagamento = riconcilia_movimento_con_scadenza_fornitore(
            movimento,
            migliori[0].scadenza,
            utente=utente,
            note="Riconciliazione automatica",
        )
        riconciliati.append(pagamento)
    return riconciliati
