from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gestione_finanziaria", "0010_documentofornitore_compensazione"),
    ]

    operations = [
        migrations.AddField(
            model_name="fattureincloudconnessione",
            name="periodo_import",
            field=models.CharField(
                choices=[("1", "1 mese"), ("3", "3 mesi"), ("6", "6 mesi"), ("9", "9 mesi"),
                         ("12", "Un anno"), ("tutte", "Tutte"), ("manuale", "Data manuale")],
                default="tutte", max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="fattureincloudconnessione", name="data_inizio_import",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fattureincloudconnessione", name="sync_progress",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
    ]
