from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from django.core.exceptions import ValidationError
from django.db import transaction

from economia.models import Iscrizione, RataIscrizione, RimodulazioneRetta
from economia.models.iscrizioni import add_months_safe


PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA = 70


def _rata_reference_date(rata):
    if rata.data_scadenza:
        return rata.data_scadenza
    return date(rata.anno_riferimento, rata.mese_riferimento, 1)


def _split_amount(total, count):
    total = total or Decimal("0.00")
    count = max(int(count or 0), 1)
    base = (total / count).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    amounts = [base for _index in range(count)]
    amounts[-1] = total - sum(amounts[:-1], Decimal("0.00"))
    return amounts


def _rata_total_amount(rata):
    return (rata.importo_finale if rata.importo_finale is not None else rata.importo_dovuto) or Decimal("0.00")


def _rata_paid_amount(rata):
    return rata.importo_pagato or Decimal("0.00")


def _rata_residual_amount(rata):
    return max(_rata_total_amount(rata) - _rata_paid_amount(rata), Decimal("0.00"))


def _rata_has_credit_or_discount_activity(rata):
    return (rata.credito_applicato or Decimal("0.00")) > 0 or (rata.altri_sgravi or Decimal("0.00")) > 0


def _add_months_from_rate(rata, months, target_day):
    riferimento = _rata_reference_date(rata)
    return add_months_safe(riferimento, months, target_day=target_day)


def rimodula_rate_future(
    iscrizione,
    *,
    rata_decorrenza,
    modalita,
    numero_rate_future,
    importo_mensile=None,
    totale_residuo=None,
    note="",
    utente=None,
):
    if iscrizione.is_pagamento_unica_soluzione:
        raise ValidationError("La rimodulazione e disponibile solo per iscrizioni con pagamento rateale.")

    numero_rate_future = int(numero_rate_future or 0)
    if numero_rate_future < 1:
        raise ValidationError("Il numero di rate future deve essere almeno 1.")
    if numero_rate_future > 36:
        raise ValidationError("Il numero di rate future non puo superare 36.")

    with transaction.atomic():
        iscrizione_locked = Iscrizione.objects.select_for_update().get(pk=iscrizione.pk)
        rata_start = RataIscrizione.objects.select_for_update().get(
            pk=rata_decorrenza.pk,
            iscrizione=iscrizione_locked,
            tipo_rata=RataIscrizione.TIPO_MENSILE,
        )
        if _rata_has_credit_or_discount_activity(rata_start):
            raise ValidationError("La rata di decorrenza ha crediti o sgravi collegati e non puo essere rimodulata.")
        if _rata_residual_amount(rata_start) <= 0:
            raise ValidationError("La rata di decorrenza non ha residuo da rimodulare.")

        decorrenza = _rata_reference_date(rata_start)
        rate_mensili = list(
            RataIscrizione.objects.select_for_update()
            .filter(iscrizione=iscrizione_locked, tipo_rata=RataIscrizione.TIPO_MENSILE)
            .order_by("anno_riferimento", "mese_riferimento", "numero_rata", "id")
        )
        rate_da_sostituire = [
            rata
            for rata in rate_mensili
            if _rata_reference_date(rata) >= decorrenza and _rata_residual_amount(rata) > 0
        ]
        if not rate_da_sostituire:
            raise ValidationError("Non ci sono rate future da rimodulare dalla decorrenza scelta.")

        rate_bloccate = [rata for rata in rate_da_sostituire if _rata_has_credit_or_discount_activity(rata)]
        if rate_bloccate:
            raise ValidationError(
                "Esistono rate future con crediti o sgravi. "
                "Scegli una decorrenza successiva oppure gestisci prima quelle rate."
            )

        totale_precedente = sum(_rata_residual_amount(rata) for rata in rate_da_sostituire)
        if totale_precedente <= 0:
            raise ValidationError("Non ci sono importi residui da rimodulare dalla decorrenza scelta.")

        if modalita == RimodulazioneRetta.MODALITA_RIDISTRIBUISCI_RESIDUO:
            residuo_rimodulato = totale_precedente
            importi_residui = _split_amount(residuo_rimodulato, numero_rate_future)
            importo_mensile_effettivo = None
        elif modalita == RimodulazioneRetta.MODALITA_IMPORTO_MENSILE:
            importo_mensile_effettivo = importo_mensile or Decimal("0.00")
            if importo_mensile_effettivo <= 0:
                raise ValidationError("Il nuovo importo mensile deve essere maggiore di zero.")
            for rata in rate_da_sostituire[:numero_rate_future]:
                if importo_mensile_effettivo < _rata_paid_amount(rata):
                    raise ValidationError(
                        "Il nuovo importo mensile non puo essere inferiore agli importi gia pagati."
                    )
            importi_finali = [importo_mensile_effettivo for _index in range(numero_rate_future)]
        elif modalita == RimodulazioneRetta.MODALITA_TOTALE_RESIDUO:
            residuo_rimodulato = totale_residuo or Decimal("0.00")
            if residuo_rimodulato <= 0:
                raise ValidationError("Il nuovo totale residuo deve essere maggiore di zero.")
            importi_residui = _split_amount(residuo_rimodulato, numero_rate_future)
            importo_mensile_effettivo = None
        else:
            raise ValidationError("Modalita di rimodulazione non valida.")

        giorno_scadenza = decorrenza.day or iscrizione_locked.get_giorno_scadenza_rate()
        rate_sostituite_count = len(rate_da_sostituire)

        if modalita in {
            RimodulazioneRetta.MODALITA_RIDISTRIBUISCI_RESIDUO,
            RimodulazioneRetta.MODALITA_TOTALE_RESIDUO,
        }:
            importi_finali = []
            for indice, importo_residuo in enumerate(importi_residui):
                rata_esistente = rate_da_sostituire[indice] if indice < len(rate_da_sostituire) else None
                importi_finali.append(
                    _rata_paid_amount(rata_esistente) + importo_residuo
                    if rata_esistente
                    else importo_residuo
                )

        rate_in_eccesso = rate_da_sostituire[numero_rate_future:]
        rate_in_eccesso_bloccate = [
            rata
            for rata in rate_in_eccesso
            if _rata_paid_amount(rata) > 0 or rata.pagata
        ]
        if rate_in_eccesso_bloccate:
            raise ValidationError(
                "Non puoi ridurre il numero di rate sotto le rate future che hanno gia importi pagati."
            )
        if rate_in_eccesso:
            RataIscrizione.objects.filter(pk__in=[rata.pk for rata in rate_in_eccesso]).delete()

        nuove_rate = []
        ultima_rata = rate_da_sostituire[-1]
        ultimo_numero_rata = max(rata.numero_rata for rata in rate_mensili)
        for indice, importo_finale in enumerate(importi_finali):
            rata_esistente = rate_da_sostituire[indice] if indice < len(rate_da_sostituire) else None
            if rata_esistente:
                importo_pagato = _rata_paid_amount(rata_esistente)
                rata_esistente.importo_dovuto = importo_finale
                rata_esistente.credito_applicato = Decimal("0.00")
                rata_esistente.altri_sgravi = Decimal("0.00")
                rata_esistente.importo_finale = importo_finale
                rata_esistente.pagata = importo_finale > 0 and importo_pagato >= importo_finale
                rata_esistente.save(
                    update_fields=[
                        "importo_dovuto",
                        "credito_applicato",
                        "altri_sgravi",
                        "importo_finale",
                        "pagata",
                    ]
                )
                continue

            extra_index = indice - len(rate_da_sostituire) + 1
            data_scadenza = _add_months_from_rate(ultima_rata, extra_index, giorno_scadenza)
            numero_rata = ultimo_numero_rata + extra_index
            nuove_rate.append(
                RataIscrizione(
                    iscrizione=iscrizione_locked,
                    tipo_rata=RataIscrizione.TIPO_MENSILE,
                    numero_rata=numero_rata,
                    mese_riferimento=data_scadenza.month,
                    anno_riferimento=data_scadenza.year,
                    descrizione=f"Rata rimodulata {indice + 1}/{numero_rate_future} - {data_scadenza.strftime('%m/%Y')}",
                    importo_dovuto=importo_finale,
                    data_scadenza=data_scadenza,
                    credito_applicato=Decimal("0.00"),
                    altri_sgravi=Decimal("0.00"),
                    importo_finale=importo_finale,
                )
            )
        RataIscrizione.objects.bulk_create(nuove_rate)

        totale_rimodulato = sum(
            max(importo_finale - _rata_paid_amount(rate_da_sostituire[indice]), Decimal("0.00"))
            if indice < len(rate_da_sostituire)
            else importo_finale
            for indice, importo_finale in enumerate(importi_finali)
        )

        rimodulazione = RimodulazioneRetta.objects.create(
            iscrizione=iscrizione_locked,
            data_decorrenza=decorrenza,
            modalita=modalita,
            numero_rate_future=numero_rate_future,
            importo_mensile=importo_mensile_effettivo,
            totale_precedente=totale_precedente,
            totale_rimodulato=totale_rimodulato,
            rate_sostituite=rate_sostituite_count,
            note=note or "",
            creata_da=utente if getattr(utente, "is_authenticated", False) else None,
        )
        iscrizione_locked._sincronizza_fondo_accantonamento_su_agevolazione()

    return rimodulazione


def ricalcola_rate_anno_scolastico(anno_scolastico):
    """Ricalcola i piani rate delle iscrizioni attive di un anno scolastico."""

    summary = Counter()
    errori = []

    iscrizioni = (
        Iscrizione.objects.filter(anno_scolastico=anno_scolastico, attiva=True)
        .select_related(
            "studente",
            "anno_scolastico",
            "condizione_iscrizione",
            "agevolazione",
        )
        .prefetch_related("rate")
        .order_by("studente__cognome", "studente__nome", "id")
    )

    for iscrizione in iscrizioni:
        try:
            summary[iscrizione.sync_rate_schedule()] += 1
        except Exception as exc:
            summary["error"] += 1
            errori.append(f"{iscrizione}: {exc}")

    return {
        "totale": sum(summary.values()),
        "summary": dict(summary),
        "errori": errori,
    }


def build_rate_batch_feedback(summary):
    if not summary:
        return "Nessuna iscrizione elaborata."

    feedback_parts = []
    if summary.get("created"):
        feedback_parts.append(f"{summary['created']} piano/i rate creati")
    if summary.get("precreated"):
        feedback_parts.append(f"{summary['precreated']} preiscrizione/i aggiunte")
    if summary.get("regenerated"):
        feedback_parts.append(f"{summary['regenerated']} piano/i rate riallineati")
    if summary.get("unchanged"):
        feedback_parts.append(f"{summary['unchanged']} gia allineati")
    if summary.get("locked"):
        feedback_parts.append(f"{summary['locked']} non modificati perche con pagamenti o movimenti")
    if summary.get("missing"):
        feedback_parts.append(f"{summary['missing']} non generabili per assenza dati tariffari")
    if summary.get("error"):
        feedback_parts.append(f"{summary['error']} con errore")

    return ". ".join(feedback_parts) if feedback_parts else "Nessuna iscrizione elaborata."


def _movimenti_da_riconciliare(data_inizio=None, data_fine=None):
    from gestione_finanziaria.models import MovimentoFinanziario, StatoRiconciliazione

    movimenti = MovimentoFinanziario.objects.filter(
        importo__gt=0,
        rata_iscrizione__isnull=True,
        riconciliazioni_rate__isnull=True,
    ).exclude(stato_riconciliazione=StatoRiconciliazione.IGNORATO)

    if data_inizio and data_fine:
        movimenti = movimenti.filter(
            data_contabile__gte=data_inizio - timedelta(days=90),
            data_contabile__lte=data_fine + timedelta(days=180),
        )

    return movimenti.distinct().order_by("data_contabile", "id")


def _rate_disponibili_queryset():
    from economia.models.iscrizioni import RataIscrizione

    return (
        RataIscrizione.objects.select_related(
            "iscrizione__studente",
            "iscrizione__anno_scolastico",
        )
        .prefetch_related(
            "iscrizione__studente__relazioni_familiari__familiare",
            "iscrizione__studente__relazioni_familiari__relazione_familiare",
        )
        .filter(
            pagata=False,
            importo_finale__gt=0,
            movimenti_finanziari__isnull=True,
            riconciliazioni_movimenti__isnull=True,
        )
        .distinct()
        .order_by("iscrizione__studente__cognome", "iscrizione__studente__nome", "anno_riferimento", "mese_riferimento", "numero_rata", "id")
    )


def _riconcilia_movimenti_con_rate(
    movimenti,
    *,
    include_rata,
    rate_queryset=None,
    utente=None,
    punteggio_minimo=PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA,
):
    from gestione_finanziaria.services import (
        riconcilia_movimento_con_rata,
        riconcilia_movimento_con_rate,
        trova_rate_candidate,
        trova_rate_cumulative_candidate,
    )

    anteprima = _preview_riconcilia_movimenti_con_rate(
        movimenti,
        include_rata=include_rata,
        rate_queryset=rate_queryset,
        punteggio_minimo=punteggio_minimo,
    )
    stats = Counter(anteprima["stats"])
    dettagli = []

    for item in anteprima["dettagli"]:
        movimento = item["movimento"]
        allocazioni = [(allocazione["rata"], allocazione["importo"]) for allocazione in item["allocazioni"]]

        if item["tipo"] == "cumulativa":
            riconcilia_movimento_con_rate(movimento, allocazioni, utente=utente)
            stats["riconciliati_cumulativi"] += 1
        else:
            riconcilia_movimento_con_rata(
                movimento,
                allocazioni[0][0],
                utente=utente,
                marca_rata_pagata=True,
            )
        dettagli.append(
            {
                "movimento_id": movimento.pk,
                "rate_ids": [rata.pk for rata, _importo in allocazioni],
                "score": item["score"],
                "tipo": item["tipo"],
            }
        )
        stats["riconciliati"] += 1

    stats["proposti"] = len(anteprima["dettagli"])

    return {
        "stats": dict(stats),
        "dettagli": dettagli,
    }


def _preview_riconcilia_movimenti_con_rate(
    movimenti,
    *,
    include_rata,
    rate_queryset=None,
    punteggio_minimo=PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA,
):
    from gestione_finanziaria.services import (
        trova_rate_candidate,
        trova_rate_cumulative_candidate,
    )

    stats = Counter()
    dettagli = []
    rate_pool = list(rate_queryset) if rate_queryset is not None else None
    rate_pool_escluse_ids = set()

    for movimento in movimenti:
        stats["movimenti_esaminati"] += 1

        movimento._arboris_importo_disponibile_cache = abs(movimento.importo or 0)
        rate_pool_disponibili = None
        if rate_pool is not None:
            rate_pool_disponibili = [
                rata
                for rata in rate_pool
                if rata.pk not in rate_pool_escluse_ids and not rata.pagata
            ]

        candidati = [
            candidato
            for candidato in trova_rate_candidate(
                movimento,
                limite=10,
                solo_disponibili=True,
                rate_pool=rate_pool_disponibili,
            )
            if include_rata(candidato.rata)
            and not candidato.rata.pagata
            and candidato.rata.pk not in rate_pool_escluse_ids
        ]
        candidati_cumulativi = trova_rate_cumulative_candidate(
            movimento,
            limite=5,
            include_rata=include_rata,
            rate_pool=rate_pool_disponibili,
        )

        opzioni = [("singola", candidato.score, candidato) for candidato in candidati]
        opzioni.extend(("cumulativa", candidato.score, candidato) for candidato in candidati_cumulativi)

        if not opzioni:
            stats["senza_candidati"] += 1
            continue

        top_score = max(score for _tipo, score, _candidato in opzioni)
        migliori = [(tipo, candidato) for tipo, score, candidato in opzioni if score == top_score]

        if top_score < punteggio_minimo:
            stats["score_basso"] += 1
            continue

        if len(migliori) > 1:
            stats["ambigui"] += 1
            continue

        tipo, candidato = migliori[0]
        if tipo == "cumulativa":
            rate_pool_escluse_ids.update(rata.pk for rata, _importo in candidato.allocazioni)
            allocazioni = candidato.allocazioni
        else:
            rate_pool_escluse_ids.add(candidato.rata.pk)
            allocazioni = [(candidato.rata, abs(movimento.importo or Decimal("0.00")))]

        stats["proposti"] += 1
        if tipo == "cumulativa":
            stats["proposti_cumulativi"] += 1
        dettagli.append(
            {
                "key": _build_riconciliazione_preview_key(movimento.pk, allocazioni),
                "movimento": movimento,
                "tipo": tipo,
                "score": candidato.score,
                "motivazioni": candidato.motivazioni,
                "allocazioni": [
                    {
                        "rata": rata,
                        "importo": importo,
                    }
                    for rata, importo in allocazioni
                ],
            }
        )

    return {
        "stats": dict(stats),
        "dettagli": dettagli,
    }


def _build_riconciliazione_preview_key(movimento_id, allocazioni):
    rate_part = "-".join(str(rata.pk) for rata, _importo in allocazioni)
    return f"{movimento_id}:{rate_part}"


def _serializza_anteprima_riconciliazione_rate(anteprima):
    dettagli = []
    for item in anteprima["dettagli"]:
        movimento = item["movimento"]
        dettagli.append(
            {
                "key": item["key"],
                "tipo": item["tipo"],
                "score": item["score"],
                "motivazioni": item["motivazioni"],
                "movimento_id": movimento.pk,
                "movimento_data": movimento.data_contabile.isoformat() if movimento.data_contabile else "",
                "movimento_descrizione": movimento.descrizione or "",
                "movimento_controparte": movimento.controparte or "",
                "movimento_conto": str(movimento.conto) if movimento.conto_id else "",
                "movimento_importo": str(abs(movimento.importo or Decimal("0.00"))),
                "allocazioni": [
                    {
                        "rata_id": allocazione["rata"].pk,
                        "rata_label": str(allocazione["rata"]),
                        "studente": str(getattr(allocazione["rata"].iscrizione, "studente", "") or ""),
                        "famiglia": "",
                        "importo": str(allocazione["importo"]),
                    }
                    for allocazione in item["allocazioni"]
                ],
            }
        )
    return {
        "stats": anteprima["stats"],
        "dettagli": dettagli,
    }


def _applica_anteprima_riconciliazione_rate(dettagli, selected_keys, *, utente=None):
    from django.core.exceptions import ValidationError
    from economia.models.iscrizioni import RataIscrizione
    from gestione_finanziaria.models import MovimentoFinanziario
    from gestione_finanziaria.services import riconcilia_movimento_con_rate

    selected_keys = set(selected_keys or [])
    stats = Counter()
    errori = []
    applicati = []

    for item in dettagli:
        if item.get("key") not in selected_keys:
            continue
        stats["selezionati"] += 1
        try:
            movimento = MovimentoFinanziario.objects.get(pk=item["movimento_id"])
            allocazioni = []
            for allocazione in item.get("allocazioni", []):
                rata = RataIscrizione.objects.select_related(
                    "iscrizione__studente",
                    "iscrizione__anno_scolastico",
                ).get(pk=allocazione["rata_id"])
                allocazioni.append((rata, Decimal(str(allocazione["importo"]))))
            riconcilia_movimento_con_rate(movimento, allocazioni, utente=utente)
        except (MovimentoFinanziario.DoesNotExist, RataIscrizione.DoesNotExist, InvalidOperation, ValidationError) as exc:
            stats["errori"] += 1
            errori.append(f"{item.get('movimento_descrizione') or item.get('movimento_id')}: {exc}")
            continue
        stats["riconciliati"] += 1
        if item.get("tipo") == "cumulativa":
            stats["riconciliati_cumulativi"] += 1
        applicati.append(item)

    stats["movimenti_esaminati"] = stats.get("selezionati", 0)
    return {
        "stats": dict(stats),
        "dettagli": applicati,
        "errori": errori,
    }


def riconcilia_pagamenti_rate_anno_scolastico(
    anno_scolastico,
    *,
    utente=None,
    punteggio_minimo=PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA,
):
    """
    Riconcilia in modo conservativo i movimenti bancari con le rate dell'anno.

    La procedura collega solo candidati unici sopra soglia, lasciando all'utente
    la riconciliazione manuale dei casi ambigui o con score basso.
    """

    movimenti = _movimenti_da_riconciliare(anno_scolastico.data_inizio, anno_scolastico.data_fine)
    rate_queryset = _rate_disponibili_queryset().filter(iscrizione__anno_scolastico=anno_scolastico)
    return _riconcilia_movimenti_con_rate(
        movimenti,
        include_rata=lambda rata: rata.iscrizione.anno_scolastico_id == anno_scolastico.pk,
        rate_queryset=rate_queryset,
        utente=utente,
        punteggio_minimo=punteggio_minimo,
    )


def anteprima_riconcilia_pagamenti_rate_anno_scolastico(
    anno_scolastico,
    *,
    punteggio_minimo=PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA,
):
    movimenti = _movimenti_da_riconciliare(anno_scolastico.data_inizio, anno_scolastico.data_fine)
    rate_queryset = _rate_disponibili_queryset().filter(iscrizione__anno_scolastico=anno_scolastico)
    anteprima = _preview_riconcilia_movimenti_con_rate(
        movimenti,
        include_rata=lambda rata: rata.iscrizione.anno_scolastico_id == anno_scolastico.pk,
        rate_queryset=rate_queryset,
        punteggio_minimo=punteggio_minimo,
    )
    return _serializza_anteprima_riconciliazione_rate(anteprima)


def riconcilia_pagamenti_iscrizione(
    iscrizione,
    *,
    utente=None,
    punteggio_minimo=PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA,
):
    """Riconcilia in modo conservativo i movimenti bancari con una sola iscrizione."""

    anno = iscrizione.anno_scolastico
    movimenti = _movimenti_da_riconciliare(anno.data_inizio, anno.data_fine)
    rate_queryset = _rate_disponibili_queryset().filter(iscrizione=iscrizione)
    return _riconcilia_movimenti_con_rate(
        movimenti,
        include_rata=lambda rata: rata.iscrizione_id == iscrizione.pk,
        rate_queryset=rate_queryset,
        utente=utente,
        punteggio_minimo=punteggio_minimo,
    )


def anteprima_riconcilia_pagamenti_iscrizione(
    iscrizione,
    *,
    punteggio_minimo=PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA,
):
    anno = iscrizione.anno_scolastico
    movimenti = _movimenti_da_riconciliare(anno.data_inizio, anno.data_fine)
    rate_queryset = _rate_disponibili_queryset().filter(iscrizione=iscrizione)
    anteprima = _preview_riconcilia_movimenti_con_rate(
        movimenti,
        include_rata=lambda rata: rata.iscrizione_id == iscrizione.pk,
        rate_queryset=rate_queryset,
        punteggio_minimo=punteggio_minimo,
    )
    return _serializza_anteprima_riconciliazione_rate(anteprima)


def applica_anteprima_riconciliazione_rate(dettagli, selected_keys, *, utente=None):
    return _applica_anteprima_riconciliazione_rate(dettagli, selected_keys, utente=utente)


def build_riconciliazione_batch_feedback(stats):
    if not stats:
        return "Nessun movimento esaminato."

    return (
        f"{stats.get('riconciliati', 0)} movimento/i riconciliati su "
        f"{stats.get('movimenti_esaminati', 0)} esaminati. "
        f"{stats.get('riconciliati_cumulativi', 0)} cumulativi, "
        f"{stats.get('ambigui', 0)} ambigui, "
        f"{stats.get('score_basso', 0)} con affidabilita bassa, "
        f"{stats.get('senza_candidati', 0)} senza candidati."
    )
