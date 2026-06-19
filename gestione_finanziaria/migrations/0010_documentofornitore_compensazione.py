from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0009_documentofornitoreimportalias"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentofornitore",
            name="compensata_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documentofornitore",
            name="nota_credito_compensazione",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fatture_compensate",
                to="gestione_finanziaria.documentofornitore",
            ),
        ),
        migrations.AlterField(
            model_name="documentofornitore",
            name="stato",
            field=models.CharField(
                choices=[
                    ("da_pagare", "Da pagare"),
                    ("parzialmente_pagato", "Parzialmente pagato"),
                    ("pagato", "Pagato"),
                    ("compensato", "Compensato da nota di credito"),
                    ("annullato", "Annullato"),
                ],
                default="da_pagare",
                max_length=30,
            ),
        ),
    ]
