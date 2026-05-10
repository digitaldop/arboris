from django.core.management.base import BaseCommand

from anagrafica.contact_services import sync_all_student_family_relations


class Command(BaseCommand):
    help = "Riallinea le relazioni dirette studente-familiare dai dati famiglia legacy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra cosa verrebbe riallineato senza modificare il database.",
        )
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Crea solo le relazioni mancanti senza aggiornare quelle gia esistenti.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        update_existing = not options["missing_only"]
        stats = sync_all_student_family_relations(
            dry_run=dry_run,
            update_existing=update_existing,
        )

        mode = "simulazione" if dry_run else "riallineamento"
        self.stdout.write(f"Relazioni anagrafiche: {mode} completata.")
        self.stdout.write(f"Studenti esaminati: {stats['studenti']}")
        self.stdout.write(f"Famiglie con familiari: {stats['famiglie']}")
        self.stdout.write(f"Familiari esaminati: {stats['familiari']}")
        self.stdout.write(f"Relazioni esaminate: {stats['relazioni_esaminate']}")
        self.stdout.write(f"Create: {stats['created']}")
        self.stdout.write(f"Aggiornate: {stats['updated']}")
        self.stdout.write(f"Invariate: {stats['unchanged']}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Nessuna modifica salvata: dry-run attivo."))
        else:
            self.stdout.write(self.style.SUCCESS("Riallineamento salvato correttamente."))
