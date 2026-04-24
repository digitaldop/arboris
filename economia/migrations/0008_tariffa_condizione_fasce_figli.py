from django.db import migrations, models


def initialize_ordine_figlio_a(apps, schema_editor):
    TariffaCondizioneIscrizione = apps.get_model("economia", "TariffaCondizioneIscrizione")
    for tariffa in TariffaCondizioneIscrizione.objects.order_by("pk"):
        tariffa.ordine_figlio_a = tariffa.ordine_figlio_da
        tariffa.save(update_fields=["ordine_figlio_a"])


class Migration(migrations.Migration):

    dependencies = [
        ("economia", "0007_condizioneiscrizione_giorno_scadenza_rate"),
    ]

    operations = [
        migrations.RenameField(
            model_name="tariffacondizioneiscrizione",
            old_name="ordine_figlio",
            new_name="ordine_figlio_da",
        ),
        migrations.AddField(
            model_name="tariffacondizioneiscrizione",
            name="ordine_figlio_a",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(initialize_ordine_figlio_a, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="tariffacondizioneiscrizione",
            options={
                "ordering": ["condizione_iscrizione", "ordine_figlio_da", "ordine_figlio_a", "id"],
                "verbose_name": "Tariffa condizione iscrizione",
                "verbose_name_plural": "Tariffe condizione iscrizione",
            },
        ),
    ]
