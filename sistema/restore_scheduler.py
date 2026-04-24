"""
Mette in coda l'esecuzione del job: Celery se CELERY_BROKER_URL è configurato, altrimenti thread in background.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)


def schedule_restore_job(job_id: int) -> None:
    broker = (getattr(settings, "CELERY_BROKER_URL", None) or "").strip()
    if broker:
        from sistema.tasks import execute_database_restore_task

        execute_database_restore_task.delay(job_id)
        logger.info("restore job %s accodato su Celery", job_id)
        return

    from sistema.restore_job_runner import run_restore_job

    def _run() -> None:
        try:
            run_restore_job(job_id, celery_task_id="thread")
        except Exception:
            logger.exception("restore job %s fallito nel thread", job_id)

    t = threading.Thread(target=_run, name=f"restore-job-{job_id}", daemon=True)
    t.start()
    logger.info("restore job %s avviato in thread (nessun broker Celery)", job_id)
