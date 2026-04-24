# Importa da import/gi_comuni_cap.xlsx (o file indicato) regioni, province, città, CAP.
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from anagrafica.dati_base_import import default_gi_file_path, run_import_dati_base


class Command(BaseCommand):
    help = "Importa dati anagrafici (regioni, province, città, CAP) da import/gi_comuni_cap.xlsx o da --file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            help=f"Excel da leggere. Predefinito: {default_gi_file_path()} (sotto BASE_DIR).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Svuota CAP e tabelle geografiche prima dell'import (fallisce se esistono indirizzi).",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default="0",
            help="Indice o nome del foglio Excel (predefinito: 0).",
        )
        parser.add_argument(
            "--header",
            type=int,
            default=None,
            help="Riga intestazione 0-based (pandas). Se omesso, prova automaticamente 1, 0, 2. Esempio forzare prima riga: --header 0",
        )

    def handle(self, *args, **options):
        file_arg = options.get("file")
        path = Path(file_arg) if file_arg else default_gi_file_path()
        if not path.is_file():
            raise CommandError(
                f"File non trovato: {path}\n"
                f"Posiziona il file in {Path(settings.BASE_DIR) / 'import' / 'gi_comuni_cap.xlsx'} "
                "oppure passa --file."
            )
        clear_first = bool(options.get("clear"))
        sheet = options.get("sheet") or "0"
        try:
            sheet_name: int | str = int(sheet)
        except ValueError:
            sheet_name = str(sheet)
        header = options.get("header")

        try:
            stats = run_import_dati_base(
                file_path=path,
                clear_first=clear_first,
                sheet_name=sheet_name,
                header=header,
            )
        except ValidationError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(
            self.style.SUCCESS(
                f"Completato da {stats['file']}\n"
                f"  Regioni (nuove create in questa run): {stats['regioni_creati']}\n"
                f"  Province (nuove create in questa run): {stats['province_creati']}\n"
                f"  Città elaborate (righe): {stats['citta_righe']}\n"
                f"  CAP creati: {stats['cap_creati']}; CAP saltati (città assente): {stats['cap_saltati']}"
            )
        )
