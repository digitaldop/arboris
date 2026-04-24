"""
Import unificato di regioni, province, città, CAP (e codice catastale/Belfiore) da
un file Excel in stile ISTAT o dataset gi_comuni (una o più righe per comune con CAP).
Usato dal comando `import_dati_base` e dal pulsante in Impostazioni generali.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from anagrafica.models import CAP, Citta, Provincia, Regione

# Percorso predefinito (relativo a BASE_DIR) per il file unico comuni+CAP
GI_COMUNI_CAP_REL_PATH = "import/gi_comuni_cap.xlsx"


def default_gi_file_path() -> Path:
    return Path(settings.BASE_DIR) / GI_COMUNI_CAP_REL_PATH


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


def _colonne_anagrafica_comuni() -> dict[str, list[str]]:
    """Candidati per mapping colonne (ISTAT, export third-party, ecc.)."""
    return {
        "regione": [
            "Denominazione Regione",
            "Regione",
            "Nome Regione",
            "Nome regione",
        ],
        "provincia": [
            "Denominazione dell'Unità territoriale sovracomunale (valida a fini statistici)",
            "Denominazione Provincia",
            "Provincia",
            "Nome Provincia",
            "Nome provincia",
        ],
        "sigla": [
            "Sigla automobilistica",
            "Sigla",
            "Sigla provincia",
            "Sig.",
        ],
        "comune": [
            "Denominazione in italiano",
            "Denominazione Comune",
            "Comune",
            "Città",
            "Nome Comune",
            "Nome comune",
        ],
        "cap": [
            "Cap",
            "CAP",
            "Cap.",
        ],
        "codice_istat": [
            "Codice Comune formato numerico",
            "Codice comune formato numerico",
            "Codice ISTAT del Comune",
            "Codice ISTAT comune",
            "Codice ISTAT",
            "Cod. ISTAT",
            "Cod Istat",
            "Codice Comune",
            "ISTAT",
            "ProCom",
            "Codice istat",
        ],
        "codice_catastale": [
            "Codice Catastale del comune",
            "Codice catastale del comune",
            "Codice catastale",
            "Codice Catastale",
            "Codice Belfiore",
            "Belfiore",
            "Catastale",
        ],
    }


def build_column_map(df: pd.DataFrame) -> dict[str, str | None]:
    column_candidates = _colonne_anagrafica_comuni()
    colonne_norm = {col: normalizza_nome_colonna(col) for col in df.columns}
    return {key: trova_colonna(colonne_norm, names) for key, names in column_candidates.items()}


def mappa_e_normalizza_dataframe(
    df: pd.DataFrame,
    column_map: dict[str, str | None],
) -> pd.DataFrame:
    col_regione = column_map.get("regione")
    col_provincia = column_map.get("provincia")
    col_sigla = column_map.get("sigla")
    col_comune = column_map.get("comune")
    col_codice_istat = column_map.get("codice_istat")
    col_cap = column_map.get("cap")
    col_codice_catastale = column_map.get("codice_catastale")

    obbligatorie = {
        "regione": col_regione,
        "provincia": col_provincia,
        "sigla": col_sigla,
        "comune": col_comune,
        "codice_istat": col_codice_istat,
    }
    mancanti = [k for k, v in obbligatorie.items() if v is None]
    if mancanti:
        raise ValidationError(
            f"Colonne obbligatorie mancanti nel file: {', '.join(mancanti)}. "
            f"Colonne lette: {list(df.columns)}"
        )

    assert col_regione and col_provincia and col_sigla and col_comune and col_codice_istat

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

    out = df.rename(columns=rename_map).copy()
    finali = ["regione", "provincia", "sigla", "comune", "codice_istat"]
    if "codice_catastale" in out.columns:
        finali.append("codice_catastale")
    if "cap" in out.columns:
        finali.append("cap")
    out = out[finali].copy()

    for col in ["regione", "provincia", "sigla", "comune", "codice_istat"]:
        out[col] = out[col].fillna("").astype(str).str.strip()

    if "codice_catastale" in out.columns:
        out["codice_catastale"] = out["codice_catastale"].fillna("").astype(str).str.strip().str.upper()
    else:
        out["codice_catastale"] = ""

    if "cap" in out.columns:
        out["cap"] = out["cap"].fillna("").astype(str).str.strip()
    else:
        out["cap"] = ""

    out = out[
        (out["regione"] != "")
        & (out["provincia"] != "")
        & (out["sigla"] != "")
        & (out["comune"] != "")
        & (out["codice_istat"] != "")
    ].copy()

    out["codice_istat"] = out["codice_istat"].str.replace(".0", "", regex=False).str.zfill(6)
    out = out[out["sigla"].str.len() == 2].copy()
    return out


def prepare_istat_una_riga_per_comune(df: pd.DataFrame) -> pd.DataFrame:
    """Stesso criterio del vecchio `import_comuni_istat` (elenco ISTAT, un comune per riga)."""
    return df.drop_duplicates(subset=["regione", "provincia", "sigla", "comune"])


def prepare_gi_splitta_citta_e_cap(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Da dataset con possibili più righe per stesso comune (più CAP):
    - comuni: una riga per codice_istat;
    - cap: tutte le coppie (codice_istat, cap) distinte, cap non vuoto.
    """
    df = df.copy()
    df_citta = (
        df.sort_values(["regione", "provincia", "comune", "sigla"])
        .drop_duplicates(subset=["codice_istat"], keep="first")
    )
    if "cap" in df.columns and df["cap"].astype(str).str.strip().ne("").any():
        cap_df = df[df["cap"].astype(str).str.strip() != ""].copy()
        cap_df = cap_df.drop_duplicates(subset=["codice_istat", "cap"])
        cap_df = cap_df[["codice_istat", "cap"]]
    else:
        cap_df = pd.DataFrame(columns=["codice_istat", "cap"])
    return df_citta, cap_df


def importa_regioni_province_citta(df: pd.DataFrame) -> tuple[int, int, int]:
    """df: un solo record per coppia (comune, provincia) o per codice_istat (consigliato)."""
    regioni_cache: dict[str, Regione] = {}
    province_cache: dict[tuple[str, str, str], Provincia] = {}
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

    province_viste: dict[tuple[str, str, str], None] = {}
    for _, row in df.iterrows():
        chiave_provincia = (row["sigla"], row["provincia"], row["regione"])
        if chiave_provincia not in province_viste:
            province_viste[chiave_provincia] = None

    ordine = 1
    for sigla, nome_provincia, nome_regione in sorted(
        province_viste.keys(), key=lambda x: (x[2], x[1], x[0])
    ):
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
        _, _created = Citta.objects.get_or_create(
            nome=row["comune"],
            provincia=provincia,
            defaults={
                "codice_istat": row["codice_istat"],
                "codice_catastale": row["codice_catastale"],
                "ordine": ordine_citta,
                "attiva": True,
            },
        )
        if not _created:
            Citta.objects.filter(nome=row["comune"], provincia=provincia).update(
                codice_istat=row["codice_istat"],
                codice_catastale=row["codice_catastale"],
                ordine=ordine_citta,
                attiva=True,
            )
        citta_count += 1
        ordine_citta += 1

    return regioni_create_count, province_create_count, citta_count


def importa_cap_da_coppie(df_cap: pd.DataFrame) -> tuple[int, int]:
    creati = 0
    saltati = 0
    ordine_progressivo: dict[int, int] = {}

    for _, row in df_cap.iterrows():
        codice_istat = str(row["codice_istat"]).strip()
        codice_istat = codice_istat.replace(".0", "").zfill(6) if codice_istat else ""
        codice_cap = str(row["cap"]).strip()
        if not codice_istat or not codice_cap:
            continue
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
            },
        )
        if not created:
            CAP.objects.filter(codice=codice_cap, citta=citta).update(attivo=True)
        else:
            creati += 1
        ordine_progressivo[citta.id] += 1
    return creati, saltati


def clear_geografia_per_import(force: bool = False) -> None:
    """
    Svuota CAP e anagrafica geografica. Fallisce se esistono indirizzi (PROTECT su Citta)
    a meno che force non sia True (sconsigliato in produzione con dati).
    """
    from anagrafica.models import Indirizzo

    if not force and Indirizzo.objects.exists():
        raise ValidationError(
            "Impossibile svuotare città e province: esistono indirizzi collegati. "
            "Rimuovi o aggiorna gli indirizzi prima, oppure importa in modalità aggiornamento senza cancelazione."
        )
    CAP.objects.all().delete()
    Citta.objects.all().delete()
    Provincia.objects.all().delete()
    Regione.objects.all().delete()


def load_excel(
    file_path: Path,
    sheet_name: int | str | None = 0,
    header: int = 0,
) -> pd.DataFrame:
    kwargs: dict[str, Any] = {"header": header}
    if sheet_name is not None:
        kwargs["sheet_name"] = sheet_name
    return pd.read_excel(file_path, **kwargs)


def _try_read_and_map_excel(
    path: Path,
    *,
    sheet_name: int | str | None,
    header_row: int,
) -> pd.DataFrame:
    raw = load_excel(path, sheet_name=sheet_name, header=header_row)
    return mappa_e_normalizza_dataframe(raw, build_column_map(raw))


# Molti file (es. gi_comuni_cap) hanno riga 0 = titolo marketing, riga 1 = intestazioni reali.
DEFAULT_HEADER_ROW_CANDIDATES = (1, 0, 2)


def run_import_dati_base(
    file_path: Path | None = None,
    *,
    clear_first: bool = False,
    sheet_name: int | str | None = 0,
    header: int | None = None,
) -> dict[str, Any]:
    """
    Esegue import comuni+CAP da file Excel. Path predefinito: import/gi_comuni_cap.xlsx sotto BASE_DIR.

    ``header``: riga 0-based usata da pandas come intestazioni. Se ``None``, prova in ordine le righe
    1, 0, 2 (tipico: prima riga titolo, seconda nomi colonna).
    """
    path = file_path or default_gi_file_path()
    if not path.is_file():
        raise ValidationError(f"File non trovato: {path}")

    if header is not None:
        try:
            df = _try_read_and_map_excel(path, sheet_name=sheet_name, header_row=header)
        except ValidationError as e:
            raise ValidationError(
                f"Riga intestazione header={header}: {e}"
            ) from e
    else:
        errors: list[tuple[int, str]] = []
        df = None
        for hr in DEFAULT_HEADER_ROW_CANDIDATES:
            try:
                df = _try_read_and_map_excel(path, sheet_name=sheet_name, header_row=hr)
                break
            except ValidationError as e:
                errors.append((hr, str(e)))
        if df is None:
            raise ValidationError(
                "Impossibile riconoscere le colonne nel file Excel. "
                f"Prove con riga intestazione (0=prima riga) {list(DEFAULT_HEADER_ROW_CANDIDATES)}. "
                f"Dettagli: {' | '.join(f'header={h}: {msg}' for h, msg in errors)}"
            )

    df_citta, df_cap = prepare_gi_splitta_citta_e_cap(df)

    stats: dict[str, Any] = {
        "file": str(path),
        "regioni_creati": 0,
        "province_creati": 0,
        "citta_righe": 0,
        "cap_creati": 0,
        "cap_saltati": 0,
    }

    with transaction.atomic():
        if clear_first:
            clear_geografia_per_import(force=False)
        n_reg, n_prov, n_città = importa_regioni_province_citta(df_citta)
        cap_ok, cap_skip = importa_cap_da_coppie(df_cap)
        stats["regioni_creati"] = n_reg
        stats["province_creati"] = n_prov
        stats["citta_righe"] = n_città
        stats["cap_creati"] = cap_ok
        stats["cap_saltati"] = cap_skip

    return stats
