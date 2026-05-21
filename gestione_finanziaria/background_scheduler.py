from __future__ import annotations

import logging
import os
import sys
import threading
import time

from django.db import close_old_connections


logger = logging.getLogger(__name__)

ENABLE_ENV_VAR = "ARBORIS_BACKGROUND_SCHEDULER_ENABLED"
INTERVAL_ENV_VAR = "ARBORIS_BACKGROUND_SCHEDULER_INTERVAL_SECONDS"
DEFAULT_INTERVAL_SECONDS = 300
MIN_INTERVAL_SECONDS = 60
RUNNER_THREAD_NAME = "arboris-finance-background-scheduler"

_runner_lock = threading.Lock()
_runner_thread: threading.Thread | None = None


def _env_bool(name: str) -> bool | None:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return None
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on", "si"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _configured_interval_seconds() -> int:
    raw_value = os.environ.get(INTERVAL_ENV_VAR, "").strip()
    if raw_value:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = DEFAULT_INTERVAL_SECONDS
    else:
        value = DEFAULT_INTERVAL_SECONDS
    return max(MIN_INTERVAL_SECONDS, value)


def _is_excluded_management_command(argv: list[str]) -> bool:
    excluded_commands = {
        "check",
        "collectstatic",
        "compilemessages",
        "createsuperuser",
        "dumpdata",
        "flush",
        "loaddata",
        "makemigrations",
        "migrate",
        "run_scheduled_psd2_sync",
        "shell",
        "showmigrations",
        "sqlmigrate",
        "test",
    }
    return any(arg in excluded_commands for arg in argv)


def _is_management_command_process(argv: list[str]) -> bool:
    if not argv:
        return False
    executable = os.path.basename(argv[0]).lower()
    return executable in {"manage.py", "django-admin", "django-admin.py"}


def _is_runserver_parent(argv: list[str]) -> bool:
    if "runserver" not in argv:
        return False
    if "--noreload" in argv:
        return False
    return os.environ.get("RUN_MAIN") not in {"true", "1"}


def should_start_background_scheduler() -> tuple[bool, str]:
    forced = _env_bool(ENABLE_ENV_VAR)
    if forced is False:
        return False, f"{ENABLE_ENV_VAR}=0"

    argv = list(sys.argv)
    if _is_management_command_process(argv) and "runserver" not in argv:
        return False, "comando di management"
    if _is_excluded_management_command(argv):
        return False, "comando di management"
    if _is_runserver_parent(argv):
        return False, "processo autoreload in attesa"

    if forced is True:
        return True, f"{ENABLE_ENV_VAR}=1"
    return True, "processo web"


def background_scheduler_status() -> dict[str, object]:
    enabled, reason = should_start_background_scheduler()
    thread_alive = bool(_runner_thread and _runner_thread.is_alive())
    interval_seconds = _configured_interval_seconds()
    return {
        "enabled": enabled,
        "reason": reason,
        "interval_seconds": interval_seconds,
        "interval_minutes": max(1, round(interval_seconds / 60)),
        "thread_alive": thread_alive,
    }


def _run_due_syncs() -> None:
    from .scheduler import maybe_run_scheduled_fatture_in_cloud_sync, maybe_run_scheduled_sync

    close_old_connections()
    try:
        maybe_run_scheduled_sync()
        maybe_run_scheduled_fatture_in_cloud_sync()
    finally:
        close_old_connections()


def _scheduler_loop(interval_seconds: int) -> None:
    initial_delay = min(30, interval_seconds)
    time.sleep(initial_delay)
    while True:
        try:
            _run_due_syncs()
        except Exception:
            logger.exception("Errore durante il controllo automatico delle sincronizzazioni finanziarie.")
        time.sleep(interval_seconds)


def start_background_scheduler_once() -> bool:
    global _runner_thread

    enabled, reason = should_start_background_scheduler()
    if not enabled:
        logger.debug("Background scheduler finanziario non avviato: %s", reason)
        return False

    with _runner_lock:
        if _runner_thread and _runner_thread.is_alive():
            return False

        interval_seconds = _configured_interval_seconds()
        _runner_thread = threading.Thread(
            target=_scheduler_loop,
            args=(interval_seconds,),
            name=RUNNER_THREAD_NAME,
            daemon=True,
        )
        _runner_thread.start()
        logger.info(
            "Background scheduler finanziario avviato ogni %s secondi (%s).",
            interval_seconds,
            reason,
        )
        return True
