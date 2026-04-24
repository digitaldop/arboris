from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from anagrafica.models import Citta


def normalize_column_name(value: str) -> str:
    value = str(value).strip().lower()
    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)
    return value


def find_column(normalized_columns: dict[str, str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        candidate_normalized = normalize_column_name(candidate)
        for original, normalized in normalized_columns.items():
            if normalized == candidate_normalized:
                return original
    return None


class Command(BaseCommand):
    help = "Importa i codici catastali dei comuni e li collega alle città esistenti."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="Percorso del file Excel o CSV con i codici catastali.",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            help="Nome del foglio Excel da leggere, se necessario.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        sheet_name = options.get("sheet")

        if not file_path.exists():
            raise CommandError(f"File non trovato: {file_path}")

        dataframe = self.load_dataframe(file_path, sheet_name=sheet_name)
        dataframe = self.prepare_dataframe(dataframe)

        with transaction.atomic():
            updated, skipped = self.import_codes(dataframe)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import codici catastali completato. Aggiornate: {updated}. Saltate: {skipped}."
            )
        )

    def load_dataframe(self, file_path: Path, sheet_name: str | None = None) -> pd.DataFrame:
        suffix = file_path.suffix.lower()

        if suffix in {".xlsx", ".xls"}:
            if sheet_name:
                return pd.read_excel(file_path, sheet_name=sheet_name, header=1)
            return pd.read_excel(file_path, sheet_name=0, header=1)

        if suffix == ".csv":
            return pd.read_csv(file_path)

        raise CommandError("Formato file non supportato. Usa CSV o Excel.")

    def prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        normalized_columns = {column: normalize_column_name(column) for column in df.columns}

        col_comune = find_column(normalized_columns, [
            "Comune",
            "Denominazione Comune",
            "Denominazione in italiano",
            "denominazione_ita",
        ])
        col_sigla = find_column(normalized_columns, [
            "Sigla automobilistica",
            "Sigla",
            "Provincia",
            "Sigla provincia",
            "sigla_provincia",
        ])
        col_codice_catastale = find_column(normalized_columns, [
            "Codice Catastale del comune",
            "Codice catastale del comune",
            "Codice catastale",
            "Codice Belfiore",
            "Belfiore",
            "codice_belfiore",
        ])

        required = {
            "comune": col_comune,
            "sigla": col_sigla,
            "codice_catastale": col_codice_catastale,
        }
        missing = [key for key, value in required.items() if value is None]
        if missing:
            raise CommandError(
                f"Non riesco a trovare le colonne obbligatorie: {', '.join(missing)}. Colonne trovate: {list(df.columns)}"
            )

        dataframe = df.rename(
            columns={
                col_comune: "comune",
                col_sigla: "sigla",
                col_codice_catastale: "codice_catastale",
            }
        )[["comune", "sigla", "codice_catastale"]].copy()

        for column in ["comune", "sigla", "codice_catastale"]:
            dataframe[column] = dataframe[column].fillna("").astype(str).str.strip()

        dataframe["sigla"] = dataframe["sigla"].str.upper()
        dataframe["codice_catastale"] = dataframe["codice_catastale"].str.upper()

        dataframe = dataframe[
            (dataframe["comune"] != "")
            & (dataframe["sigla"] != "")
            & (dataframe["codice_catastale"] != "")
        ].copy()

        dataframe = dataframe.drop_duplicates(subset=["comune", "sigla"])
        return dataframe

    def import_codes(self, df: pd.DataFrame) -> tuple[int, int]:
        updated = 0
        skipped = 0

        for _, row in df.iterrows():
            city = (
                Citta.objects
                .select_related("provincia")
                .filter(nome__iexact=row["comune"], provincia__sigla__iexact=row["sigla"])
                .first()
            )

            if not city:
                skipped += 1
                continue

            if city.codice_catastale != row["codice_catastale"]:
                city.codice_catastale = row["codice_catastale"]
                city.save(update_fields=["codice_catastale"])
                updated += 1

        return updated, skipped
