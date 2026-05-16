"""
Adapter per l'API Enable Banking (AIS / PSD2).

Autenticazione app: JWT RS256 (header ``kid`` = application id, private key PEM).
Flusso utente: ``POST /auth`` -> redirect -> callback con ``code`` ->
``POST /sessions`` -> ``session_id``; conti, saldi e transazioni con JWT.

Documentazione: https://enablebanking.com/docs/api
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests

from .base import (
    BasePsd2Adapter,
    ProviderAccount,
    ProviderBalance,
    ProviderConnectionInfo,
    ProviderInstitution,
    ProviderTransaction,
)

DEFAULT_BASE_URL = "https://api.enablebanking.com"
HTTP_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "Arboris-PSD2/1.0"
JWT_ISS = "enablebanking.com"
JWT_AUD = "api.enablebanking.com"
JWT_TTL_MAX_SECONDS = 86400  # vincolo API

# Pattern marker PEM (PKCS#8, PKCS#1, EC, cifrata, ecc.)
_PEM_BLOCK = re.compile(
    r"(-----BEGIN[^-]+-----)\s*(.+?)\s*(-----END[^-]+-----)",
    re.DOTALL | re.IGNORECASE,
)


def normalizza_pem_private_key(pem: str) -> str:
    """
    Ripristina PEM incollato in modo errato: ``MalformedFraming`` spesso deriva
    da chiave su una riga, ``\\n`` letterali, CR/LF misti, spazi nel base64.
    """
    s = (pem or "").strip()
    if not s:
        return s
    if s.startswith("\ufeff"):
        s = s[1:].strip()
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    if s.count("\n") < 2 and "\\n" in s:
        s = s.replace("\\n", "\n")
    m = _PEM_BLOCK.search(s)
    if not m:
        return s
    header, body, footer = m.group(1), m.group(2), m.group(3)
    body = re.sub(r"\s+", "", body)
    if not body:
        return s
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    return f"{header}\n" + "\n".join(lines) + f"\n{footer}\n"


class EnableBankingError(RuntimeError):
    """Errore generico di comunicazione con Enable Banking."""


def _b64url(data: bytes) -> str:
    """Base64url senza padding (stesso stile di PyJWT / RFC 7519)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt_rs256(private_key: Any, header: Dict[str, Any], payload: Dict[str, Any]) -> str:
    """
    Genera un JWT firmato RS256 senza dipendere da PyJWT (solo ``cryptography``).
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    h = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{h}.{p}".encode("ascii")
    try:
        signature = private_key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as exc:  # noqa: BLE001
        raise EnableBankingError(f"Firma JWT RS256 fallita: {exc}") from exc
    s = _b64url(signature)
    return f"{h}.{p}.{s}"


@dataclass
class EnableBankingCredentials:
    app_id: str
    private_key_pem: str
    private_key_passphrase: str = ""
    base_url: str = DEFAULT_BASE_URL
    country_default: str = "IT"
    # ``personal`` (retail) o ``business`` (corporate)
    psu_type: str = "personal"


def _istituto_key(name: str, country: str) -> str:
    return f"{name.strip()}|{country.strip().upper()}"


def _parse_istituto_id(institution_id: str) -> Tuple[str, str]:
    s = (institution_id or "").strip()
    if "|" not in s:
        raise EnableBankingError(
            "Formato institution_id atteso: 'NomeBanca|IT' (da lista istituti)."
        )
    name, country = s.rsplit("|", 1)
    if not name.strip() or not country.strip():
        raise EnableBankingError("Istituto non valido: componenti mancanti.")
    return name.strip(), country.strip().upper()


class EnableBankingAdapter(BasePsd2Adapter):
    nome_provider = "enablebanking"

    def __init__(self, credentials: EnableBankingCredentials) -> None:
        self.credentials = credentials
        self._private_key: Any = None
        self._private_key_err: Optional[str] = None
        self._last_session_id = ""
        self._last_session_accounts: List[Any] = []

    def _carica_private_key(self) -> Any:
        if self._private_key is not None or self._private_key_err:
            return self._private_key
        raw = (self.credentials.private_key_pem or "").strip()
        if not raw:
            self._private_key_err = "Private key PEM mancante."
            return None
        try:
            from cryptography.hazmat.primitives import serialization
        except ImportError as exc:
            self._private_key_err = f"cryptography non disponibile: {exc}"
            return None
        passphrase = (self.credentials.private_key_passphrase or None) or None
        password_bytes = passphrase.encode("utf-8") if passphrase else None
        normalizzato = normalizza_pem_private_key(raw)
        candidati: List[str] = [raw]
        if normalizzato and normalizzato not in candidati:
            candidati.append(normalizzato)
        ultimo: Optional[Exception] = None
        for pem in candidati:
            try:
                self._private_key = serialization.load_pem_private_key(
                    pem.encode("utf-8"),
                    password=password_bytes,
                )
                return self._private_key
            except Exception as exc:  # noqa: BLE001
                ultimo = exc
        self._private_key_err = (
            "Private key Enable Banking non valida: "
            f"{ultimo}. Incolla l'intero .pem (righe "
            "-----BEGIN/END-----) oppure controlla la passphrase se la chiave e' protetta."
        )
        self._private_key = None
        return self._private_key

    def _bearer(self) -> str:
        key = self._carica_private_key()
        if key is None:
            raise EnableBankingError(
                self._private_key_err or "Impossibile firmare le richieste (chiave mancante)."
            )
        now = int(time.time())
        # Margine 60s per non superare il limite 24h e restare sotto 86400s TTL
        exp = min(now + JWT_TTL_MAX_SECONDS - 60, now + JWT_TTL_MAX_SECONDS - 1)
        payload: Dict[str, Any] = {
            "iss": JWT_ISS,
            "aud": JWT_AUD,
            "iat": now,
            "exp": exp,
        }
        header: Dict[str, Any] = {
            "typ": "JWT",
            "alg": "RS256",
            "kid": self.credentials.app_id,
        }
        return _jwt_rs256(key, header, payload)

    def _url(self, path: str) -> str:
        base = self.credentials.base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"

    def _parse_error_body(self, body: str) -> str:
        s = (body or "")[:2000]
        return s or "(corpo risposta vuoto)"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_data: Any = None,
    ) -> Any:
        url = self._url(path)
        headers = {
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
            "Authorization": f"Bearer {self._bearer()}",
        }
        if json_data is not None:
            headers["Content-Type"] = "application/json"
        try:
            r = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise EnableBankingError(f"Errore di rete: {exc}") from exc
        if r.status_code == 204:
            return None
        if r.status_code >= 400:
            dettaglio = self._parse_error_body(r.text)
            if r.status_code == 401 and "wrong signature" in dettaglio.lower():
                dettaglio = (
                    f"{dettaglio} - Firma JWT non riconosciuta da Enable Banking. "
                    "Controlla che l'Application ID configurato in Arboris sia quello "
                    "della stessa app per cui e' stata generata/caricata la private key "
                    "PEM, e che la public key/certificato corrispondente sia associata "
                    "a quella app nel Control Panel Enable Banking."
                )
            raise EnableBankingError(
                f"HTTP {r.status_code} {method} {path}: {dettaglio}"
            )
        if not (r.text or "").strip():
            return None
        try:
            return r.json()
        except ValueError as exc:
            raise EnableBankingError(f"Risposta JSON non valida: {exc}") from exc

    def lista_istituti(self, country: str = "IT") -> List[ProviderInstitution]:
        paese = (country or self.credentials.country_default or "IT").upper()
        data = self._request("GET", "/aspsps", params={"country": paese})
        raw = (data or {}).get("aspsps") or []
        out: List[ProviderInstitution] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            ctry = str(item.get("country") or "").strip().upper()
            if not name or not ctry:
                continue
            bic = str(item.get("bic") or "").strip()
            logo = str(item.get("logo") or "").strip()
            out.append(
                ProviderInstitution(
                    id=_istituto_key(name, ctry),
                    name=name,
                    bic=bic,
                    countries=[ctry] if ctry else [],
                    logo_url=logo,
                )
            )
        return out

    def crea_connessione(
        self,
        *,
        institution_id: str,
        redirect_url: str,
        reference: str,
        max_historical_days: int = 90,
        access_valid_for_days: int = 90,
    ) -> ProviderConnectionInfo:
        aspsp_name, aspsp_country = _parse_istituto_id(institution_id)
        del max_historical_days  # non usato dall'API Enable Banking
        # ISO 8601 con suffisso Z
        until = datetime.now(timezone.utc) + timedelta(days=max(1, access_valid_for_days))
        valid_until = until.strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": aspsp_name, "country": aspsp_country},
            "state": reference,
            "redirect_url": redirect_url,
            "psu_type": (self.credentials.psu_type or "personal").lower(),
        }
        data = self._request("POST", "/auth", json_data=body)
        auth_url = str((data or {}).get("url") or "").strip()
        if not auth_url:
            raise EnableBankingError("Risposta /auth senza 'url' di reindirizzamento.")
        return ProviderConnectionInfo(
            external_connection_id=reference,
            authorization_url=auth_url,
            institution_id=institution_id,
            expires_at=until,
        )

    def scambia_codice_sessione(self, code: str) -> str:
        """Scambia il ``code`` del callback in ``session_id``."""
        c = (code or "").strip()
        if not c:
            raise EnableBankingError("Code di autorizzazione mancante.")
        data = self._request("POST", "/sessions", json_data={"code": c})
        sid = str((data or {}).get("session_id") or "").strip()
        if not sid:
            raise EnableBankingError("Risposta /sessions senza session_id.")
        accounts = (data or {}).get("accounts")
        accounts_data = (data or {}).get("accounts_data")
        if isinstance(accounts, list) and accounts:
            self._last_session_accounts = accounts
            self._last_session_id = sid
        elif isinstance(accounts_data, list) and accounts_data:
            self._last_session_accounts = accounts_data
            self._last_session_id = sid
        return sid

    @staticmethod
    def _extract_iban(acc: Dict[str, Any]) -> str:
        iban = ""
        acct = acc.get("account_id")
        if isinstance(acct, dict):
            iban = str(acct.get("iban") or "").strip()
        for key in ("all_account_ids", "allAccountIds", "identifications"):
            if iban:
                break
            values = acc.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                scheme = str(
                    item.get("scheme_name")
                    or item.get("schemeName")
                    or item.get("scheme")
                    or ""
                ).upper()
                if scheme == "IBAN":
                    iban = str(item.get("identification") or "").strip()
                    break
        return iban

    @staticmethod
    def _parse_account_id(acc: Dict[str, Any]) -> str:
        raw_account_id = acc.get("account_id")
        if isinstance(raw_account_id, str):
            return raw_account_id.strip()
        return str(acc.get("uid") or acc.get("accountId") or "").strip()

    def _account_record_from_session_payload(self, acc: Dict[str, Any]) -> ProviderAccount:
        uid = self._parse_account_id(acc)
        iban = self._extract_iban(acc)
        owner = str(acc.get("name") or acc.get("holder") or "").strip()
        details = str(acc.get("details") or "").strip()
        product = str(acc.get("product") or "").strip()
        account_product = " - ".join(part for part in (product, details) if part)
        account_type = str(
            acc.get("cash_account_type")
            or acc.get("cashAccountType")
            or ""
        ).strip().upper()
        identification_hash = str(
            acc.get("identification_hash")
            or acc.get("identificationHash")
            or ""
        ).strip()
        name = str(acc.get("name") or "").strip()
        cur = str(acc.get("currency") or "EUR").upper() or "EUR"
        aspsp = acc.get("account_servicer") or {}
        bic = str(aspsp.get("bic_fi") or aspsp.get("name") or "").strip() if isinstance(aspsp, dict) else ""
        return ProviderAccount(
            external_account_id=uid,
            iban=iban,
            currency=cur,
            owner_name=owner,
            name=details or product or name or iban or uid,
            institution_id=bic,
            identification_hash=identification_hash,
            account_type=account_type,
            account_product=account_product,
        )

    def _account_records_from_payload_list(self, items: List[Any]) -> List[ProviderAccount]:
        records: List[ProviderAccount] = []
        for item in items:
            if isinstance(item, dict):
                if item.get("uid") or item.get("accountId") or item.get("account_id"):
                    record = self._account_record_from_session_payload(item)
                    if record.external_account_id:
                        records.append(record)
            elif str(item or "").strip():
                uid = str(item).strip()
                records.append(
                    ProviderAccount(
                        external_account_id=uid,
                        name=f"Conto {uid[:8]}",
                        iban="",
                        currency="EUR",
                    )
                )
        return records

    def _enrich_account_details(self, record: ProviderAccount) -> ProviderAccount:
        if record.iban or record.account_type or record.account_product:
            return record
        try:
            data = self._request("GET", f"/accounts/{record.external_account_id}/details")
        except EnableBankingError:
            return record
        if not isinstance(data, dict):
            return record
        data.setdefault("uid", record.external_account_id)
        if record.identification_hash:
            data.setdefault("identification_hash", record.identification_hash)
        enriched = self._account_record_from_session_payload(data)
        return enriched if enriched.external_account_id else record

    def lista_conti(self, external_connection_id: str) -> List[ProviderAccount]:
        sid = (external_connection_id or "").strip()
        if not sid or sid.startswith("arboris-"):
            raise EnableBankingError(
                "Session ID mancante: completare il callback di autorizzazione."
            )
        if sid == self._last_session_id and self._last_session_accounts:
            return self._account_records_from_payload_list(self._last_session_accounts)
        data = self._request("GET", f"/sessions/{sid}")
        accounts_data = (data or {}).get("accounts_data")
        if isinstance(accounts_data, list) and accounts_data:
            return [
                self._enrich_account_details(record)
                for record in self._account_records_from_payload_list(accounts_data)
            ]
        uuids = (data or {}).get("accounts")
        if isinstance(uuids, list) and uuids:
            return [
                self._enrich_account_details(record)
                for record in self._account_records_from_payload_list(uuids)
            ]
        return []

    def saldo_conto(self, external_account_id: str) -> List[ProviderBalance]:
        account_id = (external_account_id or "").strip()
        if not account_id:
            return []
        data = self._request("GET", f"/accounts/{account_id}/balances")
        result: List[ProviderBalance] = []
        for item in (data or {}).get("balances") or []:
            if not isinstance(item, dict):
                continue
            amt = item.get("balance_amount") or {}
            try:
                valore = Decimal(str(amt.get("amount", "0")))
            except (TypeError, ValueError, ArithmeticError):
                valore = Decimal("0")
            valuta = str(amt.get("currency") or "EUR").upper() or "EUR"
            data_ref: Optional[datetime] = None
            rd = item.get("reference_date") or item.get("last_change_date_time")
            if rd:
                try:
                    s = str(rd)
                    if "T" in s:
                        data_ref = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    else:
                        data_ref = datetime.combine(
                            date.fromisoformat(s[:10]), datetime.min.time(), tzinfo=timezone.utc
                        )
                except (ValueError, TypeError):
                    data_ref = None
            result.append(
                ProviderBalance(
                    saldo=valore,
                    valuta=valuta,
                    tipo=str(item.get("balance_type") or item.get("name") or "unknown"),
                    data_riferimento=data_ref,
                )
            )
        return result

    @staticmethod
    def _parse_transaction(raw: Dict[str, Any]) -> Optional[ProviderTransaction]:
        tamount = raw.get("transaction_amount") or {}
        try:
            base = abs(Decimal(str(tamount.get("amount", "0"))))
        except (TypeError, ValueError, ArithmeticError):
            base = Decimal("0")
        valuta = str(tamount.get("currency") or "EUR").upper() or "EUR"
        ind = (raw.get("credit_debit_indicator") or "").upper()
        if ind == "CRDT":
            importo = base
        elif ind == "DBIT":
            importo = -base
        else:
            # fallback: tratta come contabile positivo/negativo
            importo = base if ind != "DBIT" else -base
        bdate = str(raw.get("booking_date") or raw.get("transaction_date") or "")
        if not bdate:
            return None
        try:
            data_cont = date.fromisoformat(bdate[:10])
        except ValueError:
            return None
        vdate = None
        vd = str(raw.get("value_date") or "")
        if vd:
            try:
                vdate = date.fromisoformat(vd[:10])
            except ValueError:
                vdate = None
        if ind == "CRDT":
            counterparty = raw.get("debtor") or {}
        else:
            counterparty = raw.get("creditor") or {}
        controparte = str(counterparty.get("name") or "") if isinstance(counterparty, dict) else ""
        iban_ct = ""
        if ind == "CRDT":
            acc_n = raw.get("debtor_account") or {}
        else:
            acc_n = raw.get("creditor_account") or {}
        if isinstance(acc_n, dict):
            iban_ct = str(acc_n.get("iban") or "").strip()
        rem = raw.get("remittance_information")
        descrizione = ""
        if isinstance(rem, list) and rem:
            descrizione = " | ".join(str(x) for x in rem if x)
        if not descrizione:
            descrizione = str(raw.get("reference_number") or raw.get("note") or "")
        txid = str(
            raw.get("entry_reference")
            or raw.get("transaction_id")
            or raw.get("internal_transaction_id")
            or ""
        )
        return ProviderTransaction(
            data_contabile=data_cont,
            data_valuta=vdate,
            importo=importo,
            valuta=valuta,
            descrizione=descrizione[:2000],
            controparte=controparte[:500],
            iban_controparte=iban_ct,
            provider_transaction_id=txid[:200],
        )

    def movimenti_conto(
        self,
        external_account_id: str,
        *,
        data_inizio: Optional[date] = None,
        data_fine: Optional[date] = None,
    ) -> List[ProviderTransaction]:
        account_id = (external_account_id or "").strip()
        if not account_id:
            return []
        risultato: List[ProviderTransaction] = []
        cont_key: Optional[str] = None
        for _ in range(500):
            params: Dict[str, Any] = {}
            if data_inizio:
                params["date_from"] = data_inizio.isoformat()
            if data_fine:
                params["date_to"] = data_fine.isoformat()
            if cont_key:
                params["continuation_key"] = cont_key
            data = self._request("GET", f"/accounts/{account_id}/transactions", params=params)
            for tr in (data or {}).get("transactions") or []:
                if isinstance(tr, dict):
                    parsed = self._parse_transaction(tr)
                    if parsed is not None:
                        risultato.append(parsed)
            cont_key = (data or {}).get("continuation_key")
            if not cont_key:
                break
        return risultato
