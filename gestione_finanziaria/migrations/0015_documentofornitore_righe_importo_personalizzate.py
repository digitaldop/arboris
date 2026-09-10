from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gestione_finanziaria", "0014_notifiche_import_stabili"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentofornitore",
            name="righe_importo_personalizzate",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
