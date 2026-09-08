"""Visibilità e letture delle notifiche, persistenti per account."""

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from sistema.models import LivelloPermesso
from sistema.permissions import user_has_module_permission

from .models import DocumentoFornitore, NotificaFinanziaria, NotificaFinanziariaLettura


def notifiche_per_utente(user):
    if not getattr(user, "is_authenticated", False):
        return NotificaFinanziaria.objects.none()
    letture = NotificaFinanziariaLettura.objects.filter(user=user, notifica_id=OuterRef("pk"))
    notifiche = NotificaFinanziaria.objects.annotate(letta=Exists(letture))
    if not user_has_module_permission(user, "gestione_finanziaria", LivelloPermesso.GESTIONE):
        notifiche = notifiche.filter(richiede_gestione=False)
    return notifiche


def riepilogo_notifiche(user):
    non_lette = notifiche_per_utente(user).filter(letta=False)
    return {
        "notifiche_finanziarie_non_lette": non_lette.count(),
        "notifiche_finanziarie_recenti": list(non_lette.order_by("-data_creazione", "-id")[:5]),
    }


@transaction.atomic
def notifica_documento_importato(documento, defaults):
    """Una notifica per documento Arboris, anche cambiando ID nell'import."""
    DocumentoFornitore.objects.select_for_update().get(pk=documento.pk)
    chiave = f"fic-documento-{documento.pk}"
    esistenti = list(NotificaFinanziaria.objects.select_for_update().filter(
        Q(chiave_deduplica__startswith="fic-document-") | Q(chiave_deduplica=chiave),
        documento=documento, tipo="fattura_ricevuta",
    ).order_by("id"))
    if not esistenti:
        return NotificaFinanziaria.objects.create(chiave_deduplica=chiave, **defaults), True
    conservata = next((n for n in esistenti if n.chiave_deduplica == chiave), esistenti[0])
    for duplicata in esistenti:
        if duplicata.pk == conservata.pk:
            continue
        utenti_lettori = NotificaFinanziariaLettura.objects.filter(notifica=conservata).values("user_id")
        NotificaFinanziariaLettura.objects.filter(notifica=duplicata).exclude(user_id__in=utenti_lettori).update(notifica=conservata)
        duplicata.delete()
    if conservata.chiave_deduplica != chiave:
        conservata.chiave_deduplica = chiave
        conservata.save(update_fields=["chiave_deduplica"])
    return conservata, False
