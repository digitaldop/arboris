from django.db import migrations


def seed_provider_base(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")

    ProviderBancario.objects.get_or_create(
        nome="Inserimento manuale",
        defaults={
            "tipo": "manuale",
            "attivo": True,
            "note": (
                "Provider di default per movimenti e conti inseriti manualmente "
                "dall'utente. Non richiede collegamenti esterni."
            ),
        },
    )

    ProviderBancario.objects.get_or_create(
        nome="Import file estratto conto",
        defaults={
            "tipo": "import_file",
            "attivo": True,
            "note": (
                "Provider per i conti alimentati tramite import di estratti conto "
                "in formato CAMT.053, MT940 o CSV."
            ),
        },
    )


def unseed_provider_base(apps, schema_editor):
    ProviderBancario = apps.get_model("gestione_finanziaria", "ProviderBancario")
    ProviderBancario.objects.filter(
        nome__in=["Inserimento manuale", "Import file estratto conto"],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_provider_base, unseed_provider_base),
    ]
