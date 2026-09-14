"""Persistent analysis requests, written in the same transaction as source changes."""
from django.db import transaction
from django.utils import timezone

from .models import RichiestaAnalisiRiconciliazione


def enqueue_analysis(tipo, oggetto_id, *, using="default"):
    if not oggetto_id:
        return
    now = timezone.now()
    RichiestaAnalisiRiconciliazione.objects.using(using).update_or_create(
        tipo=tipo, oggetto_id=oggetto_id,
        defaults={"richiesta_il": now, "riprova_il": now, "tentativi": 0, "errore": ""},
    )
    from .reconciliation_worker import kick_analysis

    transaction.on_commit(kick_analysis, using=using, robust=True)


def enqueue_existing_movements():
    from .models import MovimentoFinanziario

    ids = MovimentoFinanziario.objects.exclude(stato_riconciliazione="ignorato").values_list("pk", flat=True)
    batch = []
    for pk in ids.iterator(chunk_size=500):
        batch.append(RichiestaAnalisiRiconciliazione(tipo="movimento", oggetto_id=pk))
        if len(batch) == 500:
            RichiestaAnalisiRiconciliazione.objects.bulk_create(batch, ignore_conflicts=True)
            batch = []
    RichiestaAnalisiRiconciliazione.objects.bulk_create(batch, ignore_conflicts=True)
    from .reconciliation_worker import kick_analysis

    transaction.on_commit(kick_analysis, robust=True)
