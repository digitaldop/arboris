# Script: importa regioni, province e città da file Excel ISTAT (o compatibile).
# Uso: python manage.py import_comuni_istat [--file percorso.xlsx] [--clear]
from __future__ import annotations

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from anagrafica.dati_base_import import (
    build_column_map,
    importa_regioni_province_citta,
    mappa_e_normalizza_dataframe,
    prepare_istat_una_riga_per_comune,
    clear_geografia_per_import,
)

ISTAT_URL = "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.xlsx"


class Command(BaseCommand):
    help = "Importa regioni, province e città da file ISTAT"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            help="Percorso locale del file Excel ISTAT. Se omesso, prova a leggerlo dal permalink ufficiale.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Cancella prima tutti i dati di città, province e regioni (solo se nessun indirizzo in DB).",
        )

    def handle(self, *args, **options):
        file_path = options.get("file")
        clear = options.get("clear", False)

        try:
            df = self.carica_dataframe(file_path)
        except Exception as e:
            raise CommandError(f"Errore nel caricamento del file ISTAT: {e}")

        col_map = build_column_map(df)
        from django.core.exceptions import ValidationError

        try:
            df = mappa_e_normalizza_dataframe(df, col_map)
        except ValidationError as e:
            raise CommandError(str(e)) from e
        df = prepare_istat_una_riga_per_comune(df)

        with transaction.atomic():
            if clear:
                self.stdout.write(self.style.WARNING("Cancellazione dati esistenti..."))
                try:
                    clear_geografia_per_import(force=False)
                except ValidationError as e:
                    raise CommandError(str(e)) from e

            tot_regioni, tot_province, tot_citta = importa_regioni_province_citta(df)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import completato: {tot_regioni} regioni, {tot_province} province, {tot_citta} città."
            )
        )

    def carica_dataframe(self, file_path: str | None) -> pd.DataFrame:
        if file_path:
            from pathlib import Path

            path = Path(file_path)
            if not path.exists():
                raise CommandError(f"File non trovato: {path}")
            return pd.read_excel(path)

        self.stdout.write("Carico il file dal permalink ISTAT ufficiale...")
        return pd.read_excel(ISTAT_URL)
