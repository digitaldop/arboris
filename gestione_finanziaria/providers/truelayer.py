"""
Adapter per TrueLayer Data API (PSD2 AIS).

Documentazione: https://docs.truelayer.com/docs/quickstart-data

Differenze principali rispetto all'adapter GoCardless:

- Flusso di autorizzazione **OAuth2 standard**: l'URL di autorizzazione e'
  costruito lato client (non c'e' un endpoint "crea requisition" come
  GoCardless); al ritorno il callback riceve ``?code=...&state=...`` e il
  codice va scambiato per un access_token + refresh_token.
- **Access token a breve durata** (1h), da rinnovare con il refresh_token
  (90 giorni di default). Per questo l'adapter accetta opzionalmente una
  ``ConnessioneBancaria`` (o un oggetto con i campi token cifrati) e
  gestisce il refresh in automatico.
- Endpoint separati per il **dominio auth** (auth.truelayer.com /
  auth.truelayer-sandbox.com) e per il **dominio data** (api.truelayer.com
  / api.truelayer-sandbox.com).

Il flusso implementato e':

1. :meth:`lista_istituti` chiama ``GET /api/providers/v3/auth/`` sul dominio
   auth (pubblico) per ottenere l'elenco dei provider bancari per paese.
2. :meth:`crea_connessione` *non* effettua alcuna chiamata: costruisce solo
   l'URL OAuth2 di autorizzazione. L'``external_connection_id`` e' lo
   stesso valore del parametro ``state`` (convenzione: ``arboris-{pk}``).
3. Il callback raccoglie ``code`` e chiama :meth:`scambia_codice_autorizzazione`
   per ottenere access_token + refresh_token.
4. :meth:`lista_conti`, :meth:`saldo_conto`, :meth:`movimenti_conto`
   richiedono una :class:`ConnessioneBancaria` per prelevare il token
   aggiornato (con auto-refresh se scaduto).
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone as dt_timezone
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


HTTP_TIMEOUT_SECONDS = 30

ENVIRONMENTS: Dict[str, Dict[str, str]] = {
    "sandbox": {
        "auth": "https://auth.truelayer-sandbox.com",
        "data": "https://api.truelayer-sandbox.com",
    },
    "live": {
        "auth": "https://auth.truelayer.com",
        "data": "https://api.truelayer.com",
    },
}


SCOPE_AIS = "info accounts balance transactions offline_access"


@dataclass
class TrueLayerCredentials:
    client_id: str
    client_secret: str
    environment: str = "sandbox"
    extra_scopes: List[str] = field(default_factory=list)
    # Lista di "providers" (space-separated) da richiedere a TrueLayer.
    # Se stringa vuota, l'adapter NON imposta il parametro 'providers'
    # nell'URL di autorizzazione; TrueLayer usera' allora la lista
    # configurata a livello di app nella Console (dove l'utente puo'
    # abilitare/disabilitare retail, business e corporate separatamente
    # per ciascun paese).
    providers_default: str = ""

    def endpoint(self, tipo: str) -> str:
        env = self.environment if self.environment in ENVIRONMENTS else "sandbox"
        return ENVIRONMENTS[env][tipo]


@dataclass
class TrueLayerTokens:
    """Token correnti associati a una connessione."""

    access_token: str = ""
    refresh_token: str = ""
    access_token_expires_at: Optional[datetime] = None


class TrueLayerError(RuntimeError):
    """Errore di comunicazione con TrueLayer."""


class TrueLayerAdapter(BasePsd2Adapter):
    nome_provider = "truelayer"

    def __init__(
        self,
        credentials: TrueLayerCredentials,
        tokens: Optional[TrueLayerTokens] = None,
    ):
        self.credentials = credentials
        self.tokens = tokens or TrueLayerTokens()

    # ------------------------------------------------------------------
    #  HTTP helpers
    # ------------------------------------------------------------------

    def _auth_url(self, path: str) -> str:
        base = self.credentials.endpoint("auth").rstrip("/")
        return f"{base}{path}"

    def _data_url(self, path: str) -> str:
        base = self.credentials.endpoint("data").rstrip("/")
        return f"{base}{path}"

    def _auth_headers(self) -> Dict[str, str]:
        self._ensure_access_token()
        return {
            "accept": "application/json",
            "Authorization": f"Bearer {self.tokens.access_token}",
        }

    def _is_token_expired(self) -> bool:
        if not self.tokens.access_token:
            return True
        scadenza = self.tokens.access_token_expires_at
        if scadenza is None:
            return False
        now = datetime.now(tz=dt_timezone.utc)
        if scadenza.tzinfo is None:
            scadenza = scadenza.replace(tzinfo=dt_timezone.utc)
        # margine di sicurezza di 30 secondi
        return scadenza - timedelta(seconds=30) <= now

    def _ensure_access_token(self) -> None:
        if not self.tokens.access_token or self._is_token_expired():
            if self.tokens.refresh_token:
                self.rinnova_access_token()
            else:
                raise TrueLayerError(
                    "Access token mancante o scaduto e nessun refresh_token disponibile."
                )

    def _get_data(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = requests.get(
            self._data_url(path),
            headers=self._auth_headers(),
            params=params,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code == 401 and self.tokens.refresh_token:
            # Il token potrebbe essere scaduto tra due richieste: proviamo un refresh e ritentiamo una volta.
            self.rinnova_access_token(force=True)
            resp = requests.get(
                self._data_url(path),
                headers=self._auth_headers(),
                params=params,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        if resp.status_code >= 400:
            raise TrueLayerError(
                f"GET {path} fallito ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    # ------------------------------------------------------------------
    #  Public OAuth helpers
    # ------------------------------------------------------------------

    def build_authorization_url(
        self,
        *,
        redirect_url: str,
        state: str,
        institution_id: str = "",
        providers_override: str = "",
    ) -> str:
        """
        Costruisce l'URL OAuth2 di autorizzazione.

        Precedenza per il parametro ``providers``:

        1. Se ``institution_id`` e' specificato, si passa come
           ``providers=<id>`` per saltare il selettore di TrueLayer.
        2. Se ``providers_override`` e' non vuoto, vince (usato dalla view).
        3. Altrimenti si usa ``credentials.providers_default`` se non vuoto.
        4. Se tutti i precedenti sono vuoti, il parametro ``providers`` viene
           OMESSO: TrueLayer usa allora la lista "Allowed providers"
           configurata a livello di app nella Console (dove si possono
           abilitare retail, business e corporate separatamente per ogni
           paese).
        """

        params = {
            "response_type": "code",
            "client_id": self.credentials.client_id,
            "scope": SCOPE_AIS
            + ("" if not self.credentials.extra_scopes else " " + " ".join(self.credentials.extra_scopes)),
            "redirect_uri": redirect_url,
            "state": state,
        }

        if institution_id:
            params["providers"] = institution_id
        elif providers_override:
            params["providers"] = providers_override
        elif self.credentials.providers_default:
            params["providers"] = self.credentials.providers_default
        # else: parametro omesso -> default dell'app su TrueLayer Console

        return f"{self._auth_url('/')}?{urllib.parse.urlencode(params, safe=' ')}"

    def scambia_codice_autorizzazione(
        self, code: str, *, redirect_url: str
    ) -> TrueLayerTokens:
        """Scambia il ``code`` OAuth2 per un access_token + refresh_token."""
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
            "redirect_uri": redirect_url,
            "code": code,
        }
        resp = requests.post(
            self._auth_url("/connect/token"),
            data=payload,
            headers={"accept": "application/json"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise TrueLayerError(
                f"Exchange code fallito ({resp.status_code}): {resp.text[:300]}"
            )
        self._apply_token_response(resp.json())
        return self.tokens

    def rinnova_access_token(self, *, force: bool = False) -> TrueLayerTokens:
        """Rinnova l'access_token usando il refresh_token."""
        if not self.tokens.refresh_token:
            raise TrueLayerError("Refresh token assente: impossibile rinnovare.")
        if not force and not self._is_token_expired():
            return self.tokens

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
            "refresh_token": self.tokens.refresh_token,
        }
        resp = requests.post(
            self._auth_url("/connect/token"),
            data=payload,
            headers={"accept": "application/json"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise TrueLayerError(
                f"Refresh token fallito ({resp.status_code}): {resp.text[:300]}"
            )
        self._apply_token_response(resp.json())
        return self.tokens

    def _apply_token_response(self, data: Dict[str, Any]) -> None:
        access = data.get("access_token", "") or ""
        refresh = data.get("refresh_token", "") or self.tokens.refresh_token
        expires_in = int(data.get("expires_in", 3600) or 3600)
        self.tokens = TrueLayerTokens(
            access_token=access,
            refresh_token=refresh,
            access_token_expires_at=datetime.now(tz=dt_timezone.utc)
            + timedelta(seconds=expires_in),
        )

    # ------------------------------------------------------------------
    #  BasePsd2Adapter - implementazione
    # ------------------------------------------------------------------

    # Fallback statico: TrueLayer non espone piu' pubblicamente l'elenco completo
    # dei provider, e l'approccio raccomandato e' lasciare che sia la loro UI
    # (dopo il redirect) a mostrare all'utente le banche disponibili.
    # Qui esponiamo un insieme minimo utile a guidare l'utente.
    _FALLBACK_ISTITUTI_SANDBOX: List[ProviderInstitution] = [
        ProviderInstitution(
            id="",
            name="(Scegli la banca nella pagina TrueLayer)",
            countries=["IT", "GB"],
        ),
        ProviderInstitution(
            id="uk-cs-mock",
            name="TrueLayer Mock Bank (sandbox)",
            countries=["GB"],
        ),
        ProviderInstitution(
            id="uk-ob-all",
            name="Tutte le banche UK Open Banking (sandbox)",
            countries=["GB"],
        ),
    ]

    _FALLBACK_ISTITUTI_LIVE: List[ProviderInstitution] = [
        ProviderInstitution(
            id="",
            name="(Scegli la banca nella pagina TrueLayer)",
            countries=["IT", "GB", "FR", "ES", "DE"],
        ),
    ]

    def lista_istituti(self, country: str = "IT") -> List[ProviderInstitution]:
        """
        Ritorna l'elenco dei provider bancari disponibili.

        TrueLayer oggi non espone un endpoint pubblico riutilizzabile: la lista
        completa e' sempre presentata nella loro UI di autorizzazione. In caso
        di fallimento della chiamata opzionale a ``/api/providers/v3/auth``,
        ritorniamo un set minimo statico e lasciamo che sia TrueLayer a mostrare
        il selettore completo (basta avviare la connessione con
        ``institution_id`` vuoto).
        """
        paese = (country or "IT").upper()

        # Tentativo best-effort sull'endpoint legacy: se esiste ancora ritorniamo
        # la lista ricca, altrimenti facciamo fallback statico.
        try:
            resp = requests.get(
                self._auth_url("/api/providers/v3/auth"),
                params={
                    "clientid": self.credentials.client_id,
                    "client_secret": self.credentials.client_secret,
                },
                headers={"accept": "application/json"},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if resp.status_code < 400:
                data = resp.json()
                raw_items: List[Dict[str, Any]]
                if isinstance(data, dict) and "results" in data:
                    raw_items = data.get("results") or []
                elif isinstance(data, list):
                    raw_items = data
                else:
                    raw_items = []

                risultato: List[ProviderInstitution] = []
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    countries_node = item.get("country") or item.get("countries") or []
                    if isinstance(countries_node, str):
                        countries = [countries_node.upper()]
                    elif isinstance(countries_node, list):
                        countries = [str(c).upper() for c in countries_node if c]
                    else:
                        countries = []

                    if paese and countries and paese not in countries:
                        continue

                    risultato.append(
                        ProviderInstitution(
                            id=str(item.get("provider_id") or item.get("id") or "").strip(),
                            name=str(item.get("display_name") or item.get("name") or "").strip(),
                            bic=str(item.get("bic") or "").strip(),
                            countries=countries,
                            logo_url=str(item.get("logo_url") or item.get("logo") or "").strip(),
                        )
                    )

                visti = set()
                dedup: List[ProviderInstitution] = []
                for inst in risultato:
                    key = inst.id
                    if key and key not in visti:
                        visti.add(key)
                        dedup.append(inst)

                if dedup:
                    return dedup
        except (requests.RequestException, ValueError):
            pass

        # Fallback statico (sandbox vs live).
        pool = (
            self._FALLBACK_ISTITUTI_SANDBOX
            if self.credentials.environment == "sandbox"
            else self._FALLBACK_ISTITUTI_LIVE
        )
        if not paese:
            return list(pool)
        return [
            inst
            for inst in pool
            if not inst.countries or paese in inst.countries
        ]

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
        In TrueLayer non c'e' un endpoint "crea requisition": l'autorizzazione
        e' un puro flusso OAuth2. Usiamo ``reference`` come ``state``: il
        callback lo ritrovera' per risalire alla nostra ConnessioneBancaria.
        """
        auth_url = self.build_authorization_url(
            redirect_url=redirect_url,
            state=reference,
            institution_id=institution_id,
        )
        return ProviderConnectionInfo(
            external_connection_id=reference,
            authorization_url=auth_url,
            institution_id=institution_id,
        )

    def lista_conti(self, external_connection_id: str) -> List[ProviderAccount]:
        data = self._get_data("/data/v1/accounts")
        raw = (data or {}).get("results") or []
        conti: List[ProviderAccount] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            number_node = item.get("account_number") or {}
            iban = str(number_node.get("iban") or "").strip()
            conti.append(
                ProviderAccount(
                    external_account_id=str(item.get("account_id") or "").strip(),
                    iban=iban,
                    currency=str(item.get("currency") or "EUR").upper(),
                    owner_name=str(item.get("display_name") or "").strip(),
                    name=str(item.get("display_name") or "").strip(),
                    institution_id=str(item.get("provider", {}).get("provider_id") or "").strip(),
                )
            )
        return conti

    def saldo_conto(self, external_account_id: str) -> List[ProviderBalance]:
        data = self._get_data(f"/data/v1/accounts/{external_account_id}/balance")
        saldi: List[ProviderBalance] = []
        for item in (data or {}).get("results") or []:
            if not isinstance(item, dict):
                continue
            try:
                valore = Decimal(str(item.get("current", "0")))
            except (TypeError, ValueError):
                valore = Decimal("0")
            ref_date = None
            updated = item.get("update_timestamp")
            if updated:
                try:
                    ref_date = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                except ValueError:
                    ref_date = None
            saldi.append(
                ProviderBalance(
                    saldo=valore,
                    valuta=str(item.get("currency") or "EUR").upper(),
                    tipo="current",
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
            params["from"] = data_inizio.isoformat()
        if data_fine:
            params["to"] = data_fine.isoformat()

        risultato: List[ProviderTransaction] = []

        # Endpoint "settled" (movimenti contabilizzati)
        data = self._get_data(
            f"/data/v1/accounts/{external_account_id}/transactions",
            params=params or None,
        )
        for raw in (data or {}).get("results") or []:
            parsed = self._parse_transaction(raw, pending=False)
            if parsed is not None:
                risultato.append(parsed)

        # Endpoint "pending" - potrebbe non essere disponibile in sandbox per tutti i provider.
        try:
            data_pending = self._get_data(
                f"/data/v1/accounts/{external_account_id}/transactions/pending"
            )
            for raw in (data_pending or {}).get("results") or []:
                parsed = self._parse_transaction(raw, pending=True)
                if parsed is not None:
                    risultato.append(parsed)
        except TrueLayerError:
            # L'assenza di transazioni pending non deve bloccare la sync.
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

        data_contabile = self._parse_iso_date(raw.get("timestamp"))
        if data_contabile is None:
            return None

        # TrueLayer espone "transaction_type" = DEBIT/CREDIT e amount sempre positivo.
        # Normalizziamo: negativo = uscita, positivo = entrata.
        tipo = str(raw.get("transaction_type") or "").upper()
        if tipo == "DEBIT" and importo > 0:
            importo = -importo

        descrizione = str(
            raw.get("description")
            or raw.get("transaction_category")
            or ""
        ).strip()

        meta = raw.get("meta") or {}
        controparte = str(
            meta.get("counter_party")
            or meta.get("provider_merchant_name")
            or raw.get("merchant_name")
            or ""
        ).strip()

        iban_controparte = str(
            (raw.get("running_balance") or {}).get("iban")
            or meta.get("counter_party_iban")
            or ""
        ).replace(" ", "").upper()

        tx_id = str(
            raw.get("transaction_id")
            or raw.get("normalised_provider_transaction_id")
            or raw.get("provider_transaction_id")
            or ""
        ).strip()

        return ProviderTransaction(
            data_contabile=data_contabile,
            data_valuta=data_contabile,
            importo=importo.quantize(Decimal("0.01")),
            valuta=str(raw.get("currency") or "EUR").upper(),
            descrizione=descrizione,
            controparte=controparte,
            iban_controparte=iban_controparte,
            provider_transaction_id=tx_id,
        )

    @staticmethod
    def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
        if not raw:
            return None
        try:
            text = str(raw).replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            return dt.date()
        except ValueError:
            try:
                return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
