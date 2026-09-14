"""Non-blocking, throttled fallback for automatic database backups."""

import logging
import threading
import time

from django.contrib.auth import get_user_model
from django.db import connections

from .audit import reset_current_audit_user, set_current_audit_user
from .database_backups import BACKUP_SCHEDULE_CHECK_TTL_SECONDS, maybe_run_scheduled_backup

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_thread = None
_last_check = None


def _run_backup(user_id):
    token = None
    try:
        user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
        token = set_current_audit_user(user)
        maybe_run_scheduled_backup(user)
    except Exception:
        logger.exception("Errore durante il backup automatico in background.")
    finally:
        if token is not None:
            reset_current_audit_user(token)
        connections.close_all()


def trigger_due_backup_check_async(user=None):
    # Share the process guard, but keep backup and finance opt-outs independent.
    from gestione_finanziaria.background_scheduler import should_start_background_scheduler

    global _thread, _last_check
    if not should_start_background_scheduler(enabled_env_var="ARBORIS_BACKGROUND_BACKUP_ENABLED")[0]:
        return False
    with _lock:
        now = time.monotonic()
        if _thread and _thread.is_alive():
            return False
        if _last_check is not None and now - _last_check < BACKUP_SCHEDULE_CHECK_TTL_SECONDS:
            return False
        user_id = user.pk if getattr(user, "is_authenticated", False) else None
        worker = threading.Thread(
            target=_run_backup, args=(user_id,), name="arboris-backup-check", daemon=True,
        )
        try:
            worker.start()
        except Exception:
            logger.exception("Impossibile avviare il backup automatico in background.")
            return False
        _thread = worker
        _last_check = now
        return True
