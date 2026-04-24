from django.db import migrations


NOME_PROVIDER = "GoCardless Bank Account Data"


def seed_provider_gocardless(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")

    ProviderBancario.objects.get_or_create(
        nome=NOME_PROVIDER,
        defaults={
            "tipo": "psd2",
            "attivo": True,
            "configurazione": {
                "adapter": "gocardless_bad",
                "base_url": "https://bankaccountdata.gocardless.com/api/v2",
                "country_default": "IT",
            },
            "note": (
                "Provider PSD2 (AIS) di default. Configura Secret ID e Secret Key dalla sezione "
                "'Connessioni PSD2' prima di collegare una banca."
            ),
        },
    )


def unseed_provider_gocardless(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")
    ProviderBancario.objects.filter(nome=NOME_PROVIDER).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0002_seed_provider_base"),
    ]

    operations = [
        migrations.RunPython(seed_provider_gocardless, unseed_provider_gocardless),
    ]
