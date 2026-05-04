import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from gestione_finanziaria.fatture_in_cloud import FattureInCloudClient, FattureInCloudError
from gestione_finanziaria.fatture_in_cloud_debug import payload_debug_report_json
from gestione_finanziaria.models import FattureInCloudConnessione


class Command(BaseCommand):
    help = "Stampa la struttura mascherata di un payload Fatture in Cloud per diagnosi."

    def add_arguments(self, parser):
        parser.add_argument("--connessione", type=int, help="ID della connessione Fatture in Cloud.")
        parser.add_argument("--document-id", help="ID del documento ricevuto da ispezionare.")
        parser.add_argument("--pending", action="store_true", help="Legge il documento dalla sezione Da registrare.")
        parser.add_argument("--file", help="Legge un payload JSON locale invece di chiamare Fatture in Cloud.")
        parser.add_argument("--depth", type=int, default=5, help="Profondita' massima della struttura stampata.")
        parser.add_argument("--max-list-items", type=int, default=2, help="Numero massimo di elementi lista da mostrare.")

    def handle(self, *args, **options):
        payload_file = options.get("file")
        document_id = options.get("document_id")
        source = "file"
        if payload_file:
            try:
                payload = json.loads(Path(payload_file).read_text(encoding="utf-8"))
            except OSError as exc:
                raise CommandError(f"Impossibile leggere il file JSON: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise CommandError(f"File JSON non valido: {exc}") from exc
            document_id = document_id or payload.get("id") or "-"
        else:
            if not options.get("connessione") or not document_id:
                raise CommandError("Usa --connessione e --document-id, oppure passa un payload locale con --file.")
            try:
                connessione = FattureInCloudConnessione.objects.get(pk=options["connessione"])
            except FattureInCloudConnessione.DoesNotExist as exc:
                raise CommandError("Connessione Fatture in Cloud non trovata.") from exc
            client = FattureInCloudClient(connessione)
            source = "pending" if options["pending"] else "registered"
            try:
                if options["pending"]:
                    payload = client.get_pending_received_document(document_id)
                else:
                    payload = client.get_received_document(document_id)
            except FattureInCloudError as exc:
                raise CommandError(str(exc)) from exc

        if not isinstance(payload, dict):
            raise CommandError("Il payload recuperato non e' un oggetto JSON.")

        self.stdout.write(
            payload_debug_report_json(
                payload,
                source=source,
                document_id=document_id,
                max_depth=max(options["depth"], 1),
                max_list_items=max(options["max_list_items"], 0),
            )
        )
