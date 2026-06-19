from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0007_fornitore_dipendente_collegato"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentofornitore",
            name="descrizione_righe_fattura",
            field=models.TextField(blank=True),
        ),
    ]
