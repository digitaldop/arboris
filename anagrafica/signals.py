import logging

from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import Documento
from .storage_utils import DOCUMENT_STORAGE_ERROR_TYPES


logger = logging.getLogger(__name__)


def _delete_document_file_if_unused(file_name, *, exclude_pk=None):
    if not file_name:
        return

    remaining_documents = Documento.objects.filter(file=file_name)
    if exclude_pk is not None:
        remaining_documents = remaining_documents.exclude(pk=exclude_pk)
    if remaining_documents.exists():
        return

    storage = Documento._meta.get_field("file").storage
    try:
        if storage.exists(file_name):
            storage.delete(file_name)
    except DOCUMENT_STORAGE_ERROR_TYPES as exc:
        logger.warning(
            "Impossibile eliminare il file documento '%s' dallo storage configurato: %s",
            file_name,
            exc,
        )


@receiver(pre_save, sender=Documento)
def delete_replaced_document_file(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        current_document = sender.objects.only("file").get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    old_name = getattr(current_document.file, "name", "")
    new_name = getattr(instance.file, "name", "")
    if not old_name or old_name == new_name:
        return

    transaction.on_commit(lambda: _delete_document_file_if_unused(old_name, exclude_pk=instance.pk))


@receiver(post_delete, sender=Documento)
def delete_document_file_on_delete(sender, instance, **kwargs):
    file_name = getattr(instance.file, "name", "")
    if not file_name:
        return

    transaction.on_commit(lambda: _delete_document_file_if_unused(file_name))
