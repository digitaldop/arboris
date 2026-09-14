from django.apps import apps
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .reconciliation_queue import enqueue_analysis


@receiver(post_save)
@receiver(post_delete)
def queue_changed_financial_data(sender, instance, using="default", raw=False, **kwargs):
    if raw or sender._meta.apps is not apps:
        return
    label = sender._meta.label_lower
    scope = {
        "gestione_finanziaria.movimentofinanziario": "movimento",
        "gestione_finanziaria.scadenzapagamentofornitore": "scadenza",
        "gestione_finanziaria.documentofornitore": "documento",
        "gestione_finanziaria.fornitore": "fornitore",
        "economia.rataiscrizione": "rata",
        "economia.iscrizione": "iscrizione",
        "anagrafica.studente": "studente",
        "anagrafica.familiare": "familiare",
        "anagrafica.persona": "persona",
    }.get(label)
    if scope:
        enqueue_analysis(scope, instance.pk, using=using)
    elif label == "anagrafica.studentefamiliare":
        enqueue_analysis("studente", instance.studente_id, using=using)
    elif label == "gestione_finanziaria.riconciliazioneratamovimento":
        enqueue_analysis("movimento", instance.movimento_id, using=using)
        enqueue_analysis("rata", instance.rata_id, using=using)
    elif label == "gestione_finanziaria.pagamentofornitore":
        enqueue_analysis("movimento", instance.movimento_finanziario_id, using=using)
        enqueue_analysis("scadenza", instance.scadenza_id, using=using)
