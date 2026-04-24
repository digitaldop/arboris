from __future__ import annotations

from pathlib import Path
from sys import path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from anagrafica.models import Citta, CAP


class Command(BaseCommand):
    help = "Importa i CAP da un dataset separato e li collega alle città tramite codice ISTAT"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="Percorso del file CSV/XLSX con i CAP",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Cancella prima tutti i CAP esistenti",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            help="Nome foglio Excel da leggere, se necessario",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        clear = options.get("clear", False)
        sheet_name = options.get("sheet")

        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"File non trovato: {path}")

        df = self.load_dataframe(path, sheet_name=sheet_name)
        df = self.prepare_dataframe(df)

        with transaction.atomic():
            if clear:
                self.stdout.write(self.style.WARNING("Cancellazione CAP esistenti..."))
                CAP.objects.all().delete()

            creati, saltati = self.import_caps(df)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import CAP completato. Creati: {creati}. Saltati: {saltati}."
            )
        )

    def load_dataframe(self, path: Path, sheet_name: str | None = None) -> pd.DataFrame:
        return pd.read_excel(path, header=1)

    def prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # questo file ha una riga di intestazione sopra → header=1 già gestito
        df.columns = [str(c).strip().lower() for c in df.columns]

        if "codice_istat" not in df.columns or "cap" not in df.columns:
            raise CommandError(f"Colonne mancanti. Trovate: {list(df.columns)}")

        df["codice_istat"] = df["codice_istat"].fillna("").astype(str).str.strip()
        df["cap"] = df["cap"].fillna("").astype(str).str.strip()

        # normalizzazione ISTAT (fondamentale)
        df["codice_istat"] = df["codice_istat"].str.replace(".0", "", regex=False).str.zfill(6)

        df = df[
            (df["codice_istat"] != "") &
            (df["cap"] != "")
        ].copy()

        df = df.drop_duplicates(subset=["codice_istat", "cap"])

        return df

    def import_caps(self, df: pd.DataFrame) -> tuple[int, int]:
        creati = 0
        saltati = 0
        ordine_progressivo = {}

        for _, row in df.iterrows():
            codice_istat = row["codice_istat"]
            codice_cap = row["cap"]

            try:
                citta = Citta.objects.get(codice_istat=codice_istat)
            except Citta.DoesNotExist:
                saltati += 1
                continue

            if citta.id not in ordine_progressivo:
                ordine_progressivo[citta.id] = 1

            _, created = CAP.objects.get_or_create(
                codice=codice_cap,
                citta=citta,
                defaults={
                    "ordine": ordine_progressivo[citta.id],
                    "attivo": True,
                }
            )

            if not created:
                CAP.objects.filter(codice=codice_cap, citta=citta).update(
                    attivo=True
                )
            else:
                creati += 1

            ordine_progressivo[citta.id] += 1

        return creati, saltati