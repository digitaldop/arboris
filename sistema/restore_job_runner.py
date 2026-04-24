"""
Esecuzione del ripristino database da SistemaDatabaseRestoreJob (task Celery o thread).
"""
from __future__ import annotations

import logging
from pathlib import Path

from django.db import connections
from django.utils import timezone

from .database_backups import DatabaseBackupError, restore_database_from_backup_file
from .models import SistemaDatabaseRestoreJob, StatoRipristinoDatabase

logger = logging.getLogger(__name__)


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

    path = Path(job.percorso_file)
    if not path.exists():
        job.stato = StatoRipristinoDatabase.ERRORE
        job.messaggio_errore = "File di backup non trovato sul server (scaduto o rimosso)."
        job.data_completamento = timezone.now()
        job.save(update_fields=["stato", "messaggio_errore", "data_completamento"])
        return

    job.stato = StatoRipristinoDatabase.IN_CORSO
    job.data_avvio_ripristino = timezone.now()
    if celery_task_id:
        job.celery_task_id = celery_task_id[:120]
    job.save(update_fields=["stato", "data_avvio_ripristino", "celery_task_id"])

    try:
        safety = restore_database_from_backup_file(
            str(path),
            original_name=job.nome_file_originale,
            triggered_by=job.creato_da,
        )
    except DatabaseBackupError as exc:
        job.stato = StatoRipristinoDatabase.ERRORE
        job.messaggio_errore = str(exc)
        job.backup_sicurezza = getattr(exc, "safety_backup", None)
        job.data_completamento = timezone.now()
        job.save()
    else:
        job.stato = StatoRipristinoDatabase.COMPLETATO
        job.backup_sicurezza = safety
        job.messaggio_errore = ""
        job.data_completamento = timezone.now()
        job.save()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    finally:
        connections.close_all()
