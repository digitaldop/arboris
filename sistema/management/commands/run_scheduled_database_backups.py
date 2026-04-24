from django.core.management.base import BaseCommand

from sistema.database_backups import maybe_run_scheduled_backup


class Command(BaseCommand):
    help = "Esegue i backup database automatici in scadenza."

    def handle(self, *args, **options):
        backup = maybe_run_scheduled_backup()
        if backup:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backup automatico creato: {backup.nome_file}"
                )
            )
            return

        self.stdout.write("Nessun backup automatico da eseguire in questo momento.")
