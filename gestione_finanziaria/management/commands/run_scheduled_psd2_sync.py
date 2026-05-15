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
Usa ``--force`` per forzare l'esecuzione manuale anche fuori finestra.
"""

from django.core.management.base import BaseCommand

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
            help="Forza l'esecuzione manuale anche se l'intervallo non e' scaduto o la pianificazione automatica e' disattivata.",
        )

    def handle(self, *args, **options):
        get_or_create_singleton()

        risultato = maybe_run_scheduled_sync(force=options["force"])
        if risultato is None:
            if options["force"]:
                messaggio = "Nessuna sincronizzazione eseguita (gia' in corso o lock non disponibile)."
            else:
                messaggio = (
                    "Nessuna sincronizzazione eseguita (pianificazione disattivata, "
                    "non ancora dovuta o gia' in corso)."
                )
            self.stdout.write(self.style.NOTICE(messaggio))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Esecuzione completata - esito: {risultato.ultimo_esito}, "
            f"conti ok: {risultato.conti_sincronizzati}, in errore: {risultato.conti_in_errore}."
        ))
