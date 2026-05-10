from django.db import migrations


PROVIDERS = (
    {
        "nome": "Inserimento manuale",
        "tipo": "manuale",
        "configurazione": {},
        "note": (
            "Provider di default per movimenti e conti inseriti manualmente "
            "dall'utente. Non richiede collegamenti esterni."
        ),
    },
    {
        "nome": "Import file estratto conto",
        "tipo": "import_file",
        "configurazione": {},
        "note": (
            "Provider per i conti alimentati tramite import di estratti conto "
            "in formato CAMT.053, MT940, CSV o XLS."
        ),
    },
    {
        "nome": "GoCardless Bank Account Data",
        "tipo": "psd2",
        "configurazione": {
            "adapter": "gocardless_bad",
            "base_url": "https://bankaccountdata.gocardless.com/api/v2",
            "country_default": "IT",
        },
        "note": (
            "Provider PSD2 AIS. Configura Secret ID e Secret Key dalla sezione "
            "Connessioni PSD2 prima di collegare una banca."
        ),
    },
    {
        "nome": "TrueLayer",
        "tipo": "psd2",
        "configurazione": {
            "adapter": "truelayer",
            "environment": "sandbox",
            "country_default": "IT",
        },
        "note": (
            "Provider PSD2 AIS basato su TrueLayer Data API. Configura Client ID "
            "e Client Secret dalla sezione Connessioni PSD2."
        ),
    },
    {
        "nome": "Salt Edge",
        "tipo": "psd2",
        "configurazione": {
            "adapter": "saltedge",
            "country_default": "IT",
            "locale": "it",
            "include_fake_providers": False,
        },
        "note": (
            "Aggregatore PSD2 AIS basato su Salt Edge Account Information API. "
            "Copertura estesa per banche italiane retail e business."
        ),
    },
    {
        "nome": "Enable Banking",
        "tipo": "psd2",
        "configurazione": {
            "adapter": "enablebanking",
            "country_default": "IT",
            "psu_type": "personal",
        },
        "note": (
            "API Enable Banking AIS con autenticazione applicativa JWT RS256. "
            "Configura Application ID e private key PEM dalla sezione Connessioni PSD2."
        ),
    },
)


def seed_bank_providers(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")

    for provider in PROVIDERS:
        ProviderBancario.objects.using(db_alias).update_or_create(
            nome=provider["nome"],
            defaults={
                "tipo": provider["tipo"],
                "attivo": True,
                "configurazione": dict(provider["configurazione"]),
                "note": provider["note"],
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_bank_providers, migrations.RunPython.noop),
    ]
