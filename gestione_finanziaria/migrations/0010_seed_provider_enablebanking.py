from django.db import migrations


NOME_PROVIDER = "Enable Banking"


def seed_provider_enablebanking(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")

    ProviderBancario.objects.get_or_create(
        nome=NOME_PROVIDER,
        defaults={
            "tipo": "psd2",
            "attivo": True,
            "configurazione": {
                "adapter": "enablebanking",
                "country_default": "IT",
                "psu_type": "personal",
            },
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


def unseed_provider_enablebanking(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")
    ProviderBancario.objects.filter(nome=NOME_PROVIDER).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0009_remove_sftp_inbox"),
    ]

    operations = [
        migrations.RunPython(seed_provider_enablebanking, unseed_provider_enablebanking),
    ]
