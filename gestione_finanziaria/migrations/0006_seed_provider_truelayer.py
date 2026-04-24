from django.db import migrations


NOME_PROVIDER = "TrueLayer"


def seed_provider_truelayer(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")

    ProviderBancario.objects.get_or_create(
        nome=NOME_PROVIDER,
        defaults={
            "tipo": "psd2",
            "attivo": True,
            "configurazione": {
                "adapter": "truelayer",
                "environment": "sandbox",
                "country_default": "IT",
            },
            "note": (
                "Provider PSD2 (AIS) basato su TrueLayer Data API. Configura Client ID "
                "(secret_id) e Client Secret (secret_key) dalla sezione 'Connessioni PSD2' "
                "prima di collegare una banca. Il Redirect URI da autorizzare sulla console "
                "TrueLayer e' l'URL assoluto di '/gestione-finanziaria/connessioni/oauth-callback/'."
            ),
        },
    )


def unseed_provider_truelayer(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")
    ProviderBancario.objects.filter(nome=NOME_PROVIDER).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0005_connessionebancaria_access_token_scadenza_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_provider_truelayer, unseed_provider_truelayer),
    ]
