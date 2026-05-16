"""
Interfaccia astratta per un adapter PSD2 (AIS).

Tutti i provider (GoCardless BAD, Fabrick, Tink, ...) implementano queste
classi/metodi in modo che il resto del codice (view, servizi) sia
indipendente dall'implementazione specifica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional


@dataclass
class ProviderInstitution:
    """Istituto bancario esposto dal provider."""

    id: str
    name: str
    bic: str = ""
    countries: List[str] = field(default_factory=list)
    logo_url: str = ""


@dataclass
class ProviderAccount:
    """Conto esposto da una connessione (requisition) PSD2."""

    external_account_id: str
    iban: str = ""
    currency: str = "EUR"
    owner_name: str = ""
    name: str = ""
    institution_id: str = ""
    identification_hash: str = ""
    account_type: str = ""
    account_product: str = ""


@dataclass
class ProviderBalance:
    saldo: Decimal
    valuta: str = "EUR"
    tipo: str = ""
    data_riferimento: Optional[datetime] = None


@dataclass
class ProviderTransaction:
    data_contabile: date
    importo: Decimal
    valuta: str = "EUR"
    data_valuta: Optional[date] = None
    descrizione: str = ""
    controparte: str = ""
    iban_controparte: str = ""
    provider_transaction_id: str = ""


@dataclass
class ProviderConnectionInfo:
    """Info restituita dopo aver creato una requisition/consenso."""

    external_connection_id: str
    authorization_url: str
    institution_id: str = ""
    expires_at: Optional[datetime] = None


class BasePsd2Adapter:
    """Contratto che ogni adapter PSD2 deve rispettare."""

    nome_provider: str = "base"

    def lista_istituti(self, country: str = "IT") -> List[ProviderInstitution]:
        raise NotImplementedError

    def crea_connessione(
        self,
        *,
        institution_id: str,
        redirect_url: str,
        reference: str,
        max_historical_days: int = 90,
        access_valid_for_days: int = 90,
    ) -> ProviderConnectionInfo:
        raise NotImplementedError

    def lista_conti(self, external_connection_id: str) -> List[ProviderAccount]:
        raise NotImplementedError

    def saldo_conto(self, external_account_id: str) -> List[ProviderBalance]:
        raise NotImplementedError

    def movimenti_conto(
        self,
        external_account_id: str,
        *,
        data_inizio: Optional[date] = None,
        data_fine: Optional[date] = None,
    ) -> List[ProviderTransaction]:
        raise NotImplementedError
