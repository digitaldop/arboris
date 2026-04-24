from django.db import migrations


NOME_PROVIDER = "Salt Edge"


def seed_provider_saltedge(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")

    ProviderBancario.objects.get_or_create(
        nome=NOME_PROVIDER,
        defaults={
            "tipo": "psd2",
            "attivo": True,
            "configurazione": {
                "adapter": "saltedge",
                "country_default": "IT",
                "locale": "it",
                # Di default lasciamo disattive le fake banks: l'utente
                # le puo' riattivare da UI quando lavora in ambiente Test.
                "include_fake_providers": False,
            },
            "note": (
                "Aggregatore PSD2 (AIS) basato su Salt Edge Account Information API v6. "
                "Copertura estesa per le banche italiane retail e business "
                "(Banco BPM, UniCredit, Intesa Sanpaolo, Banca Sella, BPER, etc.). "
                "Configura 'App-id' (secret_id) e 'Secret' (secret_key) dalla sezione "
                "'Connessioni PSD2' prima di collegare una banca. Nessun Redirect URI da "
                "whitelistare: Salt Edge usa un Widget hosted e torna al callback interno "
                "di Arboris. Per l'ambiente live potrebbe essere necessario disattivare "
                "la firma RSA delle richieste nel dashboard Salt Edge, oppure estendere "
                "l'adapter per supportarla."
            ),
        },
    )


def unseed_provider_saltedge(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")
    ProviderBancario.objects.filter(nome=NOME_PROVIDER).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0006_seed_provider_truelayer"),
    ]

    operations = [
        migrations.RunPython(seed_provider_saltedge, unseed_provider_saltedge),
    ]
