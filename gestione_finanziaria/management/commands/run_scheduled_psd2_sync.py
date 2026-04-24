"""
Management command che esegue una passata di sincronizzazione PSD2 secondo
la pianificazione corrente.

Invocazione tipica da scheduler di sistema:

    # Windows Task Scheduler (ogni ora):
    python manage.py run_scheduled_psd2_sync

    # cron Linux:
    0 * * * * /path/to/venv/bin/python /app/manage.py run_scheduled_psd2_sync

La logica di "e' ora di eseguire?" e' dentro :func:`maybe_run_scheduled_sync`,
quindi e' sicuro chiamare il comando anche piu' frequentemente
dell'intervallo configurato: verra' ignorato se non e' ancora il momento.
Usa ``--force`` per forzare l'esecuzione anche fuori finestra.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from gestione_finanziaria.scheduler import (
    get_or_create_singleton,
    maybe_run_scheduled_sync,
)


class Command(BaseCommand):
    help = "Esegue la sincronizzazione PSD2 pianificata (se dovuta)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Forza l'esecuzione anche se l'intervallo non e' scaduto.",
        )

    def handle(self, *args, **options):
        config = get_or_create_singleton()
        if options["force"]:
            config.ultimo_run_at = timezone.now() - timedelta(days=365)
            config.save(update_fields=["ultimo_run_at", "data_aggiornamento"])

        risultato = maybe_run_scheduled_sync()
        if risultato is None:
            self.stdout.write(self.style.NOTICE(
                "Nessuna sincronizzazione eseguita (pianificazione disattivata, "
                "non ancora dovuta o gia' in corso)."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Esecuzione completata - esito: {risultato.ultimo_esito}, "
            f"conti ok: {risultato.conti_sincronizzati}, in errore: {risultato.conti_in_errore}."
        ))
