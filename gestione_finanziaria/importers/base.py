"""
Tipi comuni a tutti gli importatori di estratti conto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, List, Optional


@dataclass
class ParsedMovimento:
    """
    Rappresentazione normalizzata di un singolo movimento letto da un file
    di estratto conto. E' indipendente dal formato sorgente (CAMT/MT940/CSV)
    e viene consumata dal servizio di import per creare record
    :class:`gestione_finanziaria.models.MovimentoFinanziario`.
    """

    data_contabile: date
    importo: Decimal
    valuta: str = "EUR"
    data_valuta: Optional[date] = None
    descrizione: str = ""
    controparte: str = ""
    iban_controparte: str = ""
    provider_transaction_id: str = ""

    def clean(self) -> "ParsedMovimento":
        self.valuta = (self.valuta or "EUR").upper().strip()[:3] or "EUR"
        self.descrizione = (self.descrizione or "").strip()
        self.controparte = (self.controparte or "").strip()
        self.iban_controparte = (self.iban_controparte or "").replace(" ", "").upper()
        self.provider_transaction_id = (self.provider_transaction_id or "").strip()
        if self.provider_transaction_id.upper() in {"NOTPROVIDED", "NONFORNITO", "N/D", "ND"}:
            self.provider_transaction_id = ""
        if not isinstance(self.importo, Decimal):
            self.importo = Decimal(str(self.importo))
        return self


@dataclass
class RisultatoImport:
    """Sommario del processo di import (usato anche nelle view/template)."""

    totale_letti: int = 0
    inseriti: int = 0
    duplicati: int = 0
    aggiornati: int = 0
    riconciliati: int = 0
    errori: int = 0
    messaggi: List[str] = field(default_factory=list)
    movimenti_ids: List[int] = field(default_factory=list)

    def aggiungi_messaggio(self, msg: str) -> None:
        self.messaggi.append(msg)


class BaseParser:
    """Interfaccia comune per i parser di estratto conto."""

    nome_formato: str = "base"

    def parse(self, raw_bytes: bytes) -> Iterable[ParsedMovimento]:
        raise NotImplementedError
