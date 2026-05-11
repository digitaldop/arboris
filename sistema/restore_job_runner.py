"""
Esecuzione del ripristino database da SistemaDatabaseRestoreJob (task Celery o thread).
"""
from __future__ import annotations

import logging

from django.db import connections
from django.utils import timezone

from .database_backups import (
    DatabaseBackupError,
    delete_restore_file_reference,
    is_restore_upload_reference,
    restore_database_from_backup_file,
    restore_file_reference_exists,
)
from .models import SistemaDatabaseRestoreJob, StatoRipristinoDatabase

logger = logging.getLogger(__name__)


def _record_restore_job_outcome(
    *,
    job_id: int,
    stato: str,
    percorso_file: str,
    nome_file_originale: str,
    dimensione_file_bytes: int,
    data_avvio_ripristino,
    celery_task_id: str = "",
    messaggio_errore: str = "",
) -> None:
    """
    Registra l'esito anche dopo il DROP SCHEMA del restore.

    Durante il ripristino viene sostituito anche il database che contiene il record
    del job. Per questo non possiamo continuare a usare l'istanza ORM caricata prima
    del restore: dopo l'import proviamo a ricreare/aggiornare un record minimale.
    """
    try:
        if not connections["default"].in_atomic_block:
            connections.close_all()
        SistemaDatabaseRestoreJob.objects.update_or_create(
            pk=job_id,
            defaults={
                "stato": stato,
                "percorso_file": percorso_file,
                "nome_file_originale": nome_file_originale,
                "dimensione_file_bytes": dimensione_file_bytes or 0,
                "data_avvio_ripristino": data_avvio_ripristino,
                "data_completamento": timezone.now(),
                "messaggio_errore": messaggio_errore,
                "celery_task_id": (celery_task_id or "")[:120],
                "backup_sicurezza": None,
            },
        )
    except Exception:
        logger.exception("impossibile registrare l'esito del restore job %s dopo il ripristino", job_id)


def run_restore_job(job_id: int, *, celery_task_id: str = "") -> None:
    """
    Transizione in_coda → in_corso → completato/errore. Idempotente se job già terminato.
    """
    try:
        job = SistemaDatabaseRestoreJob.objects.get(pk=job_id)
    except SistemaDatabaseRestoreJob.DoesNotExist:
        logger.warning("restore job %s non trovato", job_id)
        return

    if job.stato in (
        StatoRipristinoDatabase.COMPLETATO,
        StatoRipristinoDatabase.ERRORE,
        StatoRipristinoDatabase.ANNULLATO,
    ):
        return

    if job.stato not in (StatoRipristinoDatabase.IN_CODA,):
        logger.warning("restore job %s stato inatteso: %s", job_id, job.stato)
        return

    if not restore_file_reference_exists(job.percorso_file):
        job.stato = StatoRipristinoDatabase.ERRORE
        job.messaggio_errore = "File di backup non trovato nello storage (scaduto o rimosso)."
        job.data_completamento = timezone.now()
        job.save(update_fields=["stato", "messaggio_errore", "data_completamento"])
        return

    percorso_file = job.percorso_file
    nome_file_originale = job.nome_file_originale
    dimensione_file_bytes = job.dimensione_file_bytes
    creato_da = job.creato_da
    data_avvio_ripristino = timezone.now()

    job.stato = StatoRipristinoDatabase.IN_CORSO
    job.data_avvio_ripristino = data_avvio_ripristino
    update_fields = ["stato", "data_avvio_ripristino"]
    if celery_task_id:
        job.celery_task_id = celery_task_id[:120]
        update_fields.append("celery_task_id")
    job.save(update_fields=update_fields)

    try:
        restore_database_from_backup_file(
            percorso_file,
            original_name=nome_file_originale,
            triggered_by=creato_da,
        )
    except DatabaseBackupError as exc:
        _record_restore_job_outcome(
            job_id=job_id,
            stato=StatoRipristinoDatabase.ERRORE,
            percorso_file=percorso_file,
            nome_file_originale=nome_file_originale,
            dimensione_file_bytes=dimensione_file_bytes,
            data_avvio_ripristino=data_avvio_ripristino,
            celery_task_id=celery_task_id,
            messaggio_errore=str(exc),
        )
    else:
        _record_restore_job_outcome(
            job_id=job_id,
            stato=StatoRipristinoDatabase.COMPLETATO,
            percorso_file=percorso_file,
            nome_file_originale=nome_file_originale,
            dimensione_file_bytes=dimensione_file_bytes,
            data_avvio_ripristino=data_avvio_ripristino,
            celery_task_id=celery_task_id,
        )
        if is_restore_upload_reference(percorso_file):
            delete_restore_file_reference(percorso_file)
    finally:
        if not connections["default"].in_atomic_block:
            connections.close_all()
