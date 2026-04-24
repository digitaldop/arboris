"""
Adapter per Salt Edge Account Information API v6.

Documentazione: https://docs.saltedge.com/v6/

Salt Edge e' un aggregatore PSD2 regolamentato (AISP) che copre ~5000
banche in Europa, inclusi gli istituti italiani retail e business (Banco
BPM, UniCredit, Intesa Sanpaolo, Banca Sella, BPER, etc.).

Il flusso AIS implementato in questo adapter e' quello consigliato da
Salt Edge per i partner che non devono fungere da AISP proprio:

1. **Customer**: una volta per singola organizzazione/utente Arboris
   creiamo (o riusiamo) un ``customer`` su Salt Edge. L'``identifier``
   che passiamo e' libero: qui usiamo ``arboris-conn-<pk>`` cosi' ogni
   connessione ha il suo customer dedicato, il che semplifica la
   ricerca della connection_id al callback.
2. **Connect session (Widget)**: ``POST /connections/connect`` restituisce
   un ``connect_url`` verso cui redirigere l'utente: e' la UI ospitata
   da Salt Edge dove l'utente sceglie la banca e fa SCA.
3. **Callback**: al termine, Salt Edge redirige il browser al ``return_to``
   che abbiamo passato (qui ``callback_connessione_psd2``). Per sapere
   quale connection_id e' appena stata creata basta elencare
   ``GET /connections?customer_id=<id>`` e prendere la piu' recente.
4. **Accounts & Transactions**: con la ``connection_id`` in mano,
   ``GET /accounts?connection_id=...`` e
   ``GET /transactions?connection_id=...&account_id=...`` restituiscono
   rispettivamente i conti (con saldo embedded) e i movimenti.

Autenticazione: tutti gli endpoint richiedono gli header ``App-id`` e
``Secret``. Per le app in stato "live" Salt Edge richiede anche la firma
RSA della richiesta: per le app in stato "pending"/"test"
(incluso l'ambiente dove girano le fake banks per sviluppo) basta
``App-id`` + ``Secret``. La firma RSA non e' implementata qui: se
attivate il "Signatures required" sul dashboard, disabilitatelo finche'
non viene aggiunta (o aggiungete il supporto in ``_headers``).
"""

from __future__ import annotations

import base64
import json as _json
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone as dt_timezone
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


DEFAULT_BASE_URL = "https://www.saltedge.com/api/v6"
HTTP_TIMEOUT_SECONDS = 30

# User-Agent dichiarato: alcuni WAF (Salt Edge Inc. load balancer incluso)
# filtrano il default "python-requests/..." e restituiscono 403 HTML.
DEFAULT_USER_AGENT = "Arboris-PSD2/1.0 (+https://arboris.local)"

# Consent scopes usati in v6. "accounts" -> dettagli conti + saldi;
# "transactions" -> storico movimenti.
DEFAULT_CONSENT_SCOPES: List[str] = ["accounts", "transactions"]


@dataclass
class SaltEdgeCredentials:
    app_id: str
    secret: str
    base_url: str = DEFAULT_BASE_URL
    # Se True, Salt Edge include nel widget anche le fake banks (fake_*)
    # utili in ambiente di test.
    include_fake_providers: bool = False
    # ISO 3166-1 alfa-2 del paese di default per la lista istituti.
    country_default: str = "IT"
    # Lingua del widget Salt Edge (ISO 639-1).
    locale: str = "it"
    # Private key RSA PEM (PKCS#1 o PKCS#8, opzionalmente cifrata) per la
    # firma delle richieste. Obbligatoria per app Salt Edge in stato Live
    # e spesso richiesta anche su endpoint "write" come
    # ``POST /connections/connect`` pure in stato Pending/Test: se manca,
    # il WAF puo' rispondere ``403 Forbidden`` (HTML) prima ancora di
    # arrivare all'API. Lascia stringa vuota per non firmare.
    private_key_pem: str = ""
    # Passphrase della private key PEM, se presente. Vuota = nessuna.
    private_key_passphrase: str = ""


class SaltEdgeError(RuntimeError):
    """Errore generico di comunicazione con Salt Edge."""


class SaltEdgeAdapter(BasePsd2Adapter):
    nome_provider = "saltedge"

    def __init__(
        self,
        credentials: SaltEdgeCredentials,
        *,
        customer_id: str = "",
    ):
        self.credentials = credentials
        # Se gia' noto (letto dalla ConnessioneBancaria), lo riutilizziamo
        # e non creiamo un nuovo customer al primo crea_connessione.
        self.customer_id = customer_id
        # Private key RSA caricata lazy alla prima firma.
        self._private_key = None
        self._private_key_errore: Optional[str] = None

    # ------------------------------------------------------------------
    #  HTTP helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        base = self.credentials.base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"

    def _base_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
            "App-id": self.credentials.app_id,
            "Secret": self.credentials.secret,
        }

    def _carica_private_key(self):
        if self._private_key is not None or self._private_key_errore:
            return self._private_key
        pem = (self.credentials.private_key_pem or "").strip()
        if not pem:
            return None
        try:
            from cryptography.hazmat.primitives import serialization
        except ImportError as exc:
            self._private_key_errore = (
                f"Modulo 'cryptography' non disponibile per firmare le richieste Salt Edge: {exc}"
            )
            return None
        passphrase = self.credentials.private_key_passphrase or None
        password_bytes = passphrase.encode("utf-8") if passphrase else None
        try:
            self._private_key = serialization.load_pem_private_key(
                pem.encode("utf-8"),
                password=password_bytes,
            )
        except Exception as exc:
            self._private_key_errore = (
                f"Private key Salt Edge non valida (PEM/passphrase): {exc}"
            )
            self._private_key = None
        return self._private_key

    def _firma_headers(
        self,
        metodo: str,
        url_completo: str,
        body_bytes: bytes,
    ) -> Dict[str, str]:
        """
        Genera gli header ``Expires-at`` + ``Signature`` usando la private
        key RSA configurata. Ritorna dict vuoto se la firma e' disattiva.
        """
        key = self._carica_private_key()
        if key is None:
            return {}
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError:
            return {}

        # Scadenza della richiesta: now + 60 secondi (consigliato da Salt Edge).
        expires_at = int(time.time()) + 60
        body_str = body_bytes.decode("utf-8") if body_bytes else ""
        stringa_da_firmare = f"{expires_at}|{metodo.upper()}|{url_completo}|{body_str}"
        try:
            firma = key.sign(
                stringa_da_firmare.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception as exc:
            self._private_key_errore = f"Firma Salt Edge fallita: {exc}"
            return {}
        return {
            "Expires-at": str(expires_at),
            "Signature": base64.b64encode(firma).decode("ascii"),
        }

    def _request(
        self,
        metodo: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url_completo = self._url(path)

        # Serializziamo il body a mano cosi' possiamo usare gli stessi bytes
        # sia per la firma sia per l'invio (evitando differenze dovute a
        # riordinamento chiavi o spaziature).
        body_bytes = b""
        if json_body is not None:
            body_bytes = _json.dumps(
                json_body,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")

        headers = self._base_headers()

        # Per la firma Salt Edge richiede "l'URL originale con query".
        prepared = requests.Request(
            metodo.upper(),
            url_completo,
            params=params,
            headers=headers,
            data=body_bytes if body_bytes else None,
        ).prepare()

        firma_headers = self._firma_headers(
            metodo, prepared.url, body_bytes
        )
        if firma_headers:
            prepared.headers.update(firma_headers)

        try:
            with requests.Session() as sess:
                resp = sess.send(prepared, timeout=HTTP_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise SaltEdgeError(f"{metodo} {path} errore di rete: {exc}")

        if resp.status_code == 404:
            raise SaltEdgeError(f"{metodo} {path} -> 404 (risorsa non trovata).")
        if resp.status_code >= 400:
            # Salt Edge risponde con {"error": {"class": "...", "message": "..."}}
            dettagli = resp.text[:400]
            try:
                body = resp.json()
                err = body.get("error") if isinstance(body, dict) else None
                if isinstance(err, dict):
                    dettagli = (
                        f"{err.get('class', 'Error')}: "
                        f"{err.get('message', '')}".strip()
                    ) or dettagli
            except ValueError:
                pass
            raise SaltEdgeError(
                f"{metodo} {path} fallito ({resp.status_code}): {dettagli}"
            )
        try:
            return resp.json()
        except ValueError:
            raise SaltEdgeError(
                f"{metodo} {path} risposta non JSON (status {resp.status_code})."
            )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        return self._request("POST", path, json_body=payload)

    def _put(self, path: str, payload: Dict[str, Any]) -> Any:
        return self._request("PUT", path, json_body=payload)

    # ------------------------------------------------------------------
    #  Customers
    # ------------------------------------------------------------------

    def _crea_o_recupera_customer(self, identifier: str) -> str:
        """
        Crea un Customer con ``identifier`` oppure, se gia' esistente, lo
        recupera. Gli ``identifier`` sono univoci per app su Salt Edge:
        un secondo POST con lo stesso identifier ritorna
        ``DuplicatedCustomer`` (HTTP 400/409).

        Nota: Salt Edge v6 **non** supporta il filtro ``?identifier=...`` su
        ``GET /customers`` (ritorna la lista completa ignorando il param).
        Per recuperare un customer pre-esistente dobbiamo quindi paginare la
        lista e fare il match lato client.
        """
        if not identifier:
            identifier = f"arboris-{uuid.uuid4().hex[:12]}"

        errore_post: Optional[SaltEdgeError] = None
        raw_post_response: Any = None
        try:
            raw_post_response = self._post(
                "/customers",
                {"data": {"identifier": identifier}},
            )
            cid = _estrai_customer_id(raw_post_response)
            if cid:
                return cid
        except SaltEdgeError as exc:
            errore_post = exc

        # Fallback: paginiamo GET /customers e cerchiamo l'identifier lato client.
        try:
            cid_trovato = self._cerca_customer_per_identifier(identifier)
        except SaltEdgeError as exc_list:
            raise SaltEdgeError(
                "Impossibile creare/recuperare il customer Salt Edge con "
                f"identifier '{identifier}'. "
                f"POST /customers -> {_descrivi_esito_post(errore_post, raw_post_response)}. "
                f"GET /customers (fallback) -> {exc_list}."
            )

        if cid_trovato:
            return cid_trovato

        raise SaltEdgeError(
            "Impossibile creare/recuperare il customer Salt Edge con "
            f"identifier '{identifier}'. "
            f"POST /customers -> {_descrivi_esito_post(errore_post, raw_post_response)}. "
            f"GET /customers non ha restituito nessun record con quell'identifier."
        )

    def _cerca_customer_per_identifier(self, identifier: str) -> Optional[str]:
        """
        Scorre ``GET /customers`` in paginazione e ritorna il ``customer_id``
        per il primo record con ``identifier`` corrispondente. ``None`` se
        non trovato dopo aver scandito tutte le pagine (o il limite di
        sicurezza).
        """
        params: Dict[str, Any] = {}
        max_pagine = 50  # fino a ~50.000 record a ~1.000/pagina
        for _ in range(max_pagine):
            data = self._get("/customers", params=params)
            items = (data or {}).get("data") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(item.get("identifier") or "") == identifier:
                    cid = str(item.get("id") or "").strip()
                    if cid:
                        return cid
            paging = (data or {}).get("meta") or {}
            next_id = str((paging.get("next_id") or "")).strip()
            if not next_id:
                return None
            params["from_id"] = next_id
        return None

    # ------------------------------------------------------------------
    #  BasePsd2Adapter - implementazione
    # ------------------------------------------------------------------

    def lista_istituti(self, country: str = "IT") -> List[ProviderInstitution]:
        """
        Elenca i provider bancari. Salt Edge ne espone migliaia quindi
        paginiamo in modo best-effort, tagliando a un massimo ragionevole.
        """
        paese = (country or self.credentials.country_default or "IT").upper()
        params: Dict[str, Any] = {"country_code": paese}
        if self.credentials.include_fake_providers:
            params["include_fake_providers"] = "true"

        risultato: List[ProviderInstitution] = []
        next_id: Optional[str] = None
        max_pagine = 5  # tutela: ~2000 record a 400 per pagina
        for _ in range(max_pagine):
            if next_id:
                params["from_id"] = next_id
            data = self._get("/providers", params=params)
            items = (data or {}).get("data") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                risultato.append(
                    ProviderInstitution(
                        id=str(item.get("code") or item.get("id") or "").strip(),
                        name=str(item.get("name") or "").strip(),
                        bic="",
                        countries=[paese],
                        logo_url=str(item.get("logo_url") or "").strip(),
                    )
                )
            paging = (data or {}).get("meta") or {}
            next_id = str((paging.get("next_id") or "")).strip() or None
            if not next_id:
                break

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
        """
        Crea un customer (se non ancora noto) e una Connect Session
        ``/connections/connect``. Salt Edge restituisce un ``connect_url``
        a cui reindirizziamo l'utente per scegliere la banca + SCA.
        """
        # L'identifier deve essere univoco per app su Salt Edge. Se riusiamo
        # banalmente ``reference`` (es. ``arboris-<pk>``) ogni retry della
        # stessa connessione cade su DuplicatedCustomer e ci costringe a
        # scandire l'intera lista customer per recuperarne l'id. Per evitarlo
        # aggiungiamo un suffisso casuale cosi' ogni tentativo genera un
        # customer nuovo (sono gratuiti e non vincolano le banche collegate).
        if not self.customer_id:
            suffix = uuid.uuid4().hex[:8]
            base_identifier = reference or f"arboris-{uuid.uuid4().hex[:12]}"
            identifier = f"{base_identifier}-{suffix}"
            self.customer_id = self._crea_o_recupera_customer(identifier)

        consent: Dict[str, Any] = {
            "scopes": list(DEFAULT_CONSENT_SCOPES),
            "period_days": int(max(1, min(access_valid_for_days, 180))),
        }

        attempt: Dict[str, Any] = {
            "return_to": redirect_url,
            "fetch_scopes": list(DEFAULT_CONSENT_SCOPES),
            "locale": self.credentials.locale or "it",
            "store_credentials": True,
            # custom_fields viene echeggiato in webhook/callback e ci aiuta a
            # riconoscere questa specifica connection dopo il ritorno.
            "custom_fields": {"arboris_reference": reference},
        }
        if max_historical_days and max_historical_days > 0:
            attempt["from_date"] = (
                _today_utc().replace(day=1).isoformat()
                if max_historical_days >= 365
                else _date_giorni_fa(max_historical_days).isoformat()
            )

        payload: Dict[str, Any] = {
            "data": {
                "customer_id": self.customer_id,
                "consent": consent,
                "attempt": attempt,
            }
        }
        if institution_id:
            payload["data"]["provider_code"] = institution_id
        if self.credentials.include_fake_providers:
            payload["data"]["include_fake_providers"] = True

        data = self._post("/connections/connect", payload)
        body = (data or {}).get("data") or {}
        connect_url = str(body.get("connect_url") or body.get("redirect_url") or "").strip()
        expires_raw = body.get("expires_at")
        expires_at: Optional[datetime] = None
        if expires_raw:
            try:
                expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            except ValueError:
                expires_at = None

        if not connect_url:
            raise SaltEdgeError("Salt Edge non ha restituito un 'connect_url' valido.")

        # La connection_id vera e' sconosciuta finche' l'utente non completa
        # l'autorizzazione: come placeholder usiamo il customer_id cosi' il
        # callback sa quale customer interrogare.
        return ProviderConnectionInfo(
            external_connection_id="",
            authorization_url=connect_url,
            institution_id=institution_id,
            expires_at=expires_at,
        )

    def trova_connection_id(
        self,
        *,
        customer_id: str = "",
        created_after: Optional[datetime] = None,
    ) -> str:
        """
        Recupera la connection_id appena creata interrogando
        ``GET /connections?customer_id=...``. Se ``created_after`` e'
        valorizzato, scarta le connection piu' vecchie (evita di prendere
        una connection gia' esistente qualora il customer ne avesse piu'
        d'una).
        """
        cid = customer_id or self.customer_id
        if not cid:
            raise SaltEdgeError("customer_id mancante: impossibile cercare la connection.")

        data = self._get("/connections", params={"customer_id": cid})
        items = (data or {}).get("data") or []
        candidati: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if created_after is not None:
                raw_created = item.get("created_at") or ""
                try:
                    created_dt = datetime.fromisoformat(
                        str(raw_created).replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=dt_timezone.utc)
                soglia = created_after
                if soglia.tzinfo is None:
                    soglia = soglia.replace(tzinfo=dt_timezone.utc)
                if created_dt < soglia:
                    continue
            candidati.append(item)

        if not candidati:
            raise SaltEdgeError(
                "Nessuna connection trovata per il customer Salt Edge. "
                "L'utente potrebbe aver annullato il flusso."
            )

        # Prendiamo la piu' recente per created_at (fallback su 'last_success_at').
        def _chiave(item: Dict[str, Any]) -> str:
            return str(item.get("created_at") or item.get("last_success_at") or "")

        scelta = max(candidati, key=_chiave)
        return str(scelta.get("id") or "").strip()

    def lista_conti(self, external_connection_id: str) -> List[ProviderAccount]:
        if not external_connection_id:
            raise SaltEdgeError("connection_id mancante per lista_conti.")
        data = self._get(
            "/accounts",
            params={"connection_id": external_connection_id},
        )
        items = (data or {}).get("data") or []
        conti: List[ProviderAccount] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            extra = item.get("extra") or {}
            iban = str(
                extra.get("iban")
                or extra.get("account_number")
                or ""
            ).replace(" ", "").upper()
            owner = str(
                extra.get("client_name")
                or extra.get("account_holder_name")
                or ""
            ).strip()
            name = str(
                item.get("name")
                or extra.get("account_name")
                or extra.get("product")
                or ""
            ).strip()
            conti.append(
                ProviderAccount(
                    external_account_id=str(item.get("id") or "").strip(),
                    iban=iban,
                    currency=str(item.get("currency_code") or "EUR").upper(),
                    owner_name=owner,
                    name=name or f"Conto {iban or item.get('id')}",
                    institution_id=str(item.get("connection_id") or external_connection_id),
                )
            )
        return conti

    def saldo_conto(self, external_account_id: str) -> List[ProviderBalance]:
        """
        Salt Edge non espone un endpoint dedicato per il saldo: il campo
        ``balance`` e' incluso nel record account. Ricarichiamo l'account
        specifico e produciamo il saldo corrente da quello.
        """
        # /accounts non supporta filtro per id singolo; dobbiamo usare il
        # connection_id. Non conoscendolo qui, facciamo un tentativo su
        # /accounts?customer_id=... (pero' Salt Edge v6 richiede o
        # customer_id o connection_id). Se il chiamante ha solo
        # external_account_id, deve averci gia' passato il connection_id
        # attraverso l'oggetto ContoBancario/Connessione a monte.
        # Qui ritorniamo un ProviderBalance vuoto: la pipeline principale
        # usa comunque movimenti_conto + ricalcolo saldo.
        return []

    def saldo_conto_da_connection(
        self,
        external_connection_id: str,
        external_account_id: str,
    ) -> List[ProviderBalance]:
        """Variante che conosce anche il connection_id (usata dal service)."""
        if not external_connection_id or not external_account_id:
            return []
        data = self._get(
            "/accounts",
            params={"connection_id": external_connection_id},
        )
        items = (data or {}).get("data") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "") != str(external_account_id):
                continue
            try:
                valore = Decimal(str(item.get("balance", "0")))
            except (TypeError, ValueError):
                valore = Decimal("0")
            ref: Optional[datetime] = None
            extra = item.get("extra") or {}
            raw_ref = (
                extra.get("posting_date")
                or item.get("updated_at")
                or item.get("last_update")
            )
            if raw_ref:
                try:
                    ref = datetime.fromisoformat(str(raw_ref).replace("Z", "+00:00"))
                except ValueError:
                    ref = None
            return [
                ProviderBalance(
                    saldo=valore,
                    valuta=str(item.get("currency_code") or "EUR").upper(),
                    tipo="current",
                    data_riferimento=ref,
                )
            ]
        return []

    def movimenti_conto(
        self,
        external_account_id: str,
        *,
        data_inizio: Optional[date] = None,
        data_fine: Optional[date] = None,
    ) -> List[ProviderTransaction]:
        """
        Salt Edge espone ``GET /transactions`` con paginazione via
        ``next_id``. Filtro primario: ``account_id``.
        """
        if not external_account_id:
            raise SaltEdgeError("account_id mancante per movimenti_conto.")

        risultato: List[ProviderTransaction] = []
        params: Dict[str, Any] = {"account_id": external_account_id}
        if data_inizio:
            params["from_date"] = data_inizio.isoformat()
        if data_fine:
            params["to_date"] = data_fine.isoformat()

        next_id: Optional[str] = None
        max_pagine = 20  # ~20 * 1000 (limite Salt Edge) di sicurezza
        for _ in range(max_pagine):
            if next_id:
                params["from_id"] = next_id
            data = self._get("/transactions", params=params)
            for raw in (data or {}).get("data") or []:
                parsed = self._parse_transaction(raw, pending=False)
                if parsed is not None:
                    risultato.append(parsed)
            paging = (data or {}).get("meta") or {}
            next_id = str((paging.get("next_id") or "")).strip() or None
            if not next_id:
                break

        # Transazioni pending (separate su v6 via param ?pending=true)
        try:
            pending_params: Dict[str, Any] = {
                "account_id": external_account_id,
                "pending": "true",
            }
            if data_inizio:
                pending_params["from_date"] = data_inizio.isoformat()
            if data_fine:
                pending_params["to_date"] = data_fine.isoformat()
            data_pending = self._get("/transactions", params=pending_params)
            for raw in (data_pending or {}).get("data") or []:
                parsed = self._parse_transaction(raw, pending=True)
                if parsed is not None:
                    risultato.append(parsed)
        except SaltEdgeError:
            # I movimenti pending sono opzionali: non blocchiamo la sync.
            pass

        return risultato

    def _parse_transaction(
        self, raw: Dict[str, Any], *, pending: bool
    ) -> Optional[ProviderTransaction]:
        if not isinstance(raw, dict):
            return None
        try:
            importo = Decimal(str(raw.get("amount", "0")))
        except (TypeError, ValueError):
            return None

        made_on = _parse_iso_date(raw.get("made_on"))
        if made_on is None:
            return None

        extra = raw.get("extra") or {}
        descrizione = str(
            raw.get("description")
            or extra.get("additional")
            or extra.get("information")
            or ""
        ).strip()
        controparte = str(
            extra.get("payee")
            or extra.get("payer")
            or extra.get("original_category")
            or raw.get("category")
            or ""
        ).strip()
        iban_controparte = str(
            extra.get("payee_information", {}).get("iban")
            if isinstance(extra.get("payee_information"), dict)
            else extra.get("payer_information", {}).get("iban")
            if isinstance(extra.get("payer_information"), dict)
            else extra.get("account_number") or ""
        ).replace(" ", "").upper()

        tx_id = str(raw.get("id") or "").strip()

        return ProviderTransaction(
            data_contabile=made_on,
            data_valuta=_parse_iso_date(extra.get("posting_date")) or made_on,
            importo=importo.quantize(Decimal("0.01")),
            valuta=str(raw.get("currency_code") or "EUR").upper(),
            descrizione=descrizione,
            controparte=controparte,
            iban_controparte=iban_controparte,
            provider_transaction_id=tx_id,
        )


# ======================================================================
#  Helper di modulo
# ======================================================================


def _today_utc() -> date:
    return datetime.now(tz=dt_timezone.utc).date()


def _date_giorni_fa(giorni: int) -> date:
    oggi = _today_utc()
    from datetime import timedelta

    return oggi - timedelta(days=int(max(0, giorni)))


def _parse_iso_date(raw: Any) -> Optional[date]:
    if not raw:
        return None
    try:
        text = str(raw).replace("Z", "+00:00")
        if "T" in text:
            return datetime.fromisoformat(text).date()
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _estrai_customer_id(raw: Any) -> str:
    """
    Estrae il ``customer_id`` da una response Salt Edge ``POST /customers``.

    Lo standard v6 documenta ``{"data": {"id": "<id>", "identifier": "..."}}``,
    ma il parsing qui e' permissivo per gestire anche:

    - ``{"data": [{"id": ...}]}``     (lista)
    - ``{"id": ...}``                 (senza wrapper data)
    - ``{"customer": {"id": ...}}``   (wrapper alternativo)
    - ``{"data": {"customer_id": ...}}``
    """
    if raw is None:
        return ""

    def _coerci(valore: Any) -> str:
        if valore is None:
            return ""
        return str(valore).strip()

    candidati: List[Any] = []
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, dict):
            candidati.append(data)
        elif isinstance(data, list):
            candidati.extend([x for x in data if isinstance(x, dict)])
        candidati.append(raw)
        customer_node = raw.get("customer")
        if isinstance(customer_node, dict):
            candidati.append(customer_node)

    for node in candidati:
        if not isinstance(node, dict):
            continue
        for key in ("id", "customer_id", "customerId"):
            cid = _coerci(node.get(key))
            if cid:
                return cid
    return ""


def _descrivi_esito_post(
    errore: Optional[SaltEdgeError],
    raw: Any,
) -> str:
    """Produce una riga diagnostica per il log/errore mostrato all'utente."""
    if errore is not None:
        return str(errore)
    # POST ok ma non siamo riusciti a trovare l'id: includiamo la shape della
    # response troncata cosi' il supporto puo' capire il formato reale.
    try:
        import json as _json

        snippet = _json.dumps(raw, default=str)[:400]
    except Exception:
        snippet = str(raw)[:400]
    return f"ok ma id vuoto. Response: {snippet}"
