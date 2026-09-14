"""One bounded worker per database; queued work survives worker/process failures."""
import logging
import sys
import threading
import time

from django.conf import settings
from django.db import close_old_connections, connections, transaction
from django.db.models import F
from django.utils import timezone
from datetime import timedelta

from .models import RichiestaAnalisiRiconciliazione, StatoAnalisiRiconciliazione

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_thread = None
_loop = None
_last_kick = 0


def process_pending_analysis(*, limit=40, max_seconds=20):
    from .reconciliation import analyse_request

    started = time.monotonic()
    processed = 0
    StatoAnalisiRiconciliazione.objects.get_or_create(pk=1)
    while processed < limit and time.monotonic() - started < max_seconds:
        job_id = None
        try:
            with transaction.atomic():
                lock = StatoAnalisiRiconciliazione.objects.select_for_update(skip_locked=True).filter(pk=1).first()
                if lock is None:
                    break
                job = RichiestaAnalisiRiconciliazione.objects.select_for_update().filter(
                    riprova_il__lte=timezone.now(),
                ).order_by("richiesta_il", "id").first()
                if job is None:
                    break
                job_id = job.pk
                analyse_request(job.tipo, job.oggetto_id)
                job.delete()
            processed += 1
        except Exception:
            logger.exception("Analisi riconciliazioni non completata (richiesta %s).", job_id)
            if job_id is None:
                raise
            RichiestaAnalisiRiconciliazione.objects.filter(pk=job_id).update(
                tentativi=F("tentativi") + 1,
                riprova_il=timezone.now() + timedelta(minutes=2),
                errore="Analisi non completata. Il sistema riproverà automaticamente.",
            )
            processed += 1
    return processed


def _enabled():
    from .background_scheduler import should_start_background_scheduler

    if any("celery" in arg.lower() for arg in sys.argv[:2]):
        return False
    return should_start_background_scheduler(enabled_env_var="ARBORIS_RECONCILIATION_ENABLED")[0]


def _dispatch():
    close_old_connections()
    try:
        if not RichiestaAnalisiRiconciliazione.objects.filter(riprova_il__lte=timezone.now()).exists():
            return
        if getattr(settings, "CELERY_BROKER_URL", ""):
            from .tasks import analyse_reconciliation_task

            analyse_reconciliation_task.apply_async(retry=False)
        else:
            process_pending_analysis()
    except Exception:
        logger.exception("Avvio analisi rinviato; le richieste restano in coda.")
    finally:
        connections.close_all()


def kick_analysis():
    global _thread, _last_kick
    if not _enabled():
        return False
    with _lock:
        if (_thread and _thread.is_alive()) or time.monotonic() - _last_kick < 2:
            return False
        _last_kick = time.monotonic()
        _thread = threading.Thread(target=_dispatch, daemon=True, name="arboris-reconciliation")
        _thread.start()
    return True


def start_analysis_worker():
    global _loop
    if not _enabled() or (_loop and _loop.is_alive()):
        return

    def run():
        while True:
            kick_analysis()
            time.sleep(30)

    _loop = threading.Thread(target=run, daemon=True, name="arboris-reconciliation-wakeup")
    _loop.start()
