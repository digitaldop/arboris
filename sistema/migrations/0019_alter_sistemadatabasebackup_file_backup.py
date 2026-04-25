from django.db import migrations, models

import sistema.models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0018_sistemautentepermessi_nessun_accesso"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sistemadatabasebackup",
            name="file_backup",
            field=models.FileField(upload_to=sistema.models.sistema_database_backup_upload_to),
        ),
    ]
