"""
Pianificatore di sincronizzazione PSD2.

L'approccio e' volutamente leggero: riusa la stessa strategia del backup
automatico (``sistema/database_backups.py``) basata su un singleton di
configurazione e un middleware che, a ogni richiesta idonea, verifica se
c'e' un'esecuzione in scadenza e in tal caso la lancia.

Opzioni per far girare lo scheduler:
- **Middleware** (default): comodo in dev, dipende dal traffico applicativo.
- **Management command** ``run_scheduled_psd2_sync``: da Windows Task Scheduler
  o cron, non dipende dal traffico.
- **APScheduler/Celery**: integrabili in futuro continuando a chiamare
  :func:`maybe_run_scheduled_sync`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.db import OperationalError, ProgrammingError, transaction
from django.utils import timezone

from .models import (
    ContoBancario,
    EsitoSincronizzazione,
    PianificazioneSincronizzazione,
    TipoProviderBancario,
)
from .providers.registry import ProviderConfigurazioneMancante
from .services import sincronizza_conto_psd2


STUCK_TIMEOUT = timedelta(hours=2)


def get_or_create_singleton() -> PianificazioneSincronizzazione:
    config, _ = PianificazioneSincronizzazione.objects.get_or_create(pk=1)
    return config


def is_sync_due(config: PianificazioneSincronizzazione, *, now=None) -> bool:
    if not config.attivo or config.intervallo_ore <= 0:
        return False
    now = now or timezone.now()
    if config.ultimo_run_at is None:
        return True
    return config.ultimo_run_at + timedelta(hours=config.intervallo_ore) <= now


def conti_target():
    """Insieme dei conti sincronizzabili dallo scheduler."""

    return ContoBancario.objects.filter(
        attivo=True,
        provider__attivo=True,
        provider__tipo=TipoProviderBancario.PSD2,
    ).exclude(external_account_id="")


def _acquire_lock(now) -> Optional[PianificazioneSincronizzazione]:
    """Tenta di prendere il lock di esecuzione. Ritorna la config se preso, None altrimenti."""
    try:
        with transaction.atomic():
            PianificazioneSincronizzazione.objects.get_or_create(pk=1)
            config = PianificazioneSincronizzazione.objects.select_for_update().get(pk=1)

            if not is_sync_due(config, now=now):
                return None

            is_stuck = (
                config.in_corso
                and config.avviato_at
                and config.avviato_at < now - STUCK_TIMEOUT
            )
            if config.in_corso and not is_stuck:
                return None

            config.in_corso = True
            config.avviato_at = now
            config.save(
                update_fields=[
                    "in_corso",
                    "avviato_at",
                    "data_aggiornamento",
                ]
            )
            return config
    except (OperationalError, ProgrammingError):
        return None


def maybe_run_scheduled_sync(triggered_by=None) -> Optional[PianificazioneSincronizzazione]:
    """
    Se la pianificazione e' attiva e la prossima esecuzione e' dovuta,
    esegue la sincronizzazione di tutti i conti PSD2 attivi e aggiorna il
    singleton con l'esito complessivo. Ritorna la configurazione se
    l'esecuzione e' partita, None altrimenti.
    """

    now = timezone.now()
    config = _acquire_lock(now)
    if config is None:
        return None

    conti = list(conti_target())
    sincronizzati = 0
    in_errore = 0
    messaggi = []

    for conto in conti:
        try:
            log = sincronizza_conto_psd2(
                conto,
                sync_saldo=config.sync_saldo,
                sync_movimenti=config.sync_movimenti,
                giorni_storico=config.giorni_storico,
            )
            if log.esito == EsitoSincronizzazione.ERRORE:
                in_errore += 1
                messaggi.append(f"{conto.nome_conto}: ERRORE - {log.messaggio[:200]}")
            else:
                sincronizzati += 1
        except ProviderConfigurazioneMancante as exc:
            in_errore += 1
            messaggi.append(f"{conto.nome_conto}: config mancante - {exc}")
        except Exception as exc:
            in_errore += 1
            messaggi.append(f"{conto.nome_conto}: errore imprevisto - {exc}")

    if in_errore == 0 and sincronizzati > 0:
        esito = EsitoSincronizzazione.OK
    elif in_errore > 0 and sincronizzati > 0:
        esito = EsitoSincronizzazione.PARZIALE
    elif in_errore > 0:
        esito = EsitoSincronizzazione.ERRORE
    else:
        esito = EsitoSincronizzazione.OK  # nessun conto da sincronizzare e' comunque "ok"

    testo = f"Conti sincronizzati: {sincronizzati}, in errore: {in_errore}"
    if messaggi:
        testo += "\n" + "\n".join(messaggi[:50])

    with transaction.atomic():
        config = PianificazioneSincronizzazione.objects.select_for_update().get(pk=1)
        config.in_corso = False
        config.ultimo_run_at = timezone.now()
        config.ultimo_esito = esito
        config.ultimo_messaggio = testo[:4000]
        config.conti_sincronizzati = sincronizzati
        config.conti_in_errore = in_errore
        config.save(
            update_fields=[
                "in_corso",
                "ultimo_run_at",
                "ultimo_esito",
                "ultimo_messaggio",
                "conti_sincronizzati",
                "conti_in_errore",
                "data_aggiornamento",
            ]
        )

    return config


def prossima_esecuzione_prevista(config: PianificazioneSincronizzazione):
    if not config.attivo or config.intervallo_ore <= 0:
        return None
    base = config.ultimo_run_at or timezone.now()
    return base + timedelta(hours=config.intervallo_ore)
