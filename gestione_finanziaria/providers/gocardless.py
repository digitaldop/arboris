"""
Adapter per GoCardless Bank Account Data (ex-Nordigen).

Documentazione: https://developer.gocardless.com/bank-account-data/

Flusso PSD2 in sintesi:

1. ``POST /token/new/`` con ``secret_id`` + ``secret_key`` restituisce un
   ``access`` (24h) e ``refresh`` (30g).
2. ``GET /institutions/?country=IT`` elenca le banche.
3. ``POST /agreements/enduser/`` (opzionale) crea un accordo con
   ``max_historical_days`` e ``access_valid_for_days``.
4. ``POST /requisitions/`` crea una requisition che restituisce ``link``
   (URL su cui reindirizzare l'utente per l'autorizzazione).
5. Al ritorno, ``GET /requisitions/{id}/`` elenca gli ``accounts`` collegati.
6. ``GET /accounts/{id}/balances/`` e ``/transactions/`` restituiscono saldi
   e movimenti.

L'adapter e' *stateless* rispetto al token: il token di accesso viene
ricavato a ogni istanza ma memorizzato in-memory; chi usa l'adapter in una
sessione lunga puo' riutilizzare la stessa istanza.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from .base import (
    BasePsd2Adapter,
    ProviderAccount,
    ProviderBalance,
    ProviderConnectionInfo,
    ProviderInstitution,
    ProviderTransaction,
)


DEFAULT_BASE_URL = "https://bankaccountdata.gocardless.com/api/v2"
HTTP_TIMEOUT_SECONDS = 30


@dataclass
class GoCardlessCredentials:
    secret_id: str
    secret_key: str
    base_url: str = DEFAULT_BASE_URL


class GoCardlessBadError(RuntimeError):
    """Errore generico di comunicazione con GoCardless BAD."""


class GoCardlessBadAdapter(BasePsd2Adapter):
    nome_provider = "gocardless_bad"

    def __init__(self, credentials: GoCardlessCredentials):
        self.credentials = credentials
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None

    # ------------------------------------------------------------------
    #  HTTP helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        base = self.credentials.base_url.rstrip("/")
        return f"{base}{path}"

    def _headers(self, *, autenticato: bool = True) -> Dict[str, str]:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        if autenticato:
            if not self._access_token:
                self._ensure_access_token()
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _ensure_access_token(self) -> None:
        if self._access_token:
            return
        payload = {
            "secret_id": self.credentials.secret_id,
            "secret_key": self.credentials.secret_key,
        }
        resp = requests.post(
            self._url("/token/new/"),
            json=payload,
            headers={"accept": "application/json", "content-type": "application/json"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise GoCardlessBadError(
                f"Token request failed ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        self._access_token = data.get("access")
        self._refresh_token = data.get("refresh")
        if not self._access_token:
            raise GoCardlessBadError("Risposta token senza campo 'access'.")

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = requests.get(
            self._url(path),
            headers=self._headers(),
            params=params,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise GoCardlessBadError(
                f"GET {path} fallito ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        resp = requests.post(
            self._url(path),
            headers=self._headers(),
            json=payload,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise GoCardlessBadError(
                f"POST {path} fallito ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    # ------------------------------------------------------------------
    #  API pubblica
    # ------------------------------------------------------------------

    def lista_istituti(self, country: str = "IT") -> List[ProviderInstitution]:
        data = self._get("/institutions/", params={"country": country})
        risultato: List[ProviderInstitution] = []
        for item in data or []:
            risultato.append(
                ProviderInstitution(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    bic=item.get("bic", "") or "",
                    countries=item.get("countries", []) or [],
                    logo_url=item.get("logo", "") or "",
                )
            )
        return risultato

    def crea_connessione(
        self,
        *,
        institution_id: str,
        redirect_url: str,
        reference: str,
        max_historical_days: int = 90,
        access_valid_for_days: int = 90,
    ) -> ProviderConnectionInfo:
        agreement_id = None
        try:
            agreement = self._post(
                "/agreements/enduser/",
                {
                    "institution_id": institution_id,
                    "max_historical_days": max_historical_days,
                    "access_valid_for_days": access_valid_for_days,
                    "access_scope": ["balances", "details", "transactions"],
                },
            )
            agreement_id = agreement.get("id")
        except GoCardlessBadError:
            agreement_id = None

        payload: Dict[str, Any] = {
            "redirect": redirect_url,
            "institution_id": institution_id,
            "reference": reference,
            "user_language": "IT",
        }
        if agreement_id:
            payload["agreement"] = agreement_id

        data = self._post("/requisitions/", payload)
        return ProviderConnectionInfo(
            external_connection_id=data.get("id", ""),
            authorization_url=data.get("link", ""),
            institution_id=institution_id,
        )

    def recupera_requisition(self, external_connection_id: str) -> Dict[str, Any]:
        return self._get(f"/requisitions/{external_connection_id}/")

    def lista_conti(self, external_connection_id: str) -> List[ProviderAccount]:
        requisition = self.recupera_requisition(external_connection_id)
        account_ids: List[str] = requisition.get("accounts", []) or []
        institution_id = requisition.get("institution_id", "")
        conti: List[ProviderAccount] = []
        for account_id in account_ids:
            dettagli: Dict[str, Any] = {}
            try:
                dettagli = self._get(f"/accounts/{account_id}/details/") or {}
            except GoCardlessBadError:
                dettagli = {}

            account_info = (dettagli.get("account") or {}) if isinstance(dettagli, dict) else {}
            conti.append(
                ProviderAccount(
                    external_account_id=account_id,
                    iban=account_info.get("iban", "") or "",
                    currency=account_info.get("currency", "EUR") or "EUR",
                    owner_name=account_info.get("ownerName", "") or "",
                    name=account_info.get("name", "") or account_info.get("product", "") or "",
                    institution_id=institution_id,
                )
            )
        return conti

    def saldo_conto(self, external_account_id: str) -> List[ProviderBalance]:
        data = self._get(f"/accounts/{external_account_id}/balances/")
        saldi: List[ProviderBalance] = []
        for item in (data or {}).get("balances", []) or []:
            amount_node = item.get("balanceAmount") or {}
            try:
                valore = Decimal(str(amount_node.get("amount", "0")))
            except (TypeError, ValueError):
                valore = Decimal("0")
            ref_date = None
            raw_ref = item.get("referenceDate")
            if raw_ref:
                try:
                    ref_date = datetime.fromisoformat(raw_ref)
                except ValueError:
                    ref_date = None
            saldi.append(
                ProviderBalance(
                    saldo=valore,
                    valuta=amount_node.get("currency", "EUR") or "EUR",
                    tipo=item.get("balanceType", "") or "",
                    data_riferimento=ref_date,
                )
            )
        return saldi

    def movimenti_conto(
        self,
        external_account_id: str,
        *,
        data_inizio: Optional[date] = None,
        data_fine: Optional[date] = None,
    ) -> List[ProviderTransaction]:
        params: Dict[str, Any] = {}
        if data_inizio:
            params["date_from"] = data_inizio.isoformat()
        if data_fine:
            params["date_to"] = data_fine.isoformat()

        data = self._get(
            f"/accounts/{external_account_id}/transactions/",
            params=params or None,
        )
        transactions_node = (data or {}).get("transactions") or {}
        raw_list: List[Dict[str, Any]] = []
        raw_list.extend(transactions_node.get("booked", []) or [])
        # Includiamo anche le pending per dare all'utente piena visibilita';
        # queste verranno deduplicate se/quando diventano "booked" grazie all'hash.
        raw_list.extend(transactions_node.get("pending", []) or [])

        risultato: List[ProviderTransaction] = []
        for raw in raw_list:
            amount_node = raw.get("transactionAmount") or {}
            try:
                importo = Decimal(str(amount_node.get("amount", "0")))
            except (TypeError, ValueError):
                continue

            data_booking = self._parse_date(raw.get("bookingDate"))
            data_value = self._parse_date(raw.get("valueDate"))
            data_contabile = data_booking or data_value
            if data_contabile is None:
                continue

            debtor = raw.get("debtorName", "") or ""
            creditor = raw.get("creditorName", "") or ""
            controparte = creditor if importo < 0 else debtor or creditor
            iban_node_dbtr = (raw.get("debtorAccount") or {}).get("iban", "") or ""
            iban_node_cdtr = (raw.get("creditorAccount") or {}).get("iban", "") or ""
            iban_controparte = iban_node_cdtr if importo < 0 else (iban_node_dbtr or iban_node_cdtr)

            remittance = raw.get("remittanceInformationUnstructured") or ""
            remittance_arr = raw.get("remittanceInformationUnstructuredArray") or []
            if not remittance and remittance_arr:
                remittance = " | ".join([str(x) for x in remittance_arr if x])

            descrizione = remittance or raw.get("additionalInformation", "") or ""

            risultato.append(
                ProviderTransaction(
                    data_contabile=data_contabile,
                    data_valuta=data_value,
                    importo=importo.quantize(Decimal("0.01")),
                    valuta=amount_node.get("currency", "EUR") or "EUR",
                    descrizione=descrizione.strip(),
                    controparte=controparte.strip(),
                    iban_controparte=(iban_controparte or "").replace(" ", "").upper(),
                    provider_transaction_id=(
                        raw.get("transactionId")
                        or raw.get("internalTransactionId")
                        or raw.get("entryReference")
                        or ""
                    ),
                )
            )
        return risultato

    @staticmethod
    def _parse_date(raw: Optional[str]) -> Optional[date]:
        if not raw:
            return None
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
