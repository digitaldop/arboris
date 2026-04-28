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
    ).exclude(stato_riconciliazione=StatoRiconciliazione.IGNORATO)

    if data_inizio and data_fine:
        movimenti = movimenti.filter(
            data_contabile__gte=data_inizio - timedelta(days=90),
            data_contabile__lte=data_fine + timedelta(days=180),
        )

    return movimenti.order_by("data_contabile", "id")


def _riconcilia_movimenti_con_rate(
    movimenti,
    *,
    include_rata,
    utente=None,
    punteggio_minimo=PUNTEGGIO_MINIMO_RICONCILIAZIONE_AUTOMATICA,
):
    from gestione_finanziaria.services import riconcilia_movimento_con_rata, trova_rate_candidate

    stats = Counter()
    dettagli = []

    for movimento in movimenti:
        stats["movimenti_esaminati"] += 1
        candidati = [
            candidato
            for candidato in trova_rate_candidate(movimento, limite=10)
            if include_rata(candidato.rata)
            and not candidato.rata.pagata
            and not candidato.rata.movimenti_finanziari.exists()
        ]

        if not candidati:
            stats["senza_candidati"] += 1
            continue

        top_score = candidati[0].score
        migliori = [candidato for candidato in candidati if candidato.score == top_score]

        if top_score < punteggio_minimo:
            stats["score_basso"] += 1
            continue

        if len(migliori) > 1:
            stats["ambigui"] += 1
            continue

        candidato = migliori[0]
        riconcilia_movimento_con_rata(
            movimento,
            candidato.rata,
            utente=utente,
            marca_rata_pagata=True,
        )
        stats["riconciliati"] += 1
        dettagli.append(
            {
                "movimento_id": movimento.pk,
                "rata_id": candidato.rata.pk,
                "score": candidato.score,
            }
        )

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
    return _riconcilia_movimenti_con_rate(
        movimenti,
        include_rata=lambda rata: rata.iscrizione.anno_scolastico_id == anno_scolastico.pk,
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
    return _riconcilia_movimenti_con_rate(
        movimenti,
        include_rata=lambda rata: rata.iscrizione_id == iscrizione.pk,
        utente=utente,
        punteggio_minimo=punteggio_minimo,
    )


def build_riconciliazione_batch_feedback(stats):
    if not stats:
        return "Nessun movimento esaminato."

    return (
        f"{stats.get('riconciliati', 0)} movimento/i riconciliati su "
        f"{stats.get('movimenti_esaminati', 0)} esaminati. "
        f"{stats.get('ambigui', 0)} ambigui, "
        f"{stats.get('score_basso', 0)} con affidabilita bassa, "
        f"{stats.get('senza_candidati', 0)} senza candidati."
    )
