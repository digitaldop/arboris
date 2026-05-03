from collections import Counter
from datetime import timedelta

from economia.models import Iscrizione


PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA = 70


def ricalcola_rate_anno_scolastico(anno_scolastico):
    """Ricalcola i piani rate delle iscrizioni attive di un anno scolastico."""

    summary = Counter()
    errori = []

    iscrizioni = (
        Iscrizione.objects.filter(anno_scolastico=anno_scolastico, attiva=True)
        .select_related(
            "studente",
            "studente__famiglia",
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
            "famiglia",
            "iscrizione__studente__famiglia",
            "iscrizione__anno_scolastico",
        )
        .prefetch_related("iscrizione__studente__famiglia__familiari")
        .filter(
            pagata=False,
            importo_finale__gt=0,
            movimenti_finanziari__isnull=True,
            riconciliazioni_movimenti__isnull=True,
        )
        .distinct()
        .order_by("famiglia_id", "anno_riferimento", "mese_riferimento", "numero_rata", "id")
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

    stats = Counter()
    dettagli = []
    rate_pool = list(rate_queryset) if rate_queryset is not None else None
    rate_pool_escluse_ids = set()

    for movimento in movimenti:
        stats["movimenti_esaminati"] += 1

        candidati = [
            candidato
            for candidato in trova_rate_candidate(movimento, limite=10, solo_disponibili=True)
            if include_rata(candidato.rata)
            and not candidato.rata.pagata
            and candidato.rata.pk not in rate_pool_escluse_ids
        ]
        rate_pool_disponibili = None
        if rate_pool is not None:
            rate_pool_disponibili = [
                rata
                for rata in rate_pool
                if rata.pk not in rate_pool_escluse_ids and not rata.pagata
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
            riconcilia_movimento_con_rate(movimento, candidato.allocazioni, utente=utente)
            stats["riconciliati_cumulativi"] += 1
            rate_pool_escluse_ids.update(rata.pk for rata, _importo in candidato.allocazioni)
            dettagli.append(
                {
                    "movimento_id": movimento.pk,
                    "rate_ids": [rata.pk for rata, _importo in candidato.allocazioni],
                    "score": candidato.score,
                    "tipo": "cumulativa",
                }
            )
        else:
            riconcilia_movimento_con_rata(
                movimento,
                candidato.rata,
                utente=utente,
                marca_rata_pagata=True,
            )
            rate_pool_escluse_ids.add(candidato.rata.pk)
            dettagli.append(
                {
                    "movimento_id": movimento.pk,
                    "rata_id": candidato.rata.pk,
                    "score": candidato.score,
                    "tipo": "singola",
                }
            )
        stats["riconciliati"] += 1

    return {
        "stats": dict(stats),
        "dettagli": dettagli,
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
