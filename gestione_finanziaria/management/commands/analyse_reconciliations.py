from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Elabora proposte da confermare, senza registrare pagamenti."

    def add_arguments(self, parser):
        parser.add_argument("--scan-existing", action="store_true", help="Accoda anche i movimenti già presenti.")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--max-seconds", type=int, default=60)

    def handle(self, *args, **options):
        from gestione_finanziaria.reconciliation_queue import enqueue_existing_movements
        from gestione_finanziaria.reconciliation_worker import process_pending_analysis

        if options["scan_existing"]:
            enqueue_existing_movements()
        count = process_pending_analysis(limit=options["limit"], max_seconds=options["max_seconds"])
        self.stdout.write(f"Richieste elaborate: {count}. Nessuna riconciliazione registrata.")
