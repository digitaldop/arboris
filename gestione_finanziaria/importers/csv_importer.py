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

    colonna_data_contabile: Optional[ColonnaRef] = None
    colonna_data_valuta: Optional[ColonnaRef] = None
    colonna_importo: Optional[ColonnaRef] = None
    colonna_entrate: Optional[ColonnaRef] = None
    colonna_uscite: Optional[ColonnaRef] = None
    colonna_valuta: Optional[ColonnaRef] = None
    colonna_descrizione: Optional[ColonnaRef] = None
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


def _autodetect_delimiter(sample: str) -> str:
    candidates = [";", ",", "\t", "|"]
    counts = {delim: sample.count(delim) for delim in candidates}
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        return ","
    return best


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
        if idx is not None and 0 <= idx < len(row):
            return (row[idx] or "").strip()
        return ""
    return ""


class CsvImporter(BaseParser):
    nome_formato = "csv"

    def __init__(self, config: CsvImporterConfig):
        self.config = config

    def parse(self, raw_bytes: bytes) -> Iterator[ParsedMovimento]:
        if not raw_bytes:
            return iter(())

        encodings_fallback = [self.config.encoding, "utf-8", "cp1252", "latin-1"]
        testo: Optional[str] = None
        for enc in encodings_fallback:
            if not enc:
                continue
            try:
                testo = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if testo is None:
            raise ValueError("Impossibile decodificare il file CSV con gli encoding noti.")

        delimiter = self.config.delimiter
        if not delimiter:
            delimiter = _autodetect_delimiter(testo[:4096])

        reader = csv.reader(io.StringIO(testo), delimiter=delimiter)
        rows = list(reader)
        if not rows:
            return iter(())

        header_map: Dict[str, int] = {}
        data_rows = rows
        if self.config.ha_intestazione:
            header = rows[0]
            data_rows = rows[1:]
            for idx, nome in enumerate(header):
                pulito = (nome or "").strip()
                if pulito:
                    header_map[pulito] = idx
                    header_map[pulito.lower()] = idx

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
        descrizione = _column_value(row, cfg.colonna_descrizione, header_map)
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
