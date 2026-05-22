"""
Middleware che integra lo scheduler di sincronizzazione PSD2 nelle richieste
dell'applicazione: a ogni GET/HEAD/OPTIONS con risposta 2xx/3xx su un URL
non statico controlla se la pianificazione e' attiva e in scadenza.

Questa e' una strategia "best effort" che dipende dal traffico.
Per esecuzioni indipendenti dal traffico si usa il management command
``run_scheduled_psd2_sync`` (Windows Task Scheduler / cron).
"""

from __future__ import annotations

import logging

from .background_scheduler import start_background_scheduler_once, trigger_due_sync_check_async


logger = logging.getLogger(__name__)


_EXCLUDE_PATH_PREFIXES = ("/admin/", "/media/", "/static/")


class SincronizzazionePsd2ScheduleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            return response
        if response.status_code >= 500:
            return response

        path = request.path or ""
        for prefix in _EXCLUDE_PATH_PREFIXES:
            if path.startswith(prefix):
                return response

        try:
            start_background_scheduler_once()
            trigger_due_sync_check_async()
        except Exception:
            # La sincronizzazione non deve mai compromettere la richiesta utente.
            logger.exception("Impossibile avviare il controllo asincrono delle sincronizzazioni finanziarie.")

        return response
