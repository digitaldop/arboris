"""
Registro adapter PSD2.

A partire da un'istanza :class:`ProviderBancario` restituisce l'adapter
concreto gia' configurato con le credenziali. Le credenziali sensibili
(``secret_key``, ``client_secret``) sono cifrate nel JSONField
``configurazione`` tramite :mod:`gestione_finanziaria.security`.

Formato atteso di ``ProviderBancario.configurazione`` per GoCardless BAD::

    {
        "adapter": "gocardless_bad",
        "secret_id": "...",
        "secret_key_cifrata": "...",
        "base_url": "https://...",
        "country_default": "IT"
    }

Formato atteso per TrueLayer::

    {
        "adapter": "truelayer",
        "secret_id": "<client_id>",
        "secret_key_cifrata": "<client_secret cifrato>",
        "environment": "sandbox" | "live",
        "country_default": "IT"
    }

Per gli adapter OAuth2 (TrueLayer), i token di singola connessione
(access_token, refresh_token) vivono su :class:`ConnessioneBancaria`,
non nel provider. L'adapter e' stateless rispetto ad essi finche' non
viene chiamato :func:`adapter_for_provider_with_connection`.

Formato atteso per Enable Banking (stesso campo PEM del form Salt Edge)::

    {
        "adapter": "enablebanking",
        "secret_id": "<application_id uuid>",
        "private_key_pem_cifrato": "<pem cifrato>",
        "private_key_passphrase_cifrata": "<opzionale>",
        "base_url": "https://api.enablebanking.com",
        "country_default": "IT",
        "psu_type": "personal" | "business"
    }

Il ``session_id`` autorizzato vive in ``ConnessioneBancaria.external_connection_id``.
"""

from __future__ import annotations

from typing import Optional

from ..models import ConnessioneBancaria, ProviderBancario, TipoProviderBancario
from ..security import decifra_testo_safe
from .base import BasePsd2Adapter
from .gocardless import GoCardlessBadAdapter, GoCardlessCredentials, DEFAULT_BASE_URL
from .saltedge import (
    DEFAULT_BASE_URL as SALTEDGE_DEFAULT_BASE_URL,
    SaltEdgeAdapter,
    SaltEdgeCredentials,
)
from .enablebanking import (
    DEFAULT_BASE_URL as ENABLEBANKING_DEFAULT_BASE_URL,
    EnableBankingAdapter,
    EnableBankingCredentials,
)
from .truelayer import TrueLayerAdapter, TrueLayerCredentials, TrueLayerTokens


ADAPTER_GOCARDLESS_BAD = "gocardless_bad"
ADAPTER_TRUELAYER = "truelayer"
ADAPTER_SALTEDGE = "saltedge"
ADAPTER_ENABLEBANKING = "enablebanking"


class ProviderConfigurazioneMancante(RuntimeError):
    """Sollevata quando il provider e' registrato ma non ha ancora le credenziali."""


def _adapter_id(provider: ProviderBancario) -> str:
    cfg = provider.configurazione or {}
    return cfg.get("adapter") or ADAPTER_GOCARDLESS_BAD


def _private_key_pem_cifrato_in_cfg(cfg: dict) -> str:
    """
    PEM cifrato come in ``configura_provider_psd2`` (``private_key_pem_cifrato``),
    con fallback a ``private_key_pem_cifrata`` per compatibilita' con versioni precedenti.
    """
    return (
        (cfg.get("private_key_pem_cifrato") or cfg.get("private_key_pem_cifrata") or "")
        .strip()
    )


def adapter_for_provider(
    provider: ProviderBancario,
    connessione: Optional[ConnessioneBancaria] = None,
) -> BasePsd2Adapter:
    """
    Ritorna l'adapter PSD2 configurato per ``provider``.

    Se ``connessione`` e' fornito (e il provider e' di tipo OAuth2 come
    TrueLayer), l'adapter viene inizializzato anche con i token di quella
    connessione cosi' le chiamate verso /accounts/ funzionano subito.
    """

    if provider.tipo != TipoProviderBancario.PSD2:
        raise ProviderConfigurazioneMancante(
            f"Il provider '{provider.nome}' non e' di tipo PSD2."
        )

    adapter_id = _adapter_id(provider)

    if adapter_id == ADAPTER_GOCARDLESS_BAD:
        return _build_gocardless_adapter(provider)

    if adapter_id == ADAPTER_TRUELAYER:
        return _build_truelayer_adapter(provider, connessione=connessione)

    if adapter_id == ADAPTER_SALTEDGE:
        return _build_saltedge_adapter(provider, connessione=connessione)

    if adapter_id == ADAPTER_ENABLEBANKING:
        return _build_enablebanking_adapter(provider)

    raise ProviderConfigurazioneMancante(
        f"Adapter '{adapter_id}' non supportato per il provider '{provider.nome}'."
    )


# --------------------------------------------------------------------------
#  GoCardless BAD
# --------------------------------------------------------------------------


def _build_gocardless_adapter(provider: ProviderBancario) -> GoCardlessBadAdapter:
    cfg = provider.configurazione or {}
    secret_id = cfg.get("secret_id") or ""
    secret_key_cifrata = cfg.get("secret_key_cifrata") or ""
    base_url = cfg.get("base_url") or DEFAULT_BASE_URL

    if not secret_id or not secret_key_cifrata:
        raise ProviderConfigurazioneMancante(
            f"Credenziali GoCardless mancanti per il provider '{provider.nome}'. "
            "Configura Secret ID e Secret Key prima di usare la connessione."
        )

    secret_key = decifra_testo_safe(secret_key_cifrata)
    if not secret_key:
        raise ProviderConfigurazioneMancante(
            f"Impossibile decifrare la Secret Key del provider '{provider.nome}'. "
            "Reimposta la chiave dalle impostazioni del provider."
        )

    return GoCardlessBadAdapter(
        credentials=GoCardlessCredentials(
            secret_id=secret_id,
            secret_key=secret_key,
            base_url=base_url,
        )
    )


# --------------------------------------------------------------------------
#  TrueLayer
# --------------------------------------------------------------------------


def _build_truelayer_adapter(
    provider: ProviderBancario,
    connessione: Optional[ConnessioneBancaria] = None,
) -> TrueLayerAdapter:
    cfg = provider.configurazione or {}
    client_id = cfg.get("secret_id") or ""
    client_secret_cifrato = cfg.get("secret_key_cifrata") or ""
    environment = (cfg.get("environment") or "sandbox").lower()
    if environment not in ("sandbox", "live"):
        environment = "sandbox"

    if not client_id or not client_secret_cifrato:
        raise ProviderConfigurazioneMancante(
            f"Credenziali TrueLayer mancanti per il provider '{provider.nome}'. "
            "Configura Client ID e Client Secret prima di usare la connessione."
        )

    client_secret = decifra_testo_safe(client_secret_cifrato)
    if not client_secret:
        raise ProviderConfigurazioneMancante(
            f"Impossibile decifrare il Client Secret del provider '{provider.nome}'. "
            "Reimposta la chiave dalle impostazioni del provider."
        )

    tokens: Optional[TrueLayerTokens] = None
    if connessione is not None:
        access = decifra_testo_safe(connessione.access_token_cifrato or "")
        refresh = decifra_testo_safe(connessione.refresh_token_cifrato or "")
        if access or refresh:
            tokens = TrueLayerTokens(
                access_token=access,
                refresh_token=refresh,
                access_token_expires_at=connessione.access_token_scadenza,
            )

    providers_default = (cfg.get("providers_default") or "").strip()

    return TrueLayerAdapter(
        credentials=TrueLayerCredentials(
            client_id=client_id,
            client_secret=client_secret,
            environment=environment,
            providers_default=providers_default,
        ),
        tokens=tokens,
    )


# --------------------------------------------------------------------------
#  Salt Edge
# --------------------------------------------------------------------------


def _build_saltedge_adapter(
    provider: ProviderBancario,
    connessione: Optional[ConnessioneBancaria] = None,
) -> SaltEdgeAdapter:
    cfg = provider.configurazione or {}
    # Convenzione nomi neutri (form e UI condivise con TrueLayer/GoCardless):
    # secret_id              = App-id Salt Edge
    # secret_key_cifrata     = Secret Salt Edge cifrata
    app_id = cfg.get("secret_id") or ""
    secret_cifrato = cfg.get("secret_key_cifrata") or ""
    base_url = cfg.get("base_url") or SALTEDGE_DEFAULT_BASE_URL
    include_fake = bool(cfg.get("include_fake_providers") or False)
    country_default = (cfg.get("country_default") or "IT").upper()
    locale = (cfg.get("locale") or "it").lower()

    if not app_id or not secret_cifrato:
        raise ProviderConfigurazioneMancante(
            f"Credenziali Salt Edge mancanti per il provider '{provider.nome}'. "
            "Configura App-id e Secret prima di usare la connessione."
        )

    secret = decifra_testo_safe(secret_cifrato)
    if not secret:
        raise ProviderConfigurazioneMancante(
            f"Impossibile decifrare il Secret Salt Edge del provider '{provider.nome}'. "
            "Reimposta la chiave dalle impostazioni del provider."
        )

    # Il customer_id vive sulla singola ConnessioneBancaria (viene creato al
    # primo avvio del flusso e riusato al callback). Lo conserviamo
    # cifrato nel campo ``access_token_cifrato`` per comodita'.
    customer_id = ""
    if connessione is not None:
        customer_id = decifra_testo_safe(connessione.access_token_cifrato or "") or ""

    # Private key RSA per la firma delle richieste Salt Edge (opzionale in
    # stato Pending/Test, obbligatoria in Live). Se presente, il PEM e'
    # cifrato con Fernet allo stesso modo degli altri secret.
    private_key_pem = ""
    private_key_cifrato = cfg.get("private_key_pem_cifrato") or ""
    if private_key_cifrato:
        private_key_pem = decifra_testo_safe(private_key_cifrato) or ""
    private_key_passphrase = ""
    passphrase_cifrata = cfg.get("private_key_passphrase_cifrata") or ""
    if passphrase_cifrata:
        private_key_passphrase = decifra_testo_safe(passphrase_cifrata) or ""

    return SaltEdgeAdapter(
        credentials=SaltEdgeCredentials(
            app_id=app_id,
            secret=secret,
            base_url=base_url,
            include_fake_providers=include_fake,
            country_default=country_default,
            locale=locale,
            private_key_pem=private_key_pem,
            private_key_passphrase=private_key_passphrase,
        ),
        customer_id=customer_id,
    )


# --------------------------------------------------------------------------
#  Enable Banking
# --------------------------------------------------------------------------


def _build_enablebanking_adapter(provider: ProviderBancario) -> EnableBankingAdapter:
    cfg = provider.configurazione or {}
    app_id = (cfg.get("secret_id") or "").strip()
    private_key_cifrata = _private_key_pem_cifrato_in_cfg(cfg)
    base_url = (cfg.get("base_url") or "").strip() or ENABLEBANKING_DEFAULT_BASE_URL
    country_default = (cfg.get("country_default") or "IT").upper()
    psu = (cfg.get("psu_type") or "personal").lower()
    if psu not in ("personal", "business"):
        psu = "personal"

    if not app_id or not private_key_cifrata:
        raise ProviderConfigurazioneMancante(
            f"Credenziali Enable Banking mancanti per il provider '{provider.nome}'. "
            "Configura Application ID (secret_id) e private key RSA PEM (campo cifrato) "
            "prima di usare la connessione."
        )

    private_key_pem = decifra_testo_safe(private_key_cifrata)
    if not private_key_pem:
        raise ProviderConfigurazioneMancante(
            f"Impossibile decifrare la private key Enable Banking per '{provider.nome}'. "
            "Reimposta la chiave dalle impostazioni del provider."
        )

    passphrase = ""
    passphrase_cifrata = (cfg.get("private_key_passphrase_cifrata") or "").strip()
    if passphrase_cifrata:
        passphrase = decifra_testo_safe(passphrase_cifrata) or ""

    return EnableBankingAdapter(
        credentials=EnableBankingCredentials(
            app_id=app_id,
            private_key_pem=private_key_pem,
            private_key_passphrase=passphrase,
            base_url=base_url,
            country_default=country_default,
            psu_type=psu,
        )
    )


# --------------------------------------------------------------------------
#  Helper UI
# --------------------------------------------------------------------------


def configurazione_completa(provider: Optional[ProviderBancario]) -> bool:
    if provider is None or provider.tipo != TipoProviderBancario.PSD2:
        return False
    cfg = provider.configurazione or {}
    if not (cfg.get("secret_id") or "").strip():
        return False
    if _adapter_id(provider) == ADAPTER_ENABLEBANKING:
        return bool(_private_key_pem_cifrato_in_cfg(cfg))
    return bool(cfg.get("secret_key_cifrata"))


def is_oauth_adapter(provider: ProviderBancario) -> bool:
    """True se il provider richiede scambio code -> token (es. TrueLayer)."""
    return _adapter_id(provider) == ADAPTER_TRUELAYER


def is_enablebanking_adapter(provider: ProviderBancario) -> bool:
    """True se il provider e' l'API Enable Banking (JWT + callback con code)."""
    return _adapter_id(provider) == ADAPTER_ENABLEBANKING


def is_redirect_callback_adapter(provider: ProviderBancario) -> bool:
    """
    True se il consenso richiede il callback fisso stile OAuth (stesso path per tutte
    le connessioni) con ``state=arboris-<pk>`` e ``code=``: TrueLayer, Enable Banking.
    """
    aid = _adapter_id(provider)
    return aid in (ADAPTER_TRUELAYER, ADAPTER_ENABLEBANKING)


def is_saltedge_adapter(provider: ProviderBancario) -> bool:
    """True se il provider usa il Widget Salt Edge per il consenso."""
    return _adapter_id(provider) == ADAPTER_SALTEDGE
