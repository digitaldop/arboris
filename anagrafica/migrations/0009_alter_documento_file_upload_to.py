from django.db import migrations, models

import anagrafica.models


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0008_citta_codice_catastale_familiare_sesso_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documento",
            name="file",
            field=models.FileField(upload_to=anagrafica.models.documento_upload_to),
        ),
    ]
