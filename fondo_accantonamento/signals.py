from django.db.models.signals import post_save
from django.dispatch import receiver

from economia.models import Iscrizione, RataIscrizione

from .services import (
    sincronizza_sconti_fondo_da_iscrizione,
    sincronizza_versamento_fondo_da_rata,
)


@receiver(post_save, sender=Iscrizione)
def sincronizza_fondo_su_agevolazione_dopo_iscrizione(sender, instance, **kwargs):
    """
    Sincronizza SCONTO_RETTA quando l'iscrizione e' aggiornata senza
    `sync_rate_schedule` (piano bloccato, ecc.) o in contesti oltre l'app economia.
    """
    sincronizza_sconti_fondo_da_iscrizione(instance)


@receiver(post_save, sender=RataIscrizione)
def sincronizza_fondo_dopo_salvataggio_rata(sender, instance, **kwargs):
    """
    Allinea il versamento da percentuale retta al salvataggio della rata
    (form pagamento, pagamento rapido, admin, ecc.).
    """
    rata = (
        RataIscrizione.objects.select_related("iscrizione", "iscrizione__anno_scolastico")
        .filter(pk=instance.pk)
        .first()
    )
    if not rata:
        return
    sincronizza_versamento_fondo_da_rata(rata)
