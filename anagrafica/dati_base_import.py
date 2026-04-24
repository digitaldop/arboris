"""
Import unificato di regioni, province, città, CAP (e codice catastale/Belfiore) da
un file Excel in stile ISTAT o dataset gi_comuni (una o più righe per comune con CAP).
Usato dal comando `import_dati_base` e dal pulsante in Impostazioni generali.
"""
from __future__ import annotations

import re
from pathlib import Path
from time import perf_counter
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
    # Header Excel/CSV con underscore (es. denominazione_regione) allineati a "Denominazione Regione"
    nome = nome.replace("_", " ")
    nome = re.sub(r"\s+", " ", nome)
    return nome


def trova_colonna(colonne_norm: dict[str, str], candidati: list[str]) -> str | None:
    for candidato in candidati:
        candidato_norm = normalizza_nome_colonna(candidato)
        for colonna_originale, colonna_norm in colonne_norm.items():
            if candidato_norm == colonna_norm:
                return colonna_originale
    return None


def normalizza_codice_cap(valore: Any) -> str:
    cap = str(valore or "").strip()
    if not cap:
        return ""
    if cap.endswith(".0"):
        cap = cap[:-2]
    cap = cap.replace(" ", "")
    if cap.isdigit():
        return cap.zfill(5)
    return cap.upper()


def _colonne_anagrafica_comuni() -> dict[str, list[str]]:
    """Candidati per mapping colonne (ISTAT, export third-party, ecc.)."""
    return {
        "regione": [
            "Denominazione Regione",
            "denominazione_regione",
            "Regione",
            "Nome Regione",
            "Nome regione",
        ],
        "provincia": [
            "Denominazione dell'Unità territoriale sovracomunale (valida a fini statistici)",
            "Denominazione Provincia",
            "denominazione_provincia",
            "Provincia",
            "Nome Provincia",
            "Nome provincia",
        ],
        "sigla": [
            "Sigla automobilistica",
            "sigla_provincia",
            "Sigla",
            "Sigla provincia",
            "Sig.",
        ],
        "comune": [
            "Denominazione in italiano",
            "denominazione_ita",
            "Denominazione ITA",
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
            "codice_istat",
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
            "codice_belfiore",
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
        out["cap"] = out["cap"].map(normalizza_codice_cap)
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
    regioni_uniche = sorted(df["regione"].dropna().unique())
    ordine_regioni = {nome: i for i, nome in enumerate(regioni_uniche, start=1)}
    regioni_esistenti = {
        regione.nome: regione for regione in Regione.objects.filter(nome__in=regioni_uniche)
    }
    regioni_da_creare: list[Regione] = []
    regioni_da_aggiornare: list[Regione] = []

    for nome_regione, ordine_regione in ordine_regioni.items():
        regione = regioni_esistenti.get(nome_regione)
        if regione is None:
            regioni_da_creare.append(Regione(nome=nome_regione, ordine=ordine_regione, attiva=True))
            continue
        changed = False
        if regione.ordine != ordine_regione:
            regione.ordine = ordine_regione
            changed = True
        if not regione.attiva:
            regione.attiva = True
            changed = True
        if changed:
            regioni_da_aggiornare.append(regione)

    if regioni_da_creare:
        Regione.objects.bulk_create(regioni_da_creare, batch_size=500)
    if regioni_da_aggiornare:
        Regione.objects.bulk_update(regioni_da_aggiornare, ["ordine", "attiva"], batch_size=500)

    regioni_cache = {
        regione.nome: regione for regione in Regione.objects.filter(nome__in=regioni_uniche)
    }

    province_keys = sorted(
        {
            (row.sigla, row.provincia, row.regione)
            for row in df[["sigla", "provincia", "regione"]].itertuples(index=False)
        },
        key=lambda item: (item[2], item[1], item[0]),
    )
    sigle_province = [sigla for sigla, _, _ in province_keys]
    province_esistenti = {
        provincia.sigla: provincia for provincia in Provincia.objects.filter(sigla__in=sigle_province)
    }
    province_da_creare: list[Provincia] = []
    province_da_aggiornare: list[Provincia] = []

    for ordine, (sigla, nome_provincia, nome_regione) in enumerate(province_keys, start=1):
        provincia = province_esistenti.get(sigla)
        regione = regioni_cache[nome_regione]
        if provincia is None:
            province_da_creare.append(
                Provincia(
                    sigla=sigla,
                    nome=nome_provincia,
                    regione=regione,
                    ordine=ordine,
                    attiva=True,
                )
            )
            continue
        changed = False
        if provincia.nome != nome_provincia:
            provincia.nome = nome_provincia
            changed = True
        if provincia.regione_id != regione.id:
            provincia.regione = regione
            changed = True
        if provincia.ordine != ordine:
            provincia.ordine = ordine
            changed = True
        if not provincia.attiva:
            provincia.attiva = True
            changed = True
        if changed:
            province_da_aggiornare.append(provincia)

    if province_da_creare:
        Provincia.objects.bulk_create(province_da_creare, batch_size=500)
    if province_da_aggiornare:
        Provincia.objects.bulk_update(
            province_da_aggiornare,
            ["nome", "regione", "ordine", "attiva"],
            batch_size=500,
        )

    province_cache = {
        provincia.sigla: provincia for provincia in Provincia.objects.filter(sigla__in=sigle_province)
    }

    df_ordinato = df.sort_values(["regione", "provincia", "comune"]).reset_index(drop=True)
    province_ids = [provincia.id for provincia in province_cache.values()]
    citta_esistenti = {
        (citta.nome, citta.provincia_id): citta
        for citta in Citta.objects.filter(provincia_id__in=province_ids)
    }
    citta_da_creare: list[Citta] = []
    citta_da_aggiornare: list[Citta] = []

    for ordine_citta, row in enumerate(
        df_ordinato[["comune", "sigla", "codice_istat", "codice_catastale"]].itertuples(index=False),
        start=1,
    ):
        provincia = province_cache[row.sigla]
        key = (row.comune, provincia.id)
        citta = citta_esistenti.get(key)
        if citta is None:
            citta_da_creare.append(
                Citta(
                    nome=row.comune,
                    provincia=provincia,
                    codice_istat=row.codice_istat,
                    codice_catastale=row.codice_catastale,
                    ordine=ordine_citta,
                    attiva=True,
                )
            )
            continue
        changed = False
        if citta.codice_istat != row.codice_istat:
            citta.codice_istat = row.codice_istat
            changed = True
        if citta.codice_catastale != row.codice_catastale:
            citta.codice_catastale = row.codice_catastale
            changed = True
        if citta.ordine != ordine_citta:
            citta.ordine = ordine_citta
            changed = True
        if not citta.attiva:
            citta.attiva = True
            changed = True
        if changed:
            citta_da_aggiornare.append(citta)

    if citta_da_creare:
        Citta.objects.bulk_create(citta_da_creare, batch_size=1000)
    if citta_da_aggiornare:
        Citta.objects.bulk_update(
            citta_da_aggiornare,
            ["codice_istat", "codice_catastale", "ordine", "attiva"],
            batch_size=1000,
        )

    return len(regioni_da_creare), len(province_da_creare), len(df_ordinato.index)


def importa_cap_da_coppie(df_cap: pd.DataFrame) -> tuple[int, int]:
    saltati = 0
    if df_cap.empty:
        return 0, 0

    df_cap = df_cap.copy()
    df_cap["codice_istat"] = (
        df_cap["codice_istat"].astype(str).str.strip().str.replace(".0", "", regex=False).str.zfill(6)
    )
    df_cap["cap"] = df_cap["cap"].map(normalizza_codice_cap)
    df_cap = df_cap[(df_cap["codice_istat"] != "") & (df_cap["cap"] != "")]
    if df_cap.empty:
        return 0, 0

    citta_by_istat = {
        citta.codice_istat: citta
        for citta in Citta.objects.filter(codice_istat__in=df_cap["codice_istat"].unique().tolist())
    }

    ordine_progressivo: dict[int, int] = {}
    pairs: list[tuple[str, int, int]] = []
    for row in df_cap.sort_values(["codice_istat", "cap"]).itertuples(index=False):
        citta = citta_by_istat.get(row.codice_istat)
        if citta is None:
            saltati += 1
            continue
        ordine = ordine_progressivo.get(citta.id, 1)
        pairs.append((row.cap, citta.id, ordine))
        ordine_progressivo[citta.id] = ordine + 1

    if not pairs:
        return 0, saltati

    citta_ids = sorted({citta_id for _, citta_id, _ in pairs})
    cap_esistenti = {
        (cap.codice, cap.citta_id): cap for cap in CAP.objects.filter(citta_id__in=citta_ids)
    }
    cap_da_creare: list[CAP] = []
    cap_da_aggiornare: list[CAP] = []

    for codice_cap, citta_id, ordine in pairs:
        key = (codice_cap, citta_id)
        cap = cap_esistenti.get(key)
        if cap is None:
            cap_da_creare.append(
                CAP(
                    codice=codice_cap,
                    citta_id=citta_id,
                    ordine=ordine,
                    attivo=True,
                )
            )
            continue
        changed = False
        if cap.ordine != ordine:
            cap.ordine = ordine
            changed = True
        if not cap.attivo:
            cap.attivo = True
            changed = True
        if changed:
            cap_da_aggiornare.append(cap)

    if cap_da_creare:
        CAP.objects.bulk_create(cap_da_creare, batch_size=2000)
    if cap_da_aggiornare:
        CAP.objects.bulk_update(cap_da_aggiornare, ["ordine", "attivo"], batch_size=2000)

    return len(cap_da_creare), saltati


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
    started_at = perf_counter()
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

    stats["durata_secondi"] = round(perf_counter() - started_at, 2)
    return stats
