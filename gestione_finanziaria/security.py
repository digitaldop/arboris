"""
Cifratura simmetrica dei segreti della Gestione finanziaria.

Viene utilizzata per proteggere i token di accesso/refresh delle connessioni
PSD2 (`ConnessioneBancaria.access_token_cifrato`, `refresh_token_cifrato`) e
i secret dei provider salvati nel JSONField `ProviderBancario.configurazione`.

La chiave viene letta, in ordine:
1. dalla variabile d'ambiente ``ARBORIS_FERNET_KEY`` (chiave Fernet base64, 32 byte decoded);
2. dall'attributo ``GESTIONE_FINANZIARIA_FERNET_KEY`` in ``settings``;
3. in fallback viene derivata in modo deterministico da ``settings.SECRET_KEY``
   tramite SHA-256 (utile in sviluppo, da sostituire in produzione con una
   chiave dedicata e ruotabile).
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


_FERNET_SINGLETON: Optional[Fernet] = None


def _derive_key_from_secret(secret_key: str) -> bytes:
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _resolve_key() -> bytes:
    env_key = os.environ.get("ARBORIS_FERNET_KEY")
    if env_key:
        return env_key.encode("ascii") if isinstance(env_key, str) else env_key

    settings_key = getattr(settings, "GESTIONE_FINANZIARIA_FERNET_KEY", None)
    if settings_key:
        return settings_key.encode("ascii") if isinstance(settings_key, str) else settings_key

    return _derive_key_from_secret(settings.SECRET_KEY)


def get_fernet() -> Fernet:
    global _FERNET_SINGLETON
    if _FERNET_SINGLETON is None:
        _FERNET_SINGLETON = Fernet(_resolve_key())
    return _FERNET_SINGLETON


def cifra_testo(valore: str) -> str:
    """Cifra una stringa (tipicamente un token). Ritorna token base64 ASCII."""
    if valore is None or valore == "":
        return ""
    token = get_fernet().encrypt(valore.encode("utf-8"))
    return token.decode("ascii")


def decifra_testo(token: str) -> str:
    """Decifra un valore precedentemente passato a :func:`cifra_testo`.

    Se il token e' vuoto ritorna stringa vuota. Se la decifratura fallisce
    (chiave cambiata, dato corrotto) solleva :class:`cryptography.fernet.InvalidToken`.
    """
    if not token:
        return ""
    return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")


def decifra_testo_safe(token: str, default: str = "") -> str:
    """Variante che non solleva eccezioni in caso di token invalido."""
    if not token:
        return default
    try:
        return decifra_testo(token)
    except (InvalidToken, ValueError):
        return default
