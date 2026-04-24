# Generated manually on 2026-04-22

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calendario", "0004_categoriacalendario_chiave_sistema_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="eventocalendario",
            old_name="ripeti_ogni_settimane",
            new_name="ripeti_ogni_intervallo",
        ),
        migrations.AlterField(
            model_name="eventocalendario",
            name="ripeti_ogni_intervallo",
            field=models.PositiveSmallIntegerField(
                default=1,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(365),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="eventocalendario",
            name="ripetizione",
            field=models.CharField(
                choices=[
                    ("nessuna", "Non si ripete"),
                    ("giornaliera", "Giornaliera"),
                    ("settimanale", "Settimanale"),
                    ("mensile", "Mensile"),
                    ("annuale", "Annuale"),
                ],
                default="nessuna",
                max_length=20,
            ),
        ),
    ]
