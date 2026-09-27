"""Read-only inventory usable both before and after the address migrations."""
import json
from collections import defaultdict

from django.core.management.base import BaseCommand

from anagrafica.address_normalization import address_identity
from anagrafica.models import Indirizzo


class Command(BaseCommand):
    help = "Verifica indirizzi incompleti e possibili duplicati senza modificare alcun dato."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        groups, incomplete = defaultdict(list), []
        rows = Indirizzo.objects.using(options["database"]).values("id", "via", "numero_civico", "citta_id", "cap", "provincia_id", "regione_id")
        count = 0
        for row in rows.iterator():
            count += 1
            key = address_identity(row["via"], row["numero_civico"], row["citta_id"], row["cap"], row["provincia_id"], row["regione_id"])[2]
            if key:
                groups[key].append(row["id"])
            else:
                incomplete.append(row["id"])
        duplicates = [ids for ids in groups.values() if len(ids) > 1]
        self.stdout.write(json.dumps({"totale": count, "incompleti_id": incomplete, "duplicati_potenziali_id": duplicates}, indent=2))
