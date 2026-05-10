from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from gestione_amministrativa.payroll_official_data import sync_payroll_official_data


class Command(BaseCommand):
    help = "Aggiorna il catalogo delle fonti e, dove disponibile, importa dati payroll ufficiali strutturati."

    def add_arguments(self, parser):
        parser.add_argument("--anno", type=int, default=timezone.localdate().year)
        parser.add_argument(
            "--solo-catalogo",
            action="store_true",
            help="Aggiorna solo il catalogo delle fonti ufficiali, senza scaricare file remoti.",
        )
        parser.add_argument("--timeout", type=int, default=30)
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            help="Interrompe il comando se una fonte remota non risponde correttamente.",
        )

    def handle(self, *args, **options):
        include_downloads = not options["solo_catalogo"]
        try:
            stats = sync_payroll_official_data(
                anno=options["anno"],
                include_downloads=include_downloads,
                timeout=options["timeout"],
            )
        except Exception as exc:
            if options["fail_fast"]:
                raise CommandError(str(exc)) from exc
            self.stderr.write(self.style.WARNING(f"Aggiornamento parziale: {exc}"))
            stats = sync_payroll_official_data(
                anno=options["anno"],
                include_downloads=False,
                timeout=options["timeout"],
            )

        catalogo = stats.get("catalogo_fonti", {})
        self.stdout.write(
            self.style.SUCCESS(
                "Catalogo fonti aggiornato: "
                f"{catalogo.get('created', 0)} nuove, {catalogo.get('updated', 0)} aggiornate."
            )
        )

        addizionali = stats.get("mef_addizionali", {})
        for label, result in addizionali.items():
            self.stdout.write(
                self.style.SUCCESS(
                    f"Addizionali {label}: "
                    f"{result.get('created', 0)} nuove, "
                    f"{result.get('updated', 0)} aggiornate, "
                    f"{result.get('skipped', 0)} saltate."
                )
            )
