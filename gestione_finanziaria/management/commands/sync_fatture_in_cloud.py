from datetime import timedelta

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from gestione_finanziaria.fatture_in_cloud import FattureInCloudError, sincronizza_fatture_in_cloud
from gestione_finanziaria.models import FattureInCloudConnessione
from gestione_finanziaria.scheduler import (
    FIC_SYNC_SCHEDULE_CHECK_CACHE_KEY,
    maybe_run_scheduled_fatture_in_cloud_sync,
)


class Command(BaseCommand):
    help = "Sincronizza le fatture passive da Fatture in Cloud per le connessioni attive."

    def add_arguments(self, parser):
        parser.add_argument("--connessione", type=int, help="ID della connessione da sincronizzare.")
        parser.add_argument(
            "--dal",
            dest="data_inizio",
            help="Sincronizza solo i documenti con data uguale o successiva a YYYY-MM-DD.",
        )
        parser.add_argument(
            "--scheduled",
            action="store_true",
            help="Esegue solo le connessioni dovute secondo la pianificazione.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Con --scheduled forza l'esecuzione azzerando la finestra temporale.",
        )

    def handle(self, *args, **options):
        if options["scheduled"]:
            if options["force"]:
                FattureInCloudConnessione.objects.filter(attiva=True, sync_automatico=True).update(
                    ultimo_sync_at=timezone.now() - timedelta(days=365),
                    in_corso=False,
                )
                cache.delete(FIC_SYNC_SCHEDULE_CHECK_CACHE_KEY)
            risultato = maybe_run_scheduled_fatture_in_cloud_sync()
            if risultato is None:
                self.stdout.write(self.style.NOTICE(
                    "Nessuna sincronizzazione Fatture in Cloud eseguita."
                ))
                return
            self.stdout.write(self.style.SUCCESS(
                f"Sincronizzazioni: {risultato['eseguite']}, errori: {risultato['in_errore']}, "
                f"documenti gestiti: {risultato['documenti_gestiti']}."
            ))
            return

        data_inizio = None
        if options.get("data_inizio"):
            data_inizio = parse_date(options["data_inizio"])
            if data_inizio is None:
                raise CommandError("Formato data non valido per --dal. Usa YYYY-MM-DD.")

        connessioni = FattureInCloudConnessione.objects.filter(attiva=True)
        if options.get("connessione"):
            connessioni = connessioni.filter(pk=options["connessione"])

        totale = 0
        errori = 0
        for connessione in connessioni:
            try:
                kwargs = {"data_inizio": data_inizio} if options.get("data_inizio") else {}
                stats = sincronizza_fatture_in_cloud(connessione, **kwargs)
                totale += stats["creati"] + stats["aggiornati"]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{connessione}: {stats['creati']} creati, {stats['aggiornati']} aggiornati"
                    )
                )
            except FattureInCloudError as exc:
                errori += 1
                self.stderr.write(self.style.ERROR(f"{connessione}: {exc}"))

        if errori:
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"Sincronizzazione completata. Documenti gestiti: {totale}"))
