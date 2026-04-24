"""
Segnali app: idempotenze di dati dopo le migrazioni.
"""

from django.apps import apps
from django.db.models.signals import post_migrate
from django.dispatch import receiver

_ENABLE_BANKING_NOME = "Enable Banking"
_ENABLE_BANKING_CONFIG = {
    "adapter": "enablebanking",
    "country_default": "IT",
    "psu_type": "personal",
}


@receiver(post_migrate)
def ensure_enable_banking_provider_exists(sender, app_config, **kwargs) -> None:
    """
    Garantisce la presenza del record PSD2 'Enable Banking' (come la migration
    0010). Utile se il DB e' stato creato/ripristinato senza quella migration
    o se ``migrate`` non e' mai stato lanciato dopo l'introduzione del seed.
    """
    if app_config.label != "gestione_finanziaria":
        return
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")
    ProviderBancario.objects.get_or_create(
        nome=_ENABLE_BANKING_NOME,
        defaults={
            "tipo": "psd2",
            "attivo": True,
            "configurazione": dict(_ENABLE_BANKING_CONFIG),
            "note": (
                "API Enable Banking (AIS) — autenticazione applicativa con JWT RS256. "
                "Registra l'applicazione nel control panel, carica la public key, "
                "inserisci l'Application ID (UUID) in 'Secret ID' e la private key PEM. "
                "Whitelista il redirect URI unico (callback_oauth_psd2) com'e' mostrato in "
                "configurazione. Il campo Secret Key del form non e' usato per questo "
                "provider."
            ),
        },
    )
