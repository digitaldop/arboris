"""
Parser CSV configurabile per estratti conto.

Il formato CSV non e' standardizzato fra banche: per questo l'importer
espone una configurazione (:class:`CsvImporterConfig`) dove l'utente indica:

- delimitatore (autodetect o esplicito);
- encoding sorgente;
- se la prima riga contiene intestazioni;
- quale colonna (per indice 0-based o per nome) contiene ciascun campo;
- formato delle date;
- eventuale separatore decimale diverso da ``.`` (italiano: ``,``).

Supporta due modalita' per l'importo:
- colonna singola firmata (``colonna_importo``);
- due colonne separate (``colonna_entrate`` / ``colonna_uscite``) tipiche
  degli estratti conto con "Dare" e "Avere".
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterator, List, Optional, Union

from .base import BaseParser, ParsedMovimento


ColonnaRef = Union[int, str]


@dataclass
class CsvImporterConfig:
    """Configurazione del parser CSV. I campi ``colonna_*`` possono essere
    un indice 0-based (int) oppure il nome dell'intestazione (str)."""

    delimiter: str = ""  # "" => autodetect
    encoding: str = "utf-8-sig"
    ha_intestazione: bool = True
    righe_da_saltare: int = 0

    colonna_data_contabile: Optional[ColonnaRef] = None
    colonna_data_valuta: Optional[ColonnaRef] = None
    colonna_importo: Optional[ColonnaRef] = None
    colonna_entrate: Optional[ColonnaRef] = None
    colonna_uscite: Optional[ColonnaRef] = None
    colonna_valuta: Optional[ColonnaRef] = None
    colonna_descrizione: Optional[ColonnaRef] = None
    colonne_descrizione_extra: List[ColonnaRef] = field(default_factory=list)
    colonna_controparte: Optional[ColonnaRef] = None
    colonna_iban_controparte: Optional[ColonnaRef] = None
    colonna_transaction_id: Optional[ColonnaRef] = None

    formato_data: str = "%d/%m/%Y"
    separatore_decimale: str = ","
    separatore_migliaia: str = "."

    valuta_default: str = "EUR"

    def descrizione_campi_richiesti(self) -> List[str]:
        mancanti: List[str] = []
        if self.colonna_data_contabile is None:
            mancanti.append("colonna_data_contabile")
        if (
            self.colonna_importo is None
            and (self.colonna_entrate is None or self.colonna_uscite is None)
        ):
            mancanti.append("colonna_importo oppure colonna_entrate+colonna_uscite")
        return mancanti


@dataclass
class CsvImportDetection:
    config: CsvImporterConfig
    formato_rilevato: str = "CSV"
    confidenza: int = 0
    colonne_rilevate: Dict[str, ColonnaRef] = field(default_factory=dict)
    avvisi: List[str] = field(default_factory=list)
    abi: str = ""
    cab: str = ""
    numero_conto: str = ""
    intestatario: str = ""

    @property
    def conto_label(self) -> str:
        parti = []
        if self.abi:
            parti.append(f"ABI {self.abi}")
        if self.cab:
            parti.append(f"CAB {self.cab}")
        if self.numero_conto:
            parti.append(f"Conto {self.numero_conto}")
        return " - ".join(parti)


def _autodetect_delimiter(sample: str) -> str:
    candidates = [";", ",", "\t", "|"]
    counts = {delim: sample.count(delim) for delim in candidates}
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        return ","
    return best


def _decode_csv_bytes(raw_bytes: bytes, preferred_encoding: str = "utf-8-sig") -> str:
    encodings_fallback = [preferred_encoding, "utf-8-sig", "utf-8", "cp1252", "latin-1"]
    for enc in dict.fromkeys(filter(None, encodings_fallback)):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Impossibile decodificare il file CSV con gli encoding noti.")


def _normalize_header(value: str) -> str:
    normalized = (value or "").strip().strip('"').lower()
    replacements = {
        "à": "a",
        "è": "e",
        "é": "e",
        "ì": "i",
        "ò": "o",
        "ù": "u",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _build_header_map(header: List[str]) -> Dict[str, int]:
    header_map: Dict[str, int] = {}
    for idx, nome in enumerate(header):
        pulito = (nome or "").strip()
        normalizzato = _normalize_header(pulito)
        if pulito:
            header_map[pulito] = idx
            header_map[pulito.lower()] = idx
        if normalizzato:
            header_map[normalizzato] = idx
    return header_map


def _find_column(header_map: Dict[str, int], candidates: List[str]) -> Optional[str]:
    for candidate in candidates:
        normalized = _normalize_header(candidate)
        if normalized in header_map:
            return normalized
        if candidate in header_map:
            return candidate
        lowered = candidate.lower()
        if lowered in header_map:
            return lowered
    return None


def _parse_decimal(raw: str, *, sep_decimale: str, sep_migliaia: str) -> Optional[Decimal]:
    if raw is None:
        return None
    testo = raw.strip()
    if not testo:
        return None

    if sep_migliaia and sep_migliaia != sep_decimale:
        testo = testo.replace(sep_migliaia, "")
    if sep_decimale and sep_decimale != ".":
        testo = testo.replace(sep_decimale, ".")

    testo = testo.replace(" ", "")
    testo = testo.replace("EUR", "").replace("€", "")

    try:
        return Decimal(testo)
    except InvalidOperation:
        return None


def _column_value(row: List[str], ref: Optional[ColonnaRef], header_map: Dict[str, int]) -> str:
    if ref is None:
        return ""
    if isinstance(ref, int):
        if 0 <= ref < len(row):
            return (row[ref] or "").strip()
        return ""
    if isinstance(ref, str):
        idx = header_map.get(ref)
        if idx is None:
            idx = header_map.get(ref.strip().lower())
        if idx is None:
            idx = header_map.get(_normalize_header(ref))
        if idx is not None and 0 <= idx < len(row):
            return (row[idx] or "").strip()
        return ""
    return ""


def detect_csv_import_config(raw_bytes: bytes) -> CsvImportDetection:
    testo = _decode_csv_bytes(raw_bytes)
    delimiter = _autodetect_delimiter(testo[:4096])
    rows = list(csv.reader(io.StringIO(testo), delimiter=delimiter))
    if not rows:
        raise ValueError("Il file CSV non contiene righe leggibili.")

    header = rows[0]
    header_map = _build_header_map(header)
    has_header = any(
        item in header_map
        for item in {
            "operazione",
            "data operazione",
            "data contabile",
            "importo",
            "descrizione",
            "causale",
        }
    )

    config = CsvImporterConfig(
        delimiter=delimiter,
        encoding="utf-8-sig",
        ha_intestazione=has_header,
        formato_data="%d/%m/%Y",
        separatore_decimale=",",
        separatore_migliaia=".",
    )
    detection = CsvImportDetection(config=config, confidenza=30 if has_header else 10)

    if not has_header:
        detection.avvisi.append("Intestazione non riconosciuta: potrebbe essere necessario usare le opzioni avanzate.")
        return detection

    field_candidates = {
        "colonna_data_contabile": ["Operazione", "Data operazione", "Data contabile", "Data contabilizzazione", "Data"],
        "colonna_data_valuta": ["Data valuta", "Valuta"],
        "colonna_importo": ["Importo", "Importo movimento", "Amount"],
        "colonna_controparte": ["Controparte", "Beneficiario", "Ordinante"],
        "colonna_iban_controparte": ["IBAN controparte", "Iban ordinante", "Iban beneficiario"],
        "colonna_transaction_id": ["Identificativo End to End", "End To End Id", "ID transazione", "Transaction ID"],
    }

    for config_field, candidates in field_candidates.items():
        column = _find_column(header_map, candidates)
        if column:
            setattr(config, config_field, column)
            detection.colonne_rilevate[config_field] = column
            detection.confidenza += 10

    description_columns = []
    primary_description_candidates = [
        "Informazioni di riconciliazione",
        "Descrizione",
        "Causale descrizione",
        "Descrizione operazione",
    ]
    for candidate in primary_description_candidates:
        column = _find_column(header_map, [candidate])
        if column and column not in description_columns:
            description_columns.append(column)
    if not description_columns:
        column = _find_column(header_map, ["Causale"])
        if column:
            description_columns.append(column)

    if description_columns:
        config.colonna_descrizione = description_columns[0]
        config.colonne_descrizione_extra = description_columns[1:]
        detection.colonne_rilevate["colonna_descrizione"] = ", ".join(description_columns)
        detection.confidenza += 10

    if all(_find_column(header_map, [col]) for col in ["Rag. Soc./ Intestatario", "ABI", "CAB", "Conto"]):
        detection.formato_rilevato = "CSV CBI"
        detection.confidenza += 20

    metadata_row = rows[1] if len(rows) > 1 else []
    detection.abi = _column_value(metadata_row, _find_column(header_map, ["ABI"]), header_map)
    detection.cab = _column_value(metadata_row, _find_column(header_map, ["CAB"]), header_map)
    detection.numero_conto = _column_value(metadata_row, _find_column(header_map, ["Conto"]), header_map)
    detection.intestatario = _column_value(metadata_row, _find_column(header_map, ["Rag. Soc./ Intestatario"]), header_map)

    mancanti = config.descrizione_campi_richiesti()
    if mancanti:
        detection.avvisi.append(
            "Non sono riuscito a rilevare automaticamente: " + ", ".join(mancanti) + "."
        )
    detection.confidenza = min(detection.confidenza, 100)
    return detection


class CsvImporter(BaseParser):
    nome_formato = "csv"

    def __init__(self, config: CsvImporterConfig):
        self.config = config

    def parse(self, raw_bytes: bytes) -> Iterator[ParsedMovimento]:
        if not raw_bytes:
            return iter(())

        testo = _decode_csv_bytes(raw_bytes, self.config.encoding)

        delimiter = self.config.delimiter
        if not delimiter:
            delimiter = _autodetect_delimiter(testo[:4096])

        reader = csv.reader(io.StringIO(testo), delimiter=delimiter)
        rows = list(reader)
        if not rows:
            return iter(())

        header_map: Dict[str, int] = {}
        start_idx = max(int(self.config.righe_da_saltare or 0), 0)
        rows = rows[start_idx:]
        if not rows:
            return iter(())
        data_rows = rows
        if self.config.ha_intestazione:
            header = rows[0]
            data_rows = rows[1:]
            header_map = _build_header_map(header)

        movimenti: List[ParsedMovimento] = []
        for row in data_rows:
            if not any((cell or "").strip() for cell in row):
                continue
            movimento = self._row_to_movimento(row, header_map)
            if movimento is not None:
                movimenti.append(movimento)

        return iter(movimenti)

    def _row_to_movimento(
        self, row: List[str], header_map: Dict[str, int]
    ) -> Optional[ParsedMovimento]:
        cfg = self.config

        raw_data = _column_value(row, cfg.colonna_data_contabile, header_map)
        if not raw_data:
            return None
        try:
            data_contabile = datetime.strptime(raw_data, cfg.formato_data).date()
        except ValueError:
            return None

        data_valuta = None
        raw_valuta_dt = _column_value(row, cfg.colonna_data_valuta, header_map)
        if raw_valuta_dt:
            try:
                data_valuta = datetime.strptime(raw_valuta_dt, cfg.formato_data).date()
            except ValueError:
                data_valuta = None

        importo: Optional[Decimal] = None
        if cfg.colonna_importo is not None:
            importo = _parse_decimal(
                _column_value(row, cfg.colonna_importo, header_map),
                sep_decimale=cfg.separatore_decimale,
                sep_migliaia=cfg.separatore_migliaia,
            )
        else:
            entrate = _parse_decimal(
                _column_value(row, cfg.colonna_entrate, header_map),
                sep_decimale=cfg.separatore_decimale,
                sep_migliaia=cfg.separatore_migliaia,
            ) or Decimal("0")
            uscite = _parse_decimal(
                _column_value(row, cfg.colonna_uscite, header_map),
                sep_decimale=cfg.separatore_decimale,
                sep_migliaia=cfg.separatore_migliaia,
            ) or Decimal("0")
            if entrate == 0 and uscite == 0:
                importo = None
            else:
                importo = (entrate - abs(uscite)).quantize(Decimal("0.01"))

        if importo is None:
            return None

        valuta = _column_value(row, cfg.colonna_valuta, header_map) or cfg.valuta_default
        descrizione_parti = []
        for ref in [cfg.colonna_descrizione, *cfg.colonne_descrizione_extra]:
            value = _column_value(row, ref, header_map)
            if value and value.upper() not in {"NOTPROVIDED", "N/D", "ND"} and value not in descrizione_parti:
                descrizione_parti.append(value)
        descrizione = " - ".join(descrizione_parti)
        controparte = _column_value(row, cfg.colonna_controparte, header_map)
        iban_controparte = _column_value(row, cfg.colonna_iban_controparte, header_map)
        tx_id = _column_value(row, cfg.colonna_transaction_id, header_map)

        return ParsedMovimento(
            data_contabile=data_contabile,
            data_valuta=data_valuta,
            importo=importo,
            valuta=valuta,
            descrizione=descrizione,
            controparte=controparte,
            iban_controparte=iban_controparte,
            provider_transaction_id=tx_id,
        ).clean()
