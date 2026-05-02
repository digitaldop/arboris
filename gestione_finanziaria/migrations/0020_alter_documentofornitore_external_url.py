from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0019_fattureincloudconnessione_avviato_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentofornitore",
            name="external_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
    ]
