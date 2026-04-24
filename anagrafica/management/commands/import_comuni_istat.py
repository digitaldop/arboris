#Questo script importa i dati di regioni, province e città italiane da un file Excel ufficiale dell'ISTAT, che contiene l'elenco completo dei comuni italiani con relative informazioni. Il comando può essere eseguito da terminale con:
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from anagrafica.models import Regione, Provincia, Citta


ISTAT_URL = "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.xlsx"


def normalizza_nome_colonna(nome: str) -> str:
    nome = str(nome).strip().lower()
    nome = nome.replace("\n", " ")
    nome = re.sub(r"\s+", " ", nome)
    return nome


def trova_colonna(colonne_norm: dict[str, str], candidati: list[str]) -> str | None:
    for candidato in candidati:
        candidato_norm = normalizza_nome_colonna(candidato)
        for colonna_originale, colonna_norm in colonne_norm.items():
            if candidato_norm == colonna_norm:
                return colonna_originale
    return None


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
            help="Cancella prima tutti i dati di città, province e regioni.",
        )

    def handle(self, *args, **options):
        file_path = options.get("file")
        clear = options.get("clear", False)

        try:
            df = self.carica_dataframe(file_path)
        except Exception as e:
            raise CommandError(f"Errore nel caricamento del file ISTAT: {e}")

        df = self.prepara_dataframe(df)

        with transaction.atomic():
            if clear:
                self.stdout.write(self.style.WARNING("Cancellazione dati esistenti..."))
                Citta.objects.all().delete()
                Provincia.objects.all().delete()
                Regione.objects.all().delete()

            tot_regioni, tot_province, tot_citta = self.importa_dati(df)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import completato: {tot_regioni} regioni, {tot_province} province, {tot_citta} città."
            )
        )

    def carica_dataframe(self, file_path: str | None) -> pd.DataFrame:
        if file_path:
            path = Path(file_path)
            if not path.exists():
                raise CommandError(f"File non trovato: {path}")
            return pd.read_excel(path)

        self.stdout.write("Carico il file dal permalink ISTAT ufficiale...")
        return pd.read_excel(ISTAT_URL)

    def prepara_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        colonne_norm = {col: normalizza_nome_colonna(col) for col in df.columns}

        col_regione = trova_colonna(colonne_norm, [
            "Denominazione Regione",
            "Regione",
        ])
        col_provincia = trova_colonna(colonne_norm, [
            "Denominazione dell'Unità territoriale sovracomunale (valida a fini statistici)",
            "Denominazione Provincia",
            "Provincia",
        ])
        col_sigla = trova_colonna(colonne_norm, [
            "Sigla automobilistica",
            "Sigla",
        ])
        col_comune = trova_colonna(colonne_norm, [
            "Denominazione in italiano",
            "Denominazione Comune",
            "Comune",
        ])
        col_cap = trova_colonna(colonne_norm, [
            "Cap",
            "CAP",
        ])
        col_codice_istat = trova_colonna(colonne_norm, [
            "Codice Comune formato numerico",
            "Codice comune formato numerico",
            "Codice ISTAT del Comune",
            "Codice Comune",
        ])
        col_codice_catastale = trova_colonna(colonne_norm, [
            "Codice Catastale del comune",
            "Codice catastale del comune",
            "Codice catastale",
            "Codice Belfiore",
            "Belfiore",
        ])

        obbligatorie = {
            "regione": col_regione,
            "provincia": col_provincia,
            "sigla": col_sigla,
            "comune": col_comune,
            "codice_istat": col_codice_istat,
        }

        mancanti = [k for k, v in obbligatorie.items() if v is None]
        if mancanti:
            raise CommandError(
                f"Non riesco a trovare nel file le colonne obbligatorie: {', '.join(mancanti)}. "
                f"Colonne trovate: {list(df.columns)}"
            )

        df = df.copy()

        rename_map = {
            col_regione: "regione",
            col_provincia: "provincia",
            col_sigla: "sigla",
            col_comune: "comune",
            col_codice_istat: "codice_istat",
        }
        if col_codice_catastale:
            rename_map[col_codice_catastale] = "codice_catastale"
        if col_cap:
            rename_map[col_cap] = "cap"

        df = df.rename(columns=rename_map)

        colonne_finali = ["regione", "provincia", "sigla", "comune", "codice_istat"]
        if "codice_catastale" in df.columns:
            colonne_finali.append("codice_catastale")
        if "cap" in df.columns:
            colonne_finali.append("cap")

        df = df[colonne_finali].copy()

        for col in ["regione", "provincia", "sigla", "comune", "codice_istat"]:
             df[col] = df[col].fillna("").astype(str).str.strip()

        if "codice_catastale" in df.columns:
            df["codice_catastale"] = df["codice_catastale"].fillna("").astype(str).str.strip().str.upper()
        else:
            df["codice_catastale"] = ""

        if "cap" in df.columns:
            df["cap"] = df["cap"].fillna("").astype(str).str.strip()
        else:
            df["cap"] = ""

        df = df[
            (df["regione"] != "")
            & (df["provincia"] != "")
            & (df["sigla"] != "")
            & (df["comune"] != "")
            & (df["codice_istat"] != "")
        ].copy()

        #Formatta il codice ISTAT per essere sempre di 6 caratteri, rimuovendo eventuali decimali e aggiungendo zeri iniziali se necessario
        df["codice_istat"] = df["codice_istat"].str.replace(".0", "", regex=False).str.zfill(6)

        # sicurezza aggiuntiva: la sigla deve essere di 2 caratteri
        df = df[df["sigla"].str.len() == 2].copy()

        df = df.drop_duplicates(subset=["regione", "provincia", "sigla", "comune"])

        return df

    def importa_dati(self, df: pd.DataFrame) -> tuple[int, int, int]:
        regioni_cache = {}
        province_cache = {}
        citta_count = 0

        regioni_create_count = 0
        province_create_count = 0

        regioni_uniche = sorted(df["regione"].dropna().unique())
        ordine_regioni = {nome: i for i, nome in enumerate(regioni_uniche, start=1)}

        for nome_regione, ordine_regione in ordine_regioni.items():
            regione, created = Regione.objects.get_or_create(
                nome=nome_regione,
                defaults={
                    "ordine": ordine_regione,
                    "attiva": True,
                },
            )
            if not created:
                regione.ordine = ordine_regione
                regione.attiva = True
                regione.save(update_fields=["ordine", "attiva"])
            else:
                regioni_create_count += 1

            regioni_cache[nome_regione] = regione

        province_viste = {}
        for _, row in df.iterrows():
            chiave_provincia = (row["sigla"], row["provincia"], row["regione"])
            if chiave_provincia not in province_viste:
                province_viste[chiave_provincia] = None

        ordine = 1
        for sigla, nome_provincia, nome_regione in sorted(province_viste.keys(), key=lambda x: (x[2], x[1], x[0])):
            provincia, created = Provincia.objects.get_or_create(
                sigla=sigla,
                defaults={
                    "nome": nome_provincia,
                    "regione": regioni_cache[nome_regione],
                    "ordine": ordine,
                    "attiva": True,
                },
            )
            if not created:
                provincia.nome = nome_provincia
                provincia.regione = regioni_cache[nome_regione]
                provincia.ordine = ordine
                provincia.attiva = True
                provincia.save(update_fields=["nome", "regione", "ordine", "attiva"])
            else:
                province_create_count += 1

            province_cache[(sigla, nome_provincia, nome_regione)] = provincia
            ordine += 1

        ordine_citta = 1
        for _, row in df.sort_values(["regione", "provincia", "comune"]).iterrows():
            provincia = province_cache[(row["sigla"], row["provincia"], row["regione"])]

            _, created = Citta.objects.get_or_create(
                nome=row["comune"],
                provincia=provincia,
                defaults={
                    "codice_istat": row["codice_istat"],
                    "codice_catastale": row["codice_catastale"],
                    "ordine": ordine_citta,
                    "attiva": True,
                },
            )
            if not created:
                Citta.objects.filter(nome=row["comune"], provincia=provincia).update(
                    codice_istat=row["codice_istat"],
                    codice_catastale=row["codice_catastale"],
                    ordine=ordine_citta,
                    attiva=True,
                )

            citta_count += 1
            ordine_citta += 1

        return regioni_create_count, province_create_count, citta_count
